"""Deterministic OHLCV generator + live tick simulator."""
import time
import numpy as np

SYMBOLS = ['BTCUSD', 'ETHUSD', 'EURUSD', 'GBPUSD', 'XAUUSD', 'AAPL', 'TSLA']

_BASE_PRICES = {
    'BTCUSD': 65000.0, 'ETHUSD': 3200.0, 'EURUSD': 1.08,
    'GBPUSD': 1.26, 'XAUUSD': 2350.0, 'AAPL': 180.0, 'TSLA': 250.0,
}

def generate_history(symbol, n_bars=300, tf_seconds=60, seed=None):
    if seed is None:
        seed = hash((symbol, tf_seconds)) & 0xFFFF
    rng = np.random.default_rng(seed)
    price = _BASE_PRICES.get(symbol, 100.0)
    vol = price * 0.003

    now = int(time.time())
    start = now - n_bars * tf_seconds

    times  = np.arange(n_bars) * tf_seconds + start
    opens  = np.empty(n_bars); highs = np.empty(n_bars)
    lows   = np.empty(n_bars); closes = np.empty(n_bars)
    volumes = np.empty(n_bars)

    for i in range(n_bars):
        drift = np.sin(i / 30.0) * vol * 0.2
        change = rng.normal(drift, vol)
        opens[i] = price
        closes[i] = price + change
        wick = abs(rng.normal(0, vol * 0.5))
        highs[i] = max(opens[i], closes[i]) + wick
        lows[i]  = min(opens[i], closes[i]) - wick
        volumes[i] = rng.uniform(100, 1000) * (1 + abs(change) / vol * 0.5)
        price = closes[i]

    return {'time': times, 'open': opens, 'high': highs,
            'low': lows, 'close': closes, 'volume': volumes}


def tick_update(bars, rng=None):
    """Update the last bar in-place with a simulated tick."""
    rng = rng or np.random.default_rng()
    i = len(bars['close']) - 1
    price = bars['close'][i]
    vol = max(price * 0.0005, 1e-9)
    new_p = price + rng.normal(0, vol)
    bars['close'][i] = new_p
    bars['high'][i] = max(bars['high'][i], new_p)
    bars['low'][i] = min(bars['low'][i], new_p)
    bars['volume'][i] += rng.uniform(1, 10)
    return bars


def append_bar(bars, tf_seconds=60):
    """Roll into a fresh bar continuing from the previous close."""
    last_close = bars['close'][-1]
    new_row = {'time': bars['time'][-1] + tf_seconds,
               'open': last_close, 'high': last_close,
               'low': last_close, 'close': last_close, 'volume': 0.0}
    for k, v in new_row.items():
        bars[k] = np.append(bars[k], v)
    return bars
