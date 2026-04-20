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
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}년 {text[4:]}월"
    return str(value)


def fmt_delta_count(value: float) -> str:
    if pd.isna(value):
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.0f}명"


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
    bars = (
        alt.Chart(data, title=title)
        .mark_bar(color=color, cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X(f"{x_col}:Q", title=x_title),
            y=alt.Y(
                f"{y_col}:N",
                sort="-x",
                title="",
                axis=alt.Axis(labelOverlap=False, labelLimit=120),
            ),
            tooltip=[
                alt.Tooltip(f"{y_col}:N", title="시군"),
                alt.Tooltip(f"{x_col}:Q", title=x_title, format=",.0f"),
            ],
        )
    )
    labels = (
        alt.Chart(data)
        .mark_text(align="left", baseline="middle", dx=4, color="#111827")
        .encode(
            x=alt.X(f"{x_col}:Q"),
            y=alt.Y(f"{y_col}:N", sort="-x"),
            text=alt.Text(f"{x_col}:Q", format=",.0f"),
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
        .properties(height=330)
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


def yoy_bar_line(
    frame: pd.DataFrame,
    amount_col: str,
    pct_col: str,
    title: str,
    amount_title: str,
    x_scale: alt.Scale,
):
    base = frame.dropna(subset=[amount_col]).copy()
    bars = (
        alt.Chart(base)
        .mark_bar(opacity=0.75)
        .encode(
            x=alt.X("period_date:T", title="기준월", scale=x_scale),
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
            x=alt.X("period_date:T", title="기준월", scale=x_scale),
            y=alt.Y(f"{pct_col}:Q", title="증감률(%)"),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip(f"{amount_col}:Q", title=amount_title, format=",.0f"),
                alt.Tooltip(f"{pct_col}:Q", title="증감률(%)", format=",.1f"),
            ],
        )
    )
    return alt.layer(bars, line).resolve_scale(y="independent").properties(title=title, height=330)


def metric_trend_table(
    frame: pd.DataFrame,
    value_col: str,
    yoy_abs_col: str,
    yoy_pct_col: str,
    value_label: str,
    yoy_abs_label: str,
):
    display = (
        frame[["period_key", value_col, yoy_abs_col, yoy_pct_col]]
        .sort_values("period_key", ascending=False)
        .rename(
            columns={
                "period_key": "기준년월",
                value_col: value_label,
                yoy_abs_col: yoy_abs_label,
                yoy_pct_col: "증감률(%)",
            }
        )
    )
    st.dataframe(
        display.style.format(
            {
                value_label: "{:,.0f}",
                yoy_abs_label: "{:,.0f}",
                "증감률(%)": "{:+,.1f}",
            },
            na_rep="-",
        ),
        use_container_width=True,
        hide_index=True,
    )


def sigun_amount_trend_chart(frame: pd.DataFrame):
    amount_long = frame.melt(
        id_vars=["period_key", "period_date", "sigun_name"],
        value_vars=["use_amount_million", "charge_amount_million"],
        var_name="metric",
        value_name="amount_million",
    )
    amount_long["metric_name"] = amount_long["metric"].map(
        {
            "use_amount_million": "사용액",
            "charge_amount_million": "충전액",
        }
    )
    return (
        alt.Chart(amount_long, title="선택 시군 사용액·충전액 월별 추이")
        .mark_line(point=True)
        .encode(
            x=alt.X("period_date:T", title="기준월"),
            y=alt.Y("amount_million:Q", title="금액(백만원)"),
            color=alt.Color("sigun_name:N", title="시군"),
            strokeDash=alt.StrokeDash("metric_name:N", title="구분"),
            tooltip=[
                alt.Tooltip("period_key:N", title="기준년월"),
                alt.Tooltip("sigun_name:N", title="시군"),
                alt.Tooltip("metric_name:N", title="구분"),
                alt.Tooltip("amount_million:Q", title="금액(백만원)", format=",.0f"),
            ],
        )
        .properties(height=380)
    )


def sigun_yoy_rank_chart(frame: pd.DataFrame, limit: int = 15):
    data = frame.head(limit).copy()
    bars = (
        alt.Chart(data, title=f"시군별 사용액 전년동월대비 증감률 Top {limit}")
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X("use_amount_million_yoy_pct:Q", title="사용액 증감률(%)"),
            y=alt.Y(
                "sigun_name:N",
                sort="-x",
                title="",
                axis=alt.Axis(labelOverlap=False, labelLimit=120),
            ),
            color=alt.condition(
                "datum['use_amount_million_yoy_pct'] >= 0",
                alt.value("#dc2626"),
                alt.value("#2563eb"),
            ),
            tooltip=[
                alt.Tooltip("sigun_name:N", title="시군"),
                alt.Tooltip("use_amount_million:Q", title="월별 사용액(백만원)", format=",.0f"),
                alt.Tooltip("use_amount_million_yoy_abs:Q", title="사용액 증감액(백만원)", format=",.0f"),
                alt.Tooltip("use_amount_million_yoy_pct:Q", title="사용액 증감률(%)", format=",.1f"),
            ],
        )
    )
    labels = (
        alt.Chart(data)
        .mark_text(align="left", baseline="middle", dx=4, color="#111827")
        .encode(
            x=alt.X("use_amount_million_yoy_pct:Q"),
            y=alt.Y("sigun_name:N", sort="-x"),
            text=alt.Text("use_amount_million_yoy_pct:Q", format="+,.1f"),
        )
    )
    return alt.layer(bars, labels).properties(height=max(340, min(720, len(data) * 38)))


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

trend = (
    filtered.groupby(["period_key", "period_date"], as_index=False)[
        ["new_member_count", "charge_amount_million", "use_amount_million"]
    ]
    .sum()
    .sort_values("period_date")
)
trend = add_yoy_columns(trend)

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

st.caption(f"기준 년월: {fmt_period_label(selected_period)}")
kpi_cols = st.columns(4)
kpi_cols[0].metric(
    "월별 신규가입자수",
    "-" if pd.isna(total_new_members) else f"{total_new_members:,.0f}명",
    delta=None
    if pd.isna(new_member_yoy_pct)
    else f"{fmt_delta_count(new_member_yoy_abs)} / {fmt_pct(new_member_yoy_pct)}",
)
kpi_cols[1].metric(
    "월별 충전액",
    fmt_million_money(total_charge_million),
    delta=None if pd.isna(charge_yoy_pct) else f"{fmt_delta_million(charge_yoy_abs)} / {fmt_pct(charge_yoy_pct)}",
)
kpi_cols[2].metric(
    "월별 사용액",
    fmt_million_money(total_use_million),
    delta=None if pd.isna(use_yoy_pct) else f"{fmt_delta_million(use_yoy_abs)} / {fmt_pct(use_yoy_pct)}",
)
kpi_cols[3].metric("사용액/충전액", "-" if pd.isna(use_to_charge_rate) else f"{use_to_charge_rate:,.1f}%")

tab_summary, tab_trend, tab_sigun = st.tabs(["요약", "월별 추이", "시군별 현황"])

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

    st.caption(f"기준: {fmt_period_label(selected_period)}")
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
    shared_x_scale = trend_x_scale(trend)

    st.markdown("#### 사용액")
    st.altair_chart(
        trend_line(trend, "use_amount_million", "월별 사용액 추이", "사용액(백만원)", "#0f766e", shared_x_scale),
        use_container_width=True,
    )
    left, right = st.columns([3, 2])
    with left:
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
    with right:
        metric_trend_table(
            trend,
            "use_amount_million",
            "use_amount_million_yoy_abs",
            "use_amount_million_yoy_pct",
            "월데이터(백만원)",
            "전년동월대비 증감(백만원)",
        )

    st.markdown("#### 충전액")
    st.altair_chart(
        trend_line(trend, "charge_amount_million", "월별 충전액 추이", "충전액(백만원)", "#7c3aed", shared_x_scale),
        use_container_width=True,
    )
    left, right = st.columns([3, 2])
    with left:
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
    with right:
        metric_trend_table(
            trend,
            "charge_amount_million",
            "charge_amount_million_yoy_abs",
            "charge_amount_million_yoy_pct",
            "월데이터(백만원)",
            "전년동월대비 증감(백만원)",
        )

    st.markdown("#### 신규가입자수")
    st.altair_chart(
        trend_line(trend, "new_member_count", "월별 신규가입자수 추이", "신규가입자수", "#64748b", shared_x_scale),
        use_container_width=True,
    )
    left, right = st.columns([3, 2])
    with left:
        st.altair_chart(
            yoy_bar_line(
                trend,
                "new_member_count_yoy_abs",
                "new_member_count_yoy_pct",
                "전년동월대비 신규가입자수 추이",
                "증감수(명)",
                shared_x_scale,
            ),
            use_container_width=True,
        )
    with right:
        metric_trend_table(
            trend,
            "new_member_count",
            "new_member_count_yoy_abs",
            "new_member_count_yoy_pct",
            "월데이터(명)",
            "전년동월대비 증감(명)",
        )

with tab_sigun:
    st.caption(f"기준년월: {fmt_period_label(selected_period)}")

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

    st.markdown("#### 선택 시군 월별 추이")
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
        st.altair_chart(sigun_amount_trend_chart(sigun_trend), use_container_width=True)

    st.markdown("#### 시군별 사용액 전년동월대비 증감률 순위")
    sigun_yoy = add_sigun_yoy_columns(operation)
    selected_period_yoy = (
        sigun_yoy[sigun_yoy["period_key"] == selected_period]
        .dropna(subset=["use_amount_million_yoy_pct"])
        .sort_values("use_amount_million_yoy_pct", ascending=False)
    )
    if selected_period_yoy.empty:
        st.info("시군별 전년동월대비 순위를 계산하려면 최소 13개월 이상의 데이터가 필요합니다.")
    else:
        st.altair_chart(sigun_yoy_rank_chart(selected_period_yoy), use_container_width=True)
        display_yoy_rank = selected_period_yoy[
            [
                "sigun_name",
                "use_amount_million",
                "use_amount_million_yoy_abs",
                "use_amount_million_yoy_pct",
                "charge_amount_million",
            ]
        ].rename(
            columns={
                "sigun_name": "시군명",
                "use_amount_million": "월별 사용액(백만원)",
                "use_amount_million_yoy_abs": "사용액 증감액(백만원)",
                "use_amount_million_yoy_pct": "사용액 증감률(%)",
                "charge_amount_million": "월별 충전액(백만원)",
            }
        )
        st.dataframe(
            display_yoy_rank.style.format(
                {
                    "월별 사용액(백만원)": "{:,.0f}",
                    "사용액 증감액(백만원)": "{:,.0f}",
                    "사용액 증감률(%)": "{:+,.1f}",
                    "월별 충전액(백만원)": "{:,.0f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
