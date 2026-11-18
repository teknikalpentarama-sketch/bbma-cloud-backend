import os
import asyncio
import json
import time
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from signals import analyze_bbma_mtf_v2
from bbma import analyze_bbma
from market_data import generate_history, tick_update, append_bar

try:
    from metaapi_cloud_sdk import MetaApi
    METAAPI_AVAILABLE = True
except ImportError:
    METAAPI_AVAILABLE = False

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_TOKEN = os.environ.get('METAAPI_TOKEN')
ACCOUNT_ID = os.environ.get('METAAPI_ACCOUNT_ID')

@app.get("/")
def read_root():
    return {"status": "BBMA Cloud Backend is Running!"}

@app.websocket("/ws/chart")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    current_symbol = "XAUUSD"
    current_tf = 900
    bars = None
    connection = None

    # Inisialisasi MetaApi DI DALAM fungsi async
    if METAAPI_AVAILABLE and API_TOKEN and ACCOUNT_ID:
        try:
            api = MetaApi(token=API_TOKEN)
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
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                data = json.loads(msg)
                if data.get("action") == "change":
                    current_symbol = data.get("symbol", current_symbol)
                    current_tf = int(data.get("tf", current_tf))
                    bars = None
            except asyncio.TimeoutError:
                pass

            if connection is not None:
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
                if bars is None:
                    bars = generate_history(current_symbol, 300, current_tf)
                else:
                    if time.time() - bars['time'][-1] >= current_tf:
                        append_bar(bars, current_tf)
                    tick_update(bars)

            ctx, ex, mhv, re = analyze_bbma(bars)

            tf_map = {60: 300, 300: 900, 900: 3600, 3600: 14400}
            tf_mtf = tf_map.get(current_tf, current_tf * 3)
            tf_htf = tf_map.get(tf_mtf, tf_mtf * 4)

            bars_mtf = generate_history(current_symbol, 300, tf_mtf)
            bars_htf = generate_history(current_symbol, 300, tf_htf)

            verdict = analyze_bbma_mtf_v2(bars, bars_mtf, bars_htf, current_tf)
            verdict['phase'] = verdict.get('phase', 'WAIT')
            verdict['trend'] = verdict.get('trend', '-')

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

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        print("Client terputus")
    finally:
        if connection is not None:
            await connection.close()
