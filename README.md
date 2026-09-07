# Household Maintenance Tracker - Telegram Bot 🛠️

A personal Telegram bot built with **Python**, **Django**, and **uv** to monitor and stay ahead of recurring household maintenance chores (filters, water heaters, AC, car maintenance, smoke detectors, etc.).

Features dynamic elapsed countdowns, strict calendar cadences, completion history logs with notes, Markdown report exports, and proactive deadline alerts.

---

## 🚀 Quick Tour & Setup Guide

### 1. Prerequisites
- **Python 3.13+**
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

### 2. Install Dependencies
Synchronize project packages with `uv`:
```bash
uv sync
```

### 3. Configure Telegram Bot Credentials

1. **Create Bot Token**:
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot` and follow the prompts to choose a name and username.
   - Copy the API token provided.

2. **Find Your Telegram User ID**:
   - Message [@userinfobot](https://t.me/userinfobot) on Telegram.
   - It will reply with your numerical `Id` (e.g. `123456789`). Only this ID will be allowed to talk to your bot!

3. **Set Environment Variables**:
   Export them in your terminal or create a `.env` file:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
   export TELEGRAM_AUTHORIZED_USER_ID="your_telegram_numerical_id"
   ```

### 4. Run Database Migrations
Set up SQLite tables for tasks, histories, and notification logs:
```bash
uv run python manage.py migrate
```

### 5. Launch the Telegram Bot
Run the bot listener in polling mode:
```bash
uv run python manage.py runbot
```
You will see:
```
Starting Telegram bot in polling mode...
```
Now open your bot in Telegram and send `/start`!

---

## 🤖 Available Bot Commands

| Command | Description | Example |
| :--- | :--- | :--- |
| `/start` | Welcome message and introduction | `/start` |
| `/help` | Complete cheat sheet of available commands | `/help` |
| `/list` | Show all tasks sorted by urgency and countdowns | `/list` |
| `/due` | Quick view of overdue tasks and tasks due in the next 7 days | `/due` |
| `/add <title> \| <interval> <days\|months> \| <calendar\|elapsed>` | Register a recurring chore | `/add Clean AC Filters \| 30 days \| elapsed` |
| `/done <id> [notes]` | Mark chore completed today, log notes, and auto-reschedule | `/done 1 Replaced with 3M 1500 filter` |
| `/history <id>` | View timestamps and completion notes for chore | `/history 1` |
| `/export` | Receive `maintenance_report.md` file in the chat | `/export` |

### Scheduling Modes
- **`elapsed`**: Recalculates the next due date based on when you *actually* performed the task (e.g. descale coffee maker 30 days after last completed).
- **`calendar`**: Strictly advances in fixed calendar intervals (e.g. check smoke alarms every 6 months), preserving your routine regardless of early/late completion.

---

## ⏰ Proactive Alerts

You can run the alert check anytime or trigger it periodically via cron:
```bash
uv run python manage.py send_alerts
```
This scans for:
- ⏰ **T-3 Days Alert**: Task due in exactly 3 days.
- ⚠️ **T-1 Day Alert**: Task due tomorrow.
- 🚨 **Overdue Alert**: Task overdue or due today.

*Alerts are deduplicated per cycle in SQLite (`NotificationLog`) so you never get spammed.*

---

## 🧪 Running Tests

Execute the full Django test suite (23 tests covering ORM models, domain math, report generation, Telegram auth, and command dispatch):
```bash
uv run python manage.py test
```
