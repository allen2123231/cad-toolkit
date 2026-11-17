"""Durable window names and explicit conversation handles; no global target.

Only Toolkit-managed connections are bound here. A handle is a routing identity,
not an assertion that an MCP transport represents a Codex chat.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

NAMES = {"rhino": "Rhino", "autocad": "AutoCAD", "inventor": "Inventor"}


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS windows (
                  id TEXT PRIMARY KEY, identity TEXT UNIQUE, kind TEXT, name TEXT,
                  live INTEGER, data TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS live_names ON windows(kind,name COLLATE NOCASE) WHERE live=1;
                CREATE TABLE IF NOT EXISTS requests (
                  id TEXT PRIMARY KEY, label TEXT, state TEXT, created REAL, binding_id TEXT);
                CREATE TABLE IF NOT EXISTS bindings (
                  id TEXT PRIMARY KEY, window_id TEXT, request_id TEXT UNIQUE, label TEXT,
                  active INTEGER, document_serial INTEGER, document_epoch INTEGER,
                  pending TEXT, busy INTEGER DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS one_owner ON bindings(window_id) WHERE active=1;
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / "windows.sqlite3", timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db
        finally:
            db.close()

    def sync(self, instances):
        """An enumeration is authoritative only for the supplied complete scan."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            identities = [json.dumps([i["kind"], i["pid"], i["processStart"], i["hwnd"], i.get("instance_id")], separators=(",", ":")) for i in instances]
            used = {kind: set() for kind in NAMES}
            for r in db.execute("SELECT kind,name,identity FROM windows"):
                if r["identity"] in identities: used[r["kind"]].add(r["name"].casefold())
            db.execute("UPDATE windows SET live=0")
            assigned = {kind: set() for kind in NAMES}
            for item, identity in zip(instances, identities):
                old = db.execute("SELECT * FROM windows WHERE identity=?", (identity,)).fetchone()
                if old:
                    name = old["name"]
                    if name.casefold() in assigned[item["kind"]]:
                        n = 1
                        while f'{NAMES[item["kind"]]} {n:02}'.casefold() in used[item["kind"]]: n += 1
                        name = f'{NAMES[item["kind"]]} {n:02}'
                        used[item["kind"]].add(name.casefold())
                    assigned[item["kind"]].add(name.casefold())
                    db.execute("UPDATE windows SET live=1,name=?,data=? WHERE id=?", (name, json.dumps(item), old["id"]))
                else:
                    n = 1
                    while f'{NAMES[item["kind"]]} {n:02}'.casefold() in used[item["kind"]]:
                        n += 1
                    name = f'{NAMES[item["kind"]]} {n:02}'
                    used[item["kind"]].add(name.casefold())
                    assigned[item["kind"]].add(name.casefold())
                    db.execute("INSERT INTO windows VALUES (?,?,?,?,1,?)", (uuid.uuid4().hex, identity, item["kind"], name, json.dumps(item)))
            db.execute("UPDATE bindings SET active=0 WHERE window_id IN (SELECT id FROM windows WHERE live=0)")
            db.execute("UPDATE requests SET state='expired' WHERE state='pending' AND created<?", (time.time()-300,))
        return self.windows()

    @staticmethod
    def window(row):
        return {**json.loads(row["data"]), "window_id": row["id"], "display_name": row["name"], "live": bool(row["live"])}

    def windows(self):
        with self.db() as db:
            result = [self.window(r) for r in db.execute("SELECT * FROM windows WHERE live=1 ORDER BY kind,name")]
            owners = {r["window_id"]: dict(r) for r in db.execute("SELECT * FROM bindings WHERE active=1")}
            quarantined = {r[0] for r in db.execute("SELECT window_id FROM bindings WHERE busy=-1")}
        for w in result:
            owner = owners.get(w["window_id"])
            w["quarantined"] = w["window_id"] in quarantined
            w["binding"] = ({k: owner[k] for k in ("id", "label", "busy")} | {"needs_confirmation": bool(owner["pending"])}) if owner else None
        return result

    def rename(self, window_id, name):
        name = name.strip()
        if not name or len(name) > 48 or any(ord(c) < 32 or c in "[]" for c in name):
            raise ValueError("名稱需為 1–48 個字，不能包含中括號或控制字元。")
        with self.db() as db:
            try:
                if not db.execute("UPDATE windows SET name=? WHERE id=? AND live=1", (name, window_id)).rowcount:
                    raise ValueError("這個視窗已關閉。")
            except sqlite3.IntegrityError:
                raise ValueError("同套軟體已有這個視窗名稱，請換一個名稱。") from None

    def request(self, label=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            number = db.execute("SELECT count(*) FROM requests").fetchone()[0]+1
            request_id = uuid.uuid4().hex
            label = (str(label).strip()[:48] if label else "") or f"連線 {number:02}"
            db.execute("INSERT INTO requests VALUES (?,?,'pending',?,NULL)", (request_id, label, time.time()))
        return {"request_id": request_id, "label": label, "code": request_id[:6].upper(), "state": "pending", "message": "請在 MCP Toolkit 選擇 Rhino 視窗；不要建立另一個要求。使用 get_window_binding 查詢本要求。"}

    def request_status(self, request_id):
        with self.db() as db:
            db.execute("UPDATE requests SET state='expired' WHERE state='pending' AND created<?", (time.time()-300,))
            row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                raise ValueError("找不到這個選窗要求。")
            result = dict(row)
        if result["binding_id"]:
            try:
                b = self.binding(result["binding_id"])
                result.update(window_name=b["window"]["display_name"], window_id=b["window_id"])
            except ValueError:
                result["state"] = "disconnected"
                result.pop("binding_id", None)
        return result

    def bind(self, request_id, window_id, replace_binding_id=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            req = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if not req or req["state"] != "pending" or time.time()-req["created"] > 300:
                raise ValueError("這個選窗要求已取消或逾時，請由原對話重新要求連線。")
            win = db.execute("SELECT * FROM windows WHERE id=? AND live=1 AND kind='rhino'", (window_id,)).fetchone()
            if not win:
                raise ValueError("這個 Rhino 視窗已關閉。")
            data = json.loads(win["data"])
            if db.execute("SELECT id FROM bindings WHERE window_id=? AND busy=-1", (window_id,)).fetchone():
                raise ValueError("先前指令結果未確認。請先檢查並儲存 Rhino 文件，再重新開啟 Rhino；此視窗暫不接受新連線。")
            if data.get("guard_protocol") != 1:
                raise ValueError("請更新 Rhino MCP 外掛並重新開啟 Rhino，才能使用視窗綁定。")
            binding_id = uuid.uuid4().hex
            if replace_binding_id:
                if not db.execute("SELECT id FROM bindings WHERE id=? AND window_id=? AND active=1", (replace_binding_id, window_id)).fetchone():
                    raise ValueError("原連線已改變，請重新檢查後轉交。")
                db.execute("UPDATE bindings SET active=0 WHERE id=?", (replace_binding_id,))
            try:
                db.execute("INSERT INTO bindings VALUES (?,?,?,?,1,?,?,NULL,0)", (binding_id, window_id, request_id, req["label"], data.get("document_serial", 0), data.get("document_epoch", 0)))
            except sqlite3.IntegrityError:
                raise ValueError("這個 Rhino 已由其他連線使用，請選擇其他視窗或明確轉交。") from None
            db.execute("UPDATE requests SET state='bound',binding_id=? WHERE id=?", (binding_id, request_id))
        return self.binding(binding_id)

    def binding(self, binding_id):
        with self.db() as db:
            b = db.execute("SELECT * FROM bindings WHERE id=? AND active=1", (binding_id,)).fetchone()
            w = db.execute("SELECT * FROM windows WHERE id=? AND live=1", (b["window_id"],)).fetchone() if b else None
        if not b or not w:
            raise ValueError("連線已解除或視窗已關閉，請重新要求選窗；此次工具未執行。")
        return {**dict(b), "window": self.window(w)}

    def cancel(self, request_id):
        with self.db() as db:
            db.execute("UPDATE requests SET state='cancelled' WHERE id=? AND state='pending'", (request_id,))

    def release(self, binding_id):
        with self.db() as db:
            db.execute("UPDATE bindings SET active=0,busy=CASE WHEN busy=-1 THEN -1 ELSE 0 END WHERE id=?", (binding_id,))

    def observe(self, binding_id, context):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            b = db.execute("SELECT * FROM bindings WHERE id=? AND active=1", (binding_id,)).fetchone()
            if not b or context.get("document_epoch") is None: return
            pending = json.loads(b["pending"]) if b["pending"] else {}
            if context["document_epoch"] < max(b["document_epoch"], pending.get("document_epoch", 0)): return
            if (b["document_serial"], b["document_epoch"]) != (context["document_serial"], context["document_epoch"]):
                db.execute("UPDATE bindings SET pending=? WHERE id=?", (json.dumps(context), binding_id))

    def confirm(self, binding_id, serial, epoch):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            b = db.execute("SELECT pending FROM bindings WHERE id=? AND active=1", (binding_id,)).fetchone()
            if not b or not b[0]:
                raise ValueError("沒有等待確認的文件。")
            pending = json.loads(b[0])
            if (pending["document_serial"], pending["document_epoch"]) != (serial, epoch):
                raise ValueError("文件再次切換，請重新確認。")
            db.execute("UPDATE bindings SET document_serial=?,document_epoch=?,pending=NULL WHERE id=?", (serial, epoch, binding_id))

    def panel(self):
        with self.db() as db:
            db.execute("UPDATE requests SET state='expired' WHERE state='pending' AND created<?", (time.time()-300,))
            requests = [dict(r) | {"code": r["id"][:6].upper()} for r in db.execute("SELECT * FROM requests WHERE state='pending' ORDER BY created")]
            confirmations = [dict(r) | {"context": json.loads(r["pending"])} for r in db.execute("SELECT b.*,w.name AS window_name FROM bindings b JOIN windows w ON w.id=b.window_id WHERE b.active=1 AND w.live=1 AND b.pending IS NOT NULL")]
        return {"requests": requests, "confirmations": confirmations, "windows": self.windows()}


@contextmanager
def window_lock(root, window_id, timeout=30):
    """Process-wide CAD serialization. OS releases this lock on process death."""
    import msvcrt
    if not window_id.isalnum():
        raise ValueError("Invalid window identity")
    folder = Path(root) / "window-locks"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (window_id+".lock")).open("a+b") as f:
        f.seek(0); f.write(b"0"); f.flush(); f.seek(0)
        deadline = time.monotonic()+timeout
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("視窗仍在執行指令，請稍後再試；此次要求未執行。")
                time.sleep(.05)
        try:
            yield
        finally:
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
