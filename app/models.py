"""Persistência local do histórico de respostas em SQLite."""

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from .secure_storage import is_protected, protect_text, unprotect_text

class History:
    """Gerencia respostas, estados de entrega e criptografia do histórico."""

    def __init__(self, path):
        """Abre ou migra o banco e protege respostas antigas em texto claro.

        Args:
            path: Caminho do arquivo SQLite do histórico.
        """
        self.path = str(path)
        migrated_answers = False
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY KEY, created TEXT NOT NULL, status TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '')")
            columns = {row['name'] for row in db.execute('PRAGMA table_info(answers)')}
            if 'email_status' not in columns:
                db.execute("ALTER TABLE answers ADD COLUMN email_status TEXT NOT NULL DEFAULT 'disabled'")
            if 'email_error' not in columns:
                db.execute("ALTER TABLE answers ADD COLUMN email_error TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE answers SET status='error', answer=? WHERE status='pending'", ('App fechado antes de concluir a resposta.',))
            db.execute("UPDATE answers SET email_status='error', email_error=? WHERE email_status='sending'",
                ('Entrega de e-mail não confirmada após reinício. Confira a caixa de entrada.',))
            for row in db.execute("SELECT id, answer FROM answers WHERE answer != ''").fetchall():
                if not is_protected(row['answer']):
                    db.execute('UPDATE answers SET answer=? WHERE id=?',
                        (protect_text(row['answer'], 'history:answer'), row['id']))
                    migrated_answers = True
        if migrated_answers:
            with closing(sqlite3.connect(self.path, timeout=10)) as db:
                db.execute('PRAGMA secure_delete=ON')
                db.execute('VACUUM')

    @contextmanager
    def connect(self):
        """Fornece uma conexão transacional e sempre fecha o banco SQLite.

        Yields:
            Conexão SQLite ativa dentro de um contexto transacional.
        """
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA secure_delete=ON')
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self):
        """Cria uma resposta pendente e retorna seu identificador.

        Returns:
            Identificador numérico da nova resposta.
        """
        with self.connect() as db:
            return db.execute("INSERT INTO answers(created,status) VALUES (?, 'pending')", (datetime.now(timezone.utc).isoformat(),)).lastrowid

    def finish(self, item_id, status, answer):
        """Atualiza o estado e grava o texto da resposta protegido por DPAPI.

        Args:
            item_id: Identificador da resposta no histórico.
            status: Estado final da captura.
            answer: Texto da resposta ou da mensagem de erro.
        """
        with self.connect() as db:
            stored = protect_text(answer, 'history:answer') if answer else ''
            db.execute('UPDATE answers SET status=?, answer=? WHERE id=?', (status, stored, item_id))

    def email_result(self, item_id, status, error=''):
        """Registra o estado da entrega SMTP e uma mensagem de erro segura.

        Args:
            item_id: Identificador da resposta associada ao envio.
            status: Estado da entrega SMTP.
            error: Mensagem segura a exibir se a entrega falhou.
        """
        with self.connect() as db:
            db.execute('UPDATE answers SET email_status=?, email_error=? WHERE id=?', (status, error, item_id))

    def list(self):
        """Retorna as últimas respostas, descriptografando o texto para a UI.

        Returns:
            Respostas recentes com campos de estado e conteúdo em memória.
        """
        with self.connect() as db:
            items = [dict(row) for row in db.execute('SELECT * FROM answers ORDER BY id DESC LIMIT 100')]
        for item in items:
            if is_protected(item['answer']):
                item['answer'] = unprotect_text(item['answer'], 'history:answer')
        return items

    def clear(self):
        """Apaga respostas concluídas e preserva as solicitações pendentes."""
        with self.connect() as db:
            db.execute("DELETE FROM answers WHERE status != 'pending'")
