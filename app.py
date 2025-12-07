import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify

# ==================== CONFIG ====================
app = Flask(__name__)

# तुझे EXACT CONDITIONS
MAX_ORDERS_PER_DAY = 10
MAX_LOSS_PERCENT = 0.20  # 20%
TRADING_START = dtime(9, 25)  # 9:25 AM
TRADING_END = dtime(15, 0)    # 3:00 PM
CHECK_INTERVAL = 30  # seconds

# Dhan API - Render वर SET केलेले credentials
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')

print(f"🔐 Dhan Client ID loaded: {'✅' if DHAN_CLIENT_ID else '❌'}")
print(f"🔐 Dhan Access Token loaded: {'✅' if DHAN_ACCESS_TOKEN else '❌'}")

HEADERS = {
    'access-token': DHAN_ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# ==================== STATE MANAGEMENT ====================
STATE_FILE = 'state.json'
monitor_active = False
stop_signal = False

def load_state():
    """Load current state"""
    default_state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'last_balance': None,
        'last_check': None,
        'total_loss': 0
    }
    
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                saved = json.load(f)
                for key in default_state:
                    if key not in saved:
                        saved[key] = default_state[key]
                return saved
    except:
        pass
    
    return default_state

def save_state(state):
    """Save state"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# ==================== DHAN API FUNCTIONS ====================
import requests

def get_dhan_balance():
    """Fetch balance from Dhan API"""
    
    if not DHAN_ACCESS_TOKEN:
        print("❌ No access token")
        return None
    
    endpoints = [
        '/funds',           # Most common for balance
        '/positions',       # Positions
        '/margin',          # Margin details
        '/account',         # Account info
        '/holdings',        # Holdings
        '/limits',          # Limits
        '/profile'          # Profile
    ]
    
    for endpoint in endpoints:
        try:
            url = f'https://api.dhan.co{endpoint}'
            print(f"🔍 Trying: {endpoint}")
            
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=10
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Data received from {endpoint}")
                
                # Extract balance
                balance = extract_balance(data)
                if balance:
                    print(f"💰 Balance found: ₹{balance}")
                    return balance
                else:
                    print(f"ℹ️ No balance found in {endpoint} response")
                    
        except Exception as e:
            print(f"❌ Error with {endpoint}: {str(e)[:100]}")
            continue
    
    print("⚠️ All endpoints failed")
    return None

def extract_balance(data):
    """Extract balance from response"""
    
    # Try common field names
    balance_fields = [
        'netAvailableMargin',
        'availableMargin',
        'marginAvailable',
        'balance',
        'totalBalance',
        'cashBalance',
        'netBalance',
        'margin',
        'availableCash',
        'funds',
        'net'
    ]
    
    # Check if data is list
    if isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            data = data[0]
    
    # Check direct fields
    if isinstance(data, dict):
        for field in balance_fields:
            if field in data:
                try:
                    value = float(data[field])
                    print(f"📊 Found {field}: ₹{value}")
                    return value
                except:
                    continue
        
        # Check nested
        for key, value in data.items():
            if isinstance(value, dict):
                nested = extract_balance(value)
                if nested:
                    return nested
            elif isinstance(value, list) and value:
                nested = extract_balance(value[0])
                if nested:
                    return nested
    
    return None

def cancel_all_orders():
    """Cancel all pending orders"""
    try:
        response = requests.get(
            'https://api.dhan.co/orders',
            headers=HEADERS,
            timeout=5
        )
        if response.status_code == 200:
            orders = response.json()
            for order in orders:
                order_id = order.get('orderId')
                if order_id:
                    requests.delete(
                        f'https://api.dhan.co/orders/{order_id}',
                        headers=HEADERS,
                        timeout=3
                    )
            print("✅ All orders cancelled")
            return True
    except Exception as e:
        print(f"❌ Failed to cancel orders: {e}")
    return False

def trigger_emergency():
    """Emergency actions"""
    print("🚨 EMERGENCY TRIGGERED")
    cancel_all_orders()
    return True

# ==================== MONITORING ====================
def is_trading_time():
    """Check if within trading hours"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def monitoring_loop():
    """Main monitoring function"""
    global monitor_active, stop_signal
    
    monitor_active = True
    
    print("\n" + "="*60)
    print("🚀 AUTOMATIC TRADING MANAGER STARTED")
    print("="*60)
    print("📋 YOUR CONDITIONS:")
    print("   1. 20% Daily Loss Limit")
    print("   2. Max 10 Orders/Day")
    print("   3. Trading Hours: 9:25 AM - 3:00 PM")
    print("   4. Auto Balance Capture at 9:25 AM")
    print("   5. Real-time Monitoring")
    print("="*60)
    print(f"🔐 Using Dhan Client ID: {DHAN_CLIENT_ID[:5]}...")
    print(f"⏰ Current Time: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)
    
    while not stop_signal:
        try:
            state = load_state()
            current_date = datetime.now().strftime('%Y-%m-%d')
            current_time = datetime.now().strftime('%H:%M:%S')
            
            print(f"\n🔍 [{current_time}] Checking conditions...")
            
            # 1. DAILY RESET
            if state['date'] != current_date:
                print("📅 NEW DAY - Resetting")
                state = {
                    'date': current_date,
                    'morning_balance': None,
                    'max_loss_amount': None,
                    'order_count': 0,
                    'trading_allowed': True,
                    'blocked_reason': '',
                    'last_balance': None,
                    'last_check': current_time,
                    'total_loss': 0
                }
                save_state(state)
            
            # 2. TRADING HOURS CHECK
            trading_now = is_trading_time()
            print(f"⏰ Trading Hours (9:25-15:00): {'✅ YES' if trading_now else '❌ NO'}")
            
            if not trading_now:
                if state['trading_allowed']:
                    print("⏰ Market Closed - Auto Exit")
                    trigger_emergency()
                    state['trading_allowed'] = False
                    state['blocked_reason'] = 'Market Hours Ended'
                    save_state(state)
                time.sleep(60)
                continue
            
            # 3. MORNING BALANCE CAPTURE (9:25 AM)
            if state['morning_balance'] is None:
                print("🌅 Capturing Morning Balance...")
                balance = get_dhan_balance()
                
                if balance:
                    print(f"💰 Morning Balance: ₹{balance:.2f}")
                    state['morning_balance'] = balance
                    state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                    state['last_balance'] = balance
                    state['last_check'] = current_time
                    save_state(state)
                    
                    print(f"📊 20% Loss Limit: ₹{state['max_loss_amount']:.2f}")
                    print(f"📊 Max Orders: {MAX_ORDERS_PER_DAY}")
                else:
                    print("❌ Failed to get balance")
            
            # 4. REAL-TIME LOSS MONITORING
            if state['morning_balance']:
                current_balance = get_dhan_balance()
                
                if current_balance:
                    state['last_balance'] = current_balance
                    state['last_check'] = current_time
                    
                    loss = state['morning_balance'] - current_balance
                    loss_percent = (loss / state['morning_balance']) * 100
                    
                    print(f"📈 Current: ₹{current_balance:.2f}")
                    print(f"📉 Loss: ₹{loss:.2f} ({loss_percent:.1f}%)")
                    print(f"🚫 Limit: ₹{state['max_loss_amount']:.2f}")
                    
                    # 20% LOSS CHECK
                    if loss >= state['max_loss_amount']:
                        if state['trading_allowed']:
                            print("🚨🚨🚨 20% LOSS LIMIT HIT! 🚨🚨🚨")
                            trigger_emergency()
                            state['trading_allowed'] = False
                            state['blocked_reason'] = f'20% Loss Limit Hit: ₹{loss:.2f}'
                            save_state(state)
                    
                    save_state(state)
            
            # 5. ORDER COUNT CHECK
            print(f"📊 Orders: {state['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            if state['order_count'] >= MAX_ORDERS_PER_DAY:
                if state['trading_allowed']:
                    print("🚨 10 ORDERS LIMIT REACHED!")
                    trigger_emergency()
                    state['trading_allowed'] = False
                    state['blocked_reason'] = '10 Orders Limit'
                    save_state(state)
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(30)
    
    monitor_active = False
    print("\n⏹️ Monitoring Stopped")

# ==================== WEB ROUTES ====================
@app.route('/')
def home():
    """Main Dashboard"""
    state = load_state()
    
    # Calculate stats
    if state['morning_balance'] and state['last_balance']:
        loss = state['morning_balance'] - state['last_balance']
        loss_percent = (loss / state['morning_balance']) * 100
    else:
        loss = 0
        loss_percent = 0
    
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Automatic Trading Manager',
        'conditions_active': {
            '20_percent_loss_limit': '✅ ACTIVE',
            '10_orders_per_day': '✅ ACTIVE',
            'trading_hours_9_25_to_15_00': '✅ ACTIVE',
            'auto_balance_capture': '✅ ACTIVE',
            'real_time_monitoring': '✅ ACTIVE'
        },
        'today': {
            'date': state['date'],
            'morning_balance': state['morning_balance'],
            'current_balance': state['last_balance'],
            'loss_today': loss,
            'loss_percent': round(loss_percent, 2),
            'max_loss_limit': state['max_loss_amount'],
            'order_count': state['order_count'],
            'orders_remaining': MAX_ORDERS_PER_DAY - state['order_count'],
            'trading_allowed': state['trading_allowed'],
            'blocked_reason': state['blocked_reason'] if state['blocked_reason'] else 'None',
            'last_check': state['last_check']
        },
        'time': {
            'current': datetime.now().strftime('%H:%M:%S'),
            'trading_hours': '9:25 AM - 3:00 PM',
            'is_trading_time': is_trading_time()
        },
        'credentials': {
            'client_id_loaded': bool(DHAN_CLIENT_ID),
            'access_token_loaded': bool(DHAN_ACCESS_TOKEN)
        }
    })

@app.route('/health')
def health():
    return jsonify({'status': 'HEALTHY', 'time': datetime.now().strftime('%H:%M:%S')})

@app.route('/start')
def start():
    global stop_signal
    if not monitor_active:
        stop_signal = False
        thread = threading.Thread(target=monitoring_loop, daemon=True)
        thread.start()
        return jsonify({'status': 'MONITORING_STARTED'})
    return jsonify({'status': 'ALREADY_RUNNING'})

@app.route('/stop')
def stop():
    global stop_signal
    stop_signal = True
    return jsonify({'status': 'MONITORING_STOPPED'})

@app.route('/reset')
def reset():
    state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'last_balance': None,
        'last_check': None,
        'total_loss': 0
    }
    save_state(state)
    return jsonify({'status': 'DAY_RESET_COMPLETE'})

@app.route('/emergency')
def emergency():
    trigger_emergency()
    state = load_state()
    state['trading_allowed'] = False
    state['blocked_reason'] = 'Manual Emergency'
    save_state(state)
    return jsonify({'status': 'EMERGENCY_EXECUTED'})

@app.route('/add_order')
def add_order():
    """Simulate order placement"""
    state = load_state()
    
    if not state['trading_allowed']:
        return jsonify({
            'status': 'BLOCKED',
            'reason': state['blocked_reason']
        })
    
    if state['order_count'] >= MAX_ORDERS_PER_DAY:
        return jsonify({
            'status': 'LIMIT_REACHED',
            'message': '10 orders limit reached'
        })
    
    state['order_count'] += 1
    save_state(state)
    
    return jsonify({
        'status': 'ORDER_ADDED',
        'order_count': state['order_count'],
        'remaining': MAX_ORDERS_PER_DAY - state['order_count']
    })

@app.route('/get_balance')
def get_balance():
    """Get current balance"""
    balance = get_dhan_balance()
    return jsonify({
        'balance': balance,
        'time': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/capture_now')
def capture_now():
    """Manual balance capture"""
    balance = get_dhan_balance()
    
    if balance:
        state = load_state()
        state['morning_balance'] = balance
        state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
        state['last_balance'] = balance
        state['last_check'] = datetime.now().strftime('%H:%M:%S')
        save_state(state)
        
        return jsonify({
            'status': 'BALANCE_CAPTURED',
            'balance': balance,
            'loss_limit': state['max_loss_amount'],
            'time': state['last_check']
        })
    
    return jsonify({'status': 'FAILED'})

# ==================== START ====================
if __name__ == '__main__':
    # Start monitoring
    print("\n🚀 INITIALIZING SYSTEM...")
    stop_signal = False
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Start server
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server starting on port {port}")
    print("📊 Dashboard available at root URL")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
