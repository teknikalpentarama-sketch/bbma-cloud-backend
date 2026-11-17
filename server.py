import asyncio
import json
import time
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from bbma import analyze_bbma
from signals import analyze_bbma_mtf
from market_data import generate_history, tick_update, append_bar

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "BBMA Cloud Backend is Running!"}

@app.websocket("/ws/chart")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    current_symbol = "XAUUSD"
    current_tf = 900  # 15m
    bars = None
    
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
            
            # 2. Dapatkan Data (Simulasi)
            if bars is None:
                bars = generate_history(current_symbol, 300, current_tf)
            else:
                if time.time() - bars['time'][-1] >= current_tf:
                    append_bar(bars, current_tf)
                tick_update(bars)

            # 3. Kira BBMA & AI MTF
            ctx, ex, mhv, re = analyze_bbma(bars)
            
            tf_htf_map = {60: 900, 300: 1800, 900: 3600, 3600: 14400}
            tf_htf_sec = tf_htf_map.get(current_tf, 3600)
            
            bars_htf = generate_history(current_symbol, 300, tf_htf_sec)
            
            verdict = analyze_bbma_mtf(bars_htf, bars, current_tf)
            
            # 4. FIX: Tukar format NumPy kepada format biasa (JSON serializable)
            safe_verdict = {
                "direction": str(verdict.get('direction', 'WAIT')),
                "conviction": int(verdict.get('conviction', 0)),
                "reasons": [str(r) for r in verdict.get('reasons', [])],
                "entry": float(verdict['entry']) if verdict.get('entry') is not None else None,
                "target": float(verdict['target']) if verdict.get('target') is not None else None,
                "stop": float(verdict['stop']) if verdict.get('stop') is not None else None,
                "phase": str(verdict.get('phase', '-')),
                "trend": str(verdict.get('trend', '-'))
            }
            
            to_list = lambda arr: [None if np.isnan(x) else float(x) for x in arr]
            
            # 5. Sediakan Payload
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
                "verdict": safe_verdict
            }
            
            # 6. Hantar ke Frontend
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1) 
            
    except WebSocketDisconnect:
        print("Client terputus")
    except Exception as e:
        print(f"WebSocket error: {e}")
