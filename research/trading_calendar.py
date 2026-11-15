"""Immutable, versioned UTC trading calendar for Level 3 forward evidence.

The calendar defines a two-hour London-morning observation window (07:00-09:00 UTC).
It reduces daily collection time, not the number of required trading days. Only
explicitly listed closures are neutral; unknown/missing weekdays remain expected days.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


DEFAULT_CALENDAR_PATH = Path(__file__).with_name("trading_calendar_v1.json")


class TradingCalendar:
    def __init__(self, raw: bytes):
        try:
            config = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("trading calendar must be valid UTF-8 JSON") from exc
        required = {
            "version", "timezone", "weekdays", "session_start_utc_hour",
            "session_end_utc_hour", "minimum_covered_hours", "closures",
        }
        if not isinstance(config, dict) or set(config) != required:
            raise ValueError("trading calendar has missing or unexpected fields")
        if not isinstance(config["version"], str) or not config["version"].strip():
            raise ValueError("calendar version must be a non-empty string")
        if config["timezone"] != "UTC":
            raise ValueError("only UTC calendars are supported")
        weekdays = config["weekdays"]
        if (not isinstance(weekdays, list) or not weekdays
                or any(type(day) is not int or day not in range(7) for day in weekdays)
                or len(set(weekdays)) != len(weekdays)):
            raise ValueError("weekdays must be unique ISO weekday indexes (Monday=0)")
        start, end = config["session_start_utc_hour"], config["session_end_utc_hour"]
        minimum = config["minimum_covered_hours"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= 24:
            raise ValueError("calendar session must be a valid same-day UTC hour range")
        if type(minimum) is not int or minimum != end - start:
            raise ValueError("all configured session hours must be covered")
        closures = config["closures"]
        if not isinstance(closures, list):
            raise ValueError("closures must be a list of ISO dates")
        try:
            parsed_closures = [date.fromisoformat(value) for value in closures]
        except (TypeError, ValueError) as exc:
            raise ValueError("each closure must be an ISO date") from exc
        if len(set(parsed_closures)) != len(parsed_closures):
            raise ValueError("calendar closure dates must be unique")
        self.config = config
        self.version = config["version"]
        self.weekdays = frozenset(weekdays)
        self.start_hour = start
        self.end_hour = end
        self.minimum_covered_hours = minimum
        self.closures = frozenset(parsed_closures)
        self.sha256 = hashlib.sha256(raw).hexdigest()

    @classmethod
    def load(cls, path: Path = DEFAULT_CALENDAR_PATH) -> "TradingCalendar":
        return cls(path.read_bytes())

    def is_expected_trading_day(self, day: date) -> bool:
        return day.weekday() in self.weekdays and day not in self.closures

    def expected_hours(self, day: date) -> tuple[int, ...]:
        return tuple(range(self.start_hour, self.end_hour)) if self.is_expected_trading_day(day) else ()

    def covered_hours(self, timestamps: list[str], day: date) -> frozenset[int]:
        covered = set()
        for value in timestamps:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (AttributeError, TypeError, ValueError):
                continue
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                continue
            parsed = parsed.astimezone(timezone.utc)
            if parsed.date() == day and self.start_hour <= parsed.hour < self.end_hour:
                covered.add(parsed.hour)
        return frozenset(covered)

    def latest_completed_trading_day(self, now: datetime) -> date:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("calendar evaluation time must be timezone-aware")
        now = now.astimezone(timezone.utc)
        day = now.date()
        if now.hour < self.end_hour:
            day -= timedelta(days=1)
        while not self.is_expected_trading_day(day):
            day -= timedelta(days=1)
        return day

    def consecutive_covered_days(self, timestamps: list[str], now: datetime) -> tuple[int, str]:
        day = self.latest_completed_trading_day(now)
        streak = 0
        while self.is_expected_trading_day(day):
            expected = set(self.expected_hours(day))
            if self.covered_hours(timestamps, day) != expected:
                break
            streak += 1
            day -= timedelta(days=1)
            while not self.is_expected_trading_day(day):
                day -= timedelta(days=1)
        return streak, self.latest_completed_trading_day(now).isoformat()

    def daily_coverage(self, timestamps: list[str], day: date) -> dict:
        expected = set(self.expected_hours(day))
        covered = self.covered_hours(timestamps, day)
        return {
            "date": day.isoformat(),
            "expected_hours_utc": sorted(expected),
            "covered_hours_utc": sorted(covered),
            "covered_hour_count": len(covered),
            "required_hour_count": self.minimum_covered_hours if expected else 0,
            "complete": bool(expected) and covered == expected,
            "market_closed_or_non_trading_day": not bool(expected),
        }
