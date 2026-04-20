from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from http.cookiejar import CookieJar

import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
GGDATA_MIDDLE_CATEGORY_CSV_URL = (
    "https://data.gg.go.kr/portal/data/sheet/downloadSheetData.do"
    "?downloadType=C&infId=21P6SA4OOH5AW25V3QRP38272636&infSeq=1"
)
GGDATA_MIDDLE_CATEGORY_PAGE_URL = (
    "https://data.gg.go.kr/portal/data/service/selectServicePage.do"
    "?infId=21P6SA4OOH5AW25V3QRP38272636&infSeq=1"
)


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
        "INDUTYPE_MLSFC_CODE",
        "industry_code",
    ],
    "industry_name": [
        "중분류업종명",
        "업종중분류명",
        "업종명",
        "INDUTYPE_MLSFC_NM",
        "industry_name",
    ],
    "sales_amount": [
        "매출금액",
        "매출액",
        "지역화폐매출금액",
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


def list_csv_files() -> list[Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DATA_DIR.glob("*.csv"))


def read_csv_bytes(content: bytes, source_name: str) -> pd.DataFrame:
    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(BytesIO(content), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError(f"CSV 파일을 읽을 수 없습니다: {source_name}")


def read_csv_path(path: Path) -> pd.DataFrame:
    return read_csv_bytes(path.read_bytes(), path.name)


def download_ggdata_middle_category_csv() -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 monthly-local-consumption/1.0",
        "Accept": "text/csv,application/octet-stream,*/*",
        "Referer": GGDATA_MIDDLE_CATEGORY_PAGE_URL,
    }
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    page_request = Request(GGDATA_MIDDLE_CATEGORY_PAGE_URL, headers=headers)
    request = Request(
        GGDATA_MIDDLE_CATEGORY_CSV_URL,
        headers=headers,
    )
    try:
        opener.open(page_request, timeout=30).read()
        with opener.open(request, timeout=60) as response:
            content = response.read()
    except URLError as exc:
        raise RuntimeError(f"경기데이터드림 CSV 다운로드에 실패했습니다: {exc}") from exc
    if _looks_like_block_page(content):
        raise RuntimeError(
            "경기데이터드림이 서버 측 자동 다운로드를 차단했습니다. "
            "Open API 요청주소가 공개되지 않은 데이터셋이라 현재는 CSV 업로드 방식을 사용해야 합니다."
        )
    return content


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


def sample_data() -> pd.DataFrame:
    rows = []
    months = pd.period_range("2025-01", "2025-12", freq="M")
    regions = ["수원시 영통구", "성남시 분당구", "부천시", "화성시", "고양시 덕양구", "김포시"]
    industries = ["음식", "유통", "의료", "교육", "문화/여가", "생활서비스"]
    rng = np.random.default_rng(20260420)

    for m_idx, month in enumerate(months):
        month_factor = 1 + m_idx * 0.025
        for r_idx, region in enumerate(regions):
            region_factor = 1 + r_idx * 0.08
            for i_idx, industry in enumerate(industries):
                industry_factor = 1 + i_idx * 0.11
                noise = rng.normal(1, 0.05)
                amount = 120_000_000 * month_factor * region_factor * industry_factor * noise
                rows.append(
                    {
                        "기준년월": month.strftime("%Y%m"),
                        "읍면동코드": f"41{r_idx + 1000}",
                        "읍면동명": region,
                        "중분류업종코드": f"I{i_idx + 1:02d}",
                        "중분류업종명": industry,
                        "매출금액": round(float(amount)),
                    }
                )
    df = pd.DataFrame(rows)
    df["전월대비증감값"] = (
        df.sort_values("기준년월")
        .groupby(["읍면동코드", "중분류업종코드"])["매출금액"]
        .diff()
    )
    df["전월대비증감률"] = (
        df["전월대비증감값"]
        / (
            df.sort_values("기준년월")
            .groupby(["읍면동코드", "중분류업종코드"])["매출금액"]
            .shift(1)
        )
        * 100
    )
    return df


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


def _looks_like_block_page(content: bytes) -> bool:
    head = content[:500].lower()
    return b"<script" in head or b"<html" in head or "정상적인 접근이 아닙니다".encode("utf-8") in content[:1000]
