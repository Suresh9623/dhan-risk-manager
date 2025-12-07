"""
धन डिमॅट रिस्क मॅनेजर
तुमच्या धन डिमॅट अकाउंटसाठी संपूर्ण रिस्क मॅनेजमेंट
"""

import os
import datetime
import time
import threading
from flask import Flask, jsonify, request, render_template_string
import logging

# सेटअप लॉगिंग
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# धन API
try:
    from dhanhq import dhanhq
    DHAN_AVAILABLE = True
    logger.info("✅ धन API उपलब्ध")
except ImportError:
    DHAN_AVAILABLE = False
    logger.error("❌ धन API पॅकेज नाही. 'pip install dhanhq' करा")

# ============ कॉन्फिगरेशन ============
TRADING_START_TIME = datetime.time(9, 25)  # सकाळी 9:25
TRADING_END_TIME = datetime.time(15, 0)    # दुपारी 3:00
MAX_DAILY_TRADES = 10
MAX_LOSS_PERCENTAGE = 20

# ============ धन रिस्क मॅनेजर ============
class DhanRiskManager:
    def __init__(self):
        self.dhan_client = None
        self.connected = False
        self.monitoring = False
        self.blocked = False
        self.block_reason = ""
        self.daily_trades = 0
        self.initial_capital = 0
        self.current_balance = 0
        self.total_loss = 0
        self.positions = []
        
        # धन API कनेक्शन
        self.connect_to_dhan()
        
        logger.info("🛡️ धन डिमॅट रिस्क मॅनेजर सुरू")
    
    def connect_to_dhan(self):
        """धन API सोबत कनेक्ट करा"""
        if not DHAN_AVAILABLE:
            logger.error("❌ धन API पॅकेज नाही")
            return
            
        client_id = os.environ.get('DHAN_CLIENT_ID')
        access_token = os.environ.get('DHAN_ACCESS_TOKEN')
        
        if not client_id or not access_token:
            logger.error("❌ DHAN_CLIENT_ID किंवा DHAN_ACCESS_TOKEN सेट नाही")
            logger.info("ℹ️ Render Dashboard → Environment → Add:")
            logger.info("   DHAN_CLIENT_ID = तुमचा_क्लायंट_ID")
            logger.info("   DHAN_ACCESS_TOKEN = तुमचा_टोकन")
            return
        
        try:
            logger.info("🔗 धन API सोबत कनेक्ट करत आहे...")
            self.dhan_client = dhanhq(client_id, access_token)
            self.connected = True
            
            # प्रारंभिक बॅलन्स सेट करा
            self.refresh_balance()
            
            logger.info(f"✅ धन API कनेक्टेड!")
            logger.info(f"💰 प्रारंभिक बॅलन्स: ₹{self.initial_capital}")
            
        except Exception as e:
            logger.error(f"❌ धन कनेक्शन त्रुटी: {e}")
    
    def refresh_balance(self):
        """बॅलन्स रिफ्रेश करा"""
        if not self.connected:
            return False
            
        try:
            funds = self.dhan_client.get_fund_limits()
            
            if isinstance(funds, dict):
                self.current_balance = funds.get('availableBalance', 0)
                # प्रथम वेळी initial capital सेट करा
                if self.initial_capital == 0:
                    self.initial_capital = self.current_balance
                return True
                
            elif isinstance(funds, list) and len(funds) > 0:
                self.current_balance = funds[0].get('availableBalance', 0)
                if self.initial_capital == 0:
                    self.initial_capital = self.current_balance
                return True
                
        except Exception as e:
            logger.error(f"❌ बॅलन्स फेच त्रुटी: {e}")
        
        return False
    
    def get_positions(self):
        """वर्तमान पोझिशन्स"""
        if not self.connected:
            return []
            
        try:
            positions = self.dhan_client.get_positions()
            self.positions = positions if positions else []
            return self.positions
        except:
            return []
    
    def calculate_pnl(self):
        """P&L कॅल्क्युलेट करा"""
        if not self.connected:
            return 0, 0
            
        total_pnl = 0
        positions = self.get_positions()
        
        for pos in positions:
            pnl = pos.get('pnl', 0) or pos.get('netReturns', 0)
            total_pnl += pnl
        
        # बॅलन्स तोटा
        balance_loss = max(0, self.initial_capital - self.current_balance)
        self.total_loss = abs(total_pnl) + balance_loss
        
        # तोटा टक्के
        if self.initial_capital > 0:
            loss_percentage = (self.total_loss / self.initial_capital) * 100
        else:
            loss_percentage = 0
            
        return self.total_loss, loss_percentage
    
    def exit_all_positions(self):
        """सर्व पोझिशन्स बंद करा"""
        if not self.connected:
            return False
            
        try:
            positions = self.get_positions()
            if not positions:
                return True
                
            exited = 0
            for position in positions:
                if position.get('quantity', 0) > 0:
                    try:
                        self.dhan_client.place_order(
                            security_id=position.get('securityId'),
                            exchange_segment=position.get('exchangeSegment', 'NSE_EQ'),
                            transaction_type="SELL",
                            quantity=position.get('quantity'),
                            order_type="MARKET",
                            product_type=position.get('productType', 'INTRADAY')
                        )
                        exited += 1
                    except:
                        continue
            
            logger.warning(f"🚨 {exited} पोझिशन्स एक्झिट केल्या")
            return exited > 0
            
        except Exception as e:
            logger.error(f"❌ एक्झिट त्रुटी: {e}")
            return False
    
    def check_rules(self):
        """सर्व नियम तपासा"""
        violations = []
        
        # 1. ट्रेडिंग वेळ
        current_time = datetime.datetime.now().time()
        if not (TRADING_START_TIME <= current_time <= TRADING_END_TIME):
            if current_time > TRADING_END_TIME:
                violations.append("ट्रेडिंग वेळ संपली (3:00 PM)")
                # ऑटो एक्झिट
                self.exit_all_positions()
                self.blocked = True
                self.block_reason = "3:00 PM नंतर ट्रेडिंग बंद"
            else:
                violations.append("ट्रेडिंग वेळ सुरू नाही (9:25 AM)")
        
        # 2. 20% तोटा
        _, loss_percentage = self.calculate_pnl()
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            violations.append(f"20% तोटा झाला ({loss_percentage:.1f}%)")
            # ऑटो एक्झिट
            self.exit_all_positions()
            self.blocked = True
            self.block_reason = "20% तोटा झाला"
        
        # 3. दिवसाची ट्रेड मर्यादा
        if self.daily_trades >= MAX_DAILY_TRADES:
            violations.append(f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या")
            self.blocked = True
            self.block_reason = f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या"
        
        return violations
    
    def start_monitoring(self):
        """मॉनिटरिंग सुरू करा"""
        if not self.connected:
            logger.error("❌ धन API कनेक्ट नाही")
            return
            
        self.monitoring = True
        logger.info("🔍 मॉनिटरिंग सुरू केले")
        
        def monitor():
            while self.monitoring:
                try:
                    # बॅलन्स अपडेट
                    self.refresh_balance()
                    
                    # नियम तपासा
                    violations = self.check_rules()
                    if violations:
                        for violation in violations:
                            logger.warning(f"⚠️ {violation}")
                    
                    time.sleep(30)  # प्रत्येक 30 सेकंदांनी
                    
                except Exception as e:
                    logger.error(f"❌ मॉनिटरिंग त्रुटी: {e}")
                    time.sleep(60)
        
        # बॅकग्राऊंड थ्रेड
        self.monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """मॉनिटरिंग थांबवा"""
        self.monitoring = False
        logger.info("⏸️ मॉनिटरिंग थांबवले")

# ग्लोबल इंस्टन्स
dhan_manager = DhanRiskManager()

# ============ HTML टेम्पलेट ============
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="mr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>धन डिमॅट रिस्क मॅनेजर</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
            margin-bottom: 10px;
        }
        .subtitle {
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 30px;
        }
        .status-card {
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
            font-weight: bold;
            font-size: 1.1em;
        }
        .status-connected {
            background: #d4edda;
            color: #155724;
            border: 2px solid #28a745;
        }
        .status-disconnected {
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #dc3545;
        }
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            border-left: 5px solid #3498db;
        }
        .card h3 {
            color: #2c3e50;
            margin-top: 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .info-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #dee2e6;
        }
        .info-label {
            color: #6c757d;
        }
        .info-value {
            font-weight: bold;
            color: #2c3e50;
        }
        .danger { color: #dc3545; }
        .warning { color: #ffc107; }
        .success { color: #28a745; }
        .controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 30px 0;
        }
        .btn {
            padding: 15px;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            font-size: 1em;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            transition: all 0.3s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .btn-start { background: #28a745; color: white; }
        .btn-stop { background: #dc3545; color: white; }
        .btn-exit { background: #fd7e14; color: white; }
        .btn-refresh { background: #17a2b8; color: white; }
        .btn-add { background: #6f42c1; color: white; }
        .btn-reset { background: #6c757d; color: white; }
        .rules {
            background: #e8f4f8;
            padding: 20px;
            border-radius: 10px;
            margin-top: 30px;
            border-left: 5px solid #3498db;
        }
        .rules h3 {
            color: #2c3e50;
            margin-top: 0;
        }
        .rule-item {
            padding: 10px;
            margin: 10px 0;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #2c3e50;
        }
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            font-weight: bold;
            text-align: center;
        }
        .alert-danger {
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #dc3545;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 2px solid #28a745;
        }
        @media (max-width: 768px) {
            .container { padding: 20px; }
            .dashboard { grid-template-columns: 1fr; }
            .controls { grid-template-columns: 1fr; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <h1><i class="fas fa-shield-alt"></i> धन डिमॅट रिस्क मॅनेजर</h1>
        <p class="subtitle">तुमच्या धन डिमॅट अकाउंटसाठी संपूर्ण रिस्क मॅनेजमेंट</p>
        
        <!-- कनेक्शन स्टेटस -->
        <div class="status-card {% if data.connected %}status-connected{% else %}status-disconnected{% endif %}">
            {% if data.connected %}
                <i class="fas fa-check-circle"></i> धन API कनेक्टेड
            {% else %}
                <i class="fas fa-times-circle"></i> धन API डिस्कनेक्टेड
            {% endif %}
        </div>
        
        <!-- अलर्ट मेसेज -->
        {% if data.blocked %}
        <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle"></i> {{ data.block_reason }}
        </div>
        {% endif %}
        
        <!-- डॅशबोर्ड -->
        <div class="dashboard">
            <!-- फंड माहिती -->
            <div class="card">
                <h3><i class="fas fa-wallet"></i> फंड माहिती</h3>
                <div class="info-item">
                    <span class="info-label">बॅलन्स:</span>
                    <span class="info-value success">₹{{ data.current_balance }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">तोटा:</span>
                    <span class="info-value {% if data.loss_percentage >= 10 %}danger{% else %}warning{% endif %}">
                        ₹{{ data.total_loss }} ({{ data.loss_percentage }}%)
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">एक्सपोजर:</span>
                    <span class="info-value">{{ data.exposure }}%</span>
                </div>
                <div class="info-item">
                    <span class="info-label">पोझिशन्स:</span>
                    <span class="info-value">{{ data.positions_count }}</span>
                </div>
            </div>
            
            <!-- ट्रेडिंग माहिती -->
            <div class="card">
                <h3><i class="fas fa-chart-line"></i> ट्रेडिंग माहिती</h3>
                <div class="info-item">
                    <span class="info-label">ट्रेड काउंट:</span>
                    <span class="info-value {% if data.daily_trades >= 8 %}warning{% else %}success{% endif %}">
                        {{ data.daily_trades }}/{{ data.max_trades }}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">बाकी ट्रेड्स:</span>
                    <span class="info-value">{{ data.remaining_trades }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">मॉनिटरिंग:</span>
                    <span class="info-value {% if data.monitoring_active %}success{% else %}danger{% endif %}">
                        {{ 'सक्रिय' if data.monitoring_active else 'निष्क्रिय' }}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">वेळ:</span>
                    <span class="info-value">{{ data.current_time }}</span>
                </div>
            </div>
        </div>
        
        <!-- कंट्रोल बटण्स -->
        <div class="controls">
            <button class="btn btn-start" onclick="startMonitoring()">
                <i class="fas fa-play"></i> मॉनिटरिंग सुरू
            </button>
            <button class="btn btn-stop" onclick="stopMonitoring()">
                <i class="fas fa-pause"></i> मॉनिटरिंग थांबवा
            </button>
            <button class="btn btn-exit" onclick="exitAllPositions()">
                <i class="fas fa-sign-out-alt"></i> सर्व बंद करा
            </button>
            <button class="btn btn-refresh" onclick="refreshBalance()">
                <i class="fas fa-sync-alt"></i> बॅलन्स रिफ्रेश
            </button>
            <button class="btn btn-add" onclick="addTrade()">
                <i class="fas fa-plus-circle"></i> ट्रेड जोडा
            </button>
            <button class="btn btn-reset" onclick="resetDaily()">
                <i class="fas fa-redo"></i> दिवस रिसेट
            </button>
        </div>
        
        <!-- नियम -->
        <div class="rules">
            <h3><i class="fas fa-rules"></i> रिस्क मॅनेजमेंट नियम</h3>
            <div class="rule-item">
                <strong><i class="fas fa-exclamation-triangle"></i> नियम 1:</strong> 20% तोटा झाल्यास सर्व पोझिशन्स ऑटो एक्झिट
            </div>
            <div class="rule-item">
                <strong><i class="fas fa-clock"></i> नियम 2:</strong> ट्रेडिंग वेळ: सकाळी 9:25 ते दुपारी 3:00
            </div>
            <div class="rule-item">
                <strong><i class="fas fa-chart-bar"></i> नियम 3:</strong> दिवसात फक्त 10 ट्रेड्स
            </div>
        </div>
    </div>
    
    <script>
        // मॉनिटरिंग सुरू
        function startMonitoring() {
            fetch('/api/start', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }
        
        // मॉनिटरिंग थांबवा
        function stopMonitoring() {
            fetch('/api/stop', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }
        
        // सर्व पोझिशन्स बंद
        function exitAllPositions() {
            if(confirm('सर्व पोझिशन्स बंद करायच्या?')) {
                fetch('/api/exit_all', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        alert(data.message);
                        location.reload();
                    });
            }
        }
        
        // बॅलन्स रिफ्रेश
        function refreshBalance() {
            fetch('/api/refresh_balance', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }
        
        // ट्रेड जोडा
        function addTrade() {
            fetch('/api/add_trade', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert('ट्रेड जोडला: ' + data.daily_trades + '/' + data.max_trades);
                    location.reload();
                });
        }
        
        // दिवस रिसेट
        function resetDaily() {
            if(confirm('दिवसाचा काउंटर रिसेट करायचा?')) {
                fetch('/api/reset_daily', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        alert(data.message);
                        location.reload();
                    });
            }
        }
        
        // ऑटो रिफ्रेश (प्रत्येक 60 सेकंदांनी)
        setInterval(() => {
            location.reload();
        }, 60000);
    </script>
</body>
</html>
'''

# ============ API रूट्स ============
@app.route('/')
def home():
    """मुख्य डॅशबोर्ड"""
    # बॅलन्स रिफ्रेश
    dhan_manager.refresh_balance()
    
    # P&L कॅल्क्युलेट
    total_loss, loss_percentage = dhan_manager.calculate_pnl()
    
    # नियम तपासा
    violations = dhan_manager.check_rules()
    
    data = {
        "connected": dhan_manager.connected,
        "blocked": dhan_manager.blocked,
        "block_reason": dhan_manager.block_reason,
        "current_balance": dhan_manager.current_balance,
        "total_loss": total_loss,
        "loss_percentage": round(loss_percentage, 1),
        "exposure": round((total_loss / dhan_manager.initial_capital) * 100, 1) if dhan_manager.initial_capital > 0 else 0,
        "daily_trades": dhan_manager.daily_trades,
        "max_trades": MAX_DAILY_TRADES,
        "remaining_trades": MAX_DAILY_TRADES - dhan_manager.daily_trades,
        "positions_count": len(dhan_manager.positions),
        "monitoring_active": dhan_manager.monitoring,
        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "violations": violations
    }
    
    return render_template_string(HTML_TEMPLATE, data=data)

@app.route('/api/start', methods=['POST'])
def api_start():
    """मॉनिटरिंग सुरू करा"""
    if not dhan_manager.connected:
        return jsonify({
            "status": "error",
            "message": "धन API कनेक्ट नाही"
        }), 400
    
    dhan_manager.start_monitoring()
    return jsonify({
        "status": "success",
        "message": "मॉनिटरिंग सुरू केले",
        "check_interval": "प्रत्येक 30 सेकंदांनी"
    })

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """मॉनिटरिंग थांबवा"""
    dhan_manager.stop_monitoring()
    return jsonify({
        "status": "success",
        "message": "मॉनिटरिंग थांबवले"
    })

@app.route('/api/exit_all', methods=['POST'])
def api_exit_all():
    """सर्व पोझिशन्स बंद करा"""
    if not dhan_manager.connected:
        return jsonify({
            "status": "error",
            "message": "धन API कनेक्ट नाही"
        }), 400
    
    success = dhan_manager.exit_all_positions()
    
    return jsonify({
        "status": "success" if success else "error",
        "message": "सर्व पोझिशन्स बंद करण्याची कमांड दिली" if success else "त्रुटी झाली"
    })

@app.route('/api/refresh_balance', methods=['POST'])
def api_refresh_balance():
    """बॅलन्स रिफ्रेश करा"""
    success = dhan_manager.refresh_balance()
    
    return jsonify({
        "status": "success" if success else "error",
        "message": "बॅलन्स रिफ्रेश केला" if success else "बॅलन्स रिफ्रेश अयशस्वी",
        "current_balance": dhan_manager.current_balance
    })

@app.route('/api/add_trade', methods=['POST'])
def api_add_trade():
    """ट्रेड जोडा"""
    dhan_manager.daily_trades += 1
    
    # 10 ट्रेड्स झाल्यास ब्लॉक
    if dhan_manager.daily_trades >= MAX_DAILY_TRADES:
        dhan_manager.blocked = True
        dhan_manager.block_reason = f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या"
    
    return jsonify({
        "status": "success",
        "daily_trades": dhan_manager.daily_trades,
        "max_trades": MAX_DAILY_TRADES,
        "remaining_trades": MAX_DAILY_TRADES - dhan_manager.daily_trades,
        "blocked": dhan_manager.blocked
    })

@app.route('/api/reset_daily', methods=['POST'])
def api_reset_daily():
    """दिवसाचा काउंटर रिसेट करा"""
    dhan_manager.daily_trades = 0
    dhan_manager.blocked = False
    dhan_manager.block_reason = ""
    
    return jsonify({
        "status": "success",
        "message": "दिवसाचा काउंटर रिसेट केला",
        "daily_trades": 0
    })

@app.route('/api/status', methods=['GET'])
def api_status():
    """स्टेटस मिळवा"""
    violations = dhan_manager.check_rules()
    total_loss, loss_percentage = dhan_manager.calculate_pnl()
    
    return jsonify({
        "connected": dhan_manager.connected,
        "monitoring_active": dhan_manager.monitoring,
        "blocked": dhan_manager.blocked,
        "block_reason": dhan_manager.block_reason,
        "daily_trades": dhan_manager.daily_trades,
        "remaining_trades": MAX_DAILY_TRADES - dhan_manager.daily_trades,
        "current_balance": dhan_manager.current_balance,
        "initial_capital": dhan_manager.initial_capital,
        "total_loss": total_loss,
        "loss_percentage": f"{loss_percentage:.1f}%",
        "positions_count": len(dhan_manager.positions),
        "violations": violations,
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/api/positions', methods=['GET'])
def api_positions():
    """वर्तमान पोझिशन्स"""
    positions = dhan_manager.get_positions()
    
    return jsonify({
        "status": "success",
        "positions": positions,
        "count": len(positions),
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health():
    """हेल्थ चेक"""
    return jsonify({
        "status": "healthy",
        "app": "धन डिमॅट रिस्क मॅनेजर",
        "dhan_connected": dhan_manager.connected,
        "monitoring_active": dhan_manager.monitoring,
        "timestamp": datetime.datetime.now().isoformat()
    })

# ============ सर्व्हर स्टार्ट ============
if __name__ == '__main__':
    logger.info("🚀 धन डिमॅट रिस्क मॅनेजर सुरू करत आहे...")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
