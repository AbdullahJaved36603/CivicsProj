"""School-level and global analytics functions.

All Plotly charts use a unified dark theme with glassmorphic styling
to match the dark admin dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Dark palette constants (mirrors the dashboard)
# ---------------------------------------------------------------------------
_BG_TRANSPARENT = "rgba(0,0,0,0)"
_GRID_COLOR = "rgba(255,255,255,0.04)"
_TEXT_PRIMARY = "#e2e8f0"
_TEXT_DIM = "#94a3b8"
_FONT_FAMILY = "Inter, sans-serif"

_CYAN = "#00d4ff"
_PURPLE = "#7c3aed"
_PINK = "#f472b6"
_EMERALD = "#10b981"
_AMBER = "#f59e0b"
_ROSE = "#fb7185"

_BAR_GRADIENT = [[0, _PURPLE], [0.5, _CYAN], [1, _EMERALD]]
_SUBJECT_COLORS = [_CYAN, _PINK, _PURPLE]
_GENDER_COLORS = [_CYAN, _PINK, _PURPLE]


def _apply_dark_layout(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply a consistent dark theme to any Plotly figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=_BG_TRANSPARENT,
        plot_bgcolor=_BG_TRANSPARENT,
        font=dict(family=_FONT_FAMILY, size=12, color=_TEXT_DIM),
        title=dict(
            text=title,
            font=dict(family="Space Grotesk, sans-serif", size=16, color=_TEXT_PRIMARY),
            x=0.01,
            y=0.97,
        ),
        margin=dict(l=24, r=24, t=56, b=24),
        xaxis=dict(
            gridcolor=_GRID_COLOR,
            zerolinecolor=_GRID_COLOR,
            showline=False,
            tickfont=dict(color=_TEXT_DIM, size=11),
        ),
        yaxis=dict(
            gridcolor=_GRID_COLOR,
            zerolinecolor=_GRID_COLOR,
            showline=False,
            tickfont=dict(color=_TEXT_DIM, size=11),
        ),
        legend=dict(
            bgcolor=_BG_TRANSPARENT,
            font=dict(color=_TEXT_DIM, size=11),
            borderwidth=0,
        ),
        hoverlabel=dict(
            bgcolor="#111633",
            font_size=12,
            font_family=_FONT_FAMILY,
            font_color=_TEXT_PRIMARY,
            bordercolor="rgba(255,255,255,0.08)",
        ),
        bargap=0.28,
        coloraxis_colorbar=dict(
            tickfont=dict(color=_TEXT_DIM),
            title_font=dict(color=_TEXT_DIM),
        ),
    )
    return fig


@dataclass
class AnalyticsBundle:
    class_performance: pd.DataFrame
    subject_performance: pd.DataFrame
    gender_performance: pd.DataFrame
    monthly_vs_final: pd.DataFrame


def _numeric_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame.copy()
    for column in values.columns:
        values[column] = pd.to_numeric(values[column], errors="coerce")
    return values.select_dtypes(include=["number"]).dropna(axis=1, how="all")


def _safe_avg(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return 0.0
    return round(float(clean.mean()), 2)


def _subject_profile_from_numbers(numbers: pd.DataFrame) -> pd.DataFrame:
    if numbers.empty:
        return pd.DataFrame({"subject": ["Math", "Science", "English"], "average": [0.0, 0.0, 0.0]})

    cols = list(numbers.columns)
    buckets = {
        "Math": cols[0::3],
        "Science": cols[1::3],
        "English": cols[2::3],
    }

    rows = []
    for subject, bucket_cols in buckets.items():
        if not bucket_cols:
            rows.append({"subject": subject, "average": 0.0})
            continue
        rows.append({"subject": subject, "average": _safe_avg(numbers[bucket_cols].stack())})
    return pd.DataFrame(rows)


def _gender_profile_from_students(student_df: pd.DataFrame) -> pd.DataFrame:
    if student_df.empty:
        return pd.DataFrame({"gender": ["Male", "Female"], "average": [0.0, 0.0]})

    if "gender" not in student_df.columns:
        return pd.DataFrame({"gender": ["Male", "Female"], "average": [0.0, 0.0]})

    if "final_score" in student_df.columns:
        metric_col = "final_score"
    elif "monthly_score" in student_df.columns:
        metric_col = "monthly_score"
    else:
        return pd.DataFrame({"gender": ["Male", "Female"], "average": [0.0, 0.0]})

    temp = student_df.copy()
    temp[metric_col] = pd.to_numeric(temp[metric_col], errors="coerce")
    grouped = (
        temp.groupby(temp["gender"].astype(str).str.title())[metric_col]
        .mean()
        .dropna()
        .reset_index()
        .rename(columns={"gender": "gender", metric_col: "average"})
    )
    if grouped.empty:
        return pd.DataFrame({"gender": ["Male", "Female"], "average": [0.0, 0.0]})

    grouped["average"] = grouped["average"].round(2)
    return grouped


def analytics_from_pk9_workbook(pk9_file: str) -> AnalyticsBundle:
    path = Path(pk9_file)
    if not path.exists():
        raise FileNotFoundError(f"PK9 workbook not found: {pk9_file}")

    excel = pd.ExcelFile(path)

    class_rows: List[Dict[str, float]] = []
    monthly_final_rows: List[Dict[str, float]] = []
    subject_pool: List[pd.DataFrame] = []

    for sheet in excel.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet)
        numeric = _numeric_matrix(frame)
        if numeric.empty:
            continue

        class_avg = _safe_avg(numeric.stack())
        class_rows.append({"class_name": sheet.strip(), "average": class_avg})

        split = max(1, numeric.shape[1] // 2)
        monthly_avg = _safe_avg(numeric.iloc[:, :split].stack())
        final_avg = _safe_avg(numeric.iloc[:, split:].stack()) if numeric.shape[1] > 1 else monthly_avg
        monthly_final_rows.append(
            {
                "class_name": sheet.strip(),
                "monthly_avg": monthly_avg,
                "final_avg": final_avg,
            }
        )

        subject_pool.append(_subject_profile_from_numbers(numeric))

    class_perf = pd.DataFrame(class_rows).sort_values("average", ascending=False).reset_index(drop=True)
    monthly_vs_final = pd.DataFrame(monthly_final_rows).reset_index(drop=True)

    if subject_pool:
        subject_perf = (
            pd.concat(subject_pool, ignore_index=True)
            .groupby("subject", as_index=False)["average"]
            .mean()
            .round(2)
        )
    else:
        subject_perf = pd.DataFrame({"subject": ["Math", "Science", "English"], "average": [0.0, 0.0, 0.0]})

    gender_perf = pd.DataFrame({"gender": ["Male", "Female"], "average": [0.0, 0.0]})

    return AnalyticsBundle(
        class_performance=class_perf,
        subject_performance=subject_perf,
        gender_performance=gender_perf,
        monthly_vs_final=monthly_vs_final,
    )


def analytics_from_student_sheet(student_df: pd.DataFrame) -> AnalyticsBundle:
    if student_df.empty:
        empty = pd.DataFrame()
        return AnalyticsBundle(empty, empty, empty, empty)

    temp = student_df.copy()
    temp["monthly_score"] = pd.to_numeric(temp.get("monthly_score", np.nan), errors="coerce")
    temp["final_score"] = pd.to_numeric(temp.get("final_score", np.nan), errors="coerce")

    class_perf = (
        temp.groupby("class_id", as_index=False)["final_score"]
        .mean()
        .fillna(0)
        .rename(columns={"class_id": "class_name", "final_score": "average"})
    )
    class_perf["average"] = class_perf["average"].round(2)

    subject_perf = pd.DataFrame(
        {
            "subject": ["Math", "Science", "English"],
            "average": [
                _safe_avg(temp["monthly_score"]),
                _safe_avg((temp["monthly_score"] + temp["final_score"]) / 2),
                _safe_avg(temp["final_score"]),
            ],
        }
    )

    gender_perf = _gender_profile_from_students(temp)

    monthly_vs_final = pd.DataFrame(
        {
            "metric": ["Monthly Test", "Final Exam"],
            "average": [_safe_avg(temp["monthly_score"]), _safe_avg(temp["final_score"])],
        }
    )

    return AnalyticsBundle(class_perf, subject_perf, gender_perf, monthly_vs_final)


def global_overview_from_monthly_report(monthly_report_file: str) -> pd.DataFrame:
    path = Path(monthly_report_file)
    if not path.exists():
        raise FileNotFoundError(f"Monthly report workbook not found: {monthly_report_file}")

    excel = pd.ExcelFile(path)
    rows = []
    for sheet in excel.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet)
        numeric = _numeric_matrix(frame)
        rows.append(
            {
                "report_sheet": sheet.strip(),
                "average_score": _safe_avg(numeric.stack()) if not numeric.empty else 0.0,
                "records": int(frame.shape[0]),
            }
        )

    return pd.DataFrame(rows).sort_values("average_score", ascending=False).reset_index(drop=True)


def build_plotly_charts(bundle: AnalyticsBundle) -> Dict[str, go.Figure]:
    charts: Dict[str, go.Figure] = {}

    if not bundle.class_performance.empty:
        fig = px.bar(
            bundle.class_performance,
            x="class_name",
            y="average",
            color="average",
            color_continuous_scale=_BAR_GRADIENT,
        )
        fig.update_traces(
            marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Average: %{y:.1f}<extra></extra>",
        )
        charts["class"] = _apply_dark_layout(fig, "Class Performance")

    if not bundle.subject_performance.empty:
        fig = px.bar(
            bundle.subject_performance,
            x="subject",
            y="average",
            color="subject",
            color_discrete_sequence=_SUBJECT_COLORS,
        )
        fig.update_traces(
            marker_line_width=0,
            hovertemplate="<b>%{x}</b><br>Average: %{y:.1f}<extra></extra>",
        )
        fig.update_layout(showlegend=False)
        charts["subject"] = _apply_dark_layout(fig, "Subject Performance")

    if not bundle.gender_performance.empty:
        fig = px.pie(
            bundle.gender_performance,
            names="gender",
            values="average",
            hole=0.55,
            color_discrete_sequence=_GENDER_COLORS,
        )
        fig.update_traces(
            textfont=dict(color=_TEXT_PRIMARY, size=13),
            marker=dict(line=dict(color="#060a1e", width=2)),
            hovertemplate="<b>%{label}</b><br>Average: %{value:.1f}<extra></extra>",
        )
        charts["gender"] = _apply_dark_layout(fig, "Gender-based Performance")

    if not bundle.monthly_vs_final.empty:
        if "metric" in bundle.monthly_vs_final.columns:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=bundle.monthly_vs_final["metric"],
                    y=bundle.monthly_vs_final["average"],
                    mode="lines+markers+text",
                    text=[f"{v:.1f}" for v in bundle.monthly_vs_final["average"]],
                    textposition="top center",
                    textfont=dict(color=_TEXT_PRIMARY, size=12),
                    line=dict(color=_CYAN, width=3),
                    marker=dict(size=10, color=_CYAN, line=dict(width=2, color="#060a1e")),
                    fill="tozeroy",
                    fillcolor="rgba(0,212,255,0.08)",
                    hovertemplate="<b>%{x}</b><br>Average: %{y:.1f}<extra></extra>",
                )
            )
            charts["monthly_final"] = _apply_dark_layout(fig, "Monthly vs Final Exam")
        else:
            melt = bundle.monthly_vs_final.melt(
                id_vars=["class_name"],
                value_vars=["monthly_avg", "final_avg"],
                var_name="exam_type",
                value_name="average",
            )
            color_map = {"monthly_avg": _AMBER, "final_avg": _EMERALD}
            fig = px.line(
                melt,
                x="class_name",
                y="average",
                color="exam_type",
                markers=True,
                color_discrete_map=color_map,
            )
            fig.update_traces(
                line_width=3,
                marker=dict(size=8, line=dict(width=2, color="#060a1e")),
                hovertemplate="<b>%{x}</b><br>Average: %{y:.1f}<extra></extra>",
            )
            charts["monthly_final"] = _apply_dark_layout(
                fig, "Monthly vs Final Comparison by Class"
            )

    return charts
