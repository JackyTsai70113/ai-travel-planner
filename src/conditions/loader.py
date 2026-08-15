"""JSON fixture loader with strict temporal validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import ConditionKind, ConditionRecord, ConditionRequirement, ConditionSnapshot, ConditionStatus, EligibilityWindow, EvidenceClass, SourceProvenance


def load_condition_snapshot(source: str | Path | Mapping[str, Any]) -> ConditionSnapshot:
    payload = source if isinstance(source, Mapping) else json.loads(Path(source).read_text(encoding="utf-8"))
    records = []
    for item in payload.get("records", []):
        windows = tuple(EligibilityWindow(_dt(w["starts_at"]), _dt(w["ends_at"])) for w in item.get("eligibility_windows", []))
        provenance = item.get("provenance")
        if provenance is None:
            # Compatibility for recorded fixtures produced before structured provenance.
            provenance = {
                "provider": item["source"], "source_url": f"urn:provider:{item['source']}",
                "retrieved_at": item["retrieved_at"], "evidence_class": item["evidence_class"],
                "source_type": "legacy-recorded",
            }
        records.append(ConditionRecord(
            id=item["id"], kind=ConditionKind(item["kind"]), place_ids=tuple(item["place_ids"]),
            status=ConditionStatus(item["status"]), provenance=SourceProvenance(
                provider=provenance["provider"], source_url=provenance["source_url"],
                retrieved_at=_dt(provenance["retrieved_at"]), evidence_class=EvidenceClass(provenance["evidence_class"]),
                source_type=provenance["source_type"],
            ), valid_from=_dt(item["valid_from"]),
            valid_until=_dt(item["valid_until"]), forecast_until=_dt(item["forecast_until"]) if item.get("forecast_until") else None,
            eligibility_windows=windows, soft_penalty=float(item.get("soft_penalty", 0)), details=item.get("details", {}),
        ))
    requirements = tuple(ConditionRequirement(item["place_id"], ConditionKind(item["kind"])) for item in payload.get("requirements", []))
    return ConditionSnapshot(tuple(records), requirements)


def _dt(value: str):
    from datetime import datetime
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"condition timestamp must be timezone-aware: {value}")
    return parsed
