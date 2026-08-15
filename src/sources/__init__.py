"""Research source adapters and the candidate-store boundary."""

from .adapters import AdapterFailure, FixtureCommunityRestaurantAdapter, FixtureOfficialPoiAdapter, SourceAdapter, SourceQuery, collect_from_adapters
from .candidate_store import CandidateRecord, CandidateState, CandidateStore, StaleCandidateError
from .providers import (
    GooglePlacesAdapter, HotPepperGourmetAdapter, OfficialRestaurantFeedAdapter,
    JsonHttpClient, ProviderConfigurationError,
    ProviderRequestError, ResearchEvidence, UrllibJsonHttpClient,
    YouTubeEvidenceAdapter, authority_rank, prioritize_by_authority,
)
from .travel import (
    AmadeusClient,
    AmadeusFlightAdapter,
    AmadeusHotelAdapter,
    FlightSearchQuery,
    HotelSearchQuery,
    Occupancy,
    ProviderError,
    SearchResult,
    collect_travel_searches,
)

__all__ = [
    "AdapterFailure",
    "CandidateRecord",
    "CandidateState",
    "CandidateStore",
    "FixtureCommunityRestaurantAdapter",
    "FixtureOfficialPoiAdapter",
    "GooglePlacesAdapter",
    "HotPepperGourmetAdapter",
    "OfficialRestaurantFeedAdapter",
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
    "AmadeusClient",
    "AmadeusFlightAdapter",
    "AmadeusHotelAdapter",
    "FlightSearchQuery",
    "HotelSearchQuery",
    "Occupancy",
    "ProviderError",
    "SearchResult",
    "collect_travel_searches",
]
