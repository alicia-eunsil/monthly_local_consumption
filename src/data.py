from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


GGDATA_BASE_URL = "https://openapi.gg.go.kr"
MIDDLE_CATEGORY_SERVICE = "TB25BPTGGCARDCATMSALEM"
PUBLICATION_USE_SERVICE = "RegionMnyPublctUse"
MAX_PAGE_SIZE = 1000
MAX_WORKERS = 8
REQUEST_TIMEOUT_SECONDS = 120
REQUEST_RETRIES = 3


COLUMN_ALIASES: dict[str, list[str]] = {
    "period": [
        "기준년월",
        "기준年月",
        "STD_YM",
        "BASE_YM",
        "YM",
        "period",
    ],
    "emd_code": [
        "읍면동코드",
        "행정동코드",
        "ADMDONG_CD",
        "EMD_CD",
        "ADMI_CD",
        "emd_code",
        "region_code",
    ],
    "region_name": [
        "읍면동명",
        "행정동명",
        "지역명",
        "시군구명",
        "SIGUN_NM",
        "region_name",
    ],
    "industry_code": [
        "중분류업종코드",
        "업종중분류코드",
        "업종코드",
        "MDCLASS_INDUTYPE_CD",
        "INDUTYPE_MLSFC_CODE",
        "industry_code",
    ],
    "industry_name": [
        "중분류업종명",
        "업종중분류명",
        "업종명",
        "MDCLASS_INDUTYPE_NM",
        "INDUTYPE_MLSFC_NM",
        "industry_name",
    ],
    "sales_amount": [
        "매출금액",
        "매출액",
        "지역화폐매출금액",
        "SALES_AMT",
        "SALE_AMT",
        "sales_amount",
    ],
    "sales_rank": [
        "매출금액순위",
        "매출순위",
        "RANK",
        "sales_rank",
    ],
    "sales_share": [
        "매출비율",
        "매출금액비율",
        "비율",
        "SHARE",
        "sales_share",
    ],
    "mom_abs": [
        "전월증감값",
        "전월대비증감값",
        "전월대비증감액",
        "MOM_DIFF",
        "mom_abs",
    ],
    "mom_pct": [
        "전월증감률",
        "전월대비증감률",
        "MOM_RATE",
        "mom_pct",
    ],
    "yoy_abs": [
        "전년동월증감값",
        "전년동월대비증감값",
        "전년동월대비증감액",
        "YOY_DIFF",
        "yoy_abs",
    ],
    "yoy_pct": [
        "전년동월증감률",
        "전년동월대비증감률",
        "YOY_RATE",
        "yoy_pct",
    ],
}


@dataclass(frozen=True)
class LoadResult:
    frame: pd.DataFrame
    source_name: str
    missing_required: list[str]
    original_columns: list[str]


ProgressCallback = Callable[[str, int, int], None]


def fetch_ggdata_middle_category_records(
    app_key: str,
    page_size: int = MAX_PAGE_SIZE,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    return fetch_ggdata_records(
        MIDDLE_CATEGORY_SERVICE,
        app_key,
        page_size=page_size,
        progress_callback=progress_callback,
    )


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


def normalize_consumption_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    source = df.copy()
    source.columns = [str(col).strip() for col in source.columns]

    mapped: dict[str, str] = {}
    compact_cols = {_compact(col): col for col in source.columns}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            hit = compact_cols.get(_compact(alias))
            if hit:
                mapped[target] = hit
                break

    required = ["period", "emd_code", "industry_name", "sales_amount"]
    missing_required = [name for name in required if name not in mapped]

    out = pd.DataFrame()
    for target, original in mapped.items():
        out[target] = source[original]

    if "region_name" not in out.columns and "emd_code" in out.columns:
        out["region_name"] = out["emd_code"].astype(str)
    if "industry_code" not in out.columns:
        out["industry_code"] = ""

    if "period" in out.columns:
        out["period_key"] = out["period"].map(_period_key)
        out["period_date"] = pd.to_datetime(out["period_key"] + "01", format="%Y%m%d", errors="coerce")
    else:
        out["period_key"] = ""
        out["period_date"] = pd.NaT

    text_cols = ["emd_code", "region_name", "industry_code", "industry_name"]
    for col in text_cols:
        if col in out.columns:
            out[col] = out[col].fillna("").astype(str).str.strip()

    numeric_cols = ["sales_amount", "sales_rank", "sales_share", "mom_abs", "mom_pct", "yoy_abs", "yoy_pct"]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = out[col].map(_to_float)

    out = out.dropna(subset=["period_date"])
    if "sales_amount" in out.columns:
        out = out.dropna(subset=["sales_amount"])
        out = out[out["sales_amount"] >= 0]

    return out, missing_required


def build_load_result(df: pd.DataFrame, source_name: str) -> LoadResult:
    normalized, missing = normalize_consumption_frame(df)
    return LoadResult(
        frame=normalized,
        source_name=source_name,
        missing_required=missing,
        original_columns=[str(col) for col in df.columns],
    )


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


def aggregate_by(
    df: pd.DataFrame,
    group_cols: Iterable[str],
    value_col: str = "sales_amount",
) -> pd.DataFrame:
    grouped = (
        df.groupby(list(group_cols), dropna=False, as_index=False)[value_col]
        .sum()
        .sort_values(value_col, ascending=False)
    )
    return grouped


def period_change(
    df: pd.DataFrame,
    group_cols: Iterable[str],
    current_period: str,
    lag_months: int,
) -> pd.DataFrame:
    current_date = pd.to_datetime(current_period + "01", format="%Y%m%d", errors="coerce")
    if pd.isna(current_date):
        return pd.DataFrame()
    previous_key = (current_date - pd.DateOffset(months=lag_months)).strftime("%Y%m")

    keys = list(group_cols)
    cur = (
        df[df["period_key"] == current_period]
        .groupby(keys, as_index=False)["sales_amount"]
        .sum()
        .rename(columns={"sales_amount": "current_sales"})
    )
    prev = (
        df[df["period_key"] == previous_key]
        .groupby(keys, as_index=False)["sales_amount"]
        .sum()
        .rename(columns={"sales_amount": "previous_sales"})
    )
    merged = cur.merge(prev, on=keys, how="left")
    merged["change_abs"] = merged["current_sales"] - merged["previous_sales"]
    merged["change_pct"] = np.where(
        merged["previous_sales"].fillna(0) != 0,
        merged["change_abs"] / merged["previous_sales"] * 100,
        np.nan,
    )
    return merged.sort_values("change_abs", ascending=False)


def _compact(value: object) -> str:
    return "".join(str(value or "").strip().lower().split())


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
