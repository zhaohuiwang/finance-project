


Start a venv and run the bot
```Bash
cd ~/dev/finance-project/schwab-trader && source .venv/bin/activate
python3 schwab-trading-bot/bot_v2.py
```

Dashboard URL
http://127.0.0.1:8050/

To release occupied porcess ID
```Bash
lsof -i :8050
kill -9 <pid>
```

```Bash
zhaohuiwang@WangFamily:~/dev/finance-project/schwab-trader$ sqlite3 trading_bot.db
SQLite version 3.45.1 2024-01-30 16:01:20
Enter ".help" for usage hints.
sqlite> .tables
state         transactions
sqlite> select * from state;
sqlite> select * from transactions;
1|2026-03-12T14:42:32.976913|BUY_SUBMITTED|IREN|2.0|41.175|MARKET|Risk-sized: 2 shares
2|2026-03-12T14:42:40.645050|BUY_SUBMITTED|IREN|2.0|41.145|MARKET|Risk-sized: 2 shares
3|2026-03-12T14:42:47.605828|BUY_SUBMITTED|IREN|2.0|41.165|MARKET|Risk-sized: 2 shares
4|2026-03-12T14:42:54.450428|BUY_SUBMITTED|IREN|2.0|41.165|MARKET|Risk-sized: 2 shares
```