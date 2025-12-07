"""
धन रिस्क मॅनेजर - मराठी
संपूर्ण रिस्क मॅनेजमेंट सिस्टम

नियम:
1. 20% तोटा झाला की सर्व ट्रेड्स ऑटो एक्झिट
2. ट्रेड वेळ: सकाळी 9:25 ते दुपारी 3:00  
3. दिवसात फक्त 10 ट्रेड्स
4. बॅलन्स ऑटो फेच
"""

import os
import datetime
import time
import threading
import json
from flask import Flask, jsonify, request, render_template_string
import logging
from functools import wraps

# सेटअप लॉगिंग
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# धन API इंपोर्ट करण्याचा प्रयत्न
try:
    from dhanhq import dhanhq, marketfeed
    DHAN_AVAILABLE = True
    logger.info("✅ धन API उपलब्ध")
except ImportError:
    DHAN_AVAILABLE = False
    logger.warning("⚠️ धन API उपलब्ध नाही. mock डेटा वापरत आहे.")

# ============ कॉन्फिगरेशन ============
TRADING_START_TIME = datetime.time(9, 25)  # सकाळी 9:25
TRADING_END_TIME = datetime.time(15, 0)    # दुपारी 3:00
MAX_DAILY_TRADES = 10
MAX_LOSS_PERCENTAGE = 20
BALANCE_REFRESH_INTERVAL = 300  # 5 मिनिटांनी बॅलन्स रिफ्रेश

# ============ स्टेट मॅनेजमेंट ============
class TradingState:
    def __init__(self):
        self.daily_trade_count = 0
        self.total_capital = 100000  # डिफॉल्ट कॅपिटल
        self.current_loss = 0
        self.current_profit = 0
        self.trading_enabled = True
        self.last_reset_date = datetime.date.today()
        self.trade_history = []
        self.balance_data = None
        self.last_balance_update = None
        self.positions = []
        self.dhan_connection_status = "disconnected"
        
        # धन API क्लायंट
        self.dhan_client = None
        self.init_dhan_client()
        
        logger.info("📊 ट्रेडिंग स्टेट इनिशियलाइज्ड")
        logger.info(f"📈 ट्रेडिंग वेळ: {TRADING_START_TIME} ते {TRADING_END_TIME}")
        logger.info(f"🎯 मॅक्स डेली ट्रेड्स: {MAX_DAILY_TRADES}")
        logger.info(f"⚠️ मॅक्स लॉस: {MAX_LOSS_PERCENTAGE}%")
    
    def init_dhan_client(self):
        """धन API क्लायंट इनिशियलाइज करा"""
        if not DHAN_AVAILABLE:
            logger.warning("धन API पॅकेज इन्स्टॉल नाही")
            self.dhan_connection_status = "package_not_installed"
            return
            
        client_id = os.environ.get('DHAN_CLIENT_ID')
        access_token = os.environ.get('DHAN_ACCESS_TOKEN')
        
        if client_id and access_token:
            try:
                self.dhan_client = dhanhq(client_id, access_token)
                self.dhan_connection_status = "connected"
                logger.info(f"✅ धन API कनेक्शन स्थापित. Client ID: {client_id[:10]}...")
                
                # प्रथम बॅलन्स फेच करा
                self.fetch_balance()
                # पोझिशन्स फेच करा
                self.fetch_positions()
            except Exception as e:
                self.dhan_connection_status = f"error: {str(e)}"
                logger.error(f"❌ धन API कनेक्शन त्रुटी: {e}")
        else:
            self.dhan_connection_status = "credentials_missing"
            logger.warning("⚠️ धन API क्रेडेंशियल्स सेट नाहीत (DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN)")
    
    def fetch_balance(self):
        """वास्तविक बॅलन्स फेच करा"""
        if self.dhan_client:
            try:
                logger.info("🔄 बॅलन्स फेच करत आहे...")
                balance_response = self.dhan_client.get_fund_limits()
                
                if balance_response:
                    self.balance_data = balance_response
                    
                    # वेगवेगळे बॅलन्स फील्ड्स
                    if isinstance(balance_response, dict):
                        self.total_capital = balance_response.get('availableBalance', 100000)
                    elif isinstance(balance_response, list) and len(balance_response) > 0:
                        self.total_capital = balance_response[0].get('availableBalance', 100000)
                    
                    self.last_balance_update = datetime.datetime.now()
                    
                    logger.info(f"✅ बॅलन्स फेच यशस्वी: ₹{self.total_capital}")
                    return {
                        "status": "success",
                        "balance": self.total_capital,
                        "data": balance_response,
                        "timestamp": str(self.last_balance_update)
                    }
                else:
                    logger.warning("⚠️ बॅलन्स रिस्पॉन्स रिकामा")
                    return {"status": "error", "message": "Empty balance response"}
                    
            except Exception as e:
                logger.error(f"❌ बॅलन्स फेच त्रुटी: {e}")
                return {"status": "error", "message": str(e)}
        else:
            # Mock डेटा (चाचणीसाठी)
            return self.use_mock_balance()
    
    def use_mock_balance(self):
        """Mock बॅलन्स डेटा वापरा"""
        mock_balance = {
            "availableBalance": 100000,
            "utilizedAmount": 0,
            "collateralValue": 0,
            "span": 0,
            "exposure": 0,
            "totalMarginUsed": 0,
            "availableMargin": 100000,
            "currency": "INR"
        }
        self.balance_data = mock_balance
        self.total_capital = 100000
        self.last_balance_update = datetime.datetime.now()
        
        logger.info(f"🔄 Mock बॅलन्स वापरत आहे: ₹{self.total_capital}")
        
        return {
            "status": "mock",
            "balance": self.total_capital,
            "data": mock_balance,
            "timestamp": str(self.last_balance_update),
            "message": "Mock data - Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN for real data"
        }
    
    def fetch_positions(self):
        """वर्तमान पोझिशन्स फेच करा"""
        if self.dhan_client:
            try:
                positions_response = self.dhan_client.get_positions()
                if positions_response:
                    self.positions = positions_response
                    # P&L कॅल्क्युलेशन
                    self.calculate_pnl()
                    logger.info(f"✅ {len(self.positions)} पोझिशन्स फेच केली")
                return positions_response
            except Exception as e:
                logger.error(f"❌ पोझिशन्स फेच त्रुटी: {e}")
                return []
        return []
    
    def calculate_pnl(self):
        """P&L कॅल्क्युलेट करा"""
        total_pnl = 0
        for position in self.positions:
            if 'pnl' in position:
                total_pnl += position['pnl']
            elif 'netReturns' in position:
                total_pnl += position['netReturns']
        
        if total_pnl < 0:
            self.current_loss = abs(total_pnl)
            self.current_profit = 0
        else:
            self.current_profit = total_pnl
            self.current_loss = 0
        
        return total_pnl
    
    def place_dhan_order(self, symbol, quantity, order_type="BUY", product_type="INTRADAY"):
        """धन API वर वास्तविक ऑर्डर प्लेस करा"""
        if not self.dhan_client:
            return {"status": "error", "message": "धन API कनेक्ट नाही"}
        
        try:
            # धन API ला योग्य फॉरमॅटमध्ये मॅप करा
            transaction_type = "BUY" if order_type.upper() == "BUY" else "SELL"
            
            order_response = self.dhan_client.place_order(
                security_id=symbol,
                exchange_segment="NSE_EQ",  # NSE Equity
                transaction_type=transaction_type,
                quantity=quantity,
                order_type="MARKET",  # किंवा "LIMIT"
                product_type=product_type,
                price=0  # मार्केट ऑर्डरसाठी
            )
            
            logger.info(f"✅ धन ऑर्डर प्लेस केला: {order_response}")
            
            # ट्रेड काउंट वाढवा
            self.daily_trade_count += 1
            
            # ट्रेड हिस्टरीमध्ये जोडा
            self.trade_history.append({
                "order_id": order_response.get('orderId', f"ORD_{int(time.time())}"),
                "symbol": symbol,
                "quantity": quantity,
                "type": order_type,
                "time": datetime.datetime.now().isoformat(),
                "status": "placed",
                "via": "DHAN_API"
            })
            
            return {
                "status": "success",
                "order_id": order_response.get('orderId'),
                "message": "ऑर्डर प्लेस केला",
                "data": order_response
            }
            
        except Exception as e:
            logger.error(f"❌ धन ऑर्डर त्रुटी: {e}")
            return {"status": "error", "message": str(e)}
    
    def exit_all_positions(self):
        """सर्व पोझिशन्स बंद करा"""
        if not self.dhan_client or not self.positions:
            return {"status": "error", "message": "कोणतेही पोझिशन्स नाहीत"}
        
        results = []
        for position in self.positions:
            if position.get('quantity', 0) > 0:
                try:
                    exit_order = self.dhan_client.place_order(
                        security_id=position.get('securityId'),
                        exchange_segment=position.get('exchangeSegment', 'NSE_EQ'),
                        transaction_type="SELL",
                        quantity=position.get('quantity'),
                        order_type="MARKET",
                        product_type=position.get('productType', 'INTRADAY')
                    )
                    results.append({
                        "symbol": position.get('securityId'),
                        "status": "exited",
                        "order_id": exit_order.get('orderId')
                    })
                except Exception as e:
                    results.append({
                        "symbol": position.get('securityId'),
                        "status": "error",
                        "message": str(e)
                    })
        
        logger.info(f"🔄 सर्व पोझिशन्स बंद केले: {results}")
        return {"status": "success", "exits": results}

# ग्लोबल इंस्टन्स
trading_state = TradingState()

# ============ हेल्पर फंक्शन्स ============
def check_and_reset_daily_counter():
    """दररोज ट्रेड काउंटर रिसेट करा"""
    today = datetime.date.today()
    if trading_state.last_reset_date != today:
        trading_state.daily_trade_count = 0
        trading_state.last_reset_date = today
        trading_state.trade_history = []
        trading_state.trading_enabled = True
        logger.info("🔄 दिवसाचा ट्रेड काउंटर रिसेट केला")

def is_trading_time():
    """ट्रेडिंग वेळ तपासा"""
    now = datetime.datetime.now().time()
    return TRADING_START_TIME <= now <= TRADING_END_TIME

def calculate_loss_percentage():
    """तोटा टक्केवारी काढा"""
    if trading_state.total_capital <= 0:
        return 0
    net_balance = trading_state.total_capital - trading_state.current_loss
    if net_balance <= 0:
        return 100
    loss_percentage = (trading_state.current_loss / trading_state.total_capital) * 100
    return min(100, max(0, loss_percentage))

def can_place_trade():
    """ट्रेड घेण्यास परवानगी आहे का?"""
    
    # दररोजचा काउंटर रिसेट तपासा
    check_and_reset_daily_counter()
    
    # ट्रेडिंग एनेबल तपासा
    if not trading_state.trading_enabled:
        return False, "ट्रेडिंग बंद केले आहे"
    
    # नियम 1: 20% तोटा तपासा
    loss_percentage = calculate_loss_percentage()
    
    if loss_percentage >= MAX_LOSS_PERCENTAGE:
        logger.warning(f"❌ 20% तोटा झाला आहे ({loss_percentage:.2f}%)")
        trading_state.trading_enabled = False
        # सर्व पोझिशन्स ऑटो एक्झिट
        trading_state.exit_all_positions()
        return False, "20% तोटा झाला आहे. सर्व ट्रेड्स बंद केले."
    
    # नियम 2: ट्रेडिंग वेळ तपासा
    if not is_trading_time():
        current_time = datetime.datetime.now().time()
        if current_time < TRADING_START_TIME:
            message = "ट्रेडिंग अजून सुरू झाले नाही (9:25 AM पासून)"
        else:
            message = "ट्रेडिंग वेळ संपली (3:00 PM पर्यंत)"
            # 3 PM नंतर ऑटो एक्झिट
            trading_state.exit_all_positions()
            trading_state.trading_enabled = False
        logger.warning(f"⏰ {message}")
        return False, message
    
    # नियम 3: दिवसाची ट्रेड मर्यादा तपासा
    if trading_state.daily_trade_count >= MAX_DAILY_TRADES:
        logger.warning(f"🚫 दिवसाची {MAX_DAILY_TRADES} ट्रेड्स मर्यादा संपली")
        return False, f"दिवसाची {MAX_DAILY_TRADES} ट्रेड्स मर्यादा संपली"
    
    return True, "ट्रेड घेण्यास परवानगी"

# ============ बॅकग्राऊंड मॉनिटरिंग ============
def background_monitor():
    """सतत मॉनिटरिंग करणारा थ्रेड"""
    last_balance_check = datetime.datetime.now()
    
    while True:
        try:
            now = datetime.datetime.now()
            
            # 5 मिनिटांनी बॅलन्स फेच
            if (now - last_balance_check).seconds >= BALANCE_REFRESH_INTERVAL:
                trading_state.fetch_balance()
                last_balance_check = now
            
            # 3 PM ऑटो एक्झिट
            if not is_trading_time() and trading_state.trading_enabled:
                current_time = now.time()
                if current_time > TRADING_END_TIME:
                    logger.info("🕒 3:00 PM झाली आहे, सर्व ट्रेड्स बंद करत आहे...")
                    trading_state.exit_all_positions()
                    trading_state.trading_enabled = False
            
            # 20% तोटा तपासा
            loss_percentage = calculate_loss_percentage()
            if loss_percentage >= MAX_LOSS_PERCENTAGE and trading_state.trading_enabled:
                logger.warning(f"🚨 20% तोटा झाला ({loss_percentage:.2f}%)! ट्रेडिंग बंद.")
                trading_state.trading_enabled = False
                trading_state.exit_all_positions()
            
            # 30 सेकंदांनी झोप
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"मॉनिटरिंग एरर: {e}")
            time.sleep(60)

# मॉनिटरिंग थ्रेड सुरू करा
monitor_thread = threading.Thread(target=background_monitor, daemon=True)
monitor_thread.start()

# ============ HTML टेम्पलेट (दुरुस्त केलेला) ============
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="mr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>धन रिस्क मॅनेजर</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Arial, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        
        .header { 
            background: white; 
            padding: 30px; 
            border-radius: 15px; 
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            text-align: center;
        }
        
        .header h1 { 
            color: #2c3e50; 
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        
        .header .subtitle {
            color: #7f8c8d;
            font-size: 1.1em;
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
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
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .card h2 i {
            font-size: 1.2em;
        }
        
        .status-badge {
            display: inline-block;
            padding: 8px 15px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
            margin-bottom: 15px;
        }
        
        .status-active { background: #d4edda; color: #155724; }
        .status-inactive { background: #f8d7da; color: #721c24; }
        .status-warning { background: #fff3cd; color: #856404; }
        
        .info-grid {
            display: grid;
            gap: 12px;
        }
        
        .info-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #f0f0f0;
        }
        
        .info-label { color: #7f8c8d; }
        .info-value { 
            font-weight: bold; 
            color: #2c3e50;
        }
        
        .info-value.good { color: #28a745; }
        .info-value.bad { color: #dc3545; }
        .info-value.warning { color: #ffc107; }
        
        .rules-list {
            list-style: none;
        }
        
        .rules-list li {
            padding: 12px 15px;
            margin-bottom: 10px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #3498db;
        }
        
        .api-endpoints {
            display: grid;
            gap: 10px;
        }
        
        .endpoint {
            background: #f8f9fa;
            padding: 12px;
            border-radius: 8px;
            border-left: 4px solid #6c757d;
        }
        
        .endpoint .method {
            display: inline-block;
            padding: 4px 8px;
            background: #6c757d;
            color: white;
            border-radius: 4px;
            font-size: 0.8em;
            margin-right: 10px;
        }
        
        .endpoint .method.get { background: #28a745; }
        .endpoint .method.post { background: #007bff; }
        
        .controls {
            display: flex;
            gap: 10px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s;
        }
        
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        
        .btn-refresh { background: #17a2b8; color: white; }
        .btn-reset { background: #6c757d; color: white; }
        .btn-exit { background: #dc3545; color: white; }
        .btn-trade { background: #28a745; color: white; }
        
        .footer {
            text-align: center;
            margin-top: 30px;
            color: white;
            opacity: 0.8;
        }
        
        @media (max-width: 768px) {
            .dashboard { grid-template-columns: 1fr; }
            .header { padding: 20px; }
            .header h1 { font-size: 2em; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-shield-alt"></i> धन रिस्क मॅनेजर</h1>
            <p class="subtitle">सुरक्षित ट्रेडिंगसाठी स्वयंचलित रिस्क मॅनेजमेंट सिस्टम</p>
        </div>
        
        <div class="dashboard">
            <!-- स्टेटस कार्ड -->
            <div class="card">
                <h2><i class="fas fa-chart-line"></i> सध्याची स्थिती</h2>
                <div class="status-badge {{ 'status-active' if data.trading_enabled else 'status-inactive' }}">
                    {{ 'सक्रिय' if data.trading_enabled else 'निष्क्रिय' }}
                </div>
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-label">वेळ:</span>
                        <span class="info-value">{{ data.current_time }}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">ट्रेडिंग वेळ:</span>
                        <span class="info-value {{ 'good' if data.trading_hours_active else 'bad' }}">
                            {{ 'सक्रिय' if data.trading_hours_active else 'निष्क्रिय' }}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">ट्रेड परवानगी:</span>
                        <span class="info-value {{ 'good' if data.can_trade else 'bad' }}">
                            {{ 'होय' if data.can_trade else 'नाही' }}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">संदेश:</span>
                        <span class="info-value">{{ data.trade_message }}</span>
                    </div>
                </div>
            </div>
            
            <!-- बॅलन्स कार्ड -->
            <div class="card">
                <h2><i class="fas fa-wallet"></i> बॅलन्स माहिती</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-label">उपलब्ध बॅलन्स:</span>
                        <span class="info-value good">₹{{ data.available_balance|round|int }}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">सध्याचा तोटा:</span>
                        <span class="info-value {{ 'bad' if data.current_loss > 0 else 'good' }}">
                            ₹{{ data.current_loss|round|int }}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">तोटा %:</span>
                        {% set loss_percent_num = data.loss_percentage|float %}
                        <span class="info-value {{ 'bad' if loss_percent_num >= 20 else ('warning' if loss_percent_num >= 10 else 'good') }}">
                            {{ data.loss_percentage }}%
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">निव्वळ बॅलन्स:</span>
                        <span class="info-value {{ 'bad' if data.net_balance < data.available_balance else 'good' }}">
                            ₹{{ data.net_balance|round|int }}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">धन कनेक्शन:</span>
                        <span class="info-value {{ 'good' if data.dhan_connected else 'bad' }}">
                            {{ 'कनेक्टेड' if data.dhan_connected else 'डिस्कनेक्टेड' }}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">शेवटचा अपडेट:</span>
                        <span class="info-value">{{ data.last_balance_update }}</span>
                    </div>
                </div>
                <div class="controls">
                    <button class="btn btn-refresh" onclick="refreshBalance()">
                        <i class="fas fa-sync-alt"></i> बॅलन्स रिफ्रेश
                    </button>
                </div>
            </div>
            
            <!-- ट्रेडिंग कार्ड -->
            <div class="card">
                <h2><i class="fas fa-trade"></i> ट्रेडिंग माहिती</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-label">आजचे ट्रेड्स:</span>
                        {% set trades_num = data.daily_trades|int %}
                        <span class="info-value {{ 'bad' if trades_num >= 10 else ('warning' if trades_num >= 8 else 'good') }}">
                            {{ data.daily_trades }}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">बाकी ट्रेड्स:</span>
                        <span class="info-value {{ 'bad' if data.remaining_trades == 0 else 'good' }}">
                            {{ data.remaining_trades }}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">मॅक्स ट्रेड्स/दिवस:</span>
                        <span class="info-value">{{ data.max_trades }}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">पोझिशन्स:</span>
                        <span class="info-value">{{ data.positions_count }}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">दिनांक:</span>
                        <span class="info-value">{{ data.date }}</span>
                    </div>
                </div>
                <div class="controls">
                    <button class="btn btn-reset" onclick="resetDaily()">
                        <i class="fas fa-redo"></i> दिवस रिसेट
                    </button>
                    <button class="btn btn-exit" onclick="exitAll()">
                        <i class="fas fa-sign-out-alt"></i> सर्व बंद करा
                    </button>
                </div>
            </div>
        </div>
        
        <!-- नियम कार्ड -->
        <div class="card">
            <h2><i class="fas fa-rules"></i> मुख्य नियम</h2>
            <ul class="rules-list">
                <li><strong>नियम 1:</strong> 20% तोटा झाला की सर्व ट्रेड्स ऑटो एक्झिट</li>
                <li><strong>नियम 2:</strong> ट्रेड वेळ: सकाळी 9:25 ते दुपारी 3:00</li>
                <li><strong>नियम 3:</strong> दिवसात फक्त 10 ट्रेड्स</li>
                <li><strong>नियम 4:</strong> 3:00 PM नंतर स्वयंचलित सर्व ट्रेड्स बंद</li>
            </ul>
        </div>
        
        <!-- API एंडपॉइंट्स -->
        <div class="card">
            <h2><i class="fas fa-code"></i> API एंडपॉइंट्स</h2>
            <div class="api-endpoints">
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <strong>/health</strong> - हेल्थ चेक
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <strong>/balance</strong> - बॅलन्स माहिती
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <strong>/can_trade</strong> - ट्रेड परवानगी
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <strong>/get_state</strong> - सर्व स्टेट माहिती
                </div>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <strong>/place_order</strong> - ऑर्डर प्लेस
                </div>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <strong>/update_loss</strong> - तोटा अपडेट
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>धन रिस्क मॅनेजर • सुरक्षित ट्रेडिंग • © 2025</p>
        </div>
    </div>
    
    <script>
        function refreshBalance() {
            fetch('/refresh_balance', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert('बॅलन्स रिफ्रेश केला: ' + data.message);
                    location.reload();
                });
        }
        
        function resetDaily() {
            fetch('/reset_daily', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert('दिवस रिसेट केला: ' + data.message);
                    location.reload();
                });
        }
        
        function exitAll() {
            fetch('/exit_all', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert('सर्व पोझिशन्स बंद केली: ' + data.message);
                    location.reload();
                });
        }
        
        // ऑटो रिफ्रेश (प्रत्येक 30 सेकंदांनी)
        setInterval(() => {
            fetch('/get_state')
                .then(response => response.json())
                .then(data => {
                    // फक्त आवश्यक असल्यास रीलोड करा
                    if (data.trading_enabled !== {{ 'true' if data.trading_enabled else 'false' }} ||
                        data.daily_trades !== {{ data.daily_trades }}) {
                        location.reload();
                    }
                });
        }, 30000);
    </script>
</body>
</html>
"""

# ============ API रूट्स ============
@app.route('/')
def home():
    """मुख्य डॅशबोर्ड"""
    can_trade, trade_message = can_place_trade()
    loss_percentage = calculate_loss_percentage()
    
    # डेटा तयार करा - सर्व संख्यात्मक मूल्ये सुनिश्चित करा
    data = {
        "trading_enabled": trading_state.trading_enabled,
        "trading_hours_active": is_trading_time(),
        "can_trade": can_trade,
        "trade_message": trade_message,
        "current_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "available_balance": float(trading_state.total_capital),
        "current_loss": float(trading_state.current_loss),
        "current_profit": float(trading_state.current_profit),
        "net_balance": float(trading_state.total_capital - trading_state.current_loss),
        "loss_percentage": f"{loss_percentage:.2f}",  # टेम्पलेटमध्ये float मध्ये रूपांतरित केले जाईल
        "dhan_connected": trading_state.dhan_client is not None,
        "last_balance_update": trading_state.last_balance_update.strftime("%H:%M:%S") if trading_state.last_balance_update else "कधीच नाही",
        "daily_trades": int(trading_state.daily_trade_count),
        "remaining_trades": int(MAX_DAILY_TRADES - trading_state.daily_trade_count),
        "max_trades": int(MAX_DAILY_TRADES),
        "positions_count": len(trading_state.positions),
        "date": trading_state.last_reset_date.strftime("%d-%m-%Y")
    }
    
    return render_template_string(HTML_TEMPLATE, data=data)

@app.route('/health', methods=['GET'])
def health():
    """हेल्थ चेक"""
    can_trade, message = can_place_trade()
    loss_percentage = calculate_loss_percentage()
    
    balance_info = trading_state.fetch_balance()
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "trading_permission": can_trade,
        "message": message,
        "daily_trades": trading_state.daily_trade_count,
        "remaining_trades": MAX_DAILY_TRADES - trading_state.daily_trade_count,
        "trading_hours": f"{TRADING_START_TIME} to {TRADING_END_TIME}",
        "trading_hours_active": is_trading_time(),
        "balance_status": balance_info.get("status", "unknown"),
        "available_balance": trading_state.total_capital,
        "current_loss": trading_state.current_loss,
        "loss_percentage": f"{loss_percentage:.2f}%",
        "dhan_connection_status": trading_state.dhan_connection_status,
        "last_balance_update": str(trading_state.last_balance_update) if trading_state.last_balance_update else "Never"
    })

@app.route('/balance', methods=['GET'])
def get_balance():
    """बॅलन्स माहिती मिळवा"""
    balance_result = trading_state.fetch_balance()
    loss_percentage = calculate_loss_percentage()
    
    response = {
        "status": balance_result.get("status", "unknown"),
        "available_balance": trading_state.total_capital,
        "current_loss": trading_state.current_loss,
        "current_profit": trading_state.current_profit,
        "net_balance": trading_state.total_capital - trading_state.current_loss,
        "loss_percentage": f"{loss_percentage:.2f}%",
        "loss_amount_20_percent": trading_state.total_capital * 0.20,
        "remaining_loss_buffer": (trading_state.total_capital * 0.20) - trading_state.current_loss,
        "last_updated": str(trading_state.last_balance_update) if trading_state.last_balance_update else "Never",
        "data_source": "DHAN API" if trading_state.dhan_client else "MOCK DATA",
        "dhan_connection_status": trading_state.dhan_connection_status
    }
    
    # बॅलन्स डेटा जोडा
    if trading_state.balance_data:
        response["balance_details"] = trading_state.balance_data
    
    return jsonify(response)

@app.route('/refresh_balance', methods=['POST'])
def refresh_balance():
    """बॅलन्स रिफ्रेश करा"""
    balance_result = trading_state.fetch_balance()
    
    return jsonify({
        "status": "success",
        "message": "बॅलन्स रिफ्रेश केला",
        "balance_result": balance_result,
        "new_balance": trading_state.total_capital,
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/get_funds', methods=['GET'])
def get_funds():
    """धन API पासून थेट फंड माहिती"""
    if trading_state.dhan_client:
        try:
            funds = trading_state.dhan_client.get_fund_limits()
            return jsonify({
                "status": "success",
                "funds": funds,
                "timestamp": datetime.datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500
    else:
        return jsonify({
            "status": "error",
            "message": "धन API कनेक्ट नाही. कृपया DHAN_CLIENT_ID आणि DHAN_ACCESS_TOKEN सेट करा."
        }), 400

@app.route('/can_trade', methods=['GET'])
def check_trade_permission():
    """ट्रेड घेण्याची परवानगी तपासा"""
    can_trade, message = can_place_trade()
    
    response = {
        "permission": can_trade,
        "message": message,
        "trade_count": trading_state.daily_trade_count,
        "max_trades": MAX_DAILY_TRADES,
        "remaining_trades": MAX_DAILY_TRADES - trading_state.daily_trade_count,
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "trading_hours_active": is_trading_time(),
        "trading_enabled": trading_state.trading_enabled,
        "loss_percentage": f"{calculate_loss_percentage():.2f}%"
    }
    
    logger.info(f"ट्रेड परवानगी तपास: {response}")
    return jsonify(response)

@app.route('/place_order', methods=['POST'])
def place_order():
    """ऑर्डर प्लेस करा"""
    try:
        data = request.get_json() or {}
        symbol = data.get('symbol', 'SBIN')
        quantity = data.get('quantity', 1)
        order_type = data.get('order_type', 'BUY')
        product_type = data.get('product_type', 'INTRADAY')
        
        # ट्रेड परवानगी तपासा
        can_trade, message = can_place_trade()
        if not can_trade:
            return jsonify({
                "status": "declined",
                "message": message
            }), 403
        
        # ऑर्डर प्लेस करा
        if trading_state.dhan_client:
            # वास्तविक धन ऑर्डर
            order_result = trading_state.place_dhan_order(symbol, quantity, order_type, product_type)
            return jsonify(order_result)
        else:
            # सिम्युलेटेड ऑर्डर
            order_id = f"ORD_{int(time.time())}_{trading_state.daily_trade_count + 1}"
            trading_state.daily_trade_count += 1
            trading_state.trade_history.append({
                "order_id": order_id,
                "symbol": symbol,
                "quantity": quantity,
                "type": order_type,
                "time": datetime.datetime.now().isoformat(),
                "status": "placed",
                "via": "SIMULATED"
            })
            
            logger.info(f"✅ सिम्युलेटेड ऑर्डर: {order_id}")
            
            return jsonify({
                "status": "success",
                "message": "सिम्युलेटेड ऑर्डर प्लेस केला",
                "order_id": order_id,
                "daily_trades": trading_state.daily_trade_count,
                "remaining_trades": MAX_DAILY_TRADES - trading_state.daily_trade_count,
                "note": "धन API कनेक्ट नाही. वास्तविक ऑर्डरसाठी DHAN_CLIENT_ID आणि DHAN_ACCESS_TOKEN सेट करा."
            })
        
    except Exception as e:
        logger.error(f"ऑर्डर एरर: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/update_loss', methods=['POST'])
def update_loss():
    """तोटा अपडेट करा"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        loss_amount = float(data.get('loss', 0))
        profit_amount = float(data.get('profit', 0))
        
        trading_state.current_loss = loss_amount
        trading_state.current_profit = profit_amount
        loss_percentage = calculate_loss_percentage()
        
        logger.info(f"📉 P&L अपडेट: तोटा ₹{loss_amount} | नफा ₹{profit_amount} | ({loss_percentage:.2f}%)")
        
        # 20% तोटा झाला का तपासा
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            trading_state.trading_enabled = False
            trading_state.exit_all_positions()
            logger.warning(f"🚨 20% तोटा झाला! ट्रेडिंग बंद.")
        
        return jsonify({
            "status": "success",
            "loss": loss_amount,
            "profit": profit_amount,
            "loss_percentage": f"{loss_percentage:.2f}%",
            "trading_enabled": trading_state.trading_enabled,
            "max_loss_limit": trading_state.total_capital * 0.20,
            "remaining_buffer": (trading_state.total_capital * 0.20) - loss_amount
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reset_daily', methods=['POST'])
def reset_daily():
    """दिवसाचा काउंटर रिसेट करा"""
    trading_state.daily_trade_count = 0
    trading_state.trade_history = []
    trading_state.last_reset_date = datetime.date.today()
    trading_state.trading_enabled = True
    trading_state.current_loss = 0
    trading_state.current_profit = 0
    
    logger.info("🔄 दिवसाचा काउंटर रिसेट केला")
    
    return jsonify({
        "status": "success",
        "message": "दिवसाचा काउंटर रिसेट केला",
        "trade_count": 0,
        "loss": 0,
        "profit": 0,
        "trading_enabled": True
    })

@app.route('/exit_all', methods=['POST'])
def exit_all():
    """सर्व पोझिशन्स बंद करा"""
    exit_result = trading_state.exit_all_positions()
    
    return jsonify({
        "status": "success",
        "message": "सर्व पोझिशन्स बंद करण्याची कमांड दिली",
        "result": exit_result,
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/get_state', methods=['GET'])
def get_state():
    """सर्व स्टेट माहिती मिळवा"""
    can_trade, message = can_place_trade()
    loss_percentage = calculate_loss_percentage()
    
    # पोझिशन्स फेच करा
    positions = trading_state.fetch_positions()
    
    return jsonify({
        "date": trading_state.last_reset_date.isoformat(),
        "daily_trades": trading_state.daily_trade_count,
        "max_trades": MAX_DAILY_TRADES,
        "remaining_trades": MAX_DAILY_TRADES - trading_state.daily_trade_count,
        "trading_permission": can_trade,
        "message": message,
        "capital": trading_state.total_capital,
        "current_loss": trading_state.current_loss,
        "current_profit": trading_state.current_profit,
        "loss_percentage": f"{loss_percentage:.2f}%",
        "trading_time_active": is_trading_time(),
        "current_time": datetime.datetime.now().strftime("%H:%M:%S"),
        "trading_enabled": trading_state.trading_enabled,
        "dhan_connection_status": trading_state.dhan_connection_status,
        "last_balance_update": str(trading_state.last_balance_update) if trading_state.last_balance_update else "Never",
        "positions_count": len(positions),
        "positions": positions[:5],  # फक्त पहिली 5 पोझिशन्स
        "recent_trades": trading_state.trade_history[-5:],  # शेवटचे 5 ट्रेड्स
        "rules": {
            "trading_hours": f"{TRADING_START_TIME} to {TRADING_END_TIME}",
            "max_daily_trades": MAX_DAILY_TRADES,
            "max_loss_percentage": MAX_LOSS_PERCENTAGE,
            "auto_exit_at_3pm": True,
            "auto_exit_at_20_percent_loss": True
        }
    })

@app.route('/get_positions', methods=['GET'])
def get_positions():
    """वर्तमान पोझिशन्स मिळवा"""
    positions = trading_state.fetch_positions()
    
    return jsonify({
        "status": "success",
        "positions_count": len(positions),
        "positions": positions,
        "total_pnl": trading_state.current_profit - trading_state.current_loss,
        "timestamp": datetime.datetime.now().isoformat()
    })

# ============ सर्व्हर स्टार्ट ============
if __name__ == '__main__':
    logger.info("🚀 धन रिस्क मॅनेजर सुरू करत आहे...")
    logger.info(f"📍 ट्रेडिंग वेळ: {TRADING_START_TIME} ते {TRADING_END_TIME}")
    logger.info(f"🎯 दिवसाचे कमाल ट्रेड्स: {MAX_DAILY_TRADES}")
    logger.info(f"⚠️ कमाल तोटा मर्यादा: {MAX_LOSS_PERCENTAGE}%")
    logger.info(f"💰 धन कनेक्शन: {trading_state.dhan_connection_status}")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
