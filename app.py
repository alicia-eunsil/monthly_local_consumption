from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.data import (
    build_load_result,
    list_csv_files,
    period_change,
    read_csv_bytes,
    read_csv_path,
    download_ggdata_middle_category_csv,
    sample_data,
)
from src.settings import get_access_code, get_app_key


st.set_page_config(
    page_title="경기도 지역화폐 월별 소비 현황",
    page_icon="LC",
    layout="wide",
)

st.markdown(
    """
<style>
.stApp {
  font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
}
.stMetric {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 14px;
}
div[data-testid="stMetricValue"] {
  font-size: 1.45rem;
}
div[data-testid="stSidebar"] {
  border-right: 1px solid #e5e7eb;
}
</style>
""",
    unsafe_allow_html=True,
)


def require_access_code() -> None:
    expected = get_access_code()
    if not expected:
        return

    if st.session_state.get("_access_granted_code") == expected:
        return

    st.title("Access Code")
    with st.form("access_code_form", clear_on_submit=True):
        entered = st.text_input("Access code", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if str(entered).strip() == expected:
            st.session_state["_access_granted_code"] = expected
            st.rerun()
        st.error("Invalid access code.")
    st.stop()


@st.cache_data(show_spinner=False)
def _load_path_cached(path_text: str, modified_ns: int):
    path = Path(path_text)
    raw = read_csv_path(path)
    return build_load_result(raw, path.name)


@st.cache_data(show_spinner=False)
def _load_upload_cached(content: bytes, source_name: str):
    raw = read_csv_bytes(content, source_name)
    return build_load_result(raw, source_name)


@st.cache_data(show_spinner=False)
def _load_sample_cached():
    return build_load_result(sample_data(), "샘플 데이터")


@st.cache_data(show_spinner=False, ttl=60 * 60 * 6)
def _load_ggdata_csv_cached():
    content = download_ggdata_middle_category_csv()
    raw = read_csv_bytes(content, "경기데이터드림 카드업종중분류 CSV")
    return build_load_result(raw, "경기데이터드림 카드업종중분류 CSV")


def fmt_money(value: float) -> str:
    if pd.isna(value):
        return "-"
    abs_value = abs(float(value))
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:,.1f}억"
    if abs_value >= 10_000:
        return f"{value / 10_000:,.0f}만"
    return f"{value:,.0f}"


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:+.1f}%"


def pct_delta(current: float, previous: float) -> float:
    if pd.isna(previous) or previous == 0:
        return float("nan")
    return (current - previous) / previous * 100


def total_for_period(frame: pd.DataFrame, period_key: str) -> float:
    return float(frame.loc[frame["period_key"] == period_key, "sales_amount"].sum())


def chart_bar(
    frame: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    limit: int = 15,
    color: str = "#2563eb",
):
    data = frame.head(limit).copy()
    return (
        alt.Chart(data, title=title)
        .mark_bar(color=color, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X(f"{x_col}:Q", title="매출금액"),
            y=alt.Y(f"{y_col}:N", sort="-x", title=""),
            tooltip=[
                alt.Tooltip(f"{y_col}:N", title="구분"),
                alt.Tooltip(f"{x_col}:Q", title="매출금액", format=",.0f"),
            ],
        )
        .properties(height=max(300, min(560, len(data) * 30)))
    )


def chart_change(frame: pd.DataFrame, label_col: str, title: str, limit: int = 15):
    data = frame.dropna(subset=["change_abs"]).copy()
    data = data.reindex(data["change_abs"].abs().sort_values(ascending=False).index).head(limit)
    return (
        alt.Chart(data, title=title)
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X("change_abs:Q", title="증감액"),
            y=alt.Y(f"{label_col}:N", sort="-x", title=""),
            color=alt.condition(
                alt.datum.change_abs >= 0,
                alt.value("#dc2626"),
                alt.value("#2563eb"),
            ),
            tooltip=[
                alt.Tooltip(f"{label_col}:N", title="구분"),
                alt.Tooltip("current_sales:Q", title="현재 매출", format=",.0f"),
                alt.Tooltip("previous_sales:Q", title="비교 매출", format=",.0f"),
                alt.Tooltip("change_abs:Q", title="증감액", format=",.0f"),
                alt.Tooltip("change_pct:Q", title="증감률", format=".1f"),
            ],
        )
        .properties(height=max(300, min(560, len(data) * 30)))
    )


require_access_code()

st.title("경기도 지역화폐 월별 소비 현황")
st.caption("월별 지역화폐 매출을 지역과 업종 관점에서 모니터링합니다.")

with st.sidebar:
    st.subheader("데이터")
    app_key = get_app_key()
    if app_key:
        st.success("APP_KEY 설정됨")
    else:
        st.info("CSV 모드는 APP_KEY 없이 사용할 수 있습니다.")

    csv_files = list_csv_files()
    uploaded = st.file_uploader("CSV 업로드", type=["csv"])

    if uploaded is not None:
        source_type = "업로드 CSV"
    elif csv_files:
        source_type = "data 폴더 CSV"
    elif app_key:
        source_type = "경기데이터드림 CSV"
    else:
        source_type = "경기데이터드림 CSV"

    source_type = st.radio(
        "데이터 소스",
        ["경기데이터드림 CSV", "업로드 CSV", "data 폴더 CSV", "샘플 데이터"],
        index=["경기데이터드림 CSV", "업로드 CSV", "data 폴더 CSV", "샘플 데이터"].index(source_type),
    )

    load_result = None
    if source_type == "경기데이터드림 CSV":
        with st.spinner("경기데이터드림 CSV를 불러오는 중입니다."):
            try:
                load_result = _load_ggdata_csv_cached()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
                st.info("포털 다운로드가 막히면 CSV 업로드 또는 data 폴더 CSV 방식을 사용하세요.")
                st.stop()
    elif source_type == "업로드 CSV":
        if uploaded is None:
            st.info("CSV 파일을 업로드하세요.")
            st.stop()
        load_result = _load_upload_cached(uploaded.getvalue(), uploaded.name)
    elif source_type == "data 폴더 CSV":
        if not csv_files:
            st.info("data 폴더에 CSV 파일을 넣어주세요.")
            st.stop()
        selected_file = st.selectbox("파일", csv_files, format_func=lambda p: p.name)
        load_result = _load_path_cached(str(selected_file), selected_file.stat().st_mtime_ns)
    else:
        load_result = _load_sample_cached()

df = load_result.frame
if load_result.missing_required:
    st.error("필수 컬럼을 찾지 못했습니다.")
    st.write("누락:", ", ".join(load_result.missing_required))
    st.write("원본 컬럼:", ", ".join(load_result.original_columns))
    st.stop()

if df.empty:
    st.warning("분석 가능한 데이터가 없습니다.")
    st.stop()

with st.sidebar:
    st.caption(f"소스: {load_result.source_name}")
    if load_result.source_name == "샘플 데이터":
        st.warning("현재 화면은 샘플 데이터 기준입니다.")

    period_options = sorted(df["period_key"].dropna().unique(), reverse=True)
    selected_period = st.selectbox("기준년월", period_options)

    region_options = sorted([x for x in df["region_name"].dropna().unique() if x])
    industry_options = sorted([x for x in df["industry_name"].dropna().unique() if x])
    selected_regions = st.multiselect("지역", region_options, placeholder="전체")
    selected_industries = st.multiselect("업종", industry_options, placeholder="전체")

filtered = df.copy()
if selected_regions:
    filtered = filtered[filtered["region_name"].isin(selected_regions)]
if selected_industries:
    filtered = filtered[filtered["industry_name"].isin(selected_industries)]

if filtered.empty:
    st.warning("선택한 조건의 데이터가 없습니다.")
    st.stop()

current = filtered[filtered["period_key"] == selected_period].copy()
previous_period = (
    pd.to_datetime(selected_period + "01", format="%Y%m%d") - pd.DateOffset(months=1)
).strftime("%Y%m")
yoy_period = (
    pd.to_datetime(selected_period + "01", format="%Y%m%d") - pd.DateOffset(months=12)
).strftime("%Y%m")

total_current = total_for_period(filtered, selected_period)
total_previous = total_for_period(filtered, previous_period)
total_yoy = total_for_period(filtered, yoy_period)
mom = pct_delta(total_current, total_previous)
yoy = pct_delta(total_current, total_yoy)

kpi_cols = st.columns(5)
kpi_cols[0].metric("총 매출", fmt_money(total_current))
kpi_cols[1].metric("전월 대비", fmt_pct(mom), delta=fmt_pct(mom) if not pd.isna(mom) else None)
kpi_cols[2].metric("전년 동월 대비", fmt_pct(yoy), delta=fmt_pct(yoy) if not pd.isna(yoy) else None)
kpi_cols[3].metric("지역 수", f"{current['region_name'].nunique():,}")
kpi_cols[4].metric("업종 수", f"{current['industry_name'].nunique():,}")

tab_summary, tab_region, tab_industry, tab_change, tab_data = st.tabs(
    ["요약", "지역", "업종", "변화", "데이터"]
)

with tab_summary:
    trend = (
        filtered.groupby(["period_key", "period_date"], as_index=False)["sales_amount"]
        .sum()
        .sort_values("period_date")
    )
    trend_chart = (
        alt.Chart(trend, title="월별 지역화폐 매출 추이")
        .mark_line(point=True, color="#0f766e")
        .encode(
            x=alt.X("period_date:T", title="기준월"),
            y=alt.Y("sales_amount:Q", title="매출금액"),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip("sales_amount:Q", title="매출금액", format=",.0f"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(trend_chart, use_container_width=True)

    left, right = st.columns(2)
    region_rank = (
        current.groupby("region_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )
    industry_rank = (
        current.groupby("industry_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )
    left.altair_chart(
        chart_bar(region_rank, "sales_amount", "region_name", "지역별 매출 Top 15", color="#1d4ed8"),
        use_container_width=True,
    )
    right.altair_chart(
        chart_bar(industry_rank, "sales_amount", "industry_name", "업종별 매출 Top 15", color="#b45309"),
        use_container_width=True,
    )

    heat_regions = region_rank.head(15)["region_name"].tolist()
    heat_industries = industry_rank.head(10)["industry_name"].tolist()
    heat = current[
        current["region_name"].isin(heat_regions) & current["industry_name"].isin(heat_industries)
    ]
    if not heat.empty:
        heat = (
            heat.groupby(["region_name", "industry_name"], as_index=False)["sales_amount"]
            .sum()
            .copy()
        )
        heat_chart = (
            alt.Chart(heat, title="지역 x 업종 매출 히트맵")
            .mark_rect()
            .encode(
                x=alt.X("industry_name:N", title="업종"),
                y=alt.Y("region_name:N", title="지역", sort=heat_regions),
                color=alt.Color("sales_amount:Q", title="매출금액", scale=alt.Scale(scheme="tealblues")),
                tooltip=[
                    alt.Tooltip("region_name:N", title="지역"),
                    alt.Tooltip("industry_name:N", title="업종"),
                    alt.Tooltip("sales_amount:Q", title="매출금액", format=",.0f"),
                ],
            )
            .properties(height=430)
        )
        st.altair_chart(heat_chart, use_container_width=True)

with tab_region:
    region_rank = (
        current.groupby("region_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )
    st.altair_chart(
        chart_bar(region_rank, "sales_amount", "region_name", "지역별 매출 순위", limit=25, color="#1d4ed8"),
        use_container_width=True,
    )

    region_mom = period_change(filtered, ["region_name"], selected_period, 1)
    region_yoy = period_change(filtered, ["region_name"], selected_period, 12)
    left, right = st.columns(2)
    if not region_mom.empty:
        left.altair_chart(
            chart_change(region_mom, "region_name", "지역별 전월 대비 변화", limit=15),
            use_container_width=True,
        )
    if not region_yoy.empty:
        right.altair_chart(
            chart_change(region_yoy, "region_name", "지역별 전년 동월 대비 변화", limit=15),
            use_container_width=True,
        )

    st.dataframe(region_rank, use_container_width=True, hide_index=True)

with tab_industry:
    industry_rank = (
        current.groupby("industry_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )
    st.altair_chart(
        chart_bar(industry_rank, "sales_amount", "industry_name", "업종별 매출 순위", limit=25),
        use_container_width=True,
    )

    industry_mom = period_change(filtered, ["industry_name"], selected_period, 1)
    industry_yoy = period_change(filtered, ["industry_name"], selected_period, 12)
    left, right = st.columns(2)
    if not industry_mom.empty:
        left.altair_chart(
            chart_change(industry_mom, "industry_name", "업종별 전월 대비 변화", limit=15),
            use_container_width=True,
        )
    if not industry_yoy.empty:
        right.altair_chart(
            chart_change(industry_yoy, "industry_name", "업종별 전년 동월 대비 변화", limit=15),
            use_container_width=True,
        )

    st.dataframe(industry_rank, use_container_width=True, hide_index=True)

with tab_change:
    compare_unit = st.radio("비교 단위", ["지역", "업종", "지역 x 업종"], horizontal=True)
    lag_label = st.radio("비교 기준", ["전월", "전년 동월"], horizontal=True)
    lag = 1 if lag_label == "전월" else 12

    if compare_unit == "지역":
        group_cols = ["region_name"]
        label_col = "region_name"
    elif compare_unit == "업종":
        group_cols = ["industry_name"]
        label_col = "industry_name"
    else:
        temp = filtered.copy()
        temp["region_industry"] = temp["region_name"] + " / " + temp["industry_name"]
        filtered_for_change = temp
        group_cols = ["region_industry"]
        label_col = "region_industry"

    if compare_unit != "지역 x 업종":
        filtered_for_change = filtered

    change_df = period_change(filtered_for_change, group_cols, selected_period, lag)
    if change_df.empty:
        st.info("비교 가능한 데이터가 없습니다.")
    else:
        st.altair_chart(
            chart_change(change_df, label_col, f"{compare_unit}별 {lag_label} 변화", limit=30),
            use_container_width=True,
        )
        view = change_df.copy()
        view["change_pct"] = view["change_pct"].round(2)
        st.dataframe(view, use_container_width=True, hide_index=True)

with tab_data:
    st.write(f"원본 소스: {load_result.source_name}")
    st.write(f"분석 행 수: {len(filtered):,}")
    st.write("표준 컬럼:", ", ".join(filtered.columns))
    st.dataframe(filtered.sort_values(["period_key", "region_name", "industry_name"]), use_container_width=True)
    csv = filtered.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "필터링 데이터 다운로드",
        data=csv,
        file_name="filtered_local_consumption.csv",
        mime="text/csv",
    )
