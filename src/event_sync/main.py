"""Entry point for event-calendar-sync.

Collects events from every provider, dedupes them, and either prints a dry
run summary or writes new events to the configured iCloud calendar over
CalDAV.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .calendar_client import CalendarClient
from .models import (
    Event,
    Settings,
    event_uid,
    has_duplicate,
    load_settings,
    send_discord_summary,
)
from .providers import fetch_bandsintown, fetch_public_pages, fetch_ticketmaster


def collect_events(settings: Settings) -> tuple[list[Event], list[str]]:
    collected: list[Event] = []
    errors: list[str] = []
    providers = [
        ("ticketmaster", lambda: fetch_ticketmaster(settings)),
        ("bandsintown", lambda: fetch_bandsintown(settings)),
        ("public_pages", lambda: fetch_public_pages(settings)),
    ]
    for name, call in providers:
        try:
            collected.extend(call())
        except Exception as exc:
            errors.append(f"{name}: {exc.__class__.__name__}")
    return collected, errors


def unique_events(events: list[Event]) -> list[Event]:
    unique: list[Event] = []
    for event in sorted(events, key=lambda item: (item.start.isoformat(), item.title)):
        if not has_duplicate(event, unique):
            unique.append(event)
    return unique


def run(settings: Settings) -> dict:
    events, provider_errors = collect_events(settings)
    events = unique_events(events)
    summary = {
        "dry_run": settings.dry_run,
        "found": len(events),
        "added": 0,
        "skipped_duplicates": 0,
        "provider_errors": provider_errors,
    }

    if settings.dry_run:
        for event in events:
            print(f"DRY RUN would add: {event.display_title} | {event.start} | {event.best_url}")
            summary["added"] += 1
        send_discord_summary(settings.discord_webhook_url, summary)
        return summary

    if not settings.icloud_username or not settings.icloud_app_password:
        raise RuntimeError("ICLOUD_USERNAME and ICLOUD_APP_PASSWORD are required when DRY_RUN=false")

    tz = ZoneInfo(settings.default_timezone)
    start = datetime.now(tz=tz) - timedelta(days=1)
    end = start + timedelta(days=settings.lookahead_days + 2)
    client = CalendarClient(
        username=settings.icloud_username,
        app_password=settings.icloud_app_password,
        caldav_url=settings.icloud_caldav_url,
        calendar_name=settings.target_calendar_name,
    )
    existing = client.existing_keys(start, end)
    for event in events:
        if client.exists(event, existing):
            summary["skipped_duplicates"] += 1
            continue
        client.add_event(event)
        existing.add(f"uid:{event_uid(event)}")
        summary["added"] += 1

    send_discord_summary(settings.discord_webhook_url, summary)
    return summary


def main() -> None:
    settings = load_settings()
    summary = run(settings)
    print(
        "Finished event-calendar-sync: "
        f"found={summary['found']} added={summary['added']} "
        f"duplicates={summary['skipped_duplicates']} dry_run={summary['dry_run']}"
    )


if __name__ == "__main__":
    main()
