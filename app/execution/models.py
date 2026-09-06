from dataclasses import dataclass
from typing import Any
@dataclass(frozen=True)
class ExecutionDecision:
    allowed:bool
    reason:str
    positions:tuple[dict[str,Any],...]=()
    open_orders:tuple[Any,...]=()
    executed_count:int=0
    active_positions:int=0
    open_order_count:int=0
@dataclass
class PendingOrder:
    symbol:str
    signal:Any
    source:str="scanner"
    created_at:str=""
    attempts:int=0
