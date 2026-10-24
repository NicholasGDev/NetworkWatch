const $ = (id) => document.getElementById(id);

function rate(bps) {
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps'];
  let i = 0;
  while (bps >= 1000 && i < units.length - 1) { bps /= 1000; i++; }
  return (i ? bps.toFixed(bps < 10 ? 2 : 1) : Math.round(bps)) + ' ' + units[i];
}
function bytes(n) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return n.toFixed(i ? 1 : 0) + ' ' + units[i];
}
function duration(s) {
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return (d ? d + 'd ' : '') + h + 'h ' + String(m).padStart(2, '0') + 'm';
}
function cell(text, cls) {
  const td = document.createElement('td');
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}
function badge(text, cls) {
  const span = document.createElement('span');
  span.className = 'badge badge-sm ' + cls;
  span.textContent = text;
  return span;
}

function chart(history) {
  const w = 600, h = 180, pad = 8;
  const peak = Math.max(1000, ...history.flatMap(([, d, u]) => [d, u]));
  const x = (i) => history.length < 2 ? w : i * w / (history.length - 1);
  const y = (v) => h - pad - v / peak * (h - 2 * pad);
  const points = (k) => history.map((p, i) => x(i).toFixed(1) + ',' + y(p[k]).toFixed(1)).join(' ');
  $('down-line').setAttribute('points', points(1));
  $('up-line').setAttribute('points', points(2));
  $('down-area').setAttribute('d', history.length ? 'M0,' + h + ' L' + points(1).replaceAll(' ', ' L') + ' L' + w + ',' + h + ' Z' : '');
  $('peak').textContent = rate(peak);
}

function render(s) {
  $('host').textContent = s.hostname;
  $('uptime').textContent = duration(s.uptime);
  $('down').textContent = rate(s.down_bps);
  $('up').textContent = rate(s.up_bps);
  $('recv').textContent = bytes(s.total_recv);
  $('sent').textContent = bytes(s.total_sent);
  $('established').textContent = s.connections.established;
  $('listen').textContent = s.connections.listen;
  $('conn-total').textContent = s.connections.total;
  const observed = s.observed;
  $('observed-process').textContent = observed.process ? '— ' + observed.process : '';
  $('observed-error').textContent = observed.error || '';
  $('capture-error').textContent = observed.capture_error || 'Captura UDP/IPv4 por socket bruto ativa.';
  $('capture-error').className = 'text-xs ' + (observed.capture_error ? 'text-warning' : 'text-success');
  const rows = observed.endpoints.map((endpoint) => {
    const tr = document.createElement('tr');
    tr.append(cell(endpoint.protocol), cell(endpoint.ip, 'font-mono'), cell(endpoint.port, 'font-mono'),
      cell(endpoint.seconds_ago + 's', 'font-mono'));
    return tr;
  });
  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = cell(observed.process ? 'Nenhum IP remoto observável neste momento.' : 'Aguardando aplicativo ativo…',
      'text-base-content/40');
    td.colSpan = 4;
    tr.append(td);
    rows.push(tr);
  }
  $('observed').replaceChildren(...rows);

  const ok = s.latency.filter((t) => t.ok);
  const probed = s.latency.some((t) => t.ok !== null);
  $('latency').textContent = ok.length ? Math.round(ok.reduce((a, t) => a + t.ms, 0) / ok.length) + ' ms' : '—';
  $('latency-note').textContent = probed ? ok.length + ' de ' + s.latency.length + ' destinos respondendo' : 'Aguardando sondagem';

  $('ifaces').replaceChildren(...s.interfaces.map((i) => {
    const tr = document.createElement('tr');
    const status = document.createElement('td');
    status.append(badge(i.up ? 'Ativa' : 'Inativa', i.up ? 'badge-success' : 'badge-ghost'));
    tr.append(cell(i.name, 'max-w-48 truncate'), status, cell(i.ipv4 || '—', 'font-mono'),
      cell(i.speed_mbps ? i.speed_mbps + ' Mbps' : '—', 'text-right font-mono whitespace-nowrap'),
      cell(rate(i.down_bps), 'text-right font-mono whitespace-nowrap'), cell(rate(i.up_bps), 'text-right font-mono whitespace-nowrap'));
    return tr;
  }));

  $('targets').replaceChildren(...s.latency.map((t) => {
    const li = document.createElement('li');
    li.className = 'py-2 flex items-center justify-between gap-3';
    const name = document.createElement('div');
    const title = document.createElement('p'); title.className = 'text-sm'; title.textContent = t.name;
    const host = document.createElement('p'); host.className = 'text-xs font-mono text-base-content/40'; host.textContent = t.host;
    name.append(title, host);
    li.append(name, t.ok === null ? badge('aguardando', 'badge-ghost') : t.ok ? badge(t.ms + ' ms', t.ms < 80 ? 'badge-success' : 'badge-warning') : badge('sem resposta', 'badge-error'));
    return li;
  }));

  chart(s.history);
}

async function refresh() {
  try {
    const response = await fetch('/api/network');
    if (!response.ok) throw new Error();
    render(await response.json());
    $('live').className = 'badge badge-success badge-xs';
    $('live-text').textContent = 'Ao vivo';
  } catch {
    $('live').className = 'badge badge-error badge-xs';
    $('live-text').textContent = 'Sem dados do coletor';
  } finally {
    $('clock').textContent = new Date().toLocaleTimeString('pt-BR');
    setTimeout(refresh, 1000);
  }
}
refresh();
