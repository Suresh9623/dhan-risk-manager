import os
import requests
from flask import Flask, jsonify
import json

app = Flask(__name__)

print("\n" + "="*70)
print("🔧 DHAN API DEBUGGER - FINDING EXACT PROBLEM")
print("="*70)

# ==================== GET CREDENTIALS ====================
ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN')
CLIENT_ID = os.environ.get('DHAN_CLIENT_ID')

print("📊 CREDENTIALS ANALYSIS:")
print("-" * 40)

if not ACCESS_TOKEN:
    print("❌ CRITICAL: No DHAN_ACCESS_TOKEN found in environment!")
    print("   Render Dashboard → Environment → Add DHAN_ACCESS_TOKEN")
else:
    print(f"✅ DHAN_ACCESS_TOKEN: Found ({len(ACCESS_TOKEN)} characters)")
    print(f"   First 30 chars: {ACCESS_TOKEN[:30]}")
    print(f"   Last 10 chars: ...{ACCESS_TOKEN[-10:]}")
    
    # Check token format
    if ACCESS_TOKEN.startswith('eyJ'):
        print("   ✅ Format: JWT token (correct)")
    elif 'bearer' in ACCESS_TOKEN.lower():
        print("   ⚠️ Warning: Contains 'bearer' - remove it!")
        print("   Fix: Use only the token without 'Bearer ' prefix")
    else:
        print("   ⚠️ Format: Unknown - should start with 'eyJ'")

if not CLIENT_ID:
    print("❌ CRITICAL: No DHAN_CLIENT_ID found!")
else:
    print(f"✅ DHAN_CLIENT_ID: Found - {CLIENT_ID}")

print("-" * 40)

# ==================== TEST ENDPOINTS ====================
DHAN_ENDPOINTS = [
    {"name": "FUNDS", "url": "https://api.dhan.co/funds"},
    {"name": "MARGIN", "url": "https://api.dhan.co/margin"},
    {"name": "POSITIONS", "url": "https://api.dhan.co/positions"},
    {"name": "PROFILE", "url": "https://api.dhan.co/profile"},
    {"name": "ACCOUNT", "url": "https://api.dhan.co/account"},
    {"name": "HOLDINGS", "url": "https://api.dhan.co/holdings"},
    {"name": "LIMITS", "url": "https://api.dhan.co/limits"}
]

HEADERS = {
    'access-token': ACCESS_TOKEN if ACCESS_TOKEN else '',
    'Content-Type': 'application/json'
}

def test_dhan_connection():
    """Test connection to all Dhan endpoints"""
    print("\n🔗 TESTING DHAN API CONNECTIONS:")
    print("-" * 40)
    
    results = []
    
    for endpoint in DHAN_ENDPOINTS:
        try:
            print(f"\n🔍 Testing {endpoint['name']}...")
            print(f"   URL: {endpoint['url']}")
            
            response = requests.get(
                endpoint['url'],
                headers=HEADERS,
                timeout=15
            )
            
            status_emoji = "✅" if response.status_code == 200 else "❌"
            print(f"   {status_emoji} Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   📦 Response received ({len(response.text)} chars)")
                
                # Try to parse JSON
                try:
                    data = response.json()
                    print(f"   📊 JSON parsed successfully")
                    
                    # Look for balance fields
                    if isinstance(data, dict):
                        balance_fields = ['availableMargin', 'netAvailableMargin', 'balance', 'cashBalance']
                        for field in balance_fields:
                            if field in data:
                                print(f"   💰 Found {field}: {data[field]}")
                    
                except json.JSONDecodeError:
                    print(f"   ⚠️ Response is not valid JSON")
                    print(f"   📄 Preview: {response.text[:200]}")
            
            elif response.status_code == 401:
                print("   🔐 ERROR: Unauthorized - Invalid or expired token!")
            elif response.status_code == 403:
                print("   🚫 ERROR: Forbidden - Check permissions!")
            elif response.status_code == 404:
                print("   📭 ERROR: Endpoint not found")
            else:
                print(f"   ❗ Unexpected status: {response.status_code}")
                print(f"   📄 Response: {response.text[:200]}")
            
            results.append({
                "endpoint": endpoint['name'],
                "status_code": response.status_code,
                "success": response.status_code == 200
            })
            
        except requests.exceptions.Timeout:
            print(f"   ⏰ TIMEOUT: Request took too long")
            results.append({
                "endpoint": endpoint['name'],
                "error": "Timeout"
            })
        except requests.exceptions.ConnectionError:
            print(f"   🔌 CONNECTION ERROR: Cannot reach Dhan API")
            results.append({
                "endpoint": endpoint['name'], 
                "error": "Connection failed"
            })
        except Exception as e:
            print(f"   💥 EXCEPTION: {str(e)}")
            results.append({
                "endpoint": endpoint['name"],
                "error": str(e)
            })
    
    print("-" * 40)
    
    # Summary
    success_count = sum(1 for r in results if r.get('success') == True)
    print(f"\n📈 SUMMARY: {success_count}/{len(results)} endpoints successful")
    
    if success_count == 0:
        print("🚨 CRITICAL: All endpoints failed!")
        print("   Possible issues:")
        print("   1. Invalid/expired access token")
        print("   2. Network blocking API calls")
        print("   3. Dhan API server down")
    
    return results

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    """Main debug page"""
    return jsonify({
        "service": "Dhan API Debugger",
        "endpoints": {
            "/test": "Run full API tests",
            "/simple": "Quick connection test", 
            "/token": "Check token details",
            "/headers": "Show request headers"
        }
    })

@app.route('/test')
def run_tests():
    """Run all tests"""
    results = test_dhan_connection()
    
    # Also check environment
    env_status = {
        "DHAN_ACCESS_TOKEN_set": bool(ACCESS_TOKEN),
        "DHAN_CLIENT_ID_set": bool(CLIENT_ID),
        "token_length": len(ACCESS_TOKEN) if ACCESS_TOKEN else 0,
        "token_preview": ACCESS_TOKEN[:20] + "..." if ACCESS_TOKEN and len(ACCESS_TOKEN) > 20 else ACCESS_TOKEN
    }
    
    return jsonify({
        "environment": env_status,
        "test_results": results,
        "total_tests": len(results),
        "successful_tests": sum(1 for r in results if r.get('success') == True)
    })

@app.route('/simple')
def simple_test():
    """Simple test - just funds endpoint"""
    try:
        response = requests.get(
            "https://api.dhan.co/funds",
            headers=HEADERS,
            timeout=10
        )
        
        return jsonify({
            "endpoint": "funds",
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "response_preview": response.text[:500] if response.text else "Empty response",
            "headers_sent": {
                "access-token": f"{ACCESS_TOKEN[:20]}..." if ACCESS_TOKEN and len(ACCESS_TOKEN) > 20 else ACCESS_TOKEN,
                "content-type": "application/json"
            }
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        })

@app.route('/token')
def token_info():
    """Show token information"""
    if not ACCESS_TOKEN:
        return jsonify({"error": "No token found"})
    
    analysis = {
        "length": len(ACCESS_TOKEN),
        "starts_with": ACCESS_TOKEN[:10],
        "ends_with": ACCESS_TOKEN[-10:],
        "is_jwt_format": ACCESS_TOKEN.startswith('eyJ'),
        "contains_bearer": 'bearer' in ACCESS_TOKEN.lower(),
        "dot_count": ACCESS_TOKEN.count('.'),
        "parts": ACCESS_TOKEN.split('.') if '.' in ACCESS_TOKEN else []
    }
    
    # Check common issues
    issues = []
    if 'bearer' in ACCESS_TOKEN.lower():
        issues.append("Contains 'Bearer' prefix - remove it!")
    if not ACCESS_TOKEN.startswith('eyJ'):
        issues.append("Not JWT format - should start with 'eyJ'")
    if ACCESS_TOKEN.count('.') != 2:
        issues.append(f"JWT should have 2 dots, found {ACCESS_TOKEN.count('.')}")
    if len(ACCESS_TOKEN) < 50:
        issues.append(f"Token too short ({len(ACCESS_TOKEN)} chars)")
    
    analysis["issues"] = issues
    analysis["has_issues"] = len(issues) > 0
    
    return jsonify(analysis)

@app.route('/headers')
def show_headers():
    """Show what headers are being sent"""
    return jsonify({
        "actual_headers": HEADERS,
        "access_token_preview": f"{ACCESS_TOKEN[:30]}..." if ACCESS_TOKEN and len(ACCESS_TOKEN) > 30 else ACCESS_TOKEN,
        "client_id": CLIENT_ID
    })

# ==================== START APPLICATION ====================
if __name__ == '__main__':
    # Run initial tests
    print("\n🚀 STARTING DEBUG SERVER...")
    test_dhan_connection()
    
    # Start server
    port = int(os.environ.get('PORT', 10000))
    print(f"\n🌐 Server running on port {port}")
    print("📋 Available endpoints:")
    print("  /         - Main page")
    print("  /test     - Full API tests")
    print("  /simple   - Quick test")
    print("  /token    - Token analysis")
    print("  /headers  - Request headers")
    print("="*70)
    
    app.run(host='0.0.0.0', port=port, debug=False)
