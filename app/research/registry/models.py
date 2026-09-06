from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class StrategyStatus(str, Enum):
    BASELINE = "BASELINE"
    RESEARCH = "RESEARCH"
    TESTING = "TESTING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class StrategyRecord:
    name: str
    status: StrategyStatus
    source_path: str
    version: str = "v1"
    locked: bool = False
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    last_tested_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyRecord":
        payload = dict(data)
        payload["status"] = StrategyStatus(payload["status"])
        return cls(**payload)
