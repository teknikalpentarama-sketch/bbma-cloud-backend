import os
import asyncio
import json
import time
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Import SDK MetaApi
from metaapi_cloud_sdk import MetaApi

# Import logik BBMA & AI anda
from bbma import analyze_bbma
from signals import analyze_bbma_mtf_v2
from market_data import generate_history, tick_update, append_bar

# =====================================================================
# LAPISAN 1: SETUP APLIKASI & CORS
# =====================================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# LAPISAN 2: SETUP TOKEN & METAPI (Di sinilah kod yang anda tanya diletakkan)
# =====================================================================
API_TOKEN = os.environ.get('METAAPI_TOKEN')
ACCOUNT_ID = os.environ.get('METAAPI_ACCOUNT_ID')

if not API_TOKEN or not ACCOUNT_ID:
    print("⚠️ AMARAN: METAAPI_TOKEN atau METAAPI_ACCOUNT_ID tidak dijumpai di Render Environment!")
    print("Aplikasi akan menggunakan data SIMULASI buat sementara waktu.")

# Cipta instance MetaApi global
api = None
if API_TOKEN:
    api = MetaApi(token=API_TOKEN)


@app.get("/")
def read_root():
    return {"status": "BBMA Cloud Backend is Running!"}

# =====================================================================
# LAPISAN 3: WEBSOCKET (Tempat data dihantar ke frontend)
# =====================================================================
@app.websocket("/ws/chart")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    current_symbol = "XAUUSD"
    current_tf = 900  # 15m
    bars = None
    connection = None
    
    # Cuba sambung ke MetaApi
    if api and ACCOUNT_ID:
        try:
            account = await api.metatrader_account_api.get_account(account_id=ACCOUNT_ID)
            connection = account.get_streaming_connection()
            await connection.connect()
            await connection.wait_synchronized()
            print("✅ Berjaya sambung ke MetaApi Cloud!")
        except Exception as e:
            print(f"❌ Gagal sambung ke MetaApi: {e}")
            connection = None
    
    try:
        while True:
            # 1. Terima arahan dari frontend
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                data = json.loads(msg)
                if data.get("action") == "change":
                    current_symbol = data.get("symbol", current_symbol)
                    current_tf = int(data.get("tf", current_tf))
                    bars = None 
            except asyncio.TimeoutError:
                pass 
            
            # 2. Dapatkan Data
            if connection is not None:
                # --- GUNA DATA LIVE METAPI ---
                tf_minutes = current_tf // 60
                tf_str = f"{tf_minutes}m" if tf_minutes < 60 else f"{tf_minutes // 60}h"
                try:
                    candles = await connection.get_historical_candles(
                        symbol=current_symbol, 
                        timeframe=tf_str, 
                        limit=300
                    )
                    bars = {
                        'time': np.array([c['time'] for c in candles]),
                        'open': np.array([c['open'] for c in candles]),
                        'high': np.array([c['high'] for c in candles]),
                        'low': np.array([c['low'] for c in candles]),
                        'close': np.array([c['close'] for c in candles]),
                        'volume': np.array([c['tickVolume'] for c in candles]),
                    }
                except Exception as e:
                    print(f"Gagal ambil data live: {e}")
                    if bars is None:
                        bars = generate_history(current_symbol, 300, current_tf)
            else:
                # --- GUNA DATA SIMULASI (FALLBACK) ---
                if bars is None:
                    bars = generate_history(current_symbol, 300, current_tf)
                else:
                    if time.time() - bars['time'][-1] >= current_tf:
                        append_bar(bars, current_tf)
                    tick_update(bars)

            # 3. Kira BBMA & AI MTF
            ctx, ex, mhv, re = analyze_bbma(bars)
            
            tf_map = {60: 300, 300: 900, 900: 3600, 3600: 14400}
            tf_mtf = tf_map.get(current_tf, current_tf * 3)
            tf_htf = tf_map.get(tf_mtf, tf_mtf * 4)
            
            # (Nota: Untuk data MTF/HTF di MetaApi, anda perlu buat panggilan API berasingan. 
            # Buat masa ini kita kekalkan simulasi untuk MTF/HTF supaya tak crash)
            bars_mtf = generate_history(current_symbol, 300, tf_mtf)
            bars_htf = generate_history(current_symbol, 300, tf_htf)
            
            verdict = analyze_bbma_mtf_v2(bars, bars_mtf, bars_htf, current_tf)
            verdict['phase'] = verdict.get('phase', 'WAIT')
            verdict['trend'] = verdict.get('trend', '-')

            # 4. Sediakan Data untuk Frontend
            to_list = lambda arr: [None if np.isnan(x) else float(x) for x in arr]
            
            payload = {
                "type": "update",
                "bars": [{"time": int(t), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)} 
                         for t, o, h, l, c, v in zip(bars['time'], bars['open'], bars['high'], bars['low'], bars['close'], bars['volume'])],
                "bb_upper": to_list(ctx.bb_upper),
                "bb_middle": to_list(ctx.bb_middle),
                "bb_lower": to_list(ctx.bb_lower),
                "ma5_high": to_list(ctx.ma5_high),
                "ma10_high": to_list(ctx.ma10_high),
                "ma5_low": to_list(ctx.ma5_low),
                "ma10_low": to_list(ctx.ma10_low),
                "ma50": to_list(ctx.ma50),
                "verdict": verdict
            }
            
            # 5. Hantar ke Frontend
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1) 
            
    except WebSocketDisconnect:
        print("Client terputus")
    finally:
        if connection is not None:
            await connection.close()
