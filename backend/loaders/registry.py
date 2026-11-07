"""Maps DATASET_MODE -> concrete BaseDataLoader."""

from __future__ import annotations

from config import TARGET_BBOX
from loaders.base import BaseDataLoader
from loaders.housing_loader import HousingTransactionLoader
from loaders.osm_loader import OSMAmenityLoader
from loaders.pokemon_loader import PokemonTelemetryLoader

LOADERS = {
    "pokemon": lambda: PokemonTelemetryLoader(),
    "osm": lambda: OSMAmenityLoader(TARGET_BBOX),
    "housing": lambda: HousingTransactionLoader(),
}


def get_loader(mode: str) -> BaseDataLoader:
    try:
        return LOADERS[mode]()
    except KeyError as exc:
        raise ValueError(f"No loader registered for DATASET_MODE={mode!r}") from exc
