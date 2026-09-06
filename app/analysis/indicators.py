import pandas as pd
def add_indicators(df:pd.DataFrame)->pd.DataFrame:
    out=df.copy();out["ema20"]=out.close.ewm(span=20,adjust=False).mean();out["ema50"]=out.close.ewm(span=50,adjust=False).mean()
    delta=out.close.diff();gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean();loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rs=gain/loss.replace(0,pd.NA);out["rsi14"]=100-100/(1+rs);prev=out.close.shift(1)
    tr=pd.concat([out.high-out.low,(out.high-prev).abs(),(out.low-prev).abs()],axis=1).max(axis=1)
    out["atr14"]=tr.rolling(14).mean();out["volume20"]=out.volume.rolling(20).mean();out["breakout_high"]=out.high.rolling(20).max().shift(1);out["breakout_low"]=out.low.rolling(20).min().shift(1)
    return out
