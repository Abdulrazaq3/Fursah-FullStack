from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .errors import DataAccessError


RAW_COLUMNS = ["source_id", "source_type", "source_name", "published_at", "content"]


@dataclass(frozen=True)
class PackageInspection:
    directory_exists: bool
    raw_data_valid: bool
    prepared_data_valid: bool
    details: dict[str, str]

    @property
    def ready(self) -> bool:
        return all(self.as_checks().values())

    def as_checks(self) -> dict[str, bool]:
        return {
            "data_directory": self.directory_exists,
            "raw_data": self.raw_data_valid,
            "prepared_data": self.prepared_data_valid,
        }


class DatasetLoader:
    """Read physical files; extraction and domain mapping remain learner tasks.

    Optional example prepared format: a nonempty JSON array of objects at
    prepared/opportunities.json. Other stores need not use this helper. Its inspection is a file diagnostic,
    not the application readiness check. No fallback dataset is provided.
    """

    def __init__(self, settings: Settings) -> None:
        self.data_dir = settings.data_dir

    def inspect(self) -> PackageInspection:
        raw_valid = prepared_valid = False
        details: dict[str, str] = {}
        try:
            self.load_raw_opportunities()
            raw_valid = True
        except DataAccessError as exc:
            details["raw_data"] = str(exc)
        try:
            self.load_prepared_opportunities()
            prepared_valid = True
        except DataAccessError as exc:
            details["prepared_data"] = str(exc)
        return PackageInspection(self.data_dir.is_dir(), raw_valid, prepared_valid, details)

    def load_raw_opportunities(self) -> list[dict[str, str]]:
        """Return announcements as text, without solving the preparation exercise."""
        path = self.data_dir / "raw" / "raw_opportunities.csv"
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames != RAW_COLUMNS:
                    raise DataAccessError("Raw CSV columns do not match data/README.md.")
                records = list(reader)
        except (OSError, UnicodeError, csv.Error) as exc:
            raise DataAccessError("Raw announcements could not be read; check data/README.md.") from exc
        if not records or any(
            set(row) != set(RAW_COLUMNS)
            or any(not isinstance(value, str) or not value.strip() for value in row.values())
            for row in records
        ):
            raise DataAccessError("Raw CSV contains empty or malformed records.")
        if len({row["source_id"] for row in records}) != len(records):
            raise DataAccessError("Raw CSV contains duplicate source IDs.")
        return records

    def load_prepared_opportunities(self) -> list[dict[str, Any]]:
        """Check only file structure; learners validate facts and map API fields."""
        path = self.data_dir / "prepared" / "opportunities.json"
        if not path.is_file():
            raise DataAccessError("Prepared data is missing. Create data/prepared/opportunities.json following data/README.md.")
        try:
            records = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise DataAccessError(
                "Prepared data is unreadable or contains invalid JSON. Follow data/README.md "
                "and create data/prepared/opportunities.json."
            ) from exc
        if not isinstance(records, list) or not records or not all(
            isinstance(record, dict) and record for record in records
        ):
            raise DataAccessError("Prepared opportunities.json must be a nonempty array of objects.")
        return records
