"""CalDAV client that writes events into the target iCloud calendar."""
from __future__ import annotations

from datetime import datetime, timedelta

import caldav
from icalendar import Alarm, Calendar
from icalendar import Event as ICalEvent

from .models import Event, event_uid, normalize_text


def vevent_for_event(event: Event) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//event-calendar-sync//EN")
    cal.add("version", "2.0")

    item = ICalEvent()
    item.add("uid", event_uid(event))
    item.add("summary", event.display_title)
    item.add("dtstart", event.start)
    item.add("dtend", event.start + timedelta(hours=2))
    item.add("dtstamp", datetime.now(tz=event.start.tzinfo))
    if event.location:
        item.add("location", event.location)
    if event.best_url:
        item.add("url", event.best_url)
    if event.description:
        item.add("description", event.description)

    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", "Event reminder")
    alarm.add("trigger", timedelta(hours=-24))
    item.add_component(alarm)

    cal.add_component(item)
    return cal


class CalendarClient:
    def __init__(
        self,
        username: str,
        app_password: str,
        caldav_url: str,
        calendar_name: str,
    ) -> None:
        self.username = username
        self.app_password = app_password
        self.caldav_url = caldav_url
        self.calendar_name = calendar_name
        self._calendar = None

    def connect(self):
        client = caldav.DAVClient(
            url=self.caldav_url,
            username=self.username,
            password=self.app_password,
        )
        principal = client.principal()
        for calendar in principal.calendars():
            if calendar.name == self.calendar_name:
                self._calendar = calendar
                return calendar
        raise RuntimeError(
            f'Calendar "{self.calendar_name}" was not found. Create it in Apple Calendar first.'
        )

    @property
    def calendar(self):
        return self._calendar or self.connect()

    def existing_keys(self, start: datetime, end: datetime) -> set[str]:
        keys: set[str] = set()
        for result in self.calendar.date_search(start=start, end=end):
            component = result.icalendar_component
            uid = str(component.get("uid", ""))
            summary = normalize_text(str(component.get("summary", "")))
            dtstart = component.get("dtstart")
            url = str(component.get("url", ""))
            if uid:
                keys.add(f"uid:{uid}")
            if summary and dtstart:
                keys.add(f"title-start:{summary}|{dtstart.dt}")
            if url and dtstart:
                keys.add(f"url-start:{url}|{dtstart.dt}")
        return keys

    def exists(self, event: Event, keys: set[str]) -> bool:
        uid = event_uid(event)
        title = normalize_text(event.display_title)
        return (
            f"uid:{uid}" in keys
            or f"title-start:{title}|{event.start}" in keys
            or bool(event.best_url and f"url-start:{event.best_url}|{event.start}" in keys)
        )

    def add_event(self, event: Event) -> None:
        self.calendar.save_event(vevent_for_event(event).to_ical().decode("utf-8"))
