from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.data import fetch_ggdata_publication_use_records, normalize_publication_use_frame
from src.settings import get_access_code, get_app_key


st.set_page_config(
    page_title="경기도 지역화폐 발행·이용 현황",
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


def load_operation_with_progress(app_key: str) -> pd.DataFrame:
    status = st.empty()
    progress = st.progress(0)

    def update(_service: str, done: int, total: int) -> None:
        safe_total = max(total, 1)
        percent = min(99, int(100 * done / safe_total))
        status.info(f"운영 현황 데이터를 불러오는 중... ({done:,}/{safe_total:,} 페이지)")
        progress.progress(percent)

    try:
        records = fetch_ggdata_publication_use_records(app_key, progress_callback=update)
        operation = normalize_publication_use_frame(pd.DataFrame(records))
        progress.progress(100)
        status.success("데이터 로딩 완료")
        return operation
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
                alt.Tooltip(f"{y_col}:N", title="시군"),
                alt.Tooltip(f"{x_col}:Q", title=x_title, format=",.0f"),
            ],
        )
        .properties(height=max(300, min(560, len(data) * 30)))
    )


def trend_line(frame: pd.DataFrame, y_col: str, title: str, y_title: str, color: str):
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

st.title("경기도 지역화폐 발행·이용 현황")
st.caption("최신 월별 신규가입자수, 충전액, 사용액을 시군 단위로 확인합니다.")

with st.sidebar:
    st.subheader("데이터")
    app_key = get_app_key()
    if app_key:
        st.success("APP_KEY 설정됨")
        if st.button("데이터 새로고침"):
            st.session_state.pop("_loaded_app_key", None)
            st.session_state.pop("_loaded_operation", None)
            st.rerun()
    else:
        st.error("APP_KEY가 필요합니다.")

if not app_key:
    st.stop()

if st.session_state.get("_loaded_app_key") == app_key and "_loaded_operation" in st.session_state:
    operation = st.session_state["_loaded_operation"]
else:
    try:
        operation = load_operation_with_progress(app_key)
        st.session_state["_loaded_app_key"] = app_key
        st.session_state["_loaded_operation"] = operation
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        st.stop()

if operation.empty:
    st.warning("분석 가능한 데이터가 없습니다.")
    st.stop()

with st.sidebar:
    st.caption("소스: 경기데이터드림 Open API 지역화폐 발행 및 이용 현황")
    period_options = sorted(operation["period_key"].dropna().unique(), reverse=True)
    selected_period = st.selectbox("기준년월", period_options)

    sigun_options = sorted([x for x in operation["sigun_name"].dropna().unique() if x])
    selected_siguns = st.multiselect("시군", sigun_options, placeholder="전체")

filtered = operation.copy()
if selected_siguns:
    filtered = filtered[filtered["sigun_name"].isin(selected_siguns)]

if filtered.empty:
    st.warning("선택한 조건의 데이터가 없습니다.")
    st.stop()

current = filtered[filtered["period_key"] == selected_period].copy()

total_new_members = float(current["new_member_count"].sum()) if not current.empty else float("nan")
total_charge_million = float(current["charge_amount_million"].sum()) if not current.empty else float("nan")
total_use_million = float(current["use_amount_million"].sum()) if not current.empty else float("nan")
use_to_charge_rate = (
    total_use_million / total_charge_million * 100
    if not pd.isna(total_charge_million) and total_charge_million != 0
    else float("nan")
)

kpi_cols = st.columns(4)
kpi_cols[0].metric("월별 신규가입자수", "-" if pd.isna(total_new_members) else f"{total_new_members:,.0f}명")
kpi_cols[1].metric("월별 충전액", fmt_million_money(total_charge_million))
kpi_cols[2].metric("월별 사용액", fmt_million_money(total_use_million))
kpi_cols[3].metric("사용액/충전액", "-" if pd.isna(use_to_charge_rate) else f"{use_to_charge_rate:,.1f}%")

tab_summary, tab_trend, tab_sigun = st.tabs(["요약", "월별 추이", "시군별 현황"])

trend = (
    filtered.groupby(["period_key", "period_date"], as_index=False)[
        ["new_member_count", "charge_amount_million", "use_amount_million"]
    ]
    .sum()
    .sort_values("period_date")
)

with tab_summary:
    amount_long = trend.melt(
        id_vars=["period_key", "period_date"],
        value_vars=["charge_amount_million", "use_amount_million"],
        var_name="metric",
        value_name="amount_million",
    )
    amount_long["metric_name"] = amount_long["metric"].map(
        {
            "charge_amount_million": "충전액",
            "use_amount_million": "사용액",
        }
    )
    amount_chart = (
        alt.Chart(amount_long, title="월별 충전액·사용액 추이")
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
        .properties(height=340)
    )
    st.altair_chart(amount_chart, use_container_width=True)

    sigun_rank = (
        current.groupby("sigun_name", as_index=False)[
            ["new_member_count", "charge_amount_million", "use_amount_million"]
        ]
        .sum()
        .sort_values("use_amount_million", ascending=False)
    )
    left, right = st.columns(2)
    left.altair_chart(
        chart_bar(sigun_rank, "use_amount_million", "sigun_name", "시군별 사용액 Top 10", "사용액(백만원)", 10, "#0f766e"),
        use_container_width=True,
    )
    right.altair_chart(
        chart_bar(
            sigun_rank.sort_values("charge_amount_million", ascending=False),
            "charge_amount_million",
            "sigun_name",
            "시군별 충전액 Top 10",
            "충전액(백만원)",
            10,
            "#7c3aed",
        ),
        use_container_width=True,
    )

with tab_trend:
    st.altair_chart(
        trend_line(trend, "use_amount_million", "월별 사용액 추이", "사용액(백만원)", "#0f766e"),
        use_container_width=True,
    )
    st.altair_chart(
        trend_line(trend, "charge_amount_million", "월별 충전액 추이", "충전액(백만원)", "#7c3aed"),
        use_container_width=True,
    )
    st.altair_chart(
        trend_line(trend, "new_member_count", "월별 신규가입자수 추이", "신규가입자수", "#64748b"),
        use_container_width=True,
    )

with tab_sigun:
    sigun_rank = (
        current.groupby("sigun_name", as_index=False)[
            ["new_member_count", "charge_amount_million", "use_amount_million"]
        ]
        .sum()
        .sort_values("use_amount_million", ascending=False)
    )
    left, right = st.columns(2)
    left.altair_chart(
        chart_bar(sigun_rank, "use_amount_million", "sigun_name", "시군별 사용액 순위", "사용액(백만원)", 31, "#0f766e"),
        use_container_width=True,
    )
    right.altair_chart(
        chart_bar(
            sigun_rank.sort_values("new_member_count", ascending=False),
            "new_member_count",
            "sigun_name",
            "시군별 신규가입자수 순위",
            "신규가입자수",
            31,
            "#64748b",
        ),
        use_container_width=True,
    )

    display = sigun_rank.rename(
        columns={
            "sigun_name": "시군명",
            "new_member_count": "월별 신규가입자수",
            "charge_amount_million": "월별 충전액(백만원)",
            "use_amount_million": "월별 사용액(백만원)",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
