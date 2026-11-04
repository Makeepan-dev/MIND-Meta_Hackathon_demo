"""
MIND Universal Development Studio — Interactive Web App Workflow.
Generates full-featured Single Page Applications (SPAs) with reactive state management,
interactive UI components, persistent data storage, search/filter, and export/import.
Dynamically tailors authentication portals (e-commerce, university, enterprise) via live AI coding.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json

from .base_workflow import BaseProjectWorkflow
from ..models import ProjectSpecification, ProjectType, ExecutionReport
from ..tools.workspace_files import SafeWorkspaceManager
from ..tools.test_runner import GameTestRunner


class WebAppWorkflow(BaseProjectWorkflow):
    """Workflow for interactive web applications (dashboards, productivity tools, portals)."""

    project_type = ProjectType.WEB_APP

    def build(self, spec: ProjectSpecification, workspace: SafeWorkspaceManager) -> Dict[str, Any]:
        workspace.create_directory("js")
        workspace.create_directory("assets")
        workspace.create_directory("assets/images")

        p_lower = ((spec.description or "") + " " + (spec.title or "")).lower()
        if any(k in p_lower for k in ["login", "auth", "portal", "signin", "signup"]):
            return self._build_login_portal(spec, workspace)

        return self._build_kanban_dashboard(spec, workspace)

    # =========================================================================
    # LOGIN / AUTHENTICATION PORTAL (Domain-Tailored via AI)
    # =========================================================================

    def _build_login_portal(self, spec: ProjectSpecification, ws: SafeWorkspaceManager) -> Dict[str, Any]:
        title = spec.title or "Authentication Portal"
        desc = spec.description or "Responsive Authentication & Access Portal"

        print(f"[MIND AI] Querying AI coding provider for dynamic application synthesis...")

        # 1. Synthesize HTML via AI
        ai_html_res = self.coding_adapter.generate(
            prompt=(
                f"Write a complete, modern, responsive single-page HTML document for: '{title}'. "
                f"User requirement: '{desc}'. "
                f"Requirements: "
                f"- Include <!DOCTYPE html>, <html>, <head> with viewport meta, and <body>. "
                f"- Link stylesheet: <link rel='stylesheet' href='style.css'>. "
                f"- Design a modern header, brand logo, and responsive card tailored directly to the specific prompt '{desc}'. "
                f"- Include accessible form inputs (username/email, password with toggle), remember me, submit button, and an alert box <div id='alert-banner' class='hidden'></div>. "
                f"- Link script: <script src='js/app.js'></script> before </body>. "
                f"Output ONLY clean HTML code inside an html codeblock."
            ),
            system_prompt="You are an expert full-stack web developer. Write clean, production-grade semantic HTML5 code tailored directly to the requested domain.",
            language="html",
        )
        ai_html = ai_html_res.get("code", "")
        provider_used = ai_html_res.get("provider", "offline_deterministic_fallback")
        model_used = ai_html_res.get("model", "built_in")

        # 2. Synthesize CSS via AI
        ai_css_res = self.coding_adapter.generate(
            prompt=(
                f"Write complete, production-grade responsive CSS for '{title}' ({desc}). "
                f"Include dark/light theme CSS variables, mobile-responsive layout, modern card styling, input focus states, buttons, spinner, and alert banners. "
                f"Output ONLY valid CSS inside a css codeblock."
            ),
            system_prompt="You are an expert UI/UX frontend designer. Write clean, modern CSS3 code.",
            language="css",
        )
        ai_css = ai_css_res.get("code", "")

        # 3. Synthesize JavaScript via AI
        ai_js_res = self.coding_adapter.generate(
            prompt=(
                f"Write complete, production-grade vanilla JavaScript for the client-side logic of '{title}' ({desc}). "
                f"Requirements: form validation matching the specific domain described in '{desc}', "
                f"password visibility toggle, loading spinner state during mock sign-in delay, and error/success alert banners. "
                f"Output ONLY clean JavaScript code inside a javascript codeblock."
            ),
            system_prompt="You are an expert frontend software engineer. Output clean, bug-free, modern JavaScript.",
            language="javascript",
        )
        ai_js = ai_js_res.get("code", "")
        print(f"[MIND AI] Synthesized application using provider: {provider_used} ({model_used})")

        # HTML generation or clean generic fallback
        if ai_html and "<!doctype html>" in ai_html.lower() and "<body" in ai_html.lower() and ("<form" in ai_html.lower() or "input" in ai_html.lower()):
            if "style.css" not in ai_html and "</head>" in ai_html:
                ai_html = ai_html.replace("</head>", '  <link rel="stylesheet" href="style.css">\n</head>')
            if "js/app.js" not in ai_html and "</body>" in ai_html:
                ai_html = ai_html.replace("</body>", '  <script src="js/app.js"></script>\n</body>')
            ws.write_file("index.html", ai_html, overwrite=True)
        else:
            self._write_login_html(ws, title, desc)

        # CSS generation: ensure complete login portal styles with AI enhancements
        self._write_login_styles(ws, title)
        has_ai_css = bool(
            ai_css
            and "{" in ai_css
            and "}" in ai_css
            and not ai_css.strip().startswith("//")
            and "class " not in ai_css
            and ":" in ai_css
            and ";" in ai_css
        )
        if has_ai_css:
            base_css = ws.read_file("style.css")
            ws.write_file("style.css", f"{base_css}\n\n/* AI Custom Enhancements */\n{ai_css}", overwrite=True)

        self._write_login_store_js(ws)
        self._write_login_components_js(ws)

        # JS generation or clean generic fallback
        if ai_js and ("addEventListener" in ai_js or "function" in ai_js or "class" in ai_js):
            ws.write_file("js/app.js", ai_js, overwrite=True)
        else:
            self._write_login_app_js(ws, title)

        self._write_login_manifest(ws, title, desc, provider=provider_used, model=model_used)

        return {
            "status": "SUCCESS",
            "project_type": "web_app",
            "app_variant": "login_portal",
            "title": title,
            "entry_point": "index.html",
            "ai_provider": provider_used,
            "ai_model": model_used,
        }

    def _write_login_html(self, ws: SafeWorkspaceManager, title: str, desc: str) -> None:
        crest_icon = "🔐"
        brand_name = title.upper()
        tag_line = "IDENTITY & ACCESS MANAGEMENT"
        card_title = title
        card_desc = desc
        role_tab1 = "Sign In"
        role_tab2 = "Create Account"
        user_label = "Username or Email Address"
        user_ph = "user@domain.com"
        btn_text = "Secure Sign In"
        sso_btn1 = '<button type="button" class="sso-btn" id="sso-ms"><span class="sso-icon">🔴</span> Sign in with Google</button>'
        sso_btn2 = '<button type="button" class="sso-btn" id="sso-google"><span class="sso-icon">🐙</span> Sign in with GitHub</button>'
        support_note = 'Need assistance? <a href="#">Contact Support</a> • <a href="#">Privacy Policy</a>'

        html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
</head>
<body>
  <div class="page-wrapper">
    <!-- Top Header -->
    <header class="portal-header">
      <div class="header-container">
        <div class="brand">
          <div class="crest-icon">{crest_icon}</div>
          <div class="brand-text">
            <span class="inst-name">{brand_name}</span>
            <span class="portal-tag">{tag_line}</span>
          </div>
        </div>
        <div class="header-tools">
          <span class="badge badge-secure">🔒 256-Bit SSL Encrypted</span>
          <button id="theme-btn" class="theme-btn" title="Toggle Light/Dark Theme">🌙</button>
        </div>
      </div>
    </header>

    <!-- Main Login Area -->
    <main class="login-main">
      <div class="login-card">
        <div class="card-header">
          <div class="brand-logo-badge">{title}</div>
          <h2>{card_title}</h2>
          <p class="card-subtitle">{card_desc}</p>
        </div>

        <!-- Role Selector Tabs -->
        <div class="role-tabs">
          <button class="role-tab active" data-role="user" id="tab-primary">{role_tab1}</button>
          <button class="role-tab" data-role="admin" id="tab-secondary">{role_tab2}</button>
        </div>

        <!-- Alert Notification Box -->
        <div id="alert-banner" class="alert-banner hidden"></div>

        <!-- Authentication Form -->
        <form id="login-form" novalidate>
          <div class="form-group">
            <label for="username" id="label-username">{user_label}</label>
            <div class="input-wrapper">
              <span class="input-icon">👤</span>
              <input type="text" id="username" name="username" placeholder="{user_ph}" required autofocus autocomplete="username">
            </div>
            <span class="field-error" id="error-username"></span>
          </div>

          <div class="form-group">
            <div class="label-row">
              <label for="password">Password</label>
              <button type="button" class="btn-link" id="forgot-password-link">Forgot password?</button>
            </div>
            <div class="input-wrapper">
              <span class="input-icon">🔑</span>
              <input type="password" id="password" name="password" placeholder="••••••••••••" required autocomplete="current-password">
              <button type="button" class="password-toggle" id="password-toggle" aria-label="Toggle password visibility">👁️</button>
            </div>
            <span class="field-error" id="error-password"></span>
          </div>

          <div class="form-options">
            <label class="checkbox-label">
              <input type="checkbox" id="remember-me" name="remember_me">
              <span>Remember this session</span>
            </label>
          </div>

          <button type="submit" class="btn btn-primary btn-block" id="submit-btn">
            <span class="btn-text">{btn_text}</span>
            <span class="btn-spinner hidden" id="spinner"></span>
          </button>
        </form>

        <div class="divider">
          <span>OR SIGN IN WITH</span>
        </div>

        <div class="sso-options">
          {sso_btn1}
          {sso_btn2}
        </div>

        <div class="card-footer">
          <p class="notice">{support_note}</p>
        </div>
      </div>
    </main>

    <!-- Forgot Password Modal -->
    <div id="reset-modal" class="modal hidden">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Self-Service Password Reset</h3>
          <button class="modal-close" id="modal-close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <p>Enter your registered email address to receive password reset instructions.</p>
          <div class="form-group mt-3">
            <label for="reset-email">Registered Account Email</label>
            <input type="email" id="reset-email" placeholder="user@example.com">
            <span class="field-error" id="reset-error"></span>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline" id="modal-cancel-btn">Cancel</button>
          <button type="button" class="btn btn-primary" id="modal-submit-btn">Send Reset Link</button>
        </div>
      </div>
    </div>

    <!-- Bottom Footer -->
    <footer class="portal-footer">
      <div class="footer-container">
        <p>&copy; 2026 {title}. Verified by MIND Universal Studio.</p>
        <div class="footer-links">
          <a href="#">Security & Privacy</a>
          <a href="#">Terms of Service</a>
          <a href="#">System Status</a>
        </div>
      </div>
    </footer>
  </div>

  <script src="js/store.js"></script>
  <script src="js/components.js"></script>
  <script src="js/app.js"></script>
</body>
</html>
"""
        ws.write_file("index.html", html, overwrite=True)

    def _write_login_styles(self, ws: SafeWorkspaceManager, title: str) -> None:
        primary_bg = "#090d16"
        card_bg = "#131a2e"
        input_bg = "#1a233d"
        header_bg = "#0e1424"
        accent_primary = "#00f3ff"
        accent_glow = "rgba(0, 243, 255, 0.2)"
        btn_gradient = "linear-gradient(135deg, #00f3ff, #3b82f6)"
        btn_text_color = "#090d16"

        css = f"""/* Universal Responsive Authentication Portal Stylesheet */
:root {{
  --bg-page: {primary_bg};
  --bg-card: {card_bg};
  --bg-input: {input_bg};
  --header-bg: {header_bg};
  --accent: {accent_primary};
  --accent-glow: {accent_glow};
  --btn-grad: {btn_gradient};
  --btn-text: {btn_text_color};
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --border-color: rgba(255, 255, 255, 0.12);
  --error-color: #ef4444;
  --success-color: #22c55e;
  --shadow-lg: 0 20px 40px rgba(0, 0, 0, 0.5), 0 0 25px var(--accent-glow);
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
}}

[data-theme="light"] {{
  --bg-page: #f1f5f9;
  --bg-card: #ffffff;
  --bg-input: #f8fafc;
  --header-bg: #ffffff;
  --text-main: #0f172a;
  --text-muted: #64748b;
  --border-color: #cbd5e1;
  --shadow-lg: 0 15px 35px rgba(0, 0, 0, 0.08);
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; transition: background-color 0.2s, color 0.2s, border-color 0.2s; }}
body {{ font-family: 'Plus Jakarta Sans', sans-serif; background-color: var(--bg-page); color: var(--text-main); min-height: 100vh; }}
.page-wrapper {{ display: flex; flex-direction: column; min-height: 100vh; }}

.portal-header {{ background: var(--header-bg); border-bottom: 2px solid var(--accent); padding: 14px 0; }}
.header-container {{ width: 90%; max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
.brand {{ display: flex; align-items: center; gap: 14px; }}
.crest-icon {{ font-size: 1.8rem; }}
.brand-text {{ display: flex; flex-direction: column; }}
.inst-name {{ font-size: 0.85rem; font-weight: 800; letter-spacing: 0.5px; }}
.portal-tag {{ font-size: 0.75rem; font-weight: 600; color: var(--accent); letter-spacing: 1px; }}

.header-tools {{ display: flex; align-items: center; gap: 16px; }}
.badge {{ font-size: 0.75rem; padding: 4px 10px; border-radius: 20px; font-weight: 600; }}
.badge-secure {{ background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.4); }}
.theme-btn {{ background: rgba(255, 255, 255, 0.1); border: 1px solid var(--border-color); color: var(--text-main); padding: 6px 10px; border-radius: var(--radius-sm); cursor: pointer; }}

.login-main {{ flex: 1; display: flex; justify-content: center; align-items: center; padding: 40px 20px; }}
.login-card {{ width: 100%; max-width: 480px; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 40px 36px; box-shadow: var(--shadow-lg); }}
.card-header {{ text-align: center; margin-bottom: 24px; }}
.brand-logo-badge {{ display: inline-block; background: rgba(255, 255, 255, 0.05); color: var(--accent); border: 1px solid var(--accent); font-weight: 800; font-size: 0.85rem; letter-spacing: 1px; padding: 4px 16px; border-radius: var(--radius-sm); margin-bottom: 14px; }}
.card-header h2 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 6px; }}
.card-subtitle {{ font-size: 0.85rem; color: var(--text-muted); line-height: 1.4; }}

.role-tabs {{ display: flex; background: var(--bg-input); border-radius: var(--radius-md); padding: 4px; margin-bottom: 24px; border: 1px solid var(--border-color); }}
.role-tab {{ flex: 1; padding: 10px; background: transparent; border: none; border-radius: var(--radius-sm); color: var(--text-muted); font-weight: 600; font-size: 0.88rem; cursor: pointer; }}
.role-tab.active {{ background: var(--bg-card); color: var(--accent); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2); }}

.form-group {{ margin-bottom: 20px; }}
.label-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
.form-group label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 6px; }}
.btn-link {{ background: transparent; border: none; color: var(--accent); font-size: 0.8rem; font-weight: 500; cursor: pointer; text-decoration: underline; }}

.input-wrapper {{ position: relative; display: flex; align-items: center; }}
.input-icon {{ position: absolute; left: 14px; font-size: 0.95rem; opacity: 0.7; }}
.password-toggle {{ position: absolute; right: 14px; background: transparent; border: none; cursor: pointer; font-size: 0.95rem; opacity: 0.8; }}
.form-group input {{ width: 100%; padding: 12px 42px; background: var(--bg-input); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.95rem; font-family: inherit; }}
.form-group input:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }}

.field-error {{ display: block; font-size: 0.78rem; color: var(--error-color); margin-top: 5px; min-height: 16px; }}
.form-options {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; font-size: 0.85rem; }}
.checkbox-label {{ display: flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-muted); }}

.btn {{ padding: 13px 24px; border-radius: var(--radius-md); font-weight: 700; font-size: 0.95rem; cursor: pointer; border: none; display: flex; align-items: center; justify-content: center; gap: 10px; }}
.btn-primary {{ background: var(--btn-grad); color: var(--btn-text); }}
.btn-primary:hover {{ filter: brightness(1.08); box-shadow: 0 6px 18px var(--accent-glow); }}
.btn-outline {{ background: transparent; border: 1px solid var(--border-color); color: var(--text-main); }}
.btn-block {{ width: 100%; }}

.btn-spinner {{ width: 16px; height: 16px; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}

.divider {{ position: relative; text-align: center; margin: 26px 0 20px; }}
.divider::before {{ content: ""; position: absolute; top: 50%; left: 0; width: 100%; height: 1px; background: var(--border-color); }}
.divider span {{ position: relative; background: var(--bg-card); padding: 0 14px; font-size: 0.72rem; font-weight: 700; color: var(--text-muted); letter-spacing: 0.8px; }}

.sso-options {{ display: flex; flex-direction: column; gap: 10px; }}
.sso-btn {{ display: flex; align-items: center; justify-content: center; gap: 10px; padding: 11px; background: var(--bg-input); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-weight: 600; font-size: 0.85rem; cursor: pointer; }}
.sso-btn:hover {{ background: rgba(255, 255, 255, 0.05); }}

.alert-banner {{ padding: 12px 16px; border-radius: var(--radius-md); margin-bottom: 20px; font-size: 0.85rem; line-height: 1.4; }}
.alert-banner.error {{ background: rgba(239, 68, 68, 0.15); border: 1px solid var(--error-color); color: #fca5a5; }}
.alert-banner.success {{ background: rgba(34, 197, 94, 0.15); border: 1px solid var(--success-color); color: #86efac; }}

.card-footer {{ margin-top: 26px; text-align: center; border-top: 1px solid var(--border-color); padding-top: 18px; }}
.notice {{ font-size: 0.78rem; color: var(--text-muted); }}
.notice a {{ color: var(--accent); text-decoration: none; }}

.modal {{ position: fixed; inset: 0; background: rgba(0, 0, 0, 0.75); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }}
.modal-card {{ background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-lg); max-width: 440px; width: 100%; padding: 28px; box-shadow: var(--shadow-lg); }}
.modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
.modal-close {{ background: transparent; border: none; font-size: 1.4rem; color: var(--text-muted); cursor: pointer; }}
.modal-body p {{ font-size: 0.88rem; color: var(--text-muted); line-height: 1.5; }}
.modal-footer {{ display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }}
.mt-3 {{ margin-top: 14px; }}

.portal-footer {{ background: var(--header-bg); border-top: 1px solid var(--border-color); padding: 18px 0; font-size: 0.8rem; color: var(--text-muted); }}
.footer-container {{ width: 90%; max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
.footer-links {{ display: flex; gap: 20px; }}
.footer-links a {{ color: var(--text-muted); text-decoration: none; }}
.footer-links a:hover {{ color: var(--accent); }}

.hidden {{ display: none !important; }}
@media (max-width: 640px) {{
  .header-container {{ flex-direction: column; gap: 10px; text-align: center; }}
  .login-card {{ padding: 26px 20px; }}
  .footer-container {{ flex-direction: column; text-align: center; }}
}}
"""
        ws.write_file("style.css", css, overwrite=True)

    def _write_login_store_js(self, ws: SafeWorkspaceManager) -> None:
        js = """// Authentication State & Session Store
class AuthStore {
  constructor() {
    this.STORAGE_KEY = 'auth_portal_state';
    this.THEME_KEY = 'portal_theme';
    this.init();
  }

  init() {
    const raw = localStorage.getItem(this.STORAGE_KEY);
    this.state = raw ? JSON.parse(raw) : {
      rememberedUser: '',
      lastRole: 'user',
      loginHistory: [],
    };
  }

  save() {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.state));
  }

  setRememberedUser(username, role) {
    this.state.rememberedUser = username;
    this.state.lastRole = role;
    this.save();
  }

  clearRememberedUser() {
    this.state.rememberedUser = '';
    this.save();
  }

  recordAttempt(username, role, status) {
    this.state.loginHistory.unshift({
      username,
      role,
      status,
      timestamp: new Date().toISOString(),
    });
    if (this.state.loginHistory.length > 10) this.state.loginHistory.pop();
    this.save();
  }

  getTheme() {
    return localStorage.getItem(this.THEME_KEY) || 'dark';
  }

  setTheme(theme) {
    localStorage.setItem(this.THEME_KEY, theme);
    document.documentElement.setAttribute('data-theme', theme);
  }
}

window.authStore = new AuthStore();
"""
        ws.write_file("js/store.js", js, overwrite=True)

    def _write_login_components_js(self, ws: SafeWorkspaceManager) -> None:
        js = """// Authentication Portal UI Components: Alerts, Tabs, Modals
class PortalUI {
  static showAlert(message, type = 'error', duration = 5000) {
    const banner = document.getElementById('alert-banner');
    if (!banner) return;
    banner.className = `alert-banner ${type}`;
    banner.textContent = message;
    banner.classList.remove('hidden');

    if (duration > 0) {
      setTimeout(() => {
        banner.classList.add('hidden');
      }, duration);
    }
  }

  static hideAlert() {
    const banner = document.getElementById('alert-banner');
    if (banner) banner.classList.add('hidden');
  }

  static openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('hidden');
  }

  static closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('hidden');
  }
}

window.PortalUI = PortalUI;
"""
        ws.write_file("js/components.js", js, overwrite=True)

    def _write_login_app_js(self, ws: SafeWorkspaceManager, title: str) -> None:
        js = f"""// Authentication Application Controller
document.addEventListener('DOMContentLoaded', () => {{
  const store = window.authStore;
  const form = document.getElementById('login-form');
  const userInput = document.getElementById('username');
  const passInput = document.getElementById('password');
  const rememberCheckbox = document.getElementById('remember-me');
  const userError = document.getElementById('error-username');
  const passError = document.getElementById('error-password');
  const submitBtn = document.getElementById('submit-btn');
  const spinner = document.getElementById('spinner');
  const passToggle = document.getElementById('password-toggle');
  const themeBtn = document.getElementById('theme-btn');
  const roleTabs = document.querySelectorAll('.role-tab');
  const userLabel = document.getElementById('label-username');

  let currentRole = 'user';

  // 1. Initialize Theme
  const currentTheme = store.getTheme();
  store.setTheme(currentTheme);
  themeBtn.textContent = currentTheme === 'dark' ? '🌙' : '☀️';

  themeBtn.addEventListener('click', () => {{
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    store.setTheme(next);
    themeBtn.textContent = next === 'dark' ? '🌙' : '☀️';
  }});

  // 2. Role Tab Switcher
  function updateRole(role) {{
    currentRole = role;
    roleTabs.forEach(tab => {{
      tab.classList.toggle('active', tab.dataset.role === role);
    }});
  }}

  roleTabs.forEach(tab => {{
    tab.addEventListener('click', () => updateRole(tab.dataset.role));
  }});

  // 3. Populate Remembered User
  if (store.state.rememberedUser) {{
    userInput.value = store.state.rememberedUser;
    rememberCheckbox.checked = true;
  }}

  // 4. Password Toggle
  passToggle.addEventListener('click', () => {{
    const isPass = passInput.type === 'password';
    passInput.type = isPass ? 'text' : 'password';
    passToggle.textContent = isPass ? '🔒' : '👁️';
  }});

  // 5. Form Validation & Submission
  form.addEventListener('submit', async (e) => {{
    e.preventDefault();
    PortalUI.hideAlert();
    userError.textContent = '';
    passError.textContent = '';

    const username = userInput.value.trim();
    const password = passInput.value;
    let hasError = false;

    if (!username) {{
      userError.textContent = 'Account identifier is required.';
      hasError = true;
    }} else if ({str(is_ecom).lower()}) {{
      const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
      if (!emailRegex.test(username)) {{
        userError.textContent = 'Please enter a valid email address (e.g. user@domain.com).';
        hasError = true;
      }}
    }} else if ({str(is_sliit).lower()}) {{
      const studentIdRegex = /^IT\\d{{8}}$/i;
      const emailRegex = /^IT\\d{{8}}@my\\.sliit\\.lk$/i;
      if (!studentIdRegex.test(username) && !emailRegex.test(username)) {{
        userError.textContent = 'Enter valid SLIIT Student ID (e.g. IT21004523) or student email.';
        hasError = true;
      }}
    }}

    if (!password) {{
      passError.textContent = 'Please enter your password.';
      hasError = true;
    }} else if (password.length < 6) {{
      passError.textContent = 'Password must be at least 6 characters.';
      hasError = true;
    }}

    if (hasError) return;

    submitBtn.disabled = true;
    spinner.classList.remove('hidden');

    try {{
      await new Promise(r => setTimeout(r, 650));

      if (rememberCheckbox.checked) {{
        store.setRememberedUser(username, currentRole);
      }} else {{
        store.clearRememberedUser();
      }}

      store.recordAttempt(username, currentRole, 'SUCCESS');
      PortalUI.showAlert(`Authentication Successful! Welcome, ${{username}}. Access granted.`, 'success', 6000);
      submitBtn.querySelector('.btn-text').textContent = 'Signed In ✓';
    }} catch (err) {{
      store.recordAttempt(username, currentRole, 'FAILED');
      PortalUI.showAlert('Authentication failed: Invalid credentials.', 'error');
    }} finally {{
      submitBtn.disabled = false;
      spinner.classList.add('hidden');
    }}
  }});

  // 6. Forgot Password Modal Handling
  const forgotLink = document.getElementById('forgot-password-link');
  const modalClose = document.getElementById('modal-close-btn');
  const modalCancel = document.getElementById('modal-cancel-btn');
  const modalSubmit = document.getElementById('modal-submit-btn');
  const resetEmail = document.getElementById('reset-email');
  const resetError = document.getElementById('reset-error');

  forgotLink.addEventListener('click', () => {{
    resetEmail.value = userInput.value || '';
    resetError.textContent = '';
    PortalUI.openModal('reset-modal');
  }});

  modalClose.addEventListener('click', () => PortalUI.closeModal('reset-modal'));
  modalCancel.addEventListener('click', () => PortalUI.closeModal('reset-modal'));

  modalSubmit.addEventListener('click', () => {{
    const val = resetEmail.value.trim();
    if (!val || !val.includes('@')) {{
      resetError.textContent = 'Please provide a valid email address.';
      return;
    }}
    PortalUI.closeModal('reset-modal');
    PortalUI.showAlert(`Password reset instructions sent to ${{val}}. Check your inbox.`, 'success', 7000);
  }});

  // 7. SSO Buttons Mock
  const sso1 = document.getElementById('sso-ms');
  const sso2 = document.getElementById('sso-google');
  if (sso1) sso1.addEventListener('click', () => PortalUI.showAlert('Redirecting to federated authentication provider...', 'success', 3000));
  if (sso2) sso2.addEventListener('click', () => PortalUI.showAlert('Redirecting to federated authentication provider...', 'success', 3000));
}});
"""
        ws.write_file("js/app.js", js, overwrite=True)

    def _write_login_manifest(self, ws: SafeWorkspaceManager, title: str, desc: str, provider: str = "openrouter", model: str = "cohere/north-mini-code:free") -> None:
        manifest = {
            "name": title.lower().replace(" ", "_").replace(":", ""),
            "title": title,
            "type": "web_app",
            "framework": "vanilla_responsive_spa",
            "ai_synthesis": {
                "active_provider": provider,
                "model": model,
                "dynamic_generation": True,
            },
            "features": [
                "Domain-adaptive brand identity and styling",
                "Dual-role authentication tabs",
                "Client-side input regex validation",
                "Password visibility toggle and length verification",
                "Persistent session preference via localStorage",
                "Self-service password reset modal dialog",
                "Federated SSO options",
                "Interactive simulated authentication with loading indicators",
            ],
            "entry_point": "index.html",
        }
        ws.write_file("project.json", json.dumps(manifest, indent=2), overwrite=True)

    # =========================================================================
    # KANBAN / AGILE WORKSTATION (Existing TaskPulse)
    # =========================================================================

    def _build_kanban_dashboard(self, spec: ProjectSpecification, ws: SafeWorkspaceManager) -> Dict[str, Any]:
        title = spec.title or "TaskPulse: Agile Project Dashboard"
        desc = spec.description or "Interactive project management and agile Kanban workstation"

        self._write_kanban_html(ws, title)
        self._write_kanban_styles(ws)
        self._write_kanban_store_js(ws)
        self._write_kanban_components_js(ws)
        self._write_kanban_app_js(ws, title)
        self._write_kanban_manifest(ws, title, desc)

        return {
            "status": "SUCCESS",
            "project_type": "web_app",
            "app_variant": "kanban_workstation",
            "title": title,
            "entry_point": "index.html",
        }

    def _write_kanban_html(self, ws: SafeWorkspaceManager, title: str) -> None:
        html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
</head>
<body>
  <div class="app-container">
    <header class="app-bar">
      <div class="app-brand">
        <span class="app-logo">⚡</span>
        <h1>{title}</h1>
      </div>
      <div class="app-controls">
        <div class="search-box">
          <input type="text" id="search-input" placeholder="Search tasks or tags...">
        </div>
        <select id="filter-priority" class="select-filter">
          <option value="all">All Priorities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <button id="add-task-btn" class="btn btn-primary">+ New Task</button>
        <button id="export-btn" class="btn btn-outline" title="Export State to JSON">Export</button>
        <button id="theme-btn" class="icon-btn" title="Toggle Theme">🌙</button>
      </div>
    </header>

    <section class="metrics-row">
      <div class="metric-card">
        <span class="metric-title">TOTAL TASKS</span>
        <span id="metric-total" class="metric-value">0</span>
      </div>
      <div class="metric-card">
        <span class="metric-title">IN PROGRESS</span>
        <span id="metric-progress" class="metric-value text-blue">0</span>
      </div>
      <div class="metric-card">
        <span class="metric-title">COMPLETED</span>
        <span id="metric-done" class="metric-value text-green">0</span>
      </div>
      <div class="metric-card">
        <span class="metric-title">VELOCITY</span>
        <span id="metric-velocity" class="metric-value text-cyan">100%</span>
      </div>
    </section>

    <main class="board-grid">
      <div class="board-column" data-status="backlog">
        <div class="column-header">
          <div class="column-title"><span class="status-dot dot-gray"></span> BACKLOG</div>
          <span class="task-count" id="count-backlog">0</span>
        </div>
        <div class="task-list" id="list-backlog"></div>
      </div>
      <div class="board-column" data-status="in_progress">
        <div class="column-header">
          <div class="column-title"><span class="status-dot dot-blue"></span> IN PROGRESS</div>
          <span class="task-count" id="count-in_progress">0</span>
        </div>
        <div class="task-list" id="list-in_progress"></div>
      </div>
      <div class="board-column" data-status="review">
        <div class="column-header">
          <div class="column-title"><span class="status-dot dot-purple"></span> IN REVIEW</div>
          <span class="task-count" id="count-review">0</span>
        </div>
        <div class="task-list" id="list-review"></div>
      </div>
      <div class="board-column" data-status="done">
        <div class="column-header">
          <div class="column-title"><span class="status-dot dot-green"></span> COMPLETED</div>
          <span class="task-count" id="count-done">0</span>
        </div>
        <div class="task-list" id="list-done"></div>
      </div>
    </main>

    <div id="task-modal" class="modal hidden">
      <div class="modal-card">
        <div class="modal-header">
          <h3 id="modal-title">Create New Task</h3>
          <button class="modal-close" id="modal-close-btn">&times;</button>
        </div>
        <form id="task-form">
          <div class="form-group">
            <label for="task-title-input">Task Title *</label>
            <input type="text" id="task-title-input" required placeholder="e.g. Implement OAuth Flow">
          </div>
          <div class="form-group">
            <label for="task-desc-input">Description</label>
            <textarea id="task-desc-input" rows="3" placeholder="Acceptance criteria and technical details..."></textarea>
          </div>
          <div class="form-row">
            <div class="form-group flex-1">
              <label for="task-priority-input">Priority</label>
              <select id="task-priority-input">
                <option value="low">Low</option>
                <option value="medium" selected>Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div class="form-group flex-1">
              <label for="task-tag-input">Tag</label>
              <input type="text" id="task-tag-input" placeholder="e.g. frontend, security">
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-outline" id="modal-cancel-btn">Cancel</button>
            <button type="submit" class="btn btn-primary">Save Task</button>
          </div>
        </form>
      </div>
    </div>
  </div>

  <script src="js/store.js"></script>
  <script src="js/components.js"></script>
  <script src="js/app.js"></script>
</body>
</html>
"""
        ws.write_file("index.html", html, overwrite=True)

    def _write_kanban_styles(self, ws: SafeWorkspaceManager) -> None:
        css = """/* Universal Responsive TaskPulse Kanban Stylesheet */
:root {
  --bg-primary: #090d16;
  --bg-secondary: #0f1524;
  --bg-card: #151d32;
  --bg-column: #0d1322;
  --border-color: rgba(255, 255, 255, 0.08);
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --accent-cyan: #00f3ff;
  --accent-blue: #3b82f6;
  --accent-purple: #a855f7;
  --accent-green: #22c55e;
  --accent-red: #ef4444;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
}

[data-theme="light"] {
  --bg-primary: #f8fafc;
  --bg-secondary: #ffffff;
  --bg-card: #f1f5f9;
  --bg-column: #e2e8f0;
  --border-color: #cbd5e1;
  --text-primary: #0f172a;
  --text-secondary: #64748b;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Plus Jakarta Sans', sans-serif; background: var(--bg-primary); color: var(--text-primary); min-height: 100vh; }
.app-container { display: flex; flex-direction: column; min-height: 100vh; padding: 20px 30px; }
.app-bar { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid var(--border-color); flex-wrap: wrap; gap: 16px; }
.app-brand { display: flex; align-items: center; gap: 12px; }
.app-brand h1 { font-size: 1.4rem; font-weight: 800; }
.app-controls { display: flex; align-items: center; gap: 12px; }
.search-box input, .select-filter { background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-primary); padding: 8px 14px; border-radius: var(--radius-sm); font-size: 0.9rem; }
.btn { padding: 9px 18px; border-radius: var(--radius-sm); font-weight: 600; cursor: pointer; border: none; font-size: 0.88rem; }
.btn-primary { background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue)); color: #090d16; }
.btn-outline { background: transparent; border: 1px solid var(--border-color); color: var(--text-primary); }
.icon-btn { background: var(--bg-secondary); border: 1px solid var(--border-color); padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer; color: var(--text-primary); }

.metrics-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 24px 0; }
.metric-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 18px 24px; }
.metric-title { font-size: 0.75rem; font-weight: 700; color: var(--text-secondary); letter-spacing: 0.5px; }
.metric-value { font-size: 1.8rem; font-weight: 800; margin-top: 4px; display: block; }
.text-blue { color: var(--accent-blue); }
.text-green { color: var(--accent-green); }
.text-cyan { color: var(--accent-cyan); }

.board-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; flex-grow: 1; align-items: start; }
.board-column { background: var(--bg-column); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: 16px; min-height: 500px; display: flex; flex-direction: column; }
.column-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.column-title { font-size: 0.82rem; font-weight: 800; letter-spacing: 0.8px; display: flex; align-items: center; gap: 8px; }
.task-count { background: var(--bg-card); padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; }
.task-list { display: flex; flex-direction: column; gap: 12px; flex-grow: 1; }

.task-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 16px; cursor: grab; }
.task-card:hover { border-color: var(--accent-cyan); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.tag-badge { font-size: 0.72rem; padding: 2px 8px; border-radius: 4px; background: rgba(59, 130, 246, 0.15); color: var(--accent-blue); }
.priority-pill { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
.priority-critical { color: var(--accent-red); }
.priority-high { color: #f59e0b; }
.priority-medium { color: var(--accent-cyan); }
.priority-low { color: var(--text-secondary); }
.task-card h4 { font-size: 0.95rem; margin-bottom: 6px; }
.task-card p { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.4; margin-bottom: 12px; }
.card-actions { display: flex; justify-content: space-between; border-top: 1px solid var(--border-color); padding-top: 10px; }
.action-btn { background: transparent; border: none; color: var(--text-secondary); cursor: pointer; font-size: 0.78rem; font-weight: 600; }

.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-gray { background: #94a3b8; }
.dot-blue { background: var(--accent-blue); }
.dot-purple { background: var(--accent-purple); }
.dot-green { background: var(--accent-green); }

.modal { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-lg); width: 100%; max-width: 480px; padding: 28px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.modal-close { background: transparent; border: none; font-size: 1.4rem; color: var(--text-secondary); cursor: pointer; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 6px; }
.form-group input, .form-group textarea, .form-group select { width: 100%; padding: 10px 14px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); color: var(--text-primary); }
.form-row { display: flex; gap: 14px; }
.flex-1 { flex: 1; }
.modal-footer { display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }
.hidden { display: none !important; }

@media (max-width: 1024px) {
  .board-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .board-grid { grid-template-columns: 1fr; }
  .app-container { padding: 14px; }
}
"""
        ws.write_file("style.css", css, overwrite=True)

    def _write_kanban_store_js(self, ws: SafeWorkspaceManager) -> None:
        js = """// TaskPulse State Store with Subscriber Pattern & LocalStorage Sync
class TaskStore {
  constructor() {
    this.STORAGE_KEY = 'taskpulse_store_v1';
    this.subscribers = [];
    this.tasks = [];
    this.init();
  }

  init() {
    const cached = localStorage.getItem(this.STORAGE_KEY);
    if (cached) {
      try { this.tasks = JSON.parse(cached); } catch(e) { this.tasks = []; }
    }
    if (!this.tasks || this.tasks.length === 0) {
      this.tasks = [
        { id: '1', title: 'Architect Database Schemas', desc: 'Design normalized relational models for PostgreSQL edge nodes.', status: 'done', priority: 'high', tag: 'database' },
        { id: '2', title: 'Implement JWT Session Gateway', desc: 'Verify cryptographic signature validity and token refresh bounds.', status: 'in_progress', priority: 'critical', tag: 'security' },
        { id: '3', title: 'Configure CDN Asset Edge Caching', desc: 'Deploy automated invalidation rules for generated 3D assets.', status: 'review', priority: 'medium', tag: 'devops' },
        { id: '4', title: 'Three.js Camera Collision Culling', desc: 'Implement frustum intersection checks for obstacle rendering.', status: 'backlog', priority: 'low', tag: 'graphics' }
      ];
      this.save();
    }
  }

  save() {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.tasks));
    this.notify();
  }

  subscribe(fn) { this.subscribers.push(fn); fn(this.tasks); }
  notify() { this.subscribers.forEach(fn => fn(this.tasks)); }

  addTask(task) {
    task.id = Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    this.tasks.push(task);
    this.save();
  }

  moveTask(id, newStatus) {
    const t = this.tasks.find(x => x.id === id);
    if (t) { t.status = newStatus; this.save(); }
  }

  deleteTask(id) {
    this.tasks = this.tasks.filter(x => x.id !== id);
    this.save();
  }

  exportJSON() {
    const blob = new Blob([JSON.stringify(this.tasks, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `taskpulse_backup_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
  }
}
window.taskStore = new TaskStore();
"""
        ws.write_file("js/store.js", js, overwrite=True)

    def _write_kanban_components_js(self, ws: SafeWorkspaceManager) -> None:
        js = """// TaskPulse UI Component Builders
class Components {
  static createTaskCard(task) {
    const card = document.createElement('div');
    card.className = 'task-card';
    card.dataset.id = task.id;

    card.innerHTML = `
      <div class="card-top">
        <span class="tag-badge">#${task.tag || 'general'}</span>
        <span class="priority-pill priority-${task.priority}">${task.priority}</span>
      </div>
      <h4>${task.title}</h4>
      <p>${task.desc || 'No description provided.'}</p>
      <div class="card-actions">
        <button class="action-btn next-btn">Advance ➔</button>
        <button class="action-btn delete-btn">✕</button>
      </div>
    `;
    return card;
  }
}
window.Components = Components;
"""
        ws.write_file("js/components.js", js, overwrite=True)

    def _write_kanban_app_js(self, ws: SafeWorkspaceManager, title: str) -> None:
        js = """// TaskPulse App Controller
document.addEventListener('DOMContentLoaded', () => {
  const store = window.taskStore;
  const lists = {
    backlog: document.getElementById('list-backlog'),
    in_progress: document.getElementById('list-in_progress'),
    review: document.getElementById('list-review'),
    done: document.getElementById('list-done'),
  };
  const counts = {
    backlog: document.getElementById('count-backlog'),
    in_progress: document.getElementById('count-in_progress'),
    review: document.getElementById('count-review'),
    done: document.getElementById('count-done'),
  };
  const metrics = {
    total: document.getElementById('metric-total'),
    progress: document.getElementById('metric-progress'),
    done: document.getElementById('metric-done'),
    velocity: document.getElementById('metric-velocity'),
  };

  const modal = document.getElementById('task-modal');
  const addTaskBtn = document.getElementById('add-task-btn');
  const closeBtn = document.getElementById('modal-close-btn');
  const cancelBtn = document.getElementById('modal-cancel-btn');
  const form = document.getElementById('task-form');
  const searchInput = document.getElementById('search-input');
  const filterPriority = document.getElementById('filter-priority');
  const exportBtn = document.getElementById('export-btn');
  const themeBtn = document.getElementById('theme-btn');

  // Theme toggle
  themeBtn.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    themeBtn.textContent = next === 'dark' ? '🌙' : '☀️';
  });

  exportBtn.addEventListener('click', () => store.exportJSON());

  addTaskBtn.addEventListener('click', () => modal.classList.remove('hidden'));
  closeBtn.addEventListener('click', () => modal.classList.add('hidden'));
  cancelBtn.addEventListener('click', () => modal.classList.add('hidden'));

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    store.addTask({
      title: document.getElementById('task-title-input').value.trim(),
      desc: document.getElementById('task-desc-input').value.trim(),
      priority: document.getElementById('task-priority-input').value,
      tag: document.getElementById('task-tag-input').value.trim(),
      status: 'backlog',
    });
    form.reset();
    modal.classList.add('hidden');
  });

  let activeSearch = '';
  let activePriority = 'all';

  searchInput.addEventListener('input', (e) => { activeSearch = e.target.value.toLowerCase(); render(); });
  filterPriority.addEventListener('change', (e) => { activePriority = e.target.value; render(); });

  function render() {
    const tasks = store.tasks;
    Object.values(lists).forEach(l => l.innerHTML = '');
    const colCounts = { backlog: 0, in_progress: 0, review: 0, done: 0 };

    tasks.forEach(t => {
      const matchSearch = t.title.toLowerCase().includes(activeSearch) || (t.tag && t.tag.toLowerCase().includes(activeSearch));
      const matchPri = activePriority === 'all' || t.priority === activePriority;
      if (matchSearch && matchPri) {
        colCounts[t.status] = (colCounts[t.status] || 0) + 1;
        const card = Components.createTaskCard(t);

        card.querySelector('.delete-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          store.deleteTask(t.id);
        });

        const nextBtn = card.querySelector('.next-btn');
        nextBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          const order = ['backlog', 'in_progress', 'review', 'done'];
          const idx = order.indexOf(t.status) + 1;
          if (idx < order.length) store.moveTask(t.id, order[idx]);
        });

        if (lists[t.status]) lists[t.status].appendChild(card);
      }
    });

    Object.keys(counts).forEach(k => { if (counts[k]) counts[k].textContent = colCounts[k] || 0; });

    const total = tasks.length;
    const done = tasks.filter(x => x.status === 'done').length;
    const inProg = tasks.filter(x => x.status === 'in_progress' || x.status === 'review').length;
    metrics.total.textContent = total;
    metrics.done.textContent = done;
    metrics.progress.textContent = inProg;
    metrics.velocity.textContent = `${total > 0 ? Math.round((done / total) * 100) : 100}%`;
  }

  store.subscribe(() => render());
});
"""
        ws.write_file("js/app.js", js, overwrite=True)

    def _write_kanban_manifest(self, ws: SafeWorkspaceManager, title: str, desc: str) -> None:
        manifest = {
            "name": title.lower().replace(" ", "_"),
            "title": title,
            "type": "web_app",
            "framework": "vanilla_spa_modular",
            "features": [
                "Reactive state store with subscriber pattern",
                "Persistent localStorage cache with backup export",
                "Real-time task search and priority filter",
                "Agile Kanban multi-stage progression",
                "Live velocity & progress analytics gauges",
            ],
            "entry_point": "index.html",
        }
        ws.write_file("project.json", json.dumps(manifest, indent=2), overwrite=True)

    def verify(self, project_dir: Path) -> ExecutionReport:
        runner = GameTestRunner(project_dir)
        report = runner.run_all_tests()
        report.project_type = "web_app"
        report.entry_point = "index.html"
        return report

    def get_run_instructions(self, project_dir: Path) -> Dict[str, Any]:
        return {
            "run_command": f"python -m http.server 8080 --directory {project_dir}",
            "url": "http://127.0.0.1:8080/index.html",
            "instructions": "Host with python -m http.server or open index.html directly in a browser.",
        }
