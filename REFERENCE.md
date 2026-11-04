

```Bash
uv run equityforge show-config
uv run equityforge universe
```

Run this for credential trouble shooting
```Bash
uv run python - <<'PY'
import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()

key = os.getenv("ALPACA_API_KEY", "").strip()
secret = os.getenv("ALPACA_API_SECRET_KEY", "").strip()

print("API key:", "SET" if key else "MISSING")
print("API secret:", "SET" if secret else "MISSING")

if not key or not secret:
    raise SystemExit("Check your .env file and variable names.")

try:
    client = TradingClient(key, secret, paper=True)
    account = client.get_account()
    print("Authentication successful.")
    print("Account status:", account.status)
except Exception as exc:
    print("Authentication failed:", type(exc).__name__)
    print(str(exc))
PY
```



###########################################################################
# Dockdb
###########################################################################

```Bash

uv run python -c "
import duckdb;
con=duckdb.connect(':memory:');
print(duckdb.__version__, con.execute('SELECT 1').fetchone());
con.close()
"


uv run python -c "
import duckdb; 
duckdb.connect('data/screener.duckdb').sql('SHOW TABLES').show()
"
```

# See the structure and basic stats of a specified table
```Bash
uv run python -c "
import duckdb
con = duckdb.connect('data/screener.duckdb')
con.sql('SUMMARIZE table_name').show()
"
```
Note: It is optional to put table_name in quotation marks. 

```Bash
uv run python -c "
import duckdb
con=duckdb.connect('data/screener.duckdb', read_only=True);
con.sql(\"DESCRIBE 'table_name'\").show();
con.close()"
```

# Preview the first few rows
```Bash
uv run python -c "
import duckdb
con = duckdb.connect('data/screener.duckdb')
con.sql('SELECT * FROM assets LIMIT 5').show(max_width=10000)
"

```

# Get the row count for a specified table
```Bash
uv run python -c "
import duckdb
con = duckdb.connect('data/screener.duckdb')
con.sql('SELECT COUNT(*) AS rows FROM table_name').show()
"
```

# Overview of all tables at once (table names and column number)
```Bash
uv run python -c "
import duckdb
con = duckdb.connect('data/screener.duckdb')
con.sql('''
SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns c 
     WHERE c.table_name = t.table_name) AS columns
FROM information_schema.tables t
WHERE table_schema = 'main'
ORDER BY table_name
''').show()
"
```

# get row counts for every table
```Bash
uv run python -c "
import duckdb
con = duckdb.connect('data/screener.duckdb')
tables = con.sql('SHOW TABLES').fetchall()
for (name,) in tables:
    count = con.sql(f'SELECT COUNT(*) FROM \"{name}\"').fetchone()[0]
    print(f'{name:<35} {count:>10,} rows')
"
```


```bash
uv run python -c "
import duckdb

con = duckdb.connect('data/screener.duckdb', read_only=True)

tables = con.sql('''
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'main'
    ORDER BY table_name
''').fetchall()

print(f\"{'TABLE NAME':<35} {'COLUMNS':>8} {'ROWS':>12}\")
print('-' * 57)

for (name,) in tables:
    columns = con.sql(f'''
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = 'main'
          AND table_name = ?
    ''', params=[name]).fetchone()[0]

    rows = con.sql(f'SELECT COUNT(*) FROM \"{name}\"').fetchone()[0]

    print(f'{name:<35} {columns:>8,} {rows:>12,}')

con.close()
"
```


```bash
uv run python -c "
import duckdb

con = duckdb.connect('data/screener.duckdb', read_only=True)

print('=== TABLES ===')
con.sql('SHOW TABLES').show()

print('=== FOREIGN KEY CONSTRAINTS ===')
con.sql('''
    SELECT
        table_name,
        constraint_type,
        constraint_text
    FROM duckdb_constraints()
    WHERE constraint_type = 'FOREIGN KEY'
    ORDER BY table_name
''').show(max_rows=100)

con.close()
"
```




###########################################################################
# SQLite
###########################################################################

```Bash

# To open SQLite3 interactively at terminal
sqlite3 logs/trading.sqlite
# sqlite> promp
.tables         # To list all the tables
select * from state;
select * from transactions;
.schema transactions;
.schema state;

# SQLite's default wont display the column names, to enable it.
.headers on
.mode column
SELECT * FROM transactions;
SELECT * FROM state;

.quit           # To exit


# Alternative
uv run python -c "
import sqlite3

con = sqlite3.connect(
    'file:logs/trading.sqlite?mode=ro',
    uri=True
)

for row in con.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\"):
    print(row[0])

con.close()
"

# To check a specified table_name schema
uv run python -c "
import sqlite3

con = sqlite3.connect(
    'file:logs/trading.sqlite?mode=ro',
    uri=True
)

for row in con.execute('PRAGMA table_info(table_name)'):
    print(row)

con.close()
"




```


```Bash
rm config.py
rm screener.py
rm equity_forge.py

rm -rf src/
rm -rf tests/

cp  ~/Downloads/equityforge/config.py .
cp  ~/Downloads/equityforge/screener.py .
cp  ~/Downloads/equityforge/equity_forge.py .

cp  -r ~/Downloads/equityforge/tests .
cp  -r ~/Downloads/equityforge/src .
```