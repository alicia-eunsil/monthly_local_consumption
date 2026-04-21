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
INDUSTRY_SALES_SERVICE_CANDIDATES = [
    "TB25BPTGGCARDCATLSALEM",
]
MAX_PAGE_SIZE = 1000
MAX_WORKERS = 8
REQUEST_TIMEOUT_SECONDS = 120
REQUEST_RETRIES = 3
INDUSTRY_MAX_WORKERS = 3
INDUSTRY_REQUEST_TIMEOUT_SECONDS = 90
INDUSTRY_REQUEST_RETRIES = 4
INDUSTRY_PAGE_SIZE_CANDIDATES = [500, 300, 200, 100]

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


def fetch_ggdata_industry_sales_records(
    app_key: str,
    service_override: str = "",
    page_size: int = INDUSTRY_PAGE_SIZE_CANDIDATES[0],
    progress_callback: ProgressCallback | None = None,
) -> tuple[str, list[dict]]:
    candidates: list[str] = []
    if service_override and service_override.strip():
        candidates.append(service_override.strip())
    for service in INDUSTRY_SALES_SERVICE_CANDIDATES:
        if service not in candidates:
            candidates.append(service)

    attempt_logs: list[str] = []
    last_error: Exception | None = None
    for service in candidates:
        sizes = [int(page_size)] + [s for s in INDUSTRY_PAGE_SIZE_CANDIDATES if s != int(page_size)]
        tried_timeout = False
        for size in sizes:
            try:
                rows = fetch_ggdata_records(
                    service,
                    app_key,
                    page_size=size,
                    progress_callback=progress_callback,
                    max_workers=INDUSTRY_MAX_WORKERS,
                    timeout_seconds=INDUSTRY_REQUEST_TIMEOUT_SECONDS,
                    retries=INDUSTRY_REQUEST_RETRIES,
                )
                if not rows:
                    attempt_logs.append(f"{service}(pSize={size}): 행 데이터 없음")
                    break
                columns = {str(col).strip() for col in rows[0].keys()}
                keys = {_normalize_key(col) for col in columns}
                has_period = "STDYM" in keys
                has_sales = "SALESAMT" in keys
                has_name = any(
                    key in keys
                    for key in {
                        "LGCLASSINDTYPENM",
                        "LGCLASSINDUTYPENM",
                        "LGLASSINDTYPENM",
                        "LGLASSINDUTYPENM",
                        "LCLASSINDTYPENM",
                        "LCLASSINDUTYPENM",
                        "LGCLSINDTYPENM",
                        "LGCLSINDUTYPENM",
                        "INDTYPENM",
                        "INDUTYPENM",
                        "CATLNM",
                        "CATEGORYNM",
                        "CATGNM",
                        "UPTAENM",
                    }
                )
                has_code = any(
                    key in keys
                    for key in {
                        "MDCLASSINDTYPECD",
                        "MDCLASSINDUTYPECD",
                        "LGCLASSINDTYPECD",
                        "LGCLASSINDUTYPECD",
                        "INDTYPECD",
                        "INDUTYPECD",
                        "CATLCD",
                        "CATEGORYCD",
                        "CATGCD",
                    }
                )
                if has_period and has_sales and (has_name or has_code):
                    return service, rows
                missing_tokens = []
                if not has_period:
                    missing_tokens.append("STD_YM")
                if not has_sales:
                    missing_tokens.append("SALES_AMT")
                if not (has_name or has_code):
                    missing_tokens.append("LGCLASS_INDTYPE_NM or MDCLASS_INDTYPE_CD")
                sample_cols = ", ".join(sorted(columns)[:12])
                attempt_logs.append(
                    f"{service}(pSize={size}): 필수 컬럼 누락({', '.join(missing_tokens)})"
                    + (f" / 응답 컬럼({sample_cols})" if sample_cols else "")
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                message = str(exc).strip()
                lower_message = message.lower()
                if "timed out" in lower_message or "read operation timed out" in lower_message:
                    tried_timeout = True
                    attempt_logs.append(f"{service}(pSize={size}): 타임아웃")
                    continue
                attempt_logs.append(f"{service}(pSize={size}): 호출 실패({message})")
                break
        if tried_timeout:
            attempt_logs.append(f"{service}: pSize 축소 재시도 완료")

    hint = ", ".join(candidates)
    details = " | ".join(attempt_logs[:7])
    raise RuntimeError(
        "업종별 매출 API를 찾지 못했습니다. "
        f"입력한 서비스명/후보 서비스명을 확인해 주세요. ({hint})"
        + (f" / 상세: {details}" if details else "")
    ) from last_error


def fetch_ggdata_records(
    service: str,
    app_key: str,
    page_size: int = MAX_PAGE_SIZE,
    progress_callback: ProgressCallback | None = None,
    max_workers: int = MAX_WORKERS,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    retries: int = REQUEST_RETRIES,
) -> list[dict]:
    if not app_key:
        raise RuntimeError("APP_KEY가 설정되어 있지 않습니다.")

    safe_page_size = min(max(int(page_size), 1), MAX_PAGE_SIZE)
    first_payload = _fetch_ggdata_page(
        service,
        app_key,
        1,
        safe_page_size,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
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
    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as executor:
        futures = {
            executor.submit(
                _fetch_ggdata_page,
                service,
                app_key,
                page_index,
                safe_page_size,
                timeout_seconds,
                retries,
            ): page_index
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


def normalize_industry_sales_frame(df: pd.DataFrame) -> pd.DataFrame:
    source = df.copy()
    source.columns = [str(col).strip() for col in source.columns]

    period_col = _find_column(source.columns, ["STD_YM"])
    sales_col = _find_column(source.columns, ["SALES_AMT"])
    name_col = _find_column(
        source.columns,
        [
            "LGCLASS_INDTYPE_NM",
            "LGCLASS_INDUTYPE_NM",
            "LGLASS_INDTYPE_NM",
            "LGLASS_INDUTYPE_NM",
            "LCLASS_INDTYPE_NM",
            "LCLASS_INDUTYPE_NM",
            "LGCLS_INDTYPE_NM",
            "LGCLS_INDUTYPE_NM",
            "CATL_NM",
            "CATEGORY_NM",
            "CATG_NM",
            "UPTAE_NM",
        ],
        contains=["NM"],
    )
    code_col = _find_column(
        source.columns,
        [
            "MDCLASS_INDTYPE_CD",
            "MDCLASS_INDUTYPE_CD",
            "LGCLASS_INDTYPE_CD",
            "LGCLASS_INDUTYPE_CD",
            "INDTYPE_CD",
            "INDUTYPE_CD",
            "CATL_CD",
            "CATEGORY_CD",
            "CATG_CD",
        ],
        contains=["CD"],
    )
    admong_col = _find_column(source.columns, ["ADMONG_CD", "ADMDONG_CD"])
    sales_rank_col = _find_column(source.columns, ["SALES_AMT_RKI"])
    sales_rate_col = _find_column(source.columns, ["SALES_AMT_RATE"])
    mom_abs_col = _find_column(source.columns, ["BFYM_INCNDECR_VAL"])
    mom_pct_col = _find_column(source.columns, ["BFYM_INCNDECR_RATE"])
    yoy_abs_col = _find_column(source.columns, ["FYY_SMYM_INCNDECR_VAL", "BFYY_SMMN_INCNDECR_VAL"])
    yoy_pct_col = _find_column(source.columns, ["FYY_SMYM_INCNDECR_RATE", "BFYY_SMMN_INCNDECR_RATE"])

    missing = []
    if not period_col:
        missing.append("STD_YM")
    if not sales_col:
        missing.append("SALES_AMT")
    if not (name_col or code_col):
        missing.append("LGCLASS_INDTYPE_NM or MDCLASS_INDTYPE_CD")
    if missing:
        raise RuntimeError("업종별 매출 필수 컬럼을 찾지 못했습니다: " + ", ".join(missing))

    resolved_name_col = name_col or code_col or ""
    resolved_code_col = code_col or _find_column(
        source.columns,
        ["MDCLASS_INDTYPE_CD", "MDCLASS_INDUTYPE_CD", "LGCLASS_INDTYPE_CD", "LGCLASS_INDUTYPE_CD"],
    )
    out = pd.DataFrame(
        {
            "period_key": source[period_col].map(_period_key),
            "admong_code": source[admong_col].fillna("").astype(str).str.strip() if admong_col else "",
            "mdclass_indtype_code": source[resolved_code_col].fillna("").astype(str).str.strip() if resolved_code_col else "",
            "pub_category_code": source["PUB_CATEGORY_CD"].fillna("").astype(str).str.strip()
            if "PUB_CATEGORY_CD" in source.columns
            else "",
            "sales_amount": source[sales_col].map(_to_float),
            "sales_rank": source[sales_rank_col].map(_to_float) if sales_rank_col else np.nan,
            "sales_rate": source[sales_rate_col].map(_to_float) if sales_rate_col else np.nan,
            "mom_abs": source[mom_abs_col].map(_to_float) if mom_abs_col else np.nan,
            "mom_pct": source[mom_pct_col].map(_to_float) if mom_pct_col else np.nan,
            "yoy_abs": source[yoy_abs_col].map(_to_float) if yoy_abs_col else np.nan,
            "yoy_pct": source[yoy_pct_col].map(_to_float) if yoy_pct_col else np.nan,
            "lgclass_indtype_name": source[resolved_name_col].fillna("").astype(str).str.strip(),
        }
    )
    out["period_date"] = pd.to_datetime(out["period_key"] + "01", format="%Y%m%d", errors="coerce")
    out = out.dropna(subset=["period_date"])
    out = out[out["lgclass_indtype_name"] != ""]
    return out


def _fetch_ggdata_page(
    service: str,
    app_key: str,
    page_index: int,
    page_size: int,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    retries: int = REQUEST_RETRIES,
) -> dict:
    params = {
        "Key": app_key,
        "Type": "json",
        "pIndex": page_index,
        "pSize": page_size,
    }
    url = f"{GGDATA_BASE_URL}/{service}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "monthly-local-consumption/1.0"})
    last_error: Exception | None = None
    safe_retries = max(1, int(retries))
    safe_timeout = max(5, int(timeout_seconds))
    for attempt in range(1, safe_retries + 1):
        try:
            with urlopen(request, timeout=safe_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, URLError) as exc:
            last_error = exc
            if attempt == safe_retries:
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


def _normalize_key(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _find_column(columns: pd.Index | list[str], preferred: list[str], contains: list[str] | None = None) -> str:
    by_normalized = {_normalize_key(col): str(col) for col in columns}
    for key in preferred:
        normalized = _normalize_key(key)
        if normalized in by_normalized:
            return by_normalized[normalized]
    if contains:
        contains_norm = [_normalize_key(token) for token in contains]
        for col in columns:
            normalized_col = _normalize_key(col)
            if all(token in normalized_col for token in contains_norm):
                return str(col)
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
