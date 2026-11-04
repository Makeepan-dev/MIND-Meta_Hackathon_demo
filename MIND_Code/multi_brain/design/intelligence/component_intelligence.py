"""
MIND Component Intelligence Subsystem.
Constructs semantic, accessible, and responsive interface components.
"""

from __future__ import annotations

import html
from typing import Dict, List

from multi_brain.design.contracts import ComponentStructure, DesignSpecification


class ComponentIntelligence:
    """Creates and manages reusable UI components bound to design specifications."""

    def build_navbar(self, spec: DesignSpecification) -> ComponentStructure:
        clean_title = spec.project_name[:24]
        links_html = "".join([
            f'<li><a href="#{s.screen_id}" class="nav-link" data-screen="{s.screen_id}">{s.title.split("—")[-1].strip()}</a></li>'
            for s in spec.screens
        ])
        code = f"""<nav class="navbar" role="navigation" aria-label="Main Navigation">
  <div class="nav-brand">
    <span style="color:var(--primary)">⚡</span> MIND // {html.escape(clean_title)}
  </div>
  <ul class="nav-links">
    {links_html}
    <li><button class="btn btn-primary" onclick="alert('Action triggered!')" style="padding:6px 14px; font-size:12px;">Launch</button></li>
  </ul>
</nav>"""
        return ComponentStructure(
            component_id="navbar_main",
            name="GlobalNavbar",
            category="navigation",
            html_snippet=code,
            css_classes="navbar",
        )

    def build_hero(self, spec: DesignSpecification, version: int = 1) -> ComponentStructure:
        title = html.escape(spec.project_name)
        desc = html.escape(spec.purpose)
        badge_text = f"REVISED DESIGN PROTOTYPE v{version}" if version > 1 else f"DESIGN PROTOTYPE v1"
        code = f"""<header class="hero" id="overview">
  <div class="hero-badge">{badge_text}</div>
  <h1>{title}</h1>
  <p>{desc}</p>
  <div class="hero-actions">
    <button class="btn btn-primary" onclick="document.getElementById('features').scrollIntoView({{behavior:'smooth'}})">
      Explore System ➔
    </button>
    <button class="btn btn-secondary" onclick="document.getElementById('console').scrollIntoView({{behavior:'smooth'}})">
      Live Console
    </button>
  </div>
</header>"""
        return ComponentStructure(
            component_id="hero_main",
            name="HeroBanner",
            category="hero",
            html_snippet=code,
            css_classes="hero",
        )

    def build_metrics(self, spec: DesignSpecification) -> ComponentStructure:
        code = """<section class="metrics-strip" aria-label="System Metrics">
  <div class="metric-card">
    <div class="metric-value">99.98%</div>
    <div class="metric-label">System Availability</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">&lt; 12ms</div>
    <div class="metric-label">Inference Latency</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">100%</div>
    <div class="metric-label">WCAG Contrast AA</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">0 Dep</div>
    <div class="metric-label">Autonomous Runtime</div>
  </div>
</section>"""
        return ComponentStructure(
            component_id="metrics_main",
            name="MetricsStrip",
            category="metrics",
            html_snippet=code,
            css_classes="metrics-strip",
        )

    def build_feature_grid(self, spec: DesignSpecification) -> ComponentStructure:
        cards_html = """
  <div class="feature-card">
    <h3>Autonomous Design Engine</h3>
    <p>Engineered with local design intelligence, deterministic contrast verification, and responsive multi-screen routing.</p>
  </div>
  <div class="feature-card">
    <h3>Surgical Revision Loop</h3>
    <p>Supports conversational adjustments to typography, palette, and component structure without regenerating from scratch.</p>
  </div>
  <div class="feature-card">
    <h3>Strict Approval Gate</h3>
    <p>No production source files are written until you explicitly approve the live visual prototype.</p>
  </div>
"""
        code = f"""<section class="feature-grid" id="features" aria-label="Features">
{cards_html}
</section>"""
        return ComponentStructure(
            component_id="features_main",
            name="FeatureGrid",
            category="features",
            html_snippet=code,
            css_classes="feature-grid",
        )

    def build_console_dock(self, spec: DesignSpecification) -> ComponentStructure:
        code = f"""<section class="simulator-dock" id="console" aria-label="Interactive Simulator">
  <div class="dock-header">
    <span class="dock-title">● LIVE WORKSPACE INTERACTION TERMINAL</span>
    <span style="font-size:11px; color:var(--text-muted);">STATUS: ACTIVE</span>
  </div>
  <p style="font-size:14px; color:var(--text-muted); margin-bottom:16px;">
    Interact with the prototype live. Request visual adjustments via MIND chat or approve to proceed with production code synthesis.
  </p>
  <div style="display:flex; gap:10px;">
    <button class="btn btn-primary" onclick="alert('Triggering interactive action simulation!')" style="font-size:12px; padding:8px 16px;">
      Simulate Telemetry Stream
    </button>
    <button class="btn btn-secondary" onclick="window.scrollTo({{top:0, behavior:'smooth'}})" style="font-size:12px; padding:8px 16px;">
      Top of Page ↑
    </button>
  </div>
</section>"""
        return ComponentStructure(
            component_id="console_dock",
            name="ConsoleDock",
            category="console",
            html_snippet=code,
            css_classes="simulator-dock",
        )

    def build_footer(self, spec: DesignSpecification) -> ComponentStructure:
        clean_title = spec.project_name
        code = f"""<footer class="footer" role="contentinfo">
  <p>MIND // <strong>{html.escape(clean_title)}</strong> — Generated via MIND Native Design Intelligence.</p>
  <p style="margin-top:6px; font-size:11px; color:var(--text-muted);">
    Design System Verified • Responsive Layout • Zero Cloud Dependency
  </p>
</footer>"""
        return ComponentStructure(
            component_id="footer_main",
            name="SystemFooter",
            category="footer",
            html_snippet=code,
            css_classes="footer",
        )
