from __future__ import annotations
import pandas as pd
from app.config import settings
from app.analysis.patterns import detect_patterns
from app.strategy.signal import Signal
def evaluate_chart(df:pd.DataFrame)->Signal:
    if len(df)<80:return Signal("HOLD",0,("Not enough candles for chart analysis",),float(df.iloc[-1].close))
    r=df.iloc[-1];score=0;reasons=[];patterns=detect_patterns(df)
    if pd.notna(r.ema50_chart) and r.close>r.ema50_chart:score+=1;reasons.append("price above chart EMA50")
    if bool(r.above_cloud):score+=2;reasons.append("price above Ichimoku cloud")
    elif bool(r.below_cloud):score-=2;reasons.append("price below Ichimoku cloud")
    if pd.notna(r.williams_r):
        if -80<=r.williams_r<=-20:score+=1;reasons.append("Williams %R supports momentum")
        elif r.williams_r>-20:reasons.append("Williams %R is overbought")
    if pd.notna(r.mfi14):
        if 50<=r.mfi14<80:score+=1;reasons.append("MFI confirms positive money flow")
        elif r.mfi14>=80:reasons.append("MFI is overbought")
    if pd.notna(r.volume_ratio) and r.volume_ratio>=1.5:score+=2;reasons.append("volume >= 1.5x 20-bar average")
    elif pd.notna(r.volume_ratio) and r.volume_ratio>=1.0:score+=1;reasons.append("volume above 20-bar average")
    if "breakout" in patterns:score+=2;reasons.append("20-bar breakout")
    if "bullish_engulfing" in patterns:score+=1;reasons.append("bullish engulfing")
    if "bearish_engulfing" in patterns:score-=2;reasons.append("bearish engulfing")
    if "breakdown" in patterns:score-=2;reasons.append("20-bar breakdown")
    entry=float(r.close);atr=float(r.atr14) if pd.notna(r.atr14) else 0
    if score>=settings.min_score and atr>0:
        stop=entry-settings.atr_stop_mult*atr;target=entry+settings.reward_risk*(entry-stop);return Signal("BUY",score,tuple(reasons),entry,stop,target)
    if score<=-settings.min_score and atr>0:
        stop=entry+settings.atr_stop_mult*atr;target=entry-settings.reward_risk*(stop-entry);return Signal("SELL",score,tuple(reasons),entry,stop,target)
    return Signal("HOLD",score,tuple(reasons) or ("no high-quality setup",),entry)
