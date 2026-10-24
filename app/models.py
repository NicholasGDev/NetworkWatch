import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from .secure_storage import is_protected, protect_text, unprotect_text

class History:
    def __init__(self, path):
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
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA secure_delete=ON')
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
            stored = protect_text(answer, 'history:answer') if answer else ''
            db.execute('UPDATE answers SET status=?, answer=? WHERE id=?', (status, stored, item_id))

    def email_result(self, item_id, status, error=''):
        with self.connect() as db:
            db.execute('UPDATE answers SET email_status=?, email_error=? WHERE id=?', (status, error, item_id))

    def list(self):
        with self.connect() as db:
            items = [dict(row) for row in db.execute('SELECT * FROM answers ORDER BY id DESC LIMIT 100')]
        for item in items:
            if is_protected(item['answer']):
                item['answer'] = unprotect_text(item['answer'], 'history:answer')
        return items

    def clear(self):
        with self.connect() as db:
            db.execute("DELETE FROM answers WHERE status != 'pending'")
