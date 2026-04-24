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
    
    # Activity log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_type TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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

def log_activity(activity_type, message, details=None):
    """Log an activity event"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO activity_log (activity_type, message, details) VALUES (?, ?, ?)',
        (activity_type, message, json.dumps(details) if details else None)
    )
    conn.commit()
    conn.close()

def get_activities(limit=50):
    """Get recent activities"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM activity_log 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Helper functions for logging trade events
def log_trade_success(market, outcome, price, shares, usdc):
    """Log successful trade"""
    log_activity('success', f'Bought {outcome} @ ${price:.2f}', {
        'market': market[:50],
        'shares': shares,
        'usdc': usdc
    })

def log_trade_failed(market, outcome, reason):
    """Log failed trade"""
    log_activity('failed', f'Failed to buy {outcome}', {
        'market': market[:50],
        'reason': reason
    })

def log_limit_order(market, outcome, price, shares):
    """Log limit order placed"""
    log_activity('order', f'Limit order: {outcome} @ ${price:.2f}', {
        'market': market[:50],
        'shares': shares
    })

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
                    self.check_pending_second_legs(settings)
            except Exception as e:
                logger.error(f"Error in bot loop: {e}")
            
            time.sleep(30)  # Scan every 30 seconds
    
    def check_pending_second_legs(self, settings):
        """Check pending second legs and place if threshold met"""
        import requests
        
        try:
            threshold = float(settings.get('second_leg_threshold', 0.02))
            trade_amount = float(settings.get('trade_amount', 10.00))
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades WHERE status = 'pending_second'
            ''')
            pending_trades = cursor.fetchall()
            conn.close()
            
            if not pending_trades:
                return
            
            # Get current prices for each pending trade
            url = "https://clob.polymarket.com/markets?closed=false"
            response = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
            
            if response.status_code != 200:
                return
            
            all_markets = response.json()
            
            for trade in pending_trades:
                token = trade['token']
                first_outcome = trade['first_leg_outcome']
                first_price = trade['first_leg_price']
                
                # Find market
                market_data = None
                for m in all_markets:
                    if m.get('conditionToken') == token:
                        market_data = m
                        break
                
                if not market_data:
                    continue
                
                outcomes = market_data.get('outcomes', [])
                prices = market_data.get('outcomePrices', [])
                
                if len(outcomes) != 2 or len(prices) != 2:
                    continue
                
                # Find opposite outcome
                try:
                    price0 = float(prices[0])
                    price1 = float(prices[1])
                except:
                    continue
                
                if outcomes[0] == first_outcome:
                    second_outcome = outcomes[1]
                    second_price = price1
                else:
                    second_outcome = outcomes[0]
                    second_price = price0
                
                # Calculate price change
                price_change = abs(second_price - first_price)
                
                if price_change >= threshold:
                    # Place second leg
                    self.place_second_leg(trade, second_outcome, second_price, trade_amount, settings)
                    
        except Exception as e:
            logger.error(f"Error checking pending second legs: {e}")
    
    def place_second_leg(self, trade, outcome, price, amount, settings):
        """Place the second leg of the hedge"""
        import requests
        
        try:
            shares = amount / price
            trade_id = trade['id']
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades SET 
                    second_leg_outcome = ?,
                    second_leg_price = ?,
                    second_leg_shares = ?,
                    second_leg_usdc = ?,
                    status = 'open'
                WHERE id = ?
            ''', (outcome, price, shares, amount, trade_id))
            conn.commit()
            conn.close()
            
            log_trade_success(trade['market'], outcome, price, shares, amount)
            logger.info(f"Second leg placed: {outcome} @ ${price}, trade_id={trade_id}")
            
            # TODO: Actually place the order on Polymarket
            
        except Exception as e:
            logger.error(f"Error placing second leg: {e}")
    
    def scan_and_trade(self, settings):
        """Scan markets and execute hedge strategy"""
        import requests
        
        open_count = get_open_trades_count()
        max_concurrent = int(settings.get('max_concurrent_trades', 5))
        
        if open_count >= max_concurrent:
            logger.info(f"Max concurrent trades reached: {open_count}/{max_concurrent}")
            return
        
        # Get settings
        first_leg_min = float(settings.get('first_leg_min_price', 0.60))
        first_leg_max = float(settings.get('first_leg_max_price', 0.70))
        min_volume = float(settings.get('min_market_volume', 10000))
        trade_amount = float(settings.get('trade_amount', 10.00))
        
        try:
            # Fetch markets with condition info
            url = "https://clob.polymarket.com/markets?closed=false"
            headers = {"Accept": "application/json"}
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch markets: {response.status_code}")
                return
            
            all_markets = response.json()
            logger.info(f"Found {len(all_markets)} total markets")
            
            # Filter markets
            for market in all_markets:
                try:
                    # Skip if not 2 outcomes
                    outcomes = market.get('outcomes', [])
                    if len(outcomes) != 2:
                        continue
                    
                    # Check volume
                    volume = float(market.get('volume24hr', 0) or 0)
                    if volume < min_volume:
                        continue
                    
                    # Get prices
                    prices = market.get('outcomePrices', [])
                    if not prices or len(prices) != 2:
                        continue
                    
                    # Parse prices
                    try:
                        price0 = float(prices[0])
                        price1 = float(prices[1])
                    except:
                        continue
                    
                    token = market.get('conditionToken', '')
                    market_question = market.get('question', '')
                    
                    # Check if first leg is in range
                    if first_leg_min <= price0 <= first_leg_max:
                        outcome = outcomes[0]
                        self.place_first_leg(market_question, token, outcome, price0, trade_amount, settings)
                    elif first_leg_min <= price1 <= first_leg_max:
                        outcome = outcomes[1]
                        self.place_first_leg(market_question, token, outcome, price1, trade_amount, settings)
                        
                except Exception as e:
                    logger.error(f"Error processing market: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in scan_and_trade: {e}")
    
    def place_first_leg(self, market, token, outcome, price, amount, settings):
        """Place the first leg of the hedge"""
        import requests
        
        try:
            # Calculate shares
            shares = amount / price
            
            # Save trade to DB
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (market, token, first_leg_outcome, first_leg_price, 
                                   first_leg_shares, first_leg_usdc, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending_second')
            ''', (market, token, outcome, price, shares, amount))
            trade_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Log activity
            log_trade_success(market, outcome, price, shares, amount)
            log_limit_order(market, outcome, price, shares)
            
            logger.info(f"First leg placed: {outcome} @ ${price}, {shares} shares, trade_id={trade_id}")
            
            # TODO: Actually place the order on Polymarket
            # For now, just log it - actual order placement requires proper wallet setup
            
        except Exception as e:
            logger.error(f"Error placing first leg: {e}")
            log_trade_failed(market, outcome, str(e))

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
    
    conn.close()
    
    # Get activities
    activities = get_activities(50)
    
    return render_template('index.html', 
                         settings=settings, 
                         trades=trades,
                         total_trades=total_trades,
                         open_trades=open_trades,
                         stats=stats,
                         activities=activities)

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
        log_activity('success', 'Bot started', {'enabled': True})
    else:
        bot.stop()
        log_activity('info', 'Bot stopped', {'enabled': False})
    
    return jsonify({'enabled': not current})

@app.route('/api/activity', methods=['GET'])
def api_activity():
    """Get activity log"""
    activities = get_activities(50)
    return jsonify(activities)

@app.route('/api/activity', methods=['POST'])
def api_log_activity():
    """Manually log activity"""
    data = request.json
    log_activity(
        data.get('type', 'info'),
        data.get('message', ''),
        data.get('details')
    )
    return jsonify({'success': True})

# Log initial startup
log_activity('info', 'Hedge bot started', {'version': '1.0'})

if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=False)