from __future__ import annotations

import importlib
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Tuple

import altair as alt
import streamlit as st

_PLOTLY_IO: Any = None

LIGHT_THEME: Dict[str, str] = {
    "primaryColor": "#4F46E5",
    "backgroundColor": "#F5F7FA",
    "secondaryBackgroundColor": "#EDEFF5",
    "cardColor": "#FFFFFF",
    "textColor": "#111827",
    "mutedText": "#6B7280",
    "cardBorder": "#E5E7EB",
    "sidebarBg": "#EDEFF5",
    "sidebarText": "#111827",
    "buttonBg": "#4F46E5",
    "buttonText": "#FFFFFF",
    "buttonDisabledBg": "#C7D2FE",
    "buttonDisabledText": "#4B5563",
    "sidebarActiveBg": "#E0E7FF",
    "sidebarActiveText": "#1E3A8A",
    "sidebarInactiveBg": "transparent",
    "chartGrid": "#D1D5DB",
    "chartPrimary": "#4F46E5",
}

DARK_THEME: Dict[str, str] = {
    "primaryColor": "#6366F1",
    "backgroundColor": "#0F172A",
    "secondaryBackgroundColor": "#111827",
    "cardColor": "#1E293B",
    "textColor": "#E5E7EB",
    "mutedText": "#94A3B8",
    "cardBorder": "#374151",
    "sidebarBg": "#111827",
    "sidebarText": "#E5E7EB",
    "buttonBg": "#6366F1",
    "buttonText": "#FFFFFF",
    "buttonDisabledBg": "#374151",
    "buttonDisabledText": "#9CA3AF",
    "sidebarActiveBg": "#1E293B",
    "sidebarActiveText": "#A5B4FC",
    "sidebarInactiveBg": "transparent",
    "chartGrid": "#334155",
    "chartPrimary": "#93C5FD",
}


def init_ui_state() -> None:
    if "theme" not in st.session_state:
        st.session_state["theme"] = "light"
    if "is_loading" not in st.session_state:
        st.session_state["is_loading"] = False


def current_theme_name() -> str:
    return str(st.session_state.get("theme", "light")).strip().lower() or "light"


def current_theme_tokens() -> Dict[str, str]:
    return DARK_THEME if current_theme_name() == "dark" else LIGHT_THEME


def _altair_theme_config() -> Dict[str, Any]:
    tokens = current_theme_tokens()
    return {
        "config": {
            "background": tokens["cardColor"],
            "title": {"color": tokens["textColor"]},
            "axis": {
                "labelColor": tokens["textColor"],
                "titleColor": tokens["textColor"],
                "gridColor": tokens["chartGrid"],
                "domainColor": tokens["cardBorder"],
                "tickColor": tokens["cardBorder"],
            },
            "legend": {
                "labelColor": tokens["textColor"],
                "titleColor": tokens["textColor"],
            },
            "view": {
                "stroke": tokens["cardBorder"],
            },
            "range": {
                "category": [
                    tokens["chartPrimary"],
                    "#10B981",
                    "#F59E0B",
                    "#EF4444",
                    "#06B6D4",
                    "#8B5CF6",
                ]
            },
        }
    }


def apply_theme() -> None:
    tokens = current_theme_tokens()

    if not st.session_state.get("_sms_altair_theme_registered", False):
        try:
            alt.themes.register("sms_theme", _altair_theme_config)
        except Exception:
            pass
        st.session_state["_sms_altair_theme_registered"] = True

    alt.themes.enable("sms_theme")

    global _PLOTLY_IO
    if _PLOTLY_IO is None:
        try:
            _PLOTLY_IO = importlib.import_module("plotly.io")
        except Exception:
            _PLOTLY_IO = False
    if _PLOTLY_IO not in (None, False):
        try:
            _PLOTLY_IO.templates.default = "plotly_dark" if current_theme_name() == "dark" else "plotly_white"
        except Exception:
            pass

    css = f"""
    <style>
    :root {{
        --sms-primary: {tokens['primaryColor']};
        --sms-button-bg: {tokens['buttonBg']};
        --sms-button-text: {tokens['buttonText']};
        --sms-button-disabled-bg: {tokens['buttonDisabledBg']};
        --sms-button-disabled-text: {tokens['buttonDisabledText']};
        --sms-sidebar-active-bg: {tokens['sidebarActiveBg']};
        --sms-sidebar-active-text: {tokens['sidebarActiveText']};
        --sms-sidebar-inactive-bg: {tokens['sidebarInactiveBg']};
        --sms-bg: {tokens['backgroundColor']};
        --sms-surface: {tokens['secondaryBackgroundColor']};
        --sms-card: {tokens['cardColor']};
        --sms-text: {tokens['textColor']};
        --sms-muted: {tokens['mutedText']};
        --sms-border: {tokens['cardBorder']};
        --sms-sidebar: {tokens['sidebarBg']};
        --sms-sidebar-text: {tokens['sidebarText']};
    }}

    body {{
        color: var(--sms-text) !important;
        background-color: var(--sms-bg) !important;
    }}

    .stApp {{
        background: var(--sms-bg);
        color: var(--sms-text) !important;
    }}

    header[data-testid="stHeader"] {{
        background: var(--sms-surface) !important;
        border-bottom: 1px solid var(--sms-border) !important;
    }}

    [data-testid="stDecoration"] {{
        background: var(--sms-primary) !important;
    }}

    [data-testid="stToolbar"] button,
    [data-testid="stToolbar"] svg,
    [data-testid="stStatusWidget"] *,
    [data-testid="stMainMenu"] * {{
        color: var(--sms-text) !important;
        fill: var(--sms-text) !important;
    }}

    [data-testid="stAppViewContainer"] > .main {{
        background: var(--sms-bg) !important;
    }}

    .stMarkdown, .stText, .stCaption, .stAlert, p, span, label, h1, h2, h3, h4, h5, h6 {{
        color: inherit !important;
    }}

    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stMarkdownContainer"] li,
    div[data-testid="stMarkdownContainer"] strong,
    div[data-testid="stMetricLabel"] div,
    div[data-testid="stMetricValue"] div {{
        color: var(--sms-text) !important;
    }}

    div[data-testid="stDataFrame"],
    div[data-testid="stTable"] {{
        background: var(--sms-card) !important;
        border: 1px solid var(--sms-border) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }}

    div[data-testid="stDataFrame"] * {{
        color: var(--sms-text) !important;
        border-color: var(--sms-border) !important;
    }}

    div[data-testid="stDataFrame"] [role="columnheader"],
    div[data-testid="stDataFrame"] [role="gridcell"],
    div[data-testid="stDataFrame"] [class*="header"],
    div[data-testid="stDataFrame"] [class*="cell"] {{
        background: var(--sms-card) !important;
    }}

    div[data-testid="stDataFrame"] [class*="header"],
    div[data-testid="stDataFrame"] [role="columnheader"] {{
        background: var(--sms-surface) !important;
        color: var(--sms-text) !important;
    }}

    div[data-testid="stDataFrame"] [class*="row"]:hover [class*="cell"],
    div[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {{
        background: color-mix(in srgb, var(--sms-primary) 12%, var(--sms-card)) !important;
    }}

    div[data-testid="stTable"] table {{
        width: 100%;
        border-collapse: collapse;
        background: var(--sms-card) !important;
        color: var(--sms-text) !important;
    }}

    div[data-testid="stTable"] th,
    div[data-testid="stTable"] td {{
        border: 1px solid var(--sms-border) !important;
        color: var(--sms-text) !important;
        background: var(--sms-card) !important;
    }}

    div[data-testid="stTable"] th {{
        background: var(--sms-surface) !important;
    }}

    section[data-testid="stSidebar"] {{
        background: var(--sms-sidebar) !important;
        border-right: 1px solid var(--sms-border);
        color: var(--sms-sidebar-text) !important;
    }}

    section[data-testid="stSidebar"] .block-container {{
        padding-top: 1rem;
        padding-bottom: 1rem;
    }}

    section[data-testid="stSidebar"] * {{
        color: var(--sms-sidebar-text) !important;
    }}

    [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {{
        background: var(--sms-sidebar-active-bg) !important;
        color: var(--sms-sidebar-active-text) !important;
        border: 1px solid var(--sms-border) !important;
    }}

    [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {{
        background: var(--sms-sidebar-inactive-bg) !important;
        color: var(--sms-sidebar-text) !important;
        border: 1px solid var(--sms-border) !important;
    }}

    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border: 1px solid var(--sms-border) !important;
        border-radius: 14px !important;
        background: var(--sms-card) !important;
        color: var(--sms-text) !important;
    }}

    div[data-testid="stButton"] > button,
    div[data-testid="stDownloadButton"] > button,
    div[data-testid="stFormSubmitButton"] > button {{
        width: 100%;
        border-radius: 10px;
        transition: all 0.18s ease;
        border: 1px solid var(--sms-border);
        background: var(--sms-button-bg);
        color: var(--sms-button-text);
    }}

    div[data-testid="stButton"] > button:disabled,
    div[data-testid="stDownloadButton"] > button:disabled,
    div[data-testid="stFormSubmitButton"] > button:disabled {{
        background: var(--sms-button-disabled-bg) !important;
        color: var(--sms-button-disabled-text) !important;
        border-color: var(--sms-border) !important;
        opacity: 1 !important;
    }}

    div[data-testid="stButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {{
        transform: translateY(-1px);
        border-color: var(--sms-primary);
        box-shadow: 0 6px 14px rgba(79, 70, 229, 0.18);
    }}

    .sms-page-subtitle {{
        color: var(--sms-muted);
        margin-top: -0.25rem;
        margin-bottom: 0.5rem;
    }}

    .sms-sidebar-section {{
        margin-top: 0.75rem;
        margin-bottom: 0.5rem;
        color: var(--sms-muted);
        font-size: 0.82rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }}

    @media (max-width: 768px) {{
        .block-container {{
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def render_theme_toggle() -> None:
    current_theme = current_theme_name()
    st.markdown("<div class='sms-sidebar-section'>Appearance</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        dark_clicked = st.button(
            "Dark Mode 🌙",
            type="primary" if current_theme == "dark" else "secondary",
            key="theme_dark_button",
            disabled=bool(st.session_state.get("is_loading", False)),
        )
    with col2:
        light_clicked = st.button(
            "Light Mode ☀️",
            type="primary" if current_theme == "light" else "secondary",
            key="theme_light_button",
            disabled=bool(st.session_state.get("is_loading", False)),
        )

    if dark_clicked and current_theme != "dark":
        st.session_state["theme"] = "dark"
        st.rerun()
    if light_clicked and current_theme != "light":
        st.session_state["theme"] = "light"
        st.rerun()


def controls_disabled() -> bool:
    return bool(st.session_state.get("is_loading", False))


@contextmanager
def show_loading(message: str) -> Iterator[None]:
    st.session_state["is_loading"] = True
    try:
        with st.spinner(message):
            yield
    finally:
        st.session_state["is_loading"] = False


def render_page_header(title: str, subtitle: str) -> None:
    st.title(title)
    st.markdown(f"<div class='sms-page-subtitle'>{subtitle}</div>", unsafe_allow_html=True)
    st.divider()


@contextmanager
def card(title: str = "", subtitle: str = "") -> Iterator[None]:
    with st.container(border=True):
        if title:
            st.markdown(f"#### {title}")
        if subtitle:
            st.caption(subtitle)
        yield


def loading_button_label(base_label: str, loading_label: str) -> Tuple[str, bool]:
    if controls_disabled():
        return loading_label, True
    return base_label, False
