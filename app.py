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
MAX_LOSS_PERCENT = 0.20
TRADING_START = dtime(9, 2)
TRADING_END = dtime(15, 0)
CHECK_INTERVAL = 30

print("\n" + "="*60)
print("💰 ACTUAL DHAN BALANCE FETCH")
print("="*60)

# Credentials
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')

print(f"🔐 Token: {'✅ LOADED' if DHAN_ACCESS_TOKEN else '❌ MISSING'}")
print(f"🔐 Client ID: {'✅ LOADED' if DHAN_CLIENT_ID else '❌ MISSING'}")

if DHAN_ACCESS_TOKEN:
    print(f"📋 Token first 20 chars: {DHAN_ACCESS_TOKEN[:20]}...")
    print(f"📏 Token length: {len(DHAN_ACCESS_TOKEN)} chars")

print("="*60)

HEADERS = {
    'access-token': DHAN_ACCESS_TOKEN,
    'Content-Type': 'application/json'
}

# ==================== NEW DHAN API ENDPOINTS ====================
def get_actual_dhan_balance():
    """Fetch ACTUAL balance using NEW Dhan endpoints"""
    
    if not DHAN_ACCESS_TOKEN:
        print("❌ No access token")
        return None
    
    print("🔍 Fetching ACTUAL Dhan balance...")
    
    # NEW ENDPOINTS (December 2025)
    endpoints = [
        {
            'name': 'CLIENT POSITIONS',
            'url': 'https://api.dhan.co/client/positions',
            'method': 'GET'
        },
        {
            'name': 'CLIENT FUNDS', 
            'url': 'https://api.dhan.co/client/funds',
            'method': 'GET'
        },
        {
            'name': 'CLIENT MARGIN',
            'url': 'https://api.dhan.co/client/margin',
            'method': 'GET'
        },
        {
            'name': 'POSITIONS (old)',
            'url': 'https://api.dhan.co/positions',
            'method': 'GET'
        },
        {
            'name': 'FUNDS (old)',
            'url': 'https://api.dhan.co/funds',
            'method': 'GET'
        }
    ]
    
    for endpoint in endpoints:
        try:
            print(f"\n📡 Trying: {endpoint['name']}")
            print(f"   URL: {endpoint['url']}")
            
            response = requests.get(
                endpoint['url'],
                headers=HEADERS,
                timeout=10
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Response received")
                
                # Show response structure
                print(f"   📊 Response type: {type(data)}")
                
                if isinstance(data, dict):
                    print(f"   🔑 Keys: {list(data.keys())}")
                    # Show first few values
                    for key in list(data.keys())[:3]:
                        value = data[key]
                        print(f"   📝 {key}: {str(value)[:50]}...")
                
                elif isinstance(data, list) and data:
                    print(f"   📦 List length: {len(data)}")
                    if isinstance(data[0], dict):
                        print(f"   🔑 First item keys: {list(data[0].keys())[:5]}")
                
                # Try to extract balance
                balance = extract_balance_from_response(data, endpoint['name'])
                if balance:
                    print(f"   🎯 ACTUAL BALANCE FOUND: ₹{balance:,.2f}")
                    return balance
                else:
                    print(f"   ⚠️ No balance found in this response")
            
            elif response.status_code == 401:
                print("   🔐 ERROR: Unauthorized - Token invalid!")
                return None
            elif response.status_code == 404:
                print(f"   📭 Endpoint not found")
            else:
                print(f"   ❌ Error {response.status_code}: {response.text[:100]}")
                
        except Exception as e:
            print(f"   💥 Error: {str(e)[:50]}")
    
    print("❌ All endpoints failed")
    return None

def extract_balance_from_response(data, endpoint_name):
    """Extract balance from any response format"""
    
    # If it's a list of positions
    if isinstance(data, list) and endpoint_name in ['CLIENT POSITIONS', 'POSITIONS']:
        total_value = 0
        for item in data:
            if isinstance(item, dict):
                # Try all possible value fields
                for field in ['currentValue', 'marketValue', 'totalValue', 'value']:
                    if field in item:
                        try:
                            total_value += float(item[field])
                            break
                        except:
                            pass
        
        if total_value > 0:
            return total_value
    
    # If it's a dict (funds/margin response)
    elif isinstance(data, dict):
        # All possible balance field names
        balance_fields = [
            'availableMargin', 'netAvailableMargin', 'marginAvailable',
            'balance', 'totalBalance', 'cashBalance', 'netBalance',
            'funds', 'availableCash', 'net', 'total', 'cash',
            'collateral', 'equity', 'currentBalance'
        ]
        
        for field in balance_fields:
            if field in data:
                value = data[field]
                print(f"   🔍 Found {field}: {value}")
                
                try:
                    if isinstance(value, (int, float)):
                        return float(value)
                    elif isinstance(value, str):
                        # Clean string
                        cleaned = value.replace(',', '').replace('₹', '').strip()
                        return float(cleaned)
                except:
                    continue
    
    return None

# ==================== SIMPLE TEST ENDPOINTS ====================
@app.route('/')
def home():
    return jsonify({
        'status': 'ACTIVE',
        'system': 'Actual Dhan Balance Fetcher',
        'endpoints': {
            '/actual_balance': 'Get actual Dhan balance',
            '/test_endpoints': 'Test all Dhan endpoints',
            '/token_info': 'Check token info'
        }
    })

@app.route('/actual_balance')
def actual_balance():
    """Get ACTUAL Dhan balance"""
    balance = get_actual_dhan_balance()
    
    if balance:
        return jsonify({
            'success': True,
            'actual_balance': balance,
            'message': 'Actual Dhan account balance fetched',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    
    return jsonify({
        'success': False,
        'error': 'Could not fetch actual balance',
        'suggestion': 'Check token and API endpoints'
    })

@app.route('/test_endpoints')
def test_endpoints():
    """Test all possible endpoints"""
    results = []
    
    test_urls = [
        'https://api.dhan.co/client/positions',
        'https://api.dhan.co/client/funds',
        'https://api.dhan.co/client/margin',
        'https://api.dhan.co/positions',
        'https://api.dhan.co/funds',
        'https://api.dhan.co/margin',
        'https://api.dhan.co/profile'
    ]
    
    for url in test_urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=5)
            results.append({
                'url': url,
                'status': response.status_code,
                'working': response.status_code == 200
            })
        except Exception as e:
            results.append({
                'url': url,
                'error': str(e)
            })
    
    return jsonify({'endpoint_tests': results})

@app.route('/token_info')
def token_info():
    """Show token information"""
    if not DHAN_ACCESS_TOKEN:
        return jsonify({'error': 'No token'})
    
    return jsonify({
        'token_loaded': True,
        'token_length': len(DHAN_ACCESS_TOKEN),
        'first_20_chars': DHAN_ACCESS_TOKEN[:20],
        'last_10_chars': DHAN_ACCESS_TOKEN[-10:],
        'is_jwt': DHAN_ACCESS_TOKEN.startswith('eyJ')
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server starting on port {port}")
    print(f"💰 Test: https://dhan-risk-manager.onrender.com/actual_balance")
    print(f"🔧 Debug: https://dhan-risk-manager.onrender.com/test_endpoints")
    print("="*60)
    app.run(host='0.0.0.0', port=port, debug=False)
