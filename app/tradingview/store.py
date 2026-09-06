from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class TradingViewSignalStore:
    def __init__(self, path="data/tradingview.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _db(self):
        return sqlite3.connect(self.path)

    def _init(self):
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS signals ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "symbol TEXT,action TEXT,price REAL,stop REAL,target REAL,"
                "score INTEGER,message TEXT,created_at TEXT,processed INTEGER DEFAULT 0)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS webhook_status ("
                "id INTEGER PRIMARY KEY CHECK(id=1),"
                "last_received_at TEXT,"
                "last_signal_id INTEGER,"
                "last_symbol TEXT,"
                "last_action TEXT,"
                "received_count INTEGER DEFAULT 0,"
                "failed_count INTEGER DEFAULT 0,"
                "last_error TEXT)"
            )
            db.execute("INSERT OR IGNORE INTO webhook_status(id) VALUES(1)")
            db.commit()

    def add(self, signal):
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO signals(symbol,action,price,stop,target,score,message,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    signal.symbol.upper(),
                    signal.action.upper(),
                    signal.price,
                    signal.stop,
                    signal.target,
                    signal.score,
                    signal.message,
                    created_at,
                ),
            )
            signal_id = cur.lastrowid
            db.execute(
                "UPDATE webhook_status SET last_received_at=?, last_signal_id=?, "
                "last_symbol=?, last_action=?, received_count=received_count+1, last_error=NULL WHERE id=1",
                (created_at, signal_id, signal.symbol.upper(), signal.action.upper()),
            )
            db.commit()
            return signal_id

    def record_failure(self, error: str):
        with self._db() as db:
            db.execute(
                "UPDATE webhook_status SET failed_count=failed_count+1, last_error=? WHERE id=1",
                (str(error)[:500],),
            )
            db.commit()

    def pending(self, limit=50):
        with self._db() as db:
            return db.execute(
                "SELECT id,symbol,action,price,stop,target,score,message "
                "FROM signals WHERE processed=0 ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_processed(self, signal_id):
        with self._db() as db:
            db.execute("UPDATE signals SET processed=1 WHERE id=?", (signal_id,))
            db.commit()

    def status(self):
        with self._db() as db:
            row = db.execute(
                "SELECT last_received_at,last_signal_id,last_symbol,last_action,"
                "received_count,failed_count,last_error FROM webhook_status WHERE id=1"
            ).fetchone()
            pending = db.execute("SELECT COUNT(*) FROM signals WHERE processed=0").fetchone()[0]
            processed = db.execute("SELECT COUNT(*) FROM signals WHERE processed=1").fetchone()[0]
            total = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

        return {
            "last_received_at": row[0] if row else None,
            "last_signal_id": row[1] if row else None,
            "last_symbol": row[2] if row else None,
            "last_action": row[3] if row else None,
            "received": int(row[4] or 0) if row else 0,
            "failed": int(row[5] or 0) if row else 0,
            "last_error": row[6] if row else None,
            "pending": int(pending),
            "processed": int(processed),
            "total": int(total),
        }
