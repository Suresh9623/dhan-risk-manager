import os
import time
import requests
import schedule
from datetime import datetime, time as dtime
from flask import Flask
from threading import Thread

app = Flask(__name__)

# Environment Variables (Render Dashboard वरून Set करायचे)
DHAN_API_KEY = os.getenv("DHAN_API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")

class DhanAutoRiskManager:
    def __init__(self):
        self.start_balance = None
        self.order_counter = 0
        self.trading_blocked = False
        self.max_orders = 10
        self.loss_limit = 0.20  # 20%
        
    def whatsapp_alert(self, message):
        """WhatsApp Message पाठवणे"""
        try:
            from twilio.rest import Client
            client = Client(TWILIO_SID, TWILIO_TOKEN)
            client.messages.create(
                body=f"⚠️ DHAN RISK MANAGER: {message}",
                from_='whatsapp:+14155238886',
                to=f'whatsapp:+91{WHATSAPP_NUMBER}'
            )
            print(f"WhatsApp Sent: {message}")
        except Exception as e:
            print(f"WhatsApp Error: {e}")
    
    def get_dhan_balance(self):
        """DHAN Balance Fetch"""
        try:
            url = "https://api.dhan.co/balance"
            headers = {"access-token": DHAN_API_KEY}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("available_margin", 0)
        except Exception as e:
            print(f"Balance Fetch Error: {e}")
        return None
    
    def get_dhan_positions(self):
        """Open Positions Fetch"""
        try:
            url = "https://api.dhan.co/positions"
            headers = {"access-token": DHAN_API_KEY}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Positions Error: {e}")
        return []
    
    def get_dhan_orders_today(self):
        """Today's Orders Count"""
        try:
            url = "https://api.dhan.co/orders"
            headers = {"access-token": DHAN_API_KEY}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                orders = response.json()
                today = datetime.now().date()
                today_orders = [o for o in orders if 
                              datetime.strptime(o["orderTimestamp"], "%Y-%m-%d %H:%M:%S").date() == today]
                return len(today_orders)
        except Exception as e:
            print(f"Orders Error: {e}")
        return 0
    
    def emergency_exit_all(self):
        """सर्व Positions Exit"""
        try:
            positions = self.get_dhan_positions()
            headers = {"access-token": DHAN_API_KEY}
            
            for pos in positions:
                if pos.get("netQty", 0) != 0:
                    order_data = {
                        "symbol": pos["symbol"],
                        "exchange": pos["exchange"],
                        "transactionType": "SELL" if pos["netQty"] > 0 else "BUY",
                        "orderType": "MARKET",
                        "quantity": abs(pos["netQty"]),
                        "productType": "INTRADAY"
                    }
                    requests.post("https://api.dhan.co/orders", 
                                json=order_data, headers=headers, timeout=5)
            
            self.whatsapp_alert("🚨 EMERGENCY EXIT: All positions squared off")
            self.trading_blocked = True
        except Exception as e:
            print(f"Exit Error: {e}")
    
    def morning_routine(self):
        """9:25 AM चे Daily Setup"""
        if self.trading_blocked:
            self.trading_blocked = False
        
        balance = self.get_dhan_balance()
        if balance:
            self.start_balance = balance
            self.order_counter = 0
            self.whatsapp_alert(f"🟢 Trading Started | Balance: ₹{balance}")
    
    def monitor_task(self):
        """Main Monitoring Task (हर 30 सेकंद)"""
        now = datetime.now()
        current_time = now.time()
        
        # 1. Trading Hours Check (9:25 AM - 3:00 PM)
        if current_time < dtime(9, 25) or current_time > dtime(15, 0):
            return
        
        # 2. Morning Balance Capture (9:25 AM)
        if current_time >= dtime(9, 25) and current_time <= dtime(9, 26):
            if not self.start_balance:
                self.morning_routine()
        
        # 3. Order Count Check
        today_orders = self.get_dhan_orders_today()
        if today_orders >= self.max_orders and not self.trading_blocked:
            self.whatsapp_alert(f"📛 10/10 Orders Limit Reached! Trading Blocked")
            self.trading_blocked = True
        
        # 4. Loss Limit Check (20%)
        if self.start_balance and not self.trading_blocked:
            positions = self.get_dhan_positions()
            total_pnl = sum([pos.get("pnl", 0) for pos in positions])
            
            if total_pnl < 0:
                loss_percent = abs(total_pnl) / self.start_balance
                if loss_percent >= self.loss_limit:
                    self.whatsapp_alert(f"🚨 20% Loss Limit Hit! P&L: ₹{total_pnl}")
                    self.emergency_exit_all()
        
        # 5. EOD Auto Exit (2:55 PM)
        if current_time >= dtime(14, 55) and current_time <= dtime(14, 56):
            positions = self.get_dhan_positions()
            if positions:
                self.whatsapp_alert("⏰ Market Closing - Auto Exit")
                self.emergency_exit_all()

# Global Instance
risk_manager = DhanAutoRiskManager()

@app.route('/')
def home():
    return "✅ DHAN Risk Manager is RUNNING on RENDER!"

@app.route('/status')
def status():
    status_info = {
        "status": "active",
        "start_balance": risk_manager.start_balance,
        "orders_today": risk_manager.get_dhan_orders_today(),
        "trading_blocked": risk_manager.trading_blocked,
        "last_check": datetime.now().strftime("%H:%M:%S")
    }
    return status_info

def run_scheduler():
    """Background Scheduler"""
    # Morning Balance Capture
    schedule.every().day.at("09:25").do(risk_manager.morning_routine)
    
    # Every 30 Seconds Monitor
    schedule.every(30).seconds.do(risk_manager.monitor_task)
    
    # EOD Exit
    schedule.every().day.at("14:55").do(lambda: risk_manager.whatsapp_alert("EOD Exit Starting"))
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # Start Scheduler in Background Thread
    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start Flask App
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
