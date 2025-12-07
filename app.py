import os
import time
import logging
from datetime import datetime, time as dtime
from flask import Flask, jsonify
import threading

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment Variables
DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")
TWILIO_SID = os.getenv("TWILIO_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "")

# Global state
monitoring_active = False
start_balance = None
orders_today = 0
last_check = None

class DhanManager:
    def __init__(self):
        self.client = None
        self.setup_dhan()
    
    def setup_dhan(self):
        """Initialize DHAN client"""
        try:
            from dhanhq import dhanhq
            self.client = dhanhq(DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN)
            logger.info("✅ DHAN Client initialized")
            return True
        except ImportError:
            logger.error("❌ 'dhanhq' package not installed. Add 'dhanhq' to requirements.txt")
            return False
        except Exception as e:
            logger.error(f"❌ DHAN Setup error: {e}")
            return False
    
    def get_balance(self):
        """Get available balance"""
        try:
            if self.client:
                # DHAN balance API call
                response = self.client.get_funds_limits()
                if response and 'data' in response:
                    return response['data'].get('availableMargin', 0)
        except Exception as e:
            logger.error(f"Balance error: {e}")
        return None
    
    def get_positions(self):
        """Get current positions"""
        try:
            if self.client:
                response = self.client.get_positions()
                return response.get('data', [])
        except Exception as e:
            logger.error(f"Positions error: {e}")
        return []
    
    def get_today_orders(self):
        """Get today's orders count"""
        try:
            if self.client:
                response = self.client.order_book()
                orders = response.get('data', [])
                today = datetime.now().date()
                
                count = 0
                for order in orders:
                    order_time = datetime.strptime(
                        order.get('orderTimestamp', '1970-01-01'), 
                        '%Y-%m-%d %H:%M:%S'
                    ).date()
                    if order_time == today:
                        count += 1
                return count
        except Exception as e:
            logger.error(f"Orders error: {e}")
        return 0
    
    def square_off_all(self):
        """Square off all positions"""
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos.get('netQty', 0) != 0:
                    # Market order to close
                    order_args = {
                        "transaction_type": self.client.SELL if pos['netQty'] > 0 else self.client.BUY,
                        "exchange_segment": pos['exchangeSegment'],
                        "product_type": self.client.INTRADAY,
                        "order_type": self.client.MARKET,
                        "quantity": abs(pos['netQty']),
                        "security_id": str(pos['securityId'])
                    }
                    self.client.place_order(**order_args)
            return True
        except Exception as e:
            logger.error(f"Square-off error: {e}")
            return False

# Create instance
dhan = DhanManager()

def send_whatsapp_alert(message):
    """Send WhatsApp notification"""
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        message = client.messages.create(
            body=f"🛡️ DHAN Risk Manager: {message}",
            from_='whatsapp:+14155238886',
            to=f'whatsapp:+91{WHATSAPP_TO}'
        )
        logger.info(f"📱 WhatsApp sent: {message.body}")
        return True
    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        return False

def monitor_market():
    """Main monitoring function"""
    global monitoring_active, start_balance, orders_today, last_check
    
    while monitoring_active:
        try:
            now = datetime.now()
            current_time = now.time()
            last_check = now
            
            # 1. Check if within market hours (9:15 AM - 3:30 PM IST)
            market_start = dtime(9, 15)  # 9:15 AM
            market_end = dtime(15, 30)   # 3:30 PM
            
            if current_time < market_start or current_time > market_end:
                time.sleep(60)
                continue
            
            # 2. Morning setup (9:25 AM)
            if current_time >= dtime(9, 25) and current_time <= dtime(9, 26):
                if start_balance is None:
                    balance = dhan.get_balance()
                    if balance:
                        start_balance = balance
                        send_whatsapp_alert(f"✅ Trading Started | Balance: ₹{balance:,}")
            
            # 3. Get current data
            orders_today = dhan.get_today_orders()
            positions = dhan.get_positions()
            
            # 4. Check order limit (10 orders/day)
            if orders_today >= 10:
                send_whatsapp_alert(f"🚫 10/10 Orders Limit Reached!")
                monitoring_active = False
                continue
            
            # 5. Check loss limit (20%)
            if start_balance:
                total_pnl = sum([pos.get('realizedPnl', 0) + pos.get('unrealizedPnl', 0) 
                               for pos in positions])
                
                if total_pnl < 0:
                    loss_percent = abs(total_pnl) / start_balance
                    if loss_percent >= 0.20:  # 20%
                        send_whatsapp_alert(f"🚨 20% Loss Limit Hit! P&L: ₹{total_pnl:,.2f}")
                        dhan.square_off_all()
                        monitoring_active = False
                        continue
            
            # 6. EOD Auto Exit (3:25 PM)
            if current_time >= dtime(15, 25) and current_time <= dtime(15, 26):
                if positions:
                    send_whatsapp_alert("⏰ Market Closing - Auto Exit")
                    dhan.square_off_all()
            
            # Sleep for 30 seconds
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(60)

# Flask Routes
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>DHAN Risk Manager</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial; padding: 20px; background: #f5f5f5; }
            .container { max-width: 800px; margin: auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .btn { padding: 10px 20px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
            .start { background: #4CAF50; color: white; }
            .stop { background: #f44336; color: white; }
            .status { padding: 15px; margin: 10px 0; border-radius: 5px; }
            .active { background: #d4edda; border: 1px solid #c3e6cb; }
            .inactive { background: #f8d7da; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🛡️ DHAN Risk Manager</h1>
            <p>Auto risk management for DHAN Demat account</p>
            
            <div class="status" id="statusDiv">
                <h3>Status: <span id="statusText">Loading...</span></h3>
                <p>Last Check: <span id="lastCheck">-</span></p>
                <p>Start Balance: <span id="startBalance">-</span></p>
                <p>Orders Today: <span id="ordersCount">-</span></p>
            </div>
            
            <button class="btn start" onclick="startMonitor()">▶️ Start Monitoring</button>
            <button class="btn stop" onclick="stopMonitor()">⏹️ Stop Monitoring</button>
            
            <hr>
            
            <h3>Rules:</h3>
            <ul>
                <li>✅ Max 10 orders/day</li>
                <li>✅ Max 20% loss/day</li>
                <li>✅ Auto exit at 3:25 PM</li>
                <li>✅ WhatsApp alerts</li>
            </ul>
            
            <p><a href="/status" target="_blank">API Status</a> | 
               <a href="/test-alert" target="_blank">Test Alert</a> |
               <a href="/logs" target="_blank">View Logs</a></p>
        </div>
        
        <script>
            function updateStatus() {
                fetch('/api/status')
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('statusText').innerText = data.monitoring_active ? 'ACTIVE 🔵' : 'INACTIVE 🔴';
                        document.getElementById('lastCheck').innerText = data.last_check || '-';
                        document.getElementById('startBalance').innerText = data.start_balance ? '₹' + data.start_balance.toLocaleString() : '-';
                        document.getElementById('ordersCount').innerText = data.orders_today || '0';
                        
                        let statusDiv = document.getElementById('statusDiv');
                        statusDiv.className = data.monitoring_active ? 'status active' : 'status inactive';
                    });
            }
            
            function startMonitor() {
                fetch('/api/start', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        alert(data.message || 'Started');
                        updateStatus();
                    });
            }
            
            function stopMonitor() {
                fetch('/api/stop', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        alert(data.message || 'Stopped');
                        updateStatus();
                    });
            }
            
            // Update every 10 seconds
            setInterval(updateStatus, 10000);
            updateStatus();
        </script>
    </body>
    </html>
    """

@app.route('/api/status')
def api_status():
    return jsonify({
        'monitoring_active': monitoring_active,
        'start_balance': start_balance,
        'orders_today': orders_today,
        'last_check': last_check.strftime('%H:%M:%S') if last_check else None,
        'server_time': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/api/start', methods=['POST'])
def start_monitoring():
    global monitoring_active
    if not monitoring_active:
        monitoring_active = True
        thread = threading.Thread(target=monitor_market, daemon=True)
        thread.start()
        return jsonify({'message': 'Monitoring started', 'status': 'active'})
    return jsonify({'message': 'Already running', 'status': 'active'})

@app.route('/api/stop', methods=['POST'])
def stop_monitoring():
    global monitoring_active
    monitoring_active = False
    return jsonify({'message': 'Monitoring stopped', 'status': 'inactive'})

@app.route('/test-alert')
def test_alert():
    success = send_whatsapp_alert("✅ Test Alert: System is working!")
    return jsonify({'success': success, 'message': 'Test alert sent'})

@app.route('/logs')
def view_logs():
    return jsonify({
        'logs': 'View logs in Render dashboard',
        'url': 'https://dashboard.render.com/'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Starting DHAN Risk Manager on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
