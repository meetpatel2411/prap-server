"""
routes.py - Production Readiness Assessment Platform (PRAP)
Web interface views and RESTful API endpoints.
"""

import os
from flask import (
    Blueprint, request, jsonify, render_template,
    redirect, url_for, flash, current_app
)
from database import (
    get_assessment, get_assessments, delete_assessment,
    get_findings, get_finding, update_finding_status,
    create_risk_exception, get_risk_exceptions,
    get_dashboard_analytics, test_connection
)
from rules import get_all_rules, get_rule_by_id
from scanner import process_zip_upload, process_local_directory

bp = Blueprint("prap", __name__)


# =========================================================================
# WEB USER INTERFACE ROUTES (HTML Templates)
# =========================================================================

@bp.route("/", methods=["GET"])
def dashboard():
    """Main executive dashboard showing KPIs, upload launcher, and recent assessments."""
    analytics = get_dashboard_analytics()
    rules = get_all_rules()
    return render_template(
        "dashboard.html",
        analytics=analytics,
        rules=rules,
        active_page="dashboard"
    )


@bp.route("/assessments", methods=["GET"])
def assessments_list_view():
    """Historical assessments listing page."""
    assessments = get_assessments(limit=100)
    return render_template(
        "assessments.html",
        assessments=assessments,
        active_page="assessments"
    )


@bp.route("/assessments/<int:assessment_id>", methods=["GET"])
def assessment_detail_view(assessment_id: int):
    """Detailed assessment report with readiness score, findings, and exceptions."""
    assessment = get_assessment(assessment_id)
    if not assessment:
        flash(f"Assessment #{assessment_id} not found.", "error")
        return redirect(url_for("prap.assessments_list_view"))

    rules = get_all_rules()
    return render_template(
        "assessment_detail.html",
        assessment=assessment,
        rules=rules,
        active_page="assessments"
    )


@bp.route("/findings", methods=["GET"])
def findings_list_view():
    """Centralized findings explorer across all projects."""
    status_filter = request.args.get("status")
    severity_filter = request.args.get("severity")
    category_filter = request.args.get("category")
    
    findings = get_findings(
        status=status_filter,
        severity=severity_filter,
        category=category_filter
    )
    return render_template(
        "findings.html",
        findings=findings,
        selected_status=status_filter,
        selected_severity=severity_filter,
        selected_category=category_filter,
        active_page="findings"
    )


@bp.route("/exceptions", methods=["GET"])
def exceptions_list_view():
    """Risk exceptions management portal."""
    status_filter = request.args.get("status")
    exceptions = get_risk_exceptions(status=status_filter)
    return render_template(
        "exceptions.html",
        exceptions=exceptions,
        selected_status=status_filter,
        active_page="exceptions"
    )


@bp.route("/rules", methods=["GET"])
def rules_catalog_view():
    """Browse the 26 production-readiness rules catalog."""
    rules = get_all_rules()
    return render_template(
        "rules.html",
        rules=rules,
        active_page="rules"
    )


# =========================================================================
# CORE REST API ENDPOINTS
# =========================================================================

@bp.route("/api/assessments", methods=["POST"])
def trigger_assessment():
    """
    POST /api/assessments
    Triggers an assessment. Supports both:
    1. File upload (.zip) via multipart/form-data (Key: 'file' or 'zip_file')
    2. JSON payload with 'project_path' (for local developer automation)
    """
    project_name = None
    if request.is_json:
        project_name = request.json.get("project_name")
    elif request.form:
        project_name = request.form.get("project_name")


    # 1. Check for Zip Upload
    if "file" in request.files or "zip_file" in request.files:
        upload_file = request.files.get("file") or request.files.get("zip_file")
        if not upload_file or upload_file.filename == "":
            return jsonify({"error": "No selected zip file uploaded."}), 400

        try:
            result = process_zip_upload(upload_file, project_name=project_name)
            return jsonify({
                "message": "Assessment completed successfully.",
                "assessment": result
            }), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            current_app.logger.exception("Failed during zip assessment")
            return jsonify({"error": f"Assessment processing failed: {str(e)}"}), 500

    # 2. Check for JSON local path
    elif request.is_json and "project_path" in request.json:
        project_path = request.json.get("project_path")
        if not project_path:
            return jsonify({"error": "project_path cannot be empty."}), 400

        try:
            result = process_local_directory(project_path, project_name=project_name)
            return jsonify({
                "message": "Assessment completed successfully.",
                "assessment": result
            }), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            current_app.logger.exception("Failed during local directory assessment")
            return jsonify({"error": f"Local assessment failed: {str(e)}"}), 500

    else:
        return jsonify({
            "error": "Invalid request. Provide either a .zip file upload ('file') or JSON with 'project_path'."
        }), 400


@bp.route("/api/assessments/<int:assessment_id>", methods=["GET"])
def get_assessment_by_id(assessment_id: int):
    """
    GET /api/assessments/<id>
    Fetches detailed results of a specific assessment.
    """
    assessment = get_assessment(assessment_id)
    if not assessment:
        return jsonify({"error": f"Assessment #{assessment_id} not found."}), 404
    return jsonify(assessment), 200


@bp.route("/api/assessments", methods=["GET"])
def list_assessments():
    """
    GET /api/assessments
    Lists recent assessments.
    """
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    assessments = get_assessments(limit=limit, offset=offset)
    return jsonify({
        "total": len(assessments),
        "assessments": assessments
    }), 200


@bp.route("/api/assessments/<int:assessment_id>", methods=["DELETE"])
def delete_assessment_endpoint(assessment_id: int):
    """
    DELETE /api/assessments/<id>
    Deletes an assessment and cascades to findings.
    """
    success = delete_assessment(assessment_id)
    if not success:
        return jsonify({"error": f"Assessment #{assessment_id} not found."}), 404
    return jsonify({"message": f"Assessment #{assessment_id} deleted."}), 200


@bp.route("/api/findings", methods=["GET"])
def list_findings():
    """
    GET /api/findings
    Lists findings with optional filtering by status, severity, category, or assessment_id.
    """
    assessment_id = request.args.get("assessment_id", type=int)
    status = request.args.get("status")
    severity = request.args.get("severity")
    category = request.args.get("category")

    findings = get_findings(
        assessment_id=assessment_id,
        status=status,
        severity=severity,
        category=category
    )
    return jsonify({
        "count": len(findings),
        "findings": findings
    }), 200


@bp.route("/api/findings/<int:finding_id>", methods=["GET"])
def get_finding_by_id(finding_id: int):
    """
    GET /api/findings/<id>
    Retrieves a single finding.
    """
    finding = get_finding(finding_id)
    if not finding:
        return jsonify({"error": f"Finding #{finding_id} not found."}), 404
    return jsonify(finding), 200


@bp.route("/api/findings/<int:finding_id>/status", methods=["PATCH"])
def update_status_endpoint(finding_id: int):
    """
    PATCH /api/findings/<id>/status
    Updates finding status (e.g. Open, In Review, Resolved, Exception Granted).
    """
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    valid_statuses = {"Open", "In Review", "Resolved", "Exception Granted"}
    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400

    success = update_finding_status(finding_id, new_status)
    if not success:
        return jsonify({"error": f"Finding #{finding_id} not found."}), 404

    return jsonify({"message": f"Finding #{finding_id} status updated to '{new_status}'."}), 200


@bp.route("/api/exceptions", methods=["POST"])
def submit_risk_exception():
    """
    POST /api/exceptions
    Creates a risk exception according to the workflow:
    finding_id, owner, requested_by, reason, expiry_date.
    """
    data = request.get_json(silent=True) or request.form.to_dict()

    required_fields = ["finding_id", "owner", "requested_by", "reason", "expiry_date"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        finding_id = int(data["finding_id"])
    except ValueError:
        return jsonify({"error": "finding_id must be an integer."}), 400

    finding = get_finding(finding_id)
    if not finding:
        return jsonify({"error": f"Associated finding #{finding_id} not found."}), 404

    exception_record = {
        "finding_id": finding_id,
        "assessment_id": finding.get("assessment_id"),
        "rule_id": finding.get("rule_id"),
        "owner": data["owner"].strip(),
        "requested_by": data["requested_by"].strip(),
        "reason": data["reason"].strip(),
        "expiry_date": data["expiry_date"].strip()
    }

    try:
        exception_id = create_risk_exception(exception_record)
        return jsonify({
            "message": "Risk exception granted successfully.",
            "exception_id": exception_id
        }), 201
    except Exception as e:
        return jsonify({"error": f"Failed to record exception: {str(e)}"}), 500


@bp.route("/api/exceptions", methods=["GET"])
def list_risk_exceptions():
    """
    GET /api/exceptions
    Lists recorded risk exceptions.
    """
    status = request.args.get("status")
    exceptions = get_risk_exceptions(status=status)
    return jsonify({
        "count": len(exceptions),
        "exceptions": exceptions
    }), 200


@bp.route("/api/rules", methods=["GET"])
def list_rules():
    """
    GET /api/rules
    Returns catalog of the 26 readiness rules.
    """
    rules = get_all_rules()
    return jsonify({
        "count": len(rules),
        "rules": rules
    }), 200


@bp.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats_api():
    """
    GET /api/dashboard/stats
    Returns aggregate stats for metrics dashboard.
    """
    return jsonify(get_dashboard_analytics()), 200


@bp.route("/api/health", methods=["GET"])
def health_check():
    """
    GET /api/health
    Lightweight health and database connectivity check.
    """
    db_status = test_connection()
    status_code = 200 if db_status.get("status") == "connected" else 503
    return jsonify({
        "service": "Production Readiness Assessment Platform (PRAP)",
        "status": "healthy" if status_code == 200 else "degraded",
        "database": db_status
    }), status_code
