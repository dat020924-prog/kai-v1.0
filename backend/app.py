import math
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import ccxt
import pandas as pd
import ta  # TA-Lib wrapper for pandas
import requests

load_dotenv()

app = FastAPI(title="TradingView Lite", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- API Stock VN config ----
API_STOCK_VN_KEY = os.getenv("API_STOCK_VN_KEY", "")
API_STOCK_VN_BASE = "https://api.robotstock.info.vn/api_data"

# ---- Alert state (in-memory) ----
_alert_state: Dict[str, str] = {}


def _get_exchange():
    return ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })


def _fetch_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    """Fetch OHLCV from Binance via ccxt."""
    exchange = _get_exchange()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=500)
    df = pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df.set_index("time", inplace=True)
    return df


def _compute_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Compute RSI using ta library."""
    rsi_obj = ta.momentum.RSIIndicator(close, window=length)
    return rsi_obj.rsi()


# ---- Helpers for alert state (in-memory) ----

def _check_rsi_alert(symbol: str, rsi_val: float) -> Optional[str]:
    """Check RSI threshold and return alert type if triggered."""
    if math.isnan(rsi_val):
        return None

    current_signal = ""
    if rsi_val < 30:
        current_signal = "oversold"
    elif rsi_val > 70:
        current_signal = "overbought"
    else:
        current_signal = "neutral"

    prev_signal = _alert_state.get(symbol, "neutral")

    if current_signal != prev_signal and current_signal != "neutral":
        _alert_state[symbol] = current_signal
        return current_signal

    _alert_state[symbol] = current_signal
    return None


# ---- API Endpoints ----

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "tradingview-lite"}


@app.get("/api/symbols")
def get_symbols():
    """Return supported symbols."""
    return {
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "VN30F1M"],
        "default": "BTC/USDT",
    }


@app.get("/api/ohlcv")
def get_ohlcv(
    symbol: str = Query("BTC/USDT"),
    interval: str = Query("1m"),
):
    """Fetch OHLCV data from Binance."""
    try:
        df = _fetch_ohlcv(symbol, interval)
        result = []
        for idx, row in df.iterrows():
            result.append({
                "time": int(idx.timestamp()) * 1000,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
        return {
            "symbol": symbol,
            "interval": interval,
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {str(e)}")


@app.get("/api/rsi")
def get_rsi(
    symbol: str = Query("BTC/USDT"),
    interval: str = Query("1m"),
    length: int = Query(14),
):
    """Compute and return RSI for the given symbol."""
    try:
        df = _fetch_ohlcv(symbol, interval)
        rsi_series = _compute_rsi(df["close"], length)

        result = []
        for idx, val in rsi_series.items():
            if not math.isnan(val):
                result.append({
                    "time": int(idx.timestamp()) * 1000,
                    "rsi": round(float(val), 2),
                })

        latest_rsi = rsi_series.iloc[-1] if not rsi_series.isna().all() else None
        alert_type = None
        if latest_rsi is not None and not math.isnan(latest_rsi):
            alert_type = _check_rsi_alert(symbol, float(latest_rsi))

        return {
            "symbol": symbol,
            "interval": interval,
            "length": length,
            "latest_rsi": round(float(latest_rsi), 2) if latest_rsi is not None else None,
            "alert": alert_type,
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute RSI: {str(e)}")


@app.get("/api/alert-state")
def get_alert_state(symbol: str = Query("BTC/USDT")):
    """Get current alert state for a symbol."""
    return {
        "symbol": symbol,
        "state": _alert_state.get(symbol, "neutral"),
    }


@app.get("/api/alert-history")
def get_alert_history():
    """Return recent alerts (in-memory)."""
    return {"alerts": list(_alert_state.items())}


# ---- VN30F1M Endpoints ----

def _fetch_vn30f1m_historical(res: str = "1D", back: int = 100) -> list:
    """Fetch VN30F1M historical data from API Stock VN.
    Falls back to mock data if API key is missing or request fails.
    """
    if not API_STOCK_VN_KEY:
        return _mock_vn30f1m_data(res, back)

    try:
        url = f"{API_STOCK_VN_BASE}"
        params = {
            "type": "his_derivative",
            "sym": "VN30F1M",
            "key": API_STOCK_VN_KEY,
            "res": res,
            "back": back,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        # Expected format: {"data": [{"time", "open", "high", "low", "close", "volume"}, ...]}
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        # If API returns flat list
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"[WARN] API Stock VN failed: {e} — using mock data")

    return _mock_vn30f1m_data(res, back)


def _mock_vn30f1m_data(res: str = "1D", back: int = 100) -> list:
    """Generate mock VN30F1M data for development/testing."""
    import random
    data = []
    base_time = datetime.now() - timedelta(days=back if res == "1D" else back * 60)
    price = 1450.0  # Mock starting price for VN30F1M

    for i in range(back):
        if res == "1D":
            ts = base_time + timedelta(days=i)
        else:
            ts = base_time + timedelta(minutes=i)

        change = random.uniform(-8, 8)
        o = round(price + random.uniform(-3, 3), 1)
        c = round(o + change, 1)
        h = round(max(o, c) + random.uniform(0, 5), 1)
        l = round(min(o, c) - random.uniform(0, 5), 1)
        v = random.randint(500, 5000)

        if res == "1D":
            time_str = ts.strftime("%Y-%m-%d")
        else:
            time_str = ts.strftime("%Y-%m-%d %H:%M:%S")

        data.append({
            "time": time_str,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })
        price = c

    return data


@app.get("/api/vn30f1m")
def get_vn30f1m(
    res: str = Query("1D", description="Resolution: 1m, 5m, 15m, 30m, 1H, 1D"),
    back: int = Query(100, description="Number of bars"),
):
    """Fetch VN30F1M futures data from API Stock VN (or mock fallback)."""
    try:
        data = _fetch_vn30f1m_historical(res, back)
        return {
            "symbol": "VN30F1M",
            "resolution": res,
            "source": "api_stock_vn" if API_STOCK_VN_KEY else "mock",
            "count": len(data),
            "data": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch VN30F1M: {str(e)}")


@app.get("/api/vn30f1m/realtime")
def get_vn30f1m_realtime():
    """Fetch latest VN30F1M quote. Mock fallback if API unavailable."""
    if not API_STOCK_VN_KEY:
        import random
        return {
            "symbol": "VN30F1M",
            "price": round(1450 + random.uniform(-10, 10), 1),
            "change": round(random.uniform(-5, 5), 2),
            "changePercent": round(random.uniform(-1, 1), 2),
            "volume": random.randint(1000, 5000),
            "high": round(1460 + random.uniform(-5, 5), 1),
            "low": round(1440 + random.uniform(-5, 5), 1),
            "source": "mock",
            "timestamp": datetime.now().isoformat(),
        }

    try:
        url = f"{API_STOCK_VN_BASE}"
        params = {
            "type": "rt_derivative",
            "sym": "VN30F1M",
            "key": API_STOCK_VN_KEY,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        data["source"] = "api_stock_vn"
        data["timestamp"] = datetime.now().isoformat()
        return data
    except Exception as e:
        print(f"[WARN] RT API failed: {e}")
        return {
            "symbol": "VN30F1M",
            "price": 1450.0,
            "change": 0.0,
            "changePercent": 0.0,
            "volume": 0,
            "source": "mock_error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
