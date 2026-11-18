import numpy as np
from bbma import BbmaContext, detect_csm, detect_csak_v2, detect_extreme_v2, detect_reentry_v2, detect_mhv_v2

def get_state(ctx, i):
    """Mencari isyarat terkini dalam 5 bar terakhir untuk sesuatu Timeframe."""
    for j in range(i, max(0, i-5), -1):
        if detect_csm(ctx, j): return "CSM"
        csak = detect_csak_v2(ctx, j)
        if csak: return f"CSAK_{csak}"
        ext = detect_extreme_v2(ctx, j)
        if ext: return f"EXTREME_{ext}"
        re = detect_reentry_v2(ctx, j)
        if re: return f"RE-ENTRY_{re}"
        # MHV
        for k in range(j, min(len(ctx.bars['close']), j+3)):
            ext_prev = detect_extreme_v2(ctx, k-1)
            if ext_prev:
                if detect_mhv_v2(ctx, k, ext_prev): 
                    mhv_dir = 'BUY' if ext_prev=='SELL' else 'SELL'
                    return f"MHV_{mhv_dir}"
    return "NONE"

def analyze_bbma_mtf_v2(bars_ltf, bars_mtf, bars_htf, tf_seconds=60):
    ctx_ltf = BbmaContext(bars_ltf)
    ctx_mtf = BbmaContext(bars_mtf)
    ctx_htf = BbmaContext(bars_htf)

    i_ltf, i_mtf, i_htf = len(bars_ltf['close'])-1, len(bars_mtf['close'])-1, len(bars_htf['close'])-1

    htf_state = get_state(ctx_htf, i_htf)
    mtf_state = get_state(ctx_mtf, i_mtf)
    ltf_state = get_state(ctx_ltf, i_ltf)

    direction = "WAIT"
    conviction = 0
    setup_name = ""
    reasons = [f"LTF: {ltf_state}", f"MTF: {mtf_state}", f"HTF: {htf_state}"]
    close_ltf = bars_ltf['close'][i_ltf]

    # 1. REM: HTF Re-entry -> MTF Extreme -> LTF MHV
    if htf_state.startswith("RE-ENTRY") and mtf_state.startswith("EXTREME") and ltf_state.startswith("MHV"):
        setup_name = "REM SETUP"
        direction = ltf_state.split("_")[1]
        conviction = 90
    # 2. REE: HTF Re-entry -> MTF Extreme -> LTF Extreme
    elif htf_state.startswith("RE-ENTRY") and mtf_state.startswith("EXTREME") and ltf_state.startswith("EXTREME"):
        setup_name = "REE SETUP"
        direction = ltf_state.split("_")[1]
        conviction = 85
    # 3. RRE: HTF Re-entry -> MTF Re-entry -> LTF Extreme
    elif htf_state.startswith("RE-ENTRY") and mtf_state.startswith("RE-ENTRY") and ltf_state.startswith("EXTREME"):
        setup_name = "RRE SETUP"
        direction = ltf_state.split("_")[1]
        conviction = 80

    # Fallback jika tiada MTF Setup, tapi ikut Trend HTF & LTF Signal
    if direction == "WAIT":
        trend_htf = "BULLISH" if close_ltf > ctx_htf.ma50[i_htf] else "BEARISH"
        if trend_htf == "BULLISH" and ltf_state.startswith("RE-ENTRY_BUY"):
            direction = "BUY"; conviction = 60; setup_name = "LTF Re-entry"
        elif trend_htf == "BEARISH" and ltf_state.startswith("RE-ENTRY_SELL"):
            direction = "SELL"; conviction = 60; setup_name = "LTF Re-entry"

    # TPW / Levels
    entry = close_ltf if direction != "WAIT" else None
    target = ctx_ltf.bb_middle[i_ltf] if direction != "WAIT" else None # TP Wajib di Mid BB
    if direction == "BUY": stop = ctx_ltf.ma5_low[i_ltf]
    elif direction == "SELL": stop = ctx_ltf.ma5_high[i_ltf]
    else: stop = None

    return {
        'direction': direction,
        'conviction': conviction,
        'reasons': reasons,
        'entry': float(entry) if entry else None,
        'target': float(target) if target else None,
        'stop': float(stop) if stop else None,
        'next_candle_time': bars_ltf['time'][-1] + tf_seconds,
        'phase': f"{setup_name}" if setup_name else ltf_state,
        'trend': "BULLISH" if close_ltf > ctx_htf.ma50[i_htf] else "BEARISH"
    }
