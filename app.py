"""
धन रिस्क मॅनेजर - रिअल फंड डिस्प्ले
तुमचा डिमॅट अकाउंट फंड रिअल-टाइम दाखवणारा
"""

import os
import datetime
import time
import threading
from flask import Flask, jsonify, request, render_template_string
import logging

# सेटअप लॉगिंग
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# धन API इंपोर्ट करा
try:
    from dhanhq import dhanhq
    DHAN_AVAILABLE = True
    logger.info("✅ धन API उपलब्ध")
except ImportError:
    DHAN_AVAILABLE = False
    logger.error("❌ धन API पॅकेज इन्स्टॉल करा: pip install dhanhq")

# ============ कॉन्फिगरेशन ============
TRADING_START_TIME = datetime.time(9, 25)
TRADING_END_TIME = datetime.time(15, 0)
MAX_DAILY_TRADES = 10
MAX_LOSS_PERCENTAGE = 20

# ============ स्टेट मॅनेजमेंट ============
class TradingState:
    def __init__(self):
        self.daily_trade_count = 0
        self.total_capital = 0
        self.current_loss = 0
        self.current_profit = 0
        self.trading_enabled = True
        self.last_reset_date = datetime.date.today()
        self.trade_history = []
        self.positions = []
        
        # धन API क्लायंट
        self.dhan_client = None
        self.dhan_connected = False
        self.init_dhan_client()
        
        logger.info("📊 ट्रेडिंग स्टेट इनिशियलाइज्ड")
    
    def init_dhan_client(self):
        """धन API क्लायंट इनिशियलाइज करा"""
        if not DHAN_AVAILABLE:
            logger.error("❌ धन API पॅकेज नाही. requirements.txt मध्ये dhanhq जोडा.")
            return
            
        client_id = os.environ.get('DHAN_CLIENT_ID')
        access_token = os.environ.get('DHAN_ACCESS_TOKEN')
        
        if not client_id or not access_token:
            logger.error("❌ DHAN_CLIENT_ID किंवा DHAN_ACCESS_TOKEN सेट नाही")
            logger.info("ℹ️ Render Dashboard → Environment → Add Environment Variables")
            return
        
        try:
            logger.info(f"🔗 धन API सोबत कनेक्ट करत आहे...")
            self.dhan_client = dhanhq(client_id, access_token)
            self.dhan_connected = True
            
            # प्रथम बॅलन्स फेच करा
            balance = self.get_real_balance()
            if balance:
                self.total_capital = balance.get('availableBalance', 0)
                logger.info(f"✅ धन API कनेक्शन स्थापित")
                logger.info(f"💰 प्रारंभिक बॅलन्स: ₹{self.total_capital}")
            else:
                logger.error("❌ बॅलन्स फेच अयशस्वी")
                
        except Exception as e:
            logger.error(f"❌ धन API कनेक्शन त्रुटी: {e}")
    
    def get_real_balance(self):
        """वास्तविक धन बॅलन्स फेच करा"""
        if not self.dhan_client:
            logger.error("❌ धन API क्लायंट उपलब्ध नाही")
            return None
        
        try:
            logger.info("🔄 वास्तविक बॅलन्स फेच करत आहे...")
            balance_data = self.dhan_client.get_fund_limits()
            
            if isinstance(balance_data, dict):
                logger.info(f"✅ बॅलन्स डेटा: {balance_data}")
                return balance_data
            elif isinstance(balance_data, list) and len(balance_data) > 0:
                logger.info(f"✅ बॅलन्स डेटा (लिस्ट): {balance_data[0]}")
                return balance_data[0]
            else:
                logger.error(f"❌ अवैध बॅलन्स रिस्पॉन्स: {balance_data}")
                return None
                
        except Exception as e:
            logger.error(f"❌ बॅलन्स फेच त्रुटी: {str(e)}")
            return None
    
    def get_detailed_funds(self):
        """तपशीलवार फंड माहिती"""
        if not self.dhan_client:
            return {"error": "धन API कनेक्ट नाही"}
        
        try:
            funds = self.dhan_client.get_fund_limits()
            
            # संपूर्ण फंड माहिती
            if isinstance(funds, dict):
                return {
                    "status": "success",
                    "data": funds,
                    "timestamp": datetime.datetime.now().isoformat()
                }
            elif isinstance(funds, list):
                return {
                    "status": "success",
                    "data": funds[0] if funds else {},
                    "timestamp": datetime.datetime.now().isoformat()
                }
            else:
                return {"status": "error", "message": "अवैध डेटा फॉरमॅट"}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def get_positions(self):
        """वर्तमान पोझिशन्स"""
        if not self.dhan_client:
            return []
        
        try:
            positions = self.dhan_client.get_positions()
            return positions if positions else []
        except:
            return []
    
    def get_order_book(self):
        """ऑर्डर बुक"""
        if not self.dhan_client:
            return []
        
        try:
            orders = self.dhan_client.get_order_book()
            return orders if orders else []
        except:
            return []
    
    def get_trade_book(self):
        """ट्रेड बुक"""
        if not self.dhan_client:
            return []
        
        try:
            trades = self.dhan_client.get_trade_book()
            return trades if trades else []
        except:
            return []

# ग्लोबल इंस्टन्स
trading_state = TradingState()

# ============ HTML टेम्पलेट (रिअल फंड डिस्प्ले सह) ============
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="mr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>माझा डिमॅट अकाउंट - फंड माहिती</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Arial', sans-serif; }
        body { background: linear-gradient(135deg, #1a2980, #26d0ce); min-height: 100vh; padding: 20px; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; }
        
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            text-align: center;
        }
        
        .header h1 {
            color: #1a2980;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        
        .header .subtitle {
            color: #666;
            font-size: 1.1em;
        }
        
        .connection-status {
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            margin-top: 15px;
            font-size: 0.9em;
        }
        
        .connected { background: #d4edda; color: #155724; }
        .disconnected { background: #f8d7da; color: #721c24; }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .card h2 {
            color: #1a2980;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #26d0ce;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .card h2 i { color: #26d0ce; }
        
        .funds-grid, .info-grid {
            display: grid;
            gap: 15px;
        }
        
        .fund-item, .info-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid #1a2980;
        }
        
        .fund-label {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 5px;
        }
        
        .fund-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #1a2980;
        }
        
        .fund-value.green { color: #28a745; }
        .fund-value.red { color: #dc3545; }
        .fund-value.blue { color: #007bff; }
        
        .controls {
            display: flex;
            gap: 15px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s;
            font-size: 1em;
        }
        
        .btn:hover { transform: translateY(-3px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        
        .btn-refresh { background: #17a2b8; color: white; }
        .btn-details { background: #6f42c1; color: white; }
        .btn-orders { background: #fd7e14; color: white; }
        .btn-positions { background: #20c997; color: white; }
        
        .detailed-info {
            background: white;
            padding: 25px;
            border-radius: 15px;
            margin-top: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .detailed-info h3 {
            color: #1a2980;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        
        .data-table th, .data-table td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        
        .data-table th {
            background: #f8f9fa;
            color: #1a2980;
            font-weight: bold;
        }
        
        .data-table tr:hover {
            background: #f1f3f5;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border-left: 4px solid #dc3545;
        }
        
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border-left: 4px solid #28a745;
        }
        
        .footer {
            text-align: center;
            margin-top: 30px;
            color: white;
            opacity: 0.9;
            font-size: 0.9em;
        }
        
        @media (max-width: 768px) {
            .dashboard { grid-template-columns: 1fr; }
            .header { padding: 20px; }
            .header h1 { font-size: 2em; }
            .controls { flex-direction: column; }
            .btn { width: 100%; justify-content: center; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-wallet"></i> माझा डिमॅट अकाउंट फंड</h1>
            <p class="subtitle">धन ट्रेडिंग अकाउंटची रिअल-टाइम फंड माहिती</p>
            
            <div class="connection-status {{ 'connected' if data.dhan_connected else 'disconnected' }}">
                <i class="fas {{ 'fa-check-circle' if data.dhan_connected else 'fa-times-circle' }}"></i>
                {{ 'धन API कनेक्टेड' if data.dhan_connected else 'धन API डिस्कनेक्टेड' }}
            </div>
        </div>
        
        <div class="dashboard">
            <!-- मुख्य फंड कार्ड -->
            <div class="card">
                <h2><i class="fas fa-rupee-sign"></i> मुख्य बॅलन्स</h2>
                <div class="funds-grid">
                    <div class="fund-item">
                        <div class="fund-label">उपलब्ध बॅलन्स</div>
                        <div class="fund-value green">₹{{ "{:,.2f}".format(data.available_balance) }}</div>
                    </div>
                    <div class="fund-item">
                        <div class="fund-label">वापरलेली रक्कम</div>
                        <div class="fund-value red">₹{{ "{:,.2f}".format(data.utilized_amount) }}</div>
                    </div>
                    <div class="fund-item">
                        <div class="fund-label">कॉलेटरल व्हॅल्यू</div>
                        <div class="fund-value blue">₹{{ "{:,.2f}".format(data.collateral_value) }}</div>
                    </div>
                    <div class="fund-item">
                        <div class="fund-label">उपलब्ध मार्जिन</div>
                        <div class="fund-value green">₹{{ "{:,.2f}".format(data.available_margin) }}</div>
                    </div>
                </div>
                <div class="controls">
                    <button class="btn btn-refresh" onclick="refreshFunds()">
                        <i class="fas fa-sync-alt"></i> फंड रिफ्रेश
                    </button>
                    <button class="btn btn-details" onclick="showDetails()">
                        <i class="fas fa-info-circle"></i> सर्व तपशील
                    </button>
                </div>
            </div>
            
            <!-- अकाउंट माहिती कार्ड -->
            <div class="card">
                <h2><i class="fas fa-chart-pie"></i> अकाउंट सारांश</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <strong>एक्सपोजर:</strong> ₹{{ "{:,.2f}".format(data.exposure) }}
                    </div>
                    <div class="info-item">
                        <strong>एक्सपोजर लिमिट:</strong> ₹{{ "{:,.2f}".format(data.exposure_limit) }}
                    </div>
                    <div class="info-item">
                        <strong>एक्सपोजर %:</strong> {{ "{:.1f}".format(data.exposure_percentage) }}%
                    </div>
                    <div class="info-item">
                        <strong>एक्सपोजर वापर:</strong> 
                        <div style="background: #e9ecef; height: 10px; border-radius: 5px; margin-top: 5px;">
                            <div style="background: {{ 'green' if data.exposure_percentage < 50 else ('orange' if data.exposure_percentage < 80 else 'red') }}; 
                                        width: {{ data.exposure_percentage }}%; height: 100%; border-radius: 5px;"></div>
                        </div>
                    </div>
                </div>
                <div class="controls">
                    <button class="btn btn-orders" onclick="getOrderBook()">
                        <i class="fas fa-book"></i> ऑर्डर बुक
                    </button>
                    <button class="btn btn-positions" onclick="getPositions()">
                        <i class="fas fa-chart-line"></i> पोझिशन्स
                    </button>
                </div>
            </div>
        </div>
        
        <!-- तपशीलवार माहिती (डायनॅमिक) -->
        <div id="detailedInfo" class="detailed-info" style="display: none;">
            <h3><i class="fas fa-list-alt"></i> संपूर्ण फंड माहिती</h3>
            <div id="detailsContent"></div>
        </div>
        
        <!-- स्टेटस मेसेज -->
        <div id="statusMessage" style="display: none;"></div>
        
        <div class="footer">
            <p>धन ट्रेडिंग • रिअल-टाइम फंड मॉनिटरिंग • © 2025</p>
            <p style="font-size: 0.8em; margin-top: 5px;">अपडेट वेळ: {{ data.last_update }}</p>
        </div>
    </div>
    
    <script>
        // फंड रिफ्रेश
        function refreshFunds() {
            showMessage('🔄 फंड माहिती रिफ्रेश करत आहे...', 'info');
            
            fetch('/api/refresh_funds')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        showMessage('✅ फंड माहिती यशस्वीरीत्या अपडेट केली', 'success');
                        setTimeout(() => location.reload(), 1000);
                    } else {
                        showMessage('❌ त्रुटी: ' + data.message, 'error');
                    }
                })
                .catch(error => {
                    showMessage('❌ नेटवर्क त्रुटी: ' + error, 'error');
                });
        }
        
        // संपूर्ण तपशील दाखवा
        function showDetails() {
            showMessage('📋 संपूर्ण माहिती लोड करत आहे...', 'info');
            
            fetch('/api/get_full_funds')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        let detailsContent = '';
                        
                        // टेबल तयार करा
                        detailsContent += '<table class="data-table">';
                        for (const [key, value] of Object.entries(data.data)) {
                            detailsContent += `
                                <tr>
                                    <td><strong>${key}</strong></td>
                                    <td>${typeof value === 'number' ? '₹' + value.toLocaleString('en-IN', {minimumFractionDigits: 2}) : value}</td>
                                </tr>
                            `;
                        }
                        detailsContent += '</table>';
                        
                        document.getElementById('detailsContent').innerHTML = detailsContent;
                        document.getElementById('detailedInfo').style.display = 'block';
                        
                        showMessage('✅ संपूर्ण माहिती लोड केली', 'success');
                    } else {
                        showMessage('❌ त्रुटी: ' + data.message, 'error');
                    }
                });
        }
        
        // ऑर्डर बुक
        function getOrderBook() {
            showMessage('📖 ऑर्डर बुक लोड करत आहे...', 'info');
            
            fetch('/api/get_order_book')
                .then(response => response.json())
                .then(data => {
                    let content = '<h4><i class="fas fa-book-open"></i> ऑर्डर बुक</h4>';
                    
                    if (data.orders && data.orders.length > 0) {
                        content += '<table class="data-table"><tr><th>ऑर्डर ID</th><th>स्टॉक</th><th>प्रकार</th><th>प्रमाण</th><th>स्थिती</th></tr>';
                        
                        data.orders.slice(0, 10).forEach(order => {
                            content += `
                                <tr>
                                    <td>${order.orderId || 'N/A'}</td>
                                    <td>${order.securityId || 'N/A'}</td>
                                    <td><span class="badge ${order.transactionType === 'BUY' ? 'green' : 'red'}">${order.transactionType || 'N/A'}</span></td>
                                    <td>${order.quantity || 0}</td>
                                    <td><span class="badge ${order.status === 'COMPLETE' ? 'green' : 'orange'}">${order.status || 'PENDING'}</span></td>
                                </tr>
                            `;
                        });
                        
                        content += '</table>';
                    } else {
                        content += '<p class="info-message">कोणतेही ऑर्डर नाहीत</p>';
                    }
                    
                    document.getElementById('detailsContent').innerHTML = content;
                    document.getElementById('detailedInfo').style.display = 'block';
                    showMessage('✅ ऑर्डर बुक लोड केला', 'success');
                });
        }
        
        // पोझिशन्स
        function getPositions() {
            showMessage('📈 पोझिशन्स लोड करत आहे...', 'info');
            
            fetch('/api/get_positions')
                .then(response => response.json())
                .then(data => {
                    let content = '<h4><i class="fas fa-chart-line"></i> वर्तमान पोझिशन्स</h4>';
                    
                    if (data.positions && data.positions.length > 0) {
                        content += '<table class="data-table"><tr><th>स्टॉक</th><th>प्रमाण</th><th>सरासरी किंमत</th><th>P&L</th><th>वर्तमान किंमत</th></tr>';
                        
                        let totalPnl = 0;
                        data.positions.forEach(position => {
                            const pnl = position.pnl || position.netReturns || 0;
                            totalPnl += pnl;
                            
                            content += `
                                <tr>
                                    <td><strong>${position.securityId || 'N/A'}</strong></td>
                                    <td>${position.quantity || 0}</td>
                                    <td>₹${position.averagePrice ? position.averagePrice.toFixed(2) : '0.00'}</td>
                                    <td><span class="${pnl >= 0 ? 'green' : 'red'}">₹${pnl.toFixed(2)}</span></td>
                                    <td>₹${position.ltp ? position.ltp.toFixed(2) : '0.00'}</td>
                                </tr>
                            `;
                        });
                        
                        content += '</table>';
                        content += `<p style="margin-top: 15px;"><strong>एकूण P&L: </strong><span class="${totalPnl >= 0 ? 'green' : 'red'}">₹${totalPnl.toFixed(2)}</span></p>`;
                    } else {
                        content += '<p class="info-message">कोणतेही पोझिशन्स नाहीत</p>';
                    }
                    
                    document.getElementById('detailsContent').innerHTML = content;
                    document.getElementById('detailedInfo').style.display = 'block';
                    showMessage('✅ पोझिशन्स लोड केल्या', 'success');
                });
        }
        
        // मेसेज दाखवा
        function showMessage(message, type) {
            const messageDiv = document.getElementById('statusMessage');
            messageDiv.innerHTML = `
                <div class="${type === 'error' ? 'error-message' : 'success-message'}">
                    <i class="fas ${type === 'error' ? 'fa-exclamation-triangle' : 'fa-check-circle'}"></i>
                    ${message}
                </div>
            `;
            messageDiv.style.display = 'block';
            
            // 5 सेकंदांनी मेसेज हटवा
            setTimeout(() => {
                messageDiv.style.display = 'none';
            }, 5000);
        }
        
        // ऑटो रिफ्रेश (प्रत्येक 60 सेकंदांनी)
        setInterval(() => {
            fetch('/api/get_balance')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        console.log('ऑटो अपडेट:', data.message);
                    }
                });
        }, 60000);
    </script>
</body>
</html>
'''

# ============ API रूट्स ============
@app.route('/')
def home():
    """मुख्य डॅशबोर्ड - रिअल फंड डिस्प्ले"""
    # वास्तविक फंड माहिती
    balance_data = trading_state.get_real_balance() or {}
    
    # डिफॉल्ट व्हॅल्यूज
    available_balance = balance_data.get('availableBalance', 0)
    utilized_amount = balance_data.get('utilizedAmount', 0)
    collateral_value = balance_data.get('collateralValue', 0)
    exposure = balance_data.get('exposure', 0)
    available_margin = balance_data.get('availableMargin', 0)
    
    # एक्सपोजर टक्के
    exposure_limit = balance_data.get('exposureLimit', available_balance * 4)  # डिफॉल्ट 4x
    exposure_percentage = (exposure / exposure_limit * 100) if exposure_limit > 0 else 0
    
    data = {
        "dhan_connected": trading_state.dhan_connected,
        "available_balance": float(available_balance),
        "utilized_amount": float(utilized_amount),
        "collateral_value": float(collateral_value),
        "exposure": float(exposure),
        "exposure_limit": float(exposure_limit),
        "exposure_percentage": float(exposure_percentage),
        "available_margin": float(available_margin),
        "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "raw_data": balance_data  # डीबगिंगसाठी
    }
    
    return render_template_string(HTML_TEMPLATE, data=data)

@app.route('/api/get_balance', methods=['GET'])
def api_get_balance():
    """API: वर्तमान बॅलन्स"""
    balance_data = trading_state.get_real_balance()
    
    if balance_data:
        return jsonify({
            "status": "success",
            "message": "बॅलन्स मिळवला",
            "data": balance_data,
            "timestamp": datetime.datetime.now().isoformat()
        })
    else:
        return jsonify({
            "status": "error",
            "message": "बॅलन्स फेच अयशस्वी",
            "dhan_connected": trading_state.dhan_connected
        }), 500

@app.route('/api/refresh_funds', methods=['POST'])
def api_refresh_funds():
    """API: फंड रिफ्रेश"""
    balance_data = trading_state.get_real_balance()
    
    if balance_data:
        # ग्लोबल स्टेट अपडेट
        trading_state.total_capital = balance_data.get('availableBalance', 0)
        
        return jsonify({
            "status": "success",
            "message": "फंड माहिती यशस्वीरीत्या अपडेट केली",
            "available_balance": trading_state.total_capital,
            "timestamp": datetime.datetime.now().isoformat()
        })
    else:
        return jsonify({
            "status": "error",
            "message": "फंड अपडेट अयशस्वी"
        }), 500

@app.route('/api/get_full_funds', methods=['GET'])
def api_get_full_funds():
    """API: संपूर्ण फंड माहिती"""
    funds = trading_state.get_detailed_funds()
    return jsonify(funds)

@app.route('/api/get_positions', methods=['GET'])
def api_get_positions():
    """API: वर्तमान पोझिशन्स"""
    positions = trading_state.get_positions()
    
    return jsonify({
        "status": "success",
        "positions": positions,
        "count": len(positions),
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/api/get_order_book', methods=['GET'])
def api_get_order_book():
    """API: ऑर्डर बुक"""
    orders = trading_state.get_order_book()
    
    return jsonify({
        "status": "success",
        "orders": orders,
        "count": len(orders),
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/api/get_trade_book', methods=['GET'])
def api_get_trade_book():
    """API: ट्रेड बुक"""
    trades = trading_state.get_trade_book()
    
    return jsonify({
        "status": "success",
        "trades": trades,
        "count": len(trades),
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health():
    """हेल्थ चेक"""
    balance_data = trading_state.get_real_balance()
    
    return jsonify({
        "status": "healthy" if trading_state.dhan_connected else "unhealthy",
        "dhan_connected": trading_state.dhan_connected,
        "available_balance": balance_data.get('availableBalance', 0) if balance_data else 0,
        "timestamp": datetime.datetime.now().isoformat(),
        "environment_variables_set": bool(os.environ.get('DHAN_CLIENT_ID') and os.environ.get('DHAN_ACCESS_TOKEN'))
    })

# ============ सर्व्हर स्टार्ट ============
if __name__ == '__main__':
    logger.info("🚀 धन डिमॅट फंड मॉनिटर सुरू करत आहे...")
    logger.info(f"🔗 धन API कनेक्शन: {trading_state.dhan_connected}")
    
    if trading_state.dhan_connected:
        logger.info(f"💰 प्रारंभिक बॅलन्स: ₹{trading_state.total_capital}")
    else:
        logger.error("❌ धन API कनेक्ट नाही. कृपया Environment Variables तपासा.")
        logger.info("ℹ️ आवश्यक Environment Variables:")
        logger.info("   - DHAN_CLIENT_ID")
        logger.info("   - DHAN_ACCESS_TOKEN")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
