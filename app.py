from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.data import (
    build_load_result,
    fetch_ggdata_middle_category_records,
    fetch_ggdata_publication_use_records,
    normalize_publication_use_frame,
)
from src.settings import get_access_code, get_app_key


st.set_page_config(
    page_title="경기도 지역화폐 월별 소비·운영 현황",
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


def _load_data_with_progress(app_key: str):
    status = st.empty()
    progress = st.progress(0)
    stage_weights = {
        "sales": (0, 85),
        "operation": (85, 15),
    }

    def update(stage: str, service: str, done: int, total: int) -> None:
        start, weight = stage_weights[stage]
        safe_total = max(total, 1)
        percent = min(99, start + int(weight * done / safe_total))
        label = "매출 데이터" if stage == "sales" else "운영 현황"
        status.info(f"{label} 불러오는 중... ({done:,}/{safe_total:,} 페이지)")
        progress.progress(percent)

    try:
        sales_records = fetch_ggdata_middle_category_records(
            app_key,
            progress_callback=lambda service, done, total: update("sales", service, done, total),
        )
        sales = build_load_result(
            pd.DataFrame(sales_records),
            "경기데이터드림 Open API 카드업종중분류 매출",
        )

        operation_records = fetch_ggdata_publication_use_records(
            app_key,
            progress_callback=lambda service, done, total: update("operation", service, done, total),
        )
        operation = normalize_publication_use_frame(pd.DataFrame(operation_records))
        progress.progress(100)
        status.success("데이터 로딩 완료")
        return sales, operation
    finally:
        progress.empty()
        status.empty()


def fmt_money(value: float) -> str:
    if pd.isna(value):
        return "-"
    abs_value = abs(float(value))
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:,.1f}억"
    if abs_value >= 10_000:
        return f"{value / 10_000:,.0f}만"
    return f"{value:,.0f}"


def fmt_million_money(value: float) -> str:
    if pd.isna(value):
        return "-"
    return fmt_money(float(value) * 1_000_000)


def chart_bar(
    frame: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    x_title: str,
    limit: int = 15,
    color: str = "#2563eb",
):
    data = frame.head(limit).copy()
    return (
        alt.Chart(data, title=title)
        .mark_bar(color=color, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X(f"{x_col}:Q", title=x_title),
            y=alt.Y(f"{y_col}:N", sort="-x", title=""),
            tooltip=[
                alt.Tooltip(f"{y_col}:N", title="구분"),
                alt.Tooltip(f"{x_col}:Q", title=x_title, format=",.0f"),
            ],
        )
        .properties(height=max(300, min(560, len(data) * 30)))
    )


def trend_chart(frame: pd.DataFrame, y_col: str, title: str, y_title: str, color: str):
    return (
        alt.Chart(frame, title=title)
        .mark_line(point=True, color=color)
        .encode(
            x=alt.X("period_date:T", title="기준월"),
            y=alt.Y(f"{y_col}:Q", title=y_title),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip(f"{y_col}:Q", title=y_title, format=",.0f"),
            ],
        )
        .properties(height=330)
    )


require_access_code()

st.title("경기도 지역화폐 월별 소비·운영 현황")
st.caption("지역화폐 매출을 업종·지역별로 보고, 충전액·사용액·월별 신규가입자 흐름을 함께 확인합니다.")

with st.sidebar:
    st.subheader("데이터")
    app_key = get_app_key()
    if app_key:
        st.success("APP_KEY 설정됨")
        if st.button("데이터 새로고침"):
            st.session_state.pop("_loaded_app_key", None)
            st.session_state.pop("_loaded_sales_result", None)
            st.session_state.pop("_loaded_operation", None)
            st.rerun()
    else:
        st.error("APP_KEY가 필요합니다.")

if not app_key:
    st.stop()

if (
    st.session_state.get("_loaded_app_key") == app_key
    and "_loaded_sales_result" in st.session_state
    and "_loaded_operation" in st.session_state
):
    sales_result = st.session_state["_loaded_sales_result"]
    operation = st.session_state["_loaded_operation"]
else:
    try:
        sales_result, operation = _load_data_with_progress(app_key)
        st.session_state["_loaded_app_key"] = app_key
        st.session_state["_loaded_sales_result"] = sales_result
        st.session_state["_loaded_operation"] = operation
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        st.stop()

sales = sales_result.frame
if sales_result.missing_required:
    st.error("매출 데이터 필수 컬럼을 찾지 못했습니다.")
    st.write("누락:", ", ".join(sales_result.missing_required))
    st.write("원본 컬럼:", ", ".join(sales_result.original_columns))
    st.stop()

if sales.empty:
    st.warning("분석 가능한 매출 데이터가 없습니다.")
    st.stop()

with st.sidebar:
    st.caption(f"매출: {sales_result.source_name}")
    st.caption("운영: 경기데이터드림 Open API 발행 및 이용 현황")

    common_periods = sorted(
        set(sales["period_key"].dropna().unique()) & set(operation["period_key"].dropna().unique()),
        reverse=True,
    )
    fallback_periods = sorted(sales["period_key"].dropna().unique(), reverse=True)
    period_options = common_periods or fallback_periods
    selected_period = st.selectbox("기준년월", period_options)

    region_options = sorted([x for x in sales["region_name"].dropna().unique() if x])
    industry_options = sorted([x for x in sales["industry_name"].dropna().unique() if x])
    selected_regions = st.multiselect("지역(읍면동코드)", region_options, placeholder="전체")
    selected_industries = st.multiselect("업종", industry_options, placeholder="전체")

filtered_sales = sales.copy()
if selected_regions:
    filtered_sales = filtered_sales[filtered_sales["region_name"].isin(selected_regions)]
if selected_industries:
    filtered_sales = filtered_sales[filtered_sales["industry_name"].isin(selected_industries)]

if filtered_sales.empty:
    st.warning("선택한 조건의 매출 데이터가 없습니다.")
    st.stop()

current_sales = filtered_sales[filtered_sales["period_key"] == selected_period].copy()
current_operation = operation[operation["period_key"] == selected_period].copy()

total_sales = float(current_sales["sales_amount"].sum())
total_new_members = float(current_operation["new_member_count"].sum()) if not current_operation.empty else float("nan")
total_charge_million = (
    float(current_operation["charge_amount_million"].sum()) if not current_operation.empty else float("nan")
)
total_use_million = (
    float(current_operation["use_amount_million"].sum()) if not current_operation.empty else float("nan")
)

kpi_cols = st.columns(4)
kpi_cols[0].metric("총 지역화폐 매출", fmt_money(total_sales))
kpi_cols[1].metric("월별 신규가입자수", "-" if pd.isna(total_new_members) else f"{total_new_members:,.0f}명")
kpi_cols[2].metric("월별 충전액", fmt_million_money(total_charge_million))
kpi_cols[3].metric("월별 사용액", fmt_million_money(total_use_million))

tab_summary, tab_sales, tab_operation = st.tabs(["요약", "업종·지역", "운영 현황"])

with tab_summary:
    sales_trend = (
        filtered_sales.groupby(["period_key", "period_date"], as_index=False)["sales_amount"]
        .sum()
        .sort_values("period_date")
    )
    operation_trend = (
        operation.groupby(["period_key", "period_date"], as_index=False)[
            ["charge_amount_million", "use_amount_million", "new_member_count"]
        ]
        .sum()
        .sort_values("period_date")
    )

    st.altair_chart(
        trend_chart(sales_trend, "sales_amount", "월별 지역화폐 매출 추이", "매출금액", "#0f766e"),
        use_container_width=True,
    )

    operation_long = operation_trend.melt(
        id_vars=["period_key", "period_date"],
        value_vars=["charge_amount_million", "use_amount_million"],
        var_name="metric",
        value_name="amount_million",
    )
    operation_long["metric_name"] = operation_long["metric"].map(
        {
            "charge_amount_million": "충전액",
            "use_amount_million": "사용액",
        }
    )
    op_chart = (
        alt.Chart(operation_long, title="월별 충전액·사용액 추이")
        .mark_line(point=True)
        .encode(
            x=alt.X("period_date:T", title="기준월"),
            y=alt.Y("amount_million:Q", title="금액(백만원)"),
            color=alt.Color("metric_name:N", title="구분"),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip("metric_name:N", title="구분"),
                alt.Tooltip("amount_million:Q", title="금액(백만원)", format=",.0f"),
            ],
        )
        .properties(height=330)
    )
    st.altair_chart(op_chart, use_container_width=True)

    left, right = st.columns(2)
    region_rank = (
        current_sales.groupby("region_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )
    industry_rank = (
        current_sales.groupby("industry_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )
    left.altair_chart(
        chart_bar(region_rank, "sales_amount", "region_name", "지역별 매출 Top 10", "매출금액", 10, "#1d4ed8"),
        use_container_width=True,
    )
    right.altair_chart(
        chart_bar(industry_rank, "sales_amount", "industry_name", "업종별 매출 Top 10", "매출금액", 10, "#b45309"),
        use_container_width=True,
    )

with tab_sales:
    region_rank = (
        current_sales.groupby("region_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )
    industry_rank = (
        current_sales.groupby("industry_name", as_index=False)["sales_amount"]
        .sum()
        .sort_values("sales_amount", ascending=False)
    )

    left, right = st.columns(2)
    left.altair_chart(
        chart_bar(region_rank, "sales_amount", "region_name", "지역별 매출 순위", "매출금액", 25, "#1d4ed8"),
        use_container_width=True,
    )
    right.altair_chart(
        chart_bar(industry_rank, "sales_amount", "industry_name", "업종별 매출 순위", "매출금액", 25, "#b45309"),
        use_container_width=True,
    )

    heat_regions = region_rank.head(15)["region_name"].tolist()
    heat_industries = industry_rank.head(10)["industry_name"].tolist()
    heat = current_sales[
        current_sales["region_name"].isin(heat_regions)
        & current_sales["industry_name"].isin(heat_industries)
    ]
    if not heat.empty:
        heat = heat.groupby(["region_name", "industry_name"], as_index=False)["sales_amount"].sum()
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

    st.dataframe(
        current_sales.sort_values("sales_amount", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

with tab_operation:
    if current_operation.empty:
        st.info("선택한 기준월의 운영 현황 데이터가 없습니다.")
    else:
        operation_rank = (
            current_operation.groupby("sigun_name", as_index=False)[
                ["new_member_count", "charge_amount_million", "use_amount_million"]
            ]
            .sum()
            .sort_values("use_amount_million", ascending=False)
        )

        left, right = st.columns(2)
        left.altair_chart(
            chart_bar(
                operation_rank,
                "use_amount_million",
                "sigun_name",
                "시군별 사용액 Top 10",
                "사용액(백만원)",
                10,
                "#0f766e",
            ),
            use_container_width=True,
        )
        right.altair_chart(
            chart_bar(
                operation_rank.sort_values("charge_amount_million", ascending=False),
                "charge_amount_million",
                "sigun_name",
                "시군별 충전액 Top 10",
                "충전액(백만원)",
                10,
                "#7c3aed",
            ),
            use_container_width=True,
        )

        member_chart = trend_chart(
            operation_trend,
            "new_member_count",
            "월별 신규가입자수 추이",
            "신규가입자수",
            "#64748b",
        )
        st.altair_chart(member_chart, use_container_width=True)

        display_rank = operation_rank.rename(
            columns={
                "sigun_name": "시군명",
                "new_member_count": "월별 신규가입자수",
                "charge_amount_million": "월별 충전액(백만원)",
                "use_amount_million": "월별 사용액(백만원)",
            }
        )
        st.dataframe(display_rank, use_container_width=True, hide_index=True)
