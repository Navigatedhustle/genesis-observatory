import json
import sqlite3
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.lock = threading.RLock()
        self.db.executescript("""CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, scope TEXT, actor TEXT, kind TEXT, data TEXT);
        CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL,world TEXT,kind TEXT,data TEXT);""")
        self.db.commit()

    def get(self, k, default=None):
        with self.lock:
            r = self.db.execute("SELECT value FROM kv WHERE key=?", (k,)).fetchone()
        return json.loads(r[0]) if r else default

    def put(self, k, v):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, json.dumps(v)))
            self.db.commit()

    def record(self, scope, actor, kind, data):
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO records(time,scope,actor,kind,data) VALUES(?,?,?,?,?)",
                (time.time(), scope, actor, kind, json.dumps(data)),
            )
            self.db.commit()
            return cur.lastrowid

    def records(self, scope=None, actor=None, limit=100):
        where = []
        args = []
        if scope is not None:
            where.append("scope=?")
            args.append(scope)
        if actor is not None:
            where.append("actor=?")
            args.append(actor)
        q = (
            "SELECT id,time,scope,actor,kind,data FROM records"
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY id DESC LIMIT ?"
        )
        with self.lock:
            rows = self.db.execute(q, args + [limit]).fetchall()
        return [
            dict(
                id=r[0],
                time=r[1],
                scope=r[2],
                actor=r[3],
                kind=r[4],
                data=json.loads(r[5]),
            )
            for r in rows
        ]

    def action(self, world, kind, data):
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO actions(time,world,kind,data) VALUES(?,?,?,?)",
                (time.time(), world, kind, json.dumps(data)),
            )
            self.db.commit()
            return cur.lastrowid

    def atomic_state(self, worlds, settings, actions, extra=None):
        with self.lock, self.db:
            for name, kind, data in actions:
                self.db.execute(
                    "INSERT INTO actions(time,world,kind,data) VALUES(?,?,?,?)",
                    (time.time(), name, kind, json.dumps(data)),
                )
            for k, v in [("worlds", worlds), ("settings", settings)] + list(
                (extra or {}).items()
            ):
                self.db.execute(
                    "INSERT OR REPLACE INTO kv VALUES(?,?)", (k, json.dumps(v))
                )

    def last_action_id(self, world):
        with self.lock:
            row = self.db.execute(
                "SELECT id FROM actions WHERE world=? ORDER BY id DESC LIMIT 1",
                (world,),
            ).fetchone()
        return row[0] if row else 0

    def action_rows(self, world, after=0):
        with self.lock:
            rows = self.db.execute(
                "SELECT id,kind,data FROM actions WHERE world=? AND id>? ORDER BY id",
                (world, after),
            ).fetchall()
        return [{"id": r[0], "kind": r[1], "data": json.loads(r[2])} for r in rows]

    def archive_memories(self, scope, tag):
        with self.lock, self.db:
            self.db.execute(
                "UPDATE records SET scope=? WHERE scope=? AND actor!=?",
                (scope + "/archive/" + tag, scope, "operator"),
            )
