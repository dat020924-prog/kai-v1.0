# TradingView Lite

Dashboard biểu đồ candlestick + RSI chạy local trên MacBook. Backend FastAPI lấy dữ liệu từ Binance qua ccxt, frontend React/Vite render lightweight-charts.

## Stack

| Thành phần | Công nghệ |
|---|---|
| Frontend | React 19 + Vite 6 + lightweight-charts 4.2 |
| Backend | Python FastAPI + ccxt + pandas + ta |
| Market Data | Binance API (qua ccxt) |
| Indicator | RSI (ta.momentum.RSIIndicator) |

## Cài đặt

```bash
cd /Users/kai/.openclaw/workspace/Tradingview

# Backend — venv đã có, deps đã cài trong backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt  # chạy lại nếu cần

# Frontend
npm install          # từ folder frontend/
```

## Chạy app

### Cách 1: start.sh (cả backend + frontend)

```bash
chmod +x start.sh tradingviewkai.command
./start.sh
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs

### Cách 2: chạy riêng lẻ

```bash
# Terminal 1 — Backend
cd /Users/kai/.openclaw/workspace/Tradingview/backend
source ../.venv/bin/activate
python app.py

# Terminal 2 — Frontend
cd /Users/kai/.openclaw/workspace/Tradingview/frontend
npm run dev
```

## Dừng app

```bash
# Nếu chạy bằng start.sh: Ctrl+C
# Nếu chạy riêng lẻ:
curl -s http://localhost:8000/api/health  # check health
kill $(lsof -ti :8000)    # backend
curl -s http://localhost:5173/ 2>/dev/null || true
kill $(lsof -ti :5173)    # frontend
```

## Desktop shortcut

```bash
cp tradingviewkai.command ~/Desktop/
chmod +x ~/Desktop/tradingviewkai.command
```

## Frontend features

- Watchlist: BTC/USDT, ETH/USDT, SOL/USDT (dropdown selector)
- Timeframe: 1m, 5m, 15m, 1h
- Candlestick chart (lightweight-charts)
- RSI chart riêng (period=14)
- Alert panel: OVERSOLD (RSI<30) / OVERBOUGHT (RSI>70)
- Auto-refresh mỗi 10s, Pause/Resume
- Responsive layout (flexbox + ResizeObserver)

## Cấu hình alert

```bash
cp .env.example .env
```

Sửa `.env`:
- `NTFY_URL` — URL ntfy topic (nếu dùng ntfy)
- `SMTP_USER` / `SMTP_PASS` — Gmail App Password (nếu dùng email)

## API Endpoints

| Endpoint | Method | Params | Description |
|---|---|---|---|
| /api/health | GET | — | Health check |
| /api/ohlcv | GET | symbol, interval | OHLCV data từ Binance |
| /api/rsi | GET | symbol, interval, length | RSI computed |
| /api/alert-state | GET | symbol | Current alert state |
| /api/alert-history | GET | — | Recent alerts (in-memory) |
