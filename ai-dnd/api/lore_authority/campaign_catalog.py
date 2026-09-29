"""Data-driven campaign start options backed by installed region packs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,127}$")
_STARTABLE_COVERAGE = {"VERIFIED", "VERIFIED_PARTIAL"}


def _text(value: Any, label: str, limit: int = 160) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Campaign start catalog {label} is invalid.")
    return value.strip()


def _id(value: Any, label: str) -> str:
    parsed = _text(value, label, 128)
    if not _ID_PATTERN.fullmatch(parsed):
        raise ValueError(f"Campaign start catalog {label} is invalid.")
    return parsed


@dataclass(frozen=True)
class StartingLocationOption:
    entity_id: str
    name: str


@dataclass(frozen=True)
class CampaignStartPack:
    region_pack_id: str
    setting_id: str
    setting_name: str
    world_id: str
    epoch_id: str
    region_id: str
    region_name: str
    coverage_status: str
    starting_locations: tuple[StartingLocationOption, ...]


class CampaignStartCatalog:
    """Immutable list of reviewed packs that can bind a new campaign."""

    def __init__(self, packs: Sequence[CampaignStartPack]) -> None:
        pack_ids: set[str] = set()
        setting_names: dict[str, str] = {}
        normalized: list[CampaignStartPack] = []
        for pack in packs:
            if pack.region_pack_id in pack_ids:
                raise ValueError("Campaign start catalog contains duplicate pack IDs.")
            pack_ids.add(pack.region_pack_id)
            if pack.coverage_status not in _STARTABLE_COVERAGE:
                raise ValueError("Unreviewed or test-only packs cannot be start options.")
            setting_name = setting_names.setdefault(pack.setting_id, pack.setting_name)
            if setting_name != pack.setting_name:
                raise ValueError("A setting ID cannot have conflicting display names.")
            location_ids = [item.entity_id for item in pack.starting_locations]
            if not pack.starting_locations or len(set(location_ids)) != len(location_ids):
                raise ValueError("Each campaign start pack needs unique start locations.")
            normalized.append(pack)
        self._packs = tuple(normalized)
        self._by_pack_id = {item.region_pack_id: item for item in self._packs}

    @classmethod
    def from_mapping(cls, value: Any) -> "CampaignStartCatalog":
        if not isinstance(value, Mapping) or set(value) != {"packs"}:
            raise ValueError("Campaign start catalog fields are invalid.")
        rows = value["packs"]
        if not isinstance(rows, list) or not rows or len(rows) > 200:
            raise ValueError("Campaign start catalog packs are invalid.")
        packs: list[CampaignStartPack] = []
        pack_fields = {
            "region_pack_id",
            "setting_id",
            "setting_name",
            "world_id",
            "epoch_id",
            "region_id",
            "region_name",
            "coverage_status",
            "starting_locations",
        }
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != pack_fields:
                raise ValueError("Campaign start catalog pack fields are invalid.")
            raw_locations = row["starting_locations"]
            if not isinstance(raw_locations, list) or len(raw_locations) > 100:
                raise ValueError("Campaign start catalog locations are invalid.")
            locations: list[StartingLocationOption] = []
            for location in raw_locations:
                if not isinstance(location, Mapping) or set(location) != {
                    "entity_id",
                    "name",
                }:
                    raise ValueError("Campaign start catalog location fields are invalid.")
                locations.append(
                    StartingLocationOption(
                        entity_id=_id(location["entity_id"], "location entity_id"),
                        name=_text(location["name"], "location name"),
                    )
                )
            packs.append(
                CampaignStartPack(
                    region_pack_id=_id(row["region_pack_id"], "region_pack_id"),
                    setting_id=_id(row["setting_id"], "setting_id"),
                    setting_name=_text(row["setting_name"], "setting_name"),
                    world_id=_id(row["world_id"], "world_id"),
                    epoch_id=_id(row["epoch_id"], "epoch_id"),
                    region_id=_id(row["region_id"], "region_id"),
                    region_name=_text(row["region_name"], "region_name"),
                    coverage_status=_text(row["coverage_status"], "coverage_status", 40),
                    starting_locations=tuple(locations),
                )
            )
        return cls(packs)

    @property
    def packs(self) -> tuple[CampaignStartPack, ...]:
        return self._packs

    def to_response(self) -> dict[str, Any]:
        settings: dict[str, dict[str, Any]] = {}
        for pack in self._packs:
            setting = settings.setdefault(
                pack.setting_id,
                {"setting_id": pack.setting_id, "name": pack.setting_name, "regions": []},
            )
            setting["regions"].append(
                {
                    "region_pack_id": pack.region_pack_id,
                    "region_id": pack.region_id,
                    "name": pack.region_name,
                    "epoch_id": pack.epoch_id,
                    "coverage_status": pack.coverage_status,
                    "starting_locations": [
                        {"entity_id": item.entity_id, "name": item.name}
                        for item in pack.starting_locations
                    ],
                }
            )
        return {
            "settings": [
                {
                    **setting,
                    "regions": sorted(
                        setting["regions"],
                        key=lambda item: (item["name"].casefold(), item["region_pack_id"]),
                    ),
                }
                for setting in sorted(
                    settings.values(), key=lambda item: item["name"].casefold()
                )
            ]
        }

    def resolve(
        self,
        *,
        setting_id: str,
        region_pack_id: str,
        region_id: str,
        starting_location_id: str,
    ) -> tuple[CampaignStartPack, StartingLocationOption]:
        pack = self._by_pack_id.get(region_pack_id)
        if pack is None or pack.setting_id != setting_id or pack.region_id != region_id:
            raise ValueError("Campaign start selection is not an installed verified option.")
        location = next(
            (
                item
                for item in pack.starting_locations
                if item.entity_id == starting_location_id
            ),
            None,
        )
        if location is None:
            raise ValueError("Campaign start selection is not an installed verified option.")
        return pack, location