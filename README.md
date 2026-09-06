# Chart Trading Bot — IBKR Paper

This version adds a fail-closed execution gate.

Order path:
TradingView / Scanner / Strategy -> Internal Queue -> Risk -> Fresh IBKR Positions -> Fresh Open Orders -> Execution Gate -> Max 7 Executed Orders -> IBKR.

Defaults:
- Paper trading only
- Max executed orders: 7 per trading day
- Max active positions: 7
- Max open orders: 7
- Orders are recorded in SQLite
- `.env` is local and must never be committed

Windows:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python run_desktop.py
```

TradingView webhook:
```powershell
.\.venv\Scripts\python.exe run_webhook.py
```

Endpoint:
`POST /webhook/tradingview`

The webhook writes validated signals to the local SQLite queue. It does not call IBKR directly.

Live trading is disabled by design in this version. Test with the IBKR paper account only.
