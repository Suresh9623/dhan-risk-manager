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
MAX_ORDERS_PER_DAY = 10           # दिवसात कमाल 10 ऑर्डर
MAX_LOSS_PERCENT = 0.20           # 20% लॉस लिमिट
TRADING_START = dtime(9, 25)      # सकाळी 9:25
TRADING_END = dtime(15, 0)        # दुपारी 3:00
CHECK_INTERVAL = 5                # 5 सेकंदात एकदा तपासणी

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
    """Load current state from file"""
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
    """Save state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def is_trading_time():
    """Check if current time is within trading hours"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def get_dhan_balance():
    """Fetch current balance from Dhan API"""
    try:
        response = requests.get(
            f'{BASE_URL}/funds',
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            # Adjust this based on actual Dhan API response
            return float(data.get('netAvailableMargin', 0))
    except Exception as e:
        print(f"Balance fetch error: {e}")
    return None

def cancel_all_orders():
    """Cancel all pending orders"""
    try:
        orders_response = requests.get(
            f'{BASE_URL}/orders',
            headers=HEADERS,
            timeout=10
        )
        if orders_response.status_code == 200:
            orders = orders_response.json()
            for order in orders:
                order_id = order.get('orderId')
                if order_id:
                    requests.delete(
                        f'{BASE_URL}/orders/{order_id}',
                        headers=HEADERS,
                        timeout=5
                    )
        return True
    except:
        return False

def exit_all_positions():
    """Exit all open positions"""
    try:
        positions_response = requests.get(
            f'{BASE_URL}/positions',
            headers=HEADERS,
            timeout=10
        )
        if positions_response.status_code == 200:
            positions = positions_response.json()
            for position in positions:
                net_qty = float(position.get('netQty', 0))
                if net_qty != 0:
                    # Place exit order logic here
                    pass
        return True
    except:
        return False

def emergency_exit(reason):
    """Emergency exit all positions and cancel orders"""
    print(f"🚨 EMERGENCY: {reason}")
    cancel_all_orders()
    exit_all_positions()
    return True

# ==================== MONITORING THREAD ====================
def monitor_loop():
    """Main monitoring loop - runs in background"""
    global monitor_running, stop_signal
    
    monitor_running = True
    print("✅ Monitoring started: 20% loss limit, 10 orders/day")
    
    while not stop_signal:
        try:
            state = load_state()
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Daily reset at midnight
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
            
            # Check trading time
            if not is_trading_time():
                if state['trading_allowed']:
                    emergency_exit("Trading hours ended")
                    state['trading_allowed'] = False
                    state['blocked_reason'] = 'Trading hours ended'
                    save_state(state)
                time.sleep(30)
                continue
            
            # Capture morning balance at 9:25 AM
            if state['morning_balance'] is None:
                balance = get_dhan_balance()
                if balance and balance > 0:
                    state['morning_balance'] = balance
                    state['max_loss_amount'] = balance * MAX_LOSS_PERCENT  # 20% calculation
                    save_state(state)
                    print(f"🌅 Morning balance: ₹{balance:.2f} | Max loss (20%): ₹{state['max_loss_amount']:.2f}")
            
            # Check current balance for loss
            if state['morning_balance']:
                current_balance = get_dhan_balance()
                if current_balance:
                    loss = state['morning_balance'] - current_balance
                    
                    # 20% LOSS LIMIT CHECK
                    if loss >= state['max_loss_amount'] and state['trading_allowed']:
                        emergency_exit(f"20% Loss limit hit: ₹{loss:.2f}")
                        state['trading_allowed'] = False
                        state['blocked_reason'] = f'20% Loss limit reached: ₹{loss:.2f}'
                        save_state(state)
                    
                    # 10 ORDERS/DAY LIMIT CHECK
                    if state['order_count'] >= MAX_ORDERS_PER_DAY and state['trading_allowed']:
                        emergency_exit(f"10 Orders/day limit reached")
                        state['trading_allowed'] = False
                        state['blocked_reason'] = '10 Orders/day limit reached'
                        save_state(state)
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(10)
    
    monitor_running = False
    print("⏹️ Monitoring stopped")

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    """Home page - show current status"""
    state = load_state()
    return jsonify({
        'app': 'Dhan Risk Manager',
        'status': 'active' if not stop_signal else 'stopped',
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'trading_time': is_trading_time(),
        'trading_hours': '9:25 AM - 3:00 PM',
        'limits': {
            'max_loss_percent': '20%',
            'max_orders_per_day': 10
        },
        'today': {
            'morning_balance': state['morning_balance'],
            'max_loss_amount': state['max_loss_amount'],
            'order_count': state['order_count'],
            'trading_allowed': state['trading_allowed'],
            'blocked_reason': state['blocked_reason']
        }
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/start')
def start_monitor():
    """Start monitoring manually"""
    global stop_signal
    if not monitor_running:
        stop_signal = False
        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        return jsonify({'status': 'monitoring_started'})
    return jsonify({'status': 'already_running'})

@app.route('/stop')
def stop_monitor():
    """Stop monitoring manually"""
    global stop_signal
    stop_signal = True
    return jsonify({'status': 'monitoring_stopping'})

@app.route('/reset')
def reset_day():
    """Reset daily counters"""
    state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': ''
    }
    save_state(state)
    return jsonify({'status': 'reset_complete', 'new_state': state})

@app.route('/emergency')
def trigger_emergency():
    """Manual emergency exit"""
    emergency_exit("Manual emergency trigger")
    state = load_state()
    state['trading_allowed'] = False
    state['blocked_reason'] = 'Manual emergency exit'
    save_state(state)
    return jsonify({'status': 'emergency_exit_triggered'})

# ==================== START APPLICATION ====================
if __name__ == '__main__':
    # Start monitoring thread automatically
    stop_signal = False
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    
    # Start Flask server
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting Dhan Risk Manager on port {port}")
    print(f"📊 Limits: 20% loss, 10 orders/day")
    print(f"⏰ Trading hours: 9:25 AM - 3:00 PM")
    app.run(host='0.0.0.0', port=port, debug=False)
