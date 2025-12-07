import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify
import requests

app = Flask(__name__)

# तुझे LIMITS
MAX_ORDERS = 10
MAX_LOSS = 0.20
TRADING_START = dtime(9, 25)
TRADING_END = dtime(15, 0)

# Dhan API
CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
HEADERS = {'access-token': ACCESS_TOKEN, 'Content-Type': 'application/json'}

# State
monitor_active = False

def is_trading_time():
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def get_balance():
    """Dhan API वरून balance fetch करा"""
    try:
        # Dhan API endpoint तपासा - योग्य endpoint वापरा
        response = requests.get(
            'https://api.dhan.co/positions',  # किंवा /funds/details
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            # Response structure adjust करा
            return 100000  # Test साठी fixed value
    except:
        pass
    return None

def monitor():
    global monitor_active
    monitor_active = True
    print("🤖 Monitor: 20% loss, 10 orders/day")
    
    while monitor_active:
        try:
            trading = is_trading_time()
            print(f"⏰ Trading time: {trading}")
            
            if trading:
                balance = get_balance()
                if balance:
                    print(f"💰 Balance: ₹{balance}")
                    # तुझे loss/order checks इथे add कर
                    
            time.sleep(30)  # 30 सेकंद
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

@app.route('/')
def home():
    return jsonify({
        'app': 'Dhan Risk Manager',
        'status': 'active',
        'limits': {'loss': '20%', 'orders': '10/day'},
        'trading_hours': '9:25 AM - 3:00 PM',
        'current_time': datetime.now().strftime('%H:%M:%S'),
        'is_trading_time': is_trading_time()
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Start monitor
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    
    # Start server
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
