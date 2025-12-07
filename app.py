import os
import time
import json
import threading
from datetime import datetime, time as dtime
from flask import Flask, jsonify
import requests

# ============================================================
# CONFIG
# ============================================================
app = Flask(__name__)

MAX_ORDERS = 10
LOSS_LIMIT_PERCENT = 0.20
TRADING_START = dtime(9, 25)
TRADING_END = dtime(15, 0)
CHECK_INTERVAL = 30
STATE_FILE = "state.json"

# ============================================================
# DHAN CREDENTIALS
# ============================================================
DHAN_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")
DHAN_CLIENT = os.getenv("DHAN_CLIENT_ID", "")

HEADERS = {
    "access-token": DHAN_TOKEN,
    "Content-Type": "application/json"
}

# ============================================================
# STATE MANAGEMENT
# ============================================================
class TradingState:
    DEFAULT = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "morning_balance": None,
        "current_balance": None,
        "max_loss_amount": None,
        "order_count": 0,
        "trading_allowed": True,
        "blocked_reason": "",
        "last_check": None
    }

    def __init__(self):
        self.data = self.load()

    def load(self):
        if not os.path.exists(STATE_FILE):
            return self.DEFAULT.copy()
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
            for k, v in self.DEFAULT.items():
                if k not in saved:
                    saved[k] = v
            return saved
        except:
            return self.DEFAULT.copy()

    def save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def reset(self):
        self.data = self.DEFAULT.copy()
        self.data["date"] = datetime.now().strftime("%Y-%m-%d")
        self.save()

state = TradingState()

# ============================================================
# DHAN BALANCE FETCH
# ============================================================
def get_dhan_balance():
    """Stable balance fetch using multiple fallback endpoints."""
    endpoints = [
        ("https://api.dhan.co/funds", extract_balance_from_funds),
        ("https://api.dhan.co/positions", extract_balance_from_positions),
        ("https://api.dhan.co/margin", extract_balance_from_margin)
    ]

    for url, extractor in endpoints:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue

            data = r.json()
            bal = extractor(data)
            if bal:
                return round(float(bal), 2)
        except:
            continue

    return None

def extract_balance_from_funds(data):
    if not isinstance(data, dict):
        return None
    for key in ["availableMargin", "netAvailableMargin", "cashBalance", "totalBalance"]:
        if key in data:
            try:
                return float(str(data[key]).replace(",", ""))
            except:
                pass
    return None

def extract_balance_from_positions(data):
    if not isinstance(data, list) or not data:
        return None
    total = 0
    for p in data:
        try:
            if "currentValue" in p:
                total += float(p["currentValue"])
        except:
            pass
    return total if total > 0 else None

def extract_balance_from_margin(data):
    try:
        return float(data.get("availableMargin", 0))
    except:
        return None

# ============================================================
# CONDITION CHECKING
# ============================================================
def is_trading_time():
    now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def check_conditions():
    c = {
        "loss_limit": True,
        "order_limit": True,
        "trading_time": True,
        "morning_balance": True
    }

    # Trading hours
    if not is_trading_time():
        c["trading_time"] = False

    # Orders
    if state.data["order_count"] >= MAX_ORDERS:
        c["order_limit"] = False

    # 20% loss
    mb = state.data["morning_balance"]
    cb = state.data["current_balance"]

    if mb and cb:
        loss = mb - cb
        if loss >= state.data.get("max_loss_amount", 999999):
            c["loss_limit"] = False

    if not state.data["morning_balance"]:
        c["morning_balance"] = False

    all_ok = all(c.values())
    return c, all_ok

# ============================================================
# MONITOR LOOP
# ============================================================
monitoring = False
stop_flag = False

def monitor_loop():
    global monitoring, stop_flag
    monitoring = True
    print("📡 Monitoring Started")

    while not stop_flag:
        try:
            now_date = datetime.now().strftime("%Y-%m-%d")

            # Daily reset
            if state.data["date"] != now_date:
                state.reset()

            # Skip monitoring outside trading hours
            if not is_trading_time():
                time.sleep(60)
                continue

            # Morning balance
            if state.data["morning_balance"] is None:
                bal = get_dhan_balance()
                if bal:
                    state.data["morning_balance"] = bal
                    state.data["current_balance"] = bal
                    state.data["max_loss_amount"] = bal * LOSS_LIMIT_PERCENT
                    state.save()

            # Current balance
            bal = get_dhan_balance()
            if bal:
                state.data["current_balance"] = bal
                state.data["last_check"] = datetime.now().strftime("%H:%M:%S")
                state.save()

            # Check conditions
            conditions, all_ok = check_conditions()

            if not all_ok and state.data["trading_allowed"]:
                state.data["trading_allowed"] = False
                state.data["blocked_reason"] = "Condition Violation"
                state.save()

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Error:", e)
            time.sleep(30)

    monitoring = False
    print("⛔ Monitoring Stopped")

# ============================================================
# API ROUTES
# ============================================================
@app.route("/")
def home():
    bal = get_dhan_balance()
    if bal:
        state.data["current_balance"] = bal
        state.save()

    conditions, all_ok = check_conditions()
    mb = state.data["morning_balance"]
    cb = state.data["current_balance"]

    loss = (mb - cb) if (mb and cb) else 0
    percent = (loss / mb * 100) if (mb and cb) else 0

    return jsonify({
        "status": "RUNNING",
        "trading_allowed": state.data["trading_allowed"] and all_ok,
        "blocked_reason": state.data["blocked_reason"],
        "morning_balance": mb,
        "current_balance": cb,
        "loss": round(loss, 2),
        "loss_percent": round(percent, 2),
        "order_count": state.data["order_count"],
        "conditions": conditions,
        "time": datetime.now().strftime("%H:%M:%S")
    })

@app.route("/start")
def start_monitor():
    global stop_flag
    if not monitoring:
        stop_flag = False
        threading.Thread(target=monitor_loop, daemon=True).start()
        return jsonify({"started": True})
    return jsonify({"running": True})

@app.route("/stop")
def stop_monitor():
    global stop_flag
    stop_flag = True
    return jsonify({"stopping": True})

@app.route("/add_order")
def add_order():
    conditions, ok = check_conditions()
    if not ok or not state.data["trading_allowed"]:
        return jsonify({"status": "BLOCKED", "conditions": conditions})

    state.data["order_count"] += 1
    state.save()
    return jsonify({"status": "OK", "order_count": state.data["order_count"]})

@app.route("/reset")
def reset_day():
    state.reset()
    return jsonify({"reset": True})

# ============================================================
# END
# ============================================================
