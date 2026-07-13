"""Runtime configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    operations_store: Path
    research_root: Path
    operations_max_age_minutes: float
    operations_flood_max_age_minutes: float
    wra_base_url: str
    wra_api_url: str
    wra_open_data_api_url: str
    wra_api_key: str
    cwa_api_key: str
    cwa_rest_api_url: str
    cwa_open_data_file_api_url: str
    cwa_history_api_url: str
    cwa_history_data_api_url: str


def get_settings() -> Settings:
    return Settings(
        operations_store=Path(
            os.getenv(
                "MINXIONGHYDROCAST_OPERATIONS_STORE",
                "data/processed/operations",
            )
        ),
        research_root=Path(
            os.getenv(
                "MINXIONGHYDROCAST_RESEARCH_ROOT",
                "~/.local/share/minxiong-hydrocast-research",
            )
        ).expanduser(),
        operations_max_age_minutes=float(os.getenv("MINXIONGHYDROCAST_MAX_AGE_MINUTES", "30")),
        operations_flood_max_age_minutes=float(
            os.getenv("MINXIONGHYDROCAST_FLOOD_MAX_AGE_MINUTES", "90")
        ),
        wra_base_url=os.getenv("WRA_BASE_URL", "https://fhy.wra.gov.tw/fhyv2"),
        wra_api_url=os.getenv("WRA_API_URL", "https://fhy.wra.gov.tw/OpenApiv3"),
        wra_open_data_api_url=os.getenv(
            "WRA_OPEN_DATA_API_URL",
            "https://opendata.wra.gov.tw/api/v2",
        ),
        wra_api_key=os.getenv("WRA_API_KEY", ""),
        cwa_api_key=os.getenv("CWA_API_KEY", ""),
        cwa_rest_api_url=os.getenv(
            "CWA_REST_API_URL",
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore",
        ),
        cwa_open_data_file_api_url=os.getenv(
            "CWA_OPEN_DATA_FILE_API_URL",
            "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi",
        ),
        cwa_history_api_url=os.getenv(
            "CWA_HISTORY_API_URL",
            "https://opendata.cwa.gov.tw/historyapi/v1/getMetadata",
        ),
        cwa_history_data_api_url=os.getenv(
            "CWA_HISTORY_DATA_API_URL",
            "https://opendata.cwa.gov.tw/historyapi/v1/getData",
        ),
    )
