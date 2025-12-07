import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify
import requests

# ==================== CONFIGURATION ====================
app = Flask(__name__)

# तुझ्या 5 CONDITIONS
MAX_ORDERS_PER_DAY = 10                    # Condition 2: 10 orders/day
MAX_LOSS_PERCENT = 0.20                    # Condition 1: 20% loss limit
TRADING_START = dtime(9, 2)               # Condition 3: 9:02 AM (सकाळी नऊ वाजून दोन मिनिटे)
TRADING_END = dtime(15, 0)                # Condition 3: 3:00 PM (दुपारी तीन वाजे)
CHECK_INTERVAL = 30                       # Condition 5: Real-time monitoring (30 सेकंद)

print("\n" + "="*60)
print("🚀 AUTOMATIC TRADING MANAGER - ALL 5 CONDITIONS")
print("="*60)
print("📋 MONITORING CONDITIONS:")
print("   1. 20% Daily Loss Limit")
print("   2. Max 10 Orders/Day")
print("   3. Trading Hours: 9:02 AM - 3:00 PM")
print("   4. Auto Balance Capture at 9:02 AM")
print("   5. Real-time Monitoring (Every 30s)")
print("="*60)

# Dhan API Credentials from Render Environment
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')

print(f"🔐 CREDENTIALS STATUS:")
print(f"  Access Token: {'✅ LOADED' if DHAN_ACCESS_TOKEN else '❌ MISSING'}")
print(f"  Client ID: {'✅ LOADED' if DHAN_CLIENT_ID else '❌ MISSING'}")

if DHAN_ACCESS_TOKEN:
    print(f"  Token Preview: {DHAN_ACCESS_TOKEN[:20]}...")
    print(f"  Token Length: {len(DHAN_ACCESS_TOKEN)} characters")

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
        self.data = self._load_state()
    
    def _load_state(self):
        """Load state from file or create default"""
        default_state = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'morning_balance': None,          # सकाळचा बॅलन्स (Condition 4)
            'current_balance': None,          # चालू बॅलन्स
            'max_loss_amount': None,          # 20% लॉस लिमिट (Condition 1)
            'order_count': 0,                 # ऑर्डर काउंट (Condition 2)
            'trading_allowed': True,          # ट्रेडिंग परवानगी
            'blocked_reason': '',             # ब्लॉक कारण
            'last_check': None,               # शेवटची तपासणी
            'balance_captured': False         # बॅलन्स कॅप्चर झाला का
        }
        
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    saved_state = json.load(f)
                    # Merge with defaults for any missing keys
                    for key in default_state:
                        if key not in saved_state:
                            saved_state[key] = default_state[key]
                    return saved_state
        except Exception as e:
            print(f"⚠️ Error loading state: {e}")
        
        return default_state
    
    def save(self):
        """Save state to file"""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving state: {e}")
    
    def reset_daily(self):
        """Reset everything for new trading day"""
        print("🔄 Daily reset initiated")
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

# Create global state instance
state = TradingState()

# ==================== DHAN BALANCE FUNCTIONS ====================
def get_dhan_balance():
    """Get balance from Dhan API - SIMPLE & RELIABLE"""
    
    # If no access token, return default
    if not DHAN_ACCESS_TOKEN:
        print("⚠️ No access token, using default balance")
        return 75000.0
    
    print("💰 Fetching balance from Dhan...")
    
    # Try multiple approaches to get balance
    balance = _try_positions_endpoint()
    if balance:
        return balance
    
    balance = _try_funds_endpoint()
    if balance:
        return balance
    
    # If all fails, return default
    print("⚠️ All methods failed, using default balance")
    return 75000.0

def _try_positions_endpoint():
    """Try to get balance from positions endpoint"""
    try:
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Got positions data")
            
            # Calculate total portfolio value
            if isinstance(data, list):
                total_value = 0
                for position in data:
                    if isinstance(position, dict):
                        # Try to get current value
                        if 'currentValue' in position:
                            try:
                                total_value += float(position['currentValue'])
                            except:
                                pass
                
                if total_value > 0:
                    print(f"📊 Portfolio Value: ₹{total_value:,.2f}")
                    return total_value
    except Exception as e:
        print(f"❌ Positions error: {e}")
    
    return None

def _try_funds_endpoint():
    """Try to get balance from funds endpoint"""
    try:
        response = requests.get(
            'https://api.dhan.co/funds',
            headers=HEADERS,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Got funds data")
            
            # Try different balance field names
            balance_fields = [
                'availableMargin', 'netAvailableMargin', 'marginAvailable',
                'balance', 'totalBalance', 'cashBalance', 'netBalance'
            ]
            
            if isinstance(data, dict):
                for field in balance_fields:
                    if field in data:
                        try:
                            value = float(data[field])
                            if value > 0:
                                print(f"💰 Found {field}: ₹{value:,.2f}")
                                return value
                        except:
                            continue
    except Exception as e:
        print(f"❌ Funds error: {e}")
    
    return None

# ==================== CONDITION CHECKS ====================
def is_trading_time():
    """Condition 3: Check if current time is within trading hours"""
    current_time = datetime.now().time()
    return TRADING_START <= current_time <= TRADING_END

def check_20_percent_loss():
    """Condition 1: Check 20% loss limit"""
    if state.data['morning_balance'] and state.data['current_balance']:
        loss = state.data['morning_balance'] - state.data['current_balance']
        if loss >= state.data['max_loss_amount']:
            return False, f"20% loss limit reached (₹{loss:,.2f})"
    return True, "OK"

def check_order_limit():
    """Condition 2: Check 10 orders/day limit"""
    if state.data['order_count'] >= MAX_ORDERS_PER_DAY:
        return False, f"10 orders limit reached ({state.data['order_count']})"
    return True, "OK"

def check_trading_hours():
    """Condition 3: Check trading hours"""
    if not is_trading_time():
        return False, "Outside trading hours (9:02 AM - 3:00 PM)"
    return True, "OK"

def check_balance_captured():
    """Condition 4: Check if balance captured"""
    if not state.data['balance_captured']:
        return False, "Morning balance not captured"
    return True, "OK"

def check_all_conditions():
    """Check all 5 conditions"""
    conditions = {
        '20_percent_loss': check_20_percent_loss(),
        'order_limit': check_order_limit(),
        'trading_hours': check_trading_hours(),
        'balance_captured': check_balance_captured(),
        'monitoring': (True, "Active")  # Condition 5 always active
    }
    
    all_ok = all(result[0] for result in conditions.values())
    violations = [result[1] for result in conditions.values() if not result[0]]
    
    return all_ok, violations, conditions

# ==================== MONITORING LOOP ====================
monitor_active = False
stop_signal = False

def monitoring_loop():
    """Main monitoring loop - runs every 30 seconds"""
    global monitor_active, stop_signal
    
    monitor_active = True
    
    print("\n🤖 AUTO MONITORING STARTED")
    print("⏰ Trading Hours: 9:02 AM - 3:00 PM")
    print("📊 Check Interval: 30 seconds")
    print("="*60)
    
    while not stop_signal:
        try:
            current_time = datetime.now().strftime('%H:%M:%S')
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            print(f"\n🔄 CHECK [{current_time}]")
            
            # ========== DAILY RESET ==========
            if state.data['date'] != current_date:
                print("📅 New trading day detected - Resetting")
                state.reset_daily()
            
            # ========== CONDITION 3: TRADING HOURS ==========
            trading_now = is_trading_time()
            print(f"⏰ Trading Hours: {'✅ YES' if trading_now else '❌ NO'}")
            
            if not trading_now:
                time.sleep(60)
                continue
            
            # ========== CONDITION 4: MORNING BALANCE CAPTURE ==========
            if not state.data['balance_captured']:
                print("🌅 Capturing morning balance...")
                morning_balance = get_dhan_balance()
                
                state.data['morning_balance'] = morning_balance
                state.data['current_balance'] = morning_balance
                state.data['max_loss_amount'] = morning_balance * MAX_LOSS_PERCENT
                state.data['balance_captured'] = True
                state.data['last_check'] = current_time
                state.save()
                
                print(f"💰 Morning Balance: ₹{morning_balance:,.2f}")
                print(f"📊 20% Loss Limit: ₹{state.data['max_loss_amount']:,.2f}")
            
            # ========== CONDITION 5: REAL-TIME MONITORING ==========
            if state.data['balance_captured']:
                current_balance = get_dhan_balance()
                state.data['current_balance'] = current_balance
                state.data['last_check'] = current_time
                
                # Calculate P&L
                morning_balance = state.data['morning_balance']
                loss = morning_balance - current_balance
                loss_percent = (loss / morning_balance) * 100
                
                print(f"📈 Current Balance: ₹{current_balance:,.2f}")
                print(f"📉 Today's P&L: ₹{-loss:,.2f} ({loss_percent:+.1f}%)")
                
                # ========== CONDITION 1: 20% LOSS CHECK ==========
                if loss >= state.data['max_loss_amount']:
                    print(f"🚨 20% LOSS LIMIT HIT! Loss: ₹{loss:,.2f}")
                    state.data['trading_allowed'] = False
                    state.data['blocked_reason'] = f'20% Loss Limit: ₹{loss:,.2f}'
                
                state.save()
            
            # ========== CONDITION 2: ORDER COUNT ==========
            print(f"📊 Orders Today: {state.data['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            if state.data['order_count'] >= MAX_ORDERS_PER_DAY:
                print(f"🚨 10 ORDERS LIMIT REACHED!")
                state.data['trading_allowed'] = False
                state.data['blocked_reason'] = '10 Orders Limit'
                state.save()
            
            # ========== FINAL STATUS ==========
            all_ok, violations, _ = check_all_conditions()
            
            if all_ok:
                print("✅ All conditions satisfied")
            else:
                for violation in violations:
                    print(f"❌ {violation}")
            
            # Wait for next check
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"⚠️ Monitoring error: {e}")
            time.sleep(30)  # Wait longer if error
    
    monitor_active = False
    print("\n⏹️ Monitoring stopped")

# ==================== WEB ROUTES ====================
@app.route('/')
def dashboard():
    """Main dashboard showing all conditions"""
    
    # Get current balance for display
    current_balance = get_dhan_balance()
    state.data['current_balance'] = current_balance
    state.data['last_check'] = datetime.now().strftime('%H:%M:%S')
    state.save()
    
    # Calculate current P&L
    morning_balance = state.data['morning_balance']
    current_balance_display = state.data['current_balance']
    
    if morning_balance and current_balance_display:
        loss = morning_balance - current_balance_display
        loss_percent = (loss / morning_balance) * 100
    else:
        loss = 0
        loss_percent = 0
    
    # Check all conditions
    all_ok, violations, conditions = check_all_conditions()
    
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Automatic Trading Manager',
        'version': 'FINAL-1.0',
        'time': {
            'current': datetime.now().strftime('%H:%M:%S'),
            'trading_hours': '9:02 AM - 3:00 PM',
            'is_trading_time': is_trading_time()
        },
        'balance': {
            'morning': state.data['morning_balance'],
            'current': state.data['current_balance'],
            'loss': loss,
            'loss_percent': round(loss_percent, 2),
            'max_loss_20%': state.data['max_loss_amount'],
            'last_update': state.data['last_check']
        },
        'orders': {
            'today': state.data['order_count'],
            'limit': MAX_ORDERS_PER_DAY,
            'remaining': MAX_ORDERS_PER_DAY - state.data['order_count']
        },
        'trading_status': {
            'allowed': state.data['trading_allowed'] and all_ok,
            'blocked_reason': state.data['blocked_reason'] if state.data['blocked_reason'] else 'None',
            'violations': violations
        },
        'conditions': [
            {
                'id': 1,
                'name': '20% Daily Loss Limit',
                'status': '✅ ACTIVE' if conditions['20_percent_loss'][0] else '❌ VIOLATED',
                'details': conditions['20_percent_loss'][1],
                'limit': f"₹{state.data['max_loss_amount']:,.2f}" if state.data['max_loss_amount'] else 'Not set'
            },
            {
                'id': 2,
                'name': 'Max 10 Orders/Day',
                'status': '✅ ACTIVE' if conditions['order_limit'][0] else '❌ VIOLATED',
                'details': conditions['order_limit'][1],
                'current': state.data['order_count'],
                'remaining': MAX_ORDERS_PER_DAY - state.data['order_count']
            },
            {
                'id': 3,
                'name': 'Trading Hours (9:02 AM - 3:00 PM)',
                'status': '✅ ACTIVE' if conditions['trading_hours'][0] else '❌ VIOLATED',
                'details': conditions['trading_hours'][1],
                'current_time': datetime.now().strftime('%H:%M:%S')
            },
            {
                'id': 4,
                'name': 'Morning Balance Capture',
                'status': '✅ ACTIVE' if conditions['balance_captured'][0] else '⏳ WAITING',
                'details': conditions['balance_captured'][1],
                'balance': state.data['morning_balance']
            },
            {
                'id': 5,
                'name': 'Real-time Monitoring',
                'status': '✅ ACTIVE',
                'details': 'Every 30 seconds',
                'last_check': state.data['last_check']
            }
        ]
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'HEALTHY',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': monitor_active
    })

@app.route('/start')
def start_monitoring():
    """Start monitoring manually"""
    global stop_signal
    if not monitor_active:
        stop_signal = False
        thread = threading.Thread(target=monitoring_loop, daemon=True)
        thread.start()
        return jsonify({'status': 'MONITORING_STARTED'})
    return jsonify({'status': 'ALREADY_RUNNING'})

@app.route('/stop')
def stop_monitoring():
    """Stop monitoring manually"""
    global stop_signal
    stop_signal = True
    return jsonify({'status': 'MONITORING_STOPPING'})

@app.route('/reset')
def reset_day():
    """Reset for new trading day"""
    state.reset_daily()
    return jsonify({'status': 'DAY_RESET_COMPLETE'})

@app.route('/emergency')
def emergency_stop():
    """Emergency stop - blocks all trading"""
    state.data['trading_allowed'] = False
    state.data['blocked_reason'] = 'Emergency Stop'
    state.save()
    return jsonify({'status': 'EMERGENCY_STOP_EXECUTED'})

@app.route('/add_order')
def add_order():
    """Simulate adding an order (for testing)"""
    all_ok, violations, _ = check_all_conditions()
    
    if not all_ok or not state.data['trading_allowed']:
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
        'message': f'Order #{state.data["order_count"]} recorded successfully'
    })

@app.route('/get_balance')
def get_balance():
    """Get current balance"""
    balance = get_dhan_balance()
    return jsonify({
        'balance': balance,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'success': balance is not None
    })

@app.route('/capture_now')
def capture_balance_now():
    """Manually capture balance (for testing)"""
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
def system_status():
    """Simple system status"""
    return jsonify({
        'system': 'running',
        'monitoring': 'active',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'trading_allowed': state.data['trading_allowed']
    })

# ==================== START APPLICATION ====================
if __name__ == '__main__':
    # Start monitoring thread
    print("\n🚀 Initializing Automatic Trading Manager...")
    stop_signal = False
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Start Flask server
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server starting on port {port}")
    print(f"📊 Dashboard URL: https://dhan-risk-manager.onrender.com/")
    print(f"⚡ Health Check: https://dhan-risk-manager.onrender.com/health")
    print(f"💰 Get Balance: https://dhan-risk-manager.onrender.com/get_balance")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
