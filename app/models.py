import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

class History:
    def __init__(self, path):
        self.path = str(path)
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

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self):
        with self.connect() as db:
            return db.execute("INSERT INTO answers(created,status) VALUES (?, 'pending')", (datetime.now(timezone.utc).isoformat(),)).lastrowid

    def finish(self, item_id, status, answer):
        with self.connect() as db:
            db.execute('UPDATE answers SET status=?, answer=? WHERE id=?', (status, answer, item_id))

    def email_result(self, item_id, status, error=''):
        with self.connect() as db:
            db.execute('UPDATE answers SET email_status=?, email_error=? WHERE id=?', (status, error, item_id))

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM answers ORDER BY id DESC LIMIT 100')]

    def clear(self):
        with self.connect() as db:
            db.execute("DELETE FROM answers WHERE status != 'pending'")
