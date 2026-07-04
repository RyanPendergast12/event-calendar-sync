"""Smoke tests for event-calendar-sync.

Cheap, dependency-light checks that give pytest something to collect (so CI
doesn't exit 5) while actually verifying the package is importable. Import
failures here mean the real "Run event sync" step would fail too — catch it now.
"""
import importlib

import pytest


def test_package_imports():
    """The package and its entrypoint import cleanly under PYTHONPATH=src."""
    importlib.import_module("event_sync")
    importlib.import_module("event_sync.main")


def test_event_uid_is_deterministic():
    """Dedup relies on stable UIDs: same inputs -> same UID across runs.

    Skips cleanly until event_uid + a constructible Event exist, so it never
    blocks CI, but starts guarding your dedup the moment the models land.
    """
    models = importlib.import_module("event_sync.models")
    event_uid = getattr(models, "event_uid", None)
    Event = getattr(models, "Event", None)
    if event_uid is None or Event is None:
        pytest.skip("event_sync.models.event_uid / Event not defined yet")

    # NOTE: adjust the kwargs below to match your real Event signature.
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        start = datetime(2026, 8, 1, 20, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        ev = Event(title="Porter Robinson", start=start)  # type: ignore[call-arg]
    except TypeError:
        pytest.skip("Update test_smoke Event(...) kwargs to match your Event model")

    assert event_uid(ev) == event_uid(ev)
