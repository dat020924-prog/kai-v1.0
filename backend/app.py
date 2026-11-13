import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import ccxt
import pandas as pd
import ta  # TA-Lib wrapper for pandas

load_dotenv()

app = FastAPI(title="TradingView Lite", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"],
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
