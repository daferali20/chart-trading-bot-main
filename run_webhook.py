import uvicorn
from app.config import settings
if __name__=="__main__":
    uvicorn.run("app.tradingview.webhook:app",host=settings.tradingview_webhook_host,port=settings.tradingview_webhook_port,reload=False)
