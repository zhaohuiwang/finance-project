"""
Some example scripts to pull data from trading_bot.db

"""

# Show all transactions (simple print)
import sqlite3

DB_FILE = "trading_bot.db"

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("""
    SELECT timestamp, action, symbol, shares, price, order_type, note
    FROM transactions
    ORDER BY timestamp DESC
    LIMIT 20
""")

print("Recent Transactions:")
print("-" * 80)
for row in cursor.fetchall():
    ts, action, symbol, shares, price, order_type, note = row
    print(
        f"{ts} | {action:8} | {symbol:6} | {shares:>6} | ${price:>7.2f} | {order_type:8} | {note}"
    )

conn.close()


# Summary by symbol (total bought/sold, avg price, net position)
import sqlite3
from collections import defaultdict

DB_FILE = "trading_bot.db"

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("""
    SELECT symbol, action, SUM(shares) as total_shares, AVG(price) as avg_price
    FROM transactions
    WHERE action IN ('BUY (stream)', 'BUY_SUBMITTED', 'SELL (stream)')
    GROUP BY symbol, action
    ORDER BY symbol
""")

print("Position Summary by Symbol:")
print("-" * 70)

data = defaultdict(
    lambda: {"buy_shares": 0, "buy_avg": 0, "sell_shares": 0, "sell_avg": 0}
)

for symbol, action, total_shares, avg_price in cursor.fetchall():
    if "BUY" in action:
        data[symbol]["buy_shares"] += total_shares
        data[symbol]["buy_avg"] = avg_price  # simplistic – real avg needs weighted
    elif "SELL" in action:
        data[symbol]["sell_shares"] += total_shares
        data[symbol]["sell_avg"] = avg_price

for symbol, vals in data.items():
    net_shares = vals["buy_shares"] - vals["sell_shares"]
    print(
        f"{symbol:6} | Bought: {vals['buy_shares']:>6.1f} @ ${vals['buy_avg']:>6.2f} "
        f"| Sold: {vals['sell_shares']:>6.1f} @ ${vals['sell_avg']:>6.2f} "
        f"| Net: {net_shares:+8.1f}"
    )

conn.close()

# Profit/Loss calculation (simple realized P/L)
import sqlite3

DB_FILE = "trading_bot.db"


def calculate_realized_pl():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT symbol, action, shares, price
        FROM transactions
        WHERE action IN ('BUY (detected via stream)', 'SELL (detected via stream)')
        ORDER BY symbol, timestamp
    """)

    positions = {}
    total_pl = 0.0

    for symbol, action, shares, price in cursor.fetchall():
        if symbol not in positions:
            positions[symbol] = []

        if "BUY" in action:
            positions[symbol].extend([price] * int(shares))
        elif "SELL" in action:
            if positions[symbol]:
                for _ in range(int(shares)):
                    if positions[symbol]:
                        buy_price = positions[symbol].pop(0)  # FIFO
                        pl = (price - buy_price) * 1  # per share
                        total_pl += pl
                        print(
                            f"Closed {symbol}: Bought ${buy_price:.2f} → Sold ${price:.2f} = ${pl:+.2f}"
                        )

    conn.close()
    print(f"\nTotal Realized P/L: ${total_pl:,.2f}")


calculate_realized_pl()

# Quick dashboard-style summary (console table with rich)
# pip install rich
from rich.console import Console
from rich.table import Table
import sqlite3

DB_FILE = "trading_bot.db"

console = Console()

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("""
    SELECT 
        symbol,
        COUNT(*) as trade_count,
        MIN(timestamp) as first_trade,
        MAX(timestamp) as last_trade,
        SUM(CASE WHEN action LIKE '%BUY%' THEN shares ELSE 0 END) as total_bought,
        SUM(CASE WHEN action LIKE '%SELL%' THEN shares ELSE 0 END) as total_sold
    FROM transactions
    GROUP BY symbol
    ORDER BY last_trade DESC
""")

table = Table(title="Trading Activity Summary")
table.add_column("Symbol", style="cyan")
table.add_column("Trades", justify="right")
table.add_column("First Trade")
table.add_column("Last Trade")
table.add_column("Bought", justify="right")
table.add_column("Sold", justify="right")
table.add_column("Net", justify="right", style="bold")

for row in cursor.fetchall():
    symbol, trades, first, last, bought, sold = row
    net = bought - sold
    net_style = "green" if net > 0 else "red" if net < 0 else "white"
    table.add_row(
        symbol,
        str(trades),
        first[:10] if first else "-",
        last[:10] if last else "-",
        f"{bought:,.1f}",
        f"{sold:,.1f}",
        f"[bold {net_style}]{net:+,.1f}[/bold {net_style}]",
    )

console.print(table)
conn.close()

# Export to CSV (all transactions)
import sqlite3
import csv
from datetime import datetime

DB_FILE = "trading_bot.db"
EXPORT_FILE = f"transactions_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("SELECT * FROM transactions ORDER BY timestamp DESC")
headers = [desc[0] for desc in cursor.description]
rows = cursor.fetchall()

with open(EXPORT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(rows)

print(f"Exported {len(rows)} transactions to: {EXPORT_FILE}")

conn.close()
