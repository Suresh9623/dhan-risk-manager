import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request
import requests

# ==================== CONFIGURATION ====================
app = Flask(__name__)

# तुझ्या 5 CONDITIONS
MAX_ORDERS_PER_DAY = 10
MAX_LOSS_PERCENT = 0.20  # 20%
TRADING_START = dtime(9, 25)  # 9:25 AM
TRADING_END = dtime(15, 0)    # 3:00 PM
CHECK_INTERVAL = 30  # seconds

# ==================== CREDENTIALS ====================
print("\n" + "="*60)
print("🚀 AUTOMATIC TRADING MANAGER STARTING...")
print("="*60)

# Get credentials from Render environment
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')

print(f"🔐 Credentials Status:")
print(f"  Access Token: {'✅ LOADED' if DHAN_ACCESS_TOKEN else '❌ MISSING'}")
print(f"  Client ID: {'✅ LOADED' if DHAN_CLIENT_ID else '❌ MISSING'}")

if DHAN_ACCESS_TOKEN:
    print(f"  Token Preview: {DHAN_ACCESS_TOKEN[:30]}...")
    print(f"  Token Length: {len(DHAN_ACCESS_TOKEN)} chars")

print("="*60)

# Dhan API Headers
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
            'last_check': None
        }
        
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    saved = json.load(f)
                    # Merge with defaults
                    for key in default_state:
                        if key not in saved:
                            saved[key] = default_state[key]
                    return saved
        except Exception as e:
            print(f"❌ Error loading state: {e}")
        
        return default_state
    
    def save(self):
        """Save state to file"""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving state: {e}")
    
    def reset_daily(self):
        """Reset for new trading day"""
        self.data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'morning_balance': None,
            'current_balance': None,
            'max_loss_amount': None,
            'order_count': 0,
            'trading_allowed': True,
            'blocked_reason': '',
            'last_check': None
        }
        self.save()
        print("🔄 Daily reset completed")

# Global state
state = TradingState()

# ==================== DHAN API FUNCTIONS ====================
def get_dhan_balance():
    """Get balance from Dhan API - SIMPLE & RELIABLE"""
    
    if not DHAN_ACCESS_TOKEN:
        print("❌ No access token")
        return None
    
    # Try different endpoints
    endpoints = [
        {
            'url': 'https://api.dhan.co/positions',
            'name': 'Positions',
            'extract': extract_balance_from_positions
        },
        {
            'url': 'https://api.dhan.co/funds',
            'name': 'Funds',
            'extract': extract_balance_from_funds
        },
        {
            'url': 'https://api.dhan.co/margin',
            'name': 'Margin', 
            'extract': extract_balance_from_margin
        }
    ]
    
    for endpoint in endpoints:
        try:
            print(f"🔍 Trying {endpoint['name']}...")
            
            response = requests.get(
                endpoint['url'],
                headers=HEADERS,
                timeout=10
            )
            
            print(f"   📡 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Response received")
                
                # Show response structure for debugging
                if isinstance(data, dict):
                    print(f"   🔑 Keys: {list(data.keys())[:5]}")
                elif isinstance(data, list) and data:
                    print(f"   📦 List length: {len(data)}")
                    if isinstance(data[0], dict):
                        print(f"   🔑 First item keys: {list(data[0].keys())[:5]}")
                
                # Try to extract balance
                balance = endpoint['extract'](data)
                if balance is not None:
                    print(f"   💰 BALANCE FOUND: ₹{balance:,.2f}")
                    return balance
                else:
                    print(f"   ⚠️ Could not extract balance from {endpoint['name']}")
            
            elif response.status_code == 401:
                print("   🔐 Error: Unauthorized - Check your access token")
                return None
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:50]}")
    
    print("⚠️ Could not fetch balance from any endpoint")
    return None

def extract_balance_from_positions(data):
    """Extract balance from positions response"""
    try:
        if isinstance(data, list) and len(data) > 0:
            # Calculate total portfolio value
            total_value = 0
            for position in data:
                if isinstance(position, dict):
                    # Try different field names
                    if 'currentValue' in position:
                        total_value += float(position['currentValue'])
                    elif 'ltp' in position and 'quantity' in position:
                        ltp = float(position.get('ltp', 0))
                        quantity = float(position.get('quantity', 0))
                        total_value += ltp * quantity
            
            if total_value > 0:
                return total_value
    except Exception as e:
        print(f"   ❌ Error extracting from positions: {e}")
    
    return None

def extract_balance_from_funds(data):
    """Extract balance from funds response"""
    try:
        if isinstance(data, dict):
            # Try all possible balance field names
            balance_fields = [
                'availableMargin',
                'netAvailableMargin', 
                'marginAvailable',
                'balance',
                'cashBalance',
                'totalBalance',
                'netBalance',
                'funds',
                'availableCash'
            ]
            
            for field in balance_fields:
                if field in data:
                    value = data[field]
                    if isinstance(value, (int, float)) and value > 0:
                        print(f"   ✅ Found {field}: {value}")
                        return float(value)
                    
                    # Try string conversion
                    elif isinstance(value, str):
                        try:
                            num_value = float(value.replace(',', ''))
                            if num_value > 0:
                                print(f"   ✅ Converted {field}: {num_value}")
                                return num_value
                        except:
                            pass
    except Exception as e:
        print(f"   ❌ Error extracting from funds: {e}")
    
    return None

def extract_balance_from_margin(data):
    """Extract balance from margin response"""
    try:
        if isinstance(data, dict):
            if 'availableMargin' in data:
                value = data['availableMargin']
                if isinstance(value, (int, float)) and value > 0:
                    return float(value)
    except:
        pass
    
    return None

# ==================== CONDITION CHECKS ====================
def is_trading_time():
    """Condition 3: Check if within trading hours"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def check_all_conditions():
    """Check all 5 conditions"""
    
    conditions = {
        'condition_1': {'status': True, 'message': '20% Loss Limit'},
        'condition_2': {'status': True, 'message': '10 Orders/Day'},
        'condition_3': {'status': True, 'message': 'Trading Hours'},
        'condition_4': {'status': True, 'message': 'Balance Captured'},
        'condition_5': {'status': True, 'message': 'Real-time Monitoring'}
    }
    
    # Condition 3: Trading hours
    if not is_trading_time():
        conditions['condition_3']['status'] = False
        conditions['condition_3']['message'] = 'Outside trading hours (9:25-15:00)'
    
    # Condition 2: Order count
    if state.data['order_count'] >= MAX_ORDERS_PER_DAY:
        conditions['condition_2']['status'] = False
        conditions['condition_2']['message'] = f'10 orders limit reached ({state.data["order_count"]})'
    
    # Condition 1: 20% loss
    if state.data['morning_balance'] and state.data['current_balance']:
        loss = state.data['morning_balance'] - state.data['current_balance']
        if loss >= state.data['max_loss_amount']:
            conditions['condition_1']['status'] = False
            conditions['condition_1']['message'] = f'20% loss limit reached (₹{loss:,.2f})'
    
    # Condition 4: Balance captured
    if not state.data['morning_balance']:
        conditions['condition_4']['status'] = False
        conditions['condition_4']['message'] = 'Morning balance not captured'
    
    # Count violations
    violations = sum(1 for c in conditions.values() if not c['status'])
    
    return conditions, violations == 0

# ==================== MONITORING LOOP ====================
monitor_active = False
stop_signal = False

def monitoring_loop():
    """Main monitoring loop"""
    global monitor_active, stop_signal
    
    monitor_active = True
    
    print("\n" + "="*60)
    print("🤖 AUTOMATIC TRADING MANAGER ACTIVE")
    print("="*60)
    print("📋 MONITORING 5 CONDITIONS:")
    print("   1. 20% Daily Loss Limit")
    print("   2. Max 10 Orders/Day")
    print("   3. Trading Hours: 9:25 AM - 3:00 PM")
    print("   4. Auto Balance Capture at 9:25 AM")
    print("   5. Real-time Monitoring (Every 30s)")
    print("="*60)
    
    while not stop_signal:
        try:
            current_time = datetime.now().strftime('%H:%M:%S')
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            print(f"\n🔄 CHECK [{current_time}]")
            
            # Daily reset check
            if state.data['date'] != current_date:
                print("📅 New trading day - Resetting")
                state.reset_daily()
            
            # Condition 3: Trading hours check
            trading_now = is_trading_time()
            print(f"⏰ Trading Hours: {'✅ YES' if trading_now else '❌ NO'}")
            
            if not trading_now:
                print("⏰ Outside trading hours - Sleeping...")
                time.sleep(60)
                continue
            
            # Condition 4: Morning balance capture (9:25 AM)
            if state.data['morning_balance'] is None:
                print("🌅 Capturing morning balance...")
                balance = get_dhan_balance()
                
                if balance:
                    state.data['morning_balance'] = balance
                    state.data['current_balance'] = balance
                    state.data['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                    state.data['last_check'] = current_time
                    state.save()
                    
                    print(f"💰 Morning Balance: ₹{balance:,.2f}")
                    print(f"📊 20% Loss Limit: ₹{state.data['max_loss_amount']:,.2f}")
                else:
                    print("⏳ Could not fetch balance, retrying...")
            
            # Condition 5: Real-time monitoring
            if state.data['morning_balance']:
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
                    
                    # Save updated state
                    state.save()
            
            # Condition 2: Order count
            print(f"📊 Orders Today: {state.data['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            # Check all conditions
            conditions, all_ok = check_all_conditions()
            
            if all_ok:
                print("✅ All conditions satisfied")
            else:
                # Show which conditions failed
                for name, cond in conditions.items():
                    if not cond['status']:
                        print(f"🚨 {cond['message']}")
                
                # Block trading if any condition fails
                if state.data['trading_allowed']:
                    state.data['trading_allowed'] = False
                    state.data['blocked_reason'] = 'Condition violation'
                    state.save()
                    print("🛑 Trading blocked due to condition violation")
            
            # Sleep for next check
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"❌ Monitoring error: {e}")
            time.sleep(30)
    
    monitor_active = False
    print("\n⏹️ Monitoring stopped")

# ==================== WEB INTERFACE ====================
@app.route('/')
def dashboard():
    """Main dashboard"""
    
    # Get current balance for display
    current_balance = get_dhan_balance()
    if current_balance:
        state.data['current_balance'] = current_balance
        state.data['last_check'] = datetime.now().strftime('%H:%M:%S')
        state.save()
    
    # Calculate P&L
    morning_balance = state.data['morning_balance']
    current_balance_display = state.data['current_balance']
    
    if morning_balance and current_balance_display:
        loss = morning_balance - current_balance_display
        loss_percent = (loss / morning_balance) * 100 if morning_balance > 0 else 0
    else:
        loss = 0
        loss_percent = 0
    
    # Check conditions
    conditions, all_ok = check_all_conditions()
    
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Automatic Trading Manager',
        'version': '4.0',
        'trading_status': {
            'allowed': state.data['trading_allowed'] and all_ok,
            'blocked_reason': state.data['blocked_reason'] if state.data['blocked_reason'] else 'None',
            'all_conditions_ok': all_ok
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
            'last_check': state.data['last_check']
        },
        'conditions': [
            {
                'id': 1,
                'name': '20% Loss Limit',
                'status': '✅ ACTIVE' if conditions['condition_1']['status'] else '❌ VIOLATED',
                'details': conditions['condition_1']['message']
            },
            {
                'id': 2,
                'name': '10 Orders/Day',
                'status': '✅ ACTIVE' if conditions['condition_2']['status'] else '❌ VIOLATED',
                'details': conditions['condition_2']['message']
            },
            {
                'id': 3,
                'name': 'Trading Hours (9:25-15:00)',
                'status': '✅ ACTIVE' if conditions['condition_3']['status'] else '❌ VIOLATED',
                'details': conditions['condition_3']['message']
            },
            {
                'id': 4,
                'name': 'Morning Balance Capture',
                'status': '✅ ACTIVE' if conditions['condition_4']['status'] else '❌ VIOLATED',
                'details': conditions['condition_4']['message']
            },
            {
                'id': 5,
                'name': 'Real-time Monitoring',
                'status': '✅ ACTIVE',
                'details': f'Every {CHECK_INTERVAL} seconds'
            }
        ],
        'time': {
            'current': datetime.now().strftime('%H:%M:%S'),
            'is_trading_time': is_trading_time()
        }
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'HEALTHY',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/start')
def start_monitoring():
    global stop_signal
    if not monitor_active:
        stop_signal = False
        thread = threading.Thread(target=monitoring_loop, daemon=True)
        thread.start()
        return jsonify({'status': 'MONITORING_STARTED'})
    return jsonify({'status': 'ALREADY_RUNNING'})

@app.route('/stop')
def stop_monitoring():
    global stop_signal
    stop_signal = True
    return jsonify({'status': 'MONITORING_STOPPING'})

@app.route('/reset')
def reset_day():
    state.reset_daily()
    return jsonify({'status': 'DAY_RESET_COMPLETE'})

@app.route('/add_order')
def add_order():
    """Simulate order placement"""
    conditions, all_ok = check_all_conditions()
    
    if not all_ok or not state.data['trading_allowed']:
        return jsonify({
            'status': 'BLOCKED',
            'reason': 'Condition violation or trading blocked',
            'violations': [c['message'] for c in conditions.values() if not c['status']]
        })
    
    state.data['order_count'] += 1
    state.save()
    
    return jsonify({
        'status': 'ORDER_ADDED',
        'order_count': state.data['order_count'],
        'orders_remaining': MAX_ORDERS_PER_DAY - state.data['order_count'],
        'message': f'Order #{state.data["order_count"]} added successfully'
    })

@app.route('/get_balance')
def get_current_balance():
    """Get current balance"""
    balance = get_dhan_balance()
    return jsonify({
        'balance': balance,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'success': balance is not None
    })

@app.route('/debug')
def debug_info():
    """Debug information"""
    return jsonify({
        'environment': {
            'DHAN_ACCESS_TOKEN_set': bool(DHAN_ACCESS_TOKEN),
            'DHAN_CLIENT_ID_set': bool(DHAN_CLIENT_ID),
            'token_preview': DHAN_ACCESS_TOKEN[:20] + '...' if DHAN_ACCESS_TOKEN else None
        },
        'monitoring': {
            'active': monitor_active,
            'check_interval': CHECK_INTERVAL
        },
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'trading_time': is_trading_time()
    })

# ==================== START APPLICATION ====================
if __name__ == '__main__':
    # Start monitoring in background
    print("\n🚀 Starting monitoring system...")
    stop_signal = False
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Start Flask server
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Web server starting on port {port}")
    print(f"📊 Dashboard URL: https://dhan-risk-manager.onrender.com/")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
