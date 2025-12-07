import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify
import requests

# ==================== CONFIGURATION ====================
app = Flask(__name__)

# तुझे नवीन LIMITS (20% loss, 10 orders/day)
MAX_ORDERS_PER_DAY = 10
MAX_LOSS_PERCENT = 0.20
TRADING_START = dtime(9, 25)
TRADING_END = dtime(15, 0)
CHECK_INTERVAL = 30  # 30 सेकंदात एकदा तपासणी (कमी करा)

# Dhan API Configuration
CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
BASE_URL = 'https://api.dhan.co'
HEADERS = {
    'access-token': ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# State Management
STATE_FILE = 'state.json'
monitor_running = False
stop_signal = False

# ==================== HELPER FUNCTIONS ====================
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': ''
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def is_trading_time():
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def get_dhan_balance():
    """Fetch balance from Dhan API - CORRECTED ENDPOINT"""
    try:
        # ✅ योग्य endpoint: /positions (किंवा /funds/details Dhan docs प्रमाणे)
        response = requests.get(
            f'{BASE_URL}/positions',
            headers=HEADERS,
            timeout=10
        )
        print(f"API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"API Response Data: {data}")
            
            # Dhan API response structure adjust करा
            # Common fields: netAvailableMargin, availableMargin, marginAvailable
            if isinstance(data, list) and len(data) > 0:
                # Positions array असल्यास
                return float(data[0].get('netAvailableMargin', 0))
            elif isinstance(data, dict):
                # Direct object असल्यास
                return float(data.get('netAvailableMargin', 
                              data.get('availableMargin', 
                              data.get('marginAvailable', 0))))
        else:
            print(f"API Error: {response.text}")
    except Exception as e:
        print(f"Balance fetch error: {str(e)}")
    return None

def monitor_loop():
    global monitor_running, stop_signal
    
    monitor_running = True
    print("✅ Monitoring started: 20% loss limit, 10 orders/day")
    
    while not stop_signal:
        try:
            state = load_state()
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Daily reset
            if state['date'] != current_date:
                state = {
                    'date': current_date,
                    'morning_balance': None,
                    'max_loss_amount': None,
                    'order_count': 0,
                    'trading_allowed': True,
                    'blocked_reason': ''
                }
                save_state(state)
                print("🔄 New day - counters reset")
            
            # Trading time check
            trading_now = is_trading_time()
            print(f"⏰ Trading time: {trading_now}, Current: {datetime.now().time()}")
            
            if not trading_now:
                if state['trading_allowed']:
                    print("⏰ Trading hours ended - blocking trades")
                    state['trading_allowed'] = False
                    state['blocked_reason'] = 'Trading hours ended'
                    save_state(state)
                time.sleep(60)  # 1 मिनिट
                continue
            
            # Capture morning balance at 9:25 AM
            if state['morning_balance'] is None:
                print("🌅 Attempting to capture morning balance...")
                balance = get_dhan_balance()
                
                if balance is not None:
                    print(f"✅ Balance fetched: ₹{balance:.2f}")
                    state['morning_balance'] = balance
                    state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                    save_state(state)
                    print(f"🌅 Morning balance set: ₹{balance:.2f} | Max loss (20%): ₹{state['max_loss_amount']:.2f}")
                else:
                    print("⏳ Waiting for balance details...")
            
            # If morning balance captured, check for loss
            if state['morning_balance']:
                current_balance = get_dhan_balance()
                
                if current_balance is not None:
                    loss = state['morning_balance'] - current_balance
                    print(f"📊 Current balance: ₹{current_balance:.2f}, Loss: ₹{loss:.2f}")
                    
                    # 20% LOSS LIMIT CHECK
                    if loss >= state['max_loss_amount'] and state['trading_allowed']:
                        print(f"🚨 20% Loss limit hit: ₹{loss:.2f} >= ₹{state['max_loss_amount']:.2f}")
                        state['trading_allowed'] = False
                        state['blocked_reason'] = f'20% Loss limit: ₹{loss:.2f}'
                        save_state(state)
                    
                    # 10 ORDERS/DAY CHECK (simulated - तू manually increment कर)
                    if state['order_count'] >= MAX_ORDERS_PER_DAY and state['trading_allowed']:
                        print(f"🔢 10 Orders limit reached: {state['order_count']}")
                        state['trading_allowed'] = False
                        state['blocked_reason'] = '10 Orders/day limit'
                        save_state(state)
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"❌ Monitor error: {str(e)}")
            time.sleep(30)
    
    monitor_running = False
    print("⏹️ Monitoring stopped")

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    state = load_state()
    return jsonify({
        'app': 'Dhan Risk Manager',
        'status': 'active',
        'version': '2.0',
        'limits': {
            'max_loss_percent': '20%',
            'max_orders_per_day': 10
        },
        'trading_hours': '9:25 AM - 3:00 PM',
        'current_time': datetime.now().strftime('%H:%M:%S'),
        'is_trading_time': is_trading_time(),
        'today': {
            'morning_balance': state['morning_balance'],
            'max_loss_amount': state['max_loss_amount'],
            'order_count': state['order_count'],
            'trading_allowed': state['trading_allowed'],
            'blocked_reason': state['blocked_reason'] or 'None'
        }
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/start')
def start_monitor():
    global stop_signal
    if not monitor_running:
        stop_signal = False
        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        return jsonify({'status': 'monitoring_started'})
    return jsonify({'status': 'already_running'})

@app.route('/stop')
def stop_monitor():
    global stop_signal
    stop_signal = True
    return jsonify({'status': 'monitoring_stopping'})

@app.route('/reset')
def reset_day():
    state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': ''
    }
    save_state(state)
    return jsonify({'status': 'reset_complete'})

@app.route('/increment')
def increment_order():
    """Manually increment order count for testing"""
    state = load_state()
    state['order_count'] += 1
    save_state(state)
    return jsonify({
        'status': 'order_incremented',
        'new_count': state['order_count']
    })

# ==================== START APPLICATION ====================
if __name__ == '__main__':
    # Start monitoring
    stop_signal = False
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    
    # Start server
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Dhan Risk Manager starting...")
    print(f"📊 Limits: 20% loss, 10 orders/day")
    print(f"⏰ Trading: 9:25 AM - 3:00 PM")
    print(f"🌐 Port: {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
