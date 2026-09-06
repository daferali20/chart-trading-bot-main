from dataclasses import dataclass
import pandas as pd
from app.config import settings
@dataclass(frozen=True)
class Signal:
    action:str;score:int;reasons:tuple[str,...];entry:float;stop:float|None=None;target:float|None=None
def analyze(df:pd.DataFrame)->Signal:
    if len(df)<60:return Signal("HOLD",0,("Not enough data",),float(df.iloc[-1].close))
    r=df.iloc[-1];score=0;reasons=[]
    if r.close>r.ema20>r.ema50:score+=1;reasons.append("EMA trend bullish")
    if 50<=r.rsi14<75:score+=1;reasons.append("RSI momentum confirmed")
    if pd.notna(r.volume20) and r.volume>r.volume20:score+=1;reasons.append("volume above average")
    if pd.notna(r.breakout_high) and r.close>r.breakout_high:score+=2;reasons.append("20-bar breakout")
    entry=float(r.close)
    if score>=settings.min_score and pd.notna(r.atr14) and r.atr14>0:
        stop=entry-settings.atr_stop_mult*float(r.atr14);target=entry+settings.reward_risk*(entry-stop);return Signal("BUY",score,tuple(reasons),entry,stop,target)
    return Signal("HOLD",score,tuple(reasons) or ("conditions not met",),entry)
