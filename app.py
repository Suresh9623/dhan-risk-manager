import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify
import requests

app = Flask(__name__)

# तुझ्या 5 CONDITIONS
MAX_ORDERS_PER_DAY = 10
MAX_LOSS_PERCENT = 0.20  # 20%
TRADING_START = dtime(9, 2)    # 9:02 AM
TRADING_END = dtime(15, 0)     # 3:00 PM
CHECK_INTERVAL = 30

print("\n" + "="*60)
print("💰 REAL DHAN BALANCE MANAGER")
print("="*60)

# Dhan Credentials
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')

print(f"🔐 Credentials Status:")
print(f"  Access Token: {'✅ LOADED' if DHAN_ACCESS_TOKEN else '❌ MISSING'}")
print(f"  Client ID: {'✅ LOADED' if DHAN_CLIENT_ID else '❌ MISSING'}")

if DHAN_ACCESS_TOKEN:
    print(f"  Token starts with: {DHAN_ACCESS_TOKEN[:20]}...")

print("="*60)

HEADERS = {
    'access-token': DHAN_ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# ==================== REAL BALANCE FETCH ====================
def get_real_dhan_balance():
    """Fetch ACTUAL balance from Dhan - NO DEFAULT VALUES"""
    
    if not DHAN_ACCESS_TOKEN:
        print("❌ ERROR: No access token found!")
        print("   Render Dashboard → Environment → Add DHAN_ACCESS_TOKEN")
        return None
    
    print("🔍 Fetching REAL balance from Dhan...")
    
    # 1. Try /positions endpoint (most reliable)
    try:
        print("📡 Trying /positions endpoint...")
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=10
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Got positions data")
            
            # DEBUG: Show response structure
            print(f"   📊 Response type: {type(data)}")
            
            if isinstance(data, list):
                print(f"   📦 Number of positions: {len(data)}")
                
                # Calculate TOTAL PORTFOLIO VALUE
                total_portfolio_value = 0
                
                for position in data:
                    if isinstance(position, dict):
                        print(f"   🔍 Position: {position.get('tradingSymbol', 'Unknown')}")
                        
                        # Try to get current value
                        if 'currentValue' in position:
                            try:
                                value = float(position['currentValue'])
                                total_portfolio_value += value
                                print(f"   💰 Current Value: ₹{value:,.2f}")
                            except:
                                pass
                        # If no currentValue, try to calculate
                        elif 'ltp' in position and 'quantity' in position:
                            try:
                                ltp = float(position['ltp'])
                                qty = float(position['quantity'])
                                value = ltp * qty
                                total_portfolio_value += value
                                print(f"   📈 Calculated: {qty} × ₹{ltp} = ₹{value:,.2f}")
                            except:
                                pass
                
                if total_portfolio_value > 0:
                    print(f"   🎯 TOTAL PORTFOLIO VALUE: ₹{total_portfolio_value:,.2f}")
                    return total_portfolio_value
                else:
                    print("   ⚠️ No positions or zero value")
            
            # Show sample of data for debugging
            if isinstance(data, dict):
                print(f"   🔑 Keys: {list(data.keys())}")
            elif isinstance(data, list) and data:
                print(f"   📄 First position sample: {data[0]}")
        
        elif response.status_code == 401:
            print("   🔐 ERROR 401: Unauthorized - Token invalid/expired!")
            print("   Please generate new token from https://developers.dhan.co")
            return None
        else:
            print(f"   ❌ Error {response.status_code}: {response.text[:100]}")
            
    except Exception as e:
        print(f"   💥 Positions endpoint error: {e}")
    
    # 2. Try /funds endpoint
    try:
        print("📡 Trying /funds endpoint...")
        response = requests.get(
            'https://api.dhan.co/funds',
            headers=HEADERS,
            timeout=10
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Got funds data")
            
            # Show full response for debugging
            print(f"   📄 Funds response: {data}")
            
            # Check for balance in various field names
            balance_fields = [
                'availableMargin', 'netAvailableMargin', 'marginAvailable',
                'balance', 'totalBalance', 'cashBalance', 'netBalance',
                'funds', 'availableCash', 'net'
            ]
            
            if isinstance(data, dict):
                for field in balance_fields:
                    if field in data:
                        value = data[field]
                        print(f"   🔍 Found '{field}': {value}")
                        
                        try:
                            # Convert to number
                            if isinstance(value, str):
                                # Remove commas and ₹ symbol
                                value = value.replace(',', '').replace('₹', '').strip()
                            
                            num_value = float(value)
                            if num_value > 0:
                                print(f"   🎯 AVAILABLE BALANCE: ₹{num_value:,.2f}")
                                return num_value
                        except Exception as e:
                            print(f"   ❌ Could not convert {field}: {e}")
            
            # Try nested structure
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, dict):
                        for field in balance_fields:
                            if field in val:
                                try:
                                    num_value = float(val[field])
                                    if num_value > 0:
                                        print(f"   🎯 BALANCE from {key}.{field}: ₹{num_value:,.2f}")
                                        return num_value
                                except:
                                    pass
        
        elif response.status_code == 404:
            print("   📭 ERROR 404: /funds endpoint not found")
            print("   Dhan API might have changed endpoints")
            
    except Exception as e:
        print(f"   💥 Funds endpoint error: {e}")
    
    # 3. Try /margin endpoint
    try:
        print("📡 Trying /margin endpoint...")
        response = requests.get(
            'https://api.dhan.co/margin',
            headers=HEADERS,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Got margin data: {data}")
            
            if isinstance(data, dict) and 'availableMargin' in data:
                try:
                    margin = float(data['availableMargin'])
                    print(f"   🎯 AVAILABLE MARGIN: ₹{margin:,.2f}")
                    return margin
                except:
                    pass
                    
    except Exception as e:
        print(f"   💥 Margin endpoint error: {e}")
    
    print("❌ ALL ENDPOINTS FAILED - Could not fetch real balance")
    print("   Possible issues:")
    print("   1. Token expired/invalid")
    print("   2. Dhan API down")
    print("   3. Network issues")
    
    return None

# ==================== STATE MANAGEMENT ====================
STATE_FILE = 'state.json'

def load_state():
    """Load or create state"""
    default = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'current_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'last_check': None,
        'real_balance_fetched': False
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

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except:
        pass

state = load_state()

# ==================== MONITORING ====================
def is_trading_time():
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

monitor_active = False
stop_signal = False

def monitoring_loop():
    global monitor_active, stop_signal
    
    monitor_active = True
    
    print("\n" + "="*60)
    print("🤖 REAL BALANCE MONITORING STARTED")
    print("="*60)
    
    while not stop_signal:
        try:
            current_time = datetime.now().strftime('%H:%M:%S')
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            print(f"\n⏰ [{current_time}] Checking...")
            
            # Daily reset
            if state['date'] != current_date:
                print("📅 New day - Resetting")
                state.update({
                    'date': current_date,
                    'morning_balance': None,
                    'current_balance': None,
                    'max_loss_amount': None,
                    'order_count': 0,
                    'trading_allowed': True,
                    'blocked_reason': '',
                    'last_check': None,
                    'real_balance_fetched': False
                })
                save_state(state)
            
            # Trading hours
            if not is_trading_time():
                print("⏰ Outside trading hours (9:02-15:00)")
                time.sleep(60)
                continue
            
            # Fetch REAL balance
            if not state['real_balance_fetched']:
                print("🌅 Fetching REAL morning balance...")
                real_balance = get_real_dhan_balance()
                
                if real_balance:
                    state['morning_balance'] = real_balance
                    state['current_balance'] = real_balance
                    state['max_loss_amount'] = real_balance * MAX_LOSS_PERCENT
                    state['real_balance_fetched'] = True
                    state['last_check'] = current_time
                    save_state(state)
                    
                    print(f"💰 REAL MORNING BALANCE: ₹{real_balance:,.2f}")
                    print(f"📊 20% LOSS LIMIT: ₹{state['max_loss_amount']:,.2f}")
                else:
                    print("❌ Failed to fetch real balance, retrying...")
            
            # Real-time monitoring
            if state['real_balance_fetched']:
                current_real_balance = get_real_dhan_balance()
                
                if current_real_balance:
                    state['current_balance'] = current_real_balance
                    state['last_check'] = current_time
                    
                    # Calculate ACTUAL loss
                    morning = state['morning_balance']
                    current = state['current_balance']
                    actual_loss = morning - current
                    loss_percent = (actual_loss / morning) * 100 if morning > 0 else 0
                    
                    print(f"📈 CURRENT REAL BALANCE: ₹{current_real_balance:,.2f}")
                    print(f"📉 ACTUAL LOSS TODAY: ₹{actual_loss:,.2f} ({loss_percent:+.1f}%)")
                    
                    # 20% loss check
                    if actual_loss >= state['max_loss_amount']:
                        print(f"🚨 ACTUAL 20% LOSS HIT! ₹{actual_loss:,.2f}")
                        state['trading_allowed'] = False
                        state['blocked_reason'] = f'20% Actual Loss: ₹{actual_loss:,.2f}'
                    
                    save_state(state)
            
            # Order count
            print(f"📊 Orders Today: {state['order_count']}/{MAX_ORDERS_PER_DAY}")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print(f"❌ Monitoring error: {e}")
            time.sleep(30)
    
    monitor_active = False

# ==================== WEB ROUTES ====================
@app.route('/')
def dashboard():
    """Show REAL balance dashboard"""
    
    # Fetch current REAL balance
    current_real_balance = get_real_dhan_balance()
    
    if current_real_balance:
        state['current_balance'] = current_real_balance
        state['last_check'] = datetime.now().strftime('%H:%M:%S')
        save_state(state)
    
    # Calculate ACTUAL P&L
    morning = state['morning_balance']
    current = state['current_balance']
    
    if morning and current:
        actual_loss = morning - current
        loss_percent = (actual_loss / morning) * 100
    else:
        actual_loss = 0
        loss_percent = 0
    
    return jsonify({
        'status': 'ACTIVE',
        'system': 'REAL Dhan Balance Manager',
        'real_balance_info': {
            'morning_balance': state['morning_balance'],
            'current_real_balance': state['current_balance'],
            'actual_loss_today': actual_loss,
            'actual_loss_percent': round(loss_percent, 2),
            'max_loss_limit': state['max_loss_amount'],
            'last_fetch': state['last_check'],
            'balance_type': 'REAL DHAN ACCOUNT'
        },
        'orders': {
            'today': state['order_count'],
            'limit': MAX_ORDERS_PER_DAY,
            'remaining': MAX_ORDERS_PER_DAY - state['order_count']
        },
        'trading': {
            'allowed': state['trading_allowed'],
            'blocked_reason': state['blocked_reason'] or 'None',
            'hours': '9:02 AM - 3:00 PM',
            'current_time': datetime.now().strftime('%H:%M:%S')
        },
        'message': 'This shows ACTUAL Dhan account balance, not default values'
    })

@app.route('/real_balance')
def real_balance():
    """Get REAL balance only"""
    balance = get_real_dhan_balance()
    
    if balance:
        return jsonify({
            'success': True,
            'real_balance': balance,
            'message': 'Actual Dhan account balance',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Could not fetch real balance',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })

@app.route('/debug_api')
def debug_api():
    """Debug Dhan API connection"""
    try:
        response = requests.get(
            'https://api.dhan.co/positions',
            headers=HEADERS,
            timeout=10
        )
        
        return jsonify({
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'response_preview': response.text[:500] if response.text else 'Empty',
            'token_valid': response.status_code == 200
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

# ==================== START ====================
if __name__ == '__main__':
    # Start monitoring
    print("\n🚀 Starting REAL balance monitoring...")
    stop_signal = False
    monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Start server
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server starting on port {port}")
    print(f"📊 Dashboard: https://dhan-risk-manager.onrender.com/")
    print(f"💰 Real Balance: https://dhan-risk-manager.onrender.com/real_balance")
    print(f"🔧 Debug API: https://dhan-risk-manager.onrender.com/debug_api")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
