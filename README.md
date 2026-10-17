# BotTele – Telegram Shop Bot

A Telegram bot for selling digital goods (accounts, keys, etc.) with an internal wallet, automatic top-ups via **Sepay** (Vietnamese bank transfer) and **Binance** (USDT TRC20/BEP20), stock management, order handling, and admin/subadmin roles. Multi-language support included.

## Features

- **Users**: browse products, choose quantity, buy, view dashboard/profile, switch language.
- **Top-ups**: bank transfer via Sepay webhook; USDT (TRC20, BEP20) verified through the Binance API; top-up orders expire after `ORDER_TTL_SECONDS`.
- **Administration**: add/remove products, manage stock (`pushItem`, `pullItem`, `updatestock`, ...), process orders, refunds, broadcasts, block/unblock users, statistics.
- **Roles**: admin (`ADMIN_ID`), subadmins (stored in the DB), regular users.
- **Reminders**: every hour, admins/subadmins are reminded of unprocessed `PENDING` orders (with confirm / cancel / mute buttons).

## Project structure

```
main.py                  Bot setup, handler registration, reminder job, webhook server
run.py                   Entry point
config.py                Settings loaded from .env (pydantic-settings)
sepay_webhook.py         Flask webhook receiving Sepay transactions
look_up.py               Binance transaction lookup
services/binance_api.py  Binance API client (HMAC-signed)
commands/                User, admin and boss commands; dbconfig.py creates the SQLite schema
i18n.py, locales.py      Translations
data/database.db         SQLite database (auto-created, not committed)
```

## Requirements

- Python 3.10+
- A bot token from [@BotFather](https://t.me/BotFather)
- (Optional) a Sepay account and a Binance API key (read-only recommended)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirments.txt
cp .env.example .env     # then fill in the values
python run.py
```

## Configuration (`.env`)

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token (required) |
| `ADMIN_ID` | Telegram ID of the main admin |
| `USER_NAME` | Support username shown to users |
| `PATH_DB` | SQLite path, default `data/database.db` |
| `SEPAY_WEBHOOK_KEY` | Key used to authenticate Sepay webhooks |
| `WEBHOOK_PATH` | Webhook path, default `/sepay/webhook` |
| `PORT` | Webhook server port, default `5051` |
| `ORDER_TTL_SECONDS` | Top-up order lifetime, default `900` |
| `BANK_ACC`, `BANK_CODE`, `BANK_NAME`, `ACC_OWNER` | Receiving bank account details |
| `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_ID` | Binance credentials |
| `TRC20_ADDRESS`, `BEP20_ADDRESS` | Wallet addresses receiving USDT |

> **Security:** never commit `.env`, the database, or logs (they are already in `.gitignore`). Use a read-only Binance API key.

## Sepay webhook

Point the Sepay webhook to `https://<domain>:<PORT><WEBHOOK_PATH>` (POST) using the same key as `SEPAY_WEBHOOK_KEY`. Put it behind an HTTPS reverse proxy (nginx/caddy).

## Main commands

**Users:** `/start`, `/help`, `/dashboard`, `/listproducts`, `/addfund`, `/cancelrecharge`, `/myid`, `/aboutme`, `/language`

**Admin / subadmin:** `/help_admin`, `/help_subadmin`, `/addproduct`, `/removeproduct`, `/pushItem`, `/pullItem`, `/pullItems`, `/updatestock`, `/myStocks`, `/myStock`, `/listorders`, `/users`, `/detailuser`, `/refund`, `/broadcast`, `/block_user`, `/unblock_user`, `/stats`, `/add_admin`, `/remove_admin`, `/subAdmins`

## Running on a VPS

Run it under `systemd`, `supervisor` or `tmux` so it restarts automatically:

```ini
[Service]
WorkingDirectory=/path/to/BotTele
ExecStart=/path/to/BotTele/.venv/bin/python run.py
Restart=always
```
