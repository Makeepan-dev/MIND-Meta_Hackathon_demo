"""
MIND Design Generator.
Assembles complete HTML/CSS/JS interfaces, component structures, and design documentation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from multi_brain.design.contracts import (
    ComponentStructure,
    DesignResult,
    DesignSpecification,
)
from multi_brain.design.intelligence.component_intelligence import ComponentIntelligence
from multi_brain.design.intelligence.layout_engine import LayoutIntelligence
from multi_brain.design.intelligence.reasoner import DesignReasoner
from multi_brain.design.intelligence.ux_architect import UXArchitect
from multi_brain.design.intelligence.visual_designer import VisualDesigner

logger = logging.getLogger("mind.multi_brain.design.generator")


class DesignGenerator:
    """Orchestrates intelligence layers into complete, cohesive design artifacts."""

    def __init__(self) -> None:
        self.reasoner = DesignReasoner()
        self.ux_architect = UXArchitect()
        self.visual_designer = VisualDesigner()
        self.layout_engine = LayoutIntelligence()
        self.components = ComponentIntelligence()

    def generate(
        self,
        spec: DesignSpecification,
        output_dir: Path,
        version: int = 1,
    ) -> Tuple[str, str, str, str, List[ComponentStructure]]:
        """
        Generates index.html, style.css, DESIGN.md, and SITE.md based on specification.
        Returns: (html_content, css_content, design_md, site_md, components)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Refine specification with UX and Visual decisions
        spec = self.ux_architect.architect_experience(spec)
        spec = self.visual_designer.refine_visual_design(spec)

        # 2. Generate CSS
        css_content = self.layout_engine.generate_base_css(spec)

        # 3. Assemble Components
        navbar = self.components.build_navbar(spec)
        hero = self.components.build_hero(spec, version=version)
        metrics = self.components.build_metrics(spec)
        features = self.components.build_feature_grid(spec)
        console = self.components.build_console_dock(spec)
        footer = self.components.build_footer(spec)

        comp_list = [navbar, hero, metrics, features, console, footer]

        # 4. Assemble HTML
        title = spec.project_name
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — MIND Prototype v{version}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {navbar.html_snippet}

  <main class="app-container">
    {hero.html_snippet}
    {metrics.html_snippet}
    {features.html_snippet}
    {console.html_snippet}
  </main>

  {footer.html_snippet}

  <script>
    console.log("MIND Native Prototype v{version} initialized.");
    document.querySelectorAll(".nav-link").forEach(link => {{
      link.addEventListener("click", (e) => {{
        document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
        link.classList.add("active");
      }});
    }});
  </script>
</body>
</html>"""

        # 5. Persist DESIGN.md
        design_md = self._generate_design_md(spec, version)

        # 6. Persist SITE.md
        site_md = self._generate_site_md(spec, version)

        # Write files
        (output_dir / "index.html").write_text(html_content, encoding="utf-8")
        (output_dir / "style.css").write_text(css_content, encoding="utf-8")
        (output_dir / "DESIGN.md").write_text(design_md, encoding="utf-8")
        (output_dir / "SITE.md").write_text(site_md, encoding="utf-8")

        return html_content, css_content, design_md, site_md, comp_list

    def _generate_design_md(self, spec: DesignSpecification, version: int) -> str:
        c = spec.tokens.colors
        return f"""# Design System Specification
**Project**: {spec.project_name}
**Version**: Prototype v{version}
**Design Engine**: MIND Native AI Design Intelligence
**Visual Tone**: {spec.visual_tone.value.upper()}
**Target Device**: {spec.device_type.value}

## Color Palette Tokens
- **Primary Accent**: `{c.primary}`
- **Secondary Tone**: `{c.secondary}`
- **Accent Highlight**: `{c.accent}`
- **Deep Background**: `{c.background}`
- **Surface Elevation**: `{c.surface}`
- **Primary Typography**: `{c.text_primary}`
- **Muted Typography**: `{c.text_secondary}`
- **Border Constraint**: `{c.border}`

## Typography & Scale
- Heading Stack: `{spec.tokens.typography.font_family_heading}`
- Body Stack: `{spec.tokens.typography.font_family_body}`
- Baseline Spacing Unit: `{spec.tokens.spacing_unit}px`
- Border Radius: `{spec.tokens.border_radius}`

## Accessibility Compliance
{chr(10).join(f"- {a}" for a in spec.accessibility_requirements)}
"""

    def _generate_site_md(self, spec: DesignSpecification, version: int) -> str:
        screens_text = "\n".join([
            f"- **{s.title}** (`{s.route}`): {s.purpose}\n  - Components: {', '.join(s.components)}"
            for s in spec.screens
        ])
        nav_text = "\n".join([
            f"- `{step['from']}` ➔ `{step['to']}`: {step['action']}"
            for step in spec.navigation_flow
        ])
        return f"""# Site Architecture & User Journeys
**Project**: {spec.project_name}
**Version**: Prototype v{version}

## Screen Inventory
{screens_text}

## Navigation Flow & User Journey
{nav_text}
"""
