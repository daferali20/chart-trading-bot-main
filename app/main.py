import asyncio,logging
from app.broker.ibkr import IBKRClient
from app.analysis.indicators import add_indicators
from app.strategy.signal import analyze
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s")
async def main():
    c=IBKRClient()
    try:
        df=add_indicators(await c.historical_bars());s=analyze(df)
        print(f"Signal: {s.action}");print(f"Score: {s.score}");print(f"Entry: {s.entry:.4f}")
        if s.stop:print(f"Stop: {s.stop:.4f}")
        if s.target:print(f"Target: {s.target:.4f}")
        print("Reasons:",", ".join(s.reasons))
    finally:await c.disconnect()
if __name__=="__main__":asyncio.run(main())
