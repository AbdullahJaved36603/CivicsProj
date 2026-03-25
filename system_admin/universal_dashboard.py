import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from google_sheets_controller import validate_user
from principal_dashboard import render_principal_dashboard
from super_user_dashboard import render_admin_dashboard


ROLE_TITLES = {
    "admin": "Admin",
    "principal": "Principal",
}


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
        "border": "rgba(99,102,241,0.12)",
        "control_bg": "#f8f9fc",
        "card_shadow": "0 8px 32px rgba(99,102,241,0.10)",
        "glass_bg": "rgba(255,255,255,0.72)",
        "glass_border": "rgba(255,255,255,0.45)",
        "glow_primary": "rgba(99,102,241,0.35)",
        "glow_accent": "rgba(6,182,212,0.30)",
        "gradient_start": "#6366f1",
        "gradient_mid": "#a855f7",
        "gradient_end": "#06b6d4",
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
        "border": "rgba(129,140,248,0.18)",
        "control_bg": "rgba(22,33,62,0.7)",
        "card_shadow": "0 8px 32px rgba(0,0,0,0.45)",
        "glass_bg": "rgba(15,15,35,0.72)",
        "glass_border": "rgba(129,140,248,0.14)",
        "glow_primary": "rgba(129,140,248,0.30)",
        "glow_accent": "rgba(34,211,238,0.25)",
        "gradient_start": "#818cf8",
        "gradient_mid": "#c084fc",
        "gradient_end": "#22d3ee",
    },
}


@st.cache_data(ttl=300)
def _cached_validate_user(username: str, password: str):
    return validate_user(username, password)


def _apply_login_theme(theme_name: str) -> None:
    theme = THEME_PRESETS.get(theme_name, THEME_PRESETS["Light"])
    is_dark = theme_name == "Dark"
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

        /* ─── Keyframes ───────────────────────────────── */
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(40px) scale(0.97); }}
            to   {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}
        @keyframes gradientRotate {{
            0%   {{ background-position: 0% 50%; }}
            50%  {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        @keyframes glowPulse {{
            0%, 100% {{ opacity: 0.4; filter: blur(60px); }}
            50%      {{ opacity: 0.7; filter: blur(80px); }}
        }}
        @keyframes floatSlow {{
            0%, 100% {{ transform: translateY(0px) rotate(0deg); }}
            25%      {{ transform: translateY(-12px) rotate(2deg); }}
            75%      {{ transform: translateY(6px) rotate(-1deg); }}
        }}
        @keyframes borderGlow {{
            0%, 100% {{ border-color: {theme['gradient_start']}40; box-shadow: 0 0 20px {theme['glow_primary']}; }}
            50%      {{ border-color: {theme['gradient_end']}40; box-shadow: 0 0 30px {theme['glow_accent']}; }}
        }}
        @keyframes shimmerBar {{
            0%   {{ background-position: -300% center; }}
            100% {{ background-position: 300% center; }}
        }}
        @keyframes typewriter {{
            from {{ width: 0; }}
            to   {{ width: 100%; }}
        }}
        @keyframes spinSlow {{
            from {{ transform: rotate(0deg); }}
            to   {{ transform: rotate(360deg); }}
        }}
        @keyframes ripple {{
            0%   {{ transform: scale(0); opacity: 0.5; }}
            100% {{ transform: scale(4); opacity: 0; }}
        }}

        /* ─── Global ──────────────────────────────────── */
        *, *::before, *::after {{ box-sizing: border-box; }}
        .stApp {{
            background: {theme['bg']};
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: {theme['text']};
            overflow-x: hidden;
            min-height: 100vh;
        }}

        /* ─── Animated Background ─────────────────────── */
        .login-bg-grid {{
            position: fixed;
            inset: 0;
            background-image:
                linear-gradient({'rgba(99,102,241,0.03)' if not is_dark else 'rgba(129,140,248,0.025)'} 1px, transparent 1px),
                linear-gradient(90deg, {'rgba(99,102,241,0.03)' if not is_dark else 'rgba(129,140,248,0.025)'} 1px, transparent 1px);
            background-size: 60px 60px;
            z-index: 0;
            pointer-events: none;
        }}

        .login-orb {{
            position: fixed;
            border-radius: 50%;
            pointer-events: none;
            z-index: 0;
        }}
        .login-orb-1 {{
            width: 500px; height: 500px;
            top: -180px; right: -120px;
            background: radial-gradient(circle, {theme['gradient_start']}30, transparent 70%);
            animation: glowPulse 8s ease-in-out infinite;
        }}
        .login-orb-2 {{
            width: 400px; height: 400px;
            bottom: -120px; left: -100px;
            background: radial-gradient(circle, {theme['gradient_end']}25, transparent 70%);
            animation: glowPulse 10s ease-in-out infinite 3s;
        }}
        .login-orb-3 {{
            width: 300px; height: 300px;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: radial-gradient(circle, {theme['gradient_mid']}15, transparent 70%);
            animation: glowPulse 12s ease-in-out infinite 5s;
        }}

        .block-container {{
            max-width: 480px !important;
            padding: 2.5rem 1.2rem 2rem !important;
            animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            z-index: 1;
        }}

        /* ─── Sidebar ─────────────────────────────────── */
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

        /* ─── Login Card ──────────────────────────────── */
        .login-card {{
            background: {theme['glass_bg']};
            backdrop-filter: blur(30px) saturate(200%);
            -webkit-backdrop-filter: blur(30px) saturate(200%);
            border: 1px solid {theme['glass_border']};
            border-radius: 28px;
            padding: 2.8rem 2.2rem 2.2rem;
            box-shadow: {theme['card_shadow']};
            animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1),
                       borderGlow 6s ease-in-out infinite;
            position: relative;
            overflow: hidden;
        }}
        .login-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']}, {theme['gradient_start']});
            background-size: 300% 100%;
            animation: shimmerBar 3s linear infinite;
        }}
        .login-card::after {{
            content: '';
            position: absolute;
            top: -1px; right: -1px; bottom: -1px; left: -1px;
            border-radius: 28px;
            background: linear-gradient(135deg, {theme['gradient_start']}20, transparent 40%, {theme['gradient_end']}15, transparent 70%);
            z-index: -1;
        }}

        /* ─── Animated Logo ───────────────────────────── */
        .login-logo-wrap {{
            display: flex;
            justify-content: center;
            margin-bottom: 1.5rem;
        }}
        .login-logo {{
            width: 80px; height: 80px;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']});
            border-radius: 22px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2.2rem;
            color: white;
            animation: floatSlow 6s ease-in-out infinite;
            box-shadow: 0 8px 40px {theme['glow_primary']};
            position: relative;
        }}
        .login-logo::after {{
            content: '';
            position: absolute;
            inset: -4px;
            border-radius: 26px;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_end']});
            z-index: -1;
            opacity: 0.3;
            filter: blur(12px);
            animation: glowPulse 4s ease-in-out infinite;
        }}

        .login-title {{
            text-align: center;
            margin: 0 0 0.25rem;
            font-size: 1.75rem;
            font-weight: 900;
            letter-spacing: -0.04em;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']});
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: gradientRotate 4s ease infinite;
        }}
        .login-sub {{
            text-align: center;
            color: {theme['muted']};
            font-size: 0.9rem;
            margin-bottom: 1.8rem;
            font-weight: 400;
            line-height: 1.6;
        }}

        /* ─── Form Inputs ─────────────────────────────── */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stTextInput input,
        .stSelectbox [data-baseweb="select"] > div {{
            background: {theme['control_bg']} !important;
            color: {theme['text']} !important;
            border: 1.5px solid {theme['border']} !important;
            border-radius: 14px !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 0.95rem !important;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
            padding: 0.15rem 0 !important;
        }}
        .stTextInput input:focus {{
            border-color: {theme['primary']} !important;
            box-shadow: 0 0 0 4px {theme['glow_primary']},
                        0 0 20px {theme['glow_primary']} !important;
        }}
        div[data-baseweb="select"] * {{
            color: {theme['text']} !important;
        }}
        .stTextInput label, .stSelectbox label {{
            font-weight: 700 !important;
            font-size: 0.78rem !important;
            letter-spacing: 0.08em !important;
            color: {theme['muted']} !important;
            text-transform: uppercase !important;
        }}

        /* ─── FUTURISTIC BUTTONS ──────────────────────── */
        .stButton > button,
        .stForm button {{
            width: 100%;
            border-radius: 16px !important;
            border: none !important;
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_mid']}, {theme['gradient_end']}) !important;
            background-size: 200% 200% !important;
            animation: gradientRotate 4s ease infinite !important;
            color: #ffffff !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 700 !important;
            font-size: 1rem !important;
            letter-spacing: 0.03em !important;
            padding: 0.85rem 1.8rem !important;
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1) !important;
            box-shadow: 0 6px 24px {theme['glow_primary']},
                        0 0 0 0 {theme['glow_primary']} !important;
            position: relative;
            overflow: hidden;
            cursor: pointer;
        }}
        .stButton > button::before,
        .stForm button::before {{
            content: '';
            position: absolute;
            top: 50%; left: 50%;
            width: 0; height: 0;
            background: rgba(255,255,255,0.25);
            border-radius: 50%;
            transform: translate(-50%, -50%);
            transition: width 0.6s ease, height 0.6s ease;
        }}
        .stButton > button:hover,
        .stForm button:hover {{
            transform: translateY(-3px) scale(1.02) !important;
            box-shadow: 0 12px 40px {theme['glow_primary']},
                        0 0 60px {theme['glow_accent']} !important;
            filter: brightness(1.1) !important;
        }}
        .stButton > button:hover::before,
        .stForm button:hover::before {{
            width: 300px;
            height: 300px;
        }}
        .stButton > button:active,
        .stForm button:active {{
            transform: translateY(0) scale(0.98) !important;
            box-shadow: 0 4px 16px {theme['glow_primary']} !important;
        }}

        /* ─── Toast Messages ──────────────────────────── */
        .stAlert {{
            border-radius: 16px !important;
            border: none !important;
            animation: fadeInUp 0.5s cubic-bezier(0.16,1,0.3,1) !important;
            backdrop-filter: blur(10px) !important;
        }}

        /* ─── Text ────────────────────────────────────── */
        .stMarkdown, .stCaption {{
            color: {theme['text']} !important;
            font-family: 'Inter', sans-serif !important;
        }}

        /* ─── Footer ──────────────────────────────────── */
        .login-footer {{
            text-align: center;
            margin-top: 2rem;
            color: {theme['muted']};
            font-size: 0.75rem;
            letter-spacing: 0.04em;
            animation: fadeInUp 1.2s ease;
        }}
        .login-footer span {{
            background: linear-gradient(135deg, {theme['gradient_start']}, {theme['gradient_end']});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
        }}

        /* ─── Divider ─────────────────────────────────── */
        .login-divider {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
            margin: 1.2rem 0;
            color: {theme['muted']};
            font-size: 0.78rem;
            font-weight: 500;
            letter-spacing: 0.05em;
        }}
        .login-divider::before, .login-divider::after {{
            content: '';
            flex: 1;
            height: 1px;
            background: linear-gradient(90deg, transparent, {theme['border']}, transparent);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _login_form() -> None:
    # Background decorations
    st.markdown(
        """
        <div class="login-bg-grid"></div>
        <div class="login-orb login-orb-1"></div>
        <div class="login-orb login-orb-2"></div>
        <div class="login-orb login-orb-3"></div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="login-card">
            <div class="login-logo-wrap">
                <div class="login-logo">🏫</div>
            </div>
            <h2 class="login-title">School Management Portal</h2>
            <p class="login-sub">Sign in to access your personalized dashboard<br>and manage everything in one place.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height: 0.8rem'></div>", unsafe_allow_html=True)

    with st.form("universal_login"):
        username = st.text_input("USERNAME", placeholder="Enter your username")
        password = st.text_input("PASSWORD", type="password", placeholder="Enter your password")
        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Sign In  →")

    if submitted:
        role = _cached_validate_user(username, password)
        if role in ROLE_TITLES:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["role"] = role
            st.success(f"✅ Welcome! Signed in as **{ROLE_TITLES[role]}**")
            st.rerun()
        elif role:
            st.error(f"⚠️ Role '{role}' is not supported in this dashboard yet")
        else:
            st.error("❌ Invalid username or password. Please try again.")

    st.markdown(
        '<p class="login-footer">Powered by <span>Civics School Management System</span></p>',
        unsafe_allow_html=True,
    )


def _logout() -> None:
    st.session_state.clear()
    st.rerun()


def main() -> None:
    if get_script_run_ctx() is None:
        print("Please run this app with Streamlit:")
        print("streamlit run universal_dashboard.py")
        return

    st.set_page_config(
        page_title="School Management Portal",
        page_icon="🏫",
        layout="wide",
    )

    selected_theme = st.session_state.get("login_theme", "Dark")
    with st.sidebar:
        st.markdown("### ⚙️ Portal Settings")
        dark_mode = st.toggle(
            "🌙 Dark mode",
            value=(selected_theme == "Dark"),
            key="login_dark_mode",
        )
        st.session_state["login_theme"] = "Dark" if dark_mode else "Light"

    _apply_login_theme(st.session_state.get("login_theme", "Dark"))

    if not st.session_state.get("logged_in"):
        _login_form()
        return

    username = st.session_state.get("username", "")
    role = st.session_state.get("role", "")

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        _logout()

    if role == "admin":
        render_admin_dashboard(username=username, show_logout=False)
        return

    if role == "principal":
        render_principal_dashboard(username=username, show_logout=False)
        return

    st.error(f"Unknown role '{role}'. Please logout and login again.")


if __name__ == "__main__":
    main()
