import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from google_sheets_controller import get_user, list_school_sheet_records, validate_user
from principal_manager import create_class
from school_analytics import (
    build_school_analytics_cache,
    get_school_class_subject_analytics,
    get_school_subject_analytics,
    get_request_stats,
    list_available_months,
    list_class_tabs,
    reset_request_stats,
)


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
    },
}


# ──────────────────────────────────────────────────────
#  Cached helpers
# ──────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _cached_validate_user(username: str, password: str):
    return validate_user(username, password)


@st.cache_data(ttl=300)
def _cached_user(username: str):
    return get_user(username)


@st.cache_data(ttl=300)
def _cached_school_mappings(school_name: str):
    return list_school_sheet_records(school_name=school_name, active_only=True)


@st.cache_data(ttl=900)
def _cached_school_analytics_payload(sheet_url: str):
    reset_request_stats()
    data = build_school_analytics_cache(sheet_url)
    stats = get_request_stats()
    return {"data": data, "stats": stats}


def _clear_principal_data_cache() -> None:
    _cached_user.clear()
    _cached_school_mappings.clear()


# ──────────────────────────────────────────────────────
#  Login (standalone)
# ──────────────────────────────────────────────────────

def _principal_login() -> bool:
    st.title("Principal Dashboard")
    with st.form("principal_login"):
        username = st.text_input("Principal Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        role = _cached_validate_user(username, password)
        if role == "principal":
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["role"] = role
            st.success("Principal login successful")
            return True
        st.error("Invalid credentials or non-principal account")

    return st.session_state.get("logged_in", False) and st.session_state.get("role") == "principal"


def _assigned_schools(username: str):
    user = _cached_user(username)
    if not user:
        return []
    schools_csv = user.get("schools_assigned", "")
    schools = sorted({s.strip() for s in schools_csv.split(",") if s.strip()})
    return schools


# ──────────────────────────────────────────────────────
#  Theme CSS — Futuristic
# ──────────────────────────────────────────────────────

def _apply_principal_theme(theme_name: str) -> None:
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
            top: 0; right: 0;
            width: 200px; height: 200px;
            background: radial-gradient(circle, {theme['gradient_end']}10, transparent 70%);
            pointer-events: none;
        }}
        .dash-hero-icon {{
            width: 56px; height: 56px;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']});
            background-size: 200% 200%;
            animation: gradientRotate 4s ease infinite;
            border-radius: 16px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 1.6rem;
            color: white;
            margin-bottom: 1rem;
            box-shadow: 0 6px 24px {theme['glow_primary']};
        }}
        .dash-hero h2 {{
            margin: 0;
            font-size: 1.6rem;
            font-weight: 900;
            letter-spacing: -0.04em;
            color: {theme['text']};
        }}
        .dash-hero-sub {{
            color: {theme['muted']};
            font-size: 0.9rem;
            margin-top: 0.35rem;
            line-height: 1.6;
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
            opacity: 1;
            background: radial-gradient(circle, {theme['gradient_end']}15, transparent 70%);
        }}
        .metric-card .mc-icon {{
            width: 44px; height: 44px;
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
            color: white;
            margin-bottom: 0.9rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
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
            font-size: 1.6rem;
            font-weight: 900;
            letter-spacing: -0.03em;
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

        /* ─── Form Controls ─────────────────────────── */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stTextInput input,
        .stSelectbox [data-baseweb="select"] > div,
        .stMultiSelect [data-baseweb="select"] > div,
        .stRadio [role="radiogroup"] {{
            background: {theme['control_bg']} !important;
            color: {theme['text']} !important;
            border: 1.5px solid {theme['border']} !important;
            border-radius: 14px !important;
            font-family: 'Inter', sans-serif !important;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }}
        .stTextInput input:focus {{
            border-color: {theme['primary']} !important;
            box-shadow: 0 0 0 4px {theme['glow_primary']},
                        0 0 20px {theme['glow_primary']} !important;
        }}
        div[data-baseweb="select"] * {{
            color: {theme['text']} !important;
        }}
        .stTextInput label, .stSelectbox label, .stMultiSelect label, .stRadio label {{
            font-weight: 700 !important;
            font-size: 0.78rem !important;
            letter-spacing: 0.05em !important;
            color: {theme['muted']} !important;
            text-transform: uppercase !important;
        }}

        /* ─── FUTURISTIC BUTTONS ────────────────────── */
        .stButton > button,
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
        .stForm button:hover {{
            transform: translateY(-3px) scale(1.02) !important;
            box-shadow: 0 12px 36px {theme['glow_primary']},
                        0 0 50px {theme['glow_accent']} !important;
            filter: brightness(1.08) !important;
        }}
        .stButton > button:hover::before,
        .stForm button:hover::before {{
            width: 300px; height: 300px;
        }}
        .stButton > button:active,
        .stForm button:active {{
            transform: translateY(0) scale(0.98) !important;
        }}

        /* ─── DataFrames & Charts ───────────────────── */
        .stDataFrame {{
            border-radius: 16px !important;
            overflow: hidden;
            border: 1px solid {theme['border']} !important;
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

        /* ─── Alert ─────────────────────────────────── */
        .stAlert {{
            border-radius: 16px !important;
            border: none !important;
            animation: fadeInUp 0.4s ease !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────
#  Home Page
# ──────────────────────────────────────────────────────

def _render_principal_home(username: str, school_name: str, session_name: str) -> None:
    st.markdown(
        f"""
        <div class="dash-hero">
            <div class="dash-hero-icon">👋</div>
            <h2>Welcome back, {username}</h2>
            <p class="dash-hero-sub">Manage class setup and explore detailed analytics for your assigned schools.<br>Navigate using the sidebar to get started.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    theme = THEME_PRESETS.get(
        st.session_state.get("principal_theme", "Dark"),
        THEME_PRESETS["Dark"],
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="mc-icon" style="background: {theme['metric_blue']};">🏫</div>
                <div class="mc-label">Selected School</div>
                <div class="mc-value">{school_name}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="mc-icon" style="background: {theme['metric_cyan']};">📅</div>
                <div class="mc-label">Active Session</div>
                <div class="mc-value">{session_name}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="info-banner">
            <span style="font-size:1.1rem">💡</span>
            <span>Use the sidebar to switch between <b>Class Creation</b> and <b>Analytics</b> views.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────
#  Main render
# ──────────────────────────────────────────────────────

def render_principal_dashboard(username: str, show_logout: bool = True) -> None:
    schools = _assigned_schools(username)
    if not schools:
        st.warning("No schools assigned to this principal")
        return

    selected_theme = st.session_state.get("principal_theme", "Dark")
    with st.sidebar:
        st.markdown("### 🎓 Principal Dashboard")
        st.caption(f"Signed in as **{username}**")
        st.markdown("---")
        dark_mode = st.toggle(
            "🌙 Dark mode",
            value=(selected_theme == "Dark"),
            key="principal_dark_mode",
        )
        st.session_state["principal_theme"] = "Dark" if dark_mode else "Light"

        st.markdown("---")
        selected_school = st.selectbox("🏫 School", schools, key="principal_school")
        school_mappings = _cached_school_mappings(selected_school)

        if not school_mappings:
            st.warning("No session mappings for selected school")
            selected_session = ""
            section = "Home"
        else:
            session_names = sorted({m["session_name"] for m in school_mappings})
            selected_session = st.selectbox("📅 Session", session_names, key="principal_session")
            st.markdown("---")
            section = st.radio(
                "📍 Navigate",
                ["🏠 Home", "✏️ Create Class", "📊 Analytics"],
                key="principal_nav",
            )
            section = section.split(" ", 1)[1] if " " in section else section

        if show_logout:
            st.markdown("---")
            if st.button("🚪 Logout", use_container_width=True):
                _clear_principal_data_cache()
                _cached_school_analytics_payload.clear()
                st.session_state.clear()
                st.rerun()

    _apply_principal_theme(st.session_state.get("principal_theme", "Dark"))

    school_mappings = _cached_school_mappings(selected_school)
    if not school_mappings:
        st.warning("No session mappings found for the selected school")
        return

    selected_mapping = None
    for m in school_mappings:
        if m["session_name"] == selected_session:
            selected_mapping = m
            break

    if not selected_mapping:
        st.info("No sheet mapping found for selected session")
        return

    sheet_url = selected_mapping["sheet_url"]
    payload = _cached_school_analytics_payload(sheet_url)
    school_cache = payload.get("data")
    prefetch_stats = payload.get("stats", {})
    if prefetch_stats:
        st.caption(
            f"📡 Prefetch → total: {prefetch_stats.get('total', 0)} | tabs: {prefetch_stats.get('tabs', 0)} | read: {prefetch_stats.get('read', 0)}"
        )

    # ── Home ─────────────────────────────────────────
    if section == "Home":
        _render_principal_home(username, selected_school, selected_session)
        return

    # ── Create Class ─────────────────────────────────
    if section == "Create Class":
        st.markdown(
            """
            <div class="section-header">
                <div class="sh-icon">✏️</div>
                <h3>Create New Class</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="ui-panel">', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            class_number = st.text_input("CLASS NUMBER", value="2", placeholder="e.g. 2")
        with col2:
            section_name = st.text_input("SECTION", value="A", placeholder="e.g. A")

        class_name = f"{class_number.strip()}{section_name.strip().upper()}"
        st.caption(f"📝 Class tab to create: **{class_name}**")
        if st.button("➕ Create Class", use_container_width=True):
            if not class_name.strip():
                st.error("❌ Class and section are required")
            elif create_class(username, selected_school, class_name, session_name=selected_session):
                st.success(f"✅ Class tab '{class_name}' created successfully!")
                st.balloons()
            else:
                st.error("❌ Class creation failed")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── Analytics ────────────────────────────────────
    st.markdown(
        """
        <div class="section-header">
            <div class="sh-icon">📊</div>
            <h3>School Analytics</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    analytics_classes = list_class_tabs(sheet_url, school_cache=school_cache)
    analytics_months = list_available_months(sheet_url, school_cache=school_cache)
    if not analytics_classes or not analytics_months:
        st.info("📭 Insufficient class or month data for analytics")
        return

    with st.sidebar:
        st.markdown("---")
        st.markdown("**📊 Analytics Filters**")
        selected_analytics_month = st.selectbox(
            "Month", analytics_months, key="principal_analytics_month"
        )
        selected_analytics_class = st.selectbox(
            "Class", ["All"] + analytics_classes, key="principal_analytics_class"
        )

    if st.button("🔍 Run School Analytics", use_container_width=True):
        reset_request_stats()
        if selected_analytics_class == "All":
            class_subject_result = get_school_class_subject_analytics(
                sheet_url,
                selected_analytics_month,
                school_cache=school_cache,
            )
            action_stats = get_request_stats()
            st.caption(
                f"📡 API → total: {action_stats.get('total', 0)} | tabs: {action_stats.get('tabs', 0)} | read: {action_stats.get('read', 0)}"
            )

            st.markdown("#### 📋 Subject + Class Wise (All Classes)")
            if not class_subject_result.get("success"):
                st.warning(class_subject_result.get("message", "No class-subject data found"))
            else:
                class_subject_df = pd.DataFrame(class_subject_result.get("class_subject_rows", []))
                st.dataframe(class_subject_df, use_container_width=True)
                if not class_subject_df.empty:
                    class_subject_pass_fig = px.bar(
                        class_subject_df,
                        x="class_name",
                        y="pass_rate",
                        color="subject",
                        barmode="group",
                        title="Class-wise Pass Rate (Subject Breakdown)",
                        hover_data=["appeared", "passed", "failed", "average"],
                        color_discrete_sequence=px.colors.qualitative.Set2,
                    )
                    class_subject_pass_fig.update_layout(
                        template="plotly_dark" if is_dark_mode() else "plotly_white",
                        height=460,
                        font=dict(family="Inter"),
                        title_font_size=16,
                        margin=dict(t=50, b=40),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(class_subject_pass_fig, use_container_width=True)

                    class_subject_avg_fig = px.bar(
                        class_subject_df,
                        x="class_name",
                        y="average",
                        color="subject",
                        barmode="group",
                        title="Class-wise Average Marks (Subject Breakdown)",
                        hover_data=["appeared", "passed", "failed", "pass_rate"],
                        color_discrete_sequence=px.colors.qualitative.Safe,
                    )
                    class_subject_avg_fig.update_layout(
                        template="plotly_dark" if is_dark_mode() else "plotly_white",
                        height=460,
                        font=dict(family="Inter"),
                        title_font_size=16,
                        margin=dict(t=50, b=40),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(class_subject_avg_fig, use_container_width=True)
        else:
            subject_result = get_school_subject_analytics(
                sheet_url,
                selected_analytics_month,
                class_name=selected_analytics_class,
                school_cache=school_cache,
            )
            action_stats = get_request_stats()
            st.caption(
                f"📡 API → total: {action_stats.get('total', 0)} | tabs: {action_stats.get('tabs', 0)} | read: {action_stats.get('read', 0)}"
            )

            st.markdown("#### 📋 Subject-Wise (Selected Class)")
            if not subject_result.get("success"):
                st.warning(subject_result.get("message", "No subject data found"))
            else:
                subject_df = pd.DataFrame(subject_result.get("subject_rows", []))
                st.dataframe(subject_df, use_container_width=True)
                if not subject_df.empty:
                    subject_pass_fig = px.bar(
                        subject_df,
                        x="subject",
                        y=["passed", "failed"],
                        barmode="group",
                        title="Subject-wise Passed vs Failed",
                        color_discrete_sequence=["#818cf8", "#f43f5e"],
                    )
                    subject_pass_fig.update_layout(
                        template="plotly_dark" if is_dark_mode() else "plotly_white",
                        height=460,
                        font=dict(family="Inter"),
                        title_font_size=16,
                        margin=dict(t=50, b=40),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(subject_pass_fig, use_container_width=True)


def is_dark_mode() -> bool:
    return st.session_state.get("principal_theme", "Dark") == "Dark"


# ──────────────────────────────────────────────────────
#  Standalone entry point
# ──────────────────────────────────────────────────────

def main() -> None:
    if get_script_run_ctx() is None:
        print("Please run this app with Streamlit:")
        print("streamlit run principal_dashboard.py")
        return

    st.set_page_config(page_title="Principal Dashboard", page_icon="🎓", layout="wide")
    if not _principal_login():
        return

    render_principal_dashboard(st.session_state["username"], show_logout=True)


if __name__ == "__main__":
    main()
