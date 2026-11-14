"""
Stock data loader - loads local CSV files into a dictionary for fast access.
Format: YYYYMMDD,Open,High,Low,Close,Volume,Field6,Field7,Field8
"""

import os
from datetime import datetime
from typing import Dict, List, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stock")
_cache = {}

def load_all_data():
    """Load all stock data from local files."""
    global _cache
    if _cache:
        return _cache
    
    _cache = {}
    if not os.path.exists(DATA_DIR):
        print(f"[WARN] Stock data directory not found: {DATA_DIR}")
        return _cache
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.txt'):
            symbol = filename[:-4]  # Remove .txt
            filepath = os.path.join(DATA_DIR, filename)
            _cache[symbol] = _load_symbol_data(filepath, symbol)
    
    print(f"[INFO] Loaded {len(_cache)} symbols from local stock data")
    return _cache

def _load_symbol_data(filepath: str, symbol: str) -> List[Dict[str, Any]]:
    """Load a single symbol's data from file."""
    data = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) < 6:
                    continue
                
                date_str = parts[0]  # YYYYMMDD
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d")
                except ValueError:
                    continue
                
                try:
                    o = float(parts[1])
                    h = float(parts[2])
                    l = float(parts[3])
                    c = float(parts[4])
                    v = int(float(parts[5]))
                except (ValueError, IndexError):
                    continue
                
                data.append({
                    "time": dt.strftime("%Y-%m-%d"),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                })
    except Exception as e:
        print(f"[WARN] Failed to load {symbol}: {e}")
    
    return data

def get_symbol_data(symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Get OHLCV data for a symbol."""
    if not _cache:
        load_all_data()
    
    data = _cache.get(symbol, [])
    return data[-limit:] if data else []

def get_latest_price(symbol: str) -> Optional[Dict[str, Any]]:
    """Get the latest price for a symbol."""
    if not _cache:
        load_all_data()
    
    data = _cache.get(symbol, [])
    if not data:
        return None
    
    return data[-1]

def get_all_symbols() -> List[str]:
    """Get all available symbols."""
    if not _cache:
        load_all_data()
    
    return sorted(_cache.keys())

if __name__ == "__main__":
    load_all_data()
    print(f"Total symbols: {len(get_all_symbols())}")
    print(f"Sample symbols: {get_all_symbols()[:10]}")
    print(f"VN30 data points: {len(get_symbol_data('VN30', 100))}")
    print(f"VN30 latest: {get_latest_price('VN30')}")
