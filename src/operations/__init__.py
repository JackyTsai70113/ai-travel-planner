"""Derived, mobile-oriented operational views of a Canonical Trip.

This module deliberately does not select, order, or validate itinerary items.
All place and daily-route references originate in the supplied Canonical Trip;
optional operational evidence merely annotates those references.
"""

from .handbook import build_handbook

__all__ = ["build_handbook"]
