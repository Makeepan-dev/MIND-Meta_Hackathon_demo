"""
MIND Layout Intelligence Engine.
Computes responsive CSS grid layouts, breakpoints, and container constraints.
"""

from __future__ import annotations

import logging
from typing import Dict

from multi_brain.design.contracts import DesignSpecification, DeviceType

logger = logging.getLogger("mind.multi_brain.design.layout")


class LayoutIntelligence:
    """Calculates responsive layouts and CSS rules tailored to device constraints."""

    def generate_base_css(self, spec: DesignSpecification) -> str:
        """Constructs modular CSS with variables, grid models, and responsive breakpoints."""
        tokens = spec.tokens
        c = tokens.colors
        t = tokens.typography
        is_mobile = spec.device_type == DeviceType.MOBILE

        max_width = "480px" if is_mobile else "1140px"
        container_pad = "16px" if is_mobile else "32px"

        return f"""/* MIND Native Design Intelligence — Generated Stylesheet */
:root {{
  --primary: {c.primary};
  --secondary: {c.secondary};
  --accent: {c.accent};
  --bg-dark: {c.background};
  --surface: {c.surface};
  --text-main: {c.text_primary};
  --text-muted: {c.text_secondary};
  --border: {c.border};
  --font-heading: {t.font_family_heading};
  --font-body: {t.font_family_body};
  --radius: {tokens.border_radius};
  --shadow: {tokens.box_shadow};
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  background-color: var(--bg-dark);
  color: var(--text-main);
  font-family: var(--font-body);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}}

a {{
  color: var(--primary);
  text-decoration: none;
  transition: opacity 0.2s ease;
}}
a:hover {{
  opacity: 0.85;
}}

.app-container {{
  max-width: {max_width};
  margin: 0 auto;
  padding: 0 {container_pad};
}}

/* Navbar */
.navbar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px {container_pad};
  background: rgba(10, 16, 32, 0.95);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(8px);
}}

.nav-brand {{
  font-size: 18px;
  font-weight: 800;
  color: var(--primary);
  letter-spacing: 1px;
  display: flex;
  align-items: center;
  gap: 8px;
}}

.nav-links {{
  display: flex;
  gap: 20px;
  list-style: none;
  align-items: center;
}}

.nav-links a {{
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
}}

.nav-links a:hover, .nav-links a.active {{
  color: var(--primary);
}}

/* Hero Section */
.hero {{
  padding: {'40px 16px' if is_mobile else '70px 24px'};
  text-align: center;
  max-width: 860px;
  margin: 0 auto;
}}

.hero-badge {{
  display: inline-block;
  padding: 4px 14px;
  background: rgba(0, 245, 255, 0.1);
  border: 1px solid var(--primary);
  color: var(--primary);
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  margin-bottom: 16px;
  text-transform: uppercase;
}}

.hero h1 {{
  font-size: {'28px' if is_mobile else '44px'};
  font-weight: 800;
  line-height: 1.2;
  margin-bottom: 16px;
  letter-spacing: -0.5px;
  color: #FFFFFF;
}}

.hero p {{
  font-size: {'15px' if is_mobile else '18px'};
  color: var(--text-muted);
  margin-bottom: 28px;
  line-height: 1.6;
}}

.hero-actions {{
  display: flex;
  gap: 14px;
  justify-content: center;
  flex-wrap: wrap;
}}

/* Buttons */
.btn {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 22px;
  border-radius: var(--radius);
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.btn:hover {{
  transform: translateY(-1px);
}}
.btn-primary {{
  background: var(--primary);
  color: #050811;
  box-shadow: 0 4px 14px rgba(0, 245, 255, 0.25);
}}
.btn-secondary {{
  background: var(--surface);
  color: var(--text-main);
  border: 1px solid var(--border);
}}

/* Metrics Strip */
.metrics-strip {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  padding: 24px 0 40px;
}}

.metric-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  text-align: center;
}}

.metric-value {{
  font-size: 28px;
  font-weight: 800;
  color: var(--primary);
  font-family: monospace;
}}

.metric-label {{
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-top: 4px;
}}

/* Responsive Feature Grid */
.feature-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 24px;
  padding: 20px 0 60px;
}}

.feature-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 28px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}
.feature-card:hover {{
  border-color: var(--primary);
  box-shadow: var(--shadow);
}}

.feature-card h3 {{
  color: var(--primary);
  font-size: 18px;
  margin-bottom: 10px;
}}

.feature-card p {{
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.6;
}}

/* Interactive Simulator Panel */
.simulator-dock {{
  background: #080D1A;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin: 30px 0;
}}

.dock-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
  margin-bottom: 16px;
}}

.dock-title {{
  font-size: 14px;
  font-family: monospace;
  color: var(--primary);
}}

/* Footer */
.footer {{
  border-top: 1px solid var(--border);
  padding: 30px {container_pad};
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 40px;
}}
"""
