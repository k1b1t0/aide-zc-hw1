# Task Backlog: Household Maintenance Telegram Bot (Django + uv)

---

## 1. Project Initialization and Environment Setup

### Goal

Initialize the Python development environment using `uv`, set up a Django project with a `maintenance` application, and establish a working test harness.

### Acceptance criteria

- [x] Python environment is managed using `uv` with dependencies recorded in `pyproject.toml` and locked in `uv.lock`.
- [x] Django (>= 6.1) is installed and active in the environment.
- [x] Django project configuration (`config/`) and core app (`maintenance/`) exist and `maintenance` is registered in `INSTALLED_APPS` in `config/settings.py`.
- [x] Running `python manage.py check` exits cleanly with zero errors.
- [x] Running `python manage.py test` executes smoke tests in `maintenance/tests.py` and passes with zero failures.

### Out of scope

- Creating database models or executing application-specific migrations, moved to [#2 Maintenance Task and History Data Models](#2-maintenance-task-and-history-data-models).
- Telegram bot libraries or bot handlers, moved to [#5 Telegram Bot Client and Command Handler Base](#5-telegram-bot-client-and-command-handler-base).

### Constraints

- Stay inside repository root, `config/`, and `maintenance/`.
- All dependencies must be managed via `uv` and declared in `pyproject.toml`.
- Python version >= 3.13.

---

## 2. Maintenance Task and History Data Models

### Goal

Define and migrate the Django ORM models for maintenance tasks and their historical completion logs in SQLite.

### Acceptance criteria

- [ ] `Task` model is defined in `maintenance/models.py` with the following fields:
  - `title`: `CharField(max_length=255)`
  - `interval_type`: `CharField` with choices for strict calendar (`CALENDAR`) and dynamic elapsed (`ELAPSED`)
  - `interval_value`: `PositiveIntegerField` (representing days or months)
  - `last_completed`: `DateField(null=True, blank=True)`
  - `next_due`: `DateField(null=True, blank=True)`
  - `created_at`: `DateTimeField(auto_now_add=True)`
- [ ] `TaskHistory` model is defined in `maintenance/models.py` with:
  - `task`: `ForeignKey(Task, on_delete=models.CASCADE, related_name='history')`
  - `completed_at`: `DateTimeField(default=timezone.now)`
  - `notes`: `TextField(blank=True, default='')`
- [ ] Models specify human-readable string representations (`__str__`) showing task id/title and completion record details.
- [ ] A migration file is generated under `maintenance/migrations/` creating both tables.
- [ ] Running `python manage.py migrate` executes successfully against the default SQLite database without warnings or errors.
- [ ] Model field constraints and relationships are tested in `maintenance/tests.py`, including creating a `Task`, creating associated `TaskHistory` entries, and verifying cascade deletion when a task is removed.

### Out of scope

- Calculating next due dates or intervals automatically upon saving, moved to [#3 Recalculation Domain Logic and Unit Tests](#3-recalculation-domain-logic-and-unit-tests).
- Admin panel customizations or UI views, moved to [#10 Web Admin and Dashboard](#10-web-admin-and-dashboard).

### Constraints

- Code must reside strictly within `maintenance/models.py`, `maintenance/migrations/`, and `maintenance/tests.py`.
- Must use standard Django ORM field types compatible with SQLite.
- Do not add external packages to `pyproject.toml`.

---

## 3. Recalculation Domain Logic and Unit Tests

### Goal

Implement pure date recalculation domain services that compute next due dates and day countdowns for calendar and elapsed maintenance schedules.

### Acceptance criteria

- [ ] A service module `maintenance/services.py` defines calculation functions:
  - `calculate_next_due(task, completion_date=None) -> datetime.date`
  - `get_day_countdown(next_due_date, reference_date=None) -> int` (returns positive integer for remaining days, 0 for due today, negative integer for overdue days)
  - `format_countdown_status(countdown_days: int) -> str` (e.g., returns `"Due in 5 days"`, `"Due today"`, or `"Overdue by 3 days"`)
- [ ] For `ELAPSED` mode: `next_due` is computed by adding `interval_value` days to the completion date (or today if completion date not provided).
- [ ] For `CALENDAR` mode: `next_due` advances strictly by the fixed interval cadence from the previous target date (or sets next anchor date), regardless of whether completed early or late.
- [ ] Edge case handled: when a task is completed significantly overdue, next due date does not calculate to a date in the past; it advances to the next upcoming scheduled date.
- [ ] Edge case handled: leap year dates (e.g. Feb 29) and month-end dates (e.g. Jan 31 + 1 month) do not throw `ValueError`.
- [ ] Unit tests in `maintenance/tests.py` comprehensively test calendar mode, elapsed mode, on-time completion, overdue completion, early completion, and countdown formatting without making external network calls.

### Out of scope

- Triggering recalculations from Telegram commands, moved to [#7 Implement Task Management Commands (/add and /done)](#7-implement-task-management-commands-add-and-done).
- Updating database records automatically via signals, moved to [#7 Implement Task Management Commands (/add and /done)](#7-implement-task-management-commands-add-and-done).

### Constraints

- Business logic must reside in `maintenance/services.py` (or `maintenance/domain.py`) and be decoupled from HTTP requests or Telegram bot APIs.
- Use Python's built-in `datetime` and `calendar` libraries (or Django's `timezone` utilities).
- No external datetime libraries (e.g., `pendulum`, `dateutil`) unless approved and added to `pyproject.toml`.

---

## 4. Markdown Report Generation Service

### Goal

Implement a report generation service that queries active maintenance tasks, their countdown statuses, and historical completion notes from the database and returns a structured Markdown document.

### Acceptance criteria

- [ ] A service function (e.g., `generate_markdown_report() -> str`) is defined in `maintenance/services.py` (or `maintenance/reports.py`).
- [ ] Report starts with a top-level `# Household Maintenance Report` header and a generation timestamp line in UTC ISO format (e.g., `Generated on: YYYY-MM-DD HH:MM:SS UTC`).
- [ ] Report contains distinct sections: `## Overdue Tasks`, `## Upcoming Tasks`, and `## Completion History`.
- [ ] Overdue tasks section displays a Markdown table with columns: `| Task ID | Title | Recurrence | Next Due Date | Days Overdue |`.
- [ ] Upcoming tasks section displays a Markdown table with columns: `| Task ID | Title | Recurrence | Next Due Date | Days Remaining |` sorted ascending by due date.
- [ ] Completion history section lists entries grouped by task, displaying completion timestamps and note text.
- [ ] Empty state handling: If there are no overdue tasks, displays `_No overdue tasks._`. If there are no tasks in the database, displays `_No maintenance tasks recorded._`.
- [ ] Null handling: Tasks with `next_due = None` display `N/A` without raising a `TypeError` or formatting error.
- [ ] Special character sanitization: Markdown table delimiters (`|`) or multiline notes in task titles and notes are escaped/sanitized to prevent broken table columns.
- [ ] Unit tests in `maintenance/tests.py` verify markdown generation with empty tables, populated tasks, overdue tasks, and multi-line notes.

### Out of scope

- Telegram `/export` bot command handler and uploading the file as a Telegram document, moved to [#8 Implement History and Export Commands (/history and /export)](#8-implement-history-and-export-commands-history-and-export).
- Exporting to PDF or HTML formats, moved to [#11 Optional PDF/HTML Export](#11-optional-pdfhtml-export).

### Constraints

- Files must stay inside `maintenance/` (`maintenance/reports.py` or `maintenance/services.py` and `maintenance/tests.py`).
- No external document generators or Markdown parsing packages; use standard string templates or formatting utilities.
- Pure Python/Django ORM service with no dependency on Telegram APIs.

---

## 5. Telegram Bot Client and Command Handler Base

### Goal

Set up the Telegram bot client framework within Django, configure authentication and token handling from environment variables, and implement `/start` and `/help` handlers with a management command runner.

### Acceptance criteria

- [ ] Bot dependencies (`python-telegram-bot>=20.0`) are declared in `pyproject.toml` and installed.
- [ ] Settings configuration in `config/settings.py` reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_AUTHORIZED_USER_ID` (as an integer or comma-separated list of integers) from environment variables.
- [ ] An authentication decorator or filter is implemented to ignore or reject messages from unauthorized Telegram `user_id`s with an unauthorized response.
- [ ] Command handler for `/start` sends a welcome message introducing the Household Maintenance Tracker and listing available commands.
- [ ] Command handler for `/help` returns the list of all supported commands with brief usage examples.
- [ ] A custom Django management command `python manage.py runbot` is implemented in `maintenance/management/commands/runbot.py` to start the bot in long-polling mode.
- [ ] Graceful shutdown: stopping the management command via SIGINT/Ctrl+C exits without leaving zombie threads or unhandled exceptions.
- [ ] Tests verify that unauthorized user IDs receive an access denied response or are ignored, while authorized IDs receive the welcome/help response.

### Out of scope

- Task query commands (`/list`, `/due`), moved to [#6 Implement Status and Query Commands (/list and /due)](#6-implement-status-and-query-commands-list-and-due).
- Task modification commands (`/add`, `/done`), moved to [#7 Implement Task Management Commands (/add and /done)](#7-implement-task-management-commands-add-and-done).
- Webhook deployment setup for production, moved to [#12 Production Telegram Webhook Integration](#12-production-telegram-webhook-integration).

### Constraints

- Uses `python-telegram-bot` version 20+ (async API).
- Configuration must load securely via environment variables (never hardcoded in source code).
- Bot code must reside in `maintenance/bot/` or `maintenance/management/commands/`.

---

## 6. Implement Status and Query Commands (/list and /due)

### Goal

Implement Telegram slash commands `/list` and `/due` to allow the user to view active maintenance tasks and urgency countdowns ordered by due date.

### Acceptance criteria

- [ ] Command handler `/list` queries all active `Task` objects from the database ordered by `next_due` ascending.
- [ ] `/list` output formats each task showing: ID, title, recurrence interval, next due date, and calculated countdown status (e.g. `[1] Clean HVAC Filters - Every 90 days - Due in 4 days (2026-09-15)`).
- [ ] When no tasks exist in the database, `/list` responds with `No maintenance tasks found. Use /add to create one.`
- [ ] Command handler `/due` filters tasks that are either overdue (`next_due < today`) or due within the upcoming 7 days (`next_due <= today + 7 days`).
- [ ] `/due` clearly differentiates overdue items (e.g. prefixed with `⚠️ OVERDUE by X days`) from upcoming items (e.g. `⏳ Due in X days`).
- [ ] When no tasks are due within 7 days and none are overdue, `/due` responds with `All caught up! No tasks due in the next 7 days.`
- [ ] Long output handling: If task count exceeds Telegram's 4096 character message limit, messages are cleanly chunked without cutting off in the middle of a line.
- [ ] Unit/integration tests verify `/list` and `/due` formatting for empty state, overdue items, near-due items, and items due beyond 7 days.

### Out of scope

- Marking tasks as completed from the list, moved to [#7 Implement Task Management Commands (/add and /done)](#7-implement-task-management-commands-add-and-done).
- Viewing historical completion notes, moved to [#8 Implement History and Export Commands (/history and /export)](#8-implement-history-and-export-commands-history-and-export).

### Constraints

- Must query data using Django ORM (`sync_to_async` if running inside async handlers).
- Must respect the authorized user filter established in [#5 Telegram Bot Client and Command Handler Base](#5-telegram-bot-client-and-command-handler-base).
- Bot handlers reside in `maintenance/bot/handlers/` or `maintenance/bot.py`.

---

## 7. Implement Task Management Commands (/add and /done)

### Goal

Implement Telegram commands `/add` to register new recurring maintenance tasks and `/done` to log completion with optional notes and automatically reschedule the next due date.

### Acceptance criteria

- [ ] `/add <title> | <interval_value> <days|months> | <calendar|elapsed>` parses input arguments and creates a new `Task` record.
  - Example: `/add Clean AC Filters | 30 days | elapsed`
- [ ] If `/add` receives malformed arguments, it returns a clear error message with the expected syntax and examples.
- [ ] Successfully creating a task returns a confirmation message showing task ID, title, mode, and computed initial `next_due` date.
- [ ] `/done <id> [optional notes...]` marks the specified task completed:
  - Looks up task by ID; returns error if ID is invalid or non-existent (e.g. `Task with ID 99 not found.`).
  - Creates a `TaskHistory` record linked to the task with timestamp `timezone.now()` and any user-provided notes.
  - Updates task `last_completed` date to today.
  - Recalculates and updates task `next_due` using the domain recalculation service from task #3.
  - Saves the updated task within an atomic database transaction (`transaction.atomic`).
- [ ] `/done` responds with a confirmation message displaying the completion logged, notes saved, and the newly calculated next due date.
- [ ] Tests verify `/add` with valid/invalid parameters and `/done` with valid ID, invalid ID, with notes, without notes, and checks DB state updates.

### Out of scope

- Deleting or editing existing task definitions, moved to [#13 Task Editing and Deletion Commands (/edit, /delete)](#13-task-editing-and-deletion-commands-edit-delete).
- Interactive Telegram inline keyboard selection, moved to [#14 Interactive Buttons and Inline Keyboards](#14-interactive-buttons-and-inline-keyboards).

### Constraints

- Must use `transaction.atomic()` when creating `TaskHistory` and updating `Task`.
- All user input must be validated and sanitized before database insertion.
- Code resides in `maintenance/bot/` and tests in `maintenance/tests.py`.

---

## 8. Implement History and Export Commands (/history and /export)

### Goal

Implement Telegram slash commands `/history <id>` to inspect past completions and notes for a task, and `/export` to send the generated Markdown report directly to the chat as a file document.

### Acceptance criteria

- [ ] Command `/history <id>` looks up task by ID and fetches all related `TaskHistory` records sorted by `completed_at` descending.
- [ ] If task ID does not exist, responds with `Task #<id> not found.`
- [ ] If task has no recorded completions, responds with `No completion history recorded for task #<id> (<title>).`
- [ ] Displays historical entries with formatted completion date and note text (or `(No notes provided)` if empty).
- [ ] Command `/export` invokes `generate_markdown_report()` from task #4 to compile the markdown report.
- [ ] The generated report content is converted to an in-memory document file (using `io.BytesIO`) with filename `maintenance_report.md`.
- [ ] The bot sends the file using Telegram's `send_document` API with a caption summarizing task totals.
- [ ] Error handling: If report generation fails or database is unreachable, catches the exception and returns a user-friendly error message rather than crashing the bot.
- [ ] Tests in `maintenance/tests.py` verify `/history` response format for populated and empty histories, and mock Telegram's `send_document` to test `/export`.

### Out of scope

- Automatic scheduled daily/weekly report delivery, moved to [#15 Scheduled Digest Reports](#15-scheduled-digest-reports).
- Exporting to CSV or JSON formats, moved to [#16 Multi-format Data Export](#16-multi-format-data-export).

### Constraints

- Do not write temporary report files to disk; use `io.BytesIO` / `io.StringIO` for file transmission.
- Report formatting must reuse the Markdown report service created in [#4 Markdown Report Generation Service](#4-markdown-report-generation-service).
- Handlers reside in `maintenance/bot/`.

---

## 9. Proactive Notifications and Scheduled Alerts Service

### Goal

Implement a background alerting service and Django management command that checks for tasks due in T-3 days, T-1 day, or overdue, and delivers proactive notifications to the authorized Telegram user.

### Acceptance criteria

- [ ] An alert tracking model (e.g. `NotificationLog` or tracking fields on `Task`) is created to record which alerts (T-3, T-1, Overdue) have already been sent for the current due cycle.
- [ ] An alert evaluation service (e.g. `evaluate_due_alerts()`) identifies:
  - Tasks with `next_due == today + 3 days` (T-3 alert)
  - Tasks with `next_due == today + 1 day` (T-1 alert)
  - Tasks with `next_due <= today` (Overdue alert)
- [ ] Notification deduplication: A notification is sent at most once per task per alert type per due cycle; completing a task and rescheduling resets the notification tracker.
- [ ] When matching tasks are found, messages are formatted with task title, due date, and days remaining, and sent via Telegram's `send_message` API to `TELEGRAM_AUTHORIZED_USER_ID`.
- [ ] A Django management command `python manage.py send_alerts` is created to execute the alert check once (suitable for external cron jobs).
- [ ] A periodic background job or scheduler loop (e.g., using `python-telegram-bot`'s `JobQueue`) runs the alert check once daily at a designated time (e.g., 09:00 AM).
- [ ] Tests verify that T-3, T-1, and overdue tasks trigger alerts, verify duplicate runs on the same day do not send duplicate messages, and verify alerts reset after task completion.

### Out of scope

- Customizable alert intervals per task (e.g. custom T-7 or T-14), moved to [#17 Custom Alert Schedules per Task](#17-custom-alert-schedules-per-task).
- Interactive snooze buttons in Telegram notifications, moved to [#14 Interactive Buttons and Inline Keyboards](#14-interactive-buttons-and-inline-keyboards).

### Constraints

- Must support standalone execution via `python manage.py send_alerts` without requiring the long-running bot process.
- Must persist notification dispatch state in SQLite to guarantee deduplication across restarts.
- Adhere to Telegram rate limits when sending multiple alert messages.

---

## Follow-up Tasks (Backlog)

### 10. Web Admin and Dashboard
Goal: Provide Django standard admin interface configuration for `Task` and `TaskHistory` models.

### 11. Optional PDF/HTML Export
Goal: Allow exporting the maintenance report as a styled PDF or HTML file in addition to Markdown.

### 12. Production Telegram Webhook Integration
Goal: Configure Django view endpoints and SSL webhook processing for production hosting environments.

### 13. Task Editing and Deletion Commands (/edit, /delete)
Goal: Support modifying task parameters (title, interval, mode) and deleting tasks via Telegram commands.

### 14. Interactive Buttons and Inline Keyboards
Goal: Enhance `/list`, `/due`, and alert notifications with Telegram inline action buttons (e.g., "Mark Done", "Snooze").

### 15. Scheduled Digest Reports
Goal: Enable periodic weekly or monthly maintenance summary digests delivered automatically to Telegram.

### 16. Multi-format Data Export
Goal: Add support for exporting task and history data to JSON and CSV formats.

### 17. Custom Alert Schedules per Task
Goal: Allow per-task configuration of notification lead times (e.g., alert 14 days before for HVAC filters requiring part orders).
