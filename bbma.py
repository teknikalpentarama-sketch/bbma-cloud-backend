"""BBMA Oma Ally rule engine — Extreme, MHV, Re-entry, CSAK, CSM."""
import numpy as np
from indicators import bollinger_bands, lwma, ema


class BbmaContext:
    def __init__(self, bars):
        self.bars = bars
        closes, highs, lows = bars['close'], bars['high'], bars['low']
        self.bb_upper, self.bb_middle, self.bb_lower = bollinger_bands(closes, 20, 2.0)
        self.ma5_high  = lwma(highs, 5)
        self.ma10_high = lwma(highs, 10)
        self.ma5_low   = lwma(lows,  5)
        self.ma10_low  = lwma(lows, 10)
        self.ma50      = ema(closes, 50)


def _bull(b, i):
    return b['close'][i] > b['open'][i]


def _bear(b, i):
    return b['close'][i] < b['open'][i]


def _recent_reverse(b, i, lookback=3):
    return any(b['close'][j] != b['open'][j]
               for j in range(max(0, i - lookback), i))


def detect_extreme(ctx):
    """MA5/10 High above Upper BB → SELL extreme; Low below Lower BB → BUY extreme."""
    out = []
    b = ctx.bars
    for i in range(20, len(b['close'])):
        up, lo = ctx.bb_upper[i], ctx.bb_lower[i]
        m5h, m10h = ctx.ma5_high[i], ctx.ma10_high[i]
        m5l, m10l = ctx.ma5_low[i],  ctx.ma10_low[i]
        if any(np.isnan(v) for v in (up, lo, m5h, m5l)):
            continue
        c = b['close'][i]
        if c > up or c < lo:
            continue
        if (m5h > up or m10h > up) and _bear(b, i) and _recent_reverse(b, i):
            out.append((i, 'EXTREME_SELL', b['high'][i]))
        if (m5l < lo or m10l < lo) and _bull(b, i) and _recent_reverse(b, i):
            out.append((i, 'EXTREME_BUY', b['low'][i]))
    return out


def _confirm_csa(ctx, i):
    """CSA = close crosses BOTH MA5 and MA10 (in matching direction)."""
    b = ctx.bars
    m5h, m10h = ctx.ma5_high[i], ctx.ma10_high[i]
    m5l, m10l = ctx.ma5_low[i],  ctx.ma10_low[i]
    if np.isnan(m5h) or np.isnan(m5l):
        return False
    c = b['close'][i]
    return (c > m5h and c > m10h) or (c < m5l and c < m10l)


def detect_mhv(ctx, extremes):
    """MHV = after Extreme: candle closes inside BB, has reverse candle,
    and CSA appears within the next 2 bars."""
    out, b = [], ctx.bars
    for (idx, label, _) in extremes:
        for i in range(idx + 1, min(len(b['close']), idx + 7)):
            up, lo = ctx.bb_upper[i], ctx.bb_lower[i]
            if np.isnan(up) or np.isnan(lo):
                continue
            if not (lo < b['close'][i] < up):
                continue
            if not _recent_reverse(b, i, 2):
                continue
            if _confirm_csa(ctx, i):
                out.append((i,
                            'MHV_SELL' if label == 'EXTREME_SELL' else 'MHV_BUY',
                            b['close'][i]))
                break
    return out


def detect_reentry(ctx):
    """Re-entry: close holds on the correct side of MA5/MA10 (does not pass)."""
    out, b = [], ctx.bars
    for i in range(30, len(b['close'])):
        m5h, m10h = ctx.ma5_high[i], ctx.ma10_high[i]
        m5l, m10l = ctx.ma5_low[i],  ctx.ma10_low[i]
        if np.isnan(m5h) or np.isnan(m5l):
            continue
        c, l, h = b['close'][i], b['low'][i], b['high'][i]
        if c > m5l and c > m10l and l >= m5l and _bull(b, i):
            out.append((i, 'REENTRY_BUY', c))
        elif c < m5h and c < m10h and h <= m5h and _bear(b, i):
            out.append((i, 'REENTRY_SELL', c))
    return out


def detect_csak(ctx, i):
    """CSAK: Candlestick close memotong Mid BB dan MA5/10."""
    b = ctx.bars
    c = b['close'][i]
    mid = ctx.bb_middle[i]
    m5h, m10h = ctx.ma5_high[i], ctx.ma10_high[i]
    m5l, m10l = ctx.ma5_low[i],  ctx.ma10_low[i]

    if np.isnan(mid) or np.isnan(m5h) or np.isnan(m5l):
        return None

    is_bull = c > mid and c > m5h and c > m10h
    is_bear = c < mid and c < m5l and c < m10l

    if is_bull:
        return "BULL"
    if is_bear:
        return "BEAR"
    return None


def detect_csm(ctx, i):
    """CSM: Body besar close di luar Top/Low BB."""
    b = ctx.bars
    up, lo = ctx.bb_upper[i], ctx.bb_lower[i]
    if np.isnan(up) or np.isnan(lo):
        return False
    return b['close'][i] > up or b['close'][i] < lo


def get_market_phase(ctx, i):
    """Cari fasa BBMA terkini pada index i."""
    if detect_csm(ctx, i):
        return "CSM (Momentum)"

    csak = detect_csak(ctx, i)
    if csak:
        return f"CSAK ({csak})"

    for j in range(max(0, i - 5), i):
        if not np.isnan(ctx.bb_upper[j]) and (ctx.ma5_high[j] > ctx.bb_upper[j] or ctx.ma5_low[j] < ctx.bb_lower[j]):
            return "Extreme"

    if not np.isnan(ctx.bb_lower[i]) and ctx.bb_lower[i] < ctx.bars['close'][i] < ctx.bb_upper[i]:
        return "MHV / Inside BB"

    return "Konsolidasi"


def analyze_bbma(bars):
    ctx = BbmaContext(bars)
    ex = detect_extreme(ctx)
    mhv = detect_mhv(ctx, ex)
    re = detect_reentry(ctx)
    return ctx, ex, mhv, re