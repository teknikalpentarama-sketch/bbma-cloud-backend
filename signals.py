"""BBMA Oma Ally Multi-Timeframe AI Robot"""
import numpy as np
from bbma import BbmaContext, detect_csak, detect_csm, get_market_phase
from indicators import ema


def analyze_bbma_mtf(bars_htf, bars_ltf, tf_seconds=60):
    """
    bars_htf : Timeframe Besar (Arah / Contoh H4 / H1)
    bars_ltf : Timeframe Kecil (Eksekusi / Contoh M15 / M5)
    """
    i_htf = len(bars_htf['close']) - 1
    i_ltf = len(bars_ltf['close']) - 1

    ctx_htf = BbmaContext(bars_htf)
    ctx_ltf = BbmaContext(bars_ltf)

    close_ltf = bars_ltf['close'][i_ltf]

    # 1. Tentukan Trend HTF (EMA50)
    ema50_htf = ctx_htf.ma50[i_htf]
    trend_htf = "BULLISH" if close_ltf > ema50_htf else "BEARISH"

    # 2. Fasa LTF
    phase_ltf = get_market_phase(ctx_ltf, i_ltf)
    csak_ltf = detect_csak(ctx_ltf, i_ltf)

    # 3. Deteksi Re-entry di LTF
    is_reentry_buy = (
            close_ltf > ctx_ltf.ma5_low[i_ltf] and
            close_ltf < ctx_ltf.ma5_high[i_ltf] and
            trend_htf == "BULLISH"
    )
    is_reentry_sell = (
            close_ltf < ctx_ltf.ma5_high[i_ltf] and
            close_ltf > ctx_ltf.ma5_low[i_ltf] and
            trend_htf == "BEARISH"
    )

    # 4. MTF Code (REM, REE, RRE)
    mtf_code = "WAIT"
    if trend_htf == "BULLISH":
        if "Extreme" in phase_ltf or "MHV" in phase_ltf:
            mtf_code = "REM (Re-entry HTF, Extreme LTF)"
        elif "CSAK (BULL)" in phase_ltf or is_reentry_buy:
            mtf_code = "REE (Re-entry HTF, Re-entry LTF)"
            mtf_code = "BUY SETUP"
    elif trend_htf == "BEARISH":
        if "Extreme" in phase_ltf or "MHV" in phase_ltf:
            mtf_code = "REM (Sell)"
        elif "CSAK (BEAR)" in phase_ltf or is_reentry_sell:
            mtf_code = "SELL SETUP"

    # 5. Keputusan
    direction = "WAIT"
    conviction = 0
    reasons = []

    if mtf_code == "BUY SETUP":
        direction = "BUY"
        conviction = 85 if "CSAK" in phase_ltf else 65
        reasons = [
            f"HTF Trend: Bullish (Price > EMA50)",
            f"LTF Phase: {phase_ltf}",
            "LTF: Re-entry at MA5/10 confirmed"
        ]
    elif mtf_code == "SELL SETUP":
        direction = "SELL"
        conviction = 85 if "CSAK" in phase_ltf else 65
        reasons = [
            f"HTF Trend: Bearish (Price < EMA50)",
            f"LTF Phase: {phase_ltf}",
            "LTF: Re-entry at MA5/10 confirmed"
        ]
    else:
        reasons = [
            f"HTF Trend: {trend_htf}",
            f"LTF Phase: {phase_ltf}",
            "Menunggu setup Re-entry atau CSAK..."
        ]

    # 6. Entry, TP Wajib, SL
    entry = close_ltf
    if direction == "BUY":
        target = ctx_ltf.bb_middle[i_ltf]  # TP Wajib Mid BB
        stop = ctx_ltf.ma5_low[i_ltf] - (ctx_ltf.bb_middle[i_ltf] * 0.0005)  # SL bawah MA5
    elif direction == "SELL":
        target = ctx_ltf.bb_middle[i_ltf]
        stop = ctx_ltf.ma5_high[i_ltf] + (ctx_ltf.bb_middle[i_ltf] * 0.0005)  # SL atas MA5
    else:
        target = stop = None

    return {
        'direction': direction,
        'conviction': conviction,
        'reasons': reasons,
        'entry': entry if direction != 'WAIT' else None,
        'target': target,
        'stop': stop,
        'next_candle_time': bars_ltf['time'][-1] + tf_seconds,
        'phase': phase_ltf,
        'trend': trend_htf
    }