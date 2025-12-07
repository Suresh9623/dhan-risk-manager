"""
धन ऑटो रिस्क मॅनेजर
तुम्ही मोबाईलवर ट्रेड करा, आम्ही बॅकग्राऊंडमध्ये मॉनिटर करू
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

# धन API
try:
    from dhanhq import dhanhq
    DHAN_AVAILABLE = True
    logger.info("✅ धन API उपलब्ध")
except ImportError:
    DHAN_AVAILABLE = False
    logger.error("❌ धन API पॅकेज नाही")

# ============ कॉन्फिगरेशन ============
TRADING_START_TIME = datetime.time(9, 25)  # सकाळी 9:25
TRADING_END_TIME = datetime.time(15, 0)    # दुपारी 3:00
MAX_DAILY_TRADES = 10
MAX_LOSS_PERCENTAGE = 20
CHECK_INTERVAL = 10  # सेकंद (प्रत्येक 10 सेकंदांनी तपास)

# ============ स्टेट मॅनेजमेंट ============
class AutoRiskManager:
    def __init__(self):
        self.dhan_client = None
        self.dhan_connected = False
        self.running = False
        self.last_check = None
        self.last_balance = 0
        self.initial_capital = 0
        self.current_loss = 0
        self.daily_trades = 0
        self.blocked = False
        self.block_reason = ""
        
        # धन API कनेक्शन
        self.init_dhan_client()
        
        logger.info("🤖 ऑटो रिस्क मॅनेजर सुरू")
        logger.info(f"📈 ट्रेडिंग वेळ: {TRADING_START_TIME} ते {TRADING_END_TIME}")
        logger.info(f"🎯 कमाल ट्रेड्स/दिवस: {MAX_DAILY_TRADES}")
        logger.info(f"⚠️ कमाल तोटा: {MAX_LOSS_PERCENTAGE}%")
    
    def init_dhan_client(self):
        """धन API कनेक्शन"""
        if not DHAN_AVAILABLE:
            return
            
        client_id = os.environ.get('DHAN_CLIENT_ID')
        access_token = os.environ.get('DHAN_ACCESS_TOKEN')
        
        if client_id and access_token:
            try:
                self.dhan_client = dhanhq(client_id, access_token)
                self.dhan_connected = True
                
                # प्रारंभिक बॅलन्स सेट करा
                balance = self.get_current_balance()
                if balance:
                    self.initial_capital = balance
                    self.last_balance = balance
                
                logger.info(f"✅ धन API कनेक्टेड. बॅलन्स: ₹{self.initial_capital}")
            except Exception as e:
                logger.error(f"❌ धन कनेक्शन त्रुटी: {e}")
        else:
            logger.warning("⚠️ DHAN_CLIENT_ID किंवा DHAN_ACCESS_TOKEN सेट नाही")
    
    def get_current_balance(self):
        """वर्तमान बॅलन्स"""
        if not self.dhan_client:
            return 0
            
        try:
            funds = self.dhan_client.get_fund_limits()
            if isinstance(funds, dict):
                return funds.get('availableBalance', 0)
            elif isinstance(funds, list) and len(funds) > 0:
                return funds[0].get('availableBalance', 0)
        except:
            pass
        return 0
    
    def get_positions(self):
        """वर्तमान पोझिशन्स"""
        if not self.dhan_client:
            return []
            
        try:
            positions = self.dhan_client.get_positions()
            return positions if positions else []
        except:
            return []
    
    def calculate_current_pnl(self):
        """वर्तमान P&L काढा"""
        positions = self.get_positions()
        total_pnl = 0
        
        for pos in positions:
            pnl = pos.get('pnl', 0) or pos.get('netReturns', 0)
            total_pnl += pnl
        
        # बॅलन्समधूनही तोटा काढा
        current_balance = self.get_current_balance()
        balance_loss = self.last_balance - current_balance
        
        total_loss = abs(total_pnl) + max(0, balance_loss)
        
        # तोटा टक्के
        if self.initial_capital > 0:
            loss_percentage = (total_loss / self.initial_capital) * 100
        else:
            loss_percentage = 0
        
        return total_loss, loss_percentage
    
    def exit_all_positions(self):
        """सर्व पोझिशन्स बंद करा"""
        if not self.dhan_client:
            return False
            
        try:
            positions = self.get_positions()
            if not positions:
                return True
                
            for position in positions:
                if position.get('quantity', 0) > 0:
                    self.dhan_client.place_order(
                        security_id=position.get('securityId'),
                        exchange_segment=position.get('exchangeSegment', 'NSE_EQ'),
                        transaction_type="SELL",
                        quantity=position.get('quantity'),
                        order_type="MARKET",
                        product_type=position.get('productType', 'INTRADAY')
                    )
            
            logger.warning("🚨 सर्व पोझिशन्स ऑटो एक्झिट केल्या")
            return True
        except Exception as e:
            logger.error(f"❌ पोझिशन्स एक्झिट त्रुटी: {e}")
            return False
    
    def check_rules(self):
        """सर्व नियम तपासा"""
        violations = []
        
        # 1. ट्रेडिंग वेळ तपासा
        current_time = datetime.datetime.now().time()
        if not (TRADING_START_TIME <= current_time <= TRADING_END_TIME):
            if current_time > TRADING_END_TIME:
                violations.append(("time", "ट्रेडिंग वेळ संपली (3:00 PM)"))
                # 3 PM नंतर ऑटो एक्झिट
                self.exit_all_positions()
            else:
                violations.append(("time", "ट्रेडिंग वेळ सुरू नाही (9:25 AM)"))
        
        # 2. 20% तोटा तपासा
        current_loss, loss_percentage = self.calculate_current_pnl()
        
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            violations.append(("loss", f"20% तोटा झाला ({loss_percentage:.1f}%)"))
            # ऑटो एक्झिट
            self.exit_all_positions()
            self.blocked = True
            self.block_reason = "20% तोटा झाला"
        
        # 3. दिवसाची ट्रेड मर्यादा
        if self.daily_trades >= MAX_DAILY_TRADES:
            violations.append(("trades", f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या"))
            self.blocked = True
            self.block_reason = f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या"
        
        return violations
    
    def should_block_trades(self):
        """ट्रेड्स ब्लॉक करायचे का?"""
        violations = self.check_rules()
        return len(violations) > 0, violations
    
    def start_monitoring(self):
        """मॉनिटरिंग सुरू करा"""
        if self.running:
            return
            
        self.running = True
        logger.info("🔍 ऑटो मॉनिटरिंग सुरू केले")
        
        def monitor_loop():
            while self.running:
                try:
                    # नियम तपासा
                    should_block, violations = self.should_block_trades()
                    
                    if should_block:
                        for rule, message in violations:
                            logger.warning(f"⚠️ नियम उल्लंघन: {message}")
                    
                    # बॅलन्स अपडेट
                    current_balance = self.get_current_balance()
                    if current_balance != self.last_balance:
                        self.last_balance = current_balance
                    
                    time.sleep(CHECK_INTERVAL)
                    
                except Exception as e:
                    logger.error(f"❌ मॉनिटरिंग त्रुटी: {e}")
                    time.sleep(30)
        
        # मॉनिटरिंग थ्रेड सुरू
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """मॉनिटरिंग थांबवा"""
        self.running = False
        logger.info("⏸️ ऑटो मॉनिटरिंग थांबवले")

# ग्लोबल इंस्टन्स
risk_manager = AutoRiskManager()

# ============ मोबाईल HTML टेम्पलेट ============
MOBILE_HTML = '''
<!DOCTYPE html>
<html lang="mr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>मोबाईल रिस्क मॉनिटर</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Arial', sans-serif; }
        body { background: #f5f5f5; padding: 10px; }
        
        .container { max-width: 100%; }
        
        .header {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 15px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 1.5em;
            margin-bottom: 5px;
        }
        
        .status-circle {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            margin: 15px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2em;
            font-weight: bold;
        }
        
        .status-green { background: #28a745; color: white; }
        .status-red { background: #dc3545; color: white; }
        .status-yellow { background: #ffc107; color: black; }
        
        .card {
            background: white;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        
        .card h3 {
            color: #333;
            margin-bottom: 10px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 5px;
        }
        
        .info-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        
        .info-label { color: #666; }
        .info-value { font-weight: bold; }
        
        .warning { color: #dc3545; }
        .safe { color: #28a745; }
        .caution { color: #ffc107; }
        
        .button-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 15px;
        }
        
        .btn {
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            font-size: 1em;
            cursor: pointer;
            text-align: center;
        }
        
        .btn-primary { background: #667eea; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-warning { background: #ffc107; color: black; }
        
        .alert {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-weight: bold;
        }
        
        .alert-danger { background: #f8d7da; color: #721c24; border-left: 4px solid #dc3545; }
        .alert-success { background: #d4edda; color: #155724; border-left: 4px solid #28a745; }
        .alert-warning { background: #fff3cd; color: #856404; border-left: 4px solid #ffc107; }
        
        .rule-item {
            background: #f8f9fa;
            padding: 10px;
            margin-bottom: 8px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        @media (max-width: 768px) {
            .button-group {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📱 मोबाईल रिस्क मॉनिटर</h1>
            <p>तुम्ही ट्रेड करा, आम्ही संरक्षण द्या</p>
        </div>
        
        <!-- स्टेटस सर्कल -->
        <div class="card">
            <div class="status-circle {% if data.safe_to_trade %}status-green{% elif data.caution %}status-yellow{% else %}status-red{% endif %}">
                {% if data.safe_to_trade %}✅{% elif data.caution %}⚠️{% else %}❌{% endif %}
            </div>
            <h3 style="text-align: center;">
                {% if data.safe_to_trade %}ट्रेडिंग सुरू{% elif data.caution %}सावधान{% else %}ट्रेडिंग बंद{% endif %}
            </h3>
        </div>
        
        <!-- अलर्ट मेसेज -->
        {% if data.block_reason %}
        <div class="alert alert-danger">
            ⚠️ {{ data.block_reason }}
        </div>
        {% endif %}
        
        <!-- मुख्य माहिती -->
        <div class="card">
            <h3>📊 सध्याची स्थिती</h3>
            <div class="info-item">
                <span class="info-label">तोटा:</span>
                <span class="info-value {% if data.loss_percentage >= 10 %}warning{% else %}safe{% endif %}">
                    {{ data.loss_percentage }}%
                </span>
            </div>
            <div class="info-item">
                <span class="info-label">ट्रेड काउंट:</span>
                <span class="info-value {% if data.daily_trades >= 8 %}warning{% else %}safe{% endif %}">
                    {{ data.daily_trades }}/{{ data.max_trades }}
                </span>
            </div>
            <div class="info-item">
                <span class="info-label">बॅलन्स:</span>
                <span class="info-value">₹{{ data.current_balance }}</span>
            </div>
            <div class="info-item">
                <span class="info-label">वेळ:</span>
                <span class="info-value">{{ data.current_time }}</span>
            </div>
            <div class="info-item">
                <span class="info-label">मॉनिटरिंग:</span>
                <span class="info-value {% if data.monitoring_active %}safe{% else %}warning{% endif %}">
                    {% if data.monitoring_active %}सक्रिय{% else %}निष्क्रिय{% endif %}
                </span>
            </div>
        </div>
        
        <!-- नियम -->
        <div class="card">
            <h3>📋 मुख्य नियम</h3>
            <div class="rule-item">
                <strong>नियम 1:</strong> 20% तोटा → ऑटो एक्झिट
            </div>
            <div class="rule-item">
                <strong>नियम 2:</strong> 9:25 AM ते 3:00 PM → फक्त ट्रेडिंग
            </div>
            <div class="rule-item">
                <strong>नियम 3:</strong> 10 ट्रेड्स/दिवस → नंतर ब्लॉक
            </div>
        </div>
        
        <!-- कंट्रोल बटण्स -->
        <div class="button-group">
            <button class="btn btn-danger" onclick="exitAll()">
                🚨 सर्व बंद
            </button>
            <button class="btn btn-warning" onclick="checkNow()">
                🔍 तपासा
            </button>
            <button class="btn btn-success" onclick="addTrade()">
                📈 ट्रेड जोडा
            </button>
            <button class="btn btn-primary" onclick="refreshData()">
                🔄 रिफ्रेश
            </button>
        </div>
    </div>
    
    <script>
        // सर्व ट्रेड्स बंद
        function exitAll() {
            if(confirm('सर्व ट्रेड्स बंद करायच्या?')) {
                fetch('/exit_all', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        alert(data.message);
                        refreshData();
                    });
            }
        }
        
        // तात्काळ तपास
        function checkNow() {
            fetch('/check_now')
                .then(response => response.json())
                .then(data => {
                    if(data.should_block) {
                        alert('⚠️ नियम उल्लंघन: ' + data.violations.map(v => v[1]).join(', '));
                    } else {
                        alert('✅ सर्व नियम पाळले जात आहेत');
                    }
                    refreshData();
                });
        }
        
        // ट्रेड काउंट वाढवा
        function addTrade() {
            fetch('/update_trade_count', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count: {{ data.daily_trades }} + 1 })
            })
            .then(response => response.json())
            .then(data => {
                alert('✅ ट्रेड जोडला: ' + data.daily_trades + '/' + data.max_trades);
                refreshData();
            });
        }
        
        // डेटा रिफ्रेश
        function refreshData() {
            location.reload();
        }
        
        // ऑटो रिफ्रेश (प्रत्येक 30 सेकंदांनी)
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
'''

# ============ API रूट्स ============
@app.route('/')
def home():
    """मुख्य पृष्ठ"""
    return jsonify({
        "app": "धन ऑटो रिस्क मॅनेजर",
        "status": "सक्रिय" if risk_manager.running else "निष्क्रिय",
        "description": "तुम्ही मोबाईलवर ट्रेड करा, आम्ही बॅकग्राऊंडमध्ये मॉनिटर करू",
        "rules": [
            f"20% तोटा झाला की सर्व ट्रेड्स ऑटो एक्झिट",
            f"ट्रेड वेळ: {TRADING_START_TIME} ते {TRADING_END_TIME}",
            f"दिवसात फक्त {MAX_DAILY_TRADES} ट्रेड्स"
        ],
        "monitoring_active": risk_manager.running,
        "dhan_connected": risk_manager.dhan_connected,
        "endpoints": {
            "/mobile": "मोबाईल डॅशबोर्ड",
            "/status": "स्टेटस",
            "/start": "मॉनिटरिंग सुरू",
            "/stop": "मॉनिटरिंग थांबवा",
            "/exit_all": "सर्व ट्रेड्स बंद"
        }
    })

@app.route('/mobile')
def mobile_dashboard():
    """मोबाईल डॅशबोर्ड"""
    should_block, violations = risk_manager.should_block_trades()
    current_loss, loss_percentage = risk_manager.calculate_current_pnl()
    
    # ट्रेडिंग वेळ
    current_time = datetime.datetime.now().time()
    trading_hours_active = TRADING_START_TIME <= current_time <= TRADING_END_TIME
    
    # स्टेटस निश्चित करा
    safe_to_trade = not should_block and trading_hours_active
    caution = not safe_to_trade and not risk_manager.blocked
    
    data = {
        "safe_to_trade": safe_to_trade,
        "caution": caution,
        "block_reason": risk_manager.block_reason,
        "loss_percentage": round(loss_percentage, 1),
        "daily_trades": risk_manager.daily_trades,
        "max_trades": MAX_DAILY_TRADES,
        "current_balance": risk_manager.get_current_balance(),
        "current_time": datetime.datetime.now().strftime("%H:%M:%S"),
        "monitoring_active": risk_manager.running,
        "trading_hours_active": trading_hours_active
    }
    
    return render_template_string(MOBILE_HTML, data=data)

@app.route('/start', methods=['POST'])
def start_monitoring():
    """मॉनिटरिंग सुरू करा"""
    risk_manager.start_monitoring()
    
    return jsonify({
        "status": "success",
        "message": "ऑटो मॉनिटरिंग सुरू केले",
        "check_interval": f"प्रत्येक {CHECK_INTERVAL} सेकंदांनी"
    })

@app.route('/stop', methods=['POST'])
def stop_monitoring():
    """मॉनिटरिंग थांबवा"""
    risk_manager.stop_monitoring()
    
    return jsonify({
        "status": "success",
        "message": "ऑटो मॉनिटरिंग थांबवले"
    })

@app.route('/status', methods=['GET'])
def get_status():
    """सध्याची स्थिती"""
    should_block, violations = risk_manager.should_block_trades()
    current_loss, loss_percentage = risk_manager.calculate_current_pnl()
    
    # ट्रेडिंग वेळ
    current_time = datetime.datetime.now().time()
    trading_hours_active = TRADING_START_TIME <= current_time <= TRADING_END_TIME
    
    return jsonify({
        "monitoring_active": risk_manager.running,
        "should_block_trades": should_block,
        "violations": violations,
        "current_loss": current_loss,
        "loss_percentage": f"{loss_percentage:.2f}%",
        "max_loss_allowed": f"{MAX_LOSS_PERCENTAGE}%",
        "trading_hours_active": trading_hours_active,
        "dhan_connected": risk_manager.dhan_connected,
        "current_balance": risk_manager.get_current_balance(),
        "initial_capital": risk_manager.initial_capital,
        "blocked": risk_manager.blocked,
        "block_reason": risk_manager.block_reason,
        "daily_trades": risk_manager.daily_trades,
        "remaining_trades": MAX_DAILY_TRADES - risk_manager.daily_trades,
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/check_now', methods=['GET'])
def check_now():
    """तात्काळ तपासा"""
    should_block, violations = risk_manager.check_rules()
    
    if should_block:
        # तात्काळ एक्झिट करा
        risk_manager.exit_all_positions()
    
    return jsonify({
        "status": "checked",
        "should_block": should_block,
        "violations": violations,
        "action_taken": "exited_all_positions" if should_block else "none",
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/exit_all', methods=['POST'])
def exit_all():
    """सर्व ट्रेड्स बंद करा"""
    success = risk_manager.exit_all_positions()
    
    return jsonify({
        "status": "success" if success else "error",
        "message": "सर्व ट्रेड्स बंद करण्याची कमांड दिली" if success else "त्रुटी झाली",
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/update_trade_count', methods=['POST'])
def update_trade_count():
    """ट्रेड काउंट अपडेट करा (तुम्ही मॅन्युअल सेट कराल)"""
    try:
        data = request.get_json()
        trade_count = int(data.get('count', 0))
        
        risk_manager.daily_trades = trade_count
        
        # 10 ट्रेड्स झाल्यास ब्लॉक
        if trade_count >= MAX_DAILY_TRADES:
            risk_manager.blocked = True
            risk_manager.block_reason = f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या"
        
        return jsonify({
            "status": "success",
            "daily_trades": risk_manager.daily_trades,
            "remaining_trades": MAX_DAILY_TRADES - risk_manager.daily_trades,
            "blocked": risk_manager.blocked,
            "block_reason": risk_manager.block_reason
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/reset_daily', methods=['POST'])
def reset_daily():
    """दिवसाचा काउंटर रिसेट करा"""
    risk_manager.daily_trades = 0
    risk_manager.blocked = False
    risk_manager.block_reason = ""
    
    return jsonify({
        "status": "success",
        "message": "दिवसाचा काउंटर रिसेट केला",
        "daily_trades": 0
    })

@app.route('/get_positions', methods=['GET'])
def get_positions():
    """वर्तमान पोझिशन्स"""
    positions = risk_manager.get_positions()
    
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
        "monitoring": risk_manager.running,
        "dhan_connected": risk_manager.dhan_connected,
        "check_interval_seconds": CHECK_INTERVAL,
        "timestamp": datetime.datetime.now().isoformat()
    })

# ============ सर्व्हर स्टार्ट ============
if __name__ == '__main__':
    logger.info("🚀 धन ऑटो रिस्क मॅनेजर सुरू करत आहे...")
    
    # ऑटोमॅटिक स्टार्ट मॉनिटरिंग
    risk_manager.start_monitoring()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
