"""External data sources for event-calendar-sync.

Each fetch_* function returns a list[Event]. Every network call is wrapped by
collect_events() in main.py, so one provider failing (bad key, site down,
rate limit) never blocks the others.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .models import Event, Settings

TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
BANDSINTOWN_URL = "https://rest.bandsintown.com/artists/{artist}/events/"
REQUEST_TIMEOUT = 15


def _lookahead_window(settings: Settings) -> tuple[datetime, datetime]:
    tz = ZoneInfo(settings.default_timezone)
    start = datetime.now(tz=tz)
    end = start + timedelta(days=settings.lookahead_days)
    return start, end


# ---------------------------------------------------------------------------
# Ticketmaster Discovery API
# https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
# ---------------------------------------------------------------------------
def fetch_ticketmaster(settings: Settings) -> list[Event]:
    if not settings.ticketmaster_api_key or not settings.artists or not settings.markets:
        return []

    start, end = _lookahead_window(settings)
    events: list[Event] = []

    for artist in settings.artists:
        for market in settings.markets:
            params = {
                "apikey": settings.ticketmaster_api_key,
                "keyword": artist,
                "city": market,
                "classificationName": "music",
                "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "size": 50,
            }
            response = requests.get(TICKETMASTER_URL, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("_embedded", {}).get("events", []):
                events.append(_ticketmaster_event(item, settings))

    return events


def _ticketmaster_event(item: dict, settings: Settings) -> Event:
    tz = ZoneInfo(settings.default_timezone)
    dates = item.get("dates", {}).get("start", {})
    if dates.get("dateTime"):
        start = date_parser.isoparse(dates["dateTime"]).astimezone(tz)
    else:
        local_date = dates.get("localDate", "")
        local_time = dates.get("localTime", "00:00:00")
        start = datetime.fromisoformat(f"{local_date}T{local_time}").replace(tzinfo=tz)

    venues = item.get("_embedded", {}).get("venues", [])
    venue_name = venues[0].get("name", "") if venues else ""

    return Event(
        title=item.get("name", "Untitled event"),
        start=start,
        source="ticketmaster",
        url=item.get("url", ""),
        location=venue_name,
    )


# ---------------------------------------------------------------------------
# Bandsintown Artist Events API
# https://help.artists.bandsintown.com/en/articles/9186477-api-documentation
# ---------------------------------------------------------------------------
def fetch_bandsintown(settings: Settings) -> list[Event]:
    if not settings.bandsintown_app_id or not settings.artists:
        return []

    market_names = {m.lower() for m in settings.markets}
    events: list[Event] = []

    for artist in settings.artists:
        url = BANDSINTOWN_URL.format(artist=requests.utils.quote(artist))
        params = {"app_id": settings.bandsintown_app_id, "date": "upcoming"}
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        for item in response.json():
            event = _bandsintown_event(item, settings)
            if not market_names or _matches_market(event.location, market_names):
                events.append(event)

    return events


def _matches_market(location: str, market_names: set[str]) -> bool:
    location_lower = location.lower()
    return any(market in location_lower for market in market_names)


def _bandsintown_event(item: dict, settings: Settings) -> Event:
    tz = ZoneInfo(settings.default_timezone)
    start = date_parser.isoparse(item["datetime"])
    start = start.astimezone(tz) if start.tzinfo else start.replace(tzinfo=tz)

    venue = item.get("venue", {})
    location = ", ".join(filter(None, [venue.get("name"), venue.get("city"), venue.get("region")]))
    lineup = item.get("lineup") or []
    title = item.get("title") or (lineup[0] if lineup else "Untitled event")

    offers = item.get("offers") or []
    ticket_url = offers[0]["url"] if offers else item.get("url", "")

    return Event(
        title=title,
        start=start,
        source="bandsintown",
        url=ticket_url,
        location=location,
    )


# ---------------------------------------------------------------------------
# Public pages with schema.org JSON-LD Event metadata
# ---------------------------------------------------------------------------
def fetch_public_pages(settings: Settings) -> list[Event]:
    if not settings.public_urls:
        return []

    start, end = _lookahead_window(settings)
    events: list[Event] = []

    for url in settings.public_urls:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            for entry in _flatten_ld_json(payload):
                if entry.get("@type") != "Event":
                    continue
                event = _jsonld_event(entry, url, settings)
                if event and start <= event.start <= end:
                    events.append(event)

    return events


def _flatten_ld_json(payload):
    if isinstance(payload, list):
        for item in payload:
            yield from _flatten_ld_json(item)
    elif isinstance(payload, dict):
        if "@graph" in payload:
            yield from _flatten_ld_json(payload["@graph"])
        else:
            yield payload


def _jsonld_event(entry: dict, source_url: str, settings: Settings) -> Event | None:
    start_raw = entry.get("startDate")
    if not start_raw:
        return None

    tz = ZoneInfo(settings.default_timezone)
    start = date_parser.isoparse(start_raw)
    start = start.astimezone(tz) if start.tzinfo else start.replace(tzinfo=tz)

    location = entry.get("location", {})
    location_name = location.get("name", "") if isinstance(location, dict) else str(location)

    return Event(
        title=entry.get("name", "Untitled event"),
        start=start,
        source="public_page",
        url=entry.get("url") or source_url,
        location=location_name,
        description=entry.get("description", ""),
    )
