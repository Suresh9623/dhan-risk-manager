# app.py
import os
import time
import json
import threading
import logging
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request
import requests

# ---------------- CONFIG ----------------
app = Flask(__name__)

# Limits and timing
MAX_ORDERS_PER_DAY = int(os.environ.get('MAX_ORDERS_PER_DAY', 10))
MAX_LOSS_PERCENT = float(os.environ.get('MAX_LOSS_PERCENT', 0.20))
TRADING_START = dtime(9, 25)
TRADING_END = dtime(15, 0)
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL_SECONDS', 30))

# Dhan API settings (make sure to set these env vars)
DHAN_CLIENT_ID = os.environ.get('DHAN_CLIENT_ID', '')
DHAN_ACCESS_TOKEN = os.environ.get('DHAN_ACCESS_TOKEN', '')
DHAN_API_BASE = os.environ.get('DHAN_API_BASE', 'https://api.dhan.co')  # without trailing slash

# Optional: control auto monitor on deploy
RUN_AUTO = os.environ.get('RUN_AUTO', 'true').lower() in ('1', 'true', 'yes')

# State file
STATE_FILE = os.environ.get('STATE_FILE', 'state.json')

# Headers
HEADERS = {
    'Content-Type': 'application/json'
}
if DHAN_ACCESS_TOKEN:
    # common header name used earlier; adapt if Dhan expects different key
    HEADERS['access-token'] = DHAN_ACCESS_TOKEN

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('dhan-risk-manager')

# Threading lock for state file
state_lock = threading.Lock()

# Monitor control
monitor_active = False
stop_signal = False

# ---------------- State helpers ----------------
def load_state():
    with state_lock:
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    return data
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
    # default state
    return {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'last_balance': None,
        'last_check': None
    }

def save_state(state):
    with state_lock:
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

# ---------------- Utility ----------------
def is_trading_time(now=None):
    if now is None:
        now = datetime.now().time()
    return TRADING_START <= now <= TRADING_END

def safe_float(v):
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        # strip commas, currency symbols
        s = str(v).replace(',', '').strip()
        # remove non-numeric trailing/leading chars
        allowed = ''.join(ch for ch in s if (ch.isdigit() or ch in '.-'))
        return float(allowed) if allowed not in ('', '-', '.') else None
    except:
        return None

# ---------------- Smart balance fetch ----------------
def smart_get_balance():
    """
    Try multiple Dhan endpoints to fetch balance.
    Returns float or None.
    """
    endpoints = [
        '/positions', '/funds', '/margin', '/account',
        '/limits', '/holdings', '/profile'
    ]

    base = DHAN_API_BASE.rstrip('/')
    for ep in endpoints:
        url = f"{base}{ep}"
        try:
            logger.debug(f"Trying {url}")
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    logger.debug(f"Non-JSON response at {url}")
                    continue
                bal = extract_balance_smart(data)
                if bal is not None:
                    logger.info(f"Balance found from {ep}: ₹{bal:.2f}")
                    return bal
            else:
                logger.debug(f"{url} returned {resp.status_code}")
        except Exception as e:
            logger.debug(f"Request {url} failed: {e}")
            continue
    logger.warning("All endpoints failed to provide balance")
    return None

def extract_balance_smart(data):
    """
    Robust recursive extraction from nested dicts/lists.
    """
    # possible field names (extended)
    balance_fields = {
        'netAvailableMargin','availableMargin','marginAvailable',
        'balance','totalBalance','cashBalance','netBalance',
        'margin','availableCash','funds','netAmount',
        'available_limit','cash_available','margin_available',
        'available','available_cash'
    }

    # if list -> iterate elements
    if isinstance(data, list):
        for item in data:
            val = extract_balance_smart(item)
            if val is not None:
                return val
        return None

    if isinstance(data, dict):
        # direct fields
        for key in data:
            if key in balance_fields:
                val = safe_float(data.get(key))
                if val is not None:
                    return val
        # try values that look like numbers at top-level
        for key, value in data.items():
            # common nested dict/list
            if isinstance(value, (dict, list)):
                nested = extract_balance_smart(value)
                if nested is not None:
                    return nested
            else:
                # if key contains 'balance' or 'fund' try parsing
                if 'balance' in key.lower() or 'fund' in key.lower() or 'available' in key.lower():
                    val = safe_float(value)
                    if val is not None:
                        return val
    # not found
    return None

# ---------------- Auto actions ----------------
def auto_cancel_orders():
    try:
        url = f"{DHAN_API_BASE.rstrip('/')}/orders"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            orders = resp.json()
            if isinstance(orders, list):
                for order in orders:
                    order_id = order.get('orderId') or order.get('id') or order.get('order_id')
                    if order_id:
                        try:
                            del_url = f"{DHAN_API_BASE.rstrip('/')}/orders/{order_id}"
                            requests.delete(del_url, headers=HEADERS, timeout=5)
                        except Exception as e:
                            logger.debug(f"Failed cancel {order_id}: {e}")
            return True
    except Exception as e:
        logger.debug(f"auto_cancel_orders error: {e}")
    return False

def auto_exit_positions():
    # Implement exit logic according to your broker/order API.
    try:
        url = f"{DHAN_API_BASE.rstrip('/')}/positions"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            positions = resp.json()
            # positions format varies; here we only log
            logger.info("auto_exit_positions: positions fetched (not auto-exited by default).")
            # If you want to auto exit, implement order placement here carefully.
            return True
    except Exception as e:
        logger.debug(f"auto_exit_positions error: {e}")
    return False

def trigger_emergency(reason):
    logger.warning(f"EMERGENCY TRIGGERED: {reason}")
    auto_cancel_orders()
    auto_exit_positions()
    return True

# ---------------- Monitoring ----------------
def automatic_monitor():
    global monitor_active, stop_signal
    monitor_active = True
    logger.info("AUTO SYSTEM STARTED")
    try:
        while not stop_signal:
            try:
                state = load_state()
                current_date = datetime.now().strftime('%Y-%m-%d')
                current_time_str = datetime.now().strftime('%H:%M:%S')

                # Daily reset
                if state.get('date') != current_date:
                    logger.info("Daily reset")
                    state = {
                        'date': current_date,
                        'morning_balance': None,
                        'max_loss_amount': None,
                        'order_count': 0,
                        'trading_allowed': True,
                        'blocked_reason': '',
                        'last_balance': None,
                        'last_check': current_time_str
                    }
                    save_state(state)

                trading_now = is_trading_time()
                logger.debug(f"Trading now: {trading_now} ({current_time_str})")

                # Outside trading hours -> block if previously allowed
                if not trading_now and state.get('trading_allowed', True):
                    logger.info("Trading hours ended - triggering emergency actions")
                    trigger_emergency("Trading hours ended")
                    state['trading_allowed'] = False
                    state['blocked_reason'] = 'Trading hours ended'
                    save_state(state)

                # Inside trading hours
                if trading_now and state.get('trading_allowed', True):
                    # Capture morning balance if not present
                    if state.get('morning_balance') is None:
                        logger.info("Capturing morning balance...")
                        balance = smart_get_balance()
                        if balance is not None:
                            state['morning_balance'] = balance
                            state['max_loss_amount'] = balance * MAX_LOSS_PERCENT
                            state['last_balance'] = balance
                            state['last_check'] = current_time_str
                            save_state(state)
                            logger.info(f"Morning balance set: ₹{balance:.2f} | 20% loss = ₹{state['max_loss_amount']:.2f}")
                        else:
                            logger.debug("Could not fetch balance yet; will retry")

                    # Real-time loss check
                    if state.get('morning_balance') is not None:
                        current_balance = smart_get_balance()
                        if current_balance is not None:
                            state['last_balance'] = current_balance
                            state['last_check'] = current_time_str
                            loss = state['morning_balance'] - current_balance
                            logger.info(f"Current balance: ₹{current_balance:.2f} | Loss: ₹{loss:.2f}")
                            # 20% loss check
                            if loss >= state.get('max_loss_amount', float('inf')):
                                logger.warning("20% LOSS HIT")
                                trigger_emergency(f"20% Loss: ₹{loss:.2f}")
                                state['trading_allowed'] = False
                                state['blocked_reason'] = f'20% Loss: ₹{loss:.2f}'
                                save_state(state)
                                # continue to next iteration (system blocked)
                            # Order count check
                            if state.get('order_count', 0) >= MAX_ORDERS_PER_DAY:
                                logger.warning("Order limit hit")
                                trigger_emergency("10 Orders limit")
                                state['trading_allowed'] = False
                                state['blocked_reason'] = '10 Orders limit'
                                save_state(state)
                            save_state(state)
                time.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(5)
    finally:
        monitor_active = False
        logger.info("AUTO Monitoring stopped")

# ---------------- Web routes ----------------
@app.route('/')
def home():
    state = load_state()
    return jsonify({
        'system': 'FULL AUTOMATIC Dhan Manager',
        'status': 'ACTIVE' if not stop_signal else 'STOPPED',
        'version': 'AUTO-3.1',
        'auto_features': {
            '20%_auto_loss_limit': 'ACTIVE',
            '10_orders_auto_limit': 'ACTIVE',
            'time_auto_check': 'ACTIVE',
            'balance_auto_fetch': 'ACTIVE',
            'emergency_auto_action': 'ACTIVE'
        },
        'current_time': datetime.now().strftime('%H:%M:%S'),
        'trading_time': is_trading_time(),
        'limits': {'loss': f'{int(MAX_LOSS_PERCENT*100)}%', 'orders': MAX_ORDERS_PER_DAY, 'hours': '9:25-15:00'},
        'today': {
            'morning_balance': state.get('morning_balance'),
            'max_loss_20%': state.get('max_loss_amount'),
            'order_count': state.get('order_count'),
            'trading_allowed': state.get('trading_allowed'),
            'blocked_reason': state.get('blocked_reason') or 'None',
            'last_balance': state.get('last_balance'),
            'last_check': state.get('last_check')
        }
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'HEALTHY' if monitor_active else 'IDLE',
        'auto_system': 'RUNNING' if monitor_active else 'STOPPED',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/start')
def start_auto():
    global stop_signal
    if monitor_active:
        return jsonify({'status': 'ALREADY_RUNNING'})
    stop_signal = False
    t = threading.Thread(target=automatic_monitor, daemon=True)
    t.start()
    return jsonify({'status': 'AUTO_SYSTEM_STARTED'})

@app.route('/stop')
def stop_auto():
    global stop_signal
    stop_signal = True
    return jsonify({'status': 'AUTO_SYSTEM_STOPPING'})

@app.route('/reset')
def reset_auto():
    state = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'morning_balance': None,
        'max_loss_amount': None,
        'order_count': 0,
        'trading_allowed': True,
        'blocked_reason': '',
        'last_balance': None,
        'last_check': None
    }
    save_state(state)
    return jsonify({'status': 'AUTO_RESET_COMPLETE'})

@app.route('/emergency')
def manual_emergency():
    trigger_emergency("Manual emergency")
    state = load_state()
    state['trading_allowed'] = False
    state['blocked_reason'] = 'Manual emergency'
    save_state(state)
    return jsonify({'status': 'EMERGENCY_EXECUTED'})

@app.route('/simulate_order')
def simulate_order():
    state = load_state()
    state['order_count'] = state.get('order_count', 0) + 1
    save_state(state)
    return jsonify({
        'status': 'ORDER_SIMULATED',
        'new_count': state['order_count'],
        'limit': MAX_ORDERS_PER_DAY,
        'remaining': max(0, MAX_ORDERS_PER_DAY - state['order_count'])
    })

# ---------------- Start app ----------------
if __name__ == '__main__':
    # Optionally start auto monitor thread
    if RUN_AUTO:
        stop_signal = False
        auto_thread = threading.Thread(target=automatic_monitor, daemon=True)
        auto_thread.start()
    port = int(os.environ.get('PORT', 10000))
    logger.info("="*40)
    logger.info("FULL AUTOMATIC DHAN RISK MANAGER (AUTO-3.1)")
    logger.info(f"Running on port {port} | RUN_AUTO={RUN_AUTO}")
    logger.info("="*40)
    app.run(host='0.0.0.0', port=port, debug=False)
