"""
मोबाईल फ्रेंडली डॅशबोर्ड
तुम्ही मोबाईलवरून सहज मॉनिटर करू शकता
"""

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
            <div class="status-circle {{ 'status-green' if data.safe_to_trade else ('status-yellow' if data.caution else 'status-red') }}">
                {{ '✅' if data.safe_to_trade else ('⚠️' if data.caution else '❌') }}
            </div>
            <h3 style="text-align: center;">
                {{ 'ट्रेडिंग सुरू' if data.safe_to_trade else ('सावधान' if data.caution else 'ट्रेडिंग बंद') }}
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
                <span class="info-value {{ 'warning' if data.loss_percentage >= 10 else 'safe' }}">
                    {{ data.loss_percentage }}%
                </span>
            </div>
            <div class="info-item">
                <span class="info-label">ट्रेड काउंट:</span>
                <span class="info-value {{ 'warning' if data.daily_trades >= 8 else 'safe' }}">
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
                <span class="info-value {{ 'safe' if data.monitoring_active else 'warning' }}">
                    {{ 'सक्रिय' if data.monitoring_active else 'निष्क्रिय' }}
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
