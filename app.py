"""
धन रिस्क मॅनेजर - मराठी
नियम:
1. 20% तोटा झाला की सर्व ट्रेड्स ऑटो एक्झिट
2. ट्रेड वेळ: 9:25 AM ते 3:00 PM
3. दिवसात फक्त 10 ट्रेड्स
"""

import os
import datetime
import time
import threading
from flask import Flask, jsonify, request
import logging

# सेटअप लॉगिंग
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ग्लोबल व्हेरिएबल्स
TRADING_START_TIME = datetime.time(9, 25)  # सकाळी 9:25
TRADING_END_TIME = datetime.time(15, 0)    # दुपारी 3:00
MAX_DAILY_TRADES = 10
MAX_LOSS_PERCENTAGE = 20

# स्टेट मॅनेजमेंट
class TradingState:
    def __init__(self):
        self.daily_trade_count = 0
        self.total_capital = 100000  # डिफॉल्ट कॅपिटल
        self.current_loss = 0
        self.trading_enabled = True
        self.last_reset_date = datetime.date.today()
        self.trade_history = []
        
        logger.info("📊 ट्रेडिंग स्टेट इनिशियलाइज्ड")
        logger.info(f"📈 ट्रेडिंग वेळ: {TRADING_START_TIME} ते {TRADING_END_TIME}")
        logger.info(f"🎯 मॅक्स डेली ट्रेड्स: {MAX_DAILY_TRADES}")
        logger.info(f"⚠️ मॅक्स लॉस: {MAX_LOSS_PERCENTAGE}%")

# ग्लोबल इंस्टन्स
trading_state = TradingState()

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
    loss_percentage = (trading_state.current_loss / trading_state.total_capital) * 100
    return max(0, loss_percentage)

def can_place_trade():
    """ट्रेड घेण्यास परवानगी आहे का?"""
    
    # दररोजचा काउंटर रिसेट तपासा
    check_and_reset_daily_counter()
    
    # नियम 1: 20% तोटा तपासा
    loss_percentage = calculate_loss_percentage()
    
    if loss_percentage >= MAX_LOSS_PERCENTAGE:
        logger.warning(f"❌ 20% तोटा झाला आहे ({loss_percentage:.2f}%)")
        trading_state.trading_enabled = False
        return False, "20% तोटा झाला आहे. ट्रेडिंग बंद."
    
    # ट्रेडिंग एनेबल तपासा
    if not trading_state.trading_enabled:
        return False, "ट्रेडिंग बंद केले आहे"
    
    # नियम 2: ट्रेडिंग वेळ तपासा
    if not is_trading_time():
        current_time = datetime.datetime.now().time()
        if current_time < TRADING_START_TIME:
            message = "ट्रेडिंग अजून सुरू झाले नाही (9:25 AM पासून)"
        else:
            message = "ट्रेडिंग वेळ संपली (3:00 PM पर्यंत)"
        logger.warning(f"⏰ {message}")
        return False, message
    
    # नियम 3: दिवसाची ट्रेड मर्यादा तपासा
    if trading_state.daily_trade_count >= MAX_DAILY_TRADES:
        logger.warning(f"🚫 दिवसाची {MAX_DAILY_TRADES} ट्रेड्स मर्यादा संपली")
        return False, f"दिवसाची {MAX_DAILY_TRADES} ट्रेड्स मर्यादा संपली"
    
    return True, "ट्रेड घेण्यास परवानगी"

def auto_exit_at_3pm():
    """दुपारी 3:00 ला सर्व ट्रेड्स ऑटो एक्झिट"""
    now = datetime.datetime.now()
    exit_time = datetime.datetime.combine(now.date(), TRADING_END_TIME)
    
    if now >= exit_time and trading_state.trading_enabled:
        logger.info("🕒 3:00 PM झाली आहे, सर्व ट्रेड्स बंद करत आहे...")
        trading_state.trading_enabled = False
        return "सर्व ट्रेड्स 3:00 PM ला बंद केले"
    return None

# बॅकग्राऊंड मॉनिटरिंग थ्रेड
def background_monitor():
    """सतत मॉनिटरिंग करणारा थ्रेड"""
    while True:
        try:
            # 3 PM ऑटो एक्झिट
            auto_exit_at_3pm()
            
            # 30 सेकंदांनी झोप
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"मॉनिटरिंग एरर: {e}")
            time.sleep(60)

# API रूट्स
@app.route('/')
def home():
    """मुख्य पृष्ठ"""
    return """
    <html>
    <head>
        <title>धन रिस्क मॅनेजर</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; }
            .rule { background: #e8f4f8; padding: 15px; margin: 15px 0; border-left: 5px solid #3498db; border-radius: 5px; }
            .status { padding: 10px; border-radius: 5px; font-weight: bold; }
            .green { background: #d4edda; color: #155724; }
            .red { background: #f8d7da; color: #721c24; }
            .info { background: #d1ecf1; color: #0c5460; padding: 10px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🪙 धन रिस्क मॅनेजर</h1>
            <p><strong>स्थिती:</strong> <span class="status green">सक्रिय</span></p>
            <p><strong>वेळ:</strong> """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
            
            <h2>📋 मुख्य नियम</h2>
            <div class="rule">
                <strong>नियम 1:</strong> 20% तोटा झाला की सर्व ट्रेड्स ऑटो एक्झिट
            </div>
            <div class="rule">
                <strong>नियम 2:</strong> ट्रेड वेळ: सकाळी 9:25 ते दुपारी 3:00
            </div>
            <div class="rule">
                <strong>नियम 3:</strong> दिवसात फक्त 10 ट्रेड्स
            </div>
            
            <div class="info">
                <p><strong>API एंडपॉइंट्स:</strong></p>
                <ul>
                    <li><code>/health</code> - हेल्थ चेक</li>
                    <li><code>/can_trade</code> - ट्रेड परवानगी तपासा</li>
                    <li><code>/get_state</code> - सर्व स्टेट माहिती</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health', methods=['GET'])
def health():
    """हेल्थ चेक"""
    can_trade, message = can_place_trade()
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "trading_permission": can_trade,
        "message": message,
        "daily_trades": trading_state.daily_trade_count,
        "remaining_trades": MAX_DAILY_TRADES - trading_state.daily_trade_count,
        "trading_hours": f"{TRADING_START_TIME} to {TRADING_END_TIME}",
        "loss_percentage": f"{calculate_loss_percentage():.2f}%"
    })

@app.route('/can_trade', methods=['GET'])
def check_trade_permission():
    """ट्रेड घेण्याची परवानगी तपासा"""
    can_trade, message = can_place_trade()
    
    response = {
        "permission": can_trade,
        "message": message,
        "trade_count": trading_state.daily_trade_count,
        "max_trades": MAX_DAILY_TRADES,
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "trading_hours_active": is_trading_time()
    }
    
    logger.info(f"ट्रेड परवानगी तपास: {response}")
    return jsonify(response)

@app.route('/place_order', methods=['POST'])
def place_order():
    """ऑर्डर प्लेस करा (सिम्युलेटेड)"""
    try:
        # ट्रेड परवानगी तपासा
        can_trade, message = can_place_trade()
        if not can_trade:
            return jsonify({
                "status": "declined",
                "message": message
            }), 403
        
        # सिम्युलेटेड ऑर्डर
        order_id = f"ORD_{int(time.time())}_{trading_state.daily_trade_count + 1}"
        
        # ट्रेड काउंट वाढवा
        trading_state.daily_trade_count += 1
        trading_state.trade_history.append({
            "order_id": order_id,
            "time": datetime.datetime.now().isoformat(),
            "status": "placed"
        })
        
        logger.info(f"✅ ऑर्डर प्लेस केला: {order_id}")
        
        return jsonify({
            "status": "success",
            "message": "ऑर्डर प्लेस केला",
            "order_id": order_id,
            "daily_trades": trading_state.daily_trade_count,
            "remaining_trades": MAX_DAILY_TRADES - trading_state.daily_trade_count
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
        
        trading_state.current_loss = loss_amount
        loss_percentage = calculate_loss_percentage()
        
        logger.info(f"📉 तोटा अपडेट: ₹{loss_amount} ({loss_percentage:.2f}%)")
        
        # 20% तोटा झाला का तपासा
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            trading_state.trading_enabled = False
            logger.warning(f"🚨 20% तोटा झाला! ट्रेडिंग बंद.")
        
        return jsonify({
            "status": "success",
            "loss": loss_amount,
            "loss_percentage": f"{loss_percentage:.2f}%",
            "trading_enabled": trading_state.trading_enabled
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
    
    logger.info("🔄 दिवसाचा काउंटर रिसेट केला")
    
    return jsonify({
        "status": "success",
        "message": "दिवसाचा काउंटर रिसेट केला",
        "trade_count": 0
    })

@app.route('/get_state', methods=['GET'])
def get_state():
    """सर्व स्टेट माहिती मिळवा"""
    can_trade, message = can_place_trade()
    
    return jsonify({
        "date": trading_state.last_reset_date.isoformat(),
        "daily_trades": trading_state.daily_trade_count,
        "max_trades": MAX_DAILY_TRADES,
        "remaining_trades": MAX_DAILY_TRADES - trading_state.daily_trade_count,
        "trading_permission": can_trade,
        "message": message,
        "capital": trading_state.total_capital,
        "current_loss": trading_state.current_loss,
        "loss_percentage": f"{calculate_loss_percentage():.2f}%",
        "trading_time_active": is_trading_time(),
        "current_time": datetime.datetime.now().strftime("%H:%M:%S"),
        "trading_enabled": trading_state.trading_enabled,
        "recent_trades": trading_state.trade_history[-5:]  # शेवटचे 5 ट्रेड्स
    })

# सर्व्हर सुरू करताना
if __name__ == '__main__':
    # मॉनिटरिंग थ्रेड सुरू करा
    monitor_thread = threading.Thread(target=background_monitor, daemon=True)
    monitor_thread.start()
    
    logger.info("🚀 धन रिस्क मॅनेजर सुरू करत आहे...")
    logger.info(f"📍 ट्रेडिंग वेळ: {TRADING_START_TIME} ते {TRADING_END_TIME}")
    logger.info(f"🎯 दिवसाचे कमाल ट्रेड्स: {MAX_DAILY_TRADES}")
    logger.info(f"⚠️ कमाल तोटा मर्यादा: {MAX_LOSS_PERCENTAGE}%")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
