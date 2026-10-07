# Account Setup — Owner Checklist (Phase 0, ~1 week)

Do these in order. Tick each box. Nothing here needs coding.

## A. Security basics (30 min) — do first

- [ ] Install a **password manager** (1Password, Bitwarden or Apple Passwords). Every account below gets a unique, generated password.
- [ ] Install an **authenticator app** (Google Authenticator, Microsoft Authenticator or Authy). Use it for 2FA — **not SMS**.
- [ ] Create a **dedicated email** for trading (e.g. a new Gmail alias) with 2FA on.
- [ ] Write your 2FA backup codes on paper and store them safely offline.

## B. Exchange account (2–5 days incl. verification)

Recommended to start: **BitOasis** (VARA-licensed, simplest app) or **Rain** (ADGM FSRA-licensed).
Check the licence on the regulator's public register before signing up.

- [ ] Sign up with the trading email.
- [ ] Complete **KYC**: Emirates ID + selfie + proof of address.
- [ ] Turn on **2FA** with the authenticator app.
- [ ] Set an **anti-phishing code** (if offered) — real emails from the exchange will show it.
- [ ] Turn on **withdrawal address whitelist** (if offered).
- [ ] Link your **UAE bank account** for AED deposits.
- [ ] Deposit only your **learning budget** (e.g. AED 750–1,800 / ~$200–500). Do not trade yet.

> SignalScout does **not** need exchange API keys in Phases 1–5. Never share keys, passwords or 2FA codes with anyone, including "support" on Telegram/WhatsApp.

## C. Telegram bot (10 min)

- [ ] Install Telegram and create an account.
- [ ] Open a chat with **@BotFather** → send `/newbot` → choose a name (e.g. `SaadSignalScout`) and a username ending in `bot`.
- [ ] Copy the **bot token** into a password-manager note. Treat it like a password.
- [ ] Send any message to your new bot.
- [ ] Get your **chat ID**: message **@userinfobot** — it replies with your numeric ID.
- [ ] Give both values to the developer only via the local `.env` file (never in chat or GitHub).

## D. TradingView (5 min, free)

- [ ] Create a free account at tradingview.com — used for looking at charts yourself.
- [ ] Add indicators to a BTC/USDT daily chart: **MA 50**, **MA 200**, **RSI 14**, **Volume**.
- [ ] Paid plan is **not needed** for SignalScout.

## E. Developer tools on your Mac (30 min)

- [ ] Install **Claude Code** (follow the official quickstart at docs.claude.com).
- [ ] Install **Python 3.11+** (Claude Code can do this for you: ask "install Python 3.11 with Homebrew").
- [ ] Optional: create a **private GitHub** repo `signalscout` for backups and version history.
- [ ] Open Terminal in the `SignalScout` folder, run `claude`, and say:
      **"Read CLAUDE.md and build Phase 1."**

## F. Your trading journal (5 min)

- [ ] Decide your **account size** for the bot's position sizing (your learning budget in USD).
- [ ] Commit to the rules: max 1% risk per trade, spot only, no leverage, no trades before the Phase 4 gate passes.

---
**Done with Phase 0 when:** exchange verified with 2FA, Telegram token + chat ID saved, Claude Code running in the folder.
