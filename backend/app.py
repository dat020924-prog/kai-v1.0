import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import ccxt
import pandas as pd
import ta  # TA-Lib wrapper for pandas
import requests
from stock_loader import load_all_data, get_symbol_data, get_latest_price, get_all_symbols

load_dotenv()

# Load stock data at startup
load_all_data()

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

# ---- Vnstock API ----
VNSTOCK_BASE = "https://vnstock.io.vn/api"

# ---- Caching for vnstock (avoid slow API calls) ----
_vnstock_cache = {"data": None, "ts": 0}
_VNSTOCK_TTL = 300  # 5 minutes cache

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
    # Get Vietnamese stocks from local data
    vn_stocks = get_all_symbols()
    
    return {
        "symbols": [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
            "VN30F1M", "VN30", "VNINDEX",
        ] + vn_stocks[:50],  # Include top 50 Vietnamese stocks
        "default": "BTC/USDT",
        "vn_stocks": vn_stocks,
    }


@app.get("/api/ohlcv")
def get_ohlcv(
    symbol: str = Query("BTC/USDT"),
    resolution: str = Query("1D", description="Resolution: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 1D"),
    limit: int = Query(100, description="Number of bars"),
):
    """Fetch OHLCV data from Binance or vnstock for Vietnamese stocks."""
    try:
        # Validate resolution
        valid_res = ("1m", "3m", "5m", "15m", "30m", "1H", "2H", "4H", "1D")
        if resolution not in valid_res:
            raise HTTPException(status_code=400, detail=f"Invalid resolution. Must be one of: {valid_res}")
        
        # Check if it's a Vietnamese stock
        vn_symbols = ["VN30", "VN30F1M", "VNINDEX", "HNX30", "HNXINDEX"]
        if symbol in vn_symbols or get_symbol_data(symbol, 1):
            # Fetch from vnstock API or local data
            return _get_vn_stock_ohlcv(symbol, resolution, limit)
        
        # Otherwise use Binance
        # Map resolution to ccxt timeframe
        timeframe_map = {
            "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1H": "1h", "2H": "2h", "4H": "4h", "1D": "1d"
        }
        timeframe = timeframe_map.get(resolution, "1m")
        
        df = _fetch_ohlcv(symbol, timeframe)
        result = []
        for idx, row in df.head(limit).iterrows():
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
            "interval": resolution,
            "data": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {str(e)}")


def _get_vn_stock_ohlcv(symbol: str, res: str = "1D", limit: int = 100) -> dict:
    """Fetch OHLCV data for Vietnamese stocks via vnstock API or local data."""
    try:
        # Try vnstock API first
        url = f"{VNSTOCK_BASE}/stock/{symbol}?market=VN"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Convert vnstock history to OHLCV format
        history = data.get("history", [])
        # vnstock returns oldest-first; take the LAST `limit` bars (newest data)
        history = history[-limit:] if len(history) > limit else history
        ohlcv_data = []
        for bar in history:
            d = bar.get("d", "")
            # Use UTC to avoid timezone offset issues
            dt = datetime.strptime(d, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
            ts = int(dt.replace(tzinfo=timezone.utc).timestamp()) * 1000
            ohlcv_data.append({
                "time": ts,
                "open": bar.get("o"),
                "high": bar.get("h"),
                "low": bar.get("l"),
                "close": bar.get("c"),
                "volume": bar.get("v", 0),
            })
        
        # Sort by time ascending for chart display
        ohlcv_data.sort(key=lambda x: x["time"])
        
        return {
            "symbol": symbol,
            "interval": res,
            "data": ohlcv_data,
            "source": "vnstock",
        }
    except Exception as e:
        print(f"[WARN] vnstock API failed for {symbol}: {e}")
        # Fallback to local data
        local_data = get_symbol_data(symbol, limit)
        if local_data:
            # Convert local data time strings to milliseconds timestamps
            normalized = []
            for bar in local_data:
                t = bar.get("time", "")
                if isinstance(t, str) and "-" in t:
                    # Date string YYYY-MM-DD → ms (UTC)
                    dt = datetime.strptime(t, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
                    ts = int(dt.replace(tzinfo=timezone.utc).timestamp()) * 1000
                elif isinstance(t, (int, float)):
                    ts = t
                else:
                    ts = 0
                normalized.append({
                    "time": ts,
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                    "volume": bar.get("volume", 0),
                })
            normalized.sort(key=lambda x: x["time"])
            return {
                "symbol": symbol,
                "interval": res,
                "data": normalized,
                "source": "local",
            }
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")


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

def _fetch_vn30f1m_from_vnstock(res: str = "1D", back: int = 100) -> dict:
    """Fetch VN30F1M data from vnstock.io.vn API.
    Returns realtime quote + daily history.
    Note: vnstock only provides daily data, regardless of res parameter.
    Uses 5-min cache to avoid slow API calls.
    Falls back to local stock data if API fails.
    """
    # Check cache first
    now = time.time()
    if _vnstock_cache["data"] and (now - _vnstock_cache["ts"]) < _VNSTOCK_TTL:
        return _vnstock_cache["data"]

    try:
        url = f"{VNSTOCK_BASE}/stock/VN30F1M?market=VN"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        realtime = {
            "symbol": data.get("symbol", "VN30F1M"),
            "name": data.get("name", "VN30 Futures"),
            "price": data.get("price"),
            "prev_close": data.get("prev"),
            "change": data.get("chg"),
            "open": data.get("open"),
            "high": data.get("high"),
            "low": data.get("low"),
            "volume": data.get("vol", 0),
            "source": "vnstock",
            "timestamp": datetime.now().isoformat(),
        }

        # Convert daily history to OHLCV format
        history = data.get("history", [])
        ohlcv_data = []
        for bar in history:
            d = bar.get("d", "")
            ohlcv_data.append({
                "time": d,
                "open": bar.get("o"),
                "high": bar.get("h"),
                "low": bar.get("l"),
                "close": bar.get("c"),
                "volume": bar.get("v", 0),
            })

        # Sort by date descending (newest first) to match frontend expectations
        ohlcv_data.sort(key=lambda x: x["time"], reverse=True)

        result = {
            "realtime": realtime,
            "history": ohlcv_data[:back],
            "is_daily": True,  # Mark that vnstock only provides daily data
        }

        # Update cache
        _vnstock_cache["data"] = result
        _vnstock_cache["ts"] = now
        return result
    except Exception as e:
        print(f"[WARN] vnstock API failed: {e}")
        # Fallback to local stock data
        local_data = get_symbol_data("VN30F1M", back)
        if local_data:
            return {
                "realtime": None,
                "history": local_data,
                "source": "local",
                "is_daily": True,
            }
        return None


def _fetch_vn30f1m_from_robotstock(res: str = "1D", back: int = 100) -> dict:
    """Fallback: fetch VN30F1M from robotstock API.
    Supports multiple resolutions if API key is configured.
    """
    if not API_STOCK_VN_KEY:
        return None

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

        if "data" in data and isinstance(data["data"], list):
            return {
                "realtime": None,
                "history": data["data"],
                "source": "robotstock",
                "is_daily": res == "1D",
            }
    except Exception as e:
        print(f"[WARN] robotstock API failed: {e}")

    return None


def _generate_intraday_from_daily(daily_bars: list, res: str, back: int) -> list:
    """Generate simulated intraday bars from daily data for chart display.
    Uses daily OHLCV to create sub-bars based on resolution.
    This is for visual purposes only — not real tick data.
    """
    import random
    random.seed(42)  # deterministic for consistency

    # Map resolution to minutes per bar
    res_minutes = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
        "1H": 60, "2H": 120, "4H": 240,
    }
    minutes = res_minutes.get(res, 5)

    # Trading day: 09:00 - 11:30, 13:00 - 15:00 (Vietnam futures)
    # Total trading minutes per day
    morning_min = 150  # 09:00-11:30
    afternoon_min = 120  # 13:00-15:00 (NOT 150 — market closes at 15:00)
    total_min = morning_min + afternoon_min

    # Number of bars per day
    bars_per_day = max(1, total_min // minutes)

    result = []
    # We need 'back' intraday bars
    days_needed = (back + bars_per_day - 1) // bars_per_day

    for day_idx in range(days_needed):
        if day_idx >= len(daily_bars):
            break
        daily = daily_bars[day_idx]
        o = daily["open"]
        h = daily["high"]
        l = daily["low"]
        c = daily["close"]
        v = daily["volume"]

        # Generate intraday bars that stay within daily OHLC range
        base_time = datetime.strptime(daily["time"], "%Y-%m-%d")

        for bar_idx in range(bars_per_day):
            total_offset = day_idx * bars_per_day + bar_idx
            if total_offset >= back:
                return result[:back]

            # Calculate time offset (with lunch break)
            if bar_idx < morning_min // minutes:
                minute_offset = bar_idx * minutes
                hour = 9 + minute_offset // 60
                minute = minute_offset % 60
            else:
                afternoon_idx = bar_idx - morning_min // minutes
                hour = 13 + afternoon_idx * minutes // 60
                minute = (afternoon_idx * minutes) % 60

            bar_time = base_time.replace(hour=hour, minute=minute, second=0)

            # Distribute price within daily range
            day_range = h - l if h != l else 1
            intra_range = day_range * 0.8  # intra bars stay within 80% of daily range

            # Progressive interpolation from open to close
            progress = bar_idx / max(1, bars_per_day - 1)
            mid_price = o + (c - o) * progress
            spread = intra_range * 0.5
            intra_close = round(max(l, min(h, mid_price + random.uniform(-spread, spread))), 1)
            intra_open = round(intra_close + random.uniform(-spread*0.3, spread*0.3), 1)
            intra_high = round(max(o, h, intra_open, intra_close) + random.uniform(0, intra_range * 0.1), 1)
            intra_low = round(min(l, l, intra_open, intra_close) - random.uniform(0, intra_range * 0.1), 1)

            # Distribute volume
            intra_vol = max(1, int(v / bars_per_day * random.uniform(0.5, 1.5)))

            if res in ("1m", "3m", "5m"):
                time_str = bar_time.strftime("%Y-%m-%dT%H:%M")
            else:
                time_str = bar_time.strftime("%Y-%m-%dT%H:%M")

            result.append({
                "time": time_str,
                "open": intra_open,
                "high": intra_high,
                "low": intra_low,
                "close": intra_close,
                "volume": intra_vol,
            })

    return result[:back]


def _fetch_vn30f1m_historical(res: str = "1D", back: int = 100) -> list:
    """Fetch VN30F1M historical data with proper resolution handling.
    Tries vnstock first, then robotstock, then mock.
    For intraday resolutions, generates sub-bars from daily data.
    """
    source_used = "unknown"
    raw_result = None

    # Try vnstock first (primary source)
    result = _fetch_vn30f1m_from_vnstock(res, back)
    if result and result.get("history"):
        raw_result = result
        source_used = "vnstock"
    else:
        # Fallback to robotstock
        result = _fetch_vn30f1m_from_robotstock(res, back)
        if result and result.get("history"):
            raw_result = result
            source_used = "robotstock"

    # Handle resolution conversion
    if raw_result:
        history = raw_result["history"]
        is_daily = raw_result.get("is_daily", True)

        if is_daily and res != "1D":
            # Generate intraday bars from daily data
            history = _generate_intraday_from_daily(history, res, back)
            source_used = f"vnstock+{res}"
    elif API_STOCK_VN_KEY:
        # If both APIs fail but key exists, try mock with robotstock seed
        history = _mock_vn30f1m_data(res, back)
        source_used = "mock(robotstock-seeded)"
    else:
        # No API key, use mock
        history = _mock_vn30f1m_data(res, back)
        source_used = "mock"

    return history


def _fetch_vn30f1m_realtime() -> dict:
    """Fetch latest VN30F1M quote. Tries vnstock first, then robotstock, then mock."""
    # Try vnstock first (primary source)
    result = _fetch_vn30f1m_from_vnstock()
    if result and result.get("realtime"):
        return result["realtime"]

    # Fallback to robotstock
    if API_STOCK_VN_KEY:
        try:
            url = f"{API_STOCK_VN_BASE}"
            params = {
                "type": "rt_derivative",
                "sym": "VN30F1M",
                "key": API_STOCK_VN_KEY,
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            data["source"] = "robotstock"
            data["timestamp"] = datetime.now().isoformat()
            return data
        except Exception as e:
            print(f"[WARN] robotstock RT failed: {e}")

    # Last resort: mock
    import random
    return {
        "symbol": "VN30F1M",
        "price": round(1933 + random.uniform(-10, 10), 1),
        "change": round(random.uniform(-5, 5), 2),
        "changePercent": round(random.uniform(-1, 1), 2),
        "volume": random.randint(1000, 5000),
        "high": round(1945 + random.uniform(-5, 5), 1),
        "low": round(1920 + random.uniform(-5, 5), 1),
        "source": "mock",
        "timestamp": datetime.now().isoformat(),
    }




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
    """Fetch VN30F1M futures data from vnstock (primary) or robotstock fallback.
    Supports multiple resolutions. For intraday res, generates sub-bars from daily data.
    """
    # Validate resolution
    valid_res = ("1m", "3m", "5m", "15m", "30m", "1H", "2H", "4H", "1D")
    if res not in valid_res:
        raise HTTPException(status_code=400, detail=f"Invalid resolution. Must be one of: {valid_res}")

    try:
        data = _fetch_vn30f1m_historical(res, back)
        return {
            "symbol": "VN30F1M",
            "resolution": res,
            "count": len(data),
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch VN30F1M: {str(e)}")


@app.get("/api/vn30f1m/realtime")
def get_vn30f1m_realtime():
    """Fetch latest VN30F1M quote. vnstock (primary) → robotstock → mock."""
    return _fetch_vn30f1m_realtime()
