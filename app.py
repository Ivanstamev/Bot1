# app.py - Бот с интегрирани индикатори (без TradingView)
from flask import Flask, render_template_string, request, jsonify
import json
import random
import math
from datetime import datetime
import time

app = Flask(__name__)

# ============================================
# ИНДИКАТОР 1: BTC Scalp Pro v1 - SMC + MTF
# ============================================

class IndicatorV1:
    """Първи индикатор - Order Blocks, VWAP, MTF Trend, Liquidity Zones"""
    
    @staticmethod
    def calculate_ema(data, period):
        """Изчислява EMA"""
        if len(data) < period:
            return data[-1] if data else 0
        k = 2 / (period + 1)
        ema = data[0]
        for i in range(1, len(data)):
            ema = data[i] * k + ema * (1 - k)
        return ema
    
    @staticmethod
    def calculate_rsi(data, period=14):
        """Изчислява RSI"""
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
        """Изчислява ATR"""
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
        """Изчислява VWAP (среднопретеглена цена спрямо обем)"""
        if not data:
            return 0
        total_value = 0
        total_volume = 0
        for candle in data[-100:]:  # последните 100 свещи
            typical = (candle['high'] + candle['low'] + candle['close']) / 3
            total_value += typical * candle['volume']
            total_volume += candle['volume']
        return total_value / total_volume if total_volume > 0 else 0
    
    def analyze(self, market_data):
        """
        Анализ по метода на първия индикатор
        Връща: trend (bull/bear/neutral), ob_levels, liquidity_zones
        """
        close_prices = [c['close'] for c in market_data[-50:]]
        highs = [c['high'] for c in market_data[-50:]]
        lows = [c['low'] for c in market_data[-50:]]
        
        # EMA изчисления
        ema9 = self.calculate_ema(close_prices, 9)
        ema21 = self.calculate_ema(close_prices, 21)
        
        # RSI
        rsi = self.calculate_rsi(close_prices, 14)
        
        # VWAP
        vwap = self.calculate_vwap(market_data[-100:])
        
        # ATR
        atr = self.calculate_atr(highs, lows, close_prices, 14)
        
        current_price = close_prices[-1]
        
        # Order Blocks (прости)
        bull_ob = min(lows[-5:]) if len(lows) >= 5 else current_price * 0.99
        bear_ob = max(highs[-5:]) if len(highs) >= 5 else current_price * 1.01
        
        # Ликвидни зони
        liq_high = max(highs[-20:]) if len(highs) >= 20 else current_price * 1.02
        liq_low = min(lows[-20:]) if len(lows) >= 20 else current_price * 0.98
        
        # MTF тренд (симулация на множествени таймфрейми)
        trends = []
        for tf in [1, 5, 15, 60, 240]:
            tf_ema9 = self.calculate_ema(close_prices[-tf*20:], 9) if len(close_prices) >= tf*20 else ema9
            tf_ema21 = self.calculate_ema(close_prices[-tf*20:], 21) if len(close_prices) >= tf*20 else ema21
            trends.append(1 if tf_ema9 > tf_ema21 else -1)
        
        mtf_score = sum(trends)
        mtf_bull = mtf_score >= 3
        mtf_bear = mtf_score <= -3
        
        # Волatility филтър
        atr_sma = sum(close_prices[-50:]) / 50 * 0.01  # приблизителен SMA на ATR
        vol_ok = atr > atr_sma * 1.2
        
        # Сигнали
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
    """Втори индикатор - 5 режима, Cumulative Delta, Liquidity Clusters, Gaps"""
    
    @staticmethod
    def calculate_delta(volume, high, low, close):
        """Изчислява приблизителна делта (buy/sell volume)"""
        if high == low:
            return volume / 2
        buy_volume = volume * (close - low) / (high - low)
        sell_volume = volume * (high - close) / (high - low)
        return buy_volume - sell_volume
    
    @staticmethod
    def calculate_cumulative_delta(market_data):
        """Изчислява кумулативна делта"""
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
        """Намира ликвидни кластери (нива с висок обем)"""
        recent = market_data[-30:]
        if not recent:
            return 0, 0
        # Най-висок и най-нисък обем
        max_vol_candle = max(recent, key=lambda x: x['volume'])
        min_vol_candle = min(recent, key=lambda x: x['volume'])
        return max_vol_candle['high'], min_vol_candle['low']
    
    def analyze(self, market_data, mode="SMC Pro"):
        """
        Анализ по метода на втория индикатор
        mode: Aggressive Scalp, Conservative, Breakout, Reversal, Trend Follow, SMC Pro
        """
        close_prices = [c['close'] for c in market_data[-50:]]
        highs = [c['high'] for c in market_data[-50:]]
        lows = [c['low'] for c in market_data[-50:]]
        volumes = [c['volume'] for c in market_data[-50:]]
        
        current_price = close_prices[-1]
        avg_volume = sum(volumes) / len(volumes) if volumes else 1
        volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1
        
        # EMA
        ema9 = IndicatorV1.calculate_ema(close_prices, 9)
        ema21 = IndicatorV1.calculate_ema(close_prices, 21)
        
        # RSI
        rsi = IndicatorV1.calculate_rsi(close_prices, 14)
        
        # ATR
        atr = IndicatorV1.calculate_atr(highs, lows, close_prices, 14)
        
        # VWAP
        vwap = IndicatorV1.calculate_vwap(market_data[-100:])
        
        # Cumulative Delta
        cum_delta = self.calculate_cumulative_delta(market_data)
        delta_positive = cum_delta > 0
        
        # Ликвидни кластери
        liq_high, liq_low = self.find_liquidity_clusters(market_data)
        
        # Гепове
        last_candle = market_data[-1]
        prev_candle = market_data[-2] if len(market_data) > 1 else last_candle
        gap_up = last_candle['low'] > prev_candle['high'] + atr * 0.3
        gap_down = last_candle['high'] < prev_candle['low'] - atr * 0.3
        
        # MTF потвърждение (5m)
        mtf_data = market_data[-10:]  # симулация на по-висок TF
        mtf_ema9 = IndicatorV1.calculate_ema([c['close'] for c in mtf_data], 9)
        mtf_ema21 = IndicatorV1.calculate_ema([c['close'] for c in mtf_data], 21)
        mtf_bull = mtf_ema9 > mtf_ema21
        mtf_bear = mtf_ema9 < mtf_ema21
        
        # Параметри според режима
        modes_config = {
            "Aggressive Scalp": {"rsi_min": 30, "rsi_max": 70, "vol_mult": 0.8, "atr_mult": 1.2},
            "Conservative": {"rsi_min": 45, "rsi_max": 60, "vol_mult": 1.2, "atr_mult": 1.8},
            "Breakout Hunter": {"rsi_min": 35, "rsi_max": 75, "vol_mult": 1.5, "atr_mult": 1.0},
            "Reversal Master": {"rsi_min": 25, "rsi_max": 45, "vol_mult": 1.3, "atr_mult": 1.4},
            "Trend Follower": {"rsi_min": 50, "rsi_max": 75, "vol_mult": 1.0, "atr_mult": 1.5},
            "SMC Pro": {"rsi_min": 40, "rsi_max": 65, "vol_mult": 0.9, "atr_mult": 1.3}
        }
        
        cfg = modes_config.get(mode, modes_config["SMC Pro"])
        
        # Условия за сигнали
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
        else:  # SMC Pro
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
    """Обединява двата индикатора за максимална точност"""
    
    def __init__(self, strategy="SMC Pro"):
        self.indicator_v1 = IndicatorV1()
        self.indicator_v2 = IndicatorV2()
        self.strategy = strategy
        self.decision_history = []
        
    def analyze(self, market_data):
        """
        Анализира пазара с двата индикатора
        Взима решение на базата на консенсус между тях
        """
        # Анализ от двата индикатора
        v1_result = self.indicator_v1.analyze(market_data)
        v2_result = self.indicator_v2.analyze(market_data, self.strategy)
        
        current_price = market_data[-1]['close'] if market_data else 50000
        atr = v1_result.get('atr', current_price * 0.01)
        
        # Консенсус между сигналите
        v1_signal = v1_result.get('signal', 'HOLD')
        v2_signal = v2_result.get('signal', 'HOLD')
        
        # Тежест на сигналите (V2 е по-важен защото има режими)
        if v2_signal != "HOLD":
            final_signal = v2_signal
            confidence = 85
            reason = f"Анализ V2 ({self.strategy}): RSI={v2_result['rsi']:.0f}, Обем={v2_result['volume_ratio']:.1f}x"
        elif v1_signal != "HOLD":
            final_signal = v1_signal
            confidence = 70
            reason = f"Анализ V1 (SMC): MTF={'БИЧИ' if v1_result['mtf_bull'] else 'МЕЧИ'}, RSI={v1_result['rsi']:.0f}"
        else:
            final_signal = "HOLD"
            confidence = max(
                100 - abs(v1_result['rsi'] - 50) * 2,
                50
            )
            reason = f"Няма ясен сигнал. RSI={v1_result['rsi']:.0f}, Обем={v2_result['volume_ratio']:.1f}x"
        
        # Изчисляване на нива
        sl = 0
        tp1 = 0
        tp2 = 0
        tp3 = 0
        
        # Настройки според стратегията
        atr_mult_sl = 1.3
        atr_mult_tp = [1.0, 1.8, 2.8]
        
        modes_config = {
            "Aggressive Scalp": {"sl": 1.2, "tp": [1.0, 1.8, 2.5]},
            "Conservative": {"sl": 1.8, "tp": [1.2, 2.0, 3.0]},
            "Breakout Hunter": {"sl": 1.0, "tp": [1.5, 2.5, 3.5]},
            "Reversal Master": {"sl": 1.4, "tp": [1.0, 1.5, 2.0]},
            "Trend Follower": {"sl": 1.5, "tp": [1.2, 2.0, 2.8]},
            "SMC Pro": {"sl": 1.3, "tp": [1.0, 1.8, 2.8]}
        }
        
        cfg = modes_config.get(self.strategy, modes_config["SMC Pro"])
        
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
        """Генерира симулирани пазарни данни (за тест)"""
        # В реална версия тук идват данни от API
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
        """Обновява състоянието - извиква се периодично"""
        market_data = self.generate_market_data()
        current_price = market_data[-1]['close']
        
        # Проверка за TP/SL
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
        
        # AI анализ ако няма позиция
        if self.position is None:
            analysis = self.ai_brain.analyze(market_data)
            if analysis["decision"] in ["LONG", "SHORT"] and analysis["confidence"] >= 70:
                self.open_position(analysis, current_price)
        
        return self.get_status(current_price), analysis if self.position is None else None
    
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
    
    def reset(self):
        self.__init__(self.initial_balance, self.ai_brain.strategy)


# ============================================
# ФЛАСК РУТОВЕ
# ============================================

engine = TradingEngine(10000, "SMC Pro")
last_analysis = None

# HTML Dashboard с всички функции
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>AI Trading Bot - Собствен мозък</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{background:#0a0a0a;font-family:'Segoe UI',Arial;color:white;padding:15px;}
        .header{text-align:center;margin-bottom:20px;}
        h1{color:#00ff88;font-size:24px;}
        .badge{background:#00ff88;color:#0a0a0a;display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;margin-top:5px;}
        .grid{display:grid;grid-template-columns:1fr;gap:15px;}
        .card{background:linear-gradient(135deg,#1a1a2e,#0f0f1a);border-radius:20px;padding:20px;border:1px solid rgba(0,255,136,0.3);}
        .card h3{color:#00ff88;margin-bottom:15px;font-size:16px;border-left:3px solid #00ff88;padding-left:10px;}
        .stat-value{font-size:32px;font-weight:bold;color:#00ff88;}
        .stat-label{color:#888;font-size:12px;margin-top:5px;}
        .row{display:flex;justify-content:space-between;margin:10px 0;}
        .position-long{background:rgba(0,255,0,0.2);border:1px solid #00ff00;padding:12px;border-radius:12px;text-align:center;}
        .position-short{background:rgba(255,0,0,0.2);border:1px solid #ff0000;padding:12px;border-radius:12px;text-align:center;}
        .position-none{background:#222;border:1px solid #444;padding:12px;border-radius:12px;text-align:center;}
        button{background:#00ff88;color:#0a0a0a;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:bold;margin:5px;}
        button.danger{background:#ff4444;color:white;}
        button.secondary{background:#2a4a6a;color:white;}
        select{background:#1a1a2a;color:white;border:1px solid #00ff88;padding:10px;border-radius:10px;width:100%;margin-bottom:10px;}
        .trade-item{padding:10px;border-bottom:1px solid #333;font-size:12px;}
        .trade-profit{color:#00ff88;}
        .trade-loss{color:#ff4444;}
        .analysis-box{background:#0a0a0a;border-radius:12px;padding:12px;margin-top:10px;font-size:12px;}
        .signal-buy{background:rgba(0,255,0,0.1);border-left:3px solid #00ff00;}
        .signal-sell{background:rgba(255,0,0,0.1);border-left:3px solid #ff0000;}
        @keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}
        .live{color:#00ff88;animation:pulse 2s infinite;}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AI TRADING BOT</h1>
        <div class="badge">Мозък: 2 индикатора (V1 + V2) | 6 стратегии</div>
        <div class="live">● АКТИВЕН</div>
    </div>
    
    <div class="grid">
        <!-- Баланс -->
        <div class="card">
            <h3>💰 КАПИТАЛ</h3>
            <div class="stat-value" id="balance">$0</div>
            <div class="stat-label">Текущ баланс</div>
            <div class="row">
                <span>Общ P&L: <span id="totalPnl">$0</span></span>
                <span>Процент: <span id="totalPnlPercent">0%</span></span>
            </div>
        </div>
        
        <!-- AI Анализ -->
        <div class="card">
            <h3>🧠 AI АНАЛИЗ (СОБСТВЕН МОЗЪК)</h3>
            <div id="aiDecision" class="stat-value" style="font-size:28px;">-</div>
            <div class="row">
                <span>Увереност: <span id="confidence">0%</span></span>
                <span>Причина: <span id="reason">-</span></span>
            </div>
            <div class="analysis-box" id="analysisDetails"></div>
        </div>
        
        <!-- Стратегия -->
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
            <button class="danger" onclick="resetBot()">🔄 Рестарт</button>
        </div>
    </div>
    
    <div class="grid">
        <!-- Позиция -->
        <div class="card">
            <h3>📈 ТЕКУЩА ПОЗИЦИЯ</h3>
            <div id="positionDisplay" class="position-none">Няма отворена позиция</div>
            <div id="slTpInfo" style="margin-top:10px;font-size:12px;color:#888;"></div>
        </div>
        
        <!-- Статистика -->
        <div class="card">
            <h3>📊 СТАТИСТИКА</h3>
            <div class="row">
                <span>Сделки: <b id="totalTrades">0</b></span>
                <span>Печалби: <b id="wins" style="color:#00ff88;">0</b></span>
                <span>Загуби: <b id="losses" style="color:#ff4444;">0</b></span>
            </div>
            <div class="row">
                <span>Win Rate: <b id="winRate">0%</b></span>
                <span>Коефициент: <b id="profitFactor">0</b></span>
            </div>
        </div>
    </div>
    
    <!-- История сделки -->
    <div class="card">
        <h3>📜 ИСТОРИЯ НА СДЕЛКИТЕ</h3>
        <div id="tradesList" style="max-height:250px;overflow-y:auto;"></div>
    </div>

    <script>
        let updateInterval;
        
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
            tradesDiv.innerHTML = trades.map(t => `
                <div class="trade-item">
                    ${t.type} | Вход: $${t.entry_price} | Изход: $${t.exit_price}<br>
                    P&L: <span class="${t.pnl_percent >= 0 ? 'trade-profit' : 'trade-loss'}">${t.pnl_percent >= 0 ? '+' : ''}${t.pnl_percent}%</span>
                    | Причина: ${t.reason} | ${t.exit_time.slice(0,10)}
                </div>
            `).join('');
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
        
        async function resetBot() {
            await fetch('/api/reset', {method: 'POST'});
            fetchData();
        }
        
        setInterval(fetchData, 2000);
        fetchData();
    </script>
</body>
</html>
'''

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
        # Ако няма нов анализ, върни последния
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

if __name__ == '__main__':
    print("="*50)
    print("🤖 AI TRADING BOT - СОБСТВЕН МОЗЪК")
    print("="*50)
    print("📊 Интегрирани индикатори: BTC Scalp Pro V1 + V2")
    print("🎯 Стратегии: 6 режима")
    print("🧠 AI анализ: SMC + MTF + Order Flow + Delta")
    print("="*50)
    app.run(host='0.0.0.0', port=8080)
