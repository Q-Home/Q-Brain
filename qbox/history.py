import json
import sqlite3
import time


class History:
    def __init__(self, path, max_rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.max_rows = max_rows
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)")
        self.db.commit()

    def append(self, kind, payload):
        with self.db:
            self.db.execute("INSERT INTO events(timestamp,kind,payload) VALUES(?,?,?)", (time.time(), kind, json.dumps(payload, allow_nan=False)))
            self.db.execute("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT ?)", (self.max_rows,))

    def recent(self, limit=20):
        return [{"timestamp": stamp, "kind": kind, "payload": json.loads(payload)} for stamp, kind, payload in
                self.db.execute("SELECT timestamp,kind,payload FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    def latest(self, kind):
        row = self.db.execute('SELECT timestamp,payload FROM events WHERE kind=? ORDER BY id DESC LIMIT 1', (kind,)).fetchone()
        return {'timestamp':row[0], 'payload':json.loads(row[1])} if row else None

    def close(self):
        self.db.close()
