from __future__ import annotations
from datetime import datetime
from app.execution.models import PendingOrder
class OrderQueue:
    def __init__(self): self._items={}
    def put(self,symbol,signal,source="scanner"): self._items[symbol.upper()]=PendingOrder(symbol.upper(),signal,source,datetime.now().isoformat(timespec="seconds"))
    def remove(self,symbol): self._items.pop(symbol.upper(),None)
    def get(self,symbol): return self._items.get(symbol.upper())
    def values(self): return list(self._items.values())
    def __len__(self): return len(self._items)
