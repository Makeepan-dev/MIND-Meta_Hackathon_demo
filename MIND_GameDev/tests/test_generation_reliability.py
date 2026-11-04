"""
Comprehensive regression tests for Code Extraction, Component Contract,
Cross-File Integrity Validation, and Website Workflow Generation Reliability.
Tests all 15 failure modes and edge cases.
"""

import tempfile
from pathlib import Path
import pytest

from MIND_GameDev.adapters.code_extractor import RobustCodeExtractor, ExtractionResult
from MIND_GameDev.tools.component_contract import (
    ComponentContract,
    ComponentContractExtractor,
    CrossFileIntegrityValidator,
    ValidationReport,
)
from MIND_GameDev.tools.test_runner import GameTestRunner
from MIND_GameDev.game_workflows.website_workflow import WebsiteWorkflow
from MIND_GameDev.models import ProjectSpecification, ProjectType
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager
from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.adapters.coding_adapter import CodingAdapter


# ---------------------------------------------------------------------------
# Test 1: Clean CSS extraction from fenced block with language tag
# ---------------------------------------------------------------------------
def test_extract_clean_fenced_css():
    raw = """```css
:root {
  --primary-color: #0284c7;
}
body {
  margin: 0;
  background: #0f172a;
}
```"""
    res = RobustCodeExtractor.extract(raw, "css")
    assert ":root" in res.code
    assert "--primary-color: #0284c7;" in res.code
    assert res.is_truncated is False
    assert res.stripped_preamble_lines == 0


# ---------------------------------------------------------------------------
# Test 2: Clean CSS extraction from unlabelled fenced block
# ---------------------------------------------------------------------------
def test_extract_unlabelled_fenced_css():
    raw = """```
:root {
  --primary-color: #ff0055;
}
.hero {
  padding: 4rem;
}
```"""
    res = RobustCodeExtractor.extract(raw, "css")
    assert ".hero" in res.code
    assert res.is_truncated is False


# ---------------------------------------------------------------------------
# Test 3: CSS with conversational thinking preamble (like D:\as\style.css)
# ---------------------------------------------------------------------------
def test_extract_css_with_conversational_preamble():
    preamble = "\n".join([
        "We need to produce production-grade responsive CSS for the sports platform.",
        "The design direction is athletic high-energy with bold neon accents.",
        "We need to use CSS custom properties matching tokens:",
        "- --primary-color: #ff5500",
        "Let's outline sections:",
        "1. :root defines dark theme variables",
        "2. Typography",
        "7. Hero layout: .hero { padding: 2rem; }",
        "Now let's write the CSS.",
        "We'll include:",
    ])
    css_body = """
:root {
  --primary-color: #ff5500;
  --bg-primary: #121212;
}
.navbar {
  display: flex;
}
"""
    raw = f"{preamble}\n{css_body}"
    res = RobustCodeExtractor.extract(raw, "css")
    assert res.stripped_preamble_lines > 0
    assert res.code.startswith(":root")
    assert "We need to produce" not in res.code
    assert "Let's outline" not in res.code


# ---------------------------------------------------------------------------
# Test 4: CSS with conversational postamble stripped cleanly
# ---------------------------------------------------------------------------
def test_extract_css_with_postamble():
    raw = """
:root {
  --primary-color: #00ffcc;
}
.card {
  border-radius: 8px;
}
```
I hope this stylesheet meets your requirements! Let me know if you need any adjustments.
"""
    res = RobustCodeExtractor.extract(raw, "css")
    assert ".card" in res.code
    assert "I hope this stylesheet" not in res.code
    assert "adjustments" not in res.code


# ---------------------------------------------------------------------------
# Test 5: Truncated CSS ending mid-declaration ('border-top: 1px') repaired
# ---------------------------------------------------------------------------
def test_repair_truncated_css_mid_declaration():
    truncated = """
:root {
  --bg-card: #1a1a2e;
}
.footer {
  background: var(--bg-card);
  border-top: 1px
"""
    res = RobustCodeExtractor.extract(truncated, "css")
    assert res.is_truncated is True
    assert "border-top: 1px" not in res.code  # truncated line safely dropped
    assert res.code.count("{") == res.code.count("}")  # braces balanced
    assert res.code.endswith("}")


# ---------------------------------------------------------------------------
# Test 6: Truncated CSS with unclosed curly braces repaired
# ---------------------------------------------------------------------------
def test_repair_truncated_css_unclosed_braces():
    truncated = """
@media (max-width: 768px) {
  .nav-links {
    display: none;
  .hero-section {
    padding: 1rem;
"""
    res = RobustCodeExtractor.extract(truncated, "css")
    assert res.is_truncated is True
    assert res.code.count("{") == res.code.count("}")
    assert any("Balanced" in note for note in res.repair_notes)


# ---------------------------------------------------------------------------
# Test 7: HTML extraction starting with conversational preamble
# ---------------------------------------------------------------------------
def test_extract_html_with_preamble():
    raw = """
Certainly! Here is the complete modern HTML5 code for the sports website:

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Sports Hub</title>
</head>
<body>
  <div class="content">Hello World</div>
</body>
</html>
"""
    res = RobustCodeExtractor.extract(raw, "html")
    assert res.code.startswith("<!DOCTYPE html>")
    assert res.code.endswith("</html>")
    assert "Certainly!" not in res.code
    assert res.stripped_preamble_lines > 0


# ---------------------------------------------------------------------------
# Test 8: Truncated HTML missing closing tags repaired
# ---------------------------------------------------------------------------
def test_repair_truncated_html():
    raw = """
<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
  <section class="hero">
    <h1>Welcome</h1>
"""
    res = RobustCodeExtractor.extract(raw, "html")
    assert res.is_truncated is True
    assert "</html>" in res.code
    assert "</body>" in res.code


# ---------------------------------------------------------------------------
# Test 9: JavaScript extraction with preamble and unclosed braces
# ---------------------------------------------------------------------------
def test_extract_js_with_preamble_and_repair():
    raw = """
Here is the clean JavaScript code for interactivity:

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('theme-toggle');
  if (btn) {
    btn.addEventListener('click', () => {
      document.body.classList.toggle('dark');
"""
    res = RobustCodeExtractor.extract(raw, "javascript")
    assert res.is_truncated is True
    assert "Here is the clean" not in res.code
    assert res.code.startswith("document.addEventListener")
    assert res.code.count("{") == res.code.count("}")
    assert res.code.count("(") == res.code.count(")")


# ---------------------------------------------------------------------------
# Test 10: Multiple code blocks in model response
# ---------------------------------------------------------------------------
def test_extract_multiple_codeblocks_selects_requested_language():
    raw = """
Here is a small config snippet:
```json
{"theme": "dark"}
```

And here is the complete stylesheet:
```css
:root {
  --primary: #3b82f6;
}
.header {
  height: 60px;
}
```
"""
    res = RobustCodeExtractor.extract(raw, "css")
    assert ":root" in res.code
    assert ".header" in res.code
    assert '{"theme"' not in res.code


# ---------------------------------------------------------------------------
# Test 11: ComponentContract extraction from HTML
# ---------------------------------------------------------------------------
def test_component_contract_extraction():
    html_markup = """
<!DOCTYPE html>
<html>
<body>
  <header class="navbar main-nav">
    <div id="brand-logo" class="brand">SportsApp</div>
    <button id="theme-toggle" class="btn icon-btn">Theme</button>
  </header>
  <main class="hero-section container">
    <h1 class="hero-title">Welcome</h1>
    <form id="reg-form" class="registration-form">
      <input type="text" name="athlete_name" id="athlete-input">
      <button type="submit" class="cta-button">Register</button>
    </form>
  </main>
</body>
</html>
"""
    contract = ComponentContractExtractor.extract(html_markup)
    assert "navbar" in contract.classes
    assert "main-nav" in contract.classes
    assert "brand" in contract.classes
    assert "hero-section" in contract.classes
    assert "cta-button" in contract.classes
    assert "theme-toggle" in contract.ids
    assert "brand-logo" in contract.ids
    assert "reg-form" in contract.ids
    assert "athlete_name" in contract.form_names


# ---------------------------------------------------------------------------
# Test 12: ComponentContract prompt generation includes non-invention directive
# ---------------------------------------------------------------------------
def test_component_contract_prompt_generation():
    contract = ComponentContract(
        classes=["navbar", "brand", "cta-button"],
        ids=["theme-toggle", "reg-form"],
    )
    prompt = contract.to_css_contract_prompt()
    assert "CRITICAL COMPONENT CONTRACT" in prompt
    assert ".navbar" in prompt
    assert ".cta-button" in prompt
    assert "#theme-toggle" in prompt
    assert "Do NOT use alternative BEM names" in prompt


# ---------------------------------------------------------------------------
# Test 13: CrossFileIntegrityValidator detects mismatch
# ---------------------------------------------------------------------------
def test_cross_file_integrity_validator_detects_mismatch():
    html_markup = """
<div class="navbar">
  <div class="brand">Logo</div>
  <div class="hero-section">
    <div class="card-grid">
      <div class="app-card">Card 1</div>
    </div>
    <button class="cta-button">Click</button>
  </div>
</div>
"""
    # CSS using totally different BEM classes (like what Cohere previously did)
    css_markup = """
:root { --color: red; }
.nav { display: flex; }
.nav__brand { font-size: 20px; }
.hero { padding: 2rem; }
.feature-card { background: white; }
.hero__cta { border: none; }
"""
    report = CrossFileIntegrityValidator.validate(html_markup, css_markup)
    assert report.is_valid is False
    assert report.coverage_pct < 20.0
    assert any("HTML/CSS class coverage too low" in err for err in report.errors)


# ---------------------------------------------------------------------------
# Test 14: CrossFileIntegrityValidator passes matching HTML & CSS
# ---------------------------------------------------------------------------
def test_cross_file_integrity_validator_passes_matching():
    html_markup = """
<header class="navbar">
  <div class="brand">Brand</div>
  <button class="cta-button">Action</button>
</header>
"""
    css_markup = """
:root { --primary: blue; }
.navbar { display: flex; }
.brand { font-weight: bold; }
.cta-button { padding: 10px; }
"""
    report = CrossFileIntegrityValidator.validate(html_markup, css_markup)
    assert report.is_valid is True
    assert report.coverage_pct == 100.0
    assert len(report.errors) == 0


# ---------------------------------------------------------------------------
# Test 15: Verifier rejects uncleaned D:\as\style.css and passes repaired version
# ---------------------------------------------------------------------------
def test_verifier_rejects_defective_as_css_and_passes_repaired(tmp_path):
    as_path = Path("D:/as/style.css")
    if not as_path.exists():
        pytest.skip("D:/as/style.css does not exist on this machine")

    runner = GameTestRunner(tmp_path)

    # 1. Test defective raw file
    defective_res = runner._verify_css_content(as_path)
    assert defective_res["passed"] is False

    # 2. Extract and repair through RobustCodeExtractor
    raw_content = as_path.read_text(encoding="utf-8")
    clean_result = RobustCodeExtractor.extract(raw_content, "css")
    assert clean_result.is_truncated is True
    assert clean_result.code.count("{") == clean_result.code.count("}")

    repaired_file = tmp_path / "style.css"
    repaired_file.write_text(clean_result.code, encoding="utf-8")

    # 3. Test repaired file
    repaired_res = runner._verify_css_content(repaired_file)
    assert repaired_res["passed"] is True


# ---------------------------------------------------------------------------
# Test 16: End-to-end staged website workflow generation in test mode
# ---------------------------------------------------------------------------
def test_website_workflow_end_to_end_test_mode(tmp_path):
    cfg = GameDevConfig.load()
    cfg.test_mode = True
    adapter = CodingAdapter(cfg)
    workflow = WebsiteWorkflow(coding_adapter=adapter)

    spec = ProjectSpecification(
        title="Artisan Bakery and Cafe",
        description="Handcrafted sourdough, organic pastries, espresso bar, and online order form.",
        project_type=ProjectType.WEBSITE,
        destination_dir=str(tmp_path),
        theme="warm earthy tones, artisan bakery",
        pages=["index.html", "menu.html", "about.html", "contact.html"],
    )

    workspace = SafeWorkspaceManager(tmp_path)
    result = workflow.build(spec, workspace)

    assert result["status"] == "SUCCESS"
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "style.css").exists()
    assert (tmp_path / "js" / "main.js").exists()
    assert (tmp_path / "menu.html").exists()
    assert (tmp_path / "project.json").exists()

    # Static verification suite
    exec_report = workflow.verify(tmp_path)
    assert exec_report.success is True
    assert exec_report.status == "VERIFIED"
