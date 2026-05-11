from flask import Flask, jsonify, request
import random
from datetime import datetime

app = Flask(__name__)

# Търговски двигател
class TradingEngine:
    def __init__(self):
        self.balance = 10000
        self.position = None
        self.trades = []
    
    def get_status(self):
        return {
            "balance": self.balance,
            "position": self.position,
            "total_trades": len(self.trades)
        }

engine = TradingEngine()

@app.route('/')
def home():
    return {"status": "online", "message": "AI Trading Bot is running!"}

@app.route('/api/status')
def status():
    return jsonify(engine.get_status())

@app.route('/webhook', methods=['POST'])
def webhook():
    signal = request.get_data(as_text=True)
    print(f"Received signal: {signal}")
    return {"status": "ok", "signal": signal}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
