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
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def is_protected(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def _blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _crypt(data, purpose, protect):
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
    if not isinstance(value, str):
        raise TypeError('O dado a proteger precisa ser texto.')
    encoded = _crypt(value.encode('utf-8'), purpose, True)
    return PREFIX + base64.urlsafe_b64encode(encoded).decode('ascii')


def unprotect_text(value, purpose):
    if not is_protected(value):
        raise ValueError('O dado não contém uma proteção DPAPI reconhecida.')
    try:
        encoded = base64.urlsafe_b64decode(value[len(PREFIX):].encode('ascii'))
        return _crypt(encoded, purpose, False).decode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Não foi possível descriptografar o dado local.') from exc


def load_config(path):
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
