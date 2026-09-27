"""
rules.py - Production Readiness Assessment Platform (PRAP)
Rule engine loader and evaluator.
Loads rules from rules.yaml and evaluates them against project directories.
"""

import os
import re
import yaml
from pathlib import Path
from typing import List, Dict, Any, Tuple

DEFAULT_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.yaml")

# In-memory rule catalog cache
_RULES_CACHE: List[Dict[str, Any]] = []
_RULES_BY_ID: Dict[str, Dict[str, Any]] = {}


def load_rules(yaml_path: str = None) -> List[Dict[str, Any]]:
    """
    Loads rules from the specified YAML file into a dictionary/list on app startup.
    """
    global _RULES_CACHE, _RULES_BY_ID
    if yaml_path is None:
        yaml_path = DEFAULT_RULES_PATH

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"Rules YAML file not found at: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    rules = data.get("rules", [])
    _RULES_CACHE = rules
    _RULES_BY_ID = {rule["id"]: rule for rule in rules if "id" in rule}
    return _RULES_CACHE


def get_all_rules() -> List[Dict[str, Any]]:
    """Returns all cached rules, loading them if not yet loaded."""
    if not _RULES_CACHE:
        load_rules()
    return _RULES_CACHE


def get_rule_by_id(rule_id: str) -> Dict[str, Any]:
    """Retrieves a single rule by its unique ID."""
    if not _RULES_BY_ID:
        load_rules()
    return _RULES_BY_ID.get(rule_id)


def is_binary_or_ignored(filepath: Path) -> bool:
    """Helper to skip binary, git, and compiled files."""
    ignored_parts = {".git", "__pycache__", "venv", ".venv", "node_modules", ".pytest_cache", ".idea", ".vscode"}
    if any(part in filepath.parts for part in ignored_parts):
        return True
    binary_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz", ".pyc", ".db", ".sqlite", ".sqlite3", ".sock"}
    if filepath.suffix.lower() in binary_suffixes:
        return True
    return False


def _iter_files(project_dir: Path, extensions: List[str] = None, exclude_paths: List[str] = None):
    """Yields readable files matching optional extension and exclusion constraints."""
    exclude_paths = exclude_paths or []
    for root, dirs, files in os.walk(project_dir):
        # Exclude directories in-place for efficiency
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "venv", ".venv", "node_modules", ".pytest_cache"}]
        
        rel_root = os.path.relpath(root, project_dir).replace("\\", "/")
        if any(exc.rstrip("/") in rel_root for exc in exclude_paths):
            continue

        for file in files:
            file_path = Path(root) / file
            if is_binary_or_ignored(file_path):
                continue

            rel_file = file_path.relative_to(project_dir).as_posix()
            if any(exc in rel_file for exc in exclude_paths):
                continue

            if extensions:
                ext_matches = any(
                    file_path.name.lower().endswith(ext.lower()) or file_path.suffix.lower() == ext.lower()
                    for ext in extensions
                )
                if not ext_matches:
                    continue

            yield file_path, rel_file


def evaluate_rule(rule: Dict[str, Any], project_dir: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Evaluates a single rule against target project directory.
    Returns:
        (passed: bool, findings: List[Dict[str, Any]])
    """
    proj_path = Path(project_dir)
    if not proj_path.exists() or not proj_path.is_dir():
        return False, [{
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
            "category": rule.get("category"),
            "severity": rule.get("severity"),
            "description": f"Target project directory does not exist: {project_dir}",
            "file_path": "",
            "line_number": 0,
            "snippet": "",
            "suggestion": "Provide a valid, accessible project directory."
        }]

    check_type = rule.get("check_type", "custom")

    if check_type == "file_exists":
        return _check_file_exists(rule, proj_path)
    elif check_type == "forbidden_regex":
        return _check_forbidden_regex(rule, proj_path)
    elif check_type == "pattern_presence":
        return _check_pattern_presence(rule, proj_path)
    elif check_type == "file_content_contains":
        return _check_file_content_contains(rule, proj_path)
    elif check_type == "negative_pattern":
        return _check_negative_pattern(rule, proj_path)
    else:
        return True, []


def _check_file_exists(rule: Dict[str, Any], proj_path: Path) -> Tuple[bool, List[Dict[str, Any]]]:
    """Passes if at least one of target_files exists in proj_path."""
    targets = rule.get("target_files", [])
    found = False
    for t in targets:
        target_path = proj_path / t
        if target_path.exists():
            found = True
            break
        # Also check recursively for tests folder or files
        if t.endswith("/"):
            dirname = t.rstrip("/")
            if any(d.name == dirname for d in proj_path.rglob(dirname) if d.is_dir() and not is_binary_or_ignored(d)):
                found = True
                break
        elif any(f.name == t for f in proj_path.rglob(t) if not is_binary_or_ignored(f)):
            found = True
            break

    if found:
        return True, []

    return False, [{
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "category": rule.get("category"),
        "severity": rule.get("severity"),
        "description": f"Missing required file(s): {', '.join(targets)}",
        "file_path": targets[0] if targets else "",
        "line_number": 0,
        "snippet": "",
        "suggestion": rule.get("suggestion", "")
    }]


def _check_forbidden_regex(rule: Dict[str, Any], proj_path: Path) -> Tuple[bool, List[Dict[str, Any]]]:
    """Fails if any forbidden regex patterns match in target files."""
    patterns = [re.compile(p, re.MULTILINE) for p in rule.get("patterns", [])]
    extensions = rule.get("file_extensions")
    exclude_paths = rule.get("exclude_paths", [])

    findings = []
    for file_path, rel_path in _iter_files(proj_path, extensions, exclude_paths):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, start=1):
                    for pat in patterns:
                        if pat.search(line):
                            findings.append({
                                "rule_id": rule.get("id"),
                                "rule_name": rule.get("name"),
                                "category": rule.get("category"),
                                "severity": rule.get("severity"),
                                "description": f"Forbidden pattern detected: {rule.get('description')}",
                                "file_path": rel_path,
                                "line_number": line_num,
                                "snippet": line.strip()[:160],
                                "suggestion": rule.get("suggestion", "")
                            })
                            if len(findings) >= 10:  # Cap findings per rule to prevent flooding
                                return False, findings
        except Exception:
            continue

    passed = len(findings) == 0
    return passed, findings


def _check_pattern_presence(rule: Dict[str, Any], proj_path: Path) -> Tuple[bool, List[Dict[str, Any]]]:
    """Passes if at least one of the patterns is found in project files."""
    patterns = [re.compile(p) for p in rule.get("patterns", [])]
    extensions = rule.get("file_extensions")
    exclude_paths = rule.get("exclude_paths", [])

    for file_path, rel_path in _iter_files(proj_path, extensions, exclude_paths):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for pat in patterns:
                    if pat.search(content):
                        return True, []
        except Exception:
            continue

    return False, [{
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "category": rule.get("category"),
        "severity": rule.get("severity"),
        "description": f"Missing expected pattern: {rule.get('description')}",
        "file_path": "",
        "line_number": 0,
        "snippet": "",
        "suggestion": rule.get("suggestion", "")
    }]


def _check_file_content_contains(rule: Dict[str, Any], proj_path: Path) -> Tuple[bool, List[Dict[str, Any]]]:
    """Checks that a target file exists and contains all required patterns."""
    target_file = rule.get("target_file")
    required_patterns = [re.compile(p) for p in rule.get("required_patterns", [])]

    # Search for target file
    candidate = proj_path / target_file
    if not candidate.exists():
        # Check recursively in root or immediate children
        found_files = list(proj_path.glob(f"**/{target_file}"))
        if not found_files:
            return False, [{
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name"),
                "category": rule.get("category"),
                "severity": rule.get("severity"),
                "description": f"Target file '{target_file}' was not found in the project.",
                "file_path": target_file,
                "line_number": 0,
                "snippet": "",
                "suggestion": rule.get("suggestion", "")
            }]
        candidate = found_files[0]

    try:
        with open(candidate, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        missing = []
        for pat in required_patterns:
            if not pat.search(content):
                missing.append(pat.pattern)

        if missing:
            return False, [{
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name"),
                "category": rule.get("category"),
                "severity": rule.get("severity"),
                "description": f"File '{target_file}' is missing required entries: {', '.join(missing)}",
                "file_path": str(candidate.relative_to(proj_path).as_posix()),
                "line_number": 0,
                "snippet": "",
                "suggestion": rule.get("suggestion", "")
            }]

        return True, []
    except Exception as e:
        return False, [{
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
            "category": rule.get("category"),
            "severity": rule.get("severity"),
            "description": f"Error reading '{target_file}': {str(e)}",
            "file_path": target_file,
            "line_number": 0,
            "snippet": "",
            "suggestion": rule.get("suggestion", "")
        }]


def _check_negative_pattern(rule: Dict[str, Any], proj_path: Path) -> Tuple[bool, List[Dict[str, Any]]]:
    """Finds pattern matches that lack a required keyword/parameter."""
    patterns = [re.compile(p) for p in rule.get("patterns", [])]
    forbidden_unless = re.compile(rule.get("forbidden_unless", ""))
    extensions = rule.get("file_extensions")
    exclude_paths = rule.get("exclude_paths", [])

    findings = []
    for file_path, rel_path in _iter_files(proj_path, extensions, exclude_paths):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, start=1):
                    for pat in patterns:
                        if pat.search(line):
                            if not forbidden_unless.search(line):
                                findings.append({
                                    "rule_id": rule.get("id"),
                                    "rule_name": rule.get("name"),
                                    "category": rule.get("category"),
                                    "severity": rule.get("severity"),
                                    "description": f"Invocation without mandatory safety parameter: {rule.get('description')}",
                                    "file_path": rel_path,
                                    "line_number": line_num,
                                    "snippet": line.strip()[:160],
                                    "suggestion": rule.get("suggestion", "")
                                })
        except Exception:
            continue

    passed = len(findings) == 0
    return passed, findings
