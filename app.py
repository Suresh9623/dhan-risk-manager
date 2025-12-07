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
from flask_cors import CORS
import logging

# सेटअप लॉगिंग
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ग्लोबल व्हेरिएबल्स
TRADING_START_TIME = datetime.time(9, 25)  # सकाळी 9:25
TRADING_END_TIME = datetime.time(15, 0)    # दुपारी 3:00
MAX_DAILY_TRADES = 10
MAX_LOSS_PERCENTAGE = 20

# स्टेट मॅनेजमेंट
class TradingState:
    def __init__(self):
        self.daily_trade_count = 0
        self.total_capital = 100000  # डिफॉल्ट कॅपिटल (तुम्ही बदलू शकता)
        self.current_loss = 0
        self.trading_enabled = False
        self.last_reset_date = datetime.date.today()
        self.trade_history = []
        
        # धन API क्रेडेंशियल्स (एन्वायरनमेंट व्हेरिएबल्समधून)
        self.client_id = os.environ.get('DHAN_CLIENT_ID', '')
        self.access_token = os.environ.get('DHAN_ACCESS_TOKEN', '')
        
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
        logger.info("🔄 दिवसाचा ट्रेड काउंटर रिसेट केला")

def is_trading_time():
    """ट्रेडिंग वेळ तपासा"""
    now = datetime.datetime.now().time()
    return TRADING_START_TIME <= now <= TRADING_END_TIME

def calculate_loss_percentage(current_value):
    """तोटा टक्केवारी काढा"""
    loss = trading_state.total_capital - current_value
    loss_percentage = (loss / trading_state.total_capital) * 100
    return max(0, loss_percentage)  # नेगेटिव्ह नाही

def can_place_trade():
    """ट्रेड घेण्यास परवानगी आहे का?"""
    
    # दररोजचा काउंटर रिसेट तपासा
    check_and_reset_daily_counter()
    
    # नियम 1: 20% तोटा तपासा
    loss_percentage = calculate_loss_percentage(
        trading_state.total_capital - trading_state.current_loss
    )
    
    if loss_percentage >= MAX_LOSS_PERCENTAGE:
        logger.warning(f"❌ 20% तोटा झाला आहे ({loss_percentage:.2f}%)")
        trading_state.trading_enabled = False
        return False, "20% तोटा झाला आहे. ट्रेडिंग बंद."
    
    # नियम 2: ट्रेडिंग वेळ तपासा
    if not is_trading_time():
        current_time = datetime.datetime.now().time()
        if current_time < TRADING_START_TIME:
            message = f"ट्रेडिंग अजून सुरू झाले नाही (9:25 AM पासून)"
        else:
            message = f"ट्रेडिंग वेळ संपली (3:00 PM पर्यंत)"
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
        # इथे धन API वर एक्झिट ऑर्डर पाठवा
        return "सर्व ट्रेड्स 3:00 PM ला बंद केले"
    return None

# बॅकग्राऊंड मॉनिटरिंग थ्रेड
def background_monitor():
    """सतत मॉनिटरिंग करणारा थ्रेड"""
    while True:
        try:
            # 3 PM ऑटो एक्झिट
            auto_exit_at_3pm()
            
            # ट्रेडिंग वेळ तपासा
            if not is_trading_time():
                trading_state.trading_enabled = False
            
            # 20 सेकंदांनी झोप
            time.sleep(20)
            
        except Exception as e:
            logger.error(f"मॉनिटरिंग एरर: {e}")
            time.sleep(60)

# API रूट्स
@app.route('/')
def home():
    """मुख्य पृष्ठ"""
    return jsonify({
        "अॅप": "धन रिस्क मॅनेजर",
        "भाषा": "मराठी",
        "स्थिती": "सक्रिय",
        "नियम": [
            "20% तोटा झाला की सर्व ट्रेड्स ऑटो एक्झिट",
            "ट्रेड वेळ: सकाळी 9:25 ते दुपारी 3:00",
            "दिवसात फक्त 10 ट्रेड्स"
        ]
    })

@app.route('/health')
def health():
    """हेल्थ चेक"""
    can_trade, message = can_place_trade()
    
    return jsonify({
        "स्थिती": "स्वस्थ",
        "ट्रेडिंग_परवानगी": can_trade,
        "संदेश": message,
        "वेळ": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "आजचे_ट्रेड्स": trading_state.daily_trade_count,
        "बाकी_ट्रेड्स": MAX_DAILY_TRADES - trading_state.daily_trade_count,
        "ट्रेडिंग_वेळ": f"{TRADING_START_TIME} ते {TRADING_END_TIME}",
        "कॅपिटल": trading_state.total_capital,
        "सध्याचा_तोटा": f"{trading_state.current_loss} ({calculate_loss_percentage(trading_state.total_capital - trading_state.current_loss):.2f}%)"
    })

@app.route('/can_trade', methods=['GET'])
def check_trade_permission():
    """ट्रेड घेण्याची परवानगी तपासा"""
    can_trade, message = can_place_trade()
    
    response = {
        "परवानगी": can_trade,
        "संदेश": message,
        "ट्रेड_काउंट": trading_state.daily_trade_count,
        "मॅक्स_ट्रेड्स": MAX_DAILY_TRADES,
        "वेळ": datetime.datetime.now().strftime("%H:%M:%S")
    }
    
    logger.info(f"ट्रेड परवानगी तपास: {response}")
    return jsonify(response)

@app.route('/place_order', methods=['POST'])
def place_order():
    """ऑर्डर प्लेस करा (सिम्युलेटेड)"""
    try:
        data = request.json
        symbol = data.get('symbol', '')
        quantity = data.get('quantity', 0)
        
        if not symbol or quantity <= 0:
            return jsonify({
                "स्थिती": "अयशस्वी",
                "संदेश": "चुकीचा डेटा"
            }), 400
        
        # ट्रेड परवानगी तपासा
        can_trade, message = can_place_trade()
        if not can_trade:
            return jsonify({
                "स्थिती": "नकार",
                "संदेश": message
            }), 403
        
        # सिम्युलेटेड ऑर्डर
        order_id = f"ORD_{int(time.time())}_{trading_state.daily_trade_count + 1}"
        
        # ट्रेड काउंट वाढवा
        trading_state.daily_trade_count += 1
        trading_state.trade_history.append({
            "order_id": order_id,
            "symbol": symbol,
            "quantity": quantity,
            "time": datetime.datetime.now().isoformat(),
            "status": "प्लेस्ड"
        })
        
        logger.info(f"✅ ऑर्डर प्लेस केला: {order_id} | सिम्बॉल: {symbol} | प्रमाण: {quantity}")
        
        return jsonify({
            "स्थिती": "यशस्वी",
            "संदेश": "ऑर्डर प्लेस केला",
            "ऑर्डर_आयडी": order_id,
            "आजचे_ट्रेड्स": trading_state.daily_trade_count,
            "बाकी_ट्रेड्स": MAX_DAILY_TRADES - trading_state.daily_trade_count
        })
        
    except Exception as e:
        logger.error(f"ऑर्डर एरर: {e}")
        return jsonify({
            "स्थिती": "त्रुटी",
            "संदेश": str(e)
        }), 500

@app.route('/update_loss', methods=['POST'])
def update_loss():
    """तोटा अपडेट करा"""
    try:
        data = request.json
        loss_amount = float(data.get('loss', 0))
        
        trading_state.current_loss = loss_amount
        loss_percentage = calculate_loss_percentage(
            trading_state.total_capital - loss_amount
        )
        
        logger.info(f"📉 तोटा अपडेट: ₹{loss_amount} ({loss_percentage:.2f}%)")
        
        # 20% तोटा झाला का तपासा
        if loss_percentage >= MAX_LOSS_PERCENTAGE:
            trading_state.trading_enabled = False
            logger.warning(f"🚨 20% तोटा झाला! ट्रेडिंग बंद.")
        
        return jsonify({
            "स्थिती": "यशस्वी",
            "तोटा": loss_amount,
            "तोटा_टक्के": f"{loss_percentage:.2f}%",
            "ट्रेडिंग_स्टेटस": "सक्रिय" if trading_state.trading_enabled else "बंद"
        })
        
    except Exception as e:
        return jsonify({"त्रुटी": str(e)}), 500

@app.route('/reset_daily', methods=['POST'])
def reset_daily():
    """दिवसाचा काउंटर रिसेट करा"""
    trading_state.daily_trade_count = 0
    trading_state.trade_history = []
    trading_state.last_reset_date = datetime.date.today()
    
    logger.info("🔄 दिवसाचा काउंटर रिसेट केला")
    
    return jsonify({
        "स्थिती": "यशस्वी",
        "संदेश": "दिवसाचा काउंटर रिसेट केला",
        "ट्रेड_काउंट": 0
    })

@app.route('/get_state')
def get_state():
    """सर्व स्टेट माहिती मिळवा"""
    can_trade, message = can_place_trade()
    
    return jsonify({
        "दिनांक": trading_state.last_reset_date.isoformat(),
        "आजचे_ट्रेड्स": trading_state.daily_trade_count,
        "मॅक्स_ट्रेड्स": MAX_DAILY_TRADES,
        "बाकी_ट्रेड्स": MAX_DAILY_TRADES - trading_state.daily_trade_count,
        "ट्रेडिंग_परवानगी": can_trade,
        "संदेश": message,
        "कॅपिटल": trading_state.total_capital,
        "सध्याचा_तोटा": trading_state.current_loss,
        "तोटा_टक्के": f"{calculate_loss_percentage(trading_state.total_capital - trading_state.current_loss):.2f}%",
        "ट्रेडिंग_वेळ": is_trading_time(),
        "वर्तमान_वेळ": datetime.datetime.now().strftime("%H:%M:%S"),
        "ट्रेड_इतिहास": trading_state.trade_history[-5:]  # शेवटचे 5 ट्रेड्स
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
    
    app.run(host='0.0.0.0', port=10000, debug=False)
