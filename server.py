import os
import asyncio
import json
import time
import math
from datetime import datetime
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from signals import analyze_bbma_mtf_v2
from bbma import analyze_bbma
from market_data import generate_history, tick_update, append_bar

try:
    from tickerall import Tickerall
    TICKERALL_AVAILABLE = True
except ImportError:
    TICKERALL_AVAILABLE = False

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

API_KEY = os.environ.get('TICKERALL_API_KEY')
BROKER_SERVER = os.environ.get('BROKER_SERVER')
BROKER_LOGIN = os.environ.get('BROKER_LOGIN')
BROKER_PASSWORD = os.environ.get('BROKER_PASSWORD')

@app.get("/")
def read_root():
    return {"status": "BBMA Cloud Backend is Running!"}

@app.websocket("/ws/chart")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔌 Client Netlify telah bersambung!", flush=True)

    current_symbol = "XAUUSD"
    current_tf = 900
    bars = None
    client = None
    session = None
    is_live_data = False

    # Cuba sambung ke TickerAll
    if TICKERALL_AVAILABLE and API_KEY and BROKER_SERVER and BROKER_LOGIN and BROKER_PASSWORD:
        try:
            print("⏳ Sedang menyambung ke TickerAll...", flush=True)
            client = Tickerall(api_key=API_KEY)
            
            session = client.sessions.start(
                broker="mt5",
                server=BROKER_SERVER,
                account=int(BROKER_LOGIN),
                password=BROKER_PASSWORD,
            )
            print(f"✅ Berjaya sambung ke TickerAll! Account ID: {session.account_id}", flush=True)
        except Exception as e:
            print(f"⚠️ TickerAll gagal: {e}. Guna Data Simulasi.", flush=True)
            client = None
            session = None

    try:
        while True:
            try:
                # 1. Terima arahan frontend (jika ada perubahan TF/Symbol)
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                    data = json.loads(msg)
                    if data.get("action") == "change":
                        current_symbol = data.get("symbol", current_symbol)
                        current_tf = int(data.get("tf", current_tf))
                        bars = None
                        print(f"🔄 Tukar ke: {current_symbol} {current_tf}s", flush=True)
                except asyncio.TimeoutError:
                    pass

                # 2. Dapatkan Data
                if session is not None and client is not None:
                    try:
                        # Pastikan format TF betul (M1, M5, M15, H1)
                        tf_map = {60: "M1", 300: "M5", 900: "M15", 3600: "H1"}
                        tf_str = tf_map.get(current_tf, "M15")
                        
                        # Guna count, bukan limit
                        candles = client.candles.get(
                            session.account_id, 
                            symbol=current_symbol, 
                            timeframe=tf_str, 
                            count=300
                        )
                        
                        if candles and len(candles) > 0:
                            bars_list = []
                            for c in candles:
                                t_val = c.timestamp
                                if isinstance(t_val, str):
                                    dt = datetime.fromisoformat(t_val.replace('Z', '+00:00'))
                                    unix_time = int(dt.timestamp())
                                else:
                                    unix_time = int(t_val)

                                bars_list.append({
                                    'time': unix_time,
                                    'open': float(c.open),
                                    'high': float(c.high),
                                    'low': float(c.low),
                                    'close': float(c.close),
                                    'volume': float(c.tick_volume)
                                })
                            
                            bars = {
                                'time': np.array([b['time'] for b in bars_list]),
                                'open': np.array([b['open'] for b in bars_list]),
                                'high': np.array([b['high'] for b in bars_list]),
                                'low': np.array([b['low'] for b in bars_list]),
                                'close': np.array([b['close'] for b in bars_list]),
                                'volume': np.array([b['volume'] for b in bars_list]),
                            }
                            is_live_data = True
                        else:
                            if bars is None: bars = generate_history(current_symbol, 300, current_tf)
                            is_live_data = False
                    except Exception as e:
                        print(f"⚠️ Gagal ambil data TickerAll: {e}", flush=True)
                        if bars is None: bars = generate_history(current_symbol, 300, current_tf)
                        is_live_data = False
                else:
                    # Fallback Simulasi
                    if bars is None:
                        bars = generate_history(current_symbol, 300, current_tf)
                    else:
                        if time.time() - bars['time'][-1] >= current_tf:
                            append_bar(bars, current_tf)
                        tick_update(bars)
                    is_live_data = False

                # 3. Kira BBMA & AI MTF
                ctx, ex, mhv, re = analyze_bbma(bars)
                tf_map = {60: 300, 300: 900, 900: 3600, 3600: 14400}
                tf_mtf = tf_map.get(current_tf, current_tf * 3)
                tf_htf = tf_map.get(tf_mtf, tf_mtf * 4)
                
                bars_mtf = generate_history(current_symbol, 300, tf_mtf)
                bars_htf = generate_history(current_symbol, 300, tf_htf)
                
                verdict = analyze_bbma_mtf_v2(bars, bars_mtf, bars_htf, current_tf)
                
                safe_verdict = {
                    "direction": str(verdict.get('direction', 'WAIT')),
                    "conviction": int(verdict.get('conviction', 0)),
                    "reasons": [str(r) for r in verdict.get('reasons', [])],
                    "entry": float(verdict['entry']) if verdict.get('entry') is not None and not math.isnan(verdict['entry']) else None,
                    "target": float(verdict['target']) if verdict.get('target') is not None and not math.isnan(verdict['target']) else None,
                    "stop": float(verdict['stop']) if verdict.get('stop') is not None and not math.isnan(verdict['stop']) else None,
                    "phase": str(verdict.get('phase', '-')),
                    "trend": str(verdict.get('trend', '-'))
                }

                to_list = lambda arr: [None if np.isnan(x) else float(x) for x in arr]
                
                payload = {
                    "type": "update",
                    "is_live": is_live_data,
                    "bars": [{"time": int(t), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)} 
                             for t, o, h, l, c, v in zip(bars['time'], bars['open'], bars['high'], bars['low'], bars['close'], bars['volume'])],
                    "bb_upper": to_list(ctx.bb_upper), "bb_middle": to_list(ctx.bb_middle), "bb_lower": to_list(ctx.bb_lower),
                    "ma5_high": to_list(ctx.ma5_high), "ma10_high": to_list(ctx.ma10_high),
                    "ma5_low": to_list(ctx.ma5_low), "ma10_low": to_list(ctx.ma10_low), "ma50": to_list(ctx.ma50),
                    "verdict": safe_verdict
                }
                
                await websocket.send_text(json.dumps(payload))
                
            except WebSocketDisconnect:
                print("🔌 Browser Client terputus.", flush=True)
                break
            except Exception as loop_err:
                print(f"❌ RALAT DALAM LOOP: {loop_err}", flush=True)
                break
                
            await asyncio.sleep(1) 
            
    except WebSocketDisconnect:
        print("🔌 Client Netlify terputus dari luar.", flush=True)
    finally:
        if client is not None and session is not None:
            try:
                client.sessions.end(session.account_id)
                print("🔌 Sesi TickerAll ditutup.", flush=True)
            except Exception:
                pass
