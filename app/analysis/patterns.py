from __future__ import annotations
import pandas as pd
def detect_patterns(df:pd.DataFrame)->list[str]:
    if len(df)<5:return []
    r=df.iloc[-1];p=df.iloc[-2];patterns=[];body=abs(float(r.close-r.open));rng=float(r.high-r.low)
    if rng>0 and body/rng<0.15:patterns.append("doji")
    if p.close<p.open and r.close>r.open and r.close>=p.open and r.open<=p.close:patterns.append("bullish_engulfing")
    if p.close>p.open and r.close<r.open and r.open>=p.close and r.close<=p.open:patterns.append("bearish_engulfing")
    if pd.notna(r.breakout_high) and r.close>r.breakout_high:patterns.append("breakout")
    if pd.notna(r.breakout_low) and r.close<r.breakout_low:patterns.append("breakdown")
    return patterns
