"""Replaceable adapters that return canonical Trip V1 candidate payloads.

Adapters are deliberately read-only: they never receive a Trip document and cannot
write ``days``.  Provider responses are normalized before crossing this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class SourceQuery:
    """A provider-neutral research request."""

    destination: str
    categories: tuple[str, ...]


@dataclass(frozen=True)
class AdapterFailure:
    """A captured failure; one provider must not discard other research results."""

    adapter: str
    message: str


class SourceAdapter(ABC):
    """Normalize one provider into ``{candidate_sets collection, candidate}`` records."""

    name: str

    @abstractmethod
    def fetch(self, query: SourceQuery) -> Iterable[tuple[str, dict[str, Any]]]:
        """Return canonical candidates without provider-specific fields.

        Each tuple's first value is one Trip V1 ``candidate_sets`` collection.
        Each candidate must contain canonical ``provenance`` with ``retrieved_at``.
        """


def collect_from_adapters(
    adapters: Iterable[SourceAdapter], query: SourceQuery
) -> tuple[list[tuple[str, dict[str, Any]]], list[AdapterFailure]]:
    """Collect independent adapter output, isolating expected provider failures."""

    candidates: list[tuple[str, dict[str, Any]]] = []
    failures: list[AdapterFailure] = []
    for adapter in adapters:
        try:
            candidates.extend(adapter.fetch(query))
        except Exception as exc:  # provider/network failures are non-fatal per adapter
            failures.append(AdapterFailure(adapter=adapter.name, message=str(exc)))
    return candidates, failures


class FixtureOfficialPoiAdapter(SourceAdapter):
    """Deterministic official-tourism adapter fixture for contract tests."""

    name = "fixture-official-tourism"

    def __init__(self, retrieved_at: datetime | None = None) -> None:
        self.retrieved_at = retrieved_at or datetime.now(timezone.utc)

    def fetch(self, query: SourceQuery) -> Iterable[tuple[str, dict[str, Any]]]:
        if "pois" not in query.categories:
            return []
        provenance = {
            "source_type": "official",
            "provider": "Fukuoka City Official Tourism Guide fixture",
            "source_url": "https://gofukuoka.jp/",
            "retrieved_at": self.retrieved_at.isoformat(),
            "confidence": 0.95,
            "status": "confirmed",
        }
        return [("places", {
            "id": "ohori-park",
            "name": "大濠公園 / Ohori Park",
            "kind": "poi",
            "address": "福岡県福岡市中央区大濠公園",
            "provenance": provenance,
        })]


class FixtureCommunityRestaurantAdapter(SourceAdapter):
    """Deterministic community-source fixture; its facts remain reported, not official."""

    name = "fixture-community-restaurant"

    def __init__(self, retrieved_at: datetime | None = None) -> None:
        self.retrieved_at = retrieved_at or datetime.now(timezone.utc)

    def fetch(self, query: SourceQuery) -> Iterable[tuple[str, dict[str, Any]]]:
        if "restaurants" not in query.categories:
            return []
        provenance = {
            "source_type": "community",
            "provider": "Fukuoka family travel community fixture",
            "source_url": "https://example.test/fukuoka-family-ramen",
            "retrieved_at": self.retrieved_at.isoformat(),
            "confidence": 0.55,
            "status": "reported",
            "note": "Queue and child-friendly signals are community reports.",
        }
        return [("restaurants", {
            "place": {
                "id": "fixture-ramen",
                "name": "フィクスチャーラーメン / Fixture Ramen",
                "kind": "restaurant",
                "address": "福岡県福岡市中央区",
                "provenance": provenance,
            },
            "price_range": "¥1,000–¥2,000",
            "reservation_required": False,
            "wait_risk": "high",
            "child_friendly": True,
            "provenance": provenance,
        })]
