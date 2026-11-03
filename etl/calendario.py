"""Calendário único para corte diário e fechamento mensal."""
from datetime import date, timedelta


def last_business_day(value, holidays):
    day = date.fromisoformat(str(value)[:10])
    while day.weekday() >= 5 or day.isoformat() in holidays:
        day -= timedelta(days=1)
    return day


def previous_business_day(value, holidays):
    day = date.fromisoformat(str(value)[:10]) - timedelta(days=1)
    return last_business_day(day, holidays)
