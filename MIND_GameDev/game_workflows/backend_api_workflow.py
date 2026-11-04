"""
MIND Universal Development Studio — Backend API Workflow.
Generates robust REST API microservices with FastAPI (or Flask fallback),
Pydantic data validation schemas, structured endpoints, and automated pytest test suites.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_workflow import BaseProjectWorkflow
from ..models import ProjectSpecification, ProjectType, ExecutionReport
from ..tools.workspace_files import SafeWorkspaceManager


class BackendApiWorkflow(BaseProjectWorkflow):
    """Workflow for backend APIs, microservices, and web services."""

    project_type = ProjectType.BACKEND_API

    def build(self, spec: ProjectSpecification, workspace: SafeWorkspaceManager) -> Dict[str, Any]:
        title = spec.title or "Nexus REST API"
        desc = spec.description or "High-throughput asynchronous REST microservice with FastAPI"

        workspace.create_directory("app")
        workspace.create_directory("tests")

        self._write_app_py(workspace, title)
        self._write_models_py(workspace)
        self._write_test_api_py(workspace)
        self._write_requirements_txt(workspace)
        self._write_run_py(workspace, title)
        self._write_manifest(workspace, title, desc)

        return {
            "status": "SUCCESS",
            "project_type": "backend_api",
            "title": title,
            "entry_point": "app/main.py",
        }

    def _write_app_py(self, ws: SafeWorkspaceManager, title: str) -> None:
        code = f"""\"\"\"
{title} — Core FastAPI Application.
Provides health monitoring, resource CRUD, and inventory analytics.
\"\"\"

import time
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from .models import ItemCreate, ItemUpdate, ItemResponse, HealthResponse, StatsResponse

app = FastAPI(
    title="{title}",
    description="Autonomously Generated Microservice API by MIND Universal Studio",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory Database Store
db: dict[str, dict] = {{
    "item-1": {{
        "id": "item-1",
        "title": "Quantum Compute Blade",
        "description": "High-density rackmount neural accelerator",
        "category": "hardware",
        "price": 12499.99,
        "in_stock": True,
        "created_at": time.time() - 86400,
    }},
    "item-2": {{
        "id": "item-2",
        "title": "Edge Gateway Appliance",
        "description": "Low-power IoT cryptographic firewall router",
        "category": "networking",
        "price": 899.50,
        "in_stock": True,
        "created_at": time.time() - 43200,
    }},
}}

START_TIME = time.time()


@app.get("/", tags=["System"])
def root():
    return {{"message": "{title} is operational", "docs": "/docs"}}


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    return HealthResponse(
        status="healthy",
        uptime_seconds=round(time.time() - START_TIME, 2),
        version="1.0.0",
        database_connected=True,
    )


@app.get("/api/v1/items", response_model=List[ItemResponse], tags=["Items"])
def list_items(
    category: Optional[str] = Query(None, description="Filter by category"),
    in_stock_only: bool = Query(False, description="Filter only in-stock items"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    items = list(db.values())
    if category:
        items = [i for i in items if i["category"].lower() == category.lower()]
    if in_stock_only:
        items = [i for i in items if i["in_stock"]]
    return items[skip : skip + limit]


@app.post("/api/v1/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED, tags=["Items"])
def create_item(payload: ItemCreate):
    item_id = f"item-{{len(db) + 1}}-{{int(time.time()) % 10000}}"
    new_item = {{
        "id": item_id,
        "title": payload.title,
        "description": payload.description,
        "category": payload.category,
        "price": payload.price,
        "in_stock": payload.in_stock,
        "created_at": time.time(),
    }}
    db[item_id] = new_item
    return new_item


@app.get("/api/v1/items/{{item_id}}", response_model=ItemResponse, tags=["Items"])
def get_item(item_id: str):
    if item_id not in db:
        raise HTTPException(status_code=404, detail=f"Item with ID '{{item_id}}' not found")
    return db[item_id]


@app.put("/api/v1/items/{{item_id}}", response_model=ItemResponse, tags=["Items"])
def update_item(item_id: str, payload: ItemUpdate):
    if item_id not in db:
        raise HTTPException(status_code=404, detail=f"Item with ID '{{item_id}}' not found")
    
    item = db[item_id]
    update_data = payload.model_dump(exclude_unset=True)
    item.update(update_data)
    return item


@app.delete("/api/v1/items/{{item_id}}", status_code=status.HTTP_200_OK, tags=["Items"])
def delete_item(item_id: str):
    if item_id not in db:
        raise HTTPException(status_code=404, detail=f"Item with ID '{{item_id}}' not found")
    deleted = db.pop(item_id)
    return {{"success": True, "deleted_id": item_id, "title": deleted["title"]}}


@app.get("/api/v1/stats", response_model=StatsResponse, tags=["Analytics"])
def get_stats():
    total_items = len(db)
    total_val = sum(i["price"] for i in db.values())
    avg_price = (total_val / total_items) if total_items > 0 else 0.0
    return StatsResponse(
        total_items=total_items,
        total_inventory_value=round(total_val, 2),
        average_price=round(avg_price, 2),
    )
"""
        ws.write_file("app/main.py", code, overwrite=True)

    def _write_models_py(self, ws: SafeWorkspaceManager) -> None:
        code = """\"\"\"Pydantic Request and Response Schemas.\"\"\"

from typing import Optional
from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    category: str = Field("general", min_length=2, max_length=50)
    price: float = Field(..., gt=0.0)
    in_stock: bool = True


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(None, gt=0.0)
    in_stock: Optional[bool] = None


class ItemResponse(ItemBase):
    id: str
    created_at: float


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    version: str
    database_connected: bool


class StatsResponse(BaseModel):
    total_items: int
    total_inventory_value: float
    average_price: float
"""
        ws.write_file("app/models.py", code, overwrite=True)

    def _write_test_api_py(self, ws: SafeWorkspaceManager) -> None:
        code = """\"\"\"Automated Test Suite for REST API Endpoints.\"\"\"

import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "operational" in response.json()["message"]


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True


def test_list_items():
    response = client.get("/api/v1/items")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) >= 2


def test_create_and_get_item():
    payload = {
        "title": "Autonomous Drone Sensor",
        "description": "LIDAR telemetry module",
        "category": "avionics",
        "price": 3499.00,
        "in_stock": True,
    }
    # 1. Create
    create_resp = client.post("/api/v1/items", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["title"] == payload["title"]
    assert "id" in created

    # 2. Get by ID
    item_id = created["id"]
    get_resp = client.get(f"/api/v1/items/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == item_id


def test_update_item():
    update_payload = {"price": 2999.00, "in_stock": False}
    resp = client.put("/api/v1/items/item-1", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["price"] == 2999.00
    assert data["in_stock"] is False


def test_delete_item():
    # Create temporary item
    c_resp = client.post("/api/v1/items", json={"title": "To Delete", "price": 10.0, "category": "temp"})
    del_id = c_resp.json()["id"]

    # Delete
    del_resp = client.delete(f"/api/v1/items/{del_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Confirm 404
    get_again = client.get(f"/api/v1/items/{del_id}")
    assert get_again.status_code == 404


def test_nonexistent_item_404():
    resp = client.get("/api/v1/items/non_existent_id_9999")
    assert resp.status_code == 404


def test_stats_analytics():
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] >= 1
    assert data["total_inventory_value"] > 0
"""
        ws.write_file("tests/test_api.py", code, overwrite=True)

    def _write_requirements_txt(self, ws: SafeWorkspaceManager) -> None:
        content = "fastapi>=0.100.0\nuvicorn>=0.20.0\npydantic>=2.0.0\npytest>=7.0.0\nhttpx>=0.24.0\n"
        ws.write_file("requirements.txt", content, overwrite=True)

    def _write_run_py(self, ws: SafeWorkspaceManager, title: str) -> None:
        code = """\"\"\"FastAPI Application Local Runner.\"\"\"
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
"""
        ws.write_file("run.py", code, overwrite=True)

    def _write_manifest(self, ws: SafeWorkspaceManager, title: str, desc: str) -> None:
        manifest = {
            "name": title.lower().replace(" ", "_"),
            "title": title,
            "type": "backend_api",
            "framework": "fastapi",
            "entry_point": "app/main.py",
            "endpoints": [
                "GET /",
                "GET /health",
                "GET /api/v1/items",
                "POST /api/v1/items",
                "GET /api/v1/items/{id}",
                "PUT /api/v1/items/{id}",
                "DELETE /api/v1/items/{id}",
                "GET /api/v1/stats",
            ],
            "test_command": "pytest tests/ -v",
            "run_command": "uvicorn app.main:app --port 8000",
        }
        ws.write_file("project.json", json.dumps(manifest, indent=2), overwrite=True)

    def verify(self, project_dir: Path) -> ExecutionReport:
        """Executes automated endpoint testing via pytest in the project directory."""
        start_time = time.time()
        test_file = project_dir / "tests" / "test_api.py"

        errors: List[str] = []
        tests_passed = 0
        tests_failed = 0

        # 1. Static file check
        expected_files = ["app/main.py", "app/models.py", "tests/test_api.py", "project.json"]
        files_checked = [f.name for f in project_dir.rglob("*.py")] + ["project.json"]
        for f in expected_files:
            if not (project_dir / f).exists():
                errors.append(f"Missing essential file: {f}")

        # 2. Run pytest in project directory
        cmd = [sys.executable, "-m", "pytest", str(test_file), "-v"]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_dir.resolve())

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(project_dir.resolve()),
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = proc.stdout + proc.stderr
            for line in output.splitlines():
                if " PASSED" in line:
                    tests_passed += 1
                elif " FAILED" in line or " ERROR" in line:
                    tests_failed += 1
                    errors.append(line.strip())

            success = proc.returncode == 0 and len(errors) == 0
        except Exception as e:
            success = False
            errors.append(f"Pytest execution failed: {e}")

        elapsed = round(time.time() - start_time, 3)
        return ExecutionReport(
            workflow_id=str(uuid.uuid4())[:8],
            project_name=project_dir.name,
            success=success,
            status="VERIFIED" if success else "FAILED",
            target_engine="FastAPI",
            project_type="backend_api",
            project_path=str(project_dir),
            entry_point="app/main.py",
            files_created=files_checked,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            elapsed_seconds=elapsed,
            summary=f"Backend API verification completed: {tests_passed} passed, {tests_failed} failed in {elapsed}s.",
            errors=errors,
            details={"pytest_output": output if 'output' in locals() else ""},
        )

    def get_run_instructions(self, project_dir: Path) -> Dict[str, Any]:
        return {
            "run_command": f"uvicorn app.main:app --port 8000 --app-dir {project_dir}",
            "url": "http://127.0.0.1:8000/docs",
            "instructions": "Run uvicorn or python run.py to launch the interactive Swagger UI at /docs.",
        }
