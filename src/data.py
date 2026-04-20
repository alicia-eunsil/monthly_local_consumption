from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


GGDATA_BASE_URL = "https://openapi.gg.go.kr"
PUBLICATION_USE_SERVICE = "RegionMnyPublctUse"
MAX_PAGE_SIZE = 1000
MAX_WORKERS = 8
REQUEST_TIMEOUT_SECONDS = 120
REQUEST_RETRIES = 3

ProgressCallback = Callable[[str, int, int], None]


def fetch_ggdata_publication_use_records(
    app_key: str,
    page_size: int = MAX_PAGE_SIZE,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    return fetch_ggdata_records(
        PUBLICATION_USE_SERVICE,
        app_key,
        page_size=page_size,
        progress_callback=progress_callback,
    )


def fetch_ggdata_records(
    service: str,
    app_key: str,
    page_size: int = MAX_PAGE_SIZE,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    if not app_key:
        raise RuntimeError("APP_KEY가 설정되어 있지 않습니다.")

    safe_page_size = min(max(int(page_size), 1), MAX_PAGE_SIZE)
    first_payload = _fetch_ggdata_page(service, app_key, 1, safe_page_size)
    _raise_result_error(first_payload)
    total_count = _extract_total_count(first_payload, service)
    rows = _extract_rows(first_payload, service)

    if total_count <= len(rows):
        if progress_callback:
            progress_callback(service, 1, 1)
        return rows

    total_pages = int(np.ceil(total_count / safe_page_size))
    if progress_callback:
        progress_callback(service, 1, total_pages)

    page_rows: dict[int, list[dict]] = {1: rows}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_ggdata_page, service, app_key, page_index, safe_page_size): page_index
            for page_index in range(2, total_pages + 1)
        }
        for future in as_completed(futures):
            page_index = futures[future]
            payload = future.result()
            _raise_result_error(payload)
            page_rows[page_index] = _extract_rows(payload, service)
            if progress_callback:
                progress_callback(service, len(page_rows), total_pages)

    rows = []
    for page_index in range(1, total_pages + 1):
        rows.extend(page_rows.get(page_index, []))
    return rows


def normalize_publication_use_frame(df: pd.DataFrame) -> pd.DataFrame:
    source = df.copy()
    source.columns = [str(col).strip() for col in source.columns]
    required = ["STD_YM", "SIGUN_NM", "CARD_PUBLCT_CNT", "CARD_CHRGNG_AMT", "CARD_USE_AMT"]
    missing = [col for col in required if col not in source.columns]
    if missing:
        raise RuntimeError("발행 및 이용 현황 필수 컬럼을 찾지 못했습니다: " + ", ".join(missing))

    out = pd.DataFrame(
        {
            "period_key": source["STD_YM"].map(_period_key),
            "sigun_name": source["SIGUN_NM"].fillna("").astype(str).str.strip(),
            "new_member_count": source["CARD_PUBLCT_CNT"].map(_to_float),
            "charge_amount_million": source["CARD_CHRGNG_AMT"].map(_to_float),
            "use_amount_million": source["CARD_USE_AMT"].map(_to_float),
            "sigun_code": source["SIGUN_CD"].fillna("").astype(str).str.strip() if "SIGUN_CD" in source.columns else "",
        }
    )
    out["period_date"] = pd.to_datetime(out["period_key"] + "01", format="%Y%m%d", errors="coerce")
    out = out.dropna(subset=["period_date"])
    return out


def _fetch_ggdata_page(service: str, app_key: str, page_index: int, page_size: int) -> dict:
    params = {
        "Key": app_key,
        "Type": "json",
        "pIndex": page_index,
        "pSize": page_size,
    }
    url = f"{GGDATA_BASE_URL}/{service}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "monthly-local-consumption/1.0"})
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, URLError) as exc:
            last_error = exc
            if attempt == REQUEST_RETRIES:
                break
        except json.JSONDecodeError as exc:
            raise RuntimeError("경기데이터드림 Open API 응답을 JSON으로 해석할 수 없습니다.") from exc
    raise RuntimeError(
        f"경기데이터드림 Open API 호출에 실패했습니다. "
        f"service={service}, page={page_index}, size={page_size}, error={last_error}"
    )


def _extract_total_count(payload: dict, service: str) -> int:
    sections = payload.get(service, [])
    for section in sections:
        head = section.get("head") if isinstance(section, dict) else None
        if not head:
            continue
        for item in head:
            if "list_total_count" in item:
                return int(item.get("list_total_count") or 0)
            result = item.get("RESULT")
            if result and result.get("CODE") not in {"INFO-000", "INFO-200"}:
                raise RuntimeError(result.get("MESSAGE", "Open API 오류가 발생했습니다."))
    return 0


def _raise_result_error(payload: dict) -> None:
    top_result = payload.get("RESULT")
    if isinstance(top_result, dict):
        code = str(top_result.get("CODE", ""))
        if code and code not in {"INFO-000", "INFO-200"}:
            raise RuntimeError(top_result.get("MESSAGE", "Open API 오류가 발생했습니다."))


def _extract_rows(payload: dict, service: str) -> list[dict]:
    sections = payload.get(service, [])
    for section in sections:
        if isinstance(section, dict) and "row" in section:
            return list(section.get("row") or [])
    return []


def _period_key(value: object) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 6:
        return digits[:6]
    return ""


def _to_float(value: object) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "nan", "None", "null"}:
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan
