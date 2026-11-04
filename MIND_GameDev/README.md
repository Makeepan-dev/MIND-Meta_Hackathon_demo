# MIND Universal Development Studio
## Autonomous Multi-Provider AI Software Engineering Engine

MIND Universal Development Studio is an autonomous, cross-domain software engineering agent extracted from the MIND Multi-Brain architecture. It allows users to describe software requirements in natural language (via voice or text), have AI infer the domain architecture, plan and scaffold projects, synthesize 2D and 3D assets, run automated verification tests, and immediately serve or execute the applications.

---

## 1. Verified Universal Capabilities

| Category | Domain Status | Scaffolding Engine | Automated Verification Routine | Live Execution Evidence |
|---|---|---|---|---|
| **Auth / Login Portals** | **Implemented & Tested** | `WebAppWorkflow` (Responsive Vanilla SPA) | Campus brand theme, role switching (Student/Staff), regex ID validation, modal dialogs | ✅ Verified on Edge DOM & Node.js V8 |
| **Interactive Web Apps** | **Implemented & Tested** | `WebAppWorkflow` (Single Page Apps) | Reactive state store, localStorage persistence, Kanban CRUD, analytics gauges | ✅ Tested on Edge DOM & Node.js V8 |
| **Multi-Page Websites** | **Implemented & Tested** | `WebsiteWorkflow` (HTML5/CSS3/JS) | Multi-page HTML tags, responsive CSS, theme toggle, form validator, HTTP server | ✅ Tested on Edge DOM |
| **Backend REST APIs** | **Implemented & Tested** | `BackendApiWorkflow` (FastAPI) | Automated pytest endpoint tests (CRUD, 404s, schema validation, health) | ✅ 8 of 8 endpoint tests pass |
| **3D WebGL Games** | **Implemented & Tested** | `EndlessRunnerGenerator` (Three.js) | GLB magic `0x46546C67`, OBJ geometry, Web Audio API, ephemeral HTTP server | ✅ Playable in Browser & Headless Edge |
| **Desktop Utilities** | **Implemented & Tested** | `DesktopAppWorkflow` (Tkinter) | Platform telemetry diagnostics collector, headless smoke tests | ✅ Pytest verified |
| **Automations & CLI** | **Implemented & Tested** | `AutomationWorkflow` (Python CLI) | Subcommand arguments (`audit`, `process`), batch processor test suite | ✅ Pytest verified |
| **Mobile Applications** | **Implemented & Tested** | `MobileAppWorkflow` (Android) | XML manifest parsing, ConstraintLayout XML, Kotlin activity structure | ✅ XML & Gradle verified |
| **Custom Solutions** | **Implemented & Tested** | `CustomWorkflow` (Dual Web/CLI) | Modular Python engine, interactive web console, automated unit test suite | ✅ Pytest verified |

---

## 2. Integrated Free AI Providers & Strict Cost Protection

MIND Universal Studio is configured for **zero billable expenditure**. It enforces strict cost protection rules:
1. **Never Silently Switch to Paid Models**: Paid models are unconditionally rejected when free-only mode is active.
2. **Never Buy Credits or Activate Auto-Recharge**: Zero payments, subscriptions, or credit purchases are possible.
3. **Graceful Failover Chain**: OpenRouter Free (`:free` models) ➔ Local Ollama (if installed & online) ➔ Offline Deterministic Engine.

### Provider Details & Documentation

| Provider | Purpose | Free Access Tier | Official Documentation & Key Signup |
|---|---|---|---|
| **OpenRouter Free Tier** | Code synthesis & reasoning | Models ending in `:free` or `openrouter/free` (e.g. `google/gemma-2-9b-it:free`, `meta-llama/llama-3.3-70b-instruct:free`, `qwen/qwen-2.5-coder-32b-instruct:free`) | [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart) • [Keys](https://openrouter.ai/keys) |
| **Ollama (Local AI)** | Offline local code generation | 100% free & local. Checks if configured model (`qwen2.5-coder:7b`) is installed. Gracefully bypasses if stopped. | [Ollama API Documentation](https://docs.ollama.com/api) |
| **AI Horde** | 2D Concept Art Diffusion | Free distributed community cluster. Works anonymously with key `0000000000` or optional user key. Bounded polling with local Pillow fallback. | [AI Horde Documentation](https://stablehorde.net/docs/image/) • [Web Portal](https://horde.tazlin.net/) |
| **Procedural 3D** | 3D meshes for games | Pure-Python binary glTF 2.0 (`.glb`) and Wavefront (`.obj`) generator. Zero network required. | Built-in local math generator |
| **Procedural Audio** | Sound effects & music | Browser Web Audio API oscillator synthesis. Zero external downloads. | Built-in Web Audio API |

### Environment Variables

Configure providers non-invasively via environment variables (never paste secrets into code):
- `OPENROUTER_API_KEY`: OpenRouter API key.
- `OPENROUTER_MODEL`: Selected model (default: `google/gemma-2-9b-it:free`).
- `OPENROUTER_FREE_ONLY`: Enforces free-only restriction (default: `1` / True).
- `OLLAMA_API_BASE`: Local Ollama URL (default: `http://localhost:11434`).
- `OLLAMA_CODING_MODEL`: Target Ollama model (default: `qwen2.5-coder:7b`).
- `AI_HORDE_API_KEY`: Custom AI Horde key (default: `0000000000` for anonymous free access).
- `AI_HORDE_TIMEOUT_SECONDS`: Maximum polling duration before local fallback (default: `15`).

---

## 3. Provider Diagnostics

Inspect provider readiness and connectivity at any time without spending credits:

```powershell
venv\Scripts\python.exe -m MIND_GameDev --providers
```

Example Output:
```
======================================================================
          MIND UNIVERSAL STUDIO — AI PROVIDER DIAGNOSTICS         
======================================================================
Cost Policy: Free-Only Enforcement = True
Guarantee:   Strictly blocks paid models and silent billing failover.
----------------------------------------------------------------------
[1] OpenRouter Free Models:
    • Auth Status:      [CONFIGURED - KEY REDACTED] / [UNSET - LOCAL FALLBACK ACTIVE]
    • Selected Model:   google/gemma-2-9b-it:free
    • Verified Free:    True
    • Reachable:        True / Offline
    • Docs / Free Keys: https://openrouter.ai/keys

[2] Local Ollama Engine:
    • Endpoint:         http://localhost:11434
    • Configured Model: qwen2.5-coder:7b
    • Service Status:   Online / Offline
    • Model Installed:  True / False

[3] AI Horde Image Diffusion:
    • Access Tier:      Anonymous Public Free Tier ('0000000000')
    • Endpoint:         https://aihorde.net/api/v2
    • Cluster Status:   Online
    • Fallback Engine:  Local Pillow Engine (Ready)

[4] Local Procedural Engines:
    • 3D Geometry:      100% Operational (Local / Zero Network Required)
    • Audio FX:         100% Operational (In-browser oscillator)
----------------------------------------------------------------------
ACTIVE TIER: OPENROUTER_FREE / OLLAMA_LOCAL / OFFLINE_DETERMINISTIC
======================================================================
```

---

## 4. Universal Project Classification Rules

The studio uses a deterministic token-boundary classifier (`WorkflowRegistry.infer_project_type`) that categorizes requests across 8 domains without collisions:

| Inferred Type | Trigger Phrases & Keywords |
|---|---|
| `web_app` | `login screen`, `login page`, `login form`, `authentication screen`, `auth portal`, `signup`, `registration`, `dashboard`, `kanban`, `single page app`, `portal` |
| `website` | `portfolio website`, `landing page`, `multi-page website`, `business site`, `marketing website`, `corporate website`, `showcase` |
| `backend_api` | `rest api`, `rest endpoint`, `backend api`, `backend service`, `microservice`, `fastapi`, `crud`, `endpoints` |
| `mobile_app` | `android app`, `mobile application`, `mobile app`, `flutter app`, `kotlin app`, `apk` |
| `desktop_app` | `desktop application`, `desktop app`, `windows utility`, `desktop tool`, `tkinter`, `gui tool` |
| `game` | `endless runner`, `3d game`, `platformer game`, `arcade game`, `webgl game`, `three.js game`, `gameplay` |
| `automation` | `batch processor`, `automation script`, `automation tool`, `file-processing tool`, `cli tool`, `cron job` |
| `custom` | Ambiguous requests (e.g. `Build a tool for my team`) or unclassified generic prompts (NEVER defaults to `game`!) |

### Explicit CLI Override

You can override automatic classification at any time using `--type`:
```powershell
venv\Scripts\python.exe -m MIND_GameDev --create "Project description" --type website
```

---

## 5. Verified Demonstrations & Command Examples

### 1. SLIIT Campus Responsive Login Screen (`web_app`)
```powershell
venv\Scripts\python.exe -m MIND_GameDev --create "Create a responsive login screen for SLIIT Campus" --serve
```
- **Generated Location**: `workspace/sliit_campus_login/`
- **Features**: Official Navy (`#002147`) & Gold (`#f39c12`) branding, Student vs Staff/Faculty role tabs, client-side regex ID validation (`ITxxxxxxxx`), password visibility eye toggle, forgot password modal dialog, simulated authentication delay with loading spinner, and remembered credentials persistence in `localStorage`.

### 2. Responsive Multi-Page Portfolio Website (`website`)
```powershell
venv\Scripts\python.exe -m MIND_GameDev --create "Build a responsive multi-page portfolio website" --serve
```
- **Generated Location**: `workspace/nova_creative_portfolio/`
- **Features**: 4 connected pages (`index.html`, `about.html`, `services.html`, `contact.html`), responsive grid, light/dark theme switcher, mobile hamburger menu, interactive contact form validation.

### 3. Task Management Web Application (`web_app`)
```powershell
venv\Scripts\python.exe -m MIND_GameDev --create "Build a task management web app with persistent local storage" --serve
```
- **Generated Location**: `workspace/taskpulse_workstation/`
- **Features**: Full Agile Kanban board (Backlog, In Progress, Review, Completed), reactive subscriber state store, search and priority filtering, velocity analytics gauges, JSON export/backup.

### 4. Backend REST Microservice with Tests (`backend_api`)
```powershell
venv\Scripts\python.exe -m MIND_GameDev --create "Create a small REST API with automated endpoint tests"
```
- **Generated Location**: `workspace/nexus_rest_api/`
- **Features**: FastAPI microservice with CRUD endpoints, Pydantic schemas, and 8 automated pytest tests verifying health, item creation, duplicate rejection, and 404 handling.

### 5. Playable 3D Endless Runner Game (`game`)
```powershell
venv\Scripts\python.exe -m MIND_GameDev --create "Create a 3D endless runner with jumping, sliding, obstacles, and scoring" --serve
```
- **Generated Location**: `workspace/cyberdash_3d/`
- **Features**: Three.js WebGL rendering, 3 lanes, keyboard & touch controls, procedural barrier obstacles, spinning collectible coins, procedural Web Audio SFX, HUD, collision detection, game over restart loop.

---

## 6. Automated Test Suite

Run the complete test suite:

```powershell
# Standalone MIND Universal Studio tests (34 passed in ~41s)
venv\Scripts\python.exe -m pytest MIND_GameDev/tests -v

# Baseline MIND Multi-Brain tests (32 passed in ~9s)
venv\Scripts\python.exe -m pytest MIND_Code/tests/test_multi_brain.py MIND_Code/tests/test_asset_pipeline.py -q
```

All 66 tests execute completely offline without consuming paid API credits or tokens.
