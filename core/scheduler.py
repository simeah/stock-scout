"""
core/scheduler.py
=================
Optional background scheduler for automated weekly Sunday night runs.
Uses APScheduler (pip install apscheduler).

The scheduler runs inside the Streamlit process — no separate process needed.
For production use, a cron job is more reliable (instructions provided in UI).
"""

import threading
from datetime import datetime
from typing import Callable

_scheduler = None
_lock      = threading.Lock()


def start_weekly_scheduler(
    run_fn:     Callable,       # the function to call (no args)
    day:        str = "sun",    # day of week
    hour:       int = 21,       # 9 PM
    minute:     int = 0,
    timezone:   str = "Europe/London",
) -> bool:
    """
    Start a weekly APScheduler job.
    Returns True if started, False if APScheduler not installed.
    """
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron         import CronTrigger
    except ImportError:
        return False

    with _lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)

        _scheduler = BackgroundScheduler(timezone=timezone)
        _scheduler.add_job(
            run_fn,
            CronTrigger(day_of_week=day, hour=hour, minute=minute, timezone=timezone),
            id="weekly_run",
            replace_existing=True,
        )
        _scheduler.start()
    return True


def stop_scheduler():
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def next_run_time() -> str | None:
    if not is_running():
        return None
    try:
        job = _scheduler.get_job("weekly_run")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%A %d %b %Y at %H:%M %Z")
    except Exception:
        pass
    return None


def cron_instructions(hour: int = 21, minute: int = 0) -> str:
    """Return cron setup instructions for the user's platform."""
    return f"""
**Option A — Cron job (Mac/Linux, most reliable):**
```bash
# Open crontab
crontab -e

# Add this line to run every Sunday at {hour:02d}:{minute:02d}
{minute} {hour} * * 0 cd ~/stockscout && python run_headless.py >> ~/stockscout/logs/run.log 2>&1
```

**Option B — Windows Task Scheduler:**
1. Open Task Scheduler → Create Basic Task
2. Trigger: Weekly → Sunday → {hour:02d}:{minute:02d}
3. Action: Start a program → `python`
4. Arguments: `~/stockscout/run_headless.py`

**Option C — Keep the Streamlit app open**
The built-in scheduler above works as long as the app tab is open.
"""
