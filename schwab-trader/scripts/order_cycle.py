
import os
import time

import csv
import logging
import pytz

from pathlib import Path
from datetime import datetime, time as dt_time
from src.schwab_trader.accounts.schwab import client
from filelock import FileLock, Timeout


logger = logging.getLogger(__name__)
# ---------------- CONFIG ----------------

POLL_INTERVAL         = 10   # now slower since less polling needed
PROFIT_REPORT_INTERVAL= 3600

EASTERN = pytz.timezone("US/Eastern")
MARKET_OPEN  = dt_time(9, 30)
MARKET_CLOSE = dt_time(16, 0)

PROFIT_MARGIN   = 0.03   # 3%
REENTRY_MARGIN  = 0.02   # 2% below last sell
STOP_LOSS_THRESHOLD = 0.05  # 5% below buy fill
LOG_FILE = Path("trades.log.csv")
LOCK_FILE = LOG_FILE.with_suffix(LOG_FILE.suffix + ".lock")  # e.g. trades.log.csv.lock
# ---------------------------------------


symbols = {
    "AAPL": {"qty": 1, "state": "INIT", "entry_order_id": None,
             "last_buy": None, "last_sell": None, "buy_price": None},
    "TSLA": {"qty": 1, "state": "INIT", "entry_order_id": None,
             "last_buy": None, "last_sell": None, "buy_price": None}
}
# "INIT" is short for "Initialized"

# ---------------- HELPERS ----------------
# Global state for dynamic columns (persists order across restarts)
_field_order: list[str] = []
_seen_fields: set[str] = set()
_initialized = False


def _initialize_from_existing_file() -> None:
    """Read the first line of an existing CSV so column order survives restarts."""
    global _field_order, _seen_fields, _initialized

    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 0:
        with LOG_FILE.open("r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
                if header:
                    _field_order = header[:]
                    _seen_fields = set(header)
            except StopIteration:
                pass  # empty file

    _initialized = True


def log_trade(**kwargs) -> None:
    """
    Completely dynamic, thread-safe, process-safe CSV logger.
    
    - Accepts any key=value pairs.
    - Columns appear in order of first appearance.
    - Survives bot restarts (reads existing header).
    - Uses FileLock to prevent corruption from concurrent writes (threads or processes).
    
    Example:
        log_trade(timestamp="2026-03-07 19:45:12", symbol="AAPL", action="BUY", price=178.45, quantity=150)
    """
    if not kwargs:
        return

    if not _initialized:
        _initialize_from_existing_file()

    # Register new fields in order of appearance
    for key in list(kwargs.keys()):
        if key not in _seen_fields:
            _seen_fields.add(key)
            _field_order.append(key)

    # Build row matching current header order
    row = [kwargs.get(field, "") for field in _field_order]

    # Lock-protected write
    try:
        with FileLock(LOCK_FILE, timeout=10):  # 10s timeout; adjust as needed
            # Re-check file emptiness under lock (extra safety)
            needs_header = not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0

            with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if needs_header:
                    writer.writerow(_field_order)
                writer.writerow(row)

    except Timeout:
        print(f"Warning: Could not acquire lock for {LOG_FILE} after 10s – skipping log entry")
        # Or raise, log elsewhere, queue for retry, etc. – up to you
    except Exception as e:
        print(f"Error writing to log: {e}")


def extract_fill_prices(order_json, aggregate='first'):
    """
    Return executed fill price(s).
    
    aggregate:
    - 'first'    → first fillPrice found (simple default)
    - 'average'  → volume-weighted average if quantities present
    - 'all'      → list of all fillPrices
    """
    if not order_json or not isinstance(order_json, dict):
        return None

    fills = []
    quantities = []

    if "executionLegs" in order_json:
        for leg in order_json["executionLegs"]:
            fp = leg.get("fillPrice")
            qty = leg.get("filledQuantity") or leg.get("quantity", 0)
            if fp is not None:
                try:
                    fp_float = float(fp)
                    fills.append(fp_float)
                    quantities.append(float(qty) if qty else 1.0)
                except (ValueError, TypeError):
                    continue

    if fills:
        if aggregate == 'all':
            return fills
        elif aggregate == 'average' and quantities:
            total_qty = sum(quantities)
            return sum(f * q for f, q in zip(fills, quantities)) / total_qty
        else:
            return fills[0]  # first

    # No fills → fallback to requested price
    p = order_json.get("price")
    if p is not None:
        try:
            return float(p)
        except (ValueError, TypeError):
            pass

    return None

def print_profit_summary():
    if not os.path.isfile(LOG_FILE):
        return
    profits = {}
    with open(LOG_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row["symbol"]
            action = row["action"]
            price = float(row["price"] or 0)
            qty = symbols.get(sym, {}).get("qty", 1)
            if sym not in profits:
                profits[sym] = 0.0
            if "BUY" in action.upper():
                profits[sym] -= price * qty
            else:
                profits[sym] += price * qty
    print("\n--- Profit Summary ---")
    for sym, profit in profits.items():
        print(f"{sym}: ${profit:.2f}")
    print("----------------------\n")

def place_order(order_payload):
    r = client.place_order(ACCOUNT_HASH, order_payload)
    if r.status_code not in (200, 201):
        raise Exception(f"Order failed: {r.status_code} - {r.text}")
    loc = r.headers.get("location")
    if not loc:
        raise Exception("No location header in response")
    return loc.split("/")[-1]  # order ID

def get_order_status(order_id):
    if not order_id:
        return None
    try:
        resp = client.get_order(ACCOUNT_HASH, order_id)
        return resp.json().get("status")
    except:
        return None

def get_filled_price(order_id):
    try:
        detail = client.get_order(ACCOUNT_HASH, order_id).json()
        return safe_extract_price(detail)
    except:
        return None

# ---------------- BRACKET BUY HELPER ----------------
def place_buy_limit_with_bracket(symbol, qty, limit_buy_price):
    """
    Places BUY LIMIT + attached OCO (SELL LIMIT profit + SELL STOP loss)
    """
    buy_price = round(limit_buy_price, 2)
    profit_price = round(buy_price * (1 + PROFIT_MARGIN), 2)
    stop_price  = round(buy_price * (1 - STOP_LOSS_THRESHOLD), 2)

    payload = {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "LIMIT",
        "price": buy_price,
        "orderStrategyType": "TRIGGER",  # or "NORMAL" — TRIGGER often used for attached
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": qty,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
            }
        ],
        "childOrderStrategies": [
            {
                "orderStrategyType": "OCO",
                "childOrderStrategies": [
                    # Profit target: SELL LIMIT
                    {
                        "session": "NORMAL",
                        "duration": "DAY",
                        "orderType": "LIMIT",
                        "price": profit_price,
                        "orderStrategyType": "SINGLE",
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity": qty,
                                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                            }
                        ]
                    },
                    # Stop loss: SELL STOP
                    {
                        "session": "NORMAL",
                        "duration": "DAY",
                        "orderType": "STOP",
                        "stopPrice": stop_price,  # ← important: stopPrice, not price
                        "orderStrategyType": "SINGLE",
                        "orderLegCollection": [
                            {
                                "instruction": "SELL",
                                "quantity": qty,
                                "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                            }
                        ]
                    }
                ]
            }
        ]
    }

    print(f"{symbol} → Placing BUY LIMIT @ {buy_price:.2f} + bracket "
          f"(profit @ {profit_price:.2f} | stop @ {stop_price:.2f})")
    return place_order(payload)

# ---------------- MAIN LOOP ----------------
def run_bot():
    cycle = 1
    last_report = time.time()

    while True:
        now_eastern = datetime.now(EASTERN)
        now_time = now_eastern.time()

        if not (MARKET_OPEN <= now_time <= MARKET_CLOSE):
            print(f"Market closed ({now_time.strftime('%H:%M')}) — waiting 60s")
            time.sleep(60)
            continue

        if time.time() - last_report > PROFIT_REPORT_INTERVAL:
            print_profit_summary()
            last_report = time.time()

        for symbol, data in symbols.items():
            state = data["state"]
            entry_order_id = data["entry_order_id"]

            try:
                if state == "INIT":
                    # Initial sell to start cycle (if you hold shares)
                    print(f"{symbol} INIT → SELL MARKET")
                    sell_payload = {
                        "session": "NORMAL",
                        "duration": "DAY",
                        "orderType": "MARKET",
                        "orderStrategyType": "SINGLE",
                        "orderLegCollection": [{
                            "instruction": "SELL",
                            "quantity": data["qty"],
                            "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                        }]
                    }
                    data["entry_order_id"] = place_order(sell_payload)
                    data["state"] = "WAITING_SELL_FILL"

                elif state == "WAITING_SELL_FILL":
                    status = get_order_status(entry_order_id)
                    if status == "FILLED":
                        sell_price = get_filled_price(entry_order_id)
                        log_trade(symbol, cycle, "SELL MARKET (init)", sell_price)
                        print(f"{symbol} Initial sell filled @ {sell_price:.2f}")
                        reentry_price = sell_price * (1 - REENTRY_MARGIN)
                        data["entry_order_id"] = place_buy_limit_with_bracket(
                            symbol, data["qty"], reentry_price
                        )
                        data["state"] = "WAITING_BUY_FILL"
                        cycle += 1  # new cycle after exit

                elif state == "WAITING_BUY_FILL":
                    status = get_order_status(entry_order_id)
                    if status == "FILLED":
                        buy_price = get_filled_price(entry_order_id)
                        log_trade(symbol, cycle, "BUY LIMIT + BRACKET ENTRY", buy_price)
                        print(f"{symbol} Buy filled @ {buy_price:.2f} — bracket active!")
                        data["buy_price"] = buy_price
                        data["last_buy"] = buy_price
                        data["state"] = "POSITION_HELD_WITH_BRACKET"

                elif state == "POSITION_HELD_WITH_BRACKET":
                    # Light check: if entry order is GONE or FILLED + children triggered
                    # (in practice, once buy fills, bracket is live — we wait for next sell)
                    # For simplicity: poll until we detect no position or log via webhook later
                    # Here we assume after fill → wait for manual log or add position check
                    # For now: reset after long timeout or add get_positions logic
                    # (advanced: poll account positions)
                    status = get_order_status(entry_order_id)
                    if status in ("CANCELED", "REJECTED", "EXPIRED"):
                        print(f"{symbol} Entry order no longer active — checking next")
                        data["state"] = "INIT"  # or add position query
                    time.sleep(POLL_INTERVAL)

            except Exception as e:
                print(f"ERROR {symbol}: {e}")
                time.sleep(15)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    print("Bracket-order bot starting...")
    run_bot()
    
    




# import schwabdev
# import time
# import csv
# import os
# from datetime import datetime, time as dt_time
# import pytz

# # ---------------- CONFIG ----------------
# APP_KEY      = "YOUR_APP_KEY"
# APP_SECRET   = "YOUR_APP_SECRET"
# ACCOUNT_HASH = "YOUR_ACCOUNT_HASH"

# POLL_INTERVAL         = 5
# PROFIT_REPORT_INTERVAL= 3600

# EASTERN = pytz.timezone("US/Eastern")
# MARKET_OPEN  = dt_time(9, 30)
# MARKET_CLOSE = dt_time(16, 0)

# PROFIT_MARGIN   = 0.03
# REENTRY_MARGIN  = 0.02
# STOP_LOSS_THRESHOLD = 0.05
# LOG_FILE        = "trade_log.csv"
# # ---------------------------------------

# client = schwabdev.Client(APP_KEY, APP_SECRET)
# client.update_tokens_auto()

# symbols = {
#     "AAPL": {"qty": 10, "state": "INIT", "order_id": None,
#              "last_buy": None, "last_sell": None, "stop_loss_id": None, "buy_price": None},
#     "TSLA": {"qty": 5, "state": "INIT", "order_id": None,
#              "last_buy": None, "last_sell": None, "stop_loss_id": None, "buy_price": None}
# }

# # ---------------- HELPERS ----------------

# def log_trade(symbol, cycle, action, price):
#     price_val = f"{price:.2f}" if price is not None else ""
#     file_exists = os.path.isfile(LOG_FILE)
#     with open(LOG_FILE, "a", newline="") as f:
#         writer = csv.writer(f)
#         if not file_exists:
#             writer.writerow(["timestamp", "symbol", "cycle", "action", "price"])
#         writer.writerow([datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S"), symbol, cycle, action, price_val])

# def safe_extract_price(order_obj):
#     if not order_obj: return None
#     if "price" in order_obj and order_obj["price"] is not None:
#         try: return float(order_obj["price"])
#         except: pass
#     if "executionLegs" in order_obj:
#         for leg in order_obj["executionLegs"]:
#             if leg.get("fillPrice"):
#                 try: return float(leg["fillPrice"])
#                 except: pass
#     return None

# def print_profit_summary():
#     if not os.path.isfile(LOG_FILE): return
#     profits = {}
#     with open(LOG_FILE, newline="") as f:
#         reader = csv.DictReader(f)
#         for row in reader:
#             sym = row["symbol"]
#             action = row["action"]
#             price = float(row["price"] or 0)
#             qty = symbols.get(sym, {}).get("qty", 1)
#             if sym not in profits: profits[sym] = 0
#             if "BUY" in action:
#                 profits[sym] -= price * qty
#             else:
#                 profits[sym] += price * qty
#     print("\n--- Profit Summary ---")
#     for sym, profit in profits.items():
#         print(f"{sym}: ${profit:.2f}")
#     print("----------------------\n")

# def place_order(order):
#     r = client.place_order(ACCOUNT_HASH, order)
#     if r.status_code not in [200, 201]:
#         raise Exception(f"Order failed: {r.text}")
#     loc = r.headers.get("location")
#     return loc.split("/")[-1] if loc else None

# def get_order_status(order_id):
#     if not order_id: return None
#     try:
#         return client.get_order(ACCOUNT_HASH, order_id).json()["status"]
#     except:
#         return None

# def cancel_order(order_id):
#     if not order_id: return
#     try:
#         r = client.cancel_order(ACCOUNT_HASH, order_id)
#         print(f"Cancelled order {order_id} → {r.status_code}")
#     except Exception as e:
#         print(f"Cancel failed {order_id}: {e}")

# def place_stop_loss(symbol, qty, stop_price):
#     order = {
#         "session": "NORMAL", "duration": "DAY", "orderType": "STOP",
#         "stopPrice": round(stop_price, 2),          # ← FIXED: stopPrice not price
#         "orderStrategyType": "SINGLE",
#         "orderLegCollection": [{
#             "instruction": "SELL", "quantity": qty,
#             "instrument": {"symbol": symbol, "assetType": "EQUITY"}
#         }]
#     }
#     return place_order(order)

# # Order Templates
# def sell_market(symbol, qty):
#     return place_order({
#         "session":"NORMAL","duration":"DAY","orderType":"MARKET",
#         "orderStrategyType":"SINGLE",
#         "orderLegCollection":[{
#             "instruction":"SELL","quantity":qty,
#             "instrument":{"symbol":symbol,"assetType":"EQUITY"}
#         }]
#     })
# def sell_limit(symbol, qty, price):
#     return place_order({
#         "session":"NORMAL","duration":"DAY","orderType":"LIMIT",
#         "price":price,"orderStrategyType":"SINGLE",
#         "orderLegCollection":[{
#             "instruction":"SELL","quantity":qty,
#             "instrument":{"symbol":symbol,"assetType":"EQUITY"}
#         }]
#     })


# def buy_limit(symbol, qty, price):
#     return place_order({
#         "session":"NORMAL","duration":"DAY","orderType":"LIMIT",
#         "price": round(price, 2),"orderStrategyType":"SINGLE",
#         "orderLegCollection":[{
#             "instruction":"BUY","quantity":qty,
#             "instrument":{"symbol":symbol,"assetType":"EQUITY"}
#         }]
#     })


# # ---------------- MAIN LOOP ----------------
# def wait_for_fill(order_id, timeout=600):  # kept for simplicity
#     start = time.time()
#     while True:
#         status = get_order_status(order_id)
#         if status == "FILLED": return True
#         if status in ["CANCELED", "REJECTED", "EXPIRED"]: return False
#         if time.time() - start > timeout:
#             raise Exception("Order timeout")
#         time.sleep(5)

# def run_bot():
#     cycle = 1
#     last_report = time.time()

#     while True:
#         now_eastern = datetime.now(EASTERN)
#         now_time = now_eastern.time()

#         if time.time() - last_report > PROFIT_REPORT_INTERVAL:
#             print_profit_summary()
#             last_report = time.time()
            
#         if not (MARKET_OPEN <= now_time <= MARKET_CLOSE):
#             print(f"Market closed ({now_time.strftime('%H:%M')}) — waiting 60s")
#             time.sleep(60)
#             continue

#         # Optional: weekend/holiday check could be added later if needed
#         # (right now we only check time-of-day)

#         for symbol, data in symbols.items():
#             state = data["state"]
#             order_id = data["order_id"]
#             stop_loss_id = data["stop_loss_id"]

#             try:
#                 if state == "INIT":
#                     print(symbol, "→ SELL MARKET (initial exit)")
#                     data["order_id"] = sell_market(symbol, data["qty"])
#                     data["state"] = "SELL_PLACED"

#                 elif state == "SELL_PLACED":
#                     if wait_for_fill(order_id):
#                         filled_price = safe_extract_price(client.get_order(ACCOUNT_HASH, order_id).json())
#                         data["last_sell"] = filled_price
#                         log_trade(symbol, cycle, "SELL MARKET", filled_price)
#                         buy_price = filled_price * (1 - REENTRY_MARGIN)
#                         print(symbol, f"Sold @ {filled_price:.2f} → Buy limit @ {buy_price:.2f}")
#                         data["order_id"] = buy_limit(symbol, data["qty"], buy_price)
#                         data["buy_price"] = buy_price
#                         data["state"] = "BUY_LIMIT_PLACED"

#                 elif state == "BUY_LIMIT_PLACED":
#                     if wait_for_fill(order_id):
#                         order_detail = client.get_order(ACCOUNT_HASH, order_id).json()
#                         filled_price = safe_extract_price(order_detail)
#                         data["last_buy"] = filled_price
#                         log_trade(symbol, cycle, "BUY LIMIT", filled_price)
#                         print(symbol, f"Bought @ {filled_price:.2f}")

#                         # FIXED: Always place stop-loss 5% below actual fill
#                         stop_price = filled_price * (1 - STOP_LOSS_THRESHOLD)
#                         data["stop_loss_id"] = place_stop_loss(symbol, data["qty"], stop_price)
#                         print(symbol, f"Stop-loss placed @ {stop_price:.2f}")

#                         # Place profit target
#                         sell_price = filled_price * (1 + PROFIT_MARGIN)
#                         data["order_id"] = sell_limit(symbol, data["qty"], sell_price)
#                         data["state"] = "SELL_LIMIT_PLACED"

#                 elif state == "SELL_LIMIT_PLACED":
#                     # NEW: Monitor BOTH profit target AND stop-loss
#                     sell_status = get_order_status(order_id)
#                     sl_status = get_order_status(stop_loss_id)

#                     if sell_status == "FILLED":
#                         filled_price = safe_extract_price(client.get_order(ACCOUNT_HASH, order_id).json())
#                         log_trade(symbol, cycle, "SELL LIMIT PROFIT", filled_price)
#                         print(f"{symbol} PROFIT TARGET HIT @ {filled_price:.2f}")
#                         cancel_order(stop_loss_id)          # clean up
#                         data["stop_loss_id"] = None
#                         data["state"] = "SELL_PLACED"       # cycle continues
#                         cycle += 1

#                     elif sl_status == "FILLED":
#                         log_trade(symbol, cycle, "STOP LOSS TRIGGERED", None)
#                         print(f"{symbol} STOP-LOSS TRIGGERED!")
#                         cancel_order(order_id)              # cancel profit target
#                         data["order_id"] = None
#                         data["state"] = "SELL_PLACED"       # cycle continues
#                         cycle += 1

#                     else:
#                         time.sleep(POLL_INTERVAL)  # non-blocking for other symbols

#             except Exception as e:
#                 print(f"ERROR {symbol}: {e}")
#                 time.sleep(10)
#         time.sleep(POLL_INTERVAL)   # ← so you don't spin at 100% CPU

# if __name__ == "__main__":
#     print("Bot starting...")
#     run_bot()
    
    
