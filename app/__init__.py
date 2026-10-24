import secrets
from flask import Flask
from .controllers import views

def create_app(service, boot_token, network=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), BOOT_TOKEN=boot_token,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict', MAX_CONTENT_LENGTH=4096)
    app.extensions['capture'] = service
    app.extensions['network'] = network
    app.register_blueprint(views)
    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response
    return app
