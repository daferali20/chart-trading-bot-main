from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path

class OrderStore:
    def __init__(self,path="data/orders.sqlite3"):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._init_db()
    def _connect(self): return sqlite3.connect(self.path)
    def _init_db(self):
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT UNIQUE, symbol TEXT NOT NULL, action TEXT NOT NULL, quantity INTEGER NOT NULL, entry REAL, stop REAL, target REAL, status TEXT NOT NULL, source TEXT, created_at TEXT NOT NULL, filled_quantity REAL DEFAULT 0)")
            db.commit()
    def record(self,order_id,symbol,action,quantity,entry,stop,target,status,source,filled_quantity=0.0):
        with self._connect() as db:
            db.execute("INSERT INTO orders(order_id,symbol,action,quantity,entry,stop,target,status,source,created_at,filled_quantity) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(order_id) DO UPDATE SET status=excluded.status,filled_quantity=excluded.filled_quantity",(order_id,symbol.upper(),action.upper(),quantity,entry,stop,target,status,source,datetime.now().isoformat(timespec="seconds"),filled_quantity))
            db.commit()
    def executed_count(self,scope="DAY"):
        with self._connect() as db:
            if scope.upper()=="DAY":
                row=db.execute("SELECT COUNT(*) FROM orders WHERE status='FILLED' AND substr(created_at,1,10)=?",(datetime.now().strftime("%Y-%m-%d"),)).fetchone()
            else: row=db.execute("SELECT COUNT(*) FROM orders WHERE status='FILLED'").fetchone()
            return int(row[0] or 0)
