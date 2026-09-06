import asyncio,logging
from app.config import settings
from app.monitor import MarketMonitor
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s")
async def main():
    m=MarketMonitor(settings.symbol,settings.scan_interval_seconds)
    logging.getLogger(__name__).warning("IBKR PAPER TRADING ONLY | symbol=%s | port=%s",settings.symbol,settings.ib_port)
    await m.run()
if __name__=="__main__":
    try:asyncio.run(main())
    except KeyboardInterrupt:pass
