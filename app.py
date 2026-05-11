# app.py - ПЪЛЕН AI TRADING BOT с демо/реална сметка, бектест, MTF тренд
from flask import Flask, render_template_string, request, jsonify
import json
import random
import math
import requests
import hashlib
import hmac
import time
from datetime import datetime, timedelta

app = Flask(__name__)

# ============================================
# ИНДИКАТОР 1: BTC Scalp Pro v1 - SMC + MTF
# ============================================

class IndicatorV1:
    @staticmethod
    def calculate_ema(data, period):
        if len(data) < period:
            return data[-1] if data else 0
        k = 2 / (period + 1)
        ema = data[0]
        for i in range(1, len(data)):
            ema = data[i] * k + ema * (1 - k)
        return ema
    
    @staticmethod
    def calculate_rsi(data, period=14):
        if len(data) < period + 1:
            return 50
        gains = []
        losses = []
        for i in range(1, len(data)):
            diff = data[i] - data[i-1]
            if diff > 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(-diff)
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def calculate_atr(high, low, close, period=14):
        if len(high) < period + 1:
            return (high[-1] - low[-1]) if high else 0
        tr = []
        for i in range(1, len(high)):
            tr1 = high[i] - low[i]
            tr2 = abs(high[i] - close[i-1])
            tr3 = abs(low[i] - close[i-1])
            tr.append(max(tr1, tr2, tr3))
        return sum(tr[-period:]) / period
    
    @staticmethod
    def calculate_vwap(data):
        if not data:
            return 0
        total_value = 0
        total_volume = 0
        for candle in data[-100:]:
            typical = (candle['high'] + candle['low'] + candle['close']) / 3
            total_value += typical * candle['volume']
            total_volume += candle['volume']
        return total_value / total_volume if total_volume > 0 else 0
    
    def analyze(self, market_data):
        close_prices = [c['close'] for c in market_data[-50:]]
        highs = [c['high'] for c in market_data[-50:]]
        lows = [c['low'] for c in market_data[-50:]]
        
        ema9 = self.calculate_ema(close_prices, 9)
        ema21 = self.calculate_ema(close_prices, 21)
        rsi = self.calculate_rsi(close_prices, 14)
        vwap = self.calculate_vwap(market_data[-100:])
        atr = self.calculate_atr(highs, lows, close_prices, 14)
        current_price = close_prices[-1]
        
        bull_ob = min(lows[-5:]) if len(lows) >= 5 else current_price * 0.99
        bear_ob = max(highs[-5:]) if len(highs) >= 5 else current_price * 1.01
        liq_high = max(highs[-20:]) if len(highs) >= 20 else current_price * 1.02
        liq_low = min(lows[-20:]) if len(lows) >= 20 else current_price * 0.98
        
        trends = []
        for tf in [1, 5, 15, 60, 240]:
            tf_ema9 = self.calculate_ema(close_prices[-tf*20:], 9) if len(close_prices) >= tf*20 else ema9
            tf_ema21 = self.calculate_ema(close_prices[-tf*20:], 21) if len(close_prices) >= tf*20 else ema21
            trends.append(1 if tf_ema9 > tf_ema21 else -1)
        
        mtf_score = sum(trends)
        mtf_bull = mtf_score >= 3
        mtf_bear = mtf_score <= -3
        atr_sma = sum(close_prices[-50:]) / 50 * 0.01
        vol_ok = atr > atr_sma * 1.2
        
        long_cond = current_price > vwap and current_price > bull_ob and vol_ok and mtf_bull
        short_cond = current_price < vwap and current_price < bear_ob and vol_ok and mtf_bear
        
        return {
            "signal": "LONG" if long_cond else "SHORT" if short_cond else "HOLD",
            "trend": "BULL" if ema9 > ema21 else "BEAR",
            "rsi": rsi,
            "vwap": vwap,
            "atr": atr,
            "bull_ob": bull_ob,
            "bear_ob": bear_ob,
            "liq_high": liq_high,
            "liq_low": liq_low,
            "mtf_bull": mtf_bull,
            "mtf_bear": mtf_bear
        }


# ============================================
# ИНДИКАТОР 2: BTC Scalp Pro v2 - 5 режима + Order Flow
# ============================================

class IndicatorV2:
    @staticmethod
    def calculate_delta(volume, high, low, close):
        if high == low:
            return volume / 2
        buy_volume = volume * (close - low) / (high - low)
        sell_volume = volume * (high - close) / (high - low)
        return buy_volume - sell_volume
    
    @staticmethod
    def calculate_cumulative_delta(market_data):
        cum_delta = 0
        for candle in market_data[-50:]:
            delta = IndicatorV2.calculate_delta(
                candle['volume'], candle['high'], 
                candle['low'], candle['close']
            )
            cum_delta += delta
        return cum_delta
    
    @staticmethod
    def find_liquidity_clusters(market_data):
        recent = market_data[-30:]
        if not recent:
            return 0, 0
        max_vol_candle = max(recent, key=lambda x: x['volume'])
        min_vol_candle = min(recent, key=lambda x: x['volume'])
        return max_vol_candle['high'], min_vol_candle['low']
    
    def analyze(self, market_data, mode="SMC Pro"):
        close_prices = [c['close'] for c in market_data[-50:]]
        highs = [c['high'] for c in market_data[-50:]]
        lows = [c['low'] for c in market_data[-50:]]
        volumes = [c['volume'] for c in market_data[-50:]]
        
        current_price = close_prices[-1]
        avg_volume = sum(volumes) / len(volumes) if volumes else 1
        volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1
        
        ema9 = IndicatorV1.calculate_ema(close_prices, 9)
        ema21 = IndicatorV1.calculate_ema(close_prices, 21)
        rsi = IndicatorV1.calculate_rsi(close_prices, 14)
        atr = IndicatorV1.calculate_atr(highs, lows, close_prices, 14)
        vwap = IndicatorV1.calculate_vwap(market_data[-100:])
        cum_delta = self.calculate_cumulative_delta(market_data)
        delta_positive = cum_delta > 0
        liq_high, liq_low = self.find_liquidity_clusters(market_data)
        
        last_candle = market_data[-1]
        prev_candle = market_data[-2] if len(market_data) > 1 else last_candle
        gap_up = last_candle['low'] > prev_candle['high'] + atr * 0.3
        gap_down = last_candle['high'] < prev_candle['low'] - atr * 0.3
        
        mtf_data = market_data[-10:]
        mtf_ema9 = IndicatorV1.calculate_ema([c['close'] for c in mtf_data], 9)
        mtf_ema21 = IndicatorV1.calculate_ema([c['close'] for c in mtf_data], 21)
        mtf_bull = mtf_ema9 > mtf_ema21
        mtf_bear = mtf_ema9 < mtf_ema21
        
        modes_config = {
            "Aggressive Scalp": {"rsi_min": 30, "rsi_max": 70, "vol_mult": 0.8},
            "Conservative": {"rsi_min": 45, "rsi_max": 60, "vol_mult": 1.2},
            "Breakout Hunter": {"rsi_min": 35, "rsi_max": 75, "vol_mult": 1.5},
            "Reversal Master": {"rsi_min": 25, "rsi_max": 45, "vol_mult": 1.3},
            "Trend Follower": {"rsi_min": 50, "rsi_max": 75, "vol_mult": 1.0},
            "SMC Pro": {"rsi_min": 40, "rsi_max": 65, "vol_mult": 0.9}
        }
        
        cfg = modes_config.get(mode, modes_config["SMC Pro"])
        vol_ok = volume_ratio >= cfg["vol_mult"]
        rsi_long_ok = rsi >= cfg["rsi_min"] and rsi <= cfg["rsi_max"]
        rsi_short_ok = rsi >= (100 - cfg["rsi_max"]) and rsi <= (100 - cfg["rsi_min"])
        
        if mode == "Aggressive Scalp":
            long_signal = rsi_long_ok and current_price > vwap and delta_positive
            short_signal = rsi_short_ok and current_price < vwap and not delta_positive
        elif mode == "Conservative":
            long_signal = current_price > vwap and delta_positive and current_price > ema21
            short_signal = current_price < vwap and not delta_positive and current_price < ema21
        elif mode == "Breakout Hunter":
            highest = max(highs[-20:]) if len(highs) >= 20 else current_price * 1.02
            lowest = min(lows[-20:]) if len(lows) >= 20 else current_price * 0.98
            long_signal = current_price > highest and volume_ratio >= 1.5
            short_signal = current_price < lowest and volume_ratio >= 1.5
        elif mode == "Reversal Master":
            long_signal = cum_delta > 0 and current_price <= liq_low
            short_signal = cum_delta < 0 and current_price >= liq_high
        elif mode == "Trend Follower":
            long_signal = current_price > vwap and ema9 > ema21
            short_signal = current_price < vwap and ema9 < ema21
        else:
            long_signal = rsi_long_ok and current_price > vwap and delta_positive and mtf_bull
            short_signal = rsi_short_ok and current_price < vwap and not delta_positive and mtf_bear
        
        return {
            "signal": "LONG" if long_signal else "SHORT" if short_signal else "HOLD",
            "mode": mode,
            "rsi": rsi,
            "volume_ratio": volume_ratio,
            "cum_delta": cum_delta,
            "delta_positive": delta_positive,
            "vwap": vwap,
            "gap_up": gap_up,
            "gap_down": gap_down,
            "liq_high": liq_high,
            "liq_low": liq_low,
            "mtf_bull": mtf_bull,
            "mtf_bear": mtf_bear,
            "volume_spike": volume_ratio >= 1.5
        }


# ============================================
# ОБЕДИНЕН AI МОЗЪК
# ============================================

class UnifiedAIBrain:
    def __init__(self, strategy="SMC Pro"):
        self.indicator_v1 = IndicatorV1()
        self.indicator_v2 = IndicatorV2()
        self.strategy = strategy
        self.decision_history = []
        
    def analyze(self, market_data):
        v1_result = self.indicator_v1.analyze(market_data)
        v2_result = self.indicator_v2.analyze(market_data, self.strategy)
        current_price = market_data[-1]['close'] if market_data else 50000
        atr = v1_result.get('atr', current_price * 0.01)
        
        v1_signal = v1_result.get('signal', 'HOLD')
        v2_signal = v2_result.get('signal', 'HOLD')
        
        if v2_signal != "HOLD":
            final_signal = v2_signal
            confidence = 85
            reason = f"V2 ({self.strategy}): RSI={v2_result['rsi']:.0f}, Обем={v2_result['volume_ratio']:.1f}x"
        elif v1_signal != "HOLD":
            final_signal = v1_signal
            confidence = 70
            reason = f"V1 (SMC): MTF={'БИЧИ' if v1_result['mtf_bull'] else 'МЕЧИ'}"
        else:
            final_signal = "HOLD"
            confidence = max(100 - abs(v1_result['rsi'] - 50) * 2, 50)
            reason = f"Няма сигнал. RSI={v1_result['rsi']:.0f}"
        
        modes_config = {
            "Aggressive Scalp": {"sl": 1.2, "tp": [1.0, 1.8, 2.5]},
            "Conservative": {"sl": 1.8, "tp": [1.2, 2.0, 3.0]},
            "Breakout Hunter": {"sl": 1.0, "tp": [1.5, 2.5, 3.5]},
            "Reversal Master": {"sl": 1.4, "tp": [1.0, 1.5, 2.0]},
            "Trend Follower": {"sl": 1.5, "tp": [1.2, 2.0, 2.8]},
            "SMC Pro": {"sl": 1.3, "tp": [1.0, 1.8, 2.8]}
        }
        cfg = modes_config.get(self.strategy, modes_config["SMC Pro"])
        
        sl, tp1, tp2, tp3 = 0, 0, 0, 0
        if final_signal == "LONG":
            sl = current_price - atr * cfg["sl"]
            tp1 = current_price + atr * cfg["tp"][0]
            tp2 = current_price + atr * cfg["tp"][1]
            tp3 = current_price + atr * cfg["tp"][2]
        elif final_signal == "SHORT":
            sl = current_price + atr * cfg["sl"]
            tp1 = current_price - atr * cfg["tp"][0]
            tp2 = current_price - atr * cfg["tp"][1]
            tp3 = current_price - atr * cfg["tp"][2]
        
        result = {
            "decision": final_signal,
            "confidence": min(confidence, 95),
            "reason": reason,
            "sl": round(sl, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2),
            "v1_analysis": v1_result,
            "v2_analysis": v2_result,
            "current_price": current_price,
            "atr": atr
        }
        
        self.decision_history.append({
            "time": datetime.now().isoformat(),
            "decision": final_signal,
            "confidence": result["confidence"],
            "price": current_price
        })
        if len(self.decision_history) > 100:
            self.decision_history.pop(0)
        return result


# ============================================
# БЕКТЕСТ ДВИГАТЕЛ
# ============================================

class BacktestEngine:
    @staticmethod
    def run(market_data, strategy, leverage=1, initial_balance=10000):
        if not market_data or len(market_data) < 50:
            return {"error": "Няма достатъчно данни"}
        
        brain = UnifiedAIBrain(strategy)
        balance = initial_balance
        position = None
        entry_price = 0
        trades = []
        
        for i in range(50, len(market_data)):
            current_data = market_data[:i+1]
            current_price = current_data[-1]['close']
            analysis = brain.analyze(current_data)
            
            if position == 'LONG' and current_price <= entry_price * 0.98:
                pnl = (current_price - entry_price) / entry_price * 100 * leverage
                balance += balance * (pnl / 100)
                trades.append({"type": "LONG", "pnl": pnl, "exit_price": current_price})
                position = None
            elif position == 'SHORT' and current_price >= entry_price * 1.02:
                pnl = (entry_price - current_price) / entry_price * 100 * leverage
                balance += balance * (pnl / 100)
                trades.append({"type": "SHORT", "pnl": pnl, "exit_price": current_price})
                position = None
            
            if position is None and analysis["decision"] != "HOLD" and analysis["confidence"] >= 70:
                position = analysis["decision"]
                entry_price = current_price
        
        if position and market_data:
            last_price = market_data[-1]['close']
            if position == 'LONG':
                pnl = (last_price - entry_price) / entry_price * 100 * leverage
            else:
                pnl = (entry_price - last_price) / entry_price * 100 * leverage
            balance += balance * (pnl / 100)
        
        wins = len([t for t in trades if t["pnl"] > 0])
        total_pnl = (balance - initial_balance) / initial_balance * 100
        
        return {
            "initial_balance": initial_balance,
            "final_balance": round(balance, 2),
            "total_return": round(total_pnl, 2),
            "total_trades": len(trades),
            "wins": wins,
            "losses": len(trades) - wins,
            "win_rate": round(wins / len(trades) * 100, 2) if trades else 0,
            "trades": trades[-20:]
        }


# ============================================
# ТЪРГОВСКИ ДВИГАТЕЛ
# ============================================

class TradingEngine:
    def __init__(self, initial_balance=10000, strategy="SMC Pro"):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.position = None
        self.entry_price = 0
        self.entry_time = None
        self.sl = 0
        self.tp1 = 0
        self.tp2 = 0
        self.tp3 = 0
        self.trades = []
        self.ai_brain = UnifiedAIBrain(strategy)
        self.market_history = []
        
    def generate_market_data(self):
        base_price = 50000 + random.randint(-300, 300)
        high = base_price + random.randint(0, 200)
        low = base_price - random.randint(0, 200)
        candle = {
            "timestamp": time.time(),
            "open": base_price - random.randint(-50, 50),
            "high": high,
            "low": low,
            "close": base_price,
            "volume": random.randint(50, 500)
        }
        self.market_history.append(candle)
        if len(self.market_history) > 200:
            self.market_history.pop(0)
        return self.market_history
    
    def update(self):
        market_data = self.generate_market_data()
        current_price = market_data[-1]['close']
        
        if self.position == 'LONG':
            if current_price <= self.sl:
                self.close_position(current_price, "SL")
            elif current_price >= self.tp1:
                self.close_position(current_price, "TP1")
            elif current_price >= self.tp2:
                self.close_position(current_price, "TP2")
            elif current_price >= self.tp3:
                self.close_position(current_price, "TP3")
        elif self.position == 'SHORT':
            if current_price >= self.sl:
                self.close_position(current_price, "SL")
            elif current_price <= self.tp1:
                self.close_position(current_price, "TP1")
            elif current_price <= self.tp2:
                self.close_position(current_price, "TP2")
            elif current_price <= self.tp3:
                self.close_position(current_price, "TP3")
        
        if self.position is None:
            analysis = self.ai_brain.analyze(market_data)
            if analysis["decision"] in ["LONG", "SHORT"] and analysis["confidence"] >= 70:
                self.open_position(analysis, current_price)
            return self.get_status(current_price), analysis
        
        return self.get_status(current_price), None
    
    def open_position(self, analysis, price):
        if self.position is not None:
            return False
        self.position = analysis["decision"]
        self.entry_price = price
        self.entry_time = datetime.now().isoformat()
        self.sl = analysis["sl"]
        self.tp1 = analysis["tp1"]
        self.tp2 = analysis["tp2"]
        self.tp3 = analysis["tp3"]
        return True
    
    def close_position(self, price, reason):
        if self.position is None:
            return
        if self.position == 'LONG':
            pnl = (price - self.entry_price) / self.entry_price * 100
        else:
            pnl = (self.entry_price - price) / self.entry_price * 100
        pnl_amount = self.balance * (pnl / 100)
        self.balance += pnl_amount
        self.trades.append({
            "id": len(self.trades) + 1,
            "type": self.position,
            "entry_price": round(self.entry_price, 2),
            "exit_price": round(price, 2),
            "entry_time": self.entry_time,
            "exit_time": datetime.now().isoformat(),
            "pnl_percent": round(pnl, 2),
            "pnl_amount": round(pnl_amount, 2),
            "reason": reason,
            "balance_after": round(self.balance, 2)
        })
        self.position = None
        self.entry_price = 0
        self.sl = 0
        self.tp1 = 0
        self.tp2 = 0
        self.tp3 = 0
    
    def get_status(self, current_price):
        unrealized_pnl = 0
        if self.position == 'LONG':
            unrealized_pnl = (current_price - self.entry_price) / self.entry_price * 100
        elif self.position == 'SHORT':
            unrealized_pnl = (self.entry_price - current_price) / self.entry_price * 100
        wins = len([t for t in self.trades if t["pnl_percent"] > 0])
        losses = len([t for t in self.trades if t["pnl_percent"] < 0])
        total = len(self.trades)
        win_rate = (wins / total * 100) if total > 0 else 0
        return {
            "balance": round(self.balance, 2),
            "total_pnl": round(self.balance - self.initial_balance, 2),
            "total_pnl_percent": round((self.balance - self.initial_balance) / self.initial_balance * 100, 2),
            "position": self.position,
            "entry_price": self.entry_price,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "trades_count": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1)
        }
    
    def change_strategy(self, new_strategy):
        self.ai_brain.strategy = new_strategy
        self.ai_brain = UnifiedAIBrain(new_strategy)
    
    def set_demo_balance(self, new_balance):
        self.initial_balance = new_balance
        self.balance = new_balance
        self.position = None
        self.trades = []
    
    def reset(self):
        self.__init__(self.initial_balance, self.ai_brain.strategy)


# ============================================
# РЕАЛНА СМЕТКА (MEXC/BingX скелет)
# ============================================

live_connected = False
live_exchange = None
live_api_key = None
live_secret_key = None
live_passphrase = None
live_balance = 0


# ============================================
# HTML DASHBOARD (Мобилен + Всички функции)
# ============================================

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>🤖 AI Trading Bot - Pro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{background:#0a0a0a;font-family:'Segoe UI',Arial;color:white;padding:12px;}
        .header{text-align:center;margin-bottom:16px;}
        h1{color:#00ff88;font-size:22px;}
        .badge{background:#00ff88;color:#0a0a0a;display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;margin-top:5px;}
        .live-dot{color:#00ff88;animation:pulse 2s infinite;font-size:12px;margin-top:5px;}
        .tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;}
        .tab-btn{flex:1;background:#1a1a2e;border:none;padding:12px;border-radius:12px;color:white;font-weight:bold;cursor:pointer;}
        .tab-btn.active{background:#00ff88;color:#0a0a0a;}
        .tab-content{display:none;}
        .tab-content.active{display:block;}
        .card{background:linear-gradient(135deg,#1a1a2e,#0f0f1a);border-radius:20px;padding:16px;margin-bottom:16px;border:1px solid rgba(0,255,136,0.3);}
        .card h3{color:#00ff88;margin-bottom:12px;font-size:15px;border-left:3px solid #00ff88;padding-left:10px;}
        .stat-value{font-size:30px;font-weight:bold;color:#00ff88;}
        .stat-label{color:#888;font-size:11px;margin-top:4px;}
        .row{display:flex;justify-content:space-between;margin:8px 0;flex-wrap:wrap;gap:8px;}
        .position-long{background:rgba(0,255,0,0.2);border:1px solid #00ff00;padding:12px;border-radius:12px;text-align:center;}
        .position-short{background:rgba(255,0,0,0.2);border:1px solid #ff0000;padding:12px;border-radius:12px;text-align:center;}
        .position-none{background:#222;border:1px solid #444;padding:12px;border-radius:12px;text-align:center;}
        button{background:#00ff88;color:#0a0a0a;border:none;padding:10px 16px;border-radius:10px;cursor:pointer;font-weight:bold;margin:4px;font-size:14px;}
        button.danger{background:#ff4444;color:white;}
        button.secondary{background:#2a4a6a;color:white;}
        select, .input-field{background:#1a1a2a;color:white;border:1px solid #00ff88;padding:10px;border-radius:10px;width:100%;margin-bottom:8px;font-size:14px;}
        .analysis-box{background:#0a0a0a;border-radius:12px;padding:12px;margin-top:10px;font-size:12px;}
        .trade-item{padding:10px;border-bottom:1px solid #333;font-size:12px;}
        .trade-profit{color:#00ff88;}
        .trade-loss{color:#ff4444;}
        .mtf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:8px;margin-top:8px;}
        .mtf-item{background:#0a0a0a;padding:8px;border-radius:8px;text-align:center;font-size:12px;}
        .trend-bull{color:#00ff88;}
        .trend-bear{color:#ff4444;}
        .trend-neutral{color:#ffaa00;}
        @keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}
        .input-group{margin-bottom:10px;}
        .input-group label{display:block;font-size:12px;color:#888;margin-bottom:4px;}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AI TRADING BOT PRO</h1>
        <div class="badge">2 индикатора | 6 стратегии | MTF тренд</div>
        <div class="live-dot">● АКТИВЕН</div>
    </div>
    
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('demo')">📱 DEMO</button>
        <button class="tab-btn" onclick="switchTab('live')">🔴 LIVE</button>
        <button class="tab-btn" onclick="switchTab('backtest')">📊 БЕКТЕСТ</button>
    </div>
    
    <!-- DEMO TAB -->
    <div id="demoTab" class="tab-content active">
        <div class="card">
            <h3>💰 ДЕМО КАПИТАЛ</h3>
            <div class="stat-value" id="balance">$0</div>
            <div class="stat-label">Текущ баланс</div>
            <div class="row">
                <span>Общ P&L: <span id="totalPnl">$0</span></span>
                <span>Процент: <span id="totalPnlPercent">0%</span></span>
            </div>
            <div style="margin-top:12px;">
                <select id="demoBalanceSelect" onchange="changeDemoBalance()">
                    <option value="1000">$1,000</option>
                    <option value="5000">$5,000</option>
                    <option value="10000" selected>$10,000</option>
                    <option value="25000">$25,000</option>
                    <option value="50000">$50,000</option>
                </select>
                <button onclick="resetBot()" class="danger">🔄 Рестарт</button>
            </div>
        </div>
        
        <div class="card">
            <h3>🧠 AI АНАЛИЗ</h3>
            <div id="aiDecision" class="stat-value" style="font-size:26px;">-</div>
            <div class="row">
                <span>Увереност: <span id="confidence">0%</span></span>
                <span>Причина: <span id="reason">-</span></span>
            </div>
            <div class="analysis-box" id="analysisDetails"></div>
        </div>
        
        <div class="card">
            <h3>⚙️ СТРАТЕГИЯ</h3>
            <select id="strategySelect">
                <option>Aggressive Scalp</option>
                <option>Conservative</option>
                <option>Breakout Hunter</option>
                <option>Reversal Master</option>
                <option>Trend Follower</option>
                <option selected>SMC Pro</option>
            </select>
            <button onclick="changeStrategy()">✅ Смени стратегията</button>
        </div>
        
        <div class="card">
            <h3>📈 ТЕКУЩА ПОЗИЦИЯ</h3>
            <div id="positionDisplay" class="position-none">Няма отворена позиция</div>
            <div id="slTpInfo" style="margin-top:8px;font-size:11px;color:#888;"></div>
        </div>
        
        <div class="card">
            <h3>📊 СТАТИСТИКА</h3>
            <div class="row">
                <span>Сделки: <b id="totalTrades">0</b></span>
                <span>Печалби: <b id="wins" style="color:#00ff88;">0</b></span>
                <span>Загуби: <b id="losses" style="color:#ff4444;">0</b></span>
            </div>
            <div class="row">
                <span>Win Rate: <b id="winRate">0%</b></span>
            </div>
        </div>
    </div>
    
    <!-- LIVE TAB -->
    <div id="liveTab" class="tab-content">
        <div class="card">
            <h3>🔌 РЕАЛНА СМЕТКА</h3>
            <select id="exchangeSelect">
                <option value="mexc">MEXC</option>
                <option value="bingx">BingX</option>
            </select>
            <input type="text" id="apiKey" placeholder="API Key" class="input-field">
            <input type="password" id="secretKey" placeholder="Secret Key" class="input-field">
            <input type="password" id="passphrase" placeholder="Passphrase (само MEXC)" class="input-field">
            <button onclick="connectLive()">🔗 СВЪРЖИ</button>
            <div id="liveBalance" class="analysis-box" style="margin-top:12px;"></div>
        </div>
    </div>
    
    <!-- BACKTEST TAB -->
    <div id="backtestTab" class="tab-content">
        <div class="card">
            <h3>📈 ТЕСТ НА СТРАТЕГИЯ</h3>
            <select id="backtestStrategy">
                <option>SMC Pro</option>
                <option>Aggressive Scalp</option>
                <option>Conservative</option>
                <option>Breakout Hunter</option>
                <option>Reversal Master</option>
                <option>Trend Follower</option>
            </select>
            <input type="number" id="backtestLeverage" placeholder="Леверидж (1-125)" value="1" min="1" max="125" class="input-field">
            <div class="row">
                <button onclick="runBacktest(7)">📊 Тест 7 дни</button>
                <button onclick="runBacktest(30)">📈 Тест 30 дни</button>
            </div>
            <div id="backtestResult" class="analysis-box"></div>
        </div>
    </div>
    
    <!-- MTF ТРЕНД (винаги видим) -->
    <div class="card">
        <h3>⏰ MTF ТРЕНД (1m/5m/15m/1h/4h)</h3>
        <div id="mtfTrendTable" class="mtf-grid"></div>
    </div>
    
    <!-- История сделки -->
    <div class="card">
        <h3>📜 ИСТОРИЯ НА СДЕЛКИТЕ</h3>
        <div id="tradesList" style="max-height:250px;overflow-y:auto;"></div>
    </div>

    <script>
        let updateInterval;
        
        function switchTab(tab) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tab + 'Tab').classList.add('active');
            event.target.classList.add('active');
        }
        
        async function fetchData() {
            try {
                const [status, analysis, trades] = await Promise.all([
                    fetch('/api/status').then(r=>r.json()),
                    fetch('/api/analysis').then(r=>r.json()),
                    fetch('/api/trades').then(r=>r.json())
                ]);
                updateUI(status, analysis, trades);
            } catch(e) { console.error(e); }
        }
        
        function updateUI(status, analysis, trades) {
            document.getElementById('balance').innerHTML = '$' + status.balance.toFixed(2);
            document.getElementById('totalPnl').innerHTML = (status.total_pnl >= 0 ? '+' : '') + '$' + Math.abs(status.total_pnl).toFixed(2);
            document.getElementById('totalPnlPercent').innerHTML = (status.total_pnl_percent >= 0 ? '+' : '') + status.total_pnl_percent + '%';
            
            document.getElementById('aiDecision').innerHTML = analysis.decision;
            document.getElementById('confidence').innerHTML = Math.round(analysis.confidence) + '%';
            document.getElementById('reason').innerHTML = analysis.reason;
            
            let details = '';
            if(analysis.v1_analysis) {
                details += `📊 V1 (SMC): Тренд=${analysis.v1_analysis.trend} | RSI=${Math.round(analysis.v1_analysis.rsi)}<br>`;
            }
            if(analysis.v2_analysis) {
                details += `📈 V2 (${analysis.v2_analysis.mode}): Обем=${analysis.v2_analysis.volume_ratio.toFixed(1)}x | Делта=${analysis.v2_analysis.delta_positive ? 'ПОЗИТИВНА' : 'НЕГАТИВНА'}<br>`;
                details += `💰 Цена: $${analysis.current_price.toFixed(2)} | ATR: $${analysis.atr.toFixed(2)}`;
            }
            document.getElementById('analysisDetails').innerHTML = details;
            
            const posDiv = document.getElementById('positionDisplay');
            if(status.position) {
                posDiv.className = `position-${status.position.toLowerCase()}`;
                posDiv.innerHTML = `${status.position} ПОЗИЦИЯ<br>Вход: $${status.entry_price}<br>Незатворена: ${status.unrealized_pnl}%`;
                document.getElementById('slTpInfo').innerHTML = `🎯 TP1: $${status.tp1} &nbsp; TP2: $${status.tp2} &nbsp; TP3: $${status.tp3}<br>🛑 SL: $${status.sl}`;
            } else {
                posDiv.className = 'position-none';
                posDiv.innerHTML = 'Няма отворена позиция';
                document.getElementById('slTpInfo').innerHTML = '';
            }
            
            document.getElementById('totalTrades').innerHTML = status.trades_count;
            document.getElementById('wins').innerHTML = status.wins;
            document.getElementById('losses').innerHTML = status.losses;
            document.getElementById('winRate').innerHTML = status.win_rate + '%';
            
            const tradesDiv = document.getElementById('tradesList');
            if(trades.length === 0) {
                tradesDiv.innerHTML = '<div class="trade-item">Няма направени сделки</div>';
            } else {
                tradesDiv.innerHTML = trades.map(t => `
                    <div class="trade-item">
                        ${t.type} | Вход: $${t.entry_price} | Изход: $${t.exit_price}<br>
                        P&L: <span class="${t.pnl_percent >= 0 ? 'trade-profit' : 'trade-loss'}">${t.pnl_percent >= 0 ? '+' : ''}${t.pnl_percent}%</span>
                        | Причина: ${t.reason}
                    </div>
                `).join('');
            }
        }
        
        async function fetchMTFTrend() {
            try {
                const res = await fetch('/api/mtf_trend');
                const trends = await res.json();
                const mtfDiv = document.getElementById('mtfTrendTable');
                if(trends.error) {
                    mtfDiv.innerHTML = '<div>Зареждане...</div>';
                    return;
                }
                mtfDiv.innerHTML = Object.entries(trends).map(([tf, trend]) => `
                    <div class="mtf-item">
                        <strong>${tf}</strong><br>
                        <span class="trend-${trend}">${trend === 'bull' ? '⬆️ БИЧИ' : trend === 'bear' ? '⬇️ МЕЧИ' : '➡️ НЕУТРАЛЕН'}</span>
                    </div>
                `).join('');
            } catch(e) { console.error(e); }
        }
        
        async function changeStrategy() {
            const strategy = document.getElementById('strategySelect').value;
            await fetch('/api/strategy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({strategy: strategy})
            });
            fetchData();
        }
        
        async function changeDemoBalance() {
            const select = document.getElementById('demoBalanceSelect');
            let balance = parseFloat(select.value);
            await fetch('/api/demo/balance', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({balance: balance})
            });
            fetchData();
        }
        
        async function resetBot() {
            await fetch('/api/reset', {method: 'POST'});
            fetchData();
        }
        
        async function connectLive() {
            const exchange = document.getElementById('exchangeSelect').value;
            const apiKey = document.getElementById('apiKey').value;
            const secretKey = document.getElementById('secretKey').value;
            const passphrase = document.getElementById('passphrase').value;
            
            const res = await fetch('/api/live/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({exchange, api_key: apiKey, secret_key: secretKey, passphrase})
            });
            const result = await res.json();
            if(result.status === 'connected') {
                const balanceRes = await fetch('/api/live/balance');
                const balanceData = await balanceRes.json();
                document.getElementById('liveBalance').innerHTML = `
                    ✅ Свързани с ${exchange.toUpperCase()}<br>
                    Баланс: $${balanceData.balance || 0} USDT<br>
                    <small style="color:#888;">Демо режим за тест</small>
                `;
            } else {
                document.getElementById('liveBalance').innerHTML = '❌ Грешка при свързване';
            }
        }
        
        async function runBacktest(days) {
            const strategy = document.getElementById('backtestStrategy').value;
            const leverage = parseFloat(document.getElementById('backtestLeverage').value) || 1;
            const res = await fetch('/api/backtest', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ strategy, days, leverage, initial_balance: 10000 })
            });
            const result = await res.json();
            if(result.error) {
                document.getElementById('backtestResult').innerHTML = `<div class="analysis-box">❌ ${result.error}</div>`;
                return;
            }
            document.getElementById('backtestResult').innerHTML = `
                <div class="analysis-box">
                    <b>📊 РЕЗУЛТАТ (${days} дни, х${leverage})</b><br>
                    Начален баланс: $${result.initial_balance}<br>
                    Краен баланс: $${result.final_balance}<br>
                    Обща печалба: ${result.total_return > 0 ? '+' : ''}${result.total_return}%<br>
                    Сделки: ${result.total_trades} | Win Rate: ${result.win_rate}%<br>
                    Печалби: ${result.wins} | Загуби: ${result.losses}
                </div>
            `;
        }
        
        setInterval(fetchData, 2000);
        setInterval(fetchMTFTrend, 10000);
        fetchData();
        fetchMTFTrend();
    </script>
</body>
</html>
'''


# ============================================
# ФЛАСК РУТОВЕ
# ============================================

engine = TradingEngine(10000, "SMC Pro")
demo_balance = 10000

@app.route('/')
def home():
    return DASHBOARD_HTML

@app.route('/api/status')
def api_status():
    status, _ = engine.update()
    return jsonify(status)

@app.route('/api/analysis')
def api_analysis():
    _, analysis = engine.update()
    if analysis is None:
        market_data = engine.market_history
        if market_data:
            analysis = engine.ai_brain.analyze(market_data)
        else:
            analysis = {"decision": "HOLD", "confidence": 0, "reason": "Няма данни", "current_price": 0}
    return jsonify(analysis)

@app.route('/api/trades')
def api_trades():
    return jsonify(engine.trades[-20:])

@app.route('/api/strategy', methods=['POST'])
def api_strategy():
    data = request.json
    strategy = data.get('strategy', 'SMC Pro')
    engine.change_strategy(strategy)
    return jsonify({"status": "ok", "strategy": strategy})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    engine.reset()
    return jsonify({"status": "ok"})

@app.route('/api/demo/balance', methods=['GET', 'POST'])
def demo_balance_api():
    global demo_balance
    if request.method == 'POST':
        data = request.json
        new_balance = float(data.get('balance', 10000))
        demo_balance = new_balance
        engine.set_demo_balance(demo_balance)
        return jsonify({"status": "ok", "balance": demo_balance})
    return jsonify({"balance": demo_balance})

@app.route('/api/backtest', methods=['POST'])
def backtest_api():
    data = request.json
    strategy = data.get('strategy', 'SMC Pro')
    days = data.get('days', 7)
    leverage = data.get('leverage', 1)
    initial_balance = data.get('initial_balance', 10000)
    
    # Генериране на исторически данни
    historical = []
    base_price = 50000
    for i in range(30 * 24 * 2):
        change = random.uniform(-0.02, 0.02)
        base_price = base_price * (1 + change)
        historical.append({
            "timestamp": time.time() - (30*24*3600 - i*1800),
            "open": base_price * random.uniform(0.998, 1.002),
            "high": base_price * random.uniform(1, 1.01),
            "low": base_price * random.uniform(0.99, 1),
            "close": base_price,
            "volume": random.randint(50, 500)
        })
    
    result = BacktestEngine.run(historical[-days*48:], strategy, leverage, initial_balance)
    return jsonify(result)

@app.route('/api/mtf_trend')
def mtf_trend_api():
    if len(engine.market_history) < 100:
        return jsonify({"error": "Няма достатъчно данни за MTF тренд"})
    
    trends = {}
    close_prices = [c['close'] for c in engine.market_history]
    for tf, label in [(5, "5m"), (15, "15m"), (60, "1h"), (240, "4h")]:
        closes = close_prices[-tf*2:]
        if len(closes) >= 21:
            ema9 = IndicatorV1.calculate_ema(closes, 9)
            ema21 = IndicatorV1.calculate_ema(closes, 21)
            if ema9 > ema21:
                trends[label] = "bull"
            elif ema9 < ema21:
                trends[label] = "bear"
            else:
                trends[label] = "neutral"
        else:
            trends[label] = "neutral"
    
    # Добавяме 1m (симулиран)
    trends["1m"] = "bull" if len(close_prices) > 5 and close_prices[-1] > close_prices[-5] else "bear" if close_prices[-1] < close_prices[-5] else "neutral"
    
    return jsonify(trends)

@app.route('/api/live/connect', methods=['POST'])
def live_connect():
    global live_connected, live_exchange, live_api_key, live_secret_key, live_passphrase
    data = request.json
    live_exchange = data.get('exchange', 'mexc')
    live_api_key = data.get('api_key')
    live_secret_key = data.get('secret_key')
    live_passphrase = data.get('passphrase', '')
    live_connected = True
    return jsonify({"status": "connected", "exchange": live_exchange})

@app.route('/api/live/balance')
def live_balance():
    if not live_connected:
        return jsonify({"error": "Не сте свързани"})
    # Симулиран баланс за тест
    return jsonify({"balance": 50000, "available": 45000, "currency": "USDT"})


# ============================================
# СТАРТ
# ============================================

if __name__ == '__main__':
    print("="*60)
    print("🤖 AI TRADING BOT PRO - ПЪЛНА ВЕРСИЯ")
    print("="*60)
    print("📊 Индикатори: BTC Scalp Pro V1 + V2")
    print("🎯 Стратегии: 6 режима (SMC Pro, Aggressive Scalp и др.)")
    print("📱 Функции: Демо/Live сметка, Бектест 7/30 дни, MTF тренд")
    print("🚀 Стартиране на http://localhost:8080")
    print("="*60)
    app.run(host='0.0.0.0', port=8080, debug=True)
