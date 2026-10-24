import ctypes
import ipaddress
import os
import socket
import threading
import time
from collections import deque
import psutil

TARGETS = [('Cloudflare DNS', '1.1.1.1', 443), ('Google DNS', '8.8.8.8', 443), ('GitHub', 'github.com', 443)]
HIDDEN = ('loopback', 'pseudo')
BROWSERS = {'firefox.exe', 'chrome.exe', 'msedge.exe', 'brave.exe', 'opera.exe'}

def foreground_pid():
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pid = wintypes.DWORD()
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None

def process_group(pid):
    process = psutil.Process(pid)
    name = process.name()
    if any(parent.name().lower() == 'netwatch.exe' for parent in process.parents()):
        return 'netwatch.exe', set()
    if name.lower() in BROWSERS:
        while process.parent() and process.parent().name().lower() == name.lower():
            process = process.parent()
    pids = {process.pid}
    for child in process.children(recursive=True):
        pids.add(child.pid)
    return name, pids

def remote_address(address):
    try:
        ip = ipaddress.ip_address(address.split('%')[0])
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_unspecified or ip.is_multicast)

def normalized_ip(address):
    return ipaddress.ip_address(address.split('%')[0]).compressed

class NetworkMonitor:
    """Amostra tráfego a cada segundo e latência/conexões a cada `probe_every` amostras."""
    def __init__(self, counters=None, connect=socket.create_connection, targets=TARGETS, interval=1.0, probe_every=5,
                 connections=psutil.net_connections, foreground=foreground_pid, group=process_group):
        self.counters = counters or (lambda: {n: (c.bytes_sent, c.bytes_recv) for n, c in psutil.net_io_counters(pernic=True).items()})
        self.connect, self.targets, self.interval, self.probe_every = connect, targets, interval, probe_every
        self.get_connections, self.foreground, self.group = connections, foreground, group
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.history = deque(maxlen=60)
        self.rates = {}
        self.latency = [{'name': n, 'host': h, 'ms': None, 'ok': None} for n, h, _ in targets]
        self.connections = {'established': 0, 'listen': 0, 'total': 0}
        self.active_pid = None
        self.active_name = ''
        self.endpoints = {}
        self.udp_ports = {}
        self.local_ips = set()
        self.observe_error = None
        self.capture_error = 'Captura UDP indisponível até iniciar o monitor.'
        self.previous = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._probe_loop, daemon=True).start()
        threading.Thread(target=self._capture_packets, daemon=True).start()

    def stop(self):
        self.stop_event.set()

    def _run(self):
        while not self.stop_event.is_set():
            self.sample()
            self.observe()
            self.stop_event.wait(self.interval)

    def _probe_loop(self):
        while not self.stop_event.is_set():
            self.probe()
            self.stop_event.wait(self.interval * self.probe_every)

    def sample(self, now=None):
        now = time.monotonic() if now is None else now
        current = self.counters()
        if self.previous:
            before, then = self.previous
            elapsed = max(now - then, 1e-6)
            rates = {}
            for name, (sent, recv) in current.items():
                old_sent, old_recv = before.get(name, (sent, recv))
                rates[name] = (max(recv - old_recv, 0) * 8 / elapsed, max(sent - old_sent, 0) * 8 / elapsed)
            visible = [r for n, r in rates.items() if not any(h in n.lower() for h in HIDDEN)]
            with self.lock:
                self.rates = rates
                self.history.append((time.time(), sum(r[0] for r in visible), sum(r[1] for r in visible)))
        self.previous = (current, now)

    def probe(self):
        results = []
        for name, host, port in self.targets:
            start = time.perf_counter()
            try:
                with self.connect((host, port), timeout=2):
                    results.append({'name': name, 'host': host, 'ms': round((time.perf_counter() - start) * 1000, 1), 'ok': True})
            except OSError:
                results.append({'name': name, 'host': host, 'ms': None, 'ok': False})
        with self.lock:
            self.latency = results

    def observe(self):
        try:
            conns = self.get_connections('inet')
            pid = self.foreground()
            name, pids = self.group(pid) if pid else ('', set())
            ips = {normalized_ip(address.address) for addresses in psutil.net_if_addrs().values()
                   for address in addresses if address.family in (socket.AF_INET, socket.AF_INET6)}
        except (psutil.Error, OSError) as exc:
            with self.lock:
                self.observe_error = f'Não foi possível ler as conexões ({type(exc).__name__}).'
            return
        connections = {'established': sum(c.status == 'ESTABLISHED' for c in conns),
            'listen': sum(c.status == 'LISTEN' for c in conns), 'total': len(conns)}
        if pid == os.getpid() or name.lower() in ('netwatch.exe', 'netwatch-service.exe'):
            with self.lock:
                self.connections, self.observe_error = connections, None
            return
        ports = {}
        for c in conns:
            if c.type == socket.SOCK_DGRAM and c.laddr and c.pid is not None:
                ports.setdefault((normalized_ip(c.laddr.ip), c.laddr.port), set()).add(c.pid)
        now = time.monotonic()
        with self.lock:
            if pid != self.active_pid:
                self.endpoints.clear()
            self.active_pid, self.active_name = pid, name
            self.local_ips, self.udp_ports = ips, {
                key: owners for key, owners in ports.items() if len(owners) == 1 and owners <= pids
            }
            self.connections, self.observe_error = connections, None
            for c in conns:
                if c.pid not in pids or not c.raddr or not remote_address(c.raddr.ip):
                    continue
                protocol = 'UDP' if c.type == socket.SOCK_DGRAM else 'TCP'
                self.endpoints[(protocol, c.raddr.ip, c.raddr.port)] = now
            self.endpoints = {key: seen for key, seen in self.endpoints.items() if now - seen < 30}

    def _capture_packets(self):
        if os.name != 'nt':
            self.capture_error = 'Captura de pacotes requer Windows e Npcap.'
            return
        from scapy.all import conf, get_working_ifaces, sniff
        from scapy.error import Scapy_Exception
        conf.use_pcap = True
        if not conf.use_pcap:
            self.capture_error = 'Npcap não encontrado. Instale Npcap e reinicie o NetWatch para capturar UDP.'
            return
        try:
            stats = psutil.net_if_stats()
            interfaces = [iface for iface in get_working_ifaces()
                          if iface.name in stats and stats[iface.name].isup and iface.ip != '127.0.0.1']
            if not interfaces:
                raise OSError('Nenhuma interface de rede ativa encontrada.')
            self.capture_error = None
            while not self.stop_event.is_set():
                sniff(iface=interfaces, filter='udp', prn=self.on_packet, store=False, timeout=1)
        except (OSError, Scapy_Exception) as exc:
            self.capture_error = f'Falha na captura UDP ({type(exc).__name__}: {exc}).'

    def on_packet(self, packet):
        from scapy.layers.inet import IP, UDP
        from scapy.layers.inet6 import IPv6
        if not packet.haslayer(UDP):
            return
        layer = packet[IP] if packet.haslayer(IP) else packet[IPv6] if packet.haslayer(IPv6) else None
        if layer is None:
            return
        udp = packet[UDP]
        source, destination = normalized_ip(layer.src), normalized_ip(layer.dst)
        with self.lock:
            if source in self.local_ips:
                local_ip, port, remote_ip, remote_port = source, udp.sport, destination, udp.dport
            elif destination in self.local_ips:
                local_ip, port, remote_ip, remote_port = destination, udp.dport, source, udp.sport
            else:
                return
            if not remote_address(remote_ip):
                return
            if (local_ip, port) not in self.udp_ports and ('0.0.0.0', port) not in self.udp_ports and ('::', port) not in self.udp_ports:
                return
            self.endpoints[('UDP', remote_ip, remote_port)] = time.monotonic()

    def snapshot(self):
        with self.lock:
            rates, history = dict(self.rates), list(self.history)
            latency, connections = list(self.latency), dict(self.connections)
            now = time.monotonic()
            peers = sorted(((proto, ip, port, seen) for (proto, ip, port), seen in self.endpoints.items()
                if now - seen < 30), key=lambda item: item[3], reverse=True)[:100]
            observed = {'process': self.active_name, 'endpoints': [
                {'protocol': proto, 'ip': ip, 'port': port, 'seconds_ago': int(now - seen)}
                for proto, ip, port, seen in peers], 'error': self.observe_error, 'capture_error': self.capture_error}
        stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
        interfaces = []
        for name, stat in stats.items():
            if any(h in name.lower() for h in HIDDEN):
                continue
            ipv4 = next((a.address for a in addrs.get(name, []) if a.family == socket.AF_INET), '')
            down, up = rates.get(name, (0.0, 0.0))
            interfaces.append({'name': name, 'up': stat.isup, 'speed_mbps': stat.speed, 'ipv4': ipv4, 'down_bps': down, 'up_bps': up})
        interfaces.sort(key=lambda i: (not i['up'], -(i['down_bps'] + i['up_bps']), i['name']))
        totals = psutil.net_io_counters()
        last = history[-1] if history else (time.time(), 0.0, 0.0)
        return {'hostname': socket.gethostname(), 'down_bps': last[1], 'up_bps': last[2],
            'total_recv': totals.bytes_recv, 'total_sent': totals.bytes_sent,
            'history': [[round(t), d, u] for t, d, u in history], 'interfaces': interfaces,
            'latency': latency, 'connections': connections, 'observed': observed,
            'uptime': int(time.time() - psutil.boot_time())}
