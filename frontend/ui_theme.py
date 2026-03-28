from __future__ import annotations

import importlib
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Tuple

import altair as alt
import streamlit as st

_PLOTLY_IO: Any = None

LIGHT_THEME: Dict[str, str] = {
    "primaryColor": "#b77942",
    "backgroundColor": "#f7f3eb",
    "secondaryBackgroundColor": "#efe5d5",
    "cardColor": "#fffaf2",
    "textColor": "#2f241a",
    "mutedText": "#6e5a46",
    "cardBorder": "#d8c3a8",
    "sidebarBg": "#efe5d5",
    "sidebarText": "#2f241a",
    "buttonBg": "#b77942",
    "buttonText": "#fffaf2",
    "buttonDisabledBg": "#ddccb6",
    "buttonDisabledText": "#6e5a46",
    "sidebarActiveBg": "#dfc5a8",
    "sidebarActiveText": "#2f241a",
    "sidebarInactiveBg": "transparent",
    "chartGrid": "#d8c3a8",
    "chartPrimary": "#b77942",
}

DARK_THEME: Dict[str, str] = {
    "primaryColor": "#615fff",
    "backgroundColor": "#1d293d",
    "secondaryBackgroundColor": "#0f172b",
    "cardColor": "#162238",
    "textColor": "#e2e8f0",
    "mutedText": "#a7b4c9",
    "cardBorder": "#2b3a56",
    "sidebarBg": "#0f172b",
    "sidebarText": "#e2e8f0",
    "buttonBg": "#615fff",
    "buttonText": "#e2e8f0",
    "buttonDisabledBg": "#2b3a56",
    "buttonDisabledText": "#8ea1be",
    "sidebarActiveBg": "#1f2c46",
    "sidebarActiveText": "#e2e8f0",
    "sidebarInactiveBg": "transparent",
    "chartGrid": "#2b3a56",
    "chartPrimary": "#8a87ff",
}


def ensure_page_config() -> None:
    try:
        st.set_page_config(
            layout="wide",
            page_title="School Management System",
            page_icon="🎓",
        )
    except Exception:
        # Streamlit allows set_page_config only once per app run.
        pass


def init_ui_state() -> None:
    if "theme" not in st.session_state:
        st.session_state["theme"] = "dark"
    if "is_loading" not in st.session_state:
        st.session_state["is_loading"] = False


def current_theme_name() -> str:
    return str(st.session_state.get("theme", "dark")).strip().lower() or "dark"


def current_theme_tokens() -> Dict[str, str]:
    return DARK_THEME if current_theme_name() == "dark" else LIGHT_THEME


def pill_select(
    label: str,
    options: List[str],
    key: str,
    default_index: int = 0,
    disabled: bool = False,
) -> str:
    if not options:
        return ""

    safe_default_index = max(0, min(default_index, len(options) - 1))
    default_option = options[safe_default_index]

    if hasattr(st, "pills"):
        selected = st.pills(
            label,
            options=options,
            default=default_option,
            key=key,
            disabled=disabled,
        )
        return str(selected)

    return str(
        st.selectbox(
            label,
            options,
            index=safe_default_index,
            key=key,
            disabled=disabled,
        )
    )


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
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');

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

    html, body, [class*="css"], .stApp {{
        font-family: 'Space Grotesk', sans-serif !important;
    }}

    body {{
        color: var(--sms-text) !important;
        background-color: var(--sms-bg) !important;
    }}

    .stApp, [data-testid="stAppViewContainer"] > .main {{
        background: var(--sms-bg) !important;
        color: var(--sms-text) !important;
    }}

    header[data-testid="stHeader"] {{
        background: var(--sms-surface) !important;
        border-bottom: 1px solid var(--sms-border) !important;
    }}

    [data-testid="stToolbar"] button,
    [data-testid="stToolbar"] svg,
    [data-testid="stStatusWidget"] *,
    [data-testid="stMainMenu"] * {{
        color: var(--sms-text) !important;
        fill: var(--sms-text) !important;
    }}

    [data-testid="stSidebar"],
    section[data-testid="stSidebar"] {{
        background: var(--sms-sidebar) !important;
        border-right: 1px solid var(--sms-border) !important;
        color: var(--sms-sidebar-text) !important;
    }}

    section[data-testid="stSidebar"] * {{
        color: var(--sms-sidebar-text) !important;
    }}

    .stMarkdown, .stText, .stCaption, .stAlert, p, span, label, h1, h2, h3, h4, h5, h6 {{
        color: inherit !important;
    }}

    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stDataFrame"],
    div[data-testid="stTable"] {{
        background: var(--sms-card) !important;
        border: 1px solid var(--sms-border) !important;
        border-radius: 14px !important;
        color: var(--sms-text) !important;
    }}

    div[data-testid="stDataFrame"] {{
        --gdg-bg-cell: var(--sms-card) !important;
        --gdg-bg-header: var(--sms-surface) !important;
        --gdg-bg-header-has-focus: var(--sms-surface) !important;
        --gdg-bg-cell-medium: var(--sms-card) !important;
        --gdg-bg-cell-even: var(--sms-card) !important;
        --gdg-text-dark: var(--sms-text) !important;
        --gdg-text-medium: var(--sms-text) !important;
        --gdg-text-header: var(--sms-text) !important;
        --gdg-border-color: var(--sms-border) !important;
        --gdg-accent-color: var(--sms-primary) !important;
    }}

    div[data-testid="stDataFrame"] * {{
        color: var(--sms-text) !important;
        border-color: var(--sms-border) !important;
    }}

    div[data-testid="stTable"] table,
    div[data-testid="stTable"] th,
    div[data-testid="stTable"] td {{
        background: var(--sms-card) !important;
        color: var(--sms-text) !important;
        border-color: var(--sms-border) !important;
    }}

    div[data-testid="stTable"] th {{
        background: var(--sms-surface) !important;
    }}

    div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
    div[data-testid="stMultiSelect"] [data-baseweb="select"] > div,
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stTextArea"] textarea {{
        background: var(--sms-card) !important;
        color: var(--sms-text) !important;
        border: 1px solid var(--sms-border) !important;
        border-radius: 10px !important;
    }}

    div[data-testid="stSelectbox"] [data-baseweb="select"] *,
    div[data-testid="stMultiSelect"] [data-baseweb="select"] *,
    div[data-testid="stTextInput"] input::placeholder,
    div[data-testid="stNumberInput"] input::placeholder,
    div[data-testid="stDateInput"] input::placeholder,
    div[data-testid="stTextArea"] textarea::placeholder {{
        color: var(--sms-muted) !important;
        fill: var(--sms-muted) !important;
    }}

    [data-baseweb="popover"],
    [data-baseweb="menu"],
    div[role="listbox"] {{
        background: var(--sms-card) !important;
        color: var(--sms-text) !important;
        border: 1px solid var(--sms-border) !important;
    }}

    div[role="option"] {{
        color: var(--sms-text) !important;
        background: var(--sms-card) !important;
    }}

    div[role="option"][aria-selected="true"],
    div[role="option"]:hover {{
        background: color-mix(in srgb, var(--sms-primary) 14%, var(--sms-card)) !important;
    }}

    div[data-testid="stButton"] > button,
    div[data-testid="stDownloadButton"] > button,
    div[data-testid="stFormSubmitButton"] > button {{
        width: 100%;
        border-radius: 10px;
        border: 1px solid var(--sms-border);
        background: var(--sms-button-bg) !important;
        color: var(--sms-button-text) !important;
        transition: all 0.15s ease;
    }}

    div[data-testid="stButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {{
        border-color: var(--sms-primary) !important;
        box-shadow: 0 8px 20px color-mix(in srgb, var(--sms-primary) 28%, transparent);
    }}

    div[data-testid="stButton"] > button:disabled,
    div[data-testid="stDownloadButton"] > button:disabled,
    div[data-testid="stFormSubmitButton"] > button:disabled {{
        background: var(--sms-button-disabled-bg) !important;
        color: var(--sms-button-disabled-text) !important;
        border-color: var(--sms-border) !important;
        opacity: 1 !important;
    }}

    [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {{
        background: var(--sms-sidebar-active-bg) !important;
        color: var(--sms-sidebar-active-text) !important;
    }}

    [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {{
        background: var(--sms-sidebar-inactive-bg) !important;
        color: var(--sms-sidebar-text) !important;
    }}

    .sms-page-subtitle {{
        color: var(--sms-muted) !important;
        margin-top: -0.2rem;
        margin-bottom: 0.6rem;
    }}

    .sms-sidebar-section {{
        margin-top: 0.75rem;
        margin-bottom: 0.5rem;
        color: var(--sms-muted) !important;
        font-size: 0.82rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
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
            "Dark",
            type="primary" if current_theme == "dark" else "secondary",
            key="theme_dark_button",
            disabled=bool(st.session_state.get("is_loading", False)),
        )
    with col2:
        light_clicked = st.button(
            "Light",
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
    st.markdown(f"# 🎓 {title}")
    st.markdown(f"<div class='sms-page-subtitle'>{subtitle}</div>", unsafe_allow_html=True)
    st.divider()


@contextmanager
def card(title: str = "", subtitle: str = "") -> Iterator[None]:
    try:
        container = st.container(border=True, height="stretch")
    except Exception:
        container = st.container(border=True)

    with container:
        if title:
            st.markdown(f"#### {title}")
        if subtitle:
            st.caption(subtitle)
        yield


def loading_button_label(base_label: str, loading_label: str) -> Tuple[str, bool]:
    if controls_disabled():
        return loading_label, True
    return base_label, False
