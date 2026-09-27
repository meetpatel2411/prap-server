"""
tests/test_prap.py - Comprehensive Test Suite for PRAP
Tests rule engine, database operations, temporary upload pipeline,
readiness scoring, and web/API routes.
"""

import os
import io
import json
import zipfile
import tempfile
import pytest

from app import create_app
from database import init_db, get_connection
from rules import load_rules, get_all_rules


@pytest.fixture
def temp_db():
    """Provides a fresh isolated temporary SQLite database for tests."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_database.db")
    init_db(db_path)
    yield db_path


@pytest.fixture
def app_instance(temp_db):
    """Provides a configured Flask test application."""
    test_config = {
        "TESTING": True,
        "PRAP_DB_PATH": temp_db,
        "SECRET_KEY": "test-secret-key"
    }
    app = create_app(test_config=test_config)
    yield app


@pytest.fixture
def client(app_instance):
    """Provides Flask test client."""
    return app_instance.test_client()


def test_26_rules_catalog_loaded():
    """Verifies that all 26 production readiness rules are loaded with valid schemas."""
    rules = load_rules()
    assert len(rules) == 26, f"Expected 26 rules, found {len(rules)}"

    expected_categories = {"Security", "Reliability", "Observability", "Performance", "Operations", "Documentation"}
    categories_found = {r.get("category") for r in rules}
    assert categories_found == expected_categories

    for r in rules:
        assert "id" in r and len(r["id"]) >= 6
        assert "name" in r and len(r["name"]) > 0
        assert "severity" in r and r["severity"] in {"Critical", "High", "Medium", "Low"}
        assert "weight" in r and r["weight"] >= 1
        assert "check_type" in r


def test_health_check_endpoint(client):
    """Verifies GET /api/health returns HTTP 200 and healthy database status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"]["status"] == "connected"
    assert data["database"]["rules_loaded"] == 26


def test_rules_api_endpoint(client):
    """Verifies GET /api/rules returns catalog of 26 rules."""
    response = client.get("/api/rules")
    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 26
    assert len(data["rules"]) == 26


def test_web_routes_render_html(client):
    """Verifies that all HTML views render without template errors."""
    routes = ["/", "/assessments", "/findings", "/exceptions", "/rules"]
    for r in routes:
        response = client.get(r)
        assert response.status_code == 200
        assert b"PRAP" in response.data


def test_zip_upload_assessment_pipeline(client):
    """
    Tests Phase 2: In-memory Zip upload, extraction, assessment scoring,
    and automatic cleanup.
    """
    # Create an in-memory zip file representing a microservice
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. requirements.txt
        zf.writestr("requirements.txt", "flask>=3.0.0\ngunicorn>=21.0.0\npytest>=8.0.0\n")
        
        # 2. .gitignore
        zf.writestr(".gitignore", ".env\n*.pem\nvenv/\n__pycache__/\n")
        
        # 3. README.md
        zf.writestr("README.md", "# Test Service\n## Setup\nRun setup instructions.\n## Deploy\nDeploy instructions.\n")
        
        # 4. app.py with health endpoint & logging
        app_code = (
            "import os, logging\n"
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "logger = logging.getLogger(__name__)\n"
            "@app.route('/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n"
            "if __name__ == '__main__':\n"
            "    app.run(debug=False)\n"
        )
        zf.writestr("app.py", app_code)
        
        # 5. tests/test_app.py
        zf.writestr("tests/test_app.py", "def test_dummy(): assert True\n")
        
        # 6. prap.service & prap_nginx.conf
        zf.writestr("prap.service", "[Unit]\nDescription=Service\n")
        zf.writestr("prap_nginx.conf", "server { listen 80; }\n")

    zip_buffer.seek(0)

    # Post zip file to /api/assessments
    response = client.post(
        "/api/assessments",
        data={
            "file": (zip_buffer, "test_microservice.zip"),
            "project_name": "TestMicroservice"
        },
        content_type="multipart/form-data"
    )

    assert response.status_code == 201
    data = response.get_json()
    assert "assessment" in data
    assessment = data["assessment"]

    assert assessment["project_name"] == "TestMicroservice"
    assert assessment["total_rules"] == 26
    assert assessment["score"] > 0
    assert assessment["status"] in {"Ready", "Needs Attention", "High Risk"}
    assert "id" in assessment

    assessment_id = assessment["id"]

    # Verify GET /api/assessments/<id>
    get_res = client.get(f"/api/assessments/{assessment_id}")
    assert get_res.status_code == 200
    res_data = get_res.get_json()
    assert res_data["id"] == assessment_id
    assert res_data["project_name"] == "TestMicroservice"


def test_risk_exception_workflow(client):
    """
    Tests Phase 1.4 & Section 11.3:
    Submitting a risk exception for a finding and verifying status transition.
    """
    # Create an assessment with an intentional finding (hardcoded secret)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.py", "API_KEY = 'super_secret_test_key_12345'\n")

    zip_buffer.seek(0)

    res = client.post(
        "/api/assessments",
        data={"file": (zip_buffer, "vulnerable_app.zip"), "project_name": "VulnerableApp"},
        content_type="multipart/form-data"
    )
    assert res.status_code == 201
    assessment = res.get_json()["assessment"]
    assert assessment["failed_rules"] > 0

    # Retrieve findings
    findings_res = client.get(f"/api/findings?assessment_id={assessment['id']}")
    assert findings_res.status_code == 200
    findings = findings_res.get_json()["findings"]
    assert len(findings) > 0

    target_finding = findings[0]
    assert target_finding["status"] == "Open"

    # Submit Risk Exception
    exc_payload = {
        "finding_id": target_finding["id"],
        "owner": "Security Team Lead",
        "requested_by": "Developer Bob",
        "reason": "Legacy test credential will be rotated in next sprint.",
        "expiry_date": "2026-12-31"
    }
    exc_res = client.post("/api/exceptions", json=exc_payload)
    assert exc_res.status_code == 201

    # Verify finding status is now 'Exception Granted'
    updated_finding_res = client.get(f"/api/findings/{target_finding['id']}")
    assert updated_finding_res.status_code == 200
    assert updated_finding_res.get_json()["status"] == "Exception Granted"

    # Verify listing exceptions
    list_exc_res = client.get("/api/exceptions")
    assert list_exc_res.status_code == 200
    assert list_exc_res.get_json()["count"] >= 1


def test_dashboard_analytics_api(client):
    """Verifies GET /api/dashboard/stats returns aggregated metrics."""
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    stats = response.get_json()
    assert "total_assessments" in stats
    assert "average_score" in stats
    assert "ready_projects" in stats
    assert "open_findings" in stats
