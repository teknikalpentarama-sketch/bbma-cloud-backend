"""Pure-numpy indicator math — no pandas dependency."""
import numpy as np


def sma(values, period):
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if len(values) < period:
        return out
    cumsum = np.cumsum(np.insert(values, 0, 0))
    out[period - 1:] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def lwma(values, period):
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if len(values) < period:
        return out
    weights = np.arange(1, period + 1, dtype=float)
    wsum = weights.sum()
    for i in range(period - 1, len(values)):
        out[i] = np.dot(values[i - period + 1:i + 1], weights) / wsum
    return out


def ema(values, period):
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    out[period - 1] = np.mean(values[:period])
    for i in range(period, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def bollinger_bands(closes, period=20, mult=2.0):
    closes = np.asarray(closes, dtype=float)
    middle = sma(closes, period)
    upper = np.full_like(closes, np.nan)
    lower = np.full_like(closes, np.nan)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        std = np.std(window)  # population std (TradingView default)
        upper[i] = middle[i] + mult * std
        lower[i] = middle[i] - mult * std
    return upper, middle, lower


def rsi(closes, period=14):
    closes = np.asarray(closes, dtype=float)
    out = np.full_like(closes, np.nan)
    if len(closes) < period + 1:
        return out
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def macd_histogram(closes, fast=12, slow=26, signal=9):
    closes = np.asarray(closes, dtype=float)
    macd_line = ema(closes, fast) - ema(closes, slow)
    signal_line = np.full_like(macd_line, np.nan)
    valid_start = slow - 1
    if len(macd_line) > valid_start + signal - 1:
        signal_line[valid_start:] = ema(macd_line[valid_start:], signal)
    return macd_line - signal_line


def atr(highs, lows, closes, period=14):
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if n == 0:
        return np.array([])
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]))
    return sma(tr, period)