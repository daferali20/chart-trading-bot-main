from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    ib_host:str="127.0.0.1"; ib_port:int=7497; ib_client_id:int=101; account:str=""
    exchange:str="SMART"; currency:str="USD"; timeframe:str="10 mins"; history_duration:str="7 D"; paper_trading:bool=True
    symbol:str="BIAF"; watchlist_file:str="watchlist.txt"; top_gainers_count:int=10; scan_interval_seconds:int=60
    min_score:int=4; fixed_quantity:int=100; take_profit_percent:float=10.0
    max_active_trades:int=7; max_active_positions:int=7; max_open_orders:int=7; max_executed_orders:int=7; execution_count_scope:str="DAY"
    risk_per_trade:float=0.01; paper_account_value:float=100000.0; atr_stop_mult:float=1.5; reward_risk:float=2.0
    tradingview_webhook_enabled:bool=True; tradingview_webhook_host:str="127.0.0.1"; tradingview_webhook_port:int=8000; tradingview_webhook_token:str="CHANGE_ME"
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
settings=Settings()
