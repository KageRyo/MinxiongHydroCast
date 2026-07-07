"""Runtime configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    log_level: str
    wra_base_url: str
    cwa_codis_url: str
    cwa_open_data_file_api_url: str
    cwa_history_api_url: str
    ncdr_open_api_url: str


def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.getenv("FLOODCASTTW_DATA_DIR", "data")),
        log_level=os.getenv("FLOODCASTTW_LOG_LEVEL", "INFO"),
        wra_base_url=os.getenv("WRA_BASE_URL", "https://fhy.wra.gov.tw/fhyv2"),
        cwa_codis_url=os.getenv("CWA_CODIS_URL", "https://codis.cwa.gov.tw/StationData"),
        cwa_open_data_file_api_url=os.getenv(
            "CWA_OPEN_DATA_FILE_API_URL",
            "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi",
        ),
        cwa_history_api_url=os.getenv(
            "CWA_HISTORY_API_URL",
            "https://opendata.cwa.gov.tw/historyapi/v1/getMetadata",
        ),
        ncdr_open_api_url=os.getenv("NCDR_OPEN_API_URL", "https://watch.ncdr.nat.gov.tw/watch"),
    )
