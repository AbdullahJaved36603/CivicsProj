import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from google_sheets_controller import (
    get_session_folder_id,
    list_principals,
    list_school_records,
    list_school_sheet_records,
)
from principal_manager import assign_school_to_principal, create_principal, deassign_school_from_principal, view_principal_assignments
from school_analytics import (
    clear_analytics_cache,
    build_session_analytics_cache,
    get_request_stats,
    get_school_class_subject_analytics,
    get_school_month_class_analytics,
    get_school_overview_analytics,
    get_school_subject_analytics,
    get_system_wide_school_subject_analytics,
    list_available_months,
    list_class_tabs,
    reset_request_stats,
)
from school_manager import create_school, create_school_in_all_sessions, delete_school
from session_manager import create_session, delete_session, list_sessions


# ──────────────────────────────────────────────────────
#  Theme System
# ──────────────────────────────────────────────────────

THEME_PRESETS = {
    "Light": {
        "bg": "#f0f2f6",
        "surface": "#ffffff",
        "surface_alt": "#f8f9fc",
        "text": "#1a1a2e",
        "muted": "#6b7280",
        "primary": "#6366f1",
        "accent": "#06b6d4",
        "success": "#10b981",
        "danger": "#ef4444",
        "warning": "#f59e0b",
        "border": "rgba(99,102,241,0.12)",
        "control_bg": "#f8f9fc",
        "card_shadow": "0 8px 32px rgba(99,102,241,0.10)",
        "glass_bg": "rgba(255,255,255,0.72)",
        "glass_border": "rgba(255,255,255,0.45)",
        "glow_primary": "rgba(99,102,241,0.30)",
        "glow_accent": "rgba(6,182,212,0.25)",
        "gradient_start": "#6366f1",
        "gradient_mid": "#a855f7",
        "gradient_end": "#06b6d4",
        "metric_green": "linear-gradient(135deg, #10b981, #34d399)",
        "metric_blue": "linear-gradient(135deg, #6366f1, #818cf8)",
        "metric_amber": "linear-gradient(135deg, #f59e0b, #fbbf24)",
        "metric_rose": "linear-gradient(135deg, #f43f5e, #fb7185)",
        "metric_cyan": "linear-gradient(135deg, #06b6d4, #22d3ee)",
        "metric_violet": "linear-gradient(135deg, #8b5cf6, #a78bfa)",
        "danger_bg": "rgba(239,68,68,0.05)",
        "danger_border": "rgba(239,68,68,0.18)",
    },
    "Dark": {
        "bg": "#050510",
        "surface": "#0f0f23",
        "surface_alt": "#16213e",
        "text": "#eaeaff",
        "muted": "#9ca3af",
        "primary": "#818cf8",
        "accent": "#22d3ee",
        "success": "#34d399",
        "danger": "#f87171",
        "warning": "#fbbf24",
        "border": "rgba(129,140,248,0.18)",
        "control_bg": "rgba(22,33,62,0.7)",
        "card_shadow": "0 8px 32px rgba(0,0,0,0.45)",
        "glass_bg": "rgba(15,15,35,0.72)",
        "glass_border": "rgba(129,140,248,0.14)",
        "glow_primary": "rgba(129,140,248,0.25)",
        "glow_accent": "rgba(34,211,238,0.20)",
        "gradient_start": "#818cf8",
        "gradient_mid": "#c084fc",
        "gradient_end": "#22d3ee",
        "metric_green": "linear-gradient(135deg, #059669, #34d399)",
        "metric_blue": "linear-gradient(135deg, #4f46e5, #818cf8)",
        "metric_amber": "linear-gradient(135deg, #d97706, #fbbf24)",
        "metric_rose": "linear-gradient(135deg, #e11d48, #fb7185)",
        "metric_cyan": "linear-gradient(135deg, #0891b2, #22d3ee)",
        "metric_violet": "linear-gradient(135deg, #7c3aed, #a78bfa)",
        "danger_bg": "rgba(248,113,113,0.06)",
        "danger_border": "rgba(248,113,113,0.18)",
    },
}


def _is_dark() -> bool:
    return st.session_state.get("admin_theme", "Dark") == "Dark"


# ──────────────────────────────────────────────────────
#  Cached helpers
# ──────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _cached_validate_user(username: str, password: str):
    from google_sheets_controller import validate_user
    return validate_user(username, password)


@st.cache_data(ttl=300)
def _cached_sessions():
    return list_sessions()


@st.cache_data(ttl=300)
def _cached_school_records():
    return list_school_records(active_only=True)


@st.cache_data(ttl=300)
def _cached_school_mappings(session_name: str):
    return list_school_sheet_records(session_name=session_name or None, active_only=True)


@st.cache_data(ttl=300)
def _cached_principals():
    return list_principals()


@st.cache_data(ttl=900)
def _cached_session_analytics_payload(session_name: str):
    clear_analytics_cache()
    reset_request_stats()
    data = build_session_analytics_cache(session_name)
    stats = get_request_stats()
    return {"data": data, "stats": stats}


def _clear_admin_data_cache() -> None:
    _cached_sessions.clear()
    _cached_school_records.clear()
    _cached_school_mappings.clear()
    _cached_principals.clear()


# ──────────────────────────────────────────────────────
#  Theme CSS — Futuristic
# ──────────────────────────────────────────────────────

def _apply_admin_theme(theme_name: str) -> None:
    theme = THEME_PRESETS.get(theme_name, THEME_PRESETS["Light"])
    is_dark = theme_name == "Dark"
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

        /* ─── Keyframes ─────────────────────────────── */
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(30px) scale(0.97); }}
            to   {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}
        @keyframes slideInRight {{
            from {{ opacity: 0; transform: translateX(-20px); }}
            to   {{ opacity: 1; transform: translateX(0); }}
        }}
        @keyframes shimmerBar {{
            0%   {{ background-position: -300% center; }}
            100% {{ background-position: 300% center; }}
        }}
        @keyframes gradientRotate {{
            0%   {{ background-position: 0% 50%; }}
            50%  {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        @keyframes glowPulse {{
            0%, 100% {{ box-shadow: 0 0 20px {theme['glow_primary']}; }}
            50%      {{ box-shadow: 0 0 40px {theme['glow_accent']}; }}
        }}
        @keyframes countUp {{
            from {{ opacity: 0; transform: translateY(12px) scale(0.9); }}
            to   {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}
        @keyframes borderShimmer {{
            0%   {{ border-color: {theme['gradient_start']}30; }}
            50%  {{ border-color: {theme['gradient_end']}30; }}
            100% {{ border-color: {theme['gradient_start']}30; }}
        }}
        @keyframes scaleIn {{
            from {{ opacity: 0; transform: scale(0.92); }}
            to   {{ opacity: 1; transform: scale(1); }}
        }}

        /* ─── Global ────────────────────────────────── */
        *, *::before, *::after {{ box-sizing: border-box; }}
        .stApp {{
            background: {theme['bg']};
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: {theme['text']};
        }}
        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            animation: fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        /* ─── Sidebar ───────────────────────────────── */
        [data-testid="stSidebar"] {{
            background: {theme['surface']} !important;
            border-right: 1px solid {theme['border']} !important;
        }}
        [data-testid="stSidebar"]::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']});
            background-size: 300% 100%;
            animation: shimmerBar 4s linear infinite;
        }}
        [data-testid="stSidebar"] * {{
            color: {theme['text']} !important;
            font-family: 'Inter', sans-serif !important;
        }}

        /* ─── Dashboard Hero ────────────────────────── */
        .dash-hero {{
            background: {theme['glass_bg']};
            backdrop-filter: blur(24px) saturate(200%);
            border: 1.5px solid {theme['glass_border']};
            border-radius: 24px;
            padding: 2rem 2.2rem;
            box-shadow: {theme['card_shadow']};
            animation: fadeInUp 0.7s cubic-bezier(0.16, 1, 0.3, 1),
                       borderShimmer 6s ease-in-out infinite;
            position: relative;
            overflow: hidden;
            margin-bottom: 1.5rem;
        }}
        .dash-hero::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']}, {theme['gradient_start']});
            background-size: 300% 100%;
            animation: shimmerBar 3s linear infinite;
        }}
        .dash-hero::after {{
            content: '';
            position: absolute;
            top: -40px; right: -40px;
            width: 220px; height: 220px;
            background: radial-gradient(circle, {theme['gradient_end']}12, transparent 70%);
            pointer-events: none;
        }}
        .dash-hero-row {{
            display: flex;
            align-items: center;
            gap: 1.2rem;
        }}
        .dash-hero-icon {{
            width: 60px; height: 60px;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']});
            background-size: 200% 200%;
            animation: gradientRotate 4s ease infinite;
            border-radius: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.7rem;
            color: white;
            box-shadow: 0 8px 28px {theme['glow_primary']};
            flex-shrink: 0;
        }}
        .dash-hero h2 {{
            margin: 0;
            font-size: 1.65rem;
            font-weight: 900;
            letter-spacing: -0.04em;
            color: {theme['text']};
        }}
        .dash-hero-sub {{
            color: {theme['muted']};
            font-size: 0.9rem;
            margin-top: 0.2rem;
            line-height: 1.6;
        }}
        .dash-hero-badge {{
            display: inline-block;
            margin-top: 0.8rem;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']});
            background-size: 200% 200%;
            animation: gradientRotate 4s ease infinite;
            color: white;
            border-radius: 999px;
            padding: 0.3rem 1rem;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            box-shadow: 0 4px 16px {theme['glow_primary']};
        }}

        /* ─── Metric Cards ──────────────────────────── */
        .metric-card {{
            background: {theme['glass_bg']};
            backdrop-filter: blur(20px);
            border: 1.5px solid {theme['glass_border']};
            border-radius: 20px;
            padding: 1.4rem 1.5rem;
            box-shadow: {theme['card_shadow']};
            animation: fadeInUp 0.7s cubic-bezier(0.16, 1, 0.3, 1);
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            overflow: hidden;
        }}
        .metric-card::after {{
            content: '';
            position: absolute;
            top: -50%; right: -50%;
            width: 100%; height: 100%;
            background: radial-gradient(circle, {theme['gradient_end']}08, transparent 70%);
            pointer-events: none;
            transition: all 0.4s ease;
        }}
        .metric-card:hover {{
            transform: translateY(-6px) scale(1.02);
            box-shadow: 0 16px 48px {theme['glow_primary']},
                        0 0 0 1px {theme['gradient_start']}30;
        }}
        .metric-card:hover::after {{
            background: radial-gradient(circle, {theme['gradient_end']}15, transparent 70%);
        }}
        .metric-card .mc-icon {{
            width: 46px; height: 46px;
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.35rem;
            color: white;
            margin-bottom: 0.9rem;
            box-shadow: 0 4px 14px rgba(0,0,0,0.15);
        }}
        .metric-card .mc-label {{
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: {theme['muted']};
            margin-bottom: 0.25rem;
        }}
        .metric-card .mc-value {{
            font-size: 2rem;
            font-weight: 900;
            letter-spacing: -0.04em;
            color: {theme['text']};
            animation: countUp 0.8s cubic-bezier(0.16,1,0.3,1);
        }}

        /* ─── Section Headers ───────────────────────── */
        .section-header {{
            display: flex;
            align-items: center;
            gap: 0.7rem;
            margin: 2rem 0 1.2rem;
            animation: slideInRight 0.6s cubic-bezier(0.16,1,0.3,1);
        }}
        .section-header .sh-icon {{
            width: 40px; height: 40px;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_end']});
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.15rem;
            color: white;
            box-shadow: 0 4px 16px {theme['glow_primary']};
        }}
        .section-header h3 {{
            margin: 0;
            font-size: 1.3rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            color: {theme['text']};
        }}

        /* ─── Info Banner ───────────────────────────── */
        .info-banner {{
            background: {theme['glass_bg']};
            backdrop-filter: blur(16px);
            border: 1px solid {theme['glass_border']};
            border-radius: 16px;
            padding: 1rem 1.3rem;
            font-size: 0.88rem;
            color: {theme['muted']};
            display: flex;
            align-items: center;
            gap: 0.6rem;
            animation: fadeInUp 0.8s ease;
            margin-top: 1rem;
        }}

        /* ─── Cards / Panels ────────────────────────── */
        .ui-panel {{
            background: {theme['glass_bg']};
            backdrop-filter: blur(20px);
            border: 1.5px solid {theme['glass_border']};
            border-radius: 20px;
            padding: 1.6rem;
            box-shadow: {theme['card_shadow']};
            animation: fadeInUp 0.6s ease;
            margin-bottom: 1rem;
        }}
        .ui-panel h4 {{
            margin: 0 0 0.8rem;
            font-size: 1.05rem;
            font-weight: 800;
            color: {theme['text']};
            letter-spacing: -0.02em;
        }}

        /* ─── Danger zone ───────────────────────────── */
        .danger-panel {{
            background: {theme['danger_bg']};
            border: 1.5px solid {theme['danger_border']};
            border-radius: 18px;
            padding: 1.3rem 1.5rem;
            animation: fadeInUp 0.7s ease;
            position: relative;
            overflow: hidden;
        }}
        .danger-panel::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, {theme['danger']}, #fbbf24, {theme['danger']});
            background-size: 200% 100%;
            animation: shimmerBar 3s linear infinite;
        }}
        .danger-panel h5 {{
            margin: 0 0 0.7rem;
            color: {theme['danger']};
            font-size: 0.88rem;
            font-weight: 800;
            letter-spacing: 0.02em;
        }}

        /* ─── Form Controls ─────────────────────────── */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input,
        .stDateInput input,
        .stTimeInput input,
        .stSelectbox [data-baseweb="select"] > div,
        .stMultiSelect [data-baseweb="select"] > div,
        .stRadio [role="radiogroup"],
        .stDataFrame {{
            background: {theme['control_bg']} !important;
            color: {theme['text']} !important;
            border: 1.5px solid {theme['border']} !important;
            border-radius: 14px !important;
            font-family: 'Inter', sans-serif !important;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }}
        .stTextInput input:focus,
        .stTextArea textarea:focus {{
            border-color: {theme['primary']} !important;
            box-shadow: 0 0 0 4px {theme['glow_primary']},
                        0 0 20px {theme['glow_primary']} !important;
        }}
        div[data-baseweb="select"] * {{
            color: {theme['text']} !important;
        }}
        .stTextInput label, .stSelectbox label, .stMultiSelect label, .stRadio label,
        .stTextArea label, .stNumberInput label, .stCheckbox label {{
            font-weight: 700 !important;
            font-size: 0.78rem !important;
            letter-spacing: 0.05em !important;
            color: {theme['muted']} !important;
            text-transform: uppercase !important;
        }}

        /* ─── FUTURISTIC BUTTONS ────────────────────── */
        .stButton > button,
        .stDownloadButton > button,
        .stForm button {{
            border-radius: 14px !important;
            border: none !important;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']}) !important;
            background-size: 200% 200% !important;
            animation: gradientRotate 4s ease infinite !important;
            color: #ffffff !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 700 !important;
            font-size: 0.92rem !important;
            letter-spacing: 0.03em !important;
            padding: 0.7rem 1.4rem !important;
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1) !important;
            box-shadow: 0 6px 20px {theme['glow_primary']} !important;
            position: relative;
            overflow: hidden;
        }}
        .stButton > button::before,
        .stDownloadButton > button::before,
        .stForm button::before {{
            content: '';
            position: absolute;
            top: 50%; left: 50%;
            width: 0; height: 0;
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            transform: translate(-50%, -50%);
            transition: width 0.5s ease, height 0.5s ease;
        }}
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stForm button:hover {{
            transform: translateY(-3px) scale(1.02) !important;
            box-shadow: 0 12px 36px {theme['glow_primary']},
                        0 0 50px {theme['glow_accent']} !important;
            filter: brightness(1.08) !important;
        }}
        .stButton > button:hover::before,
        .stDownloadButton > button:hover::before,
        .stForm button:hover::before {{
            width: 300px; height: 300px;
        }}
        .stButton > button:active,
        .stDownloadButton > button:active,
        .stForm button:active {{
            transform: translateY(0) scale(0.98) !important;
        }}

        /* ─── DataFrames ────────────────────────────── */
        .stDataFrame {{
            border-radius: 16px !important;
            overflow: hidden;
        }}

        /* ─── Typography ────────────────────────────── */
        .stMarkdown, .stCaption, .stMetricLabel, .stMetricValue {{
            color: {theme['text']} !important;
            font-family: 'Inter', sans-serif !important;
        }}
        h1, h2, h3, h4 {{
            font-family: 'Inter', sans-serif !important;
            letter-spacing: -0.03em !important;
        }}

        /* ─── Alerts ────────────────────────────────── */
        .stAlert {{
            border-radius: 16px !important;
            border: none !important;
            animation: fadeInUp 0.4s ease !important;
        }}

        /* ─── Expander ──────────────────────────────── */
        .streamlit-expanderHeader {{
            font-family: 'Inter', sans-serif !important;
            font-weight: 700 !important;
            border-radius: 14px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────
#  Admin Home
# ──────────────────────────────────────────────────────

def _render_admin_home(username: str) -> None:
    sessions_count = len(_cached_sessions())
    schools_count = len(_cached_school_records())
    principals_count = len(_cached_principals())

    theme = THEME_PRESETS.get(
        st.session_state.get("admin_theme", "Dark"),
        THEME_PRESETS["Dark"],
    )

    st.markdown(
        f"""
        <div class="dash-hero">
            <div class="dash-hero-row">
                <div class="dash-hero-icon">⚡</div>
                <div>
                    <h2>Welcome back, {username}</h2>
                    <p class="dash-hero-sub">Your command center for managing sessions, schools, principals, and analytics.</p>
                </div>
            </div>
            <span class="dash-hero-badge">Admin Control Center</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="mc-icon" style="background: {theme['metric_blue']};">📅</div>
                <div class="mc-label">Active Sessions</div>
                <div class="mc-value">{sessions_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="mc-icon" style="background: {theme['metric_green']};">🏫</div>
                <div class="mc-label">Active Schools</div>
                <div class="mc-value">{schools_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="mc-icon" style="background: {theme['metric_violet']};">👤</div>
                <div class="mc-label">Principals</div>
                <div class="mc-value">{principals_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="info-banner">
            <span style="font-size:1.1rem">💡</span>
            <span>Use the sidebar to navigate between <b>Sessions</b>, <b>Schools</b>, <b>Principals</b>, and <b>Analytics</b>.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────
#  Admin Login (standalone)
# ──────────────────────────────────────────────────────

def _admin_login() -> bool:
    st.title("System Administration Dashboard")
    with st.form("admin_login"):
        username = st.text_input("Admin Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        role = _cached_validate_user(username, password)
        if role == "admin":
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["role"] = role
            st.success("Admin login successful")
            return True
        st.error("Invalid credentials or non-admin account")

    return st.session_state.get("logged_in", False) and st.session_state.get("role") == "admin"


# ──────────────────────────────────────────────────────
#  Session Management
# ──────────────────────────────────────────────────────

def _session_section() -> None:
    st.markdown(
        """
        <div class="section-header">
            <div class="sh-icon">📅</div>
            <h3>Session Management</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="ui-panel"><h4>➕ Create New Session</h4>', unsafe_allow_html=True)
        with st.form("create_session_form"):
            new_session = st.text_input("SESSION NAME", placeholder="e.g. 26-27")
            init_existing = st.checkbox("Initialize sheets for existing schools", value=True)
            init_editor = st.text_input("DEFAULT EDITOR EMAIL (optional)")
            create_btn = st.form_submit_button("Create Session")
        st.markdown("</div>", unsafe_allow_html=True)

        if create_btn:
            if not new_session.strip():
                st.error("❌ Please enter a session name before creating")
            else:
                folder_id = create_session(
                    new_session,
                    initialize_existing_schools=init_existing,
                    default_editor_email=init_editor,
                )
                if folder_id:
                    _clear_admin_data_cache()
                    _cached_session_analytics_payload.clear()
                    st.success(f"✅ Session created! Folder ID: {folder_id}")
                else:
                    st.error("❌ Session creation failed")

    with col2:
        st.markdown('<div class="danger-panel"><h5>⚠️ Delete Session</h5>', unsafe_allow_html=True)
        sessions = _cached_sessions()
        session_to_delete = st.selectbox("Select session to delete", [""] + sessions)
        confirm_session_delete = st.checkbox("I confirm deleting this session")
        if st.button("🗑️ Delete Session", use_container_width=True):
            if not session_to_delete:
                st.error("❌ Please select a session to delete")
            elif not confirm_session_delete:
                st.error("⚠️ Please confirm session deletion")
            elif delete_session(session_to_delete):
                _clear_admin_data_cache()
                _cached_session_analytics_payload.clear()
                st.success("✅ Session deleted (or deactivated)")
            else:
                st.error("❌ Session deletion failed")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="section-header" style="margin-top:1rem;">
            <div class="sh-icon">📋</div>
            <h3>Active Sessions</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    sessions = _cached_sessions()
    if sessions:
        st.dataframe(pd.DataFrame({"session_name": sessions}), use_container_width=True)
    else:
        st.info("📭 No active sessions found")


# ──────────────────────────────────────────────────────
#  School Management
# ──────────────────────────────────────────────────────

def _school_section() -> None:
    st.markdown(
        """
        <div class="section-header">
            <div class="sh-icon">🏫</div>
            <h3>School Management</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("📧 Editor email: `test-368@sheettest-490119.iam.gserviceaccount.com`")

    sessions = _cached_sessions()
    selected_session = st.selectbox("📅 SESSION", [""] + sessions, key="school_session")
    folder_id = get_session_folder_id(selected_session) if selected_session else ""

    st.markdown('<div class="ui-panel"><h4>➕ Add New School</h4>', unsafe_allow_html=True)
    with st.form("create_school_form"):
        school_name = st.text_input("SCHOOL NAME", placeholder="Enter school name")
        create_in_all = st.checkbox("Create in all active sessions", value=False)
        create_school_btn = st.form_submit_button("Add School")
    st.markdown("</div>", unsafe_allow_html=True)

    if create_school_btn:
        if not school_name.strip():
            st.error("❌ Please enter a school name")
            return
        if create_in_all:
            results = create_school_in_all_sessions(school_name, "")
            if results:
                _clear_admin_data_cache()
                st.success(f"✅ School created in sessions: {', '.join(results.keys())}")
            else:
                st.error("❌ School creation failed in all sessions")
        else:
            if not folder_id:
                st.error("⚠️ Select a session first")
            else:
                sheet_url = create_school(school_name, folder_id, "")
                if sheet_url:
                    _clear_admin_data_cache()
                    st.success(f"✅ School sheet created!")
                else:
                    st.error("❌ School creation failed")

    st.markdown('<div class="danger-panel"><h5>⚠️ Delete School</h5>', unsafe_allow_html=True)
    schools = [r["school_name"] for r in _cached_school_records()]
    school_to_delete = st.selectbox("Select school to delete", [""] + schools)
    confirm_school_delete = st.checkbox("I confirm deleting this school")
    if st.button("🗑️ Delete School", use_container_width=True):
        if not school_to_delete:
            st.error("❌ Please select a school to delete")
        elif not confirm_school_delete:
            st.error("⚠️ Please confirm school deletion")
        elif delete_school(school_to_delete):
            _clear_admin_data_cache()
            st.success("✅ School deleted (deactivated)")
        else:
            st.error("❌ School delete failed")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="section-header" style="margin-top:1rem;">
            <div class="sh-icon">📋</div>
            <h3>School-Session Mappings</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    mappings = _cached_school_mappings(selected_session)
    if mappings:
        st.dataframe(pd.DataFrame(mappings), use_container_width=True)
    else:
        st.info("📭 No mappings found")


# ──────────────────────────────────────────────────────
#  Principal Management
# ──────────────────────────────────────────────────────

def _principal_section() -> None:
    st.markdown(
        """
        <div class="section-header">
            <div class="sh-icon">👤</div>
            <h3>Principal Management</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    schools = [r["school_name"] for r in _cached_school_records()]
    principals = _cached_principals()

    st.markdown('<div class="ui-panel"><h4>➕ Create or Update Principal</h4>', unsafe_allow_html=True)
    with st.form("create_principal_form"):
        username = st.text_input("PRINCIPAL USERNAME", placeholder="Enter username")
        password = st.text_input("PRINCIPAL PASSWORD", type="password")
        assigned_schools = st.multiselect("ASSIGNED SCHOOLS", schools)
        create_btn = st.form_submit_button("Create / Update Principal")
    st.markdown("</div>", unsafe_allow_html=True)

    if create_btn:
        if not username.strip() or not password:
            st.error("❌ Principal username and password are required")
        elif create_principal(username, password, assigned_schools):
            _clear_admin_data_cache()
            st.success("✅ Principal created/updated successfully!")
        else:
            st.error("❌ Principal create/update failed")

    st.markdown(
        """
        <div class="section-header" style="margin-top: 1.2rem;">
            <div class="sh-icon">🔗</div>
            <h3>School Assignments</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        selected_principal = st.selectbox("PRINCIPAL", [""] + principals)
    with col_sel2:
        selected_school = st.selectbox("SCHOOL TO ASSIGN", [""] + schools)

    col_assign, col_deassign = st.columns(2)
    with col_assign:
        assign_clicked = st.button("➕ Assign School", use_container_width=True)
    with col_deassign:
        deassign_clicked = st.button("➖ Deassign School", use_container_width=True)

    if assign_clicked:
        if not selected_principal:
            st.error("❌ Please select a principal")
        elif not selected_school:
            st.error("❌ Please select a school")
        elif assign_school_to_principal(selected_principal, selected_school):
            _clear_admin_data_cache()
            st.success("✅ School assigned successfully!")
        else:
            st.error("❌ Assignment failed")

    if deassign_clicked:
        if not selected_principal:
            st.error("❌ Please select a principal")
        elif not selected_school:
            st.error("❌ Please select a school")
        elif deassign_school_from_principal(selected_principal, selected_school):
            _clear_admin_data_cache()
            st.success("✅ School deassigned successfully!")
        else:
            st.error("❌ Deassignment failed")

    st.markdown(
        """
        <div class="section-header" style="margin-top:1rem;">
            <div class="sh-icon">📋</div>
            <h3>Current Assignments</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    assignments = view_principal_assignments()
    rows = [{"principal": p, "schools": ", ".join(s)} for p, s in assignments.items()]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("📭 No principal assignments found")


# ──────────────────────────────────────────────────────
#  Analytics
# ──────────────────────────────────────────────────────

def _analytics_section() -> None:
    st.markdown(
        """
        <div class="section-header">
            <div class="sh-icon">📊</div>
            <h3>Analytics Overview</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sessions = _cached_sessions()
    if not sessions:
        st.info("📭 No active sessions found")
        return

    selected_session = st.selectbox("📅 ANALYTICS SESSION", sessions, key="analytics_session")

    col_cache_1, col_cache_2 = st.columns(2)
    with col_cache_1:
        if st.button("🔄 Load / Refresh Data", use_container_width=True):
            _cached_session_analytics_payload.clear()
            st.success("✅ Session analytics cache loaded")
    with col_cache_2:
        if st.button("🧹 Clear Local Cache", use_container_width=True):
            clear_analytics_cache()
            _cached_session_analytics_payload.clear()
            st.success("✅ Local analytics cache cleared")

    analytics_payload = _cached_session_analytics_payload(selected_session)
    cached = analytics_payload.get("data", {})
    if not cached:
        st.info("👆 Click **Load / Refresh Data** before running analytics")
        return

    req_stats = analytics_payload.get("stats", {})
    if req_stats:
        st.caption(
            f"📡 Prefetch → total: {req_stats.get('total', 0)} | tabs: {req_stats.get('tabs', 0)} | read: {req_stats.get('read', 0)}"
        )

    school_entries = cached.get("schools", [])
    if not school_entries:
        st.info("📭 No school sheets found in selected session")
        return

    all_months = cached.get("months", [])
    all_classes = cached.get("classes", [])

    _plotly_template = "plotly_dark" if _is_dark() else "plotly_white"

    # ── System-Wide Analytics ────────────────────────
    st.markdown(
        """
        <div class="section-header" style="margin-top: 1.5rem;">
            <div class="sh-icon">🌐</div>
            <h3>System-Wide Subject Analytics</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sw_col_1, sw_col_2 = st.columns(2)
    with sw_col_1:
        selected_month = st.selectbox("MONTH", all_months if all_months else [""], key="system_month")
    with sw_col_2:
        selected_class = st.selectbox("CLASS", all_classes if all_classes else [""], key="system_class")

    if st.button("🔍 Run System-Wide Analytics", use_container_width=True):
        if not selected_month or not selected_class:
            st.error("❌ Please select both month and class")
        else:
            reset_request_stats()
            subject_result = get_system_wide_school_subject_analytics(
                selected_session,
                selected_month,
                selected_class,
                session_cache=cached,
            )
            action_stats = get_request_stats()
            st.caption(
                f"📡 API → total: {action_stats.get('total', 0)} | tabs: {action_stats.get('tabs', 0)} | read: {action_stats.get('read', 0)}"
            )

            if not subject_result.get("success"):
                st.warning(subject_result.get("message", "No subject data found"))
            else:
                st.caption(
                    f"📊 Schools: {subject_result.get('schools_count', 0)} | Session: {selected_session} | Class: {selected_class} | Month: {selected_month}"
                )

                detail_df = pd.DataFrame(subject_result.get("school_subject_rows", []))
                summary_df = pd.DataFrame(subject_result.get("subject_summary", []))

                st.markdown("#### 📋 School + Subject Detailed")
                if detail_df.empty:
                    st.info("No data for selected month/class")
                else:
                    schools_list = sorted(detail_df["school_name"].unique().tolist())
                    subjects_list = sorted(detail_df["subject"].unique().tolist())

                    fcol1, fcol2 = st.columns(2)
                    with fcol1:
                        selected_schools = st.multiselect(
                            "FILTER SCHOOLS", options=schools_list, default=schools_list, key="sw_filter_schools",
                        )
                    with fcol2:
                        selected_subjects = st.multiselect(
                            "FILTER SUBJECTS", options=subjects_list, default=subjects_list, key="sw_filter_subjects",
                        )

                    filtered_df = detail_df[
                        detail_df["school_name"].isin(selected_schools)
                        & detail_df["subject"].isin(selected_subjects)
                    ].copy()

                    if filtered_df.empty:
                        st.warning("No rows match filters")
                    else:
                        st.dataframe(
                            filtered_df.sort_values(["school_name", "subject"]),
                            use_container_width=True,
                        )

                        by_school_rate = px.bar(
                            filtered_df, x="school_name", y="pass_rate", color="subject",
                            barmode="group", title="Pass Rate (%) by School & Subject",
                            hover_data=["appeared", "passed", "failed", "average"],
                            color_discrete_sequence=px.colors.qualitative.Safe,
                        )
                        by_school_rate.update_layout(
                            template=_plotly_template, height=500, font=dict(family="Inter"),
                            title_font_size=16, margin=dict(t=50, b=40),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            xaxis_title="School", yaxis_title="Pass Rate (%)", legend_title_text="Subject",
                        )
                        st.plotly_chart(by_school_rate, use_container_width=True)

                        by_school_avg = px.bar(
                            filtered_df, x="school_name", y="average", color="subject",
                            barmode="group", title="Average Marks by School & Subject",
                            hover_data=["appeared", "passed", "failed", "pass_rate"],
                            color_discrete_sequence=px.colors.qualitative.Set2,
                        )
                        by_school_avg.update_layout(
                            template=_plotly_template, height=500, font=dict(family="Inter"),
                            title_font_size=16, margin=dict(t=50, b=40),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            xaxis_title="School", yaxis_title="Average Marks", legend_title_text="Subject",
                        )
                        st.plotly_chart(by_school_avg, use_container_width=True)

                        pivot_df = filtered_df.pivot(index="subject", columns="school_name", values="pass_rate")
                        heatmap_fig = px.imshow(
                            pivot_df, text_auto=True, aspect="auto",
                            color_continuous_scale="Viridis" if _is_dark() else "Blues",
                            title="Pass Rate Heatmap (Subject vs School)",
                        )
                        heatmap_fig.update_layout(
                            template=_plotly_template, height=520, font=dict(family="Inter"),
                            title_font_size=16, margin=dict(t=50, b=40),
                            paper_bgcolor="rgba(0,0,0,0)",
                            xaxis_title="School", yaxis_title="Subject",
                        )
                        st.plotly_chart(heatmap_fig, use_container_width=True)

                with st.expander("📊 Combined Subject Summary"):
                    if not summary_df.empty:
                        st.dataframe(summary_df, use_container_width=True)
                    else:
                        st.info("No summary data")

    # ── School Drill-Down ────────────────────────────
    st.markdown(
        """
        <div class="section-header" style="margin-top: 2rem;">
            <div class="sh-icon">🔎</div>
            <h3>School Drill-Down</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    school_options = sorted({e["school_name"] for e in school_entries})
    selected_school = st.selectbox("🏫 SCHOOL", school_options, key="analytics_school")
    selected_entry = next((e for e in school_entries if e["school_name"] == selected_school), None)
    if not selected_entry:
        st.warning("Selected school mapping not found")
        return

    school_url = selected_entry.get("sheet_url", "")
    school_cache = selected_entry.get("cache")
    school_classes = list_class_tabs(school_url, school_cache=school_cache)
    school_months = list_available_months(school_url, school_cache=school_cache)

    col3, col4 = st.columns(2)
    with col3:
        selected_school_month = st.selectbox("MONTH", school_months if school_months else [""], key="school_month")
    with col4:
        selected_school_class = st.selectbox("CLASS", ["All"] + school_classes, key="school_class")

    if st.button("🔍 Run School Analytics", use_container_width=True):
        if not selected_school_month:
            st.error("❌ Please select a month")
            return

        if selected_school_class == "All":
            reset_request_stats()
            class_subject_result = get_school_class_subject_analytics(
                school_url, selected_school_month, school_cache=school_cache,
            )
            action_stats = get_request_stats()
            st.caption(
                f"📡 API → total: {action_stats.get('total', 0)} | tabs: {action_stats.get('tabs', 0)} | read: {action_stats.get('read', 0)}"
            )

            st.markdown("#### 📋 Subject + Class Wise (All Classes)")
            if not class_subject_result.get("success"):
                st.warning(class_subject_result.get("message", "No data"))
            else:
                class_subject_df = pd.DataFrame(class_subject_result.get("class_subject_rows", []))
                st.dataframe(class_subject_df, use_container_width=True)
                if not class_subject_df.empty:
                    fig1 = px.bar(
                        class_subject_df, x="class_name", y="pass_rate", color="subject",
                        barmode="group", title="Class-wise Pass Rate (Subject Breakdown)",
                        hover_data=["appeared", "passed", "failed", "average"],
                        color_discrete_sequence=px.colors.qualitative.Set2,
                    )
                    fig1.update_layout(
                        template=_plotly_template, height=460, font=dict(family="Inter"),
                        title_font_size=16, margin=dict(t=50, b=40),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig1, use_container_width=True)

                    fig2 = px.bar(
                        class_subject_df, x="class_name", y="average", color="subject",
                        barmode="group", title="Class-wise Average Marks (Subject Breakdown)",
                        hover_data=["appeared", "passed", "failed", "pass_rate"],
                        color_discrete_sequence=px.colors.qualitative.Safe,
                    )
                    fig2.update_layout(
                        template=_plotly_template, height=460, font=dict(family="Inter"),
                        title_font_size=16, margin=dict(t=50, b=40),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig2, use_container_width=True)
        else:
            reset_request_stats()
            subject_result = get_school_subject_analytics(
                school_url, selected_school_month,
                class_name=selected_school_class, school_cache=school_cache,
            )
            action_stats = get_request_stats()
            st.caption(
                f"📡 API → total: {action_stats.get('total', 0)} | tabs: {action_stats.get('tabs', 0)} | read: {action_stats.get('read', 0)}"
            )
            st.markdown("#### 📋 Subject-Wise (Selected Class)")
            if not subject_result.get("success"):
                st.warning(subject_result.get("message", "No data"))
            else:
                subject_df = pd.DataFrame(subject_result.get("subject_rows", []))
                st.dataframe(subject_df, use_container_width=True)
                if not subject_df.empty:
                    fig = px.bar(
                        subject_df, x="subject", y=["passed", "failed"],
                        barmode="group", title="Subject-wise Passed vs Failed",
                        color_discrete_sequence=["#818cf8", "#f43f5e"],
                    )
                    fig.update_layout(
                        template=_plotly_template, height=460, font=dict(family="Inter"),
                        title_font_size=16, margin=dict(t=50, b=40),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────
#  Main render
# ──────────────────────────────────────────────────────

def render_admin_dashboard(username: str, show_logout: bool = True) -> None:
    selected_theme = st.session_state.get("admin_theme", "Dark")
    with st.sidebar:
        st.markdown("### 🛡️ Admin Dashboard")
        st.caption(f"Signed in as **{username}**")
        st.markdown("---")

        dark_toggle = st.toggle(
            "🌙 Dark mode",
            value=(selected_theme == "Dark"),
            key="admin_dark_mode",
        )
        st.session_state["admin_theme"] = "Dark" if dark_toggle else "Light"

        st.markdown("---")
        section = st.radio(
            "📍 Navigate",
            [
                "🏠 Home",
                "📅 Sessions",
                "🏫 Schools",
                "👤 Principals",
                "📊 Analytics",
            ],
            key="admin_nav",
        )
        section_clean = section.split(" ", 1)[1] if " " in section else section

        if show_logout:
            st.markdown("---")
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state.clear()
                st.rerun()

    _apply_admin_theme(st.session_state.get("admin_theme", "Dark"))

    if section_clean == "Home":
        _render_admin_home(username)
    elif section_clean == "Sessions":
        _session_section()
    elif section_clean == "Schools":
        _school_section()
    elif section_clean == "Principals":
        _principal_section()
    else:
        _analytics_section()


# ──────────────────────────────────────────────────────
#  Standalone entry point
# ──────────────────────────────────────────────────────

def main() -> None:
    if get_script_run_ctx() is None:
        print("Please run this app with Streamlit:")
        print("streamlit run super_user_dashboard.py")
        return

    st.set_page_config(page_title="Admin Dashboard", page_icon="🛡️", layout="wide")

    if not _admin_login():
        return

    render_admin_dashboard(st.session_state.get("username", ""), show_logout=True)


if __name__ == "__main__":
    main()
