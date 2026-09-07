# Household Maintenance Tracker - Telegram Bot

## 1. Project Overview & Objective
A Telegram bot designed for single-user/personal long-term household maintenance tracking. It monitors recurring upkeep tasks (weekly, monthly, quarterly, yearly), tracks day counts and due dates, triggers proactive reminders, logs completion history with notes, and allows exporting all records to a downloadable Markdown report.

---

## 2. Core Feature Scope

### 2.1 Task Tracking & Recalculation
- **Daycount & Target Date**: Every maintenance item tracks its last completed date, next target due date, and an active day count countdown (e.g., *"Due in 5 days"* or *"Overdue by 3 days"*).
- **Hybrid Recalculation Modes (Configurable per item)**:
  1. **Strict Calendar**: Resets based on fixed calendar intervals (e.g., 1st of every 3 months), independent of when the task was completed.
  2. **Dynamic / Elapsed**: Recalculates $N$ days/months from the *actual completion date* (e.g., coffee machine descaling every 60 days from last run).

### 2.2 User Interface & Commands (Text-based Slash Commands)
- `/start` or `/help`: Display instructions and available commands.
- `/add`: Add a new maintenance task (name, interval, mode: calendar vs. elapsed).
- `/list`: List all active maintenance items sorted by urgency (with day counts).
- `/due`: Quick overview of overdue tasks and tasks due within the next 7 days.
- `/done <id> [notes]`: Mark an item as completed today, save optional notes, and automatically schedule the next due date.
- `/history <id>`: View the completion history and notes for a specific item.
- `/export`: Generate and send the comprehensive Markdown summary file directly via Telegram for download.

### 2.3 Proactive Reminders & Notifications
- **Automated Alerts**:
  - **T-3 Days Alert**: Notification sent 3 days before a task deadline.
  - **T-1 Day Alert**: Final warning sent 1 day before the deadline.
  - **Overdue Alert**: Flagged in regular digests if a deadline passes.
- **On-Demand Checking**: Users can check the current status anytime using `/due` or `/list`.

### 2.4 History & Notes
- Every completion event logs:
  - Timestamp of completion.
  - Optional custom notes (e.g., model/part number replaced, cost, brand, observations).

### 2.5 Storage & Export
- **Primary Database**: Local SQLite (`maintenance.db`).
  - Table: `tasks` (id, title, interval_type, interval_value, last_completed, next_due, created_at).
  - Table: `history` (id, task_id, completed_at, notes).
- **Markdown Export**:
  - Triggered via `/export`.
  - Compiles all tasks, upcoming deadlines, status, and full historical logs into a clean, human-readable `.md` file sent via Telegram document upload.

---

## 3. Recommended Tech Stack
- **Language**: Python 3.10+
- **Telegram Framework**: `python-telegram-bot` (v20+ async)
- **Database**: SQLite3 (`sqlite3` standard library)
- **Scheduler**: `APScheduler` or built-in `JobQueue` from `python-telegram-bot`
- **Config**: `.env` file for `TELEGRAM_BOT_TOKEN` and authorized `USER_ID`.
