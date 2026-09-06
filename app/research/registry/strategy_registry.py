from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Optional

from app.research.registry.models import StrategyRecord, StrategyStatus


class RegistryError(RuntimeError):
    pass


class StrategyRegistry:
    """Small JSON-backed strategy registry.

    The registry stores research metadata only. It has no broker dependency and
    cannot execute trades.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path = "research/registry.json") -> None:
        self.path = Path(path)

    def _load(self) -> List[StrategyRecord]:
        if not self.path.exists():
            return []

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        rows = payload.get("strategies", [])
        return [StrategyRecord.from_dict(row) for row in rows]

    def _save(self, records: Iterable[StrategyRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "strategies": [record.to_dict() for record in records],
        }
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def list(self) -> List[StrategyRecord]:
        return self._load()

    def get(self, name: str) -> Optional[StrategyRecord]:
        return next((item for item in self._load() if item.name == name), None)

    def require(self, name: str) -> StrategyRecord:
        record = self.get(name)
        if record is None:
            raise RegistryError(f"Strategy is not registered: {name}")
        return record

    def register(self, record: StrategyRecord, *, replace_existing: bool = False) -> None:
        records = self._load()
        existing_index = next(
            (index for index, item in enumerate(records) if item.name == record.name),
            None,
        )

        if existing_index is None:
            records.append(record)
        else:
            existing = records[existing_index]
            if existing.locked:
                raise RegistryError(
                    f"Locked strategy cannot be replaced: {existing.name}"
                )
            if not replace_existing:
                raise RegistryError(f"Strategy already exists: {record.name}")
            records[existing_index] = record

        self._save(records)

    def update_status(
        self,
        name: str,
        status: StrategyStatus,
        *,
        last_tested_at: str | None = None,
    ) -> StrategyRecord:
        records = self._load()
        for index, record in enumerate(records):
            if record.name != name:
                continue

            if record.locked and record.status == StrategyStatus.BASELINE:
                raise RegistryError(
                    f"Baseline status is protected and cannot change: {name}"
                )

            updated = replace(
                record,
                status=status,
                last_tested_at=last_tested_at or record.last_tested_at,
            )
            records[index] = updated
            self._save(records)
            return updated

        raise RegistryError(f"Strategy is not registered: {name}")
