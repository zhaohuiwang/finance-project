#### How to Run
Start a venv and run the bot
```Bash
cd ~/dev/finance-project/schwab-trader && source .venv/bin/activate
python3 -m schwab_bot.bot --mode cli
```
You will see:
* Console Rich live dashboard (updates on price change)
* Web Dash dashboard at http://127.0.0.1:8050/
* All buys/sells/OCO logged in `trading_bot.db`

Buy triggers fire automatically (or ask manual confirmation after first cycle).
Bracket orders (limit + stop) are placed instantly on fill.
Cycle resets automatically after sell.


To release occupied porcess ID
```Bash
lsof -i :8050
kill -9 <pid>
```
To check transaction logs
```Bash
zhaohuiwang@WangFamily:~/dev/finance-project/schwab-trader$ sqlite3 trading_bot.db

sqlite> .tables
state         transactions
sqlite> select * from state;
sqlite> select * from transactions;

# Example log records

```

While the bot is running in one terminla, you can open another terminal and add or take off any symbol and configuration like the following.  Both aim to give you live, on-the-fly control over what the bot pays attention to — which is one of the most valuable features in a real trading bot.

```Pyhton
(schwab-trader) zhaohuiwang@WangFamily:~/dev/finance-project/schwab-trader/schwab-trading-bot$ python3

python3 schwab-trading-bot/bot.py --mode cli

python bot.py --mode full          # original behaviour (rich + web)
python bot.py --mode cli           # web only + live terminal commands

> help
> list
> add TSLA {"buy_target_price": 180.0, ...}
> remove ACHR
> remove NBIS
> pause
> resume
> stop
> restart
> config

```


expand to options/futures streaming

Chart data is now flowing → self.last_candles[symbol] holds recent candles. You can later add logic like: "only buy if last candle close < previous close AND price drop trigger".
Use bot.add_symbol("TSLA") or bot.remove_symbol("NBIS") from another thread/console if you want dynamic control.



There are two references for schwabdev api streaming
https://tylerebowers.github.io/Schwabdev/
https://github.com/tylerebowers/Schwabdev
Please help me to construct a working python project and scripts to achieve the following goals:

I want to stream a list of stock e.g. ['ARCH', 'NBIS', 'IREN'] to get realtime quote as a looup.
I also set up some trigger, for example, if "ARCH" price drop to $32 or drop 5%, I want to purchase some share via some python code based on schwabdev above. and log the purchase history including shared bought and price.
Once in my profolio, I want to setup limit order to sell (price up to certail value or % from purchase price) and stop loss oder to manage risk. log the transaction history
then tracking the price movement, if below certain value or % purchase again like in step 2, then move to step 3, repeat or cycle.
I want a log or dash board to track the transctions and losss/gains.
here is my code, please make suggestion how to improve it to make it more production ready.




