"""Research source adapters and the candidate-store boundary."""

from .adapters import AdapterFailure, FixtureCommunityRestaurantAdapter, FixtureOfficialPoiAdapter, SourceAdapter, SourceQuery, collect_from_adapters
from .candidate_store import CandidateRecord, CandidateState, CandidateStore, StaleCandidateError

__all__ = [
    "AdapterFailure",
    "CandidateRecord",
    "CandidateState",
    "CandidateStore",
    "FixtureCommunityRestaurantAdapter",
    "FixtureOfficialPoiAdapter",
    "SourceAdapter",
    "SourceQuery",
    "StaleCandidateError",
    "collect_from_adapters",
]
