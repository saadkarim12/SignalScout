# SignalScout tutorial: paper trading, start to finish

Paper trading = pretend trading. No real money moves. SignalScout never buys or sells for you.

## 0. Your daily routine now (2 minutes) - the Trend portfolio paper test
1. About 09:00 UAE time Slack sends "Daily paper check" with today's pretend positions (it stays quiet if you already checked in).
2. Open **http://127.0.0.1:8501/portfolio**. Read each coin: how much is invested, which rules say IN or OUT.
3. Open **Paper results**. Press **I checked today**. Look at the QA table: it should say all passed.
4. Nothing else. The strategy changes position only a few times a year, so on most days nothing changes. That is normal.
5. When Slack says a coin's position CHANGED, that is the "paper trade": note the new percentage in your notebook.

**When can real money start?** Only when every line on the Paper results page has a tick (90 days, QA passing, your check-ins, drawdown, position changes seen). Then only a TINY test. These rules were fixed in advance and are in `config.yaml` under `go_live`.

## 1. Start the app (nothing to do, 1 minute to check)
SignalScout now runs by itself in the background. It starts when you log in to your Mac and restarts if it crashes.
1. Open your browser at **http://127.0.0.1:8501** (bookmark it).
2. To check that everything is running: double-click **Test SignalScout** on your Desktop, type **s**, press Return. You want to see `web: RUNNING` and `reminders: RUNNING`.
3. If something is not running, type **r** to restart.
4. Keep your Mac awake and plugged in on Sunday morning. (While SignalScout runs, your Mac will not fall asleep on its own. Closing the laptop lid still puts it to sleep.)

## 2. What the page tabs do
- **Practice trades:** the 20-trade test of SignalScout's signals (section 3).
- **Weekly buys:** your pretend weekly buying diary.
- **Market mode:** is Bitcoin's big trend up (IN) or down (OUT)?
- **Price alerts:** tell me when a price is reached.
- **Market check / Alert preview:** learning tools. They show how the old checklist scores coins. That checklist lost money in tests, so use it to learn, not to trade.
- **Backtest:** the 3-year tests, including the failed ones.
- **Safety check:** confirms the app's calculations are working.

## 3. The 20-trade practice test (step by step)
Goal: do 20 pretend trades from SignalScout's signals. If the results are good, you then think about a very small real test on Binance. If not, you saved real money.

Open **http://127.0.0.1:8501/practice** (the **Practice trades** tab).

**Step A: check the market.** Click **Check the market now** and wait about 30 seconds.

**Step B: look at the signals table.** Coins marked STRONG or WATCH are signals. If the table is empty, that is normal. Close the page and come back later. Waiting is part of trading.

**Step C: log a pretend buy.** Click **Log pretend buy** on a signal. SignalScout saves the buy price, the stop (where it counts as a loss) and the target (where it counts as a win). You will see a green message that says "Logged pretend trade".

**Step D: do nothing.** SignalScout watches the price every 5 minutes. No need to look.

**Step E: read the result message.** When the stop or target is touched, you get a Slack message: "hit your TARGET" (win) or "hit your STOP" (loss), with the result in R. A trade still open after 21 days is closed at the market price.

**Step F: repeat** until the progress bar says 20 of 20 finished.

**The golden rules of the test**
- Log EVERY signal you get, not only the ones you like. Picking favourites makes the test dishonest.
- Never change the stop or target afterwards.
- A loss is normal. Even good methods lose often. Look at the total after 20, not at one trade.
- Do not use real money during the test.

**How to read the result at 20 trades**
- **PASS:** total R above 0 and average at least +0.15R. Encouraging. Because 20 trades is a small sample, the next step is a very small real test, never a big one.
- **NOT PROVEN:** do not trade this with real money. Come back to Claude and we review what happened.

**Later, if you pass (not now):** you place every buy yourself on Binance, and you put the stop and target orders on Binance right away so they work even when your Mac is off. Never risk more than 1% of your money on one trade. Only use money you can afford to lose. Check that your exchange is allowed where you live.

## 4. Your weekly routine (5 minutes, every Sunday)
1. **Noon (UAE time):** a Slack message arrives. It says the Market mode, BTC's price, and your pretend buy ($100).
2. Open the **Weekly buys** tab. Your pretend buy is already logged in the diary.
3. Read the message: mode **IN** = both plans say buy. Mode **OUT** = the cautious plan skips, the plain plan buys. The diary tracks both so you can compare.
4. Click the chart link if you want to look at BTC on TradingView.
5. Write one line for yourself: "Would I really have bought? Did I feel calm?" (a notebook is fine).
6. Done. You do not trade anything for real.

## 5. Any day (optional)
- **Price alert:** open **Price alerts**, type a coin (BTC) and a price, click **Add alert**. You get one Slack message when it is reached. It is not a buy or sell signal, only a heads-up.
- **Market mode:** you get a message only if the mode flips between IN and OUT.
- **Change the weekly amount:** edit it in Telegram with `/setweekly 100` (when Telegram works), or ask Claude.

## 6. The 12-week check-in
After 12 Sundays, open **Weekly buys** and answer:
1. Did I follow the routine every week?
2. Which plan ended better in my diary, plain or cautious?
3. Did any week make me want to break my rules?
4. Was I comfortable with the amount?
Then tell Claude. If it went well, we talk about Phase 5: very small REAL buys that YOU place yourself, with money you can afford to lose.

## 7. Rules that never change
- Only money you can afford to lose.
- Spot only. No leverage, no borrowing, no shorting.
- Never risk more than 1% of your money on one trade.
- You decide everything. SignalScout is not financial advice.
- Never share passwords, codes, bot tokens or Slack webhook links.

## 8. If something goes wrong
- **Page will not open:** use the Desktop icon, type **s** to check, then **r** to restart.
- **No Slack message on Sunday:** was the Mac awake with the lid open? Use the Desktop icon, type **s**, then **8** to send a test message.
- **Mac restarted:** nothing to do. It starts again when you log in. Check with **s**.
- **Something looks wrong:** open the **Safety check** tab, then tell Claude exactly what you see.
