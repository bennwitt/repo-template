"""Shared release-age policy for reporting, validation and installation."""

from datetime import timedelta

COOLDOWN = timedelta(days=1)
FRESHNESS = timedelta(hours=24)
