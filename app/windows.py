"""Captura da janela ativa e registro do atalho global no Windows."""

import ctypes
from ctypes import wintypes
import io
import os
import threading
from .services import UserError

def capture_active_window():
    """Captura a área visível da janela ativa e devolve PNG somente em memória."""
    if os.name != 'nt':
        raise UserError('A captura global requer Windows.')
    from PIL import ImageGrab
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsIconic.argtypes = [wintypes.HWND]
    hwnd = user32.GetForegroundWindow()
    rect = wintypes.RECT()
    if not hwnd or user32.IsIconic(hwnd) or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise UserError('Não foi possível identificar a janela ativa.')
    dwm_rect = wintypes.RECT()
    try:
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(dwm_rect), ctypes.sizeof(dwm_rect)) == 0:
            rect = dwm_rect
    except OSError:
        pass
    if rect.right <= rect.left or rect.bottom <= rect.top:
        raise UserError('A janela ativa não tem uma área visível.')
    with ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True) as image:
        image.thumbnail((2560, 2560))
        with io.BytesIO() as buffer:
            image.save(buffer, 'PNG')
            return buffer.getvalue()

class ScrollLockListener:
    """Registra Scroll Lock sem instalar um hook global de teclado."""

    def __init__(self, service):
        """Associa o ouvinte ao serviço de captura."""
        self.service = service
        self.thread_id = None

    def start(self):
        """Inicia a thread dedicada à mensagem de atalho do Windows."""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        """Registra Scroll Lock e encaminha cada evento ao serviço de captura."""
        if os.name != 'nt':
            self.service.hotkey_error = 'O atalho requer Windows.'
            return
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        # Register only this shortcut, without a broad keyboard hook.
        if not user32.RegisterHotKey(None, 1, 0x4000, 0x91):
            code = ctypes.get_last_error()
            self.service.hotkey_error_code = code
            self.service.hotkey_error = ('Scroll Lock já está em uso por outro aplicativo.' if code == 1409
                else f'O Windows não permitiu registrar Scroll Lock (erro {code}). Execute fora de um ambiente restrito.')
            return
        self.service.hotkey_ready = True
        try:
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam == 1:
                    self.service.trigger()
        finally:
            user32.UnregisterHotKey(None, 1)
            self.service.hotkey_ready = False

    def stop(self):
        """Encerra a fila de mensagens e aguarda a thread do atalho."""
        if self.thread_id and os.name == 'nt':
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            self.thread.join(timeout=2)
