"""Criptografia local de configuração e histórico usando a DPAPI do Windows."""

import base64
import ctypes
import json
import os
from pathlib import Path
import tempfile
from ctypes import wintypes

PREFIX = 'dpapi:v1:'
CONFIG_SECRET_FIELDS = (
    'gemini_api_key', 'api_key', 'github_token', 'anthropic_api_key',
    'smtp_username', 'smtp_password', 'smtp_from', 'smtp_to', 'prompt',
)


class DataBlob(ctypes.Structure):
    """Representa o bloco de bytes exigido pelas funções de criptografia Win32."""

    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def is_protected(value):
    """Indica se o texto usa o formato versionado de dados DPAPI do app.

    Args:
        value: Texto a verificar.

    Returns:
        ``True`` quando o prefixo identifica conteúdo protegido.
    """
    return isinstance(value, str) and value.startswith(PREFIX)


def _blob(data):
    """Converte bytes em uma estrutura Win32 e mantém seu buffer vivo.

    Args:
        data: Conteúdo binário a associar à estrutura.

    Returns:
        Estrutura DPAPI e buffer compatível com a API Win32.
    """
    buffer = ctypes.create_string_buffer(data, len(data))
    return DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _crypt(data, purpose, protect):
    """Protege ou revela bytes com DPAPI e entropia vinculada à finalidade.

    Args:
        data: Conteúdo binário de entrada.
        purpose: Finalidade usada para separar dados protegidos.
        protect: ``True`` para criptografar; ``False`` para descriptografar.

    Returns:
        Conteúdo binário protegido ou revelado.
    """
    if os.name != 'nt':
        raise OSError('A proteção DPAPI requer Windows.')
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(('NetWatch:' + purpose).encode('utf-8'))
    output = DataBlob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    try:
        if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(output)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.string_at(output.data, output.size)
    finally:
        if output.data:
            kernel32.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))
        _ = source_buffer, entropy_buffer


def protect_text(value, purpose):
    """Protege texto UTF-8 e o serializa no formato versionado do aplicativo.

    Args:
        value: Texto confidencial em memória.
        purpose: Finalidade associada à proteção.

    Returns:
        Texto codificado com o prefixo de versão DPAPI.
    """
    if not isinstance(value, str):
        raise TypeError('O dado a proteger precisa ser texto.')
    encoded = _crypt(value.encode('utf-8'), purpose, True)
    return PREFIX + base64.urlsafe_b64encode(encoded).decode('ascii')


def unprotect_text(value, purpose):
    """Descriptografa texto DPAPI validando formato e finalidade de uso.

    Args:
        value: Texto codificado no formato DPAPI do aplicativo.
        purpose: Finalidade usada originalmente para proteger o valor.

    Returns:
        Texto original em UTF-8.

    Raises:
        ValueError: Formato ou prefixo de proteção inválido.
        OSError: DPAPI não conseguiu revelar o valor para esta finalidade.
    """
    if not is_protected(value):
        raise ValueError('O dado não contém uma proteção DPAPI reconhecida.')
    try:
        encoded = base64.urlsafe_b64decode(value[len(PREFIX):].encode('ascii'))
        return _crypt(encoded, purpose, False).decode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Não foi possível descriptografar o dado local.') from exc


def load_config(path):
    """Carrega a configuração e migra segredos em texto claro para DPAPI."""
    path = Path(path)
    if not path.exists():
        return {}
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(config, dict):
        raise ValueError('O arquivo de configuração precisa conter um objeto JSON.')

    changed = False
    for field in CONFIG_SECRET_FIELDS:
        value = config.get(field)
        if not isinstance(value, str) or not value:
            continue
        if is_protected(value):
            config[field] = unprotect_text(value, 'config:' + field)
        else:
            config[field] = value
            changed = True

    if changed:
        stored = dict(config)
        for field in CONFIG_SECRET_FIELDS:
            value = stored.get(field)
            if isinstance(value, str) and value and not is_protected(value):
                stored[field] = protect_text(value, 'config:' + field)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.netwatch-config-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(stored, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    return config
