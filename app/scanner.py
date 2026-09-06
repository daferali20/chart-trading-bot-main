from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from ib_async import ScannerSubscription
@dataclass(frozen=True)
class Candidate:
    symbol:str;rank:int;change_percent:float
def load_watchlist(path="watchlist.txt"):
    try:
        with open(path,encoding="utf-8") as f:return [x.strip().upper() for x in f if x.strip() and not x.lstrip().startswith("#")]
    except FileNotFoundError:return []
async def top_gainers(ib,number=10):
    sub=ScannerSubscription(instrument="STK",locationCode="STK.US.MAJOR",scanCode="TOP_PERC_GAIN",numberOfRows=max(number,10),abovePrice=1.0,aboveVolume=100000)
    rows=await ib.reqScannerDataAsync(sub);return [Candidate(r.contractDetails.contract.symbol,int(r.rank)+1,0.0) for r in rows[:number]]
def merge_candidates(gainers:Iterable[Candidate],custom:Iterable[str]):
    result=[]
    for c in gainers:
        if c.symbol not in result:result.append(c.symbol)
    for s in custom:
        if s not in result:result.append(s)
    return result
