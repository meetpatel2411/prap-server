"""
scanner.py - Production Readiness Assessment Platform (PRAP)
Assessment processing pipeline and file scanner.
Handles temporary zip file ingestion, secure extraction, rule evaluation, scoring,
and guaranteed disk cleanup.
"""

import os
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from werkzeug.utils import secure_filename

from rules import get_all_rules, evaluate_rule
from database import save_assessment

# Use /tmp/prap_uploads on Linux/EC2, with cross-platform fallback for Windows/local dev
def get_upload_base_dir() -> str:
    if os.name != 'nt' and os.path.exists('/tmp'):
        base = '/tmp/prap_uploads'
    else:
        base = os.path.join(tempfile.gettempdir(), 'prap_uploads')
    os.makedirs(base, exist_ok=True)
    return base


def is_safe_zip_path(base_dir: str, target_path: str) -> bool:
    """Guards against Zip Slip (Path Traversal) vulnerabilities."""
    abs_base = os.path.abspath(base_dir)
    abs_target = os.path.abspath(target_path)
    return abs_target.startswith(abs_base)


def evaluate_project(project_dir: str, project_name: str, scan_type: str = "zip_upload") -> Dict[str, Any]:
    """
    Executes all configured readiness rules against the target project directory.
    Calculates weighted score, status, and saves results to SQLite.
    """
    start_time = time.time()
    scan_uuid = str(uuid.uuid4())
    rules = get_all_rules()

    total_rules = len(rules)
    passed_rules = 0
    failed_rules = 0
    total_weight = 0
    passed_weight = 0
    has_critical_failure = False

    all_findings: List[Dict[str, Any]] = []
    rule_results: List[Dict[str, Any]] = []

    for rule in rules:
        weight = rule.get("weight", 1)
        total_weight += weight

        passed, findings = evaluate_rule(rule, project_dir)

        if passed:
            passed_rules += 1
            passed_weight += weight
            rule_results.append({
                "rule_id": rule.get("id"),
                "name": rule.get("name"),
                "category": rule.get("category"),
                "severity": rule.get("severity"),
                "passed": True,
                "description": rule.get("description")
            })
        else:
            failed_rules += 1
            if rule.get("severity", "").lower() == "critical":
                has_critical_failure = True

            all_findings.extend(findings)
            rule_results.append({
                "rule_id": rule.get("id"),
                "name": rule.get("name"),
                "category": rule.get("category"),
                "severity": rule.get("severity"),
                "passed": False,
                "description": rule.get("description"),
                "findings_count": len(findings)
            })

    # Calculate overall readiness score (0 - 100)
    if total_weight > 0:
        score = int(round((passed_weight / total_weight) * 100))
    else:
        score = int(round((passed_rules / max(total_rules, 1)) * 100))

    score = max(0, min(100, score))

    # Determine readiness status
    if score >= 85 and not has_critical_failure:
        status = "Ready"
    elif score >= 60:
        status = "Needs Attention"
    else:
        status = "High Risk"

    duration_ms = int((time.time() - start_time) * 1000)

    summary = (
        f"Assessed {total_rules} production rules: {passed_rules} passed, "
        f"{failed_rules} failed ({len(all_findings)} finding(s)). "
        f"Readiness Score: {score}/100. Status: {status}."
    )

    assessment_record = {
        "uuid": scan_uuid,
        "project_name": project_name,
        "project_path": project_dir,
        "scan_type": scan_type,
        "score": score,
        "total_rules": total_rules,
        "passed_rules": passed_rules,
        "failed_rules": failed_rules,
        "status": status,
        "summary": summary,
        "duration_ms": duration_ms
    }

    # Persist in SQLite
    assessment_id = save_assessment(assessment_record, all_findings)
    assessment_record["id"] = assessment_id
    assessment_record["findings"] = all_findings
    assessment_record["rule_results"] = rule_results

    return assessment_record


def process_zip_upload(file_storage, project_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Temporary Processing Pipeline (Phase 2):
    1. Saves uploaded .zip to /tmp/prap_uploads/ (or OS temp dir).
    2. Extracts the contents to a unique UUID folder.
    3. Runs the assessment engine against this extracted directory.
    4. Crucial: Deletes the extracted directory and zip immediately in finally block.
    """
    filename = secure_filename(file_storage.filename or "project.zip")
    if not filename.lower().endswith(".zip"):
        raise ValueError("Uploaded file must be a valid .zip archive.")

    scan_uuid = str(uuid.uuid4())
    base_dir = get_upload_base_dir()

    zip_path = os.path.join(base_dir, f"{scan_uuid}_{filename}")
    extract_dir = os.path.join(base_dir, f"extract_{scan_uuid}")

    if not project_name:
        project_name = os.path.splitext(filename)[0]

    try:
        # 1. Save uploaded zip file
        file_storage.save(zip_path)

        # 2. Extract contents securely to unique folder
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                # Prevent Zip Slip directory traversal
                target_file_path = os.path.join(extract_dir, member.filename)
                if not is_safe_zip_path(extract_dir, target_file_path):
                    raise ValueError(f"Security error: Archive member '{member.filename}' attempts path traversal.")
                zf.extract(member, extract_dir)

        # Handle top-level single directory in zip if present
        scan_target_dir = extract_dir
        sub_items = [os.path.join(extract_dir, i) for i in os.listdir(extract_dir)]
        if len(sub_items) == 1 and os.path.isdir(sub_items[0]):
            scan_target_dir = sub_items[0]

        # 3. Run assessment engine
        result = evaluate_project(
            project_dir=scan_target_dir,
            project_name=project_name,
            scan_type="zip_upload"
        )
        return result

    finally:
        # 4. Crucial: Clean up extracted directory and uploaded zip file
        # to prevent EBS volume from filling up!
        if os.path.exists(extract_dir):
            try:
                shutil.rmtree(extract_dir, ignore_errors=True)
            except Exception:
                pass

        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass


def process_local_directory(project_path: str, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Scans a local project path directly (convenient for local CLI / dev use)."""
    if not os.path.exists(project_path) or not os.path.isdir(project_path):
        raise ValueError(f"Specified project path does not exist or is not a directory: {project_path}")

    if not project_name:
        project_name = os.path.basename(os.path.abspath(project_path))

    return evaluate_project(
        project_dir=os.path.abspath(project_path),
        project_name=project_name,
        scan_type="local_path"
    )
