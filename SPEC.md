# Polymarket Hedge Bot - Specification

## Overview
A trading bot that guarantees profit by buying both sides of a 2-outcome market when prices are favorable. Deploy on port 5005.

## Core Strategy

1. **First Leg**: Buy when a side's price is within configured range (e.g., $0.60-$0.70)
2. **Wait**: Monitor the opposite side
3. **Second Leg**: Buy opposite side when its price changes by configured threshold (e.g., $0.02)
4. **Lock in profit**: Both legs create a hedged position

## UI Controls

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| First Leg Min Price | float | 0.60 | Minimum price to buy first leg |
| First Leg Max Price | float | 0.70 | Maximum price to buy first leg |
| Second Leg Threshold | float | 0.02 | Price change on opposite side to trigger buy |
| Max Concurrent Trades | int | 5 | Maximum active markets to hold |
| Min Market Volume | float | 10000 | Minimum 24h volume to consider |
| Trade Amount | float | 10.00 | USDC amount per leg |

## Database Schema

### trades
- id (INTEGER PRIMARY KEY)
- market (TEXT)
- token (TEXT)
- first_leg_outcome (TEXT)
- first_leg_price (REAL)
- first_leg_shares (REAL)
- first_leg_usdc (REAL)
- first_leg_order_id (TEXT)
- second_leg_outcome (TEXT)
- second_leg_price (REAL)
- second_leg_shares (REAL)
- second_leg_usdc (REAL)
- second_leg_order_id (TEXT)
- status (TEXT) - 'open', 'closed'
- created_at (TIMESTAMP)
- closed_at (TIMESTAMP)

### settings
- key (TEXT PRIMARY KEY)
- value (TEXT)

## Endpoints

- GET / - Dashboard with all controls and P&L table
- POST /settings - Update bot settings
- GET /api/trades - Get all trades with P&L
- GET /api/stats - Get current stats

## Bot Behavior

1. Scan markets every 30 seconds
2. Filter by: 2 outcomes, volume >= Min Market Volume
3. Check if either side price is in First Leg range
4. If yes and below Max Concurrent Trades, place first leg buy
5. After first leg, poll every 5 seconds
6. When opposite side changes by >= Second Leg Threshold, place second leg buy
7. Mark trade as 'open' when both legs filled

## P&L Calculation

For completed trades:
- Total USDC spent = first_leg_usdc + second_leg_usdc
- Max payout if one side wins = max(first_leg_shares, second_leg_shares)
- P&L = max_payout - total_spent
- ROI% = (P&L / total_spent) * 100

## Wallet
- Same as other bots: 0x10b51f54A85f039f75b8d2856Cb96E554cafAE88
- Uses Polymarket CLOB client for order placement