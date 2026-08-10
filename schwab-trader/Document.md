
Authentication Token Lifespan

Schwab uses a two-tier OAuth 2.0 system with the following expiration rules: 
* Access Token: Valid for 30 minutes. This token is used for making actual API requests.
* Refresh Token: Valid for 7 days. Unlike some other APIs, this is a hard limit; you must manually log in and re-authenticate every week to generate a new refresh token.
schwabdev saves token as `~/.schwabdev/tokens.db`
```Bash
cd ~/.schwabdev
sqlite3 tokens.db
lsof tokens.db          # list all PIDs if Error: database is locked, then
kill <pid>

sqlite> .tables         # In the SQLite interactive shell, list all tables
sqlite> SELECT * FROM schwabdev;     # query a table, e.g. schwabdev
sqlite> Ctrl + D        # Exit SQLite or .exit

sqlite> drop table schwabdev;    # Delete the entire table (structure + data)
sqlite> delete from schwabdev; vacuum;   # Erase all data but keep the table, VACUUM rebuilds the database and frees space.
```
In Python
```Python
import sqlite3

# Connect to the database (creates it if it doesn't exist)
conn = sqlite3.connect('example.db')
cursor = conn.cursor()

# Execute a query (e.g., create a table)
cursor.execute('SELECT * FROM schwabdev;')

# Close the connection
conn.close()
```

```Bash

```


References:
1. [developer.schwab Accounts and Trading Production](https://developer.schwab.com/products/trader-api--individual/details/specifications/Retail%20Trader%20API%20Production)
2. [developer.schwab Market Data Production](https://developer.schwab.com/products/trader-api--individual/details/specifications/Market%20Data%20Production)
3. [schwab-trader github](https://github.com/ibouazizi/schwab-trader/tree/main)
4. [schwab-trader](https://pypi.org/project/schwab-trader/#description)
5. [Schwabdev Stream Field Mappings](https://github.com/tylerebowers/Schwabdev/blob/main/schwabdev/translate.py)
6. [schwab-sdk-unofficial](https://socket.dev/pypi/package/schwab-sdk-unofficial)
7. [schwab-py](https://schwab-py.readthedocs.io/en/latest/streaming.html)
8. [schwab-py streaming field information](https://schwab-py.readthedocs.io/en/latest/streaming.html)
9. [Goldman Sachs](https://github.com/goldmansachs)
10. [freqtrade](https://github.com/freqtrade/freqtrade)
11. [Microsoft Qlib](https://github.com/microsoft/qlib)






### Logics in schwab-trader/src/schwab_trader/pipelines/bot.py
After BUY fill, it immediately places a bracket OCO oder. The limit sell price is calculated as 
`limit_price = round(buy_price * (1 + cfg.limit_sell_pct / 100), 2)`
When the price hits the calculated limit or the stop, Schwab executes the sell automatically (you don’t see the bot “deciding” to sell — it’s a real live order at Schwab)
After the sell fills, the bot resets the buy flag and will buy again later if the price drops below `buy_target_price` or the `buy_drop_pct` from the last buy.

Within the submit_sell_bracket_oco() method
```Python
        limit_price = (
            limit_sell_price
            if limit_sell_price is not None
            else round(buy_price * (1 + cfg.limit_sell_pct / 100), 2)
        )
        if cfg.stop_loss_dollar > 0:
            if buy_price > limit_price:
                stop_price = round(limit_price - cfg.stop_loss_dollar, 2)
            else:
                stop_price = round(buy_price - cfg.stop_loss_dollar, 2)
            console.print(
                f"[dim cyan]Using fixed $ stop for {symbol}: "
                f"${cfg.stop_loss_dollar:.2f} below entry → stop @ ${stop_price:.2f}[/dim cyan]"
            )
        else:
            stop_price = round(buy_price * (1 - cfg.stop_loss_pct / 100), 2)
            console.print(
                f"[dim]Using % stop for {symbol}: "
                f"{cfg.stop_loss_pct}% below entry → stop @ ${stop_price:.2f}[/dim]"
            )
```
within monitor_logic()
```Pyhton
  trigger = (
      price <= cfg.buy_target_price
      or (
          last_buy
          and price <= last_buy * (1 - cfg.buy_drop_pct / 100)
      )
  )
```
The bot will trigger a buy is either of these two independent conditions is true: 1. Hard target price reached or `price <= cfg.buy_target_price` 2. Drop from last buy price or `last_buy and price <= last_buy * (1 - cfg.buy_drop_pct / 100)` The last_buy price is from the database via `get_last_buy_price(sym))`

Currently, with risk-based sizeing block commented, all buy orders used a quantity that comes diectly from fixed_shares in the config.
All sell orders use the actual current position size from Schwab account (no partial selling)
