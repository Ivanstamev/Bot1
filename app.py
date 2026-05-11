
from flask import Flask, render_template_string, request, jsonify
import json
import random
import math
import time
from datetime import datetime

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
# ИНДИКАТОР 2: BTC Scalp Pro v2
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
            "liq_high": liq_high,
            "liq_low": liq_low,
            "mtf_bull": mtf_bull
        }


# ============================================
# ОБЕДИНЕН AI МОЗЪК
# ============================================

class UnifiedAIBrain:
    def __init__(self, strategy="SMC Pro"):
        self.indicator_v1 = IndicatorV1()
        self.indicator_v2 = IndicatorV2()
        self.strategy = strategy
        
    def analyze(self, market_data):
        v1_result = self.indicator_v1.analyze(market_data)
        v2_result = self.indicator_v2.analyze(market_data, self.strategy)
        current_price = market_data[-1]['close'] if market_data else 50000
        atr = v1_result.get('atr', current_price * 0.01)
        
        v2_signal = v2_result.get('signal', 'HOLD')
        
        if v2_signal != "HOLD":
            final_signal = v2_signal
            confidence = 85
            reason = f"{self.strategy}: RSI={v2_result['rsi']:.0f}"
        else:
            final_signal = "HOLD"
            confidence = 50
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
        
        return {
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
                trades.append({"type": "LONG", "pnl": pnl})
                position = None
            elif position == 'SHORT' and current_price >= entry_price * 1.02:
                pnl = (entry_price - current_price) / entry_price * 100 * leverage
                balance += balance * (pnl / 100)
                trades.append({"type": "SHORT", "pnl": pnl})
                position = None
            
            if position is None and analysis["decision"] != "HOLD" and analysis["confidence"] >= 70:
                position = analysis["decision"]
                entry_price = current_price
        
        wins = len([t for t in trades if t["pnl"] > 0])
        total_pnl = (balance - initial_balance) / initial_balance * 100
        
        return {
            "initial_balance": initial_balance,
            "final_balance": round(balance, 2),
            "total_return": round(total_pnl, 2),
            "total_trades": len(trades),
            "wins": wins,
            "losses": len(trades) - wins,
            "win_rate": round(wins / len(trades) * 100, 2) if trades else 0
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
        elif self.position == 'SHORT':
            if current_price >= self.sl:
                self.close_position(current_price, "SL")
            elif current_price <= self.tp1:
                self.close_position(current_price, "TP1")
        
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
            "pnl_percent": round(pnl, 2),
            "reason": reason
        })
        self.position = None
    
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
# HTML DASHBOARD (опростена версия)
# ============================================

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>🤖 AI Trading Bot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{background:#0a0a0a;font-family:Arial;color:white;padding:12px;}
        h1{color:#00ff88;font-size:22px;text-align:center;margin-bottom:16px;}
        .card{background:#1a1a2e;border-radius:16px;padding:16px;margin-bottom:16px;}
        .stat-value{font-size:28px;font-weight:bold;color:#00ff88;}
        .row{display:flex;justify-content:space-between;margin:8px 0;}
        button{background:#00ff88;color:#0a0a0a;border:none;padding:10px;border-radius:10px;cursor:pointer;font-weight:bold;margin:4px;}
        select{background:#1a1a2a;color:white;border:1px solid #00ff88;padding:10px;border-radius:10px;width:100%;margin:8px 0;}
        .position-long{background:rgba(0,255,0,0.2);border:1px solid #00ff00;padding:12px;border-radius:12px;text-align:center;}
        .position-short{background:rgba(255,0,0,0.2);border:1px solid #ff0000;padding:12px;border-radius:12px;text-align:center;}
        .position-none{background:#222;border:1px solid #444;padding:12px;border-radius:12px;text-align:center;}
        .trade-item{padding:8px;border-bottom:1px solid #333;font-size:12px;}
        .profit{color:#00ff88;}
        .loss{color:#ff4444;}
    </style>
</head>
<body>
    <h1>🤖 AI TRADING BOT</h1>
    
    <div class="card">
        <div class="stat-value" id="balance">$0</div>
        <div class="row">
            <span>P&L: <span id="totalPnl">$0</span></span>
            <span>Win Rate: <span id="winRate">0%</span></span>
        </div>
    </div>
    
    <div class="card">
        <h3>🧠 AI СИГНАЛ</h3>
        <div class="stat-value" id="aiDecision" style="font-size:24px;">-</div>
        <div id="reason" style="color:#888;font-size:12px;margin-top:8px;"></div>
    </div>
    
    <div class="card">
        <select id="strategySelect">
            <option>Aggressive Scalp</option>
            <option>Conservative</option>
            <option>Breakout Hunter</option>
            <option>Reversal Master</option>
            <option>Trend Follower</option>
            <option selected>SMC Pro</option>
        </select>
        <select id="demoBalanceSelect">
            <option value="1000">$1,000</option>
            <option value="5000">$5,000</option>
            <option value="10000" selected>$10,000</option>
            <option value="25000">$25,000</option>
            <option value="50000">$50,000</option>
        </select>
        <button onclick="changeStrategy()">Смени стратегия</button>
        <button onclick="changeBalance()">Смени баланс</button>
        <button onclick="resetBot()">Рестарт</button>
    </div>
    
    <div class="card">
        <div id="positionDisplay" class="position-none">Няма позиция</div>
        <div id="slTpInfo" style="font-size:12px;margin-top:8px;"></div>
    </div>
    
    <div class="card">
        <h3>📜 История</h3>
        <div id="tradesList"></div>
    </div>

    <script>
        async function fetchData() {
            try {
                const [status, analysis, trades] = await Promise.all([
                    fetch('/api/status').then(r=>r.json()),
                    fetch('/api/analysis').then(r=>r.json()),
                    fetch('/api/trades').then(r=>r.json())
                ]);
                document.getElementById('balance').innerHTML = '$' + status.balance;
                document.getElementById('totalPnl').innerHTML = (status.total_pnl >= 0 ? '+' : '') + '$' + Math.abs(status.total_pnl);
                document.getElementById('winRate').innerHTML = status.win_rate + '%';
                document.getElementById('aiDecision').innerHTML = analysis.decision;
                document.getElementById('reason').innerHTML = analysis.reason;
                
                const posDiv = document.getElementById('positionDisplay');
                if(status.position) {
                    posDiv.className = `position-${status.position.toLowerCase()}`;
                    posDiv.innerHTML = `${status.position} @ $${status.entry_price}<br>P&L: ${status.unrealized_pnl}%`;
                    document.getElementById('slTpInfo').innerHTML = `SL: $${status.sl} | TP: $${status.tp1}`;
                } else {
                    posDiv.className = 'position-none';
                    posDiv.innerHTML = 'Няма отворена позиция';
                }
                
                document.getElementById('tradesList').innerHTML = trades.map(t => `
                    <div class="trade-item">
                        ${t.type} | ${t.entry_price} → ${t.exit_price}<br>
                        P&L: <span class="${t.pnl_percent >= 0 ? 'profit' : 'loss'}">${t.pnl_percent >= 0 ? '+' : ''}${t.pnl_percent}%</span>
                    </div>
                `).join('');
            } catch(e) { console.error(e); }
        }
        
        async function changeStrategy() {
            const strategy = document.getElementById('strategySelect').value;
            await fetch('/api/strategy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({strategy})});
            fetchData();
        }
        
        async function changeBalance() {
            const balance = parseFloat(document.getElementById('demoBalanceSelect').value);
            await fetch('/api/demo/balance', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({balance})});
            fetchData();
        }
        
        async function resetBot() {
            await fetch('/api/reset', {method:'POST'});
            fetchData();
        }
        
        setInterval(fetchData, 2000);
        fetchData();
    </script>
</body>
</html>
'''

# ============================================
# ФЛАСК РУТОВЕ
# ============================================

engine = TradingEngine(10000, "SMC Pro")

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
    if analysis is None and engine.market_history:
        analysis = engine.ai_brain.analyze(engine.market_history)
    elif analysis is None:
        analysis = {"decision": "HOLD", "confidence": 0, "reason": "Зареждане..."}
    return jsonify(analysis)

@app.route('/api/trades')
def api_trades():
    return jsonify(engine.trades[-20:])

@app.route('/api/strategy', methods=['POST'])
def api_strategy():
    data = request.json
    engine.change_strategy(data.get('strategy', 'SMC Pro'))
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    engine.reset()
    return jsonify({"status": "ok"})

@app.route('/api/demo/balance', methods=['POST'])
def demo_balance_api():
    data = request.json
    engine.set_demo_balance(float(data.get('balance', 10000)))
    return jsonify({"status": "ok"})


# ============================================
# СТАРТ
# ============================================

if __name__ == '__main__':
    print("🤖 AI Trading Bot стартира на http://0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080)
