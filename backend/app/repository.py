# Learner guidance: prepare data/raw/raw_opportunities.csv using data/README.md.
# Choose your own storage and internal schema. The bridge is an optional CSV/JSON
# helper. Map your storage into the public API contract; rename/split this module freely.
from __future__ import annotations

from typing import Any

from .infrastructure.data_package import DatasetLoader


class OpportunityRepository:
    """TRAINEE TODO: map prepared records into application domain objects."""

    def __init__(self, bridge: DatasetLoader) -> None:
        self.bridge = bridge

    def is_ready(self) -> bool:
        """TODO: check your actual storage is accessible and usable; return a bool.

        Do not require the optional JSON example when using another store.
        """
        raise NotImplementedError("Implement readiness for your chosen storage")

    def search(self, criteria: Any):
        """TODO: criteria -> candidate records with source evidence from your store.

        Read exported data or your database, not notebook cell outputs.
        Internal candidate types and search technology are your choice.
        """
        raise NotImplementedError(
            "TODO(FURSAH-LEARNER): implement opportunity repository search"
        )

    def get_details(self, opportunity_id: str):
        """TODO: ID -> OpportunityDetailsResponse, or None if the ID is absent.

        Map a real stored record to the public contract, retaining its source IDs.
        """
        raise NotImplementedError(
            "TODO(FURSAH-LEARNER): map one prepared record into OpportunityDetailsResponse"
        )
