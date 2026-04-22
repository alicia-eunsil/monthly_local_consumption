from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.data import (
    fetch_ggdata_publication_use_records,
    normalize_publication_use_frame,
)
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
        status.success("운영 현황 로딩 완료")
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


def fmt_delta_million(value: float) -> str:
    if pd.isna(value):
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{fmt_million_money(value)}"


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:+,.1f}%"


def fmt_period_label(value: str) -> str:
    text = str(value).replace("-", "")
    if len(text) == 4 and text.isdigit():
        return f"{text}년"
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}년 {text[4:]}월"
    return str(value)


def fmt_delta_count(value: float) -> str:
    if pd.isna(value):
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.0f}명"


def fmt_yoy_delta(abs_value: float, pct_value: float, is_count: bool = False) -> str:
    if pd.isna(abs_value) or pd.isna(pct_value):
        return "전년동월대비 없음"
    if is_count:
        return f"{fmt_delta_count(abs_value)} / {fmt_pct(pct_value)}"
    return f"{fmt_delta_million(abs_value)} / {fmt_pct(pct_value)}"


def chart_bar(
    frame: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    x_title: str,
    limit: int = 15,
    color: str = "#2563eb",
    value_format: str = ",.0f",
    x_axis_format: str | None = None,
    x_tick_min_step: float | None = None,
):
    data = frame.head(limit).copy()
    bars = (
        alt.Chart(data, title=title)
        .mark_bar(color=color, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X(
                f"{x_col}:Q",
                title=x_title,
                axis=(
                    alt.Axis(format=x_axis_format, tickMinStep=x_tick_min_step)
                    if x_axis_format or x_tick_min_step is not None
                    else alt.Axis()
                ),
            ),
            y=alt.Y(
                f"{y_col}:N",
                sort="-x",
                title="",
                axis=alt.Axis(labelOverlap=False, labelLimit=120),
            ),
            tooltip=[
                alt.Tooltip(f"{y_col}:N", title="시군"),
                alt.Tooltip(f"{x_col}:Q", title=x_title, format=value_format),
            ],
        )
    )
    labels = (
        alt.Chart(data)
        .mark_text(align="left", baseline="middle", dx=4, color="#111827")
        .encode(
            x=alt.X(f"{x_col}:Q"),
            y=alt.Y(f"{y_col}:N", sort="-x"),
            text=alt.Text(f"{x_col}:Q", format=value_format),
        )
    )
    return alt.layer(bars, labels).properties(height=max(340, min(720, len(data) * 38)))


def trend_x_scale(frame: pd.DataFrame) -> alt.Scale:
    dates = frame["period_date"].dropna()
    if dates.empty:
        return alt.Scale()
    return alt.Scale(domain=[dates.min(), dates.max()])


def trend_line(frame: pd.DataFrame, y_col: str, title: str, y_title: str, color: str, x_scale: alt.Scale):
    return (
        alt.Chart(frame, title=title)
        .mark_line(point=True, color=color)
        .encode(
            x=alt.X("period_date:T", title="기준월", scale=x_scale),
            y=alt.Y(f"{y_col}:Q", title=y_title),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip(f"{y_col}:Q", title=y_title, format=",.0f"),
            ],
        )
        .properties(height=330, width="container")
    )


def add_yoy_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values("period_date").copy()
    for col in ["new_member_count", "charge_amount_million", "use_amount_million"]:
        prev = out[col].shift(12)
        out[f"{col}_yoy_abs"] = out[col] - prev
        out[f"{col}_yoy_pct"] = out[f"{col}_yoy_abs"] / prev.where(prev != 0) * 100
    return out



def add_sigun_yoy_columns(frame: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, group in frame.groupby("sigun_name", dropna=False):
        parts.append(add_yoy_columns(group))
    return pd.concat(parts, ignore_index=True) if parts else frame.copy()


def build_windowed_sigun_metric(
    frame: pd.DataFrame,
    value_col: str,
    end_period_key: str,
    months: int,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    end_rows = frame[frame["period_key"] == end_period_key]
    if end_rows.empty:
        return pd.DataFrame()
    end_date = end_rows["period_date"].max()
    if pd.isna(end_date):
        return pd.DataFrame()
    start_date = end_date - pd.DateOffset(months=max(1, int(months)) - 1)
    windowed = frame[(frame["period_date"] >= start_date) & (frame["period_date"] <= end_date)].copy()
    return (
        windowed[["sigun_name", "period_key", "period_date", value_col]]
        .dropna(subset=["sigun_name", value_col])
        .sort_values(["sigun_name", "period_date"])
    )


def compute_volatility_rank(
    frame: pd.DataFrame,
    value_col: str,
    min_points: int = 3,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    out = (
        frame.groupby("sigun_name", as_index=False)[value_col]
        .agg(["count", "mean", "std"])
        .reset_index()
        .rename(columns={"count": "n", "mean": "mean_val", "std": "std_val"})
    )
    out = out[out["n"] >= int(min_points)].copy()
    out["cv_pct"] = out["std_val"] / out["mean_val"].where(out["mean_val"] != 0) * 100
    out = out.dropna(subset=["cv_pct"])
    return out.sort_values("cv_pct")


def compute_current_streaks(frame: pd.DataFrame, value_col: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["sigun_name", "direction", "streak_months"])
    records: list[dict] = []
    for sigun, group in frame.groupby("sigun_name", dropna=False):
        g = group.sort_values("period_date").copy()
        diff = g[value_col].diff().dropna()
        if diff.empty:
            continue
        direction = 1 if diff.iloc[-1] > 0 else (-1 if diff.iloc[-1] < 0 else 0)
        if direction == 0:
            continue
        streak = 0
        for value in diff.iloc[::-1]:
            sign = 1 if value > 0 else (-1 if value < 0 else 0)
            if sign == direction:
                streak += 1
            else:
                break
        if streak > 0:
            records.append(
                {
                    "sigun_name": sigun,
                    "direction": "increase" if direction > 0 else "decrease",
                    "streak_months": streak,
                }
            )
    return pd.DataFrame(records)


def yoy_bar_line(
    frame: pd.DataFrame,
    amount_col: str,
    pct_col: str,
    title: str,
    amount_title: str,
    x_scale: alt.Scale | None = None,
):
    base = frame.dropna(subset=[amount_col]).copy()
    x_encoding = alt.X("period_date:T", title="기준월") if x_scale is None else alt.X("period_date:T", title="기준월", scale=x_scale)
    bars = (
        alt.Chart(base)
        .mark_bar(opacity=0.75)
        .encode(
            x=x_encoding,
            y=alt.Y(f"{amount_col}:Q", title=amount_title),
            color=alt.condition(
                f"datum['{amount_col}'] >= 0",
                alt.value("#dc2626"),
                alt.value("#2563eb"),
            ),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip(f"{amount_col}:Q", title=amount_title, format=",.0f"),
                alt.Tooltip(f"{pct_col}:Q", title="증감률(%)", format=",.1f"),
            ],
        )
    )
    line = (
        alt.Chart(base)
        .mark_line(point=True, color="#111827")
        .encode(
            x=x_encoding,
            y=alt.Y(f"{pct_col}:Q", title="증감률(%)"),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip(f"{amount_col}:Q", title=amount_title, format=",.0f"),
                alt.Tooltip(f"{pct_col}:Q", title="증감률(%)", format=",.1f"),
            ],
        )
    )
    return alt.layer(bars, line).resolve_scale(y="independent").properties(title=title, height=330, width="container")


def render_monthly_trend_charts(trend: pd.DataFrame) -> None:
    shared_x_scale = trend_x_scale(trend)

    st.markdown("#### 사용액")
    st.altair_chart(
        trend_line(trend, "use_amount_million", "월별 사용액 추이", "사용액(백만원)", "#0f766e", shared_x_scale),
        use_container_width=True,
    )
    st.altair_chart(
        yoy_bar_line(
            trend,
            "use_amount_million_yoy_abs",
            "use_amount_million_yoy_pct",
            "전년동월대비 사용액 추이",
            "증감액(백만원)",
            shared_x_scale,
        ),
        use_container_width=True,
    )

    st.markdown("#### 충전액")
    st.altair_chart(
        trend_line(trend, "charge_amount_million", "월별 충전액 추이", "충전액(백만원)", "#7c3aed", shared_x_scale),
        use_container_width=True,
    )
    st.altair_chart(
        yoy_bar_line(
            trend,
            "charge_amount_million_yoy_abs",
            "charge_amount_million_yoy_pct",
            "전년동월대비 충전액 추이",
            "증감액(백만원)",
            shared_x_scale,
        ),
        use_container_width=True,
    )

    st.markdown("#### 신규가입자")
    st.altair_chart(
        trend_line(trend, "new_member_count", "월별 신규가입자 추이", "신규가입자(명)", "#64748b", shared_x_scale),
        use_container_width=True,
    )
    st.altair_chart(
        yoy_bar_line(
            trend,
            "new_member_count_yoy_abs",
            "new_member_count_yoy_pct",
            "전년동월대비 신규가입자 추이",
            "증감수(명)",
            shared_x_scale,
        ),
        use_container_width=True,
    )


require_access_code()

service_info_help = (
    "내용: 경기도 및 31개 시군별 지역화폐의 신규가입자수, 사용액, 충전액 추이(2024년부터 현재까지)\n"
    "출처: 경기데이터드림\n"
    "한계: 업종별, 성별, 연령별 데이터의 경우 최신데이터가 없어서 분석불가(최신월2021년 6월)\n"
    "최종수정일 및 개발자: 2026년 4월 22일(데이터팀 임은실)"
)
title_col, info_col = st.columns([8, 1])
with title_col:
    st.title("경기도 지역화폐 발행·이용 현황")
with info_col:
    st.button("ⓘ 안내", key="service_info_hover", help=service_info_help, type="secondary")
st.caption("최신 월별 신규가입자수, 충전액, 사용액을 시군 단위로 확인합니다. (지역별 사용액, 충전액, 신규가입자수에 대해 최근일 기준 데이터 제공으로 분석에 한계 발생)")

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
        operation = pd.DataFrame()
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

trend = (
    filtered.groupby(["period_key", "period_date"], as_index=False)[
        ["new_member_count", "charge_amount_million", "use_amount_million"]
    ]
    .sum()
    .sort_values("period_date")
)
trend = add_yoy_columns(trend)
trend["use_to_charge_rate"] = (
    trend["use_amount_million"] / trend["charge_amount_million"].where(trend["charge_amount_million"] != 0) * 100
)
prev_ratio = trend["use_to_charge_rate"].shift(12)
trend["use_to_charge_rate_yoy_abs"] = trend["use_to_charge_rate"] - prev_ratio
trend["use_to_charge_rate_yoy_pct"] = trend["use_to_charge_rate_yoy_abs"] / prev_ratio.where(prev_ratio != 0) * 100

current = filtered[filtered["period_key"] == selected_period].copy()
selected_trend = trend[trend["period_key"] == selected_period].head(1)

total_new_members = float(current["new_member_count"].sum()) if not current.empty else float("nan")
total_charge_million = float(current["charge_amount_million"].sum()) if not current.empty else float("nan")
total_use_million = float(current["use_amount_million"].sum()) if not current.empty else float("nan")
use_to_charge_rate = (
    total_use_million / total_charge_million * 100
    if not pd.isna(total_charge_million) and total_charge_million != 0
    else float("nan")
)
charge_yoy_abs = (
    float(selected_trend["charge_amount_million_yoy_abs"].iloc[0]) if not selected_trend.empty else float("nan")
)
charge_yoy_pct = (
    float(selected_trend["charge_amount_million_yoy_pct"].iloc[0]) if not selected_trend.empty else float("nan")
)
use_yoy_abs = (
    float(selected_trend["use_amount_million_yoy_abs"].iloc[0]) if not selected_trend.empty else float("nan")
)
use_yoy_pct = (
    float(selected_trend["use_amount_million_yoy_pct"].iloc[0]) if not selected_trend.empty else float("nan")
)
new_member_yoy_abs = (
    float(selected_trend["new_member_count_yoy_abs"].iloc[0]) if not selected_trend.empty else float("nan")
)
new_member_yoy_pct = (
    float(selected_trend["new_member_count_yoy_pct"].iloc[0]) if not selected_trend.empty else float("nan")
)
use_to_charge_yoy_abs = (
    float(selected_trend["use_to_charge_rate_yoy_abs"].iloc[0]) if not selected_trend.empty else float("nan")
)
use_to_charge_yoy_pct = (
    float(selected_trend["use_to_charge_rate_yoy_pct"].iloc[0]) if not selected_trend.empty else float("nan")
)


def period_extreme_text(frame: pd.DataFrame, value_col: str, mode: str) -> tuple[str, str]:
    base = frame.dropna(subset=[value_col]).copy()
    if base.empty:
        return "-", "기준월 없음"
    row = base.loc[base[value_col].idxmax()] if mode == "max" else base.loc[base[value_col].idxmin()]
    value_text = fmt_million_money(float(row[value_col]))
    period_text = f"기준월: {fmt_period_label(str(row['period_key']))}"
    return value_text, period_text


use_max_value, use_max_period = period_extreme_text(trend, "use_amount_million", "max")
use_min_value, use_min_period = period_extreme_text(trend, "use_amount_million", "min")
charge_max_value, charge_max_period = period_extreme_text(trend, "charge_amount_million", "max")
charge_min_value, charge_min_period = period_extreme_text(trend, "charge_amount_million", "min")

tab_summary, tab_sigun, tab_diag = st.tabs(["경기도 현황", "시군별 현황", "진단"])

st.caption(f"기준 년월: {fmt_period_label(selected_period)} / 출처: 경기데이터드림")

with tab_summary:
    kpi_cols = st.columns(8)
    kpi_cols[0].metric(
        "월별 신규가입자수",
        "-" if pd.isna(total_new_members) else f"{total_new_members:,.0f}명",
        delta=fmt_yoy_delta(new_member_yoy_abs, new_member_yoy_pct, is_count=True),
    )
    kpi_cols[1].metric(
        "월별 충전액",
        fmt_million_money(total_charge_million),
        delta=fmt_yoy_delta(charge_yoy_abs, charge_yoy_pct),
    )
    kpi_cols[2].metric(
        "월별 사용액",
        fmt_million_money(total_use_million),
        delta=fmt_yoy_delta(use_yoy_abs, use_yoy_pct),
    )
    kpi_cols[3].metric(
        "사용액/충전액",
        "-" if pd.isna(use_to_charge_rate) else f"{use_to_charge_rate:,.1f}%",
        delta=(
            "전년동월대비 없음"
            if pd.isna(use_to_charge_yoy_abs) or pd.isna(use_to_charge_yoy_pct)
            else f"{use_to_charge_yoy_abs:+,.1f}%p / {use_to_charge_yoy_pct:+,.1f}%"
        ),
    )
    kpi_cols[4].metric("전체기간 사용액 :red[최고]", use_max_value, delta=use_max_period)
    kpi_cols[5].metric("전체기간 사용액 :blue[최저]", use_min_value, delta=use_min_period)
    kpi_cols[6].metric("전체기간 충전액 :red[최고]", charge_max_value, delta=charge_max_period)
    kpi_cols[7].metric("전체기간 충전액 :blue[최저]", charge_min_value, delta=charge_min_period)

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
    amount_base = alt.Chart(amount_long).encode(
        x=alt.X("period_date:T", title="기준월"),
        y=alt.Y("amount_million:Q", title="금액(백만원)"),
        color=alt.Color("metric_name:N", title="구분"),
        tooltip=[
            alt.Tooltip("period_key:N", title="기준년월"),
            alt.Tooltip("metric_name:N", title="구분"),
            alt.Tooltip("amount_million:Q", title="금액(백만원)", format=",.0f"),
        ],
    )
    amount_chart = (
        alt.layer(
            amount_base.transform_filter(alt.datum.metric_name == "사용액").mark_line(point=True),
            amount_base.transform_filter(alt.datum.metric_name == "충전액").mark_line(point=True, strokeDash=[6, 4]),
        )
        .properties(title="월별 충전액·사용액 추이", height=340)
    )
    st.altair_chart(amount_chart, use_container_width=True)

    st.markdown("---")
    render_monthly_trend_charts(trend)

with tab_diag:
    metric_map = {
        "사용액": ("use_amount_million", "사용액(백만원)"),
        "충전액": ("charge_amount_million", "충전액(백만원)"),
        "신규가입자": ("new_member_count", "신규가입자(명)"),
    }
    period_window_map = {"최근 6개월": 6, "최근 12개월": 12, "최근 24개월": 24}

    diag_metric = st.radio(
        "진단 지표",
        list(metric_map.keys()),
        index=0,
        key="diag_metric",
        horizontal=True,
    )
    metric_col, _metric_label = metric_map[diag_metric]

    st.markdown("#### 최근 연속 증가/감소")
    streak_base = (
        filtered[["sigun_name", "period_key", "period_date", metric_col]]
        .loc[lambda d: d["period_date"] <= filtered.loc[filtered["period_key"] == selected_period, "period_date"].max()]
        .dropna(subset=["sigun_name", metric_col])
        .sort_values(["sigun_name", "period_date"])
    )
    streaks = compute_current_streaks(streak_base, metric_col)
    if streaks.empty:
        st.info("연속 증가/감소를 계산할 데이터가 부족합니다.")
    else:
        inc = streaks[streaks["direction"] == "increase"].sort_values("streak_months", ascending=False).head(5).copy()
        dec = streaks[streaks["direction"] == "decrease"].sort_values("streak_months", ascending=False).head(5).copy()
        left, right = st.columns(2)
        left.altair_chart(
            chart_bar(
                inc,
                "streak_months",
                "sigun_name",
                "증가 연속 Top 5",
                "연속 개월",
                limit=5,
                color="#5f9f8f",
                value_format=",.0f",
                x_axis_format="d",
                x_tick_min_step=1,
            ),
            use_container_width=True,
        )
        right.altair_chart(
            chart_bar(
                dec,
                "streak_months",
                "sigun_name",
                "감소 연속 Top 5",
                "연속 개월",
                limit=5,
                color="#b97a7a",
                value_format=",.0f",
                x_axis_format="d",
                x_tick_min_step=1,
            ),
            use_container_width=True,
        )

    st.markdown("---")
    st.markdown("#### 전년동월 증감률(단월)")
    st.caption(
        f"기준년월: {fmt_period_label(selected_period)} / 설명: 선택한 기준월(보통 최신월)의 값을 작년 같은 달과 비교한 증감률(%)입니다. 단일 월 비교라 일시적 변동의 영향이 있을 수 있습니다."
    )
    sigun_yoy = add_sigun_yoy_columns(filtered)
    yoy_col = f"{metric_col}_yoy_pct"
    if yoy_col not in sigun_yoy.columns:
        st.info("선택한 지표의 전년동월 비교 컬럼이 없습니다.")
    else:
        yoy_rows = (
            sigun_yoy[sigun_yoy["period_key"] == selected_period]
            .dropna(subset=[yoy_col])
            .sort_values(yoy_col, ascending=False)
        )
        if yoy_rows.empty:
            st.info("전년동월 대비를 계산할 데이터가 부족합니다.")
        else:
            left, right = st.columns(2)
            left.altair_chart(
                chart_bar(
                    yoy_rows,
                    yoy_col,
                    "sigun_name",
                    "개선 Top 5",
                    "증감률(%)",
                    limit=5,
                    color="#5f9f8f",
                    value_format="+,.1f",
                ),
                use_container_width=True,
            )
            right.altair_chart(
                chart_bar(
                    yoy_rows.sort_values(yoy_col, ascending=True),
                    yoy_col,
                    "sigun_name",
                    "악화 Top 5",
                    "증감률(%)",
                    limit=5,
                    color="#c97b7b",
                    value_format="+,.1f",
                ),
                use_container_width=True,
            )

    st.markdown("---")
    st.markdown("#### 변동성(CV=표준편차/평균)")
    st.caption("CV 낮음 = 평균 대비 변동이 작아 상대적으로 안정적 / CV 높음 = 평균 대비 변동이 커 상대적으로 변동 큼")
    diag_window_name = st.radio(
        "분석 기간",
        list(period_window_map.keys()),
        index=1,
        key="diag_window",
        horizontal=True,
    )
    window_months = period_window_map[diag_window_name]
    diag_base = build_windowed_sigun_metric(
        filtered[["sigun_name", "period_key", "period_date", metric_col]].copy(),
        metric_col,
        selected_period,
        window_months,
    )
    volatility = compute_volatility_rank(diag_base, metric_col)
    if volatility.empty:
        st.info("변동성을 계산할 데이터가 부족합니다.")
    else:
        left, right = st.columns(2)
        left.altair_chart(
            chart_bar(
                volatility,
                "cv_pct",
                "sigun_name",
                "안정 Top 5 (CV 낮음)",
                "CV(%)",
                limit=5,
                color="#5b8db8",
                value_format=",.2f",
            ),
            use_container_width=True,
        )
        right.altair_chart(
            chart_bar(
                volatility.sort_values("cv_pct", ascending=False),
                "cv_pct",
                "sigun_name",
                "변동 Top 5 (CV 높음)",
                "CV(%)",
                limit=5,
                color="#c97b7b",
                value_format=",.2f",
            ),
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

    st.markdown("---")
    st.markdown("#### 시군별 월별 추이")
    trend_sigun_options = sorted([x for x in operation["sigun_name"].dropna().unique() if x])
    default_trend_sigun = selected_siguns[0] if selected_siguns else sigun_rank["sigun_name"].iloc[0]
    default_trend_index = (
        trend_sigun_options.index(default_trend_sigun) if default_trend_sigun in trend_sigun_options else 0
    )
    selected_trend_sigun = st.radio(
        "시군 선택",
        trend_sigun_options,
        index=default_trend_index,
        horizontal=True,
    )
    sigun_trend = operation[operation["sigun_name"] == selected_trend_sigun].copy()
    if sigun_trend.empty:
        st.info("월별 추이를 볼 시군을 선택해 주세요.")
    else:
        sigun_trend_yoy = add_yoy_columns(sigun_trend.sort_values("period_date").copy())
        sigun_trend_yoy["use_to_charge_rate"] = (
            sigun_trend_yoy["use_amount_million"]
            / sigun_trend_yoy["charge_amount_million"].where(sigun_trend_yoy["charge_amount_million"] != 0)
            * 100
        )
        prev_sigun_ratio = sigun_trend_yoy["use_to_charge_rate"].shift(12)
        sigun_trend_yoy["use_to_charge_rate_yoy_abs"] = sigun_trend_yoy["use_to_charge_rate"] - prev_sigun_ratio
        sigun_trend_yoy["use_to_charge_rate_yoy_pct"] = (
            sigun_trend_yoy["use_to_charge_rate_yoy_abs"] / prev_sigun_ratio.where(prev_sigun_ratio != 0) * 100
        )
        sigun_selected = sigun_trend_yoy[sigun_trend_yoy["period_key"] == selected_period].head(1)

        sigun_new_members = float(sigun_selected["new_member_count"].iloc[0]) if not sigun_selected.empty else float("nan")
        sigun_charge_million = (
            float(sigun_selected["charge_amount_million"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_use_million = float(sigun_selected["use_amount_million"].iloc[0]) if not sigun_selected.empty else float("nan")
        sigun_use_to_charge_rate = (
            sigun_use_million / sigun_charge_million * 100
            if not pd.isna(sigun_charge_million) and sigun_charge_million != 0
            else float("nan")
        )
        sigun_charge_yoy_abs = (
            float(sigun_selected["charge_amount_million_yoy_abs"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_charge_yoy_pct = (
            float(sigun_selected["charge_amount_million_yoy_pct"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_use_yoy_abs = (
            float(sigun_selected["use_amount_million_yoy_abs"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_use_yoy_pct = (
            float(sigun_selected["use_amount_million_yoy_pct"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_new_member_yoy_abs = (
            float(sigun_selected["new_member_count_yoy_abs"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_new_member_yoy_pct = (
            float(sigun_selected["new_member_count_yoy_pct"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_use_to_charge_yoy_abs = (
            float(sigun_selected["use_to_charge_rate_yoy_abs"].iloc[0]) if not sigun_selected.empty else float("nan")
        )
        sigun_use_to_charge_yoy_pct = (
            float(sigun_selected["use_to_charge_rate_yoy_pct"].iloc[0]) if not sigun_selected.empty else float("nan")
        )

        sigun_use_max_value, sigun_use_max_period = period_extreme_text(sigun_trend_yoy, "use_amount_million", "max")
        sigun_use_min_value, sigun_use_min_period = period_extreme_text(sigun_trend_yoy, "use_amount_million", "min")
        sigun_charge_max_value, sigun_charge_max_period = period_extreme_text(
            sigun_trend_yoy, "charge_amount_million", "max"
        )
        sigun_charge_min_value, sigun_charge_min_period = period_extreme_text(
            sigun_trend_yoy, "charge_amount_million", "min"
        )

        sigun_kpi_cols = st.columns(8)
        sigun_kpi_cols[0].metric(
            "월별 신규가입자수",
            "-" if pd.isna(sigun_new_members) else f"{sigun_new_members:,.0f}명",
            delta=fmt_yoy_delta(sigun_new_member_yoy_abs, sigun_new_member_yoy_pct, is_count=True),
        )
        sigun_kpi_cols[1].metric(
            "월별 충전액",
            fmt_million_money(sigun_charge_million),
            delta=fmt_yoy_delta(sigun_charge_yoy_abs, sigun_charge_yoy_pct),
        )
        sigun_kpi_cols[2].metric(
            "월별 사용액",
            fmt_million_money(sigun_use_million),
            delta=fmt_yoy_delta(sigun_use_yoy_abs, sigun_use_yoy_pct),
        )
        sigun_kpi_cols[3].metric(
            "사용액/충전액",
            "-" if pd.isna(sigun_use_to_charge_rate) else f"{sigun_use_to_charge_rate:,.1f}%",
            delta=(
                "전년동월대비 없음"
                if pd.isna(sigun_use_to_charge_yoy_abs) or pd.isna(sigun_use_to_charge_yoy_pct)
                else f"{sigun_use_to_charge_yoy_abs:+,.1f}%p / {sigun_use_to_charge_yoy_pct:+,.1f}%"
            ),
        )
        sigun_kpi_cols[4].metric("전체기간 사용액 :red[최고]", sigun_use_max_value, delta=sigun_use_max_period)
        sigun_kpi_cols[5].metric("전체기간 사용액 :blue[최저]", sigun_use_min_value, delta=sigun_use_min_period)
        sigun_kpi_cols[6].metric("전체기간 충전액 :red[최고]", sigun_charge_max_value, delta=sigun_charge_max_period)
        sigun_kpi_cols[7].metric("전체기간 충전액 :blue[최저]", sigun_charge_min_value, delta=sigun_charge_min_period)

        sigun_x_scale = trend_x_scale(sigun_trend_yoy)

        st.altair_chart(
            trend_line(sigun_trend_yoy, "use_amount_million", "사용액 추이", "사용액(백만원)", "#0f766e", sigun_x_scale),
            use_container_width=True,
        )
        st.altair_chart(
            yoy_bar_line(
                sigun_trend_yoy,
                "use_amount_million_yoy_abs",
                "use_amount_million_yoy_pct",
                "전년동월대비 사용액 추이",
                "증감액(백만원)",
                sigun_x_scale,
            ),
            use_container_width=True,
        )

        st.altair_chart(
            trend_line(sigun_trend_yoy, "charge_amount_million", "충전액 추이", "충전액(백만원)", "#7c3aed", sigun_x_scale),
            use_container_width=True,
        )
        st.altair_chart(
            yoy_bar_line(
                sigun_trend_yoy,
                "charge_amount_million_yoy_abs",
                "charge_amount_million_yoy_pct",
                "전년동월대비 충전액 추이",
                "증감액(백만원)",
                sigun_x_scale,
            ),
            use_container_width=True,
        )

        st.altair_chart(
            trend_line(sigun_trend_yoy, "new_member_count", "신규가입자수 추이", "신규가입자수(명)", "#64748b", sigun_x_scale),
            use_container_width=True,
        )
        st.altair_chart(
            yoy_bar_line(
                sigun_trend_yoy,
                "new_member_count_yoy_abs",
                "new_member_count_yoy_pct",
                "전년동월대비 신규가입자수 추이",
                "증감수(명)",
                sigun_x_scale,
            ),
            use_container_width=True,
        )
