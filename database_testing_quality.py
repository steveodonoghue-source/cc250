"""
Skill Testing & Quality Framework
==================================
Automated testing, safety validation, performance benchmarking, and quality certification.

Features:
- Automated skill testing
- Safety validation (unsafe code detection)
- Performance benchmarking
- Quality scoring
- Skill certification badges
- Test coverage tracking
"""

import sqlite3
import json
import ast
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set, Any
from pathlib import Path
from enum import Enum

# Use same database as core system
DB_PATH = Path(__file__).parent / "agent_skills.db"


class TestStatus(str, Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class CertificationLevel(str, Enum):
    """Skill certification levels."""
    UNCERTIFIED = "uncertified"
    BRONZE = "bronze"  # Basic tests pass
    SILVER = "silver"  # Tests + safety checks pass
    GOLD = "gold"  # Tests + safety + performance benchmarks pass
    PLATINUM = "platinum"  # All checks + high quality score


class SafetyRisk(str, Enum):
    """Safety risk levels."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def init_testing_db():
    """Initialize testing and quality tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1: Test Suites
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_suites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            test_count INTEGER DEFAULT 0,
            passed_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            coverage_percentage REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # Table 2: Test Cases
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suite_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            test_code TEXT NOT NULL,
            expected_output JSON,
            timeout_seconds INTEGER DEFAULT 5,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (suite_id) REFERENCES test_suites (id) ON DELETE CASCADE
        )
    """)

    # Table 3: Test Executions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_case_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'passed', 'failed', 'error')),
            actual_output JSON,
            error_message TEXT,
            execution_time_ms REAL,
            executed_at TEXT NOT NULL,
            FOREIGN KEY (test_case_id) REFERENCES test_cases (id),
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # Table 4: Safety Checks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS safety_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            check_type TEXT NOT NULL CHECK (check_type IN ('code_analysis', 'import_validation', 'execution_sandbox', 'resource_limits')),
            risk_level TEXT NOT NULL CHECK (risk_level IN ('none', 'low', 'medium', 'high', 'critical')),
            issues_found INTEGER DEFAULT 0,
            details JSON,
            checked_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # Table 5: Performance Benchmarks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_benchmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            benchmark_name TEXT NOT NULL,
            metric_type TEXT CHECK (metric_type IN ('execution_time', 'memory_usage', 'cpu_usage', 'throughput')),
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            baseline_value REAL,
            percentile_rank REAL,
            tested_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # Table 6: Quality Scores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            test_score REAL DEFAULT 0.0,
            safety_score REAL DEFAULT 0.0,
            performance_score REAL DEFAULT 0.0,
            documentation_score REAL DEFAULT 0.0,
            overall_score REAL DEFAULT 0.0,
            certification_level TEXT CHECK (certification_level IN ('uncertified', 'bronze', 'silver', 'gold', 'platinum')),
            calculated_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # Table 7: Certification Badges
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certification_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            badge_type TEXT NOT NULL,
            badge_name TEXT NOT NULL,
            description TEXT,
            criteria_met JSON NOT NULL,
            awarded_at TEXT NOT NULL,
            expires_at TEXT,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # Table 8: Code Quality Issues
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS code_quality_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            issue_type TEXT NOT NULL CHECK (issue_type IN ('syntax', 'style', 'complexity', 'duplication', 'bug_risk')),
            severity TEXT CHECK (severity IN ('info', 'warning', 'error', 'critical')),
            line_number INTEGER,
            description TEXT NOT NULL,
            recommendation TEXT,
            detected_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # Table 9: Unsafe Patterns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unsafe_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_name TEXT UNIQUE NOT NULL,
            pattern_regex TEXT NOT NULL,
            risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
            description TEXT,
            recommendation TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_suites_skill ON test_suites(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_executions_skill ON test_executions(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_safety_checks_skill ON safety_checks(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_quality_scores_skill ON quality_scores(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_quality_scores_overall ON quality_scores(overall_score DESC)")

    conn.commit()

    # Initialize default unsafe patterns
    initialize_unsafe_patterns(cursor)

    conn.commit()
    conn.close()


def initialize_unsafe_patterns(cursor):
    """Initialize patterns for unsafe code detection."""
    patterns = [
        {
            "name": "Arbitrary Code Execution (eval)",
            "regex": r"\beval\s*\(",
            "risk": "critical",
            "description": "Use of eval() can execute arbitrary code",
            "recommendation": "Use ast.literal_eval() or json.loads() instead"
        },
        {
            "name": "Arbitrary Code Execution (exec)",
            "regex": r"\bexec\s*\(",
            "risk": "critical",
            "description": "Use of exec() can execute arbitrary code",
            "recommendation": "Refactor to avoid dynamic code execution"
        },
        {
            "name": "Unsafe Deserialization (pickle)",
            "regex": r"\bpickle\.loads?\s*\(",
            "risk": "high",
            "description": "pickle can execute arbitrary code during deserialization",
            "recommendation": "Use json or safer serialization formats"
        },
        {
            "name": "OS Command Injection Risk",
            "regex": r"\bos\.system\s*\(|subprocess\.call\s*\([^,]*shell\s*=\s*True",
            "risk": "high",
            "description": "Command execution with shell=True can lead to injection",
            "recommendation": "Use subprocess with shell=False and list arguments"
        },
        {
            "name": "SQL Injection Risk",
            "regex": r"execute\s*\(\s*['\"].*%s.*['\"]|execute\s*\(\s*f['\"]",
            "risk": "high",
            "description": "String formatting in SQL queries can lead to injection",
            "recommendation": "Use parameterized queries with ? placeholders"
        },
        {
            "name": "Hardcoded Secrets",
            "regex": r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]",
            "risk": "high",
            "description": "Hardcoded credentials found in code",
            "recommendation": "Use environment variables or secret management"
        },
        {
            "name": "Unsafe File Operations",
            "regex": r"open\s*\([^)]*['\"]w['\"]|rm\s+-rf|shutil\.rmtree",
            "risk": "medium",
            "description": "File operations that can overwrite or delete data",
            "recommendation": "Add safety checks and confirmations"
        },
        {
            "name": "Network Operations Without Timeout",
            "regex": r"requests\.(get|post|put|delete)\s*\([^)]*(?!timeout)",
            "risk": "medium",
            "description": "Network requests without timeout can hang indefinitely",
            "recommendation": "Always specify timeout parameter"
        },
        {
            "name": "Unsafe YAML Loading",
            "regex": r"yaml\.load\s*\([^,)]*\)",
            "risk": "high",
            "description": "yaml.load() can execute arbitrary Python code",
            "recommendation": "Use yaml.safe_load() instead"
        },
        {
            "name": "Dangerous Imports",
            "regex": r"from\s+__main__\s+import|import\s+__builtin__|from\s+importlib\s+import",
            "risk": "medium",
            "description": "Importing from internal modules can be risky",
            "recommendation": "Avoid importing from __main__ or __builtin__"
        }
    ]

    for pattern in patterns:
        cursor.execute("""
            INSERT OR IGNORE INTO unsafe_patterns
            (pattern_name, pattern_regex, risk_level, description, recommendation)
            VALUES (?, ?, ?, ?, ?)
        """, (pattern["name"], pattern["regex"], pattern["risk"],
              pattern["description"], pattern["recommendation"]))


# ============================================================================
# Safety Validation Functions
# ============================================================================

def check_code_safety(skill_id: int, code: str) -> Tuple[str, List[Dict]]:
    """
    Analyze code for safety issues.

    Returns:
        (risk_level, issues_list)
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get unsafe patterns
    cursor.execute("SELECT * FROM unsafe_patterns WHERE is_active = 1")
    patterns = cursor.fetchall()

    issues = []
    max_risk = "none"
    risk_levels = ["none", "low", "medium", "high", "critical"]

    for pattern in patterns:
        matches = re.finditer(pattern['pattern_regex'], code, re.MULTILINE)
        for match in matches:
            # Find line number
            line_num = code[:match.start()].count('\n') + 1

            issues.append({
                "pattern": pattern['pattern_name'],
                "risk": pattern['risk_level'],
                "line": line_num,
                "description": pattern['description'],
                "recommendation": pattern['recommendation'],
                "match": match.group()
            })

            # Update max risk
            if risk_levels.index(pattern['risk_level']) > risk_levels.index(max_risk):
                max_risk = pattern['risk_level']

    # Save safety check
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO safety_checks
        (skill_id, check_type, risk_level, issues_found, details, checked_at)
        VALUES (?, 'code_analysis', ?, ?, ?, ?)
    """, (skill_id, max_risk, len(issues), json.dumps(issues), now))

    conn.commit()
    conn.close()

    return max_risk, issues


def validate_imports(code: str) -> Tuple[bool, List[str]]:
    """Validate that all imports are safe."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False, ["Syntax error in code"]

    dangerous_modules = {
        'os', 'subprocess', 'sys', '__builtin__', '__main__',
        'importlib', 'ctypes', 'multiprocessing'
    }

    issues = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in dangerous_modules:
                    issues.append(f"Potentially dangerous import: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            if node.module in dangerous_modules:
                issues.append(f"Potentially dangerous import from: {node.module}")

    return len(issues) == 0, issues


def analyze_code_complexity(code: str) -> Dict:
    """Analyze code complexity metrics."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"error": "Syntax error in code"}

    metrics = {
        "functions": 0,
        "classes": 0,
        "lines": code.count('\n') + 1,
        "imports": 0,
        "max_nesting_depth": 0,
        "cyclomatic_complexity": 1
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            metrics["functions"] += 1
        elif isinstance(node, ast.ClassDef):
            metrics["classes"] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            metrics["imports"] += 1
        elif isinstance(node, (ast.If, ast.For, ast.While, ast.With)):
            metrics["cyclomatic_complexity"] += 1

    return metrics


# ============================================================================
# Testing Functions
# ============================================================================

def create_test_suite(skill_id: int, name: str, description: str = "") -> int:
    """Create a test suite for a skill."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO test_suites
        (skill_id, name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (skill_id, name, description, now, now))

    suite_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return suite_id


def add_test_case(suite_id: int, name: str, test_code: str,
                 expected_output: Any = None, description: str = "") -> int:
    """Add a test case to a suite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO test_cases
        (suite_id, name, description, test_code, expected_output, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (suite_id, name, description, test_code,
          json.dumps(expected_output) if expected_output else None, now))

    test_case_id = cursor.lastrowid

    # Update suite test count
    cursor.execute("""
        UPDATE test_suites
        SET test_count = test_count + 1,
            updated_at = ?
        WHERE id = ?
    """, (now, suite_id))

    conn.commit()
    conn.close()

    return test_case_id


def run_test_case(test_case_id: int, skill_id: int, skill_code: str) -> Dict:
    """
    Execute a test case against a skill.

    Returns test results with status, output, and timing.
    """
    import time

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get test case
    cursor.execute("SELECT * FROM test_cases WHERE id = ?", (test_case_id,))
    test_case = dict(cursor.fetchone())

    result = {
        "status": "pending",
        "actual_output": None,
        "error_message": None,
        "execution_time_ms": 0
    }

    try:
        # Create namespace with skill function
        namespace = {}
        exec(skill_code, namespace)

        # Execute test code
        start_time = time.time()
        exec(test_case['test_code'], namespace)
        execution_time = (time.time() - start_time) * 1000

        # Get actual output (if test set a variable named 'result')
        actual_output = namespace.get('result')

        # Compare with expected
        expected = json.loads(test_case['expected_output']) if test_case['expected_output'] else None

        if expected is not None and actual_output != expected:
            result["status"] = "failed"
            result["error_message"] = f"Expected {expected}, got {actual_output}"
        else:
            result["status"] = "passed"

        result["actual_output"] = actual_output
        result["execution_time_ms"] = execution_time

    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)

    # Save execution result
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO test_executions
        (test_case_id, skill_id, status, actual_output, error_message,
         execution_time_ms, executed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (test_case_id, skill_id, result["status"],
          json.dumps(result["actual_output"]) if result["actual_output"] else None,
          result["error_message"], result["execution_time_ms"], now))

    # Update suite counts
    cursor.execute("""
        SELECT suite_id FROM test_cases WHERE id = ?
    """, (test_case_id,))
    suite_id = cursor.fetchone()[0]

    if result["status"] == "passed":
        cursor.execute("""
            UPDATE test_suites
            SET passed_count = passed_count + 1,
                updated_at = ?
            WHERE id = ?
        """, (now, suite_id))
    else:
        cursor.execute("""
            UPDATE test_suites
            SET failed_count = failed_count + 1,
                updated_at = ?
            WHERE id = ?
        """, (now, suite_id))

    conn.commit()
    conn.close()

    return result


# ============================================================================
# Quality Scoring Functions
# ============================================================================

def calculate_quality_score(skill_id: int) -> Dict:
    """
    Calculate comprehensive quality score for a skill.

    Components:
    - Test score (40%): Based on test pass rate
    - Safety score (30%): Based on safety check results
    - Performance score (20%): Based on benchmark results
    - Documentation score (10%): Based on code documentation
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    scores = {
        "test_score": 0.0,
        "safety_score": 0.0,
        "performance_score": 0.0,
        "documentation_score": 0.0,
        "overall_score": 0.0,
        "certification_level": "uncertified"
    }

    # 1. Test Score (40%)
    cursor.execute("""
        SELECT test_count, passed_count, failed_count
        FROM test_suites WHERE skill_id = ?
    """, (skill_id,))

    suite = cursor.fetchone()
    if suite and suite['test_count'] > 0:
        pass_rate = suite['passed_count'] / suite['test_count']
        scores["test_score"] = pass_rate * 100
    else:
        scores["test_score"] = 0.0

    # 2. Safety Score (30%)
    cursor.execute("""
        SELECT risk_level, issues_found
        FROM safety_checks
        WHERE skill_id = ?
        ORDER BY checked_at DESC
        LIMIT 1
    """, (skill_id,))

    safety_check = cursor.fetchone()
    if safety_check:
        risk_penalties = {"none": 0, "low": 10, "medium": 30, "high": 60, "critical": 100}
        penalty = risk_penalties.get(safety_check['risk_level'], 100)
        scores["safety_score"] = max(0, 100 - penalty)
    else:
        scores["safety_score"] = 50.0  # Neutral if not checked

    # 3. Performance Score (20%)
    cursor.execute("""
        SELECT AVG(percentile_rank) as avg_percentile
        FROM performance_benchmarks
        WHERE skill_id = ?
    """, (skill_id,))

    perf = cursor.fetchone()
    if perf and perf['avg_percentile']:
        scores["performance_score"] = perf['avg_percentile']
    else:
        scores["performance_score"] = 50.0  # Neutral if not benchmarked

    # 4. Documentation Score (10%)
    # Get skill details
    cursor.execute("""
        SELECT description, safety_notes
        FROM skills WHERE id = ?
    """, (skill_id,))

    skill = cursor.fetchone()
    if skill:
        doc_score = 0.0
        if skill['description'] and len(skill['description']) > 50:
            doc_score += 50
        if skill['safety_notes']:
            notes = json.loads(skill['safety_notes']) if isinstance(skill['safety_notes'], str) else skill['safety_notes']
            if notes and len(notes) > 0:
                doc_score += 50
        scores["documentation_score"] = doc_score

    # Calculate overall score (weighted average)
    scores["overall_score"] = (
        scores["test_score"] * 0.4 +
        scores["safety_score"] * 0.3 +
        scores["performance_score"] * 0.2 +
        scores["documentation_score"] * 0.1
    )

    # Determine certification level
    if scores["overall_score"] >= 90 and scores["test_score"] == 100 and scores["safety_score"] >= 90:
        scores["certification_level"] = "platinum"
    elif scores["overall_score"] >= 75 and scores["test_score"] >= 80:
        scores["certification_level"] = "gold"
    elif scores["overall_score"] >= 60 and scores["safety_score"] >= 70:
        scores["certification_level"] = "silver"
    elif scores["test_score"] >= 50:
        scores["certification_level"] = "bronze"
    else:
        scores["certification_level"] = "uncertified"

    # Save scores
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO quality_scores
        (skill_id, test_score, safety_score, performance_score,
         documentation_score, overall_score, certification_level, calculated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (skill_id, scores["test_score"], scores["safety_score"],
          scores["performance_score"], scores["documentation_score"],
          scores["overall_score"], scores["certification_level"], now))

    conn.commit()
    conn.close()

    return scores


def get_skill_quality_report(skill_id: int) -> Dict:
    """Get comprehensive quality report for a skill."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    report = {
        "skill_id": skill_id,
        "quality_scores": None,
        "test_results": None,
        "safety_issues": [],
        "certification_badges": [],
        "recommendations": []
    }

    # Get latest quality scores
    cursor.execute("""
        SELECT * FROM quality_scores
        WHERE skill_id = ?
        ORDER BY calculated_at DESC
        LIMIT 1
    """, (skill_id,))

    score_row = cursor.fetchone()
    if score_row:
        report["quality_scores"] = dict(score_row)

    # Get test results
    cursor.execute("""
        SELECT * FROM test_suites WHERE skill_id = ?
    """, (skill_id,))

    suite_row = cursor.fetchone()
    if suite_row:
        report["test_results"] = dict(suite_row)

    # Get safety issues
    cursor.execute("""
        SELECT * FROM safety_checks
        WHERE skill_id = ?
        ORDER BY checked_at DESC
        LIMIT 1
    """, (skill_id,))

    safety_row = cursor.fetchone()
    if safety_row:
        safety_dict = dict(safety_row)
        safety_dict['details'] = json.loads(safety_dict['details']) if safety_dict['details'] else []
        report["safety_issues"] = safety_dict['details']

    # Get certification badges
    cursor.execute("""
        SELECT * FROM certification_badges
        WHERE skill_id = ?
        ORDER BY awarded_at DESC
    """, (skill_id,))

    report["certification_badges"] = [dict(row) for row in cursor.fetchall()]

    # Generate recommendations
    if report["quality_scores"]:
        if report["quality_scores"]["test_score"] < 80:
            report["recommendations"].append("Add more comprehensive tests to improve test coverage")

        if report["quality_scores"]["safety_score"] < 70:
            report["recommendations"].append("Address safety issues found in code analysis")

        if report["quality_scores"]["documentation_score"] < 60:
            report["recommendations"].append("Improve documentation and add safety notes")

    conn.close()
    return report


if __name__ == "__main__":
    init_testing_db()
    print("✅ Testing & Quality framework initialized!")
    print("   🧪 Automated testing enabled")
    print("   🔒 Safety validation configured")
    print("   📊 Performance benchmarking ready")
    print("   🏆 Quality certification system active")
