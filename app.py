from flask import Flask, render_template_string, request, jsonify
import json
import random
from datetime import datetime

app = Flask(__name__)

# ============================================
# AI МОЗЪК - 6 СТРАТЕГИИ
# ============================================

class AIBrain:
    """AI мозък, който взема самостоятелни решения"""
    
    STRATEGIES = {
        "Aggressive Scalp": {
            "rsi_min": 30, "rsi_max": 70, "volume_mult": 0.8,
            "atr_mult": 1.2, "risk": 0.02,
            "description": "Висок риск - много сигнали"
        },
        "Conservative": {
            "rsi_min": 45, "rsi_max": 60, "volume_mult": 1.2,
            "atr_mult": 1.8, "risk": 0.01,
            "description": "Нисък риск - качествени сигнали"
        },
        "Breakout Hunter": {
            "rsi_min": 35, "rsi_max": 75, "volume_mult": 1.5,
            "atr_mult": 1.0, "risk": 0.015,
            "description": "Търси пробиви на нива"
        },
        "Reversal Master": {
            "rsi_min": 25, "rsi_max": 45, "volume_mult": 1.3,
            "atr_mult": 1.4, "risk": 0.018,
            "description": "Търси завои на тренда"
        },
        "Trend Follower": {
            "rsi_min": 50, "rsi_max": 75, "volume_mult": 1.0,
            "atr_mult": 1.5, "risk": 0.012,
            "description": "Следва силния тренд"
        },
        "SMC Pro": {
            "rsi_min": 40, "rsi_max": 65, "volume_mult": 0.9,
            "atr_mult": 1.3, "risk": 0.015,
            "description": "Smart Money Concepts"
        }
    }
    
    def __init__(self, strategy_name="SMC Pro"):
        self.strategy = self.STRATEGIES.get(strategy_name, self.STRATEGIES["SMC Pro"])
        self.strategy_name = strategy_name
        self.decision_history = []
        
    def analyze(self, market_data):
        """Анализира пазара и взема решение"""
        rsi = market_data.get('rsi', 50)
        ema9 = market_data.get('ema9', market_data.get('price', 0))
        ema21 = market_data.get('ema21', market_data.get('price', 0))
        volume_ratio = market_data.get('volume_ratio', 1)
        vwap = market_data.get('vwap', market_data.get('price', 0))
        price = market_data.get('price', 0)
        atr = market_data.get('atr', price * 0.01)
        
        # Условия за LONG
        conditions_long = 0
        total_conditions = 5
        
        if rsi >= self.strategy["rsi_min"] and rsi <= self.strategy["rsi_max"]:
            conditions_long += 1
        if ema9 > ema21:
            conditions_long += 1
        if volume_ratio >= self.strategy["volume_mult"]:
            conditions_long += 1
        if price > vwap:
            conditions_long += 1
            
        # Условия за SHORT
        conditions_short = 0
        if rsi >= 100 - self.strategy["rsi_max"] and rsi <= 100 - self.strategy["rsi_min"]:
            conditions_short += 1
        if ema9 < ema21:
            conditions_short += 1
        if volume_ratio >= self.strategy["volume_mult"]:
            conditions_short += 1
        if price < vwap:
            conditions_short += 1
        
        long_score = conditions_long / total_conditions
        short_score = conditions_short / total_conditions
        threshold = 0.6
        
        result = {"decision": "HOLD", "confidence": 0, "reason": "", "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0}
        
        if long_score >= threshold and long_score > short_score:
            result["decision"] = "LONG"
            result["confidence"] = long_score * 100
            result["reason"] = f"{conditions_long}/5 условия за LONG"
            result["sl"] = price - atr * self.strategy["atr_mult"]
            result["tp1"] = price + atr * 1.0
            result["tp2"] = price + atr * 1.8
            result["tp3"] = price + atr * 2.8
        elif short_score >= threshold and short_score > long_score:
            result["decision"] = "SHORT"
            result["confidence"] = short_score * 100
            result["reason"] = f"{conditions_short}/5 условия за SHORT"
            result["sl"] = price + atr * self.strategy["atr_mult"]
            result["tp1"] = price - atr * 1.0
            result["tp2"] = price - atr * 1.8
            result["tp3"] = price - atr * 2.8
        else:
            result["confidence"] = max(long_score, short_score) * 100
            result["reason"] = f"Няма достатъчно увереност ({result['confidence']:.0f}%)"
        
        self.decision_history.append({
            "time": datetime.now().isoformat(),
            "decision": result["decision"],
            "confidence": result["confidence"]
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
        self.ai_brain = AIBrain(strategy)
        self.last_market = {}
        
    def update_market(self, market_data):
        """Обновява състоянието на пазара"""
        self.last_market = market_data
        current_price = market_data.get('price', 0)
        
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
        
        # AI анализ ако няма отворена позиция
        if self.position is None:
            analysis = self.ai_brain.analyze(market_data)
            if analysis["decision"] in ["LONG", "SHORT"] and analysis["confidence"] >= 65:
                self.open_position(analysis, current_price)
        
        return self.get_status(current_price)
    
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
            "entry_price": self.entry_price,
            "exit_price": price,
            "entry_time": self.entry_time,
            "exit_time": datetime.now().isoformat(),
            "pnl_percent": pnl,
            "pnl_amount": pnl_amount,
            "reason": reason,
            "balance_after": self.balance
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
            "trades_count": len(self.trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(self.trades) * 100, 1) if len(self.trades) > 0 else 0
        }
    
    def get_stats(self):
        wins = len([t for t in self.trades if t["pnl_percent"] > 0])
        losses = len([t for t in self.trades if t["pnl_percent"] < 0])
        total = len(self.trades)
        win_rate = (wins / total * 100) if total > 0 else 0
        avg_win = sum([t["pnl_percent"] for t in self.trades if t["pnl_percent"] > 0]) / wins if wins > 0 else 0
        avg_loss = sum([t["pnl_percent"] for t in self.trades if t["pnl_percent"] < 0]) / losses if losses > 0 else 0
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2)
        }

# ============================================
# ФЛАСК РУТОВЕ
# ============================================

engine = TradingEngine(10000, "SMC Pro")

def get_market_data():
    base_price = 50000 + random.randint(-200, 200)
    return {
        "price": base_price,
        "rsi": random.randint(30, 70),
        "ema9": base_price * 0.998,
        "ema21": base_price * 0.995,
        "volume_ratio": random.uniform(0.5, 2.0),
        "vwap": base_price * 0.997,
        "atr": base_price * 0.01
    }

# HTML Dashboard
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head><title>AI Trading Bot</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#0a0a0a;font-family:Arial;color:white;padding:20px;}
.card{background:#1a1a2a;border-radius:16px;padding:20px;margin-bottom:20px;border:1px solid #00ff88;}
h1{color:#00ff88;text-align:center;margin-bottom:20px;}
.stat-value{font-size:32px;font-weight:bold;color:#00ff88;}
button{background:#00ff88;color:#0a0a0a;border:none;padding:10px 20px;border-radius:8px;margin:5px;cursor:pointer;}
select{background:#1a1a2a;color:white;border:1px solid #00ff88;padding:10px;border-radius:8px;}
.grid{display:grid;gap:15px;}
.position-long{background:rgba(0,255,0,0.2);padding:10px;border-radius:8px;text-align:center;}
.position-short{background:rgba(255,0,0,0.2);padding:10px;border-radius:8px;text-align:center;}
.position-none{background:#333;padding:10px;border-radius:8px;text-align:center;}
</style>
</head>
<body>
<h1>🤖 AI TRADING BOT</h1>
<div class="grid">
<div class="card"><h3>💰 Баланс</h3><div class="stat-value" id="balance">$0</div></div>
<div class="card"><h3>📊 AI Решение</h3><div id="aiDecision" class="stat-value" style="font-size:24px;">-</div><div id="aiReason"></div></div>
<div class="card"><h3>⚙️ Стратегия</h3><select id="strategy"><option>Aggressive Scalp</option><option>Conservative</option><option>Breakout Hunter</option><option>Reversal Master</option><option>Trend Follower</option><option selected>SMC Pro</option></select><button onclick="changeStrategy()">Смени</button><button onclick="resetBot()">Рестарт</button></div>
<div class="card"><h3>📈 Позиция</h3><div id="positionDisplay" class="position-none">Няма</div></div>
<div class="card"><h3>📋 Статистика</h3><div id="stats"></div></div>
</div>
<script>
async function updateData(){
    const s=await fetch('/api/status').then(r=>r.json());
    const a=await fetch('/api/ai').then(r=>r.json());
    document.getElementById('balance').innerHTML='$'+s.balance;
    document.getElementById('aiDecision').innerHTML=a.decision;
    document.getElementById('aiReason').innerHTML=a.reason;
    let posDiv=document.getElementById('positionDisplay');
    if(s.position){posDiv.className=`position-${s.position.toLowerCase()}`;
    posDiv.innerHTML=`${s.position} ПОЗИЦИЯ<br>Вход: $${s.entry_price}<br>Незатворена: ${s.unrealized_pnl}%`;}
    else{posDiv.className='position-none';posDiv.innerHTML='Няма отворена позиция';}
    document.getElementById('stats').innerHTML=`Сделки: ${s.trades_count} | Печалби: ${s.wins} | Загуби: ${s.losses}<br>Win Rate: ${s.win_rate}% | P&L: ${s.total_pnl_percent}%`;
}
async function changeStrategy(){const s=document.getElementById('strategy').value;await fetch('/api/strategy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({strategy:s})});updateData();}
async function resetBot(){await fetch('/api/reset',{method:'POST'});updateData();}
setInterval(updateData,3000);updateData();
</script>
</body>
</html>
'''

@app.route('/')
def home():
    return DASHBOARD_HTML

@app.route('/api/status')
def api_status():
    market = get_market_data()
    status = engine.update_market(market)
    return jsonify(status)

@app.route('/api/ai')
def api_ai():
    market = get_market_data()
    analysis = engine.ai_brain.analyze(market)
    return jsonify(analysis)

@app.route('/api/strategy', methods=['POST'])
def api_strategy():
    data = request.json
    strategy = data.get('strategy', 'SMC Pro')
    engine.ai_brain = AIBrain(strategy)
    return jsonify({"status": "ok", "strategy": strategy})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    global engine
    engine = TradingEngine(10000, engine.ai_brain.strategy_name)
    return jsonify({"status": "ok"})

@app.route('/webhook', methods=['POST'])
def webhook():
    signal = request.get_data(as_text=True)
    print(f"Signal: {signal}")
    return jsonify({"status": "ok", "signal": signal})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
