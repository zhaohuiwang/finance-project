
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
3. [Goldman Sachs](https://github.com/goldmansachs)
4. [freqtrade](https://github.com/freqtrade/freqtrade)
5. [Microsoft Qlib](https://github.com/microsoft/qlib)
6. [schwab-trader github](https://github.com/ibouazizi/schwab-trader/tree/main)
7. [schwab-trader](https://pypi.org/project/schwab-trader/#description)