"""Local command receipts. Never stores prompts, arguments, or tool output."""
import datetime as dt
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time


@contextmanager
def connect(root):
    path = Path(root) / "history.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=3)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, component TEXT, tool TEXT, started REAL, finished REAL, outcome TEXT, duration_ms INTEGER)")
    try:
        with db:
            yield db
    finally:
        db.close()


def started(root, identity, component, tool):
    with connect(root) as db:
        db.execute("INSERT OR REPLACE INTO commands VALUES (?, ?, ?, ?, NULL, 'running', NULL)",
                   (identity, component, str(tool)[:120], time.time()))
        db.execute("DELETE FROM commands WHERE started < ?", (time.time() - 7 * 86400,))
        db.execute("DELETE FROM commands WHERE id NOT IN (SELECT id FROM commands ORDER BY started DESC LIMIT 2000)")


def finished(root, identity, outcome):
    now = time.time()
    with connect(root) as db:
        db.execute("UPDATE commands SET finished=?, outcome=?, duration_ms=CAST((?-started)*1000 AS INTEGER) WHERE id=?",
                   (now, outcome, now, identity))


def recent(root, limit=80):
    if not (Path(root) / "history.sqlite3").exists():
        return []
    with connect(root) as db:
        db.execute("DELETE FROM commands WHERE started < ?", (time.time() - 7 * 86400,))
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM commands ORDER BY started DESC LIMIT ?", (min(max(limit, 1), 200),)).fetchall()
    return [{**dict(row), "at": dt.datetime.fromtimestamp(row["started"], dt.timezone.utc).isoformat()} for row in rows]


def clear(root):
    with connect(root) as db:
        db.execute("DELETE FROM commands")
