"""Decay-логика: авто-resolve проблем по времени последней ошибки."""
from datetime import datetime, timezone

DECAY_HOURS = {
    "critical": 12,
    "warning": 6,
    "info": 3,
}

BURST_WINDOW_HOURS = 2
BURST_AGE_HOURS = 8

def should_auto_resolve(info: dict, now: datetime = None) -> bool:
    """Проверяет, должна ли проблема быть авто-resolved на основе timeline."""
    if now is None:
        now = datetime.now(timezone.utc)
    
    last_error_str = info.get("last_error")
    if not last_error_str:
        return False
    
    try:
        last_error = datetime.fromisoformat(last_error_str)
        if last_error.tzinfo is None:
            last_error = last_error.replace(tzinfo=timezone.utc)
    except:
        return False
    
    age_hours = round((now - last_error).total_seconds() / 3600, 2)
    severity = info.get("severity", "warning")
    threshold = DECAY_HOURS.get(severity, 6)
    
    if age_hours > threshold:
        return True
    
    window_hours = info.get("error_window_hours")
    if window_hours is not None and window_hours < BURST_WINDOW_HOURS:
        if age_hours > BURST_AGE_HOURS:
            return True
    
    return False
