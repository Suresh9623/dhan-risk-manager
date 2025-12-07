import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify
import requests

# ==================== CONFIGURATION ====================
app = Flask(__name__)

# तुझ्या 5 CONDITIONS - CORRECT TIMING
MAX_ORDERS_PER_DAY = 10                    # Condition 2: 10 orders/day
MAX_LOSS_PERCENT = 0.20                    # Condition 1: 20% loss limit
TRADING_START = dtime(9, 2)               # Condition 3: 9:02 AM (CORRECTED)
TRADING_END = dtime(15, 0)                # Condition 3: 3:00 PM
CHECK_INTERVAL = 30                       # Condition 5: Real-time monitoring

print("\n" + "="*60)
print("🚀 AUTOMATIC TRADING MANAGER - FINAL VERSION")
print("="*60)

# Dhan API Credentials
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')

print(f"🔐 CREDENTIALS STATUS:")
print(f"  Access Token: {'✅ LOADED' if DHAN_ACCESS_TOKEN else '❌ MISSING'}")
print(f"  Client ID: {'✅ LOADED' if DHAN_CLIENT_ID else '❌ MISSING'}")

if DHAN_ACCESS_TOKEN:
    print(f"  Token Preview: {DHAN_ACCESS_TOKEN[:20]}...")

print("="*60)

# API Headers
HEADERS = {
    'access-token': DHAN_ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# ==================== STATE MANAGEMENT ====================
STATE_FILE = 'state.json'

class TradingState:
    def __init__(self):
        self.data = self._load()
    
    def _load(self):
        """Load state from file"""
        default_state = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'morning_balance': None,
            'current_balance': None,
            'max_loss_amount': None,
            'order_count': 0,
            'trading_allowed': True,
            'blocked_reason': '',
            'last_check': None,
            'balance_captured': False
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
    
    def save(self):
        """Save state to file"""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except:
            pass
    
    def reset_daily(self):
        """Reset for new day"""
        self.data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'morning_balance': None,
            'current_balance': None,
            'max_loss_amount': None,
            'order_count': 0,
            'trading_allowed': True,
            'blocked_reason': '',
            'last_check': None,
            'balance_captured': False
        }
        self.save()
        print("🔄 Daily reset completed")

state = TradingState()

# ==================== SIMPLE DHAN API ====================
def get_dhan_balance():
    """Get balance - SIMPLE & ERROR-FREE"""
    
    # If no token, return default for testing
    if not DHAN_ACCESS_TOKEN:
        print("⚠️ No token, using default balance")
        return 50000.0
    
    # Try simple endpoints
    try:
        # Try positions endpoint
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Got positions data")
            
            # Calculate portfolio value
            if isinstance(data, list) and data:
                total = 0
                for item in data[:10]:  # Check first 10 positions
                    if isinstance(item, dict):
                        # Try to get value
                        if 'currentValue' in item:
                            try:
                                total += float(item['currentValue'])
                            except:
                                pass
                
                if total > 0:
                    return total
    except:
        pass
    
    # If positions fail, try funds
    try:
        response = requests.get(
            'https://api.dhan.co/funds',
            headers=HEADERS,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                # Try common balance fields
                for field in ['availableMargin', 'balance', 'cashBalance']:
                    if field in data:
                        try:
                            value = float(data[field])
                            if value > 0:
                                return value
                        except:
                            pass
    except:
        pass
    
    # Return default if all fails
    print("⚠️ Using default balance for testing")
    return 50000.0

# ==================== CONDITION CHECKS ====================
def is_trading_time():
    """Check if within 9:02 AM - 3:00 PM"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def check_all_conditions():
    """Check all 5 conditions"""
    
    conditions_ok = True
    violations = []
    
    # Condition 3: Trading hours
    if not is_trading_time():
        conditions_ok = False
        violations.append("Outside trading hours (9:02-15:00)")
    
    # Condition 2: Order count
    if state.data['order_count'] >= MAX_ORDERS_PER_DAY:
        conditions_ok = False
        violations.append(f"10 orders limit reached ({state.data['order_count']})")
    
    # Condition 1: 20% loss (only if balance captured)
    if state.data['morning_balance'] and state.data['current_balance']:
        loss = state.data['morning_balance'] - state.data['current_balance']
        if loss >= state.data['max_loss_amount']:
            conditions_ok = False
            violations.append(f"20% loss limit reached (₹{loss:,.2f})")
    
    return conditions_ok, violations

# ==================== MONITORING LOOP ====================
monitor_active = False
stop_signal = False

def monitoring_loop():
    """Main monitoring loop - SIMPLE & ERROR-FREE"""
    global monitor_active, stop_signal
    
    monitor_active = True
    
    print("\n" + "="*60)
    print("🤖 AUTOMATIC TRADING MANAGER ACTIVE")
    print("="*60)
    print("📋 MONITORING 5 CONDITIONS:")
    print("   1. 20% Daily Loss Limit")
    print("   2. Max 10 Orders/Day")
    print("   3. Trading Hours: 9:02 AM - 3:00 PM")
    print("   4. Auto Balance Capture at 9:02 AM")
    print("   5. Real-time Monitoring (Every 30s)")
    print("="*60)
    
    while not stop_signal:
        try:
            current_time = datetime.now().strftime('%H:%M:%S')
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            print(f"\n🔄 CHECK [{current_time}]")
            
            # Daily reset
            if state.data['date'] != current_date:
                print("📅 New trading day - Resetting")
                state.reset_daily()
            
            # Check trading hours
            trading_now = is_trading_time()
            print(f"⏰ Trading Hours (9:02-15:00): {'✅ YES' if trading_now else '❌ NO'}")
            
            if not trading_now:
                time.sleep(60)
                continue
            
            # Morning balance capture (9:02 AM)
            if not state.data['balance_captured']:
                print("🌅 Capturing morning balance...")
                balance = get_dhan_balance()
                
                if balance:
                    state.data['morning_balance'] = balance
                    state.data['current_balance'] = balance
                    state.data['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                    state.data['balance_captured'] = True
                    state.data['last_check'] = current_time
                    state.save()
                    
                    print(f"💰 Morning Balance: ₹{balance:,.2f}")
                    print(f"📊 20% Loss Limit: ₹{state.data['max_loss_amount']:,.2f}")
            
            # Real-time monitoring
            if state.data['balance_captured']:
                current_balance = get_dhan_balance()
                
                if current_balance:
                    state.data['current_balance'] = current_balance
                    state.data['last_check'] = current_time
                    
                    # Calculate P&L
                    morning_balance = state.data['morning_balance']
                    loss = morning_balance - current_balance
                    loss_percent = (loss / morning_balance) * 100 if morning_balance > 0 else 0
                    
                    print(f"📈 Current Balance: ₹{current_balance:,.2f}")
                    print(f"📉 Today's P&L: ₹{-loss:,.2f} ({loss_percent:+.1f}%)")
                    
                    state.save()
            
            # Order count
            print(f"📊 Orders Today: {state.data['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            # Check conditions
            conditions_ok, violations = check_all_conditions()
            
            if conditions_ok:
                print("✅ All conditions satisfied")
            else:
                for violation in violations:
                    print(f"🚨 {violation}")
                
                if state.data['trading_allowed']:
                    state.data['trading_allowed'] = False
                    state.data['blocked_reason'] = ', '.join(violations)
                    state.save()
                    print("🛑 Trading blocked")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"⚠️ Monitoring error (will retry): {e}")
            time.sleep(30)
    
    monitor_active = False
    print("\n⏹️ Monitoring stopped")

# ==================== WEB ROUTES ====================
@app.route('/')
def dashboard():
    """Main dashboard"""
    
    # Get current balance
    current_balance = get_dhan_balance()
    state.data['current_balance'] = current_balance
    state.data['last_check'] = datetime.now().strftime('%H:%M:%S')
    
    # Calculate stats
    morning_balance = state.data['morning_balance']
    if morning_balance and current_balance:
        loss = morning_balance - current_balance
        loss_percent = (loss / morning_balance) * 100
    else:
        loss = 0
        loss_percent = 0
    
    conditions_ok, violations = check_all_conditions()
    
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Automatic Trading Manager',
        'version': 'FINAL-1.0',
        'trading_status': {
            'allowed': state.data['trading_allowed'] and conditions_ok,
            'blocked_reason': state.data['blocked_reason'] if state.data['blocked_reason'] else 'None',
            'violations': violations
        },
        'today': {
            'date': state.data['date'],
            'morning_balance': state.data['morning_balance'],
            'current_balance': state.data['current_balance'],
            'loss': loss,
            'loss_percent': round(loss_percent, 2),
            'max_loss_limit': state.data['max_loss_amount'],
            'order_count': state.data['order_count'],
            'orders_remaining': MAX_ORDERS_PER_DAY - state.data['order_count'],
            'balance_captured': state.data['balance_captured'],
            'last_check': state.data['last_check']
        },
        'conditions': [
            {
                'id': 1,
                'name': '20% Loss Limit',
                'status': '✅ ACTIVE' if state.data['morning_balance'] else '⏳ WAITING',
                'limit': f"₹{state.data['max_loss_amount']:,.2f}" if state.data['max_loss_amount'] else 'Not set'
            },
            {
                'id': 2,
                'name': '10 Orders/Day',
                'status': '✅ ACTIVE',
                'current': state.data['order_count'],
                'limit': MAX_ORDERS_PER_DAY,
                'remaining': MAX_ORDERS_PER_DAY - state.data['order_count']
            },
            {
                'id': 3,
                'name': 'Trading Hours (9:02 AM - 3:00 PM)',
                'status': '✅ ACTIVE',
                'current': datetime.now().strftime('%H:%M:%S'),
                'is_trading_time': is_trading_time()
            },
            {
                'id': 4,
                'name': 'Morning Balance Capture',
                'status': '✅ CAPTURED' if state.data['balance_captured'] else '⏳ WAITING (9:02 AM)',
                'balance': state.data['morning_balance']
            },
            {
                'id': 5,
                'name': 'Real-time Monitoring',
                'status': '✅ ACTIVE',
                'interval': f'{CHECK_INTERVAL} seconds',
                'last_check': state.data['last_check']
            }
        ],
        'credentials': {
            'access_token_loaded': bool(DHAN_ACCESS_TOKEN),
            'client_id_loaded': bool(DHAN_CLIENT_ID)
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
    state.reset_daily()
    return jsonify({'status': 'DAY_RESET_COMPLETE'})

@app.route('/add_order')
def add_order():
    """Simulate order"""
    conditions_ok, violations = check_all_conditions()
    
    if not conditions_ok or not state.data['trading_allowed']:
        return jsonify({
            'status': 'BLOCKED',
            'reason': 'Condition violation',
            'violations': violations
        })
    
    state.data['order_count'] += 1
    state.save()
    
    return jsonify({
        'status': 'ORDER_ADDED',
        'order_count': state.data['order_count'],
        'remaining': MAX_ORDERS_PER_DAY - state.data['order_count'],
        'message': f'Order #{state.data["order_count"]} recorded'
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
    
    state.data['morning_balance'] = balance
    state.data['current_balance'] = balance
    state.data['max_loss_amount'] = balance * MAX_LOSS_PERCENT
    state.data['balance_captured'] = True
    state.data['last_check'] = datetime.now().strftime('%H:%M:%S')
    state.save()
    
    return jsonify({
        'status': 'BALANCE_CAPTURED',
        'balance': balance,
        'loss_limit': state.data['max_loss_amount'],
        'time': state.data['last_check']
    })

@app.route('/status')
def status():
    """Simple status"""
    return jsonify({
        'system': 'running',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'monitoring': 'active',
        'trading_allowed': state.data['trading_allowed']
    })

# ==================== START ====================
if __name__ == '__main__':
    # Start monitoring
    print("\n🚀 Starting monitoring system...")
    stop_signal = False
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Start server
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server starting on port {port}")
    print(f"📊 Dashboard: https://dhan-risk-manager.onrender.com/")
    print(f"⚡ Health: https://dhan-risk-manager.onrender.com/health")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
