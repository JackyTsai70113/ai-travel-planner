"""Research source adapters and the candidate-store boundary."""

from .adapters import AdapterFailure, FixtureCommunityRestaurantAdapter, FixtureOfficialPoiAdapter, SourceAdapter, SourceQuery, collect_from_adapters
from .candidate_store import CandidateRecord, CandidateState, CandidateStore, StaleCandidateError
from .providers import (
    GooglePlacesAdapter, JsonHttpClient, ProviderConfigurationError,
    ProviderRequestError, ResearchEvidence, UrllibJsonHttpClient,
    YouTubeEvidenceAdapter, authority_rank, prioritize_by_authority,
)

__all__ = [
    "AdapterFailure",
    "CandidateRecord",
    "CandidateState",
    "CandidateStore",
    "FixtureCommunityRestaurantAdapter",
    "FixtureOfficialPoiAdapter",
    "GooglePlacesAdapter",
    "JsonHttpClient",
    "ProviderConfigurationError",
    "ProviderRequestError",
    "ResearchEvidence",
    "SourceAdapter",
    "SourceQuery",
    "StaleCandidateError",
    "UrllibJsonHttpClient",
    "YouTubeEvidenceAdapter",
    "authority_rank",
    "collect_from_adapters",
    "prioritize_by_authority",
]
