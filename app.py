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
MAX_ORDERS_PER_DAY = 10
MAX_LOSS_PERCENT = 0.20
TRADING_START = dtime(9, 25)
TRADING_END = dtime(15, 0)
CHECK_INTERVAL = 30

# Dhan API - UPDATED ENDPOINTS
DHAN_BASE_URL = "https://api.dhan.co"

# ==================== CREDENTIALS ====================
def get_credentials():
    """Get credentials from environment"""
    access_token = os.environ.get('DHAN_ACCESS_TOKEN', '')
    client_id = os.environ.get('DHAN_CLIENT_ID', '')
    
    print("\n" + "="*60)
    print("🔐 CREDENTIALS STATUS")
    print("="*60)
    print(f"Access Token: {'✅ LOADED' if access_token else '❌ NOT FOUND'}")
    print(f"Client ID: {'✅ LOADED' if client_id else '❌ NOT FOUND'}")
    if access_token:
        print(f"Token Preview: {access_token[:30]}...")
        print(f"Token Length: {len(access_token)} chars")
    print("="*60)
    
    return {
        'access_token': access_token,
        'client_id': client_id
    }

CREDS = get_credentials()
ACCESS_TOKEN = CREDS['access_token']
CLIENT_ID = CREDS['client_id']

# CORRECT HEADERS for Dhan API v2
HEADERS = {
    'access-token': ACCESS_TOKEN,
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# ==================== STATE MANAGEMENT ====================
STATE_FILE = 'state.json'

class TradingState:
    def __init__(self):
        self.data = self.load()
    
    def load(self):
        default = {
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
                    for key in default:
                        if key not in saved:
                            saved[key] = default[key]
                    return saved
        except:
            pass
        
        return default
    
    def save(self):
        with open(STATE_FILE, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def reset(self):
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

state = TradingState()

# ==================== UPDATED DHAN API FUNCTIONS ====================
def get_dhan_balance():
    """Get balance from Dhan - UPDATED ENDPOINTS"""
    
    if not ACCESS_TOKEN:
        print("❌ No access token")
        return None
    
    # UPDATED: CORRECT DHAN ENDPOINTS (December 2025)
    endpoints = [
        {
            'name': 'FUNDS',
            'url': f'{DHAN_BASE_URL}/funds',
            'method': 'GET'
        },
        {
            'name': 'MARGIN',
            'url': f'{DHAN_BASE_URL}/margin',
            'method': 'GET' 
        },
        {
            'name': 'POSITIONS',
            'url': f'{DHAN_BASE_URL}/positions',
            'method': 'GET'
        },
        {
            'name': 'HOLDINGS',
            'url': f'{DHAN_BASE_URL}/holdings',
            'method': 'GET'
        },
        {
            'name': 'PROFILE',
            'url': f'{DHAN_BASE_URL}/profile',
            'method': 'GET'
        }
    ]
    
    for endpoint in endpoints:
        try:
            print(f"🔍 Trying: {endpoint['name']}")
            
            response = requests.get(
                endpoint['url'],
                headers=HEADERS,
                timeout=10
            )
            
            print(f"   📡 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Response received")
                
                # Debug: Show response structure
                if endpoint['name'] == 'FUNDS':
                    print(f"   📊 Funds response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                
                balance = extract_balance_v2(data, endpoint['name'])
                if balance is not None:
                    print(f"   💰 Balance found: ₹{balance:,.2f}")
                    return balance
                else:
                    print(f"   ⚠️ No balance in {endpoint['name']}")
                    
            elif response.status_code == 401:
                print("   🔐 Error: Unauthorized - Invalid token")
                return None
            elif response.status_code == 404:
                print(f"   📭 Error: Endpoint not found - {endpoint['url']}")
            else:
                print(f"   ❌ Error {response.status_code}")
                
        except Exception as e:
            print(f"   💥 Exception: {str(e)[:50]}")
    
    print("⚠️ All endpoints failed")
    return None

def extract_balance_v2(data, endpoint_name):
    """Extract balance from Dhan API v2 responses"""
    
    # Different structure for different endpoints
    if endpoint_name == 'FUNDS':
        # Funds endpoint structure
        if isinstance(data, dict):
            # Try all possible balance fields
            balance_fields = [
                'net',
                'netAvailableMargin',
                'availableMargin',
                'marginAvailable',
                'balance',
                'cashBalance',
                'totalBalance',
                'funds'
            ]
            
            for field in balance_fields:
                if field in data:
                    try:
                        value = float(data[field])
                        if value > 0:
                            return value
                    except:
                        continue
            
            # Check for nested structure
            if 'data' in data and isinstance(data['data'], dict):
                for field in balance_fields:
                    if field in data['data']:
                        try:
                            value = float(data['data'][field])
                            if value > 0:
                                return value
                        except:
                            continue
    
    elif endpoint_name == 'MARGIN':
        # Margin endpoint
        if isinstance(data, dict):
            if 'availableMargin' in data:
                return float(data['availableMargin'])
    
    elif endpoint_name == 'POSITIONS':
        # Positions endpoint - calculate from positions
        if isinstance(data, list):
            total_value = 0
            for position in data:
                if isinstance(position, dict):
                    # Calculate position value
                    ltp = float(position.get('ltp', 0))
                    quantity = float(position.get('quantity', 0))
                    total_value += ltp * quantity
            return total_value
    
    # Generic extraction
    if isinstance(data, dict):
        # Try to find any numeric value
        for key, value in data.items():
            if isinstance(value, (int, float)) and value > 1000:  # Likely balance
                return float(value)
            elif isinstance(value, dict):
                nested = extract_balance_v2(value, endpoint_name)
                if nested:
                    return nested
    
    return None

def test_all_endpoints():
    """Test all Dhan endpoints for debugging"""
    print("\n🔧 TESTING ALL DHAN ENDPOINTS")
    print("="*50)
    
    test_endpoints = [
        '/funds',
        '/margin',
        '/positions',
        '/holdings',
        '/profile',
        '/orders',
        '/trade',
        '/market/data'
    ]
    
    results = []
    
    for endpoint in test_endpoints:
        try:
            url = f'{DHAN_BASE_URL}{endpoint}'
            print(f"\n🔍 Testing: {endpoint}")
            
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            result = {
                'endpoint': endpoint,
                'status': response.status_code,
                'working': response.status_code == 200
            }
            
            if response.status_code == 200:
                print(f"   ✅ 200 OK")
                try:
                    data = response.json()
                    print(f"   📊 Response type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"   🔑 Keys: {list(data.keys())[:5]}...")
                except:
                    print(f"   📄 Response: {response.text[:100]}")
            else:
                print(f"   ❌ {response.status_code}")
                print(f"   📄 Error: {response.text[:100]}")
            
            results.append(result)
            
        except Exception as e:
            print(f"   💥 Error: {str(e)[:50]}")
            results.append({
                'endpoint': endpoint,
                'error': str(e)
            })
    
    return results

# ==================== MONITORING FUNCTIONS ====================
def is_trading_time():
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def check_conditions():
    """Check all 5 conditions"""
    
    # Condition 3: Trading hours
    if not is_trading_time():
        return False, "Outside trading hours (9:25-15:00)"
    
    # Condition 2: Order count
    if state.data['order_count'] >= MAX_ORDERS_PER_DAY:
        return False, f"10 orders limit reached ({state.data['order_count']})"
    
    # Condition 1: 20% loss
    if state.data['morning_balance'] and state.data['current_balance']:
        loss = state.data['morning_balance'] - state.data['current_balance']
        if loss >= state.data['max_loss_amount']:
            return False, f"20% loss limit reached (₹{loss:,.2f})"
    
    return True, "All conditions OK"

# ==================== MONITORING LOOP ====================
monitor_active = False
stop_signal = False

def monitoring_loop():
    global monitor_active, stop_signal
    
    monitor_active = True
    
    print("\n" + "="*60)
    print("🤖 AUTOMATIC TRADING MANAGER - UPDATED")
    print("="*60)
    print("📋 MONITORING 5 CONDITIONS:")
    print("   1. 20% Daily Loss Limit")
    print("   2. Max 10 Orders/Day")
    print("   3. Trading Hours: 9:25 AM - 3:00 PM")
    print("   4. Auto Balance Capture at 9:25 AM")
    print("   5. Real-time Monitoring (30s intervals)")
    print("="*60)
    
    # First, test all endpoints
    test_all_endpoints()
    
    while not stop_signal:
        try:
            current_time = datetime.now().strftime('%H:%M:%S')
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            print(f"\n⏰ CHECK [{current_time}]")
            
            # Daily reset
            if state.data['date'] != current_date:
                print("📅 New day - Resetting")
                state.reset()
            
            # Check trading hours
            trading_now = is_trading_time()
            print(f"🕒 Trading hours: {'✅ YES' if trading_now else '❌ NO'}")
            
            if not trading_now:
                time.sleep(60)
                continue
            
            # Morning balance capture (Condition 4)
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
                    print("⏳ Failed to get balance, retrying...")
            
            # Real-time monitoring (Condition 5)
            if state.data['morning_balance']:
                current_balance = get_dhan_balance()
                
                if current_balance:
                    state.data['current_balance'] = current_balance
                    state.data['last_check'] = current_time
                    
                    # Calculate P&L
                    loss = state.data['morning_balance'] - current_balance
                    loss_percent = (loss / state.data['morning_balance']) * 100
                    
                    print(f"📈 Current Balance: ₹{current_balance:,.2f}")
                    print(f"📉 Today's P&L: ₹{-loss:,.2f} ({loss_percent:+.1f}%)")
                    
                    # Save state
                    state.save()
            
            # Order count (Condition 2)
            print(f"📊 Orders Today: {state.data['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            # Check all conditions
            allowed, reason = check_conditions()
            if not allowed:
                print(f"🚨 BLOCKED: {reason}")
                state.data['trading_allowed'] = False
                state.data['blocked_reason'] = reason
                state.save()
            else:
                print("✅ All conditions OK")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(30)
    
    monitor_active = False
    print("⏹️ Monitoring stopped")

# ==================== FLASK ROUTES ====================
@app.route('/')
def dashboard():
    """Main dashboard"""
    
    # Get current balance
    current_balance = get_dhan_balance()
    if current_balance:
        state.data['current_balance'] = current_balance
        state.data['last_check'] = datetime.now().strftime('%H:%M:%S')
        state.save()
    
    # Calculate stats
    morning_balance = state.data['morning_balance']
    current_balance = state.data['current_balance']
    
    if morning_balance and current_balance:
        loss = morning_balance - current_balance
        loss_percent = (loss / morning_balance) * 100
    else:
        loss = 0
        loss_percent = 0
    
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Automatic Trading Manager',
        'version': '3.0',
        'conditions': [
            {
                'id': 1,
                'name': '20% Daily Loss Limit',
                'status': 'ACTIVE',
                'current': f"₹{loss:,.2f} ({loss_percent:.1f}%)",
                'limit': f"₹{state.data['max_loss_amount']:,.2f}" if state.data['max_loss_amount'] else 'Not set'
            },
            {
                'id': 2,
                'name': 'Max 10 Orders/Day',
                'status': 'ACTIVE',
                'current': state.data['order_count'],
                'limit': MAX_ORDERS_PER_DAY,
                'remaining': MAX_ORDERS_PER_DAY - state.data['order_count']
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
                'status': 'ACTIVE' if state.data['morning_balance'] else 'WAITING',
                'balance': state.data['morning_balance'],
                'captured_at': state.data['last_check'] if state.data['morning_balance'] else None
            },
            {
                'id': 5,
                'name': 'Real-time Monitoring',
                'status': 'ACTIVE',
                'interval': f'{CHECK_INTERVAL} seconds',
                'last_check': state.data['last_check']
            }
        ],
        'trading_status': {
            'allowed': state.data['trading_allowed'],
            'blocked_reason': state.data['blocked_reason'] if state.data['blocked_reason'] else 'None'
        },
        'credentials': {
            'access_token_loaded': bool(ACCESS_TOKEN),
            'client_id_loaded': bool(CLIENT_ID)
        }
    })

@app.route('/health')
def health():
    return jsonify({'status': 'HEALTHY'})

@app.route('/start')
def start():
    global stop_signal
    if not monitor_active:
        stop_signal = False
        thread = threading.Thread(target=monitoring_loop, daemon=True)
        thread.start()
        return jsonify({'status': 'STARTED'})
    return jsonify({'status': 'ALREADY_RUNNING'})

@app.route('/stop')
def stop():
    global stop_signal
    stop_signal = True
    return jsonify({'status': 'STOPPED'})

@app.route('/reset')
def reset():
    state.reset()
    return jsonify({'status': 'RESET_COMPLETE'})

@app.route('/add_order')
def add_order():
    """Simulate order"""
    if not state.data['trading_allowed']:
        return jsonify({
            'status': 'BLOCKED',
            'reason': state.data['blocked_reason']
        })
    
    state.data['order_count'] += 1
    state.save()
    
    return jsonify({
        'status': 'ORDER_ADDED',
        'order_count': state.data['order_count'],
        'remaining': MAX_ORDERS_PER_DAY - state.data['order_count']
    })

@app.route('/get_balance')
def get_balance():
    """Get current balance"""
    balance = get_dhan_balance()
    return jsonify({
        'balance': balance,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/test_endpoints')
def test_endpoints():
    """Test all Dhan endpoints"""
    results = test_all_endpoints()
    return jsonify({'results': results})

@app.route('/debug')
def debug():
    """Debug info"""
    return jsonify({
        'environment': {
            'DHAN_ACCESS_TOKEN_set': bool(ACCESS_TOKEN),
            'DHAN_CLIENT_ID_set': bool(CLIENT_ID),
            'token_preview': ACCESS_TOKEN[:20] + '...' if ACCESS_TOKEN else None
        },
        'state': state.data,
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# ==================== START ====================
if __name__ == '__main__':
    # Start monitoring
    print("\n🚀 Starting Automatic Trading Manager...")
    stop_signal = False
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Start server
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server starting on port {port}")
    print(f"📊 Dashboard: https://dhan-risk-manager.onrender.com/")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
