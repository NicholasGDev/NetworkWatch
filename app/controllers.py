"""Rotas locais do painel, da captura e do monitor de rede."""

import secrets
from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session

views = Blueprint('views', __name__)

@views.before_request
def protect():
    """Restringe o servidor a loopback e exige sessão e CSRF nas alterações."""
    if request.host.split(':')[0] != '127.0.0.1':
        abort(403)
    if request.endpoint == 'views.bootstrap':
        return
    if not session.get('authenticated'):
        abort(401)
    if request.method == 'POST' and not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
        abort(403)

@views.get('/bootstrap')
def bootstrap():
    """Consome o token inicial de uso único e abre uma sessão autenticada."""
    expected = current_app.config.get('BOOT_TOKEN')
    if not expected or not secrets.compare_digest(request.args.get('token', ''), expected):
        abort(403)
    current_app.config['BOOT_TOKEN'] = None
    session.clear()
    session['authenticated'] = True
    session['csrf'] = secrets.token_urlsafe(32)
    return redirect('/')

@views.get('/')
def monitor():
    """Renderiza a página principal do monitoramento de rede."""
    return render_template('monitor.html')

@views.get('/app')
def index():
    """Renderiza o painel de respostas com o token CSRF da sessão."""
    return render_template('index.html', csrf=session['csrf'])

@views.get('/api/network')
def network():
    """Retorna a fotografia atual do monitor de rede local."""
    monitor = current_app.extensions.get('network')
    if monitor is None:
        abort(503)
    return jsonify(monitor.snapshot())

@views.get('/api/state')
def state():
    """Retorna o estado do serviço de captura e as respostas recentes."""
    service = current_app.extensions['capture']
    return jsonify(status=service.status(), answers=service.history.list())

@views.post('/api/pause')
def pause():
    """Valida a solicitação e pausa ou retoma capturas pelo atalho."""
    service = current_app.extensions['capture']
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or not isinstance(data.get('paused'), bool):
        abort(400)
    service.paused = data['paused']
    return jsonify(service.status())

@views.post('/api/clear')
def clear():
    """Remove do histórico as respostas que já não estão pendentes."""
    current_app.extensions['capture'].history.clear()
    return jsonify(ok=True)
