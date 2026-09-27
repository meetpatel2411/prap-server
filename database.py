"""
database.py - Production Readiness Assessment Platform (PRAP)
SQLite database interface and schema management.
Provides connection pooling, table initialization, and CRUD operations.
"""

import os
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional
from rules import load_rules

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def get_db_path() -> str:
    """Returns the database file path from environment variable or default."""
    return os.environ.get("PRAP_DB_PATH", DEFAULT_DB_PATH)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Creates a new SQLite connection with foreign keys enabled and Row factory."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None):
    """
    Initializes database tables according to Section 10.1 of SRS:
    Assessment, Finding, Rule, and RiskException tables.
    """
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    with get_connection(path) as conn:
        cursor = conn.cursor()

        # Assessment Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                project_name TEXT NOT NULL,
                project_path TEXT,
                scan_type TEXT DEFAULT 'zip_upload',
                score INTEGER NOT NULL DEFAULT 0,
                total_rules INTEGER NOT NULL DEFAULT 0,
                passed_rules INTEGER NOT NULL DEFAULT 0,
                failed_rules INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Needs Attention',
                summary TEXT,
                duration_ms INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Finding Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assessment_id INTEGER NOT NULL,
                rule_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                description TEXT,
                file_path TEXT,
                line_number INTEGER DEFAULT 0,
                snippet TEXT,
                suggestion TEXT,
                status TEXT DEFAULT 'Open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
            );
        """)

        # Rule Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                weight INTEGER DEFAULT 1,
                description TEXT,
                suggestion TEXT,
                check_type TEXT DEFAULT 'custom',
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Risk Exception Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_exceptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id INTEGER NOT NULL,
                assessment_id INTEGER,
                rule_id TEXT NOT NULL,
                owner TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                status TEXT DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (finding_id) REFERENCES findings (id) ON DELETE CASCADE
            );
        """)

        # Performance Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_assessment ON findings(assessment_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assessments_created ON assessments(created_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exceptions_finding ON risk_exceptions(finding_id);")

        conn.commit()

    # Seed rules catalog into SQLite if empty
    sync_rules_to_db(path)


def sync_rules_to_db(db_path: Optional[str] = None):
    """Populates or updates the rules table from rules.yaml."""
    path = db_path or get_db_path()
    try:
        yaml_rules = load_rules()
    except Exception:
        return

    with get_connection(path) as conn:
        cursor = conn.cursor()
        for r in yaml_rules:
            cursor.execute("""
                INSERT INTO rules (rule_id, name, category, severity, weight, description, suggestion, check_type, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(rule_id) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    severity=excluded.severity,
                    weight=excluded.weight,
                    description=excluded.description,
                    suggestion=excluded.suggestion,
                    check_type=excluded.check_type;
            """, (
                r.get("id"),
                r.get("name"),
                r.get("category"),
                r.get("severity"),
                r.get("weight", 1),
                r.get("description", ""),
                r.get("suggestion", ""),
                r.get("check_type", "custom")
            ))
        conn.commit()


def test_connection(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Tests database connectivity and returns status metadata."""
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS count FROM rules;")
            rule_count = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM assessments;")
            assessment_count = cursor.fetchone()["count"]
            return {
                "status": "connected",
                "engine": "SQLite3",
                "database_path": db_path or get_db_path(),
                "rules_loaded": rule_count,
                "total_assessments": assessment_count
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def save_assessment(assessment_data: Dict[str, Any], findings: List[Dict[str, Any]], db_path: Optional[str] = None) -> int:
    """Stores assessment result and related findings in an atomic transaction."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO assessments (
                uuid, project_name, project_path, scan_type, score,
                total_rules, passed_rules, failed_rules, status, summary, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            assessment_data["uuid"],
            assessment_data.get("project_name", "Unnamed Project"),
            assessment_data.get("project_path", ""),
            assessment_data.get("scan_type", "zip_upload"),
            assessment_data.get("score", 0),
            assessment_data.get("total_rules", 0),
            assessment_data.get("passed_rules", 0),
            assessment_data.get("failed_rules", 0),
            assessment_data.get("status", "Needs Attention"),
            assessment_data.get("summary", ""),
            assessment_data.get("duration_ms", 0)
        ))
        assessment_id = cursor.lastrowid

        for f in findings:
            cursor.execute("""
                INSERT INTO findings (
                    assessment_id, rule_id, rule_name, category, severity,
                    description, file_path, line_number, snippet, suggestion, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open');
            """, (
                assessment_id,
                f.get("rule_id", ""),
                f.get("rule_name", ""),
                f.get("category", "General"),
                f.get("severity", "Medium"),
                f.get("description", ""),
                f.get("file_path", ""),
                f.get("line_number", 0),
                f.get("snippet", ""),
                f.get("suggestion", ""),
            ))

        conn.commit()
        return assessment_id


def get_assessment(assessment_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves an individual assessment with its findings and exceptions."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM assessments WHERE id = ?;", (assessment_id,))
        row = cursor.fetchone()
        if not row:
            return None

        assessment = dict(row)
        cursor.execute("SELECT * FROM findings WHERE assessment_id = ? ORDER BY id ASC;", (assessment_id,))
        assessment["findings"] = [dict(f) for f in cursor.fetchall()]

        cursor.execute("SELECT * FROM risk_exceptions WHERE assessment_id = ? ORDER BY id DESC;", (assessment_id,))
        assessment["exceptions"] = [dict(e) for e in cursor.fetchall()]

        return assessment


def get_assessments(limit: int = 50, offset: int = 0, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves previous assessment records with pagination."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM assessments 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?;
        """, (limit, offset))
        return [dict(row) for row in cursor.fetchall()]


def delete_assessment(assessment_id: int, db_path: Optional[str] = None) -> bool:
    """Deletes an assessment and cascades to findings."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM assessments WHERE id = ?;", (assessment_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_findings(assessment_id: Optional[int] = None, status: Optional[str] = None,
                 severity: Optional[str] = None, category: Optional[str] = None,
                 db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves findings with flexible filtering."""
    path = db_path or get_db_path()
    query = "SELECT f.*, a.project_name FROM findings f JOIN assessments a ON f.assessment_id = a.id WHERE 1=1"
    params = []

    if assessment_id is not None:
        query += " AND f.assessment_id = ?"
        params.append(assessment_id)
    if status:
        query += " AND f.status = ?"
        params.append(status)
    if severity:
        query += " AND f.severity = ?"
        params.append(severity)
    if category:
        query += " AND f.category = ?"
        params.append(category)

    query += " ORDER BY f.id DESC LIMIT 100;"

    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_finding(finding_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves an individual finding."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT f.*, a.project_name FROM findings f JOIN assessments a ON f.assessment_id = a.id WHERE f.id = ?;", (finding_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_finding_status(finding_id: int, status: str, db_path: Optional[str] = None) -> bool:
    """Updates the tracked status of a finding."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE findings SET status = ? WHERE id = ?;", (status, finding_id))
        conn.commit()
        return cursor.rowcount > 0


def create_risk_exception(exception_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Records a risk exception and updates the associated finding status."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO risk_exceptions (
                finding_id, assessment_id, rule_id, owner, requested_by, reason, expiry_date, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Active');
        """, (
            exception_data["finding_id"],
            exception_data.get("assessment_id"),
            exception_data.get("rule_id", ""),
            exception_data["owner"],
            exception_data["requested_by"],
            exception_data["reason"],
            exception_data["expiry_date"]
        ))
        exception_id = cursor.lastrowid

        # Update finding status to 'Exception Granted'
        cursor.execute("UPDATE findings SET status = 'Exception Granted' WHERE id = ?;", (exception_data["finding_id"],))
        conn.commit()
        return exception_id


def get_risk_exceptions(status: Optional[str] = None, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all risk exceptions."""
    path = db_path or get_db_path()
    query = """
        SELECT e.*, f.rule_name, f.category, f.severity, a.project_name
        FROM risk_exceptions e
        JOIN findings f ON e.finding_id = f.id
        LEFT JOIN assessments a ON e.assessment_id = a.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND e.status = ?"
        params.append(status)

    query += " ORDER BY e.id DESC;"

    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_dashboard_analytics(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Provides aggregated metrics for the dashboard KPI cards."""
    path = db_path or get_db_path()
    with get_connection(path) as conn:
        cursor = conn.cursor()

        # Total Assessments
        cursor.execute("SELECT COUNT(*) AS total, AVG(score) AS avg_score FROM assessments;")
        row = cursor.fetchone()
        total_assessments = row["total"] or 0
        avg_score = round(row["avg_score"] or 0, 1)

        # Ready vs Attention counts
        cursor.execute("SELECT COUNT(*) AS ready_count FROM assessments WHERE status = 'Ready';")
        ready_count = cursor.fetchone()["ready_count"] or 0

        cursor.execute("SELECT COUNT(*) AS attention_count FROM assessments WHERE status IN ('Needs Attention', 'High Risk');")
        attention_count = cursor.fetchone()["attention_count"] or 0

        # Open Findings
        cursor.execute("SELECT COUNT(*) AS open_findings FROM findings WHERE status = 'Open';")
        open_findings = cursor.fetchone()["open_findings"] or 0

        # Active Exceptions
        cursor.execute("SELECT COUNT(*) AS active_exceptions FROM risk_exceptions WHERE status = 'Active';")
        active_exceptions = cursor.fetchone()["active_exceptions"] or 0

        # Category Breakdown of findings
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM findings 
            GROUP BY category;
        """)
        categories = {row["category"]: row["count"] for row in cursor.fetchall()}

        # Severity Breakdown of findings
        cursor.execute("""
            SELECT severity, COUNT(*) as count 
            FROM findings 
            GROUP BY severity;
        """)
        severities = {row["severity"]: row["count"] for row in cursor.fetchall()}

        # Recent 5 assessments
        cursor.execute("""
            SELECT id, uuid, project_name, score, status, passed_rules, failed_rules, total_rules, created_at 
            FROM assessments 
            ORDER BY created_at DESC 
            LIMIT 5;
        """)
        recent_assessments = [dict(r) for r in cursor.fetchall()]

        return {
            "total_assessments": total_assessments,
            "average_score": avg_score,
            "ready_projects": ready_count,
            "attention_projects": attention_count,
            "open_findings": open_findings,
            "active_exceptions": active_exceptions,
            "categories": categories,
            "severities": severities,
            "recent_assessments": recent_assessments
        }
