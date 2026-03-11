"""Streamlit Super User Dashboard — Dark Glassmorphism Edition.

Premium dark-theme administration panel with sidebar navigation,
animated login, glassmorphic cards, and Plotly dark charts.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from system_admin.google_sheets_controller import GoogleSheetsController, ValidationError
from system_admin.principal_manager import PrincipalManager
from system_admin.school_analytics import (
    analytics_from_pk9_workbook,
    analytics_from_student_sheet,
    build_plotly_charts,
    global_overview_from_monthly_report,
)
from system_admin.school_manager import SchoolManager, SchoolRecord
from system_admin.session_manager import SessionManager

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
PK9_FILE = str(WORKSPACE_ROOT / "PK9 .xlsx")
MONTHLY_REPORT_FILE = str(
    WORKSPACE_ROOT / "Monthly Analysis ( Cl-2 to 6 & 8 ) January - 2026.xlsx"
)
LOCAL_DB_FILE = str(WORKSPACE_ROOT / "local_system_db.xlsx")

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG_DEEP = "#060a1e"
BG_CARD = "rgba(17,22,51,0.72)"
BG_CARD_SOLID = "#111633"
BORDER = "rgba(255,255,255,0.06)"
ACCENT_CYAN = "#00d4ff"
ACCENT_PURPLE = "#7c3aed"
ACCENT_PINK = "#f472b6"
ACCENT_EMERALD = "#10b981"
ACCENT_AMBER = "#f59e0b"
TEXT_PRIMARY = "#e2e8f0"
TEXT_DIM = "#94a3b8"

NAV_ITEMS = [
    ("overview", "System Overview"),
    ("schools", "School Management"),
    ("principals", "Principal Management"),
    ("sessions", "Session Management"),
    ("analytics", "Global Analytics"),
]

METRIC_ICONS = {
    "Schools": '<svg width="28" height="28" fill="none" viewBox="0 0 24 24"><path d="M3 21V7l9-4 9 4v14" stroke="#00d4ff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 21v-6h6v6" stroke="#00d4ff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "Classes": '<svg width="28" height="28" fill="none" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2" stroke="#7c3aed" stroke-width="1.5"/><path d="M3 10h18" stroke="#7c3aed" stroke-width="1.5"/></svg>',
    "Students": '<svg width="28" height="28" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="7" r="4" stroke="#f472b6" stroke-width="1.5"/><path d="M5.5 21a6.5 6.5 0 0 1 13 0" stroke="#f472b6" stroke-width="1.5" stroke-linecap="round"/></svg>',
    "Teachers": '<svg width="28" height="28" fill="none" viewBox="0 0 24 24"><circle cx="9" cy="7" r="3.5" stroke="#10b981" stroke-width="1.5"/><path d="M3 21a6 6 0 0 1 12 0" stroke="#10b981" stroke-width="1.5"/><path d="M16 11l2 2 4-4" stroke="#10b981" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "Sessions": '<svg width="28" height="28" fill="none" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" stroke="#f59e0b" stroke-width="1.5"/><path d="M3 10h18M8 2v4M16 2v4" stroke="#f59e0b" stroke-width="1.5" stroke-linecap="round"/></svg>',
}

ACCENT_MAP = {
    "Schools": ACCENT_CYAN,
    "Classes": ACCENT_PURPLE,
    "Students": ACCENT_PINK,
    "Teachers": ACCENT_EMERALD,
    "Sessions": ACCENT_AMBER,
}


# =====================  GLOBAL CSS  =========================================
def _inject_css() -> None:
    st.markdown(
        """
<style>
/* ---------- Fonts ---------- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* ---------- Root overrides ---------- */
:root {
    --bg-deep:   #060a1e;
    --bg-card:   rgba(17,22,51,0.72);
    --border:    rgba(255,255,255,0.06);
    --cyan:      #00d4ff;
    --purple:    #7c3aed;
    --pink:      #f472b6;
    --emerald:   #10b981;
    --amber:     #f59e0b;
    --text:      #e2e8f0;
    --text-dim:  #94a3b8;
    --radius:    14px;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
    color: var(--text);
}

/* ---------- Deep background with orbs ---------- */
.stApp {
    background:
        radial-gradient(ellipse 600px 600px at 8% 15%, rgba(0,212,255,0.10), transparent),
        radial-gradient(ellipse 500px 500px at 92% 12%, rgba(124,58,237,0.12), transparent),
        radial-gradient(ellipse 700px 700px at 78% 85%, rgba(244,114,182,0.08), transparent),
        var(--bg-deep) !important;
}

/* ---------- Hide default Streamlit chrome ---------- */
#MainMenu, header[data-testid="stHeader"], footer,
div[data-testid="stToolbar"] {visibility: hidden; height: 0;}
div[data-testid="stDecoration"] {display: none;}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0c1030 0%, #070b22 100%) !important;
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown span {
    color: var(--text-dim) !important;
}

/* ---------- Glass card ---------- */
.glass-card {
    background: var(--bg-card);
    backdrop-filter: blur(16px) saturate(1.4);
    -webkit-backdrop-filter: blur(16px) saturate(1.4);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem 1.4rem;
    margin-bottom: 1rem;
    transition: transform 0.22s ease, box-shadow 0.22s ease;
}
.glass-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 44px rgba(0,0,0,0.35);
}

/* ---------- Metric tile ---------- */
.metric-tile {
    background: var(--bg-card);
    backdrop-filter: blur(14px);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.1rem 1.2rem 0.9rem;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease;
}
.metric-tile:hover { transform: translateY(-3px); }
.metric-tile .glow {
    position: absolute; top: -30px; right: -30px;
    width: 90px; height: 90px; border-radius: 50%;
    filter: blur(30px); opacity: 0.35;
}
.metric-tile .icon { margin-bottom: 0.4rem; }
.metric-tile .label {
    font-size: 0.72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.8px;
    color: var(--text-dim);
}
.metric-tile .value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2rem; font-weight: 700; line-height: 1.1;
}

/* ---------- Section header ---------- */
.section-hdr {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700; font-size: 1.35rem;
    margin: 1.4rem 0 0.9rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 0.5rem;
}
.section-hdr .dot {
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block;
}

/* ---------- Data tables ---------- */
div[data-testid="stDataFrame"] {
    border-radius: var(--radius) !important;
    overflow: hidden;
}
div[data-testid="stDataFrame"] table {
    background: #0d1129 !important;
}

/* ---------- Form / input overrides ---------- */
div[data-testid="stForm"] {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.2rem;
}
input, textarea, select, div[data-baseweb="select"] {
    background: rgba(255,255,255,0.04) !important;
    border-color: rgba(255,255,255,0.08) !important;
    color: var(--text) !important;
    border-radius: 10px !important;
}
input:focus, textarea:focus {
    border-color: var(--cyan) !important;
    box-shadow: 0 0 0 2px rgba(0,212,255,0.15) !important;
}
label {
    color: var(--text-dim) !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ---------- Buttons ---------- */
button[kind="primary"], button[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, var(--cyan), var(--purple)) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px;
    transition: opacity 0.18s ease;
}
button[kind="primary"]:hover {
    opacity: 0.88;
}
button[kind="secondary"] {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: var(--text) !important;
    border-radius: 10px !important;
}

/* ---------- Login card ---------- */
.login-wrapper {
    max-width: 420px;
    margin: 6vh auto 0;
    text-align: center;
}
.login-card {
    background: var(--bg-card);
    backdrop-filter: blur(20px);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 2.5rem 2rem 2rem;
    box-shadow: 0 24px 64px rgba(0,0,0,0.55);
}
.login-logo {
    width: 64px; height: 64px;
    border-radius: 16px;
    background: linear-gradient(135deg, var(--cyan), var(--purple));
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto 1.2rem;
    font-size: 1.7rem; color: #fff;
    box-shadow: 0 8px 32px rgba(0,212,255,0.25);
}
.login-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.6rem; font-weight: 700;
    margin-bottom: 0.2rem;
}
.login-sub {
    font-size: 0.85rem; color: var(--text-dim);
    margin-bottom: 1.6rem;
}

/* ---------- Sidebar nav pills ---------- */
.nav-pill {
    display: flex; align-items: center; gap: 0.65rem;
    padding: 0.62rem 0.9rem;
    border-radius: 10px;
    cursor: pointer;
    font-weight: 500; font-size: 0.88rem;
    color: var(--text-dim);
    transition: background 0.18s, color 0.18s;
    margin-bottom: 2px;
    text-decoration: none !important;
}
.nav-pill:hover { background: rgba(255,255,255,0.05); color: var(--text); }
.nav-pill.active {
    background: linear-gradient(135deg, rgba(0,212,255,0.12), rgba(124,58,237,0.12));
    color: var(--cyan) !important;
    font-weight: 600;
    border: 1px solid rgba(0,212,255,0.18);
}

/* ---------- Badge ---------- */
.badge {
    display: inline-block;
    padding: 0.18rem 0.55rem;
    border-radius: 6px;
    font-size: 0.68rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.6px;
}
.badge-active { background: rgba(16,185,129,0.15); color: var(--emerald); }
.badge-offline { background: rgba(245,158,11,0.15); color: var(--amber); }

/* ---------- Plotly overrides ---------- */
.js-plotly-plot .plotly .modebar { display: none !important; }

/* ---------- Tabs override ---------- */
button[data-baseweb="tab"] {
    color: var(--text-dim) !important;
    font-weight: 500 !important;
    border-radius: 8px 8px 0 0 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--cyan) !important;
    border-bottom: 2px solid var(--cyan) !important;
}

/* ---------- Toast / alerts ---------- */
div[data-testid="stAlert"] {
    border-radius: 10px !important;
}

/* ---------- Scrollbar ---------- */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
</style>
""",
        unsafe_allow_html=True,
    )


# =====================  COMPONENTS  =========================================
def _metric_card(label: str, value, accent: str) -> str:
    icon = METRIC_ICONS.get(label, "")
    return f"""
    <div class="metric-tile">
        <div class="glow" style="background:{accent};"></div>
        <div class="icon">{icon}</div>
        <div class="label">{label}</div>
        <div class="value" style="color:{accent};">{value}</div>
    </div>"""


def _section_header(text: str, color: str = ACCENT_CYAN) -> None:
    st.markdown(
        f'<div class="section-hdr"><span class="dot" style="background:{color};"></span>{text}</div>',
        unsafe_allow_html=True,
    )


def _glass_open() -> str:
    return '<div class="glass-card">'


def _glass_close() -> str:
    return "</div>"


# =====================  SERVICES  ===========================================
@st.cache_resource
def _get_services():
    controller = GoogleSheetsController(
        backend="excel", excel_path=LOCAL_DB_FILE, cache_enabled=True
    )
    school_manager = SchoolManager(controller)
    principal_manager = PrincipalManager(controller)
    session_manager = SessionManager(controller)
    principal_manager.create_default_super_user(
        username="super_admin", password="admin123"
    )

    schools = school_manager.list_schools()
    if schools.empty:
        school_manager.add_school(
            SchoolRecord(
                school_id="SCH-PK9",
                pks_code="PKS09",
                school_name="PK9 School",
                region="Demo Region",
            )
        )
        school_manager.seed_demo_school_records("PKS09", "SCH-PK9")

    return controller, school_manager, principal_manager, session_manager


# =====================  LOGIN  ==============================================
def _login_page(principal_manager: PrincipalManager) -> None:
    st.markdown(
        f"""
        <div class="login-wrapper">
            <div class="login-card">
                <div class="login-logo">
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none">
                        <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#fff" opacity=".9"/>
                        <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="#fff" stroke-width="1.5"
                              stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
                <div class="login-title">Civics Admin</div>
                <div class="login-sub">System Administration Control Center</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_pad_l, col_center, col_pad_r = st.columns([1.5, 1, 1.5])
    with col_center:
        with st.form("login_form"):
            username = st.text_input("Username", value="super_admin")
            password = st.text_input("Password", type="password", value="admin123")
            submitted = st.form_submit_button(
                "Sign In", type="primary", use_container_width=True
            )
            if submitted:
                profile = principal_manager.authenticate(
                    username, password, role="super_user"
                )
                if profile:
                    st.session_state["auth_user"] = profile
                    st.rerun()
                else:
                    st.error("Invalid credentials or insufficient role.")

        st.markdown(
            '<p style="text-align:center;font-size:0.75rem;color:#64748b;margin-top:1.2rem;">'
            "Offline mode &bull; Excel backend &bull; Google Sheets-ready</p>",
            unsafe_allow_html=True,
        )


# =====================  SIDEBAR  ============================================
def _render_sidebar(user: dict) -> str:
    with st.sidebar:
        # Branding
        st.markdown(
            f"""
            <div style="padding:1rem 0.4rem 0.5rem;display:flex;align-items:center;gap:0.65rem;">
                <div style="width:38px;height:38px;border-radius:10px;
                            background:linear-gradient(135deg,{ACCENT_CYAN},{ACCENT_PURPLE});
                            display:flex;align-items:center;justify-content:center;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                        <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#fff" opacity=".9"/>
                        <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="#fff"
                              stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
                <div>
                    <div style="font-family:'Space Grotesk',sans-serif;font-weight:700;
                                font-size:1.05rem;color:{TEXT_PRIMARY};">Civics Admin</div>
                    <div style="font-size:0.68rem;color:{TEXT_DIM};">v2.0 &middot; Dark</div>
                </div>
            </div>
            <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:0.7rem 0 1rem;">
            """,
            unsafe_allow_html=True,
        )

        # User info
        st.markdown(
            f"""
            <div style="padding:0.5rem 0.5rem;display:flex;align-items:center;gap:0.6rem;
                        margin-bottom:1rem;">
                <div style="width:34px;height:34px;border-radius:50%;
                            background:linear-gradient(135deg,{ACCENT_PURPLE},{ACCENT_PINK});
                            display:flex;align-items:center;justify-content:center;
                            font-weight:700;font-size:0.85rem;color:#fff;">
                    {user['username'][0].upper()}
                </div>
                <div>
                    <div style="font-weight:600;font-size:0.85rem;color:{TEXT_PRIMARY};">{user['username']}</div>
                    <div style="font-size:0.68rem;color:{TEXT_DIM};">
                        <span class="badge badge-active">Super User</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Navigation
        st.markdown(
            f'<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:1px;color:{TEXT_DIM};padding:0 0.5rem;margin-bottom:0.4rem;">Navigation</div>',
            unsafe_allow_html=True,
        )

        nav_icons = {
            "overview": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/></svg>',
            "schools": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M3 21V7l9-4 9 4v14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 21v-6h6v6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            "principals": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 21a6.5 6.5 0 0113 0" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
            "sessions": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M3 10h18M8 2v4M16 2v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
            "analytics": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        }

        if "nav_page" not in st.session_state:
            st.session_state["nav_page"] = "overview"

        for key, label in NAV_ITEMS:
            active_cls = "active" if st.session_state["nav_page"] == key else ""
            icon_html = nav_icons.get(key, "")
            if st.sidebar.button(
                f"{'  ' if active_cls else ''}{label}",
                key=f"nav_{key}",
                use_container_width=True,
            ):
                st.session_state["nav_page"] = key
                st.rerun()

        # Bottom section
        st.markdown("<br>" * 3, unsafe_allow_html=True)
        st.markdown(
            f"""
            <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin-bottom:0.8rem;">
            <div style="padding:0 0.5rem;">
                <div style="font-size:0.68rem;color:{TEXT_DIM};margin-bottom:0.5rem;">
                    <span class="badge badge-offline">Offline Mode</span>
                </div>
                <div style="font-size:0.65rem;color:{TEXT_DIM};">
                    Backend: Excel &bull; {datetime.now().strftime('%b %d, %Y')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Sign Out", use_container_width=True, type="secondary"):
            st.session_state.pop("auth_user", None)
            st.session_state.pop("nav_page", None)
            st.rerun()

    return st.session_state.get("nav_page", "overview")


# =====================  PANELS  =============================================
def _overview_panel(school_manager: SchoolManager, session_manager: SessionManager) -> None:
    _section_header("System Overview", ACCENT_CYAN)

    overview = school_manager.system_overview()
    session_info = session_manager.session_overview()

    metrics = [
        ("Schools", overview.get("total_schools", 0), ACCENT_CYAN),
        ("Classes", overview.get("total_classes", 0), ACCENT_PURPLE),
        ("Students", overview.get("total_students", 0), ACCENT_PINK),
        ("Teachers", overview.get("total_teachers", 0), ACCENT_EMERALD),
        ("Sessions", session_info.get("total_sessions", 0), ACCENT_AMBER),
    ]

    cols = st.columns(5, gap="medium")
    for col, (label, value, accent) in zip(cols, metrics):
        col.markdown(_metric_card(label, value, accent), unsafe_allow_html=True)

    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)

    # School table
    _section_header("Registered Schools", ACCENT_CYAN)
    schools = school_manager.list_schools()
    if schools.empty:
        st.info("No schools registered yet.")
    else:
        st.dataframe(
            schools,
            use_container_width=True,
            hide_index=True,
            column_config={
                "status": st.column_config.TextColumn("Status", width="small"),
                "pks_code": st.column_config.TextColumn("PKS Code", width="small"),
            },
        )

    # Quick hierarchy glance
    if not schools.empty:
        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        _section_header("School Hierarchy Snapshot", ACCENT_PURPLE)
        hierarchy_cols = st.columns(min(len(schools), 4))
        for i, (_, row) in enumerate(schools.iterrows()):
            if i >= 4:
                break
            pks = str(row.get("pks_code", "")).upper()
            h = school_manager.school_hierarchy(pks)
            with hierarchy_cols[i]:
                st.markdown(
                    f"""<div class="glass-card" style="text-align:center;">
                    <div style="font-weight:700;color:{ACCENT_CYAN};font-size:0.95rem;margin-bottom:0.6rem;">
                        {row.get('school_name', pks)}
                    </div>
                    <div style="display:flex;justify-content:space-around;">
                        <div><div style="font-size:1.4rem;font-weight:700;color:{ACCENT_PURPLE};">{h['classes']}</div>
                             <div style="font-size:0.65rem;color:{TEXT_DIM};text-transform:uppercase;">Classes</div></div>
                        <div><div style="font-size:1.4rem;font-weight:700;color:{ACCENT_PINK};">{h['students']}</div>
                             <div style="font-size:0.65rem;color:{TEXT_DIM};text-transform:uppercase;">Students</div></div>
                        <div><div style="font-size:1.4rem;font-weight:700;color:{ACCENT_EMERALD};">{h['teachers']}</div>
                             <div style="font-size:0.65rem;color:{TEXT_DIM};text-transform:uppercase;">Teachers</div></div>
                    </div></div>""",
                    unsafe_allow_html=True,
                )


def _school_panel(school_manager: SchoolManager) -> None:
    _section_header("School Management", ACCENT_CYAN)

    tab_add, tab_remove, tab_seed = st.tabs(
        ["Add School", "Remove School", "Seed Demo Data"]
    )

    with tab_add:
        with st.form("add_school_form"):
            c1, c2 = st.columns(2)
            school_id = c1.text_input("School ID", placeholder="SCH-NEW")
            pks_code = c2.text_input("PKS Code", placeholder="PKS10")
            school_name = c1.text_input("School Name", placeholder="Model Campus")
            region = c2.text_input("Region", placeholder="District A")
            add_submit = st.form_submit_button(
                "Register School", type="primary", use_container_width=True
            )
            if add_submit:
                try:
                    result = school_manager.add_school(
                        SchoolRecord(
                            school_id=school_id,
                            pks_code=pks_code,
                            school_name=school_name,
                            region=region,
                        )
                    )
                    st.success(
                        f"School registered. Auto-created sheets: {result['created_sheets']}"
                    )
                except Exception as exc:
                    st.error(str(exc))

    with tab_remove:
        schools = school_manager.list_schools()
        if schools.empty:
            st.info("No schools to remove.")
        else:
            with st.form("delete_school_form"):
                remove_id = st.selectbox(
                    "Select school to remove",
                    options=schools["school_id"].astype(str).tolist(),
                )
                st.warning(
                    "This will permanently delete the school and all associated sheets."
                )
                delete_submit = st.form_submit_button(
                    "Delete School", use_container_width=True
                )
                if delete_submit:
                    try:
                        result = school_manager.remove_school(remove_id)
                        st.success(
                            f"Deleted {result['deleted_school_rows']} row(s), "
                            f"{result['deleted_sheets_count']} sheet(s) removed."
                        )
                    except Exception as exc:
                        st.error(str(exc))

    with tab_seed:
        schools = school_manager.list_schools()
        if schools.empty:
            st.info("Register a school first.")
        else:
            target = st.selectbox(
                "Target school",
                options=schools["school_id"].astype(str).tolist(),
                key="seed_select",
            )
            st.caption("Generates sample classes, teachers, and students for demo.")
            if st.button(
                "Generate Demo Data",
                type="primary",
                use_container_width=True,
            ):
                try:
                    row = schools.loc[
                        schools["school_id"].astype(str) == target
                    ].iloc[0]
                    school_manager.seed_demo_school_records(
                        str(row["pks_code"]), str(row["school_id"])
                    )
                    st.success("Demo hierarchy data generated successfully.")
                except Exception as exc:
                    st.error(str(exc))


def _principal_panel(
    school_manager: SchoolManager, principal_manager: PrincipalManager
) -> None:
    _section_header("Principal Management", ACCENT_PURPLE)

    schools = school_manager.list_schools()
    school_ids = (
        schools["school_id"].astype(str).tolist() if not schools.empty else []
    )

    tab_create, tab_assign, tab_list = st.tabs(
        ["Create Principal", "Reassign Principal", "All Principals"]
    )

    with tab_create:
        with st.form("create_principal_form"):
            c1, c2 = st.columns(2)
            principal_id = c1.text_input("Principal ID", placeholder="PR-001")
            username = c2.text_input("Username", placeholder="principal_pk9")
            password = c1.text_input(
                "Password", type="password", placeholder="Enter password"
            )
            school_id = c2.selectbox(
                "Assign to School", options=school_ids
            ) if school_ids else ""
            submit = st.form_submit_button(
                "Create Principal Account",
                type="primary",
                use_container_width=True,
            )
            if submit:
                try:
                    result = principal_manager.create_principal_account(
                        principal_id=principal_id,
                        username=username,
                        password=password,
                        school_id=school_id,
                    )
                    school_manager.assign_principal(
                        result["school_id"], result["username"]
                    )
                    st.success(
                        f"Principal **{result['username']}** created and assigned to **{result['school_id']}**."
                    )
                except Exception as exc:
                    st.error(str(exc))

    with tab_assign:
        principal_list = principal_manager.list_principals()
        principal_names = (
            principal_list["username"].astype(str).tolist()
            if not principal_list.empty
            else []
        )
        if not principal_names or not school_ids:
            st.info("Create at least one principal and one school first.")
        else:
            with st.form("assign_principal_form"):
                principal_username = st.selectbox("Principal", options=principal_names)
                school_target = st.selectbox("School", options=school_ids)
                assign_submit = st.form_submit_button(
                    "Reassign Principal",
                    use_container_width=True,
                )
                if assign_submit and principal_username and school_target:
                    try:
                        principal_manager.assign_principal_to_school(
                            principal_username, school_target
                        )
                        school_manager.assign_principal(
                            school_target, principal_username
                        )
                        st.success(
                            f"Principal **{principal_username}** assigned to **{school_target}**."
                        )
                    except Exception as exc:
                        st.error(str(exc))

    with tab_list:
        principals = principal_manager.list_principals()
        if principals.empty:
            st.info("No principals created yet.")
        else:
            st.dataframe(principals, use_container_width=True, hide_index=True)


def _session_panel(
    session_manager: SessionManager, school_manager: SchoolManager
) -> None:
    _section_header("Academic Sessions", ACCENT_AMBER)

    left, right = st.columns([1, 1.5])

    with left:
        st.markdown(
            f'{_glass_open()}<div style="font-weight:600;margin-bottom:0.8rem;color:{ACCENT_AMBER};">New Session</div>',
            unsafe_allow_html=True,
        )
        with st.form("session_form"):
            session_year = st.number_input(
                "Academic Year",
                min_value=2024,
                max_value=2050,
                value=2026,
                step=1,
            )
            submit = st.form_submit_button(
                "Create Session",
                type="primary",
                use_container_width=True,
            )
            if submit:
                try:
                    result = session_manager.create_session(int(session_year))
                    st.success(
                        f"Session **{result['session_year']}** created. "
                        f"Generated **{result['generated_sheet_count']}** worksheet(s)."
                    )
                except Exception as exc:
                    st.error(str(exc))
        st.markdown(_glass_close(), unsafe_allow_html=True)

    with right:
        _section_header("Session Registry", ACCENT_AMBER)
        sessions = session_manager.list_sessions()
        if sessions.empty:
            st.info("No sessions created yet.")
        else:
            st.dataframe(sessions, use_container_width=True, hide_index=True)

        _section_header("Linked Schools", ACCENT_CYAN)
        st.dataframe(
            school_manager.list_schools(), use_container_width=True, hide_index=True
        )


def _analytics_panel(
    controller: GoogleSheetsController, school_manager: SchoolManager
) -> None:
    _section_header("Global Analytics", ACCENT_EMERALD)

    analytics_tab_pk9, analytics_tab_report, analytics_tab_school = st.tabs(
        ["PK9 School Analytics", "Overall Report", "Principal-Level Analytics"]
    )

    with analytics_tab_pk9:
        if Path(PK9_FILE).exists():
            bundle = analytics_from_pk9_workbook(PK9_FILE)
            charts = build_plotly_charts(bundle)

            c1, c2 = st.columns(2)
            if charts.get("class"):
                c1.plotly_chart(charts["class"], use_container_width=True)
            if charts.get("subject"):
                c2.plotly_chart(charts["subject"], use_container_width=True)

            c3, c4 = st.columns(2)
            if charts.get("monthly_final"):
                c3.plotly_chart(charts["monthly_final"], use_container_width=True)
            if charts.get("gender"):
                c4.plotly_chart(charts["gender"], use_container_width=True)
        else:
            st.warning("PK9 workbook not found at expected path.")

    with analytics_tab_report:
        if Path(MONTHLY_REPORT_FILE).exists():
            global_df = global_overview_from_monthly_report(MONTHLY_REPORT_FILE)
            st.dataframe(global_df, use_container_width=True, hide_index=True)
            if not global_df.empty:
                import plotly.express as px

                fig = px.bar(
                    global_df,
                    x="report_sheet",
                    y="average_score",
                    color="average_score",
                    color_continuous_scale=[
                        [0, "#7c3aed"],
                        [0.5, "#00d4ff"],
                        [1, "#10b981"],
                    ],
                )
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter", size=12, color="#94a3b8"),
                    title=dict(
                        text="Monthly Analysis by Class",
                        font=dict(size=16, color="#e2e8f0"),
                    ),
                    margin=dict(l=20, r=20, t=50, b=20),
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Monthly analysis workbook not found.")

    with analytics_tab_school:
        schools = school_manager.list_schools()
        if schools.empty:
            st.info("No schools registered.")
            return

        selected_school = st.selectbox(
            "Select school for principal-level analytics",
            schools["school_id"].astype(str).tolist(),
            key="analytics_school_select",
        )
        row = schools.loc[
            schools["school_id"].astype(str) == selected_school
        ].iloc[0]
        pks = str(row.get("pks_code", "")).strip().upper()

        students = controller.read_sheet_or_empty(f"Students_{pks}")
        bundle = analytics_from_student_sheet(students)
        charts = build_plotly_charts(bundle)

        c1, c2 = st.columns(2)
        if charts.get("class"):
            c1.plotly_chart(charts["class"], use_container_width=True)
        if charts.get("subject"):
            c2.plotly_chart(charts["subject"], use_container_width=True)

        c3, c4 = st.columns(2)
        if charts.get("gender"):
            c3.plotly_chart(charts["gender"], use_container_width=True)
        if charts.get("monthly_final"):
            c4.plotly_chart(charts["monthly_final"], use_container_width=True)


# =====================  MAIN  ===============================================
def run_dashboard() -> None:
    st.set_page_config(
        page_title="Civics Admin",
        page_icon=":bar_chart:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_css()

    controller, school_manager, principal_manager, session_manager = _get_services()

    # ---------- Auth gate ----------
    if "auth_user" not in st.session_state:
        _login_page(principal_manager)
        return

    user = st.session_state["auth_user"]
    page = _render_sidebar(user)

    # ---------- Top bar ----------
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    margin-bottom:0.3rem;">
            <div>
                <div style="font-family:'Space Grotesk',sans-serif;font-weight:700;
                            font-size:1.6rem;color:{TEXT_PRIMARY};">
                    {dict(NAV_ITEMS).get(page, 'Dashboard')}
                </div>
                <div style="font-size:0.78rem;color:{TEXT_DIM};">
                    {datetime.now().strftime('%A, %B %d, %Y')}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- Route ----------
    if page == "overview":
        _overview_panel(school_manager, session_manager)
    elif page == "schools":
        _school_panel(school_manager)
    elif page == "principals":
        _principal_panel(school_manager, principal_manager)
    elif page == "sessions":
        _session_panel(session_manager, school_manager)
    elif page == "analytics":
        _analytics_panel(controller, school_manager)


if __name__ == "__main__":
    run_dashboard()
