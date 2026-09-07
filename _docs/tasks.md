# Task Backlog: Household Maintenance Telegram Bot (Django + uv)

## 1. Project Initialization and Environment Setup
Goal: Initialize the Python environment with `uv`, set up Django with an initial app, and establish a working test harness.
Description: Initialize a Python virtual environment using `uv` and install Django and testing dependencies. Create a new Django project and a maintenance core application, configure the app within the project settings, and write an initial smoke test in the app's test suite to verify that `python manage.py test` passes cleanly.

## 2. Maintenance Task and History Data Models
Goal: Define the database schema for maintenance tasks and completion history using Django ORM.
Description: Create the `Task` model with fields for title, interval type (calendar vs. elapsed), interval value, last completed date, and next due date. Create the related `TaskHistory` model to capture completion timestamps and optional maintenance notes. Generate and execute initial database migrations targeting the local SQLite database.

## 3. Recalculation Domain Logic and Unit Tests
Goal: Implement the core date calculation logic for strict calendar and dynamic elapsed intervals.
Description: Write pure business logic service functions (or model methods) that compute the next due date and remaining day counts based on the task's schedule type. Ensure calculations handle both fixed calendar intervals and dynamic elapsed time from the actual completion date, as well as overdue scenarios. Write comprehensive unit tests covering all calculation edge cases.

## 4. Markdown Report Generation Service
Goal: Implement a service to compile tasks, countdown statuses, and completion history into a downloadable Markdown report.
Description: Create a utility module that queries all active maintenance tasks and their historical logs from the database. Format the data into structured Markdown tables and sections detailing overdue tasks, upcoming maintenance schedules, and logged notes. Write a unit test asserting that the generated Markdown string or file accurately reflects the underlying database records.

## 5. Telegram Bot Client and Command Handler Base
Goal: Integrate Telegram bot webhook or polling infrastructure within the Django ecosystem.
Description: Set up a Telegram bot interface using environment-driven configurations for the bot token and authorized chat ID. Implement base slash command handlers for `/start` and `/help` that return command usage instructions to the user. Provide a management command or runner script to launch the bot listener in polling mode for local development.

## 6. Implement Status and Query Commands (/list and /due)
Goal: Add `/list` and `/due` slash commands to query maintenance tasks with countdowns.
Description: Connect the Telegram command dispatcher to Django's ORM to fetch tasks ordered by urgency. Implement `/list` to format all active tasks with their target dates and day counts (e.g., "Due in 4 days" or "Overdue by 2 days"). Implement `/due` to filter and display only items that are overdue or due within the next 7 days.

## 7. Implement Task Management Commands (/add and /done)
Goal: Enable adding tasks and marking tasks as completed with optional notes via Telegram commands.
Description: Implement the `/add` command parser to create new tasks specifying title, recurrence interval, and schedule mode (calendar vs. elapsed). Implement the `/done <id> [notes]` command to record a new completion entry in `TaskHistory`, recalculate the next due date using the domain logic service, and confirm the updated schedule to the user.

## 8. Implement History and Export Commands (/history and /export)
Goal: Provide task history inspection and downloadable Markdown report delivery via Telegram.
Description: Implement the `/history <id>` command to display past completion dates and saved notes for a specific maintenance task. Implement the `/export` command to trigger the Markdown generation service, produce `maintenance_report.md`, and upload it directly into the Telegram chat as a downloadable document.

## 9. Proactive Notifications and Scheduled Alerts Service
Goal: Implement scheduled checks to deliver proactive T-3 days and T-1 day deadline alerts to Telegram.
Description: Create a Django management command or background scheduled task that scans for tasks due in exactly 3 days, 1 day, or currently overdue. Ensure the alert mechanism tracks notification state to prevent duplicate alerts for the same cycle. Hook the check into a periodic execution mechanism (such as a cron job or scheduled task loop) sending notifications directly to the authorized user.
