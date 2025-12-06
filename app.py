from flask import Flask, jsonify
from datetime import datetime
import pytz

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "app": "Dhan Risk Manager",
        "status": "ready",
        "time": datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%H:%M:%S")
    })

if __name__ == '__main__':
    app.run(port=5000)
