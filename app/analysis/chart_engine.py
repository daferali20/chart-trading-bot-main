from __future__ import annotations
import pandas as pd
def add_chart_indicators(df:pd.DataFrame)->pd.DataFrame:
    out=df.copy();h,l,c,v=out.high,out.low,out.close,out.volume
    ten=(h.rolling(9).max()+l.rolling(9).min())/2;kij=(h.rolling(26).max()+l.rolling(26).min())/2
    out["tenkan"]=ten;out["kijun"]=kij;out["senkou_a"]=((ten+kij)/2).shift(26);out["senkou_b"]=((h.rolling(52).max()+l.rolling(52).min())/2).shift(26)
    hh,ll=h.rolling(14).max(),l.rolling(14).min();out["williams_r"]=-100*(hh-c)/(hh-ll).replace(0,pd.NA)
    typical=(h+l+c)/3;raw=typical*v;direction=typical.diff();pos=raw.where(direction>0,0.0).rolling(14).sum();neg=raw.where(direction<0,0.0).rolling(14).sum()
    out["mfi14"]=100-(100/(1+pos/neg.replace(0,pd.NA)));out["ema50_chart"]=c.ewm(span=50,adjust=False).mean();out["volume_sma20"]=v.rolling(20).mean();out["volume_ratio"]=v/out.volume_sma20.replace(0,pd.NA)
    out["cloud_top"]=pd.concat([out.senkou_a,out.senkou_b],axis=1).max(axis=1);out["cloud_bottom"]=pd.concat([out.senkou_a,out.senkou_b],axis=1).min(axis=1)
    out["above_cloud"]=c>out.cloud_top;out["below_cloud"]=c<out.cloud_bottom;return out
def chart_context(df:pd.DataFrame)->dict:
    r=df.iloc[-1];return {"close":float(r.close),"ema50":float(r.ema50_chart) if pd.notna(r.ema50_chart) else None,"williams_r":float(r.williams_r) if pd.notna(r.williams_r) else None,"mfi14":float(r.mfi14) if pd.notna(r.mfi14) else None,"volume_ratio":float(r.volume_ratio) if pd.notna(r.volume_ratio) else None,"above_cloud":bool(r.above_cloud) if pd.notna(r.above_cloud) else False,"below_cloud":bool(r.below_cloud) if pd.notna(r.below_cloud) else False,"cloud_top":float(r.cloud_top) if pd.notna(r.cloud_top) else None,"cloud_bottom":float(r.cloud_bottom) if pd.notna(r.cloud_bottom) else None}
