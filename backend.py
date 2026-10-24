"""Compõe e executa o backend local do NetWatch no Windows."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import secrets
import shutil
from app import create_app
from app.models import History
from app.email import SMTPEmailSender
from app.secure_storage import load_config
from app.network import NetworkMonitor
from app.services import CaptureService, ClaudeVisionClient, FallbackVision, GeminiVisionClient, GitHubModelsVisionClient, VisionClient
from app.windows import ScrollLockListener, capture_active_window

DEFAULT_PROMPT = 'Analise a captura. Se houver uma pergunta, responda diretamente e explique brevemente. Caso contrário, resuma o conteúdo relevante. Não invente texto ilegível.'
DATA_FILES = ('config.json', 'history.sqlite3')

def data_folder(environ=os.environ):
    """Cria a pasta atual e migra arquivos legados sem sobrescrever dados.

    Args:
        environ: Variáveis de ambiente usadas para resolver o diretório local.

    Returns:
        Caminho da pasta de dados do usuário.
    """
    if environ.get('SCROLLANSWER_DATA_DIR'):
        folder = Path(environ['SCROLLANSWER_DATA_DIR'])
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    base = Path(environ.get('LOCALAPPDATA', str(Path.home())))
    folder, legacy = base / 'NetWatch', base / 'ScrollAnswer'
    folder.mkdir(parents=True, exist_ok=True)
    # Migra chaves e histórico da instalação antiga, sem sobrescrever dados novos.
    for name in DATA_FILES:
        if (legacy / name).exists() and not (folder / name).exists():
            shutil.move(str(legacy / name), str(folder / name))
    return folder

def main():
    """Carrega a configuração e inicia servidor, coletor e atalho.

    Returns:
        None: O servidor permanece ativo até o processo ser encerrado.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-hotkey', action='store_true')
    args = parser.parse_args()
    if os.name == 'nt':
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    folder = data_folder()
    path = folder / 'config.json'
    config = load_config(path)
    prompt = config.get('prompt', DEFAULT_PROMPT)
    gemini = GeminiVisionClient(os.environ.get('GEMINI_API_KEY') or config.get('gemini_api_key', ''),
        os.environ.get('GEMINI_MODEL') or config.get('gemini_model', 'gemini-3.5-flash'), prompt)
    openai =VisionClient(os.environ.get('OPENAI_API_KEY') or config.get('api_key', ''),
        os.environ.get('OPENAI_MODEL') or config.get('model', 'gpt-4.1-mini'), prompt)
    github = GitHubModelsVisionClient(os.environ.get('GITHUB_TOKEN') or config.get('github_token', ''),
        os.environ.get('GITHUB_MODEL') or config.get('github_model', 'openai/gpt-6-luna'), prompt)
    claude = ClaudeVisionClient(os.environ.get('ANTHROPIC_API_KEY') or config.get('anthropic_api_key', ''),
        os.environ.get('ANTHROPIC_MODEL') or config.get('anthropic_model', 'claude-opus-5-5'), prompt)
    client = FallbackVision(gemini, openai, github, claude)
    smtp_keys = ('smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_to', 'smtp_from', 'smtp_security')
    smtp = {key: os.environ.get(key.upper()) or config.get(key) for key in smtp_keys}
    email_sender = None
    email_config_error = None
    if any(smtp.values()):
        missing = [key.upper() for key in ('smtp_host', 'smtp_username', 'smtp_password', 'smtp_to') if not smtp[key]]
        if missing:
            email_config_error = 'E-mail não configurado: faltam ' + ', '.join(missing) + '.'
        else:
            try:
                email_sender = SMTPEmailSender(smtp['smtp_host'], int(smtp['smtp_port'] or 465),
                    smtp['smtp_username'], smtp['smtp_password'], smtp['smtp_to'],
                    smtp['smtp_from'], smtp['smtp_security'] or 'ssl')
            except (ValueError, TypeError) as exc:
                email_config_error = f'E-mail não configurado: {exc}'
    service = CaptureService(History(folder / 'history.sqlite3'), client, capture_active_window,
        email_sender=email_sender, email_config_error=email_config_error)
    token = secrets.token_urlsafe(32)
    network = NetworkMonitor()
    network.start()
    app = create_app(service, token, network)
    from waitress import create_server
    server = create_server(app, host='127.0.0.1', port=0, threads=4)
    listener = ScrollLockListener(service)
    if not args.no_hotkey:
        listener.start()
    print(json.dumps({'url': f'http://127.0.0.1:{server.effective_port}/bootstrap?token={token}'}), flush=True)
    try:
        server.run()
    finally:
        listener.stop()
        network.stop()
        server.close()

if __name__ == '__main__':
    main()
