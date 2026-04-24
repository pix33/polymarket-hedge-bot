import os
import time
import json
import sqlite3
import threading
import logging
from datetime import datetime
from typing import Optional
from flask import Flask, render_template, jsonify, request

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='/app/templates')

# Configuration
HOST = "0.0.0.0"
PORT = 5005
DB_PATH = os.environ.get('DB_PATH', '/app/data/hedge.db')

# CLOB Client
PRIVATE_KEY = os.environ.get('PRIVATE_KEY', '')
POLYMARKET_API = "https://clob.polymarket.com"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Trades table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            token TEXT NOT NULL,
            condition_id TEXT,
            first_leg_outcome TEXT,
            first_leg_price REAL,
            first_leg_shares REAL,
            first_leg_usdc REAL,
            first_leg_order_id TEXT,
            second_leg_outcome TEXT,
            second_leg_price REAL,
            second_leg_shares REAL,
            second_leg_usdc REAL,
            second_leg_order_id TEXT,
            status TEXT DEFAULT 'pending_second',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        )
    ''')
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Initialize default settings
    defaults = {
        'first_leg_min_price': '0.60',
        'first_leg_max_price': '0.70',
        'second_leg_threshold': '0.02',
        'max_concurrent_trades': '5',
        'min_market_volume': '10000',
        'trade_amount': '10.00',
        'enabled': 'false'
    }
    
    for key, value in defaults.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    conn.commit()
    conn.close()

def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    rows = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}

def update_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()

def get_open_trades_count():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM trades WHERE status IN ('pending_second', 'open')")
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0

def get_active_markets():
    """Fetch active markets from Polymarket"""
    import requests
    
    url = "https://clob.polymarket.com/markets"
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching markets: {e}")
    
    return []

def get_market_details(token):
    """Get full market details including outcomes"""
    import requests
    
    url = f"https://clob.polymarket.com/markets/{token}"
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching market {token}: {e}")
    
    return None

def place_order(token, outcome, amount):
    """Place a buy order on Polymarket CLOB"""
    import requests
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs
    from py_clob_client.client import MarkovClient
    
    # This is a placeholder - we'll implement actual order placement
    # For now, just log the attempt
    logger.info(f"Would place order: token={token}, outcome={outcome}, amount={amount}")
    
    # TODO: Implement actual order placement using py-clob-client
    # The wallet private key needs to be set up properly
    
    return None

class HedgeBot:
    def __init__(self):
        self.running = False
        self.threads = []
        
    def start(self):
        if self.running:
            return
        self.running = True
        t = threading.Thread(target=self._run)
        t.daemon = True
        t.start()
        self.threads.append(t)
        logger.info("Hedge bot started")
        
    def stop(self):
        self.running = False
        logger.info("Hedge bot stopped")
        
    def _run(self):
        while self.running:
            try:
                settings = get_settings()
                if settings.get('enabled') == 'true':
                    self.scan_and_trade(settings)
            except Exception as e:
                logger.error(f"Error in bot loop: {e}")
            
            time.sleep(30)  # Scan every 30 seconds
    
    def scan_and_trade(self, settings):
        """Scan markets and execute hedge strategy"""
        open_count = get_open_trades_count()
        max_concurrent = int(settings.get('max_concurrent_trades', 5))
        
        if open_count >= max_concurrent:
            logger.info(f"Max concurrent trades reached: {open_count}/{max_concurrent}")
            return
        
        markets = get_active_markets()
        logger.info(f"Found {len(markets)} markets")
        
        # TODO: Filter and trade
        # 1. Get markets with 2 outcomes
        # 2. Check volume >= min_market_volume
        # 3. Check if any side price in first leg range
        # 4. Place first leg if conditions met
        # 5. Monitor for second leg trigger

# Initialize
init_db()
bot = HedgeBot()

# Routes
@app.route('/')
def index():
    settings = get_settings()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all trades with P&L
    cursor.execute('''
        SELECT *, 
            (first_leg_usdc + second_leg_usdc) as total_spent,
            CASE 
                WHEN first_leg_shares > second_leg_shares THEN first_leg_shares
                ELSE second_leg_shares
            END as max_payout
        FROM trades
        ORDER BY created_at DESC
        LIMIT 50
    ''')
    trades = cursor.fetchall()
    
    # Calculate stats
    cursor.execute("SELECT COUNT(*) as total FROM trades")
    total_trades = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as open_count FROM trades WHERE status IN ('pending_second', 'open')")
    open_trades = cursor.fetchone()['open_count']
    
    conn.close()
    
    # Get stats
    cursor.execute('''
        SELECT 
            COALESCE(SUM(first_leg_usdc + second_leg_usdc), 0) as total_spent,
            COALESCE(SUM(CASE 
                WHEN first_leg_shares > second_leg_shares THEN first_leg_shares
                ELSE second_leg_shares
            END), 0) as total_payout
        FROM trades 
        WHERE status = 'closed'
    ''')
    result = cursor.fetchone()
    total_spent = result['total_spent'] or 0
    total_payout = result['total_payout'] or 0
    total_pnl = total_payout - total_spent
    
    stats = {
        'enabled': settings.get('enabled') == 'true',
        'open_trades': open_trades,
        'max_concurrent': settings.get('max_concurrent_trades'),
        'total_pnl': total_pnl,
        'total_spent': total_spent
    }
    
    return render_template('index.html', 
                         settings=settings, 
                         trades=trades,
                         total_trades=total_trades,
                         open_trades=open_trades,
                         stats=stats)

@app.route('/api/settings', methods=['POST'])
def api_settings():
    data = request.json
    for key, value in data.items():
        update_setting(key, value)
    return jsonify({'success': True})

@app.route('/api/trades')
def api_trades():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM trades ORDER BY created_at DESC LIMIT 50')
    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(trades)

@app.route('/api/stats')
def api_stats():
    settings = get_settings()
    open_count = get_open_trades_count()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Calculate total P&L
    cursor.execute('''
        SELECT 
            SUM(first_leg_usdc + second_leg_usdc) as total_spent,
            SUM(CASE 
                WHEN first_leg_shares > second_leg_shares THEN first_leg_shares
                ELSE second_leg_shares
            END) as total_payout
        FROM trades 
        WHERE status = 'closed'
    ''')
    result = cursor.fetchone()
    
    total_spent = result['total_spent'] or 0
    total_payout = result['total_payout'] or 0
    total_pnl = total_payout - total_spent
    
    conn.close()
    
    return jsonify({
        'enabled': settings.get('enabled') == 'true',
        'open_trades': open_count,
        'max_concurrent': settings.get('max_concurrent_trades'),
        'total_pnl': total_pnl,
        'total_spent': total_spent
    })

@app.route('/api/toggle', methods=['POST'])
def api_toggle():
    settings = get_settings()
    current = settings.get('enabled') == 'true'
    update_setting('enabled', 'false' if current else 'true')
    
    if not current:
        bot.start()
    else:
        bot.stop()
    
    return jsonify({'enabled': not current})

if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=False)