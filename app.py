import os, time, json, threading, requests
from datetime import datetime, time as dtime
import pytz
from flask import Flask, jsonify

# -------------------------
# CONFIG FROM ENV - ⭐ तुझे नवीन LIMITS इथे ⭐
# -------------------------
CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "")
ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")
BASE_URL = os.getenv("DHAN_BASE_URL", "https://api.dhan.co")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ⭐⭐⭐ तुझे नवीन LIMITS ⭐⭐⭐
MAX_ORDERS_PER_DAY = int(os.getenv("MAX_ORDERS_PER_DAY", "10"))      # 10 orders/day
MAX_LOSS_PERCENT = float(os.getenv("MAX_LOSS_PERCENT", "0.20"))     # 20% loss limit
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

TRADING_START = dtime(int(os.getenv("TR_START_H", "9")), int(os.getenv("TR_START_M", "25")))
TRADING_END = dtime(int(os.getenv("TR_END_H", "15")), int(os.getenv("TR_END_M", "0")))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "5"))

STATE_FILE = os.getenv("STATE_FILE", "state.json")
TIMEZONE = pytz.timezone(os.getenv("TZ", "Asia/Kolkata"))

HEADERS = {
    "access-token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

# -------------------------
# Flask app
# -------------------------
app = Flask(__name__)
monitor_thread = None
stop_signal = False

def current_date_str():
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")

def now_time():
    return datetime.now(TIMEZONE).time()

def is_trading_time():
    t = now_time()
    return TRADING_START <= t <= TRADING_END

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                st = json.load(f)
        except Exception:
            st = {}
    else:
        st = {}
    st.setdefault("date", current_date_str())
    st.setdefault("morning_balance", None)
    st.setdefault("max_loss_amount", None)
    st.setdefault("order_count", 0)
    st.setdefault("trading_allowed", True)
    st.setdefault("blocked_reason", "")
    return st

def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)

def send_telegram(msg):
    try:
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception:
        pass

def get_fund_details():
    try:
        resp = requests.get(f"{BASE_URL}/funds", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return float(data.get("netAvailableMargin", 0))
    except Exception as e:
        print("get_fund_details error:", e)
        return None

def get_positions():
    try:
        resp = requests.get(f"{BASE_URL}/positions", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json() or []
    except Exception as e:
        print("get_positions error:", e)
        return []

def get_pending_orders():
    try:
        resp = requests.get(f"{BASE_URL}/orders", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json() or []
    except Exception as e:
        print("get_pending_orders error:", e)
        return []

def cancel_order(order_id):
    try:
        resp = requests.delete(f"{BASE_URL}/orders/{order_id}", headers=HEADERS, timeout=10)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print("cancel_order error:", e)
        return False

def place_exit_order_for_position(p):
    try:
        qty = abs(int(float(p.get("netQty", 0))))
        if qty == 0:
            return None
        transactionType = "SELL" if float(p.get("netQty")) > 0 else "BUY"
        payload = {
            "dhanClientId": CLIENT_ID,
            "transactionType": transactionType,
            "exchangeSegment": p.get("exchangeSegment", "NSE"),
            "productType": p.get("productType", "CNC"),
            "orderType": "MARKET",
            "validity": "DAY",
            "securityId": p.get("securityId"),
            "quantity": qty
        }
        resp = requests.post(f"{BASE_URL}/orders", json=payload, headers=HEADERS, timeout=10)
        return resp.status_code in (200, 201)
    except Exception as e:
        print("place_exit_order error:", e)
        return False

def cancel_all_orders():
    orders = get_pending_orders()
    for o in orders:
        oid = o.get("orderId") or o.get("id") or o.get("order_id")
        if oid:
            ok = cancel_order(oid)
            print(f"cancel {oid} -> {ok}")
            send_telegram(f"Cancelled order: {oid}")
    return True

def exit_all_positions():
    positions = get_positions()
    for p in positions:
        try:
            netq = float(p.get("netQty", 0))
        except:
            netq = 0
        if netq != 0:
            ok = place_exit_order_for_position(p)
            print(f"exit pos {p.get('securityId')} qty {netq} -> {ok}")
            send_telegram(f"Exited position: {p.get('securityId')} qty {netq}")
    return True

def emergency_exit_and_block(state, reason):
    print("EMERGENCY:", reason)
    send_telegram(f"🚨 EMERGENCY: {reason} at {datetime.now(TIMEZONE)}")
    cancel_all_orders()
    exit_all_positions()
    state["trading_allowed"] = False
    state["blocked_reason"] = reason
    save_state(state)

def monitor_loop():
    global stop_signal
    print("Monitor thread started")
    send_telegram("🤖 Dhan Risk Manager started successfully")
    
    while not stop_signal:
        try:
            state = load_state()
            
            if state["date"] != current_date_str():
                state = {
                    "date": current_date_str(),
                    "morning_balance": None,
                    "max_loss_amount": None,
                    "order_count": 0,
                    "trading_allowed": True,
                    "blocked_reason": ""
                }
                save_state(state)
                send_telegram("🔄 New day started - counters reset")
                time.sleep(2)
                continue

            if state["morning_balance"] is None and is_trading_time():
                fb = get_fund_details()
                if fb is not None and fb > 0:
                    state["morning_balance"] = fb
                    # ⭐ 20% loss limit calculation ⭐
                    state["max_loss_amount"] = fb * MAX_LOSS_PERCENT  # fb * 0.20
                    save_state(state)
                    send_telegram(f"🌅 Morning balance: ₹{fb:.2f} | Max loss (20%): ₹{state['max_loss_amount']:.2f}")
                else:
                    print("Waiting for fund details...")
                time.sleep(CHECK_INTERVAL)
                continue

            if not is_trading_time():
                if state["trading_allowed"]:
                    emergency_exit_and_block(state, "⏰ Trading hours ended")
                time.sleep(30)
                continue

            cur_bal = get_fund_details()
            if cur_bal is None:
                time.sleep(CHECK_INTERVAL)
                continue

            if state["morning_balance"]:
                loss_amount = state["morning_balance"] - cur_bal
                print(f"[{datetime.now(TIMEZONE)}] Orders={state['order_count']} Morning={state['morning_balance']:.2f} Current={cur_bal:.2f} Loss={loss_amount:.2f}")

                # ⭐ 20% LOSS LIMIT CHECK ⭐
                if state["trading_allowed"] and loss_amount >= state["max_loss_amount"]:
                    emergency_exit_and_block(state, f"📉 20% Loss limit hit: ₹{loss_amount:.2f} >= ₹{state['max_loss_amount']:.2f}")
                    time.sleep(2)
                    continue

                # ⭐ 10 ORDERS/DAY LIMIT CHECK ⭐
                if state["trading_allowed"] and state["order_count"] >= MAX_ORDERS_PER_DAY:
                    emergency_exit_and_block(state, f"🔢 10 Orders limit: {state['order_count']} >= {MAX_ORDERS_PER_DAY}")
                    time.sleep(2)
                    continue

            if not state["trading_allowed"]:
                cancel_all_orders()
                
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            print("Monitor loop exception:", e)
            send_telegram(f"⚠️ Monitor error: {str(e)}")
            time.sleep(10)

@app.route("/")
def index():
    st = load_state()
    st.update({
        "now": str(datetime.now(TIMEZONE)),
        "is_trading_time": is_trading_time(),
        "trading_start": TRADING_START.strftime("%H:%M"),
        "trading_end": TRADING_END.strftime("%H:%M"),
        "max_orders": MAX_ORDERS_PER_DAY,        # 10
        "max_loss_percent": MAX_LOSS_PERCENT,    # 0.20 (20%)
        "monitor_status": "running" if not stop_signal else "stopped"
    })
    return jsonify(st)

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "timestamp": str(datetime.now(TIMEZONE))})

@app.route("/start")
def start_monitor():
    global monitor_thread, stop_signal
    if monitor_thread and monitor_thread.is_alive():
        return jsonify({"status": "already_running"})
    stop_signal = False
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    send_telegram("▶️ Monitor manually started")
    return jsonify({"status": "started"})

@app.route("/stop")
def stop_monitor():
    global stop_signal
    stop_signal = True
    send_telegram("⏹️ Monitor manually stopped")
    return jsonify({"status": "stopping"})

@app.route("/reset")
def reset_day():
    state = {
        "date": current_date_str(),
        "morning_balance": None,
        "max_loss_amount": None,
        "order_count": 0,
        "trading_allowed": True,
        "blocked_reason": ""
    }
    save_state(state)
    send_telegram("🔄 Day manually reset")
    return jsonify({"status": "reset", "new_state": state})

@app.route("/emergency")
def emergency_exit():
    state = load_state()
    emergency_exit_and_block(state, "🆘 Manual emergency exit")
    return jsonify({"status": "emergency_exit_executed"})

if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
else:
    print("Starting monitor thread...")
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
