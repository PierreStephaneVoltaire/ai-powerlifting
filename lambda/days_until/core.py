from datetime import date, datetime


async def days_until(target_date: str, label: str = "target") -> dict:
    """Calculate days until a target date.

    Args:
        target_date: ISO8601 date string (YYYY-MM-DD)
        label: Human label for the milestone (e.g., "comp", "deload start")

    Returns:
        {
            "label": "comp",
            "target_date": "2026-06-14",
            "today": "2026-03-07",
            "days_remaining": 99,
            "weeks_remaining": 14,
            "days_elapsed_since": null,
            "is_past": false
        }

    Raises:
        ValueError: If target_date format invalid
    """
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {target_date}. Expected YYYY-MM-DD.")

    today = date.today()
    today_str = today.isoformat()

    delta = (target - today).days

    if delta > 0:
        return {
            "label": label,
            "target_date": target_date,
            "today": today_str,
            "days_remaining": delta,
            "weeks_remaining": delta // 7,
            "days_elapsed_since": None,
            "is_past": False,
        }
    else:
        return {
            "label": label,
            "target_date": target_date,
            "today": today_str,
            "days_remaining": 0,
            "weeks_remaining": 0,
            "days_elapsed_since": abs(delta),
            "is_past": True,
        }