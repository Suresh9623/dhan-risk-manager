"""
धन ऑटो रिस्क मॅनेजर - सोपी आवृत्ती
तुम्ही मोबाईलवर ट्रेड करा, आम्ही बॅकग्राऊंडमध्ये मॉनिटर करू
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

# ============ कॉन्फिगरेशन ============
TRADING_START_TIME = datetime.time(9, 25)  # सकाळी 9:25
TRADING_END_TIME = datetime.time(15, 0)    # दुपारी 3:00
MAX_DAILY_TRADES = 10
MAX_LOSS_PERCENTAGE = 20

# ============ स्टेट मॅनेजमेंट ============
class RiskManager:
    def __init__(self):
        self.daily_trades = 0
        self.initial_capital = 100000
        self.current_balance = 100000
        self.current_loss = 0
        self.running = False
        self.blocked = False
        self.block_reason = ""
        self.last_update = datetime.datetime.now()
        
        logger.info("🤖 रिस्क मॅनेजर सुरू")
        logger.info(f"📈 ट्रेडिंग वेळ: {TRADING_START_TIME} ते {TRADING_END_TIME}")
        logger.info(f"🎯 कमाल ट्रेड्स/दिवस: {MAX_DAILY_TRADES}")
        logger.info(f"⚠️ कमाल तोटा: {MAX_LOSS_PERCENTAGE}%")
    
    def check_rules(self):
        """सर्व नियम तपासा"""
        violations = []
        
        # 1. ट्रेडिंग वेळ तपासा
        current_time = datetime.datetime.now().time()
        if not (TRADING_START_TIME <= current_time <= TRADING_END_TIME):
            if current_time > TRADING_END_TIME:
                violations.append("ट्रेडिंग वेळ संपली (3:00 PM)")
                self.blocked = True
                self.block_reason = "3:00 PM नंतर ट्रेडिंग बंद"
            else:
                violations.append("ट्रेडिंग वेळ सुरू नाही (9:25 AM)")
        
        # 2. 20% तोटा तपासा
        loss_percentage = (self.current_loss / self.initial_capital) * 100
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            violations.append(f"20% तोटा झाला ({loss_percentage:.1f}%)")
            self.blocked = True
            self.block_reason = "20% तोटा झाला"
        
        # 3. दिवसाची ट्रेड मर्यादा
        if self.daily_trades >= MAX_DAILY_TRADES:
            violations.append(f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या")
            self.blocked = True
            self.block_reason = f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या"
        
        return violations
    
    def should_block_trades(self):
        """ट्रेड्स ब्लॉक करायचे का?"""
        violations = self.check_rules()
        return len(violations) > 0, violations
    
    def start_monitoring(self):
        """मॉनिटरिंग सुरू करा"""
        self.running = True
        logger.info("🔍 मॉनिटरिंग सुरू केले")
    
    def stop_monitoring(self):
        """मॉनिटरिंग थांबवा"""
        self.running = False
        logger.info("⏸️ मॉनिटरिंग थांबवले")

# ग्लोबल इंस्टन्स
risk_manager = RiskManager()

# ============ HTML टेम्पलेट ============
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="mr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>धन रिस्क मॅनेजर</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 500px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
        }
        .status {
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            text-align: center;
            font-weight: bold;
        }
        .status-active {
            background: #d4edda;
            color: #155724;
        }
        .status-blocked {
            background: #f8d7da;
            color: #721c24;
        }
        .info-grid {
            margin: 20px 0;
        }
        .info-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }
        .controls {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 20px 0;
        }
        button {
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-weight: bold;
            cursor: pointer;
        }
        .btn-start { background: #28a745; color: white; }
        .btn-stop { background: #dc3545; color: white; }
        .btn-add { background: #007bff; color: white; }
        .btn-exit { background: #ffc107; color: black; }
        .rules {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📱 धन रिस्क मॅनेजर</h1>
        
        <div class="status {% if data.blocked %}status-blocked{% else %}status-active{% endif %}">
            {% if data.blocked %}
                ❌ {{ data.block_reason }}
            {% else %}
                ✅ ट्रेडिंग परवानगी आहे
            {% endif %}
        </div>
        
        <div class="info-grid">
            <div class="info-item">
                <span>ट्रेड काउंट:</span>
                <strong>{{ data.daily_trades }}/{{ data.max_trades }}</strong>
            </div>
            <div class="info-item">
                <span>तोटा:</span>
                <strong>{{ data.loss_percentage }}%</strong>
            </div>
            <div class="info-item">
                <span>बॅलन्स:</span>
                <strong>₹{{ data.current_balance }}</strong>
            </div>
            <div class="info-item">
                <span>मॉनिटरिंग:</span>
                <strong>{{ 'सक्रिय' if data.monitoring_active else 'निष्क्रिय' }}</strong>
            </div>
            <div class="info-item">
                <span>वेळ:</span>
                <strong>{{ data.current_time }}</strong>
            </div>
        </div>
        
        <div class="controls">
            <button class="btn-start" onclick="startMonitoring()">▶️ सुरू करा</button>
            <button class="btn-stop" onclick="stopMonitoring()">⏸️ थांबवा</button>
            <button class="btn-add" onclick="addTrade()">📈 ट्रेड जोडा</button>
            <button class="btn-exit" onclick="resetDaily()">🔄 दिवस रिसेट</button>
        </div>
        
        <div class="rules">
            <h3>📋 मुख्य नियम</h3>
            <p>1. 20% तोटा → ऑटो एक्झिट</p>
            <p>2. 9:25 AM ते 3:00 PM → फक्त ट्रेडिंग</p>
            <p>3. 10 ट्रेड्स/दिवस → नंतर ब्लॉक</p>
        </div>
    </div>
    
    <script>
        function startMonitoring() {
            fetch('/api/start', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }
        
        function stopMonitoring() {
            fetch('/api/stop', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }
        
        function addTrade() {
            fetch('/api/add_trade', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert('ट्रेड जोडला: ' + data.daily_trades + '/' + data.max_trades);
                    location.reload();
                });
        }
        
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
        
        // ऑटो रिफ्रेश (प्रत्येक 30 सेकंदांनी)
        setInterval(() => {
            location.reload();
        }, 30000);
    </script>
</body>
</html>
'''

# ============ API रूट्स ============
@app.route('/')
def home():
    """मुख्य पृष्ठ"""
    should_block, violations = risk_manager.should_block_trades()
    loss_percentage = (risk_manager.current_loss / risk_manager.initial_capital) * 100
    
    data = {
        "blocked": risk_manager.blocked,
        "block_reason": risk_manager.block_reason,
        "daily_trades": risk_manager.daily_trades,
        "max_trades": MAX_DAILY_TRADES,
        "loss_percentage": round(loss_percentage, 1),
        "current_balance": risk_manager.current_balance,
        "monitoring_active": risk_manager.running,
        "current_time": datetime.datetime.now().strftime("%H:%M:%S")
    }
    
    return render_template_string(HTML_TEMPLATE, data=data)

@app.route('/api/start', methods=['POST'])
def api_start():
    """मॉनिटरिंग सुरू करा"""
    risk_manager.start_monitoring()
    return jsonify({
        "status": "success",
        "message": "मॉनिटरिंग सुरू केले"
    })

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """मॉनिटरिंग थांबवा"""
    risk_manager.stop_monitoring()
    return jsonify({
        "status": "success",
        "message": "मॉनिटरिंग थांबवले"
    })

@app.route('/api/add_trade', methods=['POST'])
def api_add_trade():
    """ट्रेड जोडा"""
    risk_manager.daily_trades += 1
    
    # 10 ट्रेड्स झाल्यास ब्लॉक
    if risk_manager.daily_trades >= MAX_DAILY_TRADES:
        risk_manager.blocked = True
        risk_manager.block_reason = f"{MAX_DAILY_TRADES} ट्रेड्स झाल्या"
    
    return jsonify({
        "status": "success",
        "daily_trades": risk_manager.daily_trades,
        "max_trades": MAX_DAILY_TRADES,
        "blocked": risk_manager.blocked
    })

@app.route('/api/reset_daily', methods=['POST'])
def api_reset_daily():
    """दिवसाचा काउंटर रिसेट करा"""
    risk_manager.daily_trades = 0
    risk_manager.blocked = False
    risk_manager.block_reason = ""
    
    return jsonify({
        "status": "success",
        "message": "दिवसाचा काउंटर रिसेट केला",
        "daily_trades": 0
    })

@app.route('/api/update_loss', methods=['POST'])
def api_update_loss():
    """तोटा अपडेट करा"""
    try:
        data = request.get_json()
        loss = float(data.get('loss', 0))
        
        risk_manager.current_loss = loss
        
        # 20% तोटा तपासा
        loss_percentage = (loss / risk_manager.initial_capital) * 100
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            risk_manager.blocked = True
            risk_manager.block_reason = "20% तोटा झाला"
        
        return jsonify({
            "status": "success",
            "loss": loss,
            "loss_percentage": f"{loss_percentage:.1f}%",
            "blocked": risk_manager.blocked
        })
    except:
        return jsonify({"error": "Invalid data"}), 400

@app.route('/api/status', methods=['GET'])
def api_status():
    """स्टेटस मिळवा"""
    should_block, violations = risk_manager.should_block_trades()
    loss_percentage = (risk_manager.current_loss / risk_manager.initial_capital) * 100
    
    return jsonify({
        "monitoring_active": risk_manager.running,
        "blocked": risk_manager.blocked,
        "block_reason": risk_manager.block_reason,
        "daily_trades": risk_manager.daily_trades,
        "remaining_trades": MAX_DAILY_TRADES - risk_manager.daily_trades,
        "loss_percentage": f"{loss_percentage:.1f}%",
        "current_balance": risk_manager.current_balance,
        "violations": violations,
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health():
    """हेल्थ चेक"""
    return jsonify({
        "status": "healthy",
        "app": "धन रिस्क मॅनेजर",
        "version": "1.0",
        "timestamp": datetime.datetime.now().isoformat()
    })

# ============ सर्व्हर स्टार्ट ============
if __name__ == '__main__':
    logger.info("🚀 धन रिस्क मॅनेजर सुरू करत आहे...")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
