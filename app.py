import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request
import requests

# ==================== CONFIGURATION ====================
app = Flask(__name__)

# तुझ्या सर्व 5 CONDITIONS
MAX_ORDERS_PER_DAY = 10                    # Condition 2: 10 orders/day
MAX_LOSS_PERCENT = 0.20                    # Condition 1: 20% loss limit
TRADING_START = dtime(9, 25)              # Condition 3: 9:25 AM
TRADING_END = dtime(15, 0)                # Condition 3: 3:00 PM
CHECK_INTERVAL = 30                       # Condition 5: Real-time monitoring

# Dhan API Configuration
DHAN_BASE_URL = "https://api.dhan.co"

# ==================== CREDENTIALS HANDLING ====================
def get_dhan_credentials():
    """Smart credential loading - tries multiple sources"""
    
    # Source 1: Environment variables (Render)
    access_token = os.environ.get('DHAN_ACCESS_TOKEN')
    client_id = os.environ.get('DHAN_CLIENT_ID')
    
    # Source 2: Alternative environment variable names
    if not access_token:
        for key in os.environ:
            if 'token' in key.lower() and 'dhan' in key.lower():
                access_token = os.environ.get(key)
                print(f"✅ Found token in: {key}")
                break
    
    # Source 3: Check for any token-like variable
    if not access_token:
        for key, value in os.environ.items():
            if len(value) > 50 and 'eyJ' in value:  # JWT token pattern
                access_token = value
                print(f"✅ Found JWT token in: {key}")
                break
    
    return {
        'access_token': access_token,
        'client_id': client_id,
        'token_loaded': bool(access_token),
        'client_id_loaded': bool(client_id)
    }

# Load credentials
CREDS = get_dhan_credentials()
ACCESS_TOKEN = CREDS['access_token']
CLIENT_ID = CREDS['client_id']

print("\n" + "="*60)
print("🔐 CREDENTIALS STATUS")
print("="*60)
print(f"Access Token Loaded: {'✅ YES' if CREDS['token_loaded'] else '❌ NO'}")
print(f"Client ID Loaded: {'✅ YES' if CREDS['client_id_loaded'] else '❌ NO'}")
if ACCESS_TOKEN:
    print(f"Token Preview: {ACCESS_TOKEN[:20]}...")
print("="*60)

# API Headers
HEADERS = {
    'access-token': ACCESS_TOKEN if ACCESS_TOKEN else '',
    'Content-Type': 'application/json'
}

# ==================== STATE MANAGEMENT ====================
STATE_FILE = 'state.json'
monitor_active = False
stop_signal = False

class TradingState:
    def __init__(self):
        self.load()
    
    def load(self):
        """Load state from file"""
        default_state = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'morning_balance': None,      # Condition 4: Morning balance
            'current_balance': None,
            'max_loss_amount': None,      # Condition 1: 20% limit amount
            'order_count': 0,             # Condition 2: Order counter
            'trading_allowed': True,
            'blocked_reason': '',
            'last_check': None,
            'total_loss': 0,
            'max_profit': 0,
            'daily_pnl': 0
        }
        
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    saved = json.load(f)
                    # Merge with defaults
                    for key in default_state:
                        if key not in saved:
                            saved[key] = default_state[key]
                    self.data = saved
                    return
        except Exception as e:
            print(f"❌ Error loading state: {e}")
        
        self.data = default_state
    
    def save(self):
        """Save state to file"""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving state: {e}")
    
    def reset_daily(self):
        """Reset for new day"""
        self.data.update({
            'date': datetime.now().strftime('%Y-%m-%d'),
            'morning_balance': None,
            'current_balance': None,
            'max_loss_amount': None,
            'order_count': 0,
            'trading_allowed': True,
            'blocked_reason': '',
            'last_check': None,
            'total_loss': 0,
            'max_profit': 0,
            'daily_pnl': 0
        })
        self.save()
        print("🔄 Daily reset completed")

# Global state object
state_manager = TradingState()

# ==================== DHAN API FUNCTIONS ====================
def fetch_dhan_balance():
    """Fetch balance from Dhan API - tries multiple endpoints"""
    
    if not ACCESS_TOKEN:
        print("❌ No access token available")
        return None
    
    endpoints = [
        {'path': '/funds', 'name': 'Funds'},
        {'path': '/positions', 'name': 'Positions'},
        {'path': '/margin', 'name': 'Margin'},
        {'path': '/account', 'name': 'Account'},
        {'path': '/holdings', 'name': 'Holdings'},
        {'path': '/limits', 'name': 'Limits'},
        {'path': '/profile', 'name': 'Profile'}
    ]
    
    for endpoint in endpoints:
        try:
            url = f"{DHAN_BASE_URL}{endpoint['path']}"
            print(f"🔍 Trying {endpoint['name']} endpoint...")
            
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=15
            )
            
            print(f"   📡 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                balance = extract_balance(data)
                if balance is not None:
                    print(f"   ✅ Balance found: ₹{balance:,.2f}")
                    return balance
                else:
                    print(f"   ⚠️ No balance found in response")
            else:
                print(f"   ❌ API Error: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ Timeout on {endpoint['name']}")
        except requests.exceptions.ConnectionError:
            print(f"   🔌 Connection error on {endpoint['name']}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:50]}")
    
    print("⚠️ All endpoints failed to return balance")
    return None

def extract_balance(data):
    """Extract balance from API response"""
    
    # If data is a list, check first item
    if isinstance(data, list):
        if data:
            data = data[0]
        else:
            return None
    
    # Common balance field names in Dhan API
    balance_fields = [
        'netAvailableMargin', 'availableMargin', 'marginAvailable',
        'balance', 'totalBalance', 'cashBalance', 'netBalance',
        'margin', 'availableCash', 'funds', 'net',
        'cashAvailable', 'marginAvailable', 'collateral'
    ]
    
    if isinstance(data, dict):
        # Check direct fields
        for field in balance_fields:
            if field in data:
                try:
                    value = float(data[field])
                    if value > 0:
                        return value
                except (ValueError, TypeError):
                    continue
        
        # Check nested structures
        for key, value in data.items():
            if isinstance(value, dict):
                nested = extract_balance(value)
                if nested is not None:
                    return nested
            elif isinstance(value, list) and value:
                nested = extract_balance(value[0])
                if nested is not None:
                    return nested
    
    return None

def cancel_all_orders():
    """Cancel all pending orders"""
    try:
        response = requests.get(
            f"{DHAN_BASE_URL}/orders",
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            orders = response.json()
            for order in orders:
                order_id = order.get('orderId')
                if order_id:
                    requests.delete(
                        f"{DHAN_BASE_URL}/orders/{order_id}",
                        headers=HEADERS,
                        timeout=5
                    )
            print("✅ All orders cancelled")
            return True
    except Exception as e:
        print(f"❌ Failed to cancel orders: {e}")
    return False

def exit_all_positions():
    """Exit all open positions"""
    try:
        response = requests.get(
            f"{DHAN_BASE_URL}/positions",
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            positions = response.json()
            print(f"📊 Found {len(positions)} positions to exit")
            return True
    except Exception as e:
        print(f"❌ Failed to exit positions: {e}")
    return False

# ==================== CONDITION CHECKS ====================
def is_trading_time():
    """Condition 3: Check if within 9:25 AM - 3:00 PM"""
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def check_20_percent_loss():
    """Condition 1: Check 20% loss limit"""
    state = state_manager.data
    
    if state['morning_balance'] and state['current_balance']:
        loss = state['morning_balance'] - state['current_balance']
        
        if loss >= state['max_loss_amount']:
            print(f"🚨 CONDITION 1 VIOLATED: 20% Loss Limit Hit!")
            print(f"   Loss: ₹{loss:,.2f} / Limit: ₹{state['max_loss_amount']:,.2f}")
            return False
    return True

def check_order_limit():
    """Condition 2: Check 10 orders/day limit"""
    state = state_manager.data
    
    if state['order_count'] >= MAX_ORDERS_PER_DAY:
        print(f"🚨 CONDITION 2 VIOLATED: 10 Orders Limit Reached!")
        print(f"   Orders: {state['order_count']} / Limit: {MAX_ORDERS_PER_DAY}")
        return False
    return True

def check_trading_hours():
    """Condition 3: Check trading hours"""
    if not is_trading_time():
        print("🚨 CONDITION 3 VIOLATED: Outside Trading Hours!")
        print(f"   Current: {datetime.now().strftime('%H:%M:%S')}")
        print(f"   Allowed: {TRADING_START.strftime('%H:%M')} - {TRADING_END.strftime('%H:%M')}")
        return False
    return True

def trigger_emergency(reason):
    """Emergency actions when any condition is violated"""
    print(f"\n🚨🚨🚨 EMERGENCY: {reason} 🚨🚨🚨")
    print("🛑 Executing emergency actions...")
    
    # 1. Cancel all orders
    cancel_all_orders()
    
    # 2. Exit all positions
    exit_all_positions()
    
    # 3. Block trading
    state_manager.data['trading_allowed'] = False
    state_manager.data['blocked_reason'] = reason
    state_manager.save()
    
    print("✅ Emergency actions completed")
    return True

# ==================== MAIN MONITORING LOOP ====================
def monitoring_loop():
    """Main loop that monitors all 5 conditions"""
    global monitor_active, stop_signal
    
    monitor_active = True
    
    print("\n" + "="*60)
    print("🤖 AUTOMATIC TRADING MANAGER - ALL 5 CONDITIONS ACTIVE")
    print("="*60)
    print("📋 MONITORING CONDITIONS:")
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
            if state_manager.data['date'] != current_date:
                print("📅 New trading day detected")
                state_manager.reset_daily()
            
            # ========== CONDITION 3: TRADING HOURS CHECK ==========
            if not check_trading_hours():
                if state_manager.data['trading_allowed']:
                    trigger_emergency("Outside Trading Hours")
                time.sleep(60)
                continue
            
            # ========== CONDITION 4: MORNING BALANCE CAPTURE ==========
            if state_manager.data['morning_balance'] is None:
                print("🌅 Capturing morning balance...")
                balance = fetch_dhan_balance()
                
                if balance:
                    state_manager.data['morning_balance'] = balance
                    state_manager.data['current_balance'] = balance
                    state_manager.data['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                    state_manager.data['last_check'] = current_time
                    state_manager.save()
                    
                    print(f"💰 Morning Balance: ₹{balance:,.2f}")
                    print(f"📊 20% Loss Limit: ₹{state_manager.data['max_loss_amount']:,.2f}")
                else:
                    print("⏳ Waiting for balance data...")
            
            # ========== REAL-TIME MONITORING ==========
            if state_manager.data['morning_balance']:
                # Get current balance
                current_balance = fetch_dhan_balance()
                
                if current_balance:
                    state_manager.data['current_balance'] = current_balance
                    state_manager.data['last_check'] = current_time
                    
                    # Calculate P&L
                    morning_balance = state_manager.data['morning_balance']
                    loss = morning_balance - current_balance
                    loss_percent = (loss / morning_balance) * 100 if morning_balance > 0 else 0
                    
                    print(f"📈 Current Balance: ₹{current_balance:,.2f}")
                    print(f"📊 Today's P&L: ₹{-loss:,.2f} ({loss_percent:+.1f}%)")
                    print(f"📉 Loss vs Limit: ₹{loss:,.2f} / ₹{state_manager.data['max_loss_amount']:,.2f}")
                    
                    # ========== CONDITION 1: 20% LOSS CHECK ==========
                    if not check_20_percent_loss():
                        trigger_emergency("20% Loss Limit Reached")
                    
                    # Save updated state
                    state_manager.save()
            
            # ========== CONDITION 2: ORDER COUNT CHECK ==========
            print(f"📊 Orders Today: {state_manager.data['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            if not check_order_limit():
                trigger_emergency("10 Orders Limit Reached")
            
            # ========== SUMMARY ==========
            print("✅ All conditions OK" if state_manager.data['trading_allowed'] else "🛑 Trading Blocked")
            
            # Wait for next check
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"❌ Monitoring error: {e}")
            time.sleep(30)
    
    monitor_active = False
    print("\n⏹️ Monitoring stopped")

# ==================== FLASK ROUTES ====================
@app.route('/')
def dashboard():
    """Main dashboard showing all 5 conditions"""
    state = state_manager.data
    
    # Calculate current stats
    morning_balance = state['morning_balance']
    current_balance = state['current_balance']
    
    if morning_balance and current_balance:
        loss = morning_balance - current_balance
        loss_percent = (loss / morning_balance) * 100
    else:
        loss = 0
        loss_percent = 0
    
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Automatic Trading Manager',
        'version': '2.0',
        'conditions': [
            {
                'id': 1,
                'name': '20% Daily Loss Limit',
                'status': 'ACTIVE',
                'current': f"₹{loss:,.2f} ({loss_percent:.1f}%)",
                'limit': f"₹{state['max_loss_amount']:,.2f}" if state['max_loss_amount'] else 'Not set'
            },
            {
                'id': 2,
                'name': 'Max 10 Orders/Day',
                'status': 'ACTIVE',
                'current': state['order_count'],
                'limit': MAX_ORDERS_PER_DAY,
                'remaining': MAX_ORDERS_PER_DAY - state['order_count']
            },
            {
                'id': 3,
                'name': 'Trading Hours (9:25 AM - 3:00 PM)',
                'status': 'ACTIVE',
                'current': datetime.now().strftime('%H:%M:%S'),
                'is_trading_time': is_trading_time()
            },
            {
                'id': 4,
                'name': 'Morning Balance Capture',
                'status': 'ACTIVE' if state['morning_balance'] else 'WAITING',
                'balance': state['morning_balance'],
                'captured_at': state['last_check'] if state['morning_balance'] else None
            },
            {
                'id': 5,
                'name': 'Real-time Monitoring',
                'status': 'ACTIVE',
                'interval': f'{CHECK_INTERVAL} seconds',
                'last_check': state['last_check']
            }
        ],
        'trading_status': {
            'allowed': state['trading_allowed'],
            'blocked_reason': state['blocked_reason'] if state['blocked_reason'] else 'None'
        },
        'credentials': {
            'access_token_loaded': CREDS['token_loaded'],
            'client_id_loaded': CREDS['client_id_loaded']
        }
    })

@app.route('/health')
def health():
    return jsonify({'status': 'HEALTHY', 'timestamp': datetime.now().isoformat()})

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
    return jsonify({'status': 'MONITORING_STOPPED'})

@app.route('/reset')
def reset_system():
    state_manager.reset_daily()
    return jsonify({'status': 'SYSTEM_RESET'})

@app.route('/emergency')
def emergency():
    trigger_emergency("Manual Emergency Trigger")
    return jsonify({'status': 'EMERGENCY_EXECUTED'})

@app.route('/add_order')
def add_order():
    """Simulate order placement"""
    if not state_manager.data['trading_allowed']:
        return jsonify({
            'status': 'BLOCKED',
            'reason': state_manager.data['blocked_reason']
        })
    
    state_manager.data['order_count'] += 1
    state_manager.save()
    
    return jsonify({
        'status': 'ORDER_RECORDED',
        'order_count': state_manager.data['order_count'],
        'remaining': MAX_ORDERS_PER_DAY - state_manager.data['order_count'],
        'message': f'{state_manager.data["order_count"]}/{MAX_ORDERS_PER_DAY} orders used'
    })

@app.route('/get_balance')
def get_balance():
    """Get current balance"""
    balance = fetch_dhan_balance()
    return jsonify({
        'balance': balance,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/capture_balance')
def capture_balance():
    """Manual balance capture"""
    balance = fetch_dhan_balance()
    
    if balance:
        state_manager.data['morning_balance'] = balance
        state_manager.data['current_balance'] = balance
        state_manager.data['max_loss_amount'] = balance * MAX_LOSS_PERCENT
        state_manager.data['last_check'] = datetime.now().strftime('%H:%M:%S')
        state_manager.save()
        
        return jsonify({
            'status': 'BALANCE_CAPTURED',
            'balance': balance,
            'loss_limit': state_manager.data['max_loss_amount'],
            'time': state_manager.data['last_check']
        })
    
    return jsonify({'status': 'FAILED', 'message': 'Could not fetch balance'})

@app.route('/debug')
def debug():
    """Debug endpoint"""
    return jsonify({
        'environment_variables': {
            'DHAN_ACCESS_TOKEN_set': bool(os.environ.get('DHAN_ACCESS_TOKEN')),
            'DHAN_CLIENT_ID_set': bool(os.environ.get('DHAN_CLIENT_ID')),
            'all_dhan_vars': [k for k in os.environ if 'DHAN' in k]
        },
        'state': state_manager.data,
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'trading_time': is_trading_time(),
        'monitor_active': monitor_active
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
    print(f"📊 Dashboard: https://dhan-risk-manager.onrender.com/")
    print(f"🔧 Debug: https://dhan-risk-manager.onrender.com/debug")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
