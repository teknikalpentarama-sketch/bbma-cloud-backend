                if session is not None and client is not None:
                    try:
                        # 1. Pastikan format timeframe betul untuk TickerAll
                        tf_map = {60: "M1", 300: "M5", 900: "M15", 3600: "H1"}
                        tf_str = tf_map.get(current_tf, "M15")
                        
                        # 2. Tukar 'limit' kepada 'count'
                        candles = client.candles.get(
                            session.account_id, 
                            symbol=current_symbol, 
                            timeframe=tf_str, 
                            count=300  # <-- Guna 'count', bukan 'limit'
                        )
                        
                        if candles and len(candles) > 0:
                            bars_list = []
                            for c in candles:
                                # 3. TickerAll guna .timestamp (bukan .time)
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
                                    'volume': float(c.tick_volume) # <-- Guna 'tick_volume'
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
                    except Exception as e:
                        print(f"⚠️ Gagal ambil data TickerAll: {e}", flush=True)
                        if bars is None: bars = generate_history(current_symbol, 300, current_tf)
                        is_live_data = False
