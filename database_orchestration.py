"""
Advanced Agent Orchestration Module
====================================
Enables parallel execution, custom workflows, conditional routing, and agent collaboration.

Features:
- Parallel agent execution
- Custom workflow definitions
- Conditional routing based on complexity/type
- Agent specialization settings
- Collaboration protocols
- Workflow templates
"""

import sqlite3
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from enum import Enum

# Use same database as core system
DB_PATH = Path(__file__).parent / "agent_skills.db"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RoutingStrategy(str, Enum):
    """Task routing strategies."""
    COMPLEXITY_BASED = "complexity_based"  # Route based on task complexity
    SKILL_BASED = "skill_based"  # Route to agent with best skill match
    LOAD_BALANCED = "load_balanced"  # Distribute evenly across agents
    PRIORITY_BASED = "priority_based"  # Route based on priority
    CUSTOM = "custom"  # User-defined routing logic


def init_orchestration_db():
    """Initialize orchestration tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1: Workflow Definitions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            workflow_type TEXT CHECK (workflow_type IN ('sequential', 'parallel', 'conditional', 'hybrid')),
            config JSON NOT NULL,
            is_template BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Table 2: Workflow Steps
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            task_description TEXT,
            depends_on_step INTEGER,
            timeout_seconds INTEGER DEFAULT 300,
            retry_count INTEGER DEFAULT 0,
            parallel_group INTEGER DEFAULT 0,
            condition_expression TEXT,
            config JSON,
            FOREIGN KEY (workflow_id) REFERENCES workflow_definitions (id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on_step) REFERENCES workflow_steps (id),
            UNIQUE(workflow_id, step_number)
        )
    """)

    # Table 3: Workflow Executions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
            input_data JSON,
            output_data JSON,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (workflow_id) REFERENCES workflow_definitions (id)
        )
    """)

    # Table 4: Step Executions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS step_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            step_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
            input_data JSON,
            output_data JSON,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            retry_attempt INTEGER DEFAULT 0,
            FOREIGN KEY (execution_id) REFERENCES workflow_executions (id) ON DELETE CASCADE,
            FOREIGN KEY (step_id) REFERENCES workflow_steps (id)
        )
    """)

    # Table 5: Routing Rules
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routing_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            strategy TEXT NOT NULL CHECK (strategy IN ('complexity_based', 'skill_based', 'load_balanced', 'priority_based', 'custom')),
            priority INTEGER DEFAULT 0,
            condition_expression TEXT,
            target_agent TEXT NOT NULL,
            config JSON,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Table 6: Agent Specializations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_specializations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            specialization_area TEXT NOT NULL,
            proficiency_level INTEGER CHECK (proficiency_level >= 1 AND proficiency_level <= 10),
            keywords JSON,
            success_rate REAL DEFAULT 0.0,
            average_duration REAL DEFAULT 0.0,
            task_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(agent_name, specialization_area)
        )
    """)

    # Table 7: Agent Collaboration Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collaboration_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            participating_agents JSON NOT NULL,
            collaboration_type TEXT CHECK (collaboration_type IN ('sequential', 'parallel', 'round_robin', 'consensus')),
            status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'failed')),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            message_count INTEGER DEFAULT 0,
            result JSON
        )
    """)

    # Table 8: Collaboration Messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collaboration_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collaboration_id INTEGER NOT NULL,
            from_agent TEXT NOT NULL,
            to_agent TEXT,
            message_type TEXT CHECK (message_type IN ('request', 'response', 'broadcast', 'handoff')),
            content TEXT NOT NULL,
            metadata JSON,
            created_at TEXT NOT NULL,
            FOREIGN KEY (collaboration_id) REFERENCES collaboration_sessions (id) ON DELETE CASCADE
        )
    """)

    # Table 9: Workflow Templates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            category TEXT,
            use_case TEXT,
            template_config JSON NOT NULL,
            estimated_duration TEXT,
            complexity_level TEXT CHECK (complexity_level IN ('simple', 'medium', 'complex')),
            popularity_score INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_executions_session ON workflow_executions(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_executions_execution ON step_executions(execution_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_routing_rules_priority ON routing_rules(priority DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_spec_agent ON agent_specializations(agent_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_collab_session_id ON collaboration_sessions(session_id)")

    conn.commit()

    # Initialize default data
    initialize_default_specializations(cursor)
    initialize_workflow_templates(cursor)
    initialize_routing_rules(cursor)

    conn.commit()
    conn.close()


def initialize_default_specializations(cursor):
    """Initialize default agent specializations."""
    specializations = [
        # Planner specializations
        ("Planner", "Architecture Design", 9, ["architecture", "design", "planning", "system", "structure"]),
        ("Planner", "Requirements Analysis", 8, ["requirements", "analysis", "specification", "scope"]),
        ("Planner", "Task Breakdown", 9, ["breakdown", "decomposition", "subtasks", "planning"]),

        # Coder specializations
        ("Coder", "Algorithm Implementation", 9, ["algorithm", "implementation", "coding", "logic"]),
        ("Coder", "API Development", 8, ["api", "endpoint", "rest", "graphql", "backend"]),
        ("Coder", "Frontend Development", 7, ["ui", "frontend", "react", "vue", "html", "css"]),

        # FileHandler specializations
        ("FileHandler", "File I/O Operations", 10, ["file", "read", "write", "io", "filesystem"]),
        ("FileHandler", "Data Parsing", 8, ["parse", "json", "xml", "csv", "data"]),
        ("FileHandler", "File Organization", 7, ["organize", "structure", "directory", "manage"]),

        # Reviewer specializations
        ("Reviewer", "Code Review", 9, ["review", "quality", "standards", "best practices"]),
        ("Reviewer", "Security Audit", 8, ["security", "vulnerability", "audit", "safe"]),
        ("Reviewer", "Performance Analysis", 7, ["performance", "optimization", "speed", "efficiency"]),

        # SkillGenerator specializations
        ("SkillGenerator", "Tool Creation", 10, ["tool", "function", "skill", "capability"]),
        ("SkillGenerator", "Code Generation", 9, ["generate", "create", "build", "synthesize"]),
        ("SkillGenerator", "Automation", 8, ["automate", "script", "workflow", "process"]),

        # Executor specializations
        ("Executor", "Code Execution", 10, ["execute", "run", "test", "validate"]),
        ("Executor", "Testing", 9, ["test", "unit test", "integration", "validation"]),
        ("Executor", "Debugging", 7, ["debug", "troubleshoot", "fix", "error"]),
    ]

    now = datetime.now().isoformat()

    for agent_name, area, proficiency, keywords in specializations:
        cursor.execute("""
            INSERT OR IGNORE INTO agent_specializations
            (agent_name, specialization_area, proficiency_level, keywords, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (agent_name, area, proficiency, json.dumps(keywords), now, now))


def initialize_workflow_templates(cursor):
    """Initialize default workflow templates."""
    templates = [
        {
            "name": "Simple Code Review",
            "description": "Sequential workflow: Coder writes code, Reviewer reviews it",
            "category": "Development",
            "use_case": "Quick code changes with review",
            "complexity": "simple",
            "duration": "2-5 minutes",
            "config": {
                "type": "sequential",
                "steps": [
                    {"agent": "Coder", "task": "Write code based on requirements"},
                    {"agent": "Reviewer", "task": "Review code for quality and security"}
                ]
            }
        },
        {
            "name": "Parallel Research",
            "description": "Multiple agents research different aspects simultaneously",
            "category": "Research",
            "use_case": "Comprehensive topic research",
            "complexity": "medium",
            "duration": "5-10 minutes",
            "config": {
                "type": "parallel",
                "steps": [
                    {"agent": "Planner", "task": "Research technical approach", "parallel_group": 1},
                    {"agent": "Coder", "task": "Research implementation patterns", "parallel_group": 1},
                    {"agent": "Reviewer", "task": "Research best practices", "parallel_group": 1}
                ]
            }
        },
        {
            "name": "Full Development Cycle",
            "description": "Complete development workflow with planning, coding, review, and testing",
            "category": "Development",
            "use_case": "New feature development",
            "complexity": "complex",
            "duration": "10-20 minutes",
            "config": {
                "type": "sequential",
                "steps": [
                    {"agent": "Planner", "task": "Create implementation plan"},
                    {"agent": "Coder", "task": "Implement feature"},
                    {"agent": "Reviewer", "task": "Review implementation"},
                    {"agent": "Executor", "task": "Run tests and validate"}
                ]
            }
        },
        {
            "name": "Skill Generation Pipeline",
            "description": "Generate, test, and publish a new skill",
            "category": "Skill Development",
            "use_case": "Creating new marketplace skills",
            "complexity": "medium",
            "duration": "5-10 minutes",
            "config": {
                "type": "sequential",
                "steps": [
                    {"agent": "Planner", "task": "Define skill requirements"},
                    {"agent": "SkillGenerator", "task": "Generate skill code"},
                    {"agent": "Executor", "task": "Test skill functionality"},
                    {"agent": "Reviewer", "task": "Review and certify skill"}
                ]
            }
        }
    ]

    now = datetime.now().isoformat()

    for template in templates:
        cursor.execute("""
            INSERT OR IGNORE INTO workflow_templates
            (name, description, category, use_case, template_config,
             estimated_duration, complexity_level, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            template["name"],
            template["description"],
            template["category"],
            template["use_case"],
            json.dumps(template["config"]),
            template["duration"],
            template["complexity"],
            now
        ))


def initialize_routing_rules(cursor):
    """Initialize default routing rules."""
    rules = [
        {
            "name": "Simple Tasks to Coder",
            "description": "Route simple implementation tasks directly to Coder",
            "strategy": "complexity_based",
            "priority": 5,
            "condition": "complexity < 3",
            "target": "Coder",
            "config": {"max_lines": 50, "max_functions": 3}
        },
        {
            "name": "Complex Tasks to Planner First",
            "description": "Route complex tasks to Planner for breakdown",
            "strategy": "complexity_based",
            "priority": 10,
            "condition": "complexity >= 7",
            "target": "Planner",
            "config": {"requires_planning": True}
        },
        {
            "name": "File Operations to FileHandler",
            "description": "Route file-related tasks to FileHandler",
            "strategy": "skill_based",
            "priority": 8,
            "condition": "keywords IN ['file', 'read', 'write', 'io']",
            "target": "FileHandler",
            "config": {"file_operations": True}
        },
        {
            "name": "Testing to Executor",
            "description": "Route testing tasks to Executor",
            "strategy": "skill_based",
            "priority": 9,
            "condition": "keywords IN ['test', 'execute', 'run', 'validate']",
            "target": "Executor",
            "config": {"testing": True}
        }
    ]

    now = datetime.now().isoformat()

    for rule in rules:
        cursor.execute("""
            INSERT OR IGNORE INTO routing_rules
            (name, description, strategy, priority, condition_expression,
             target_agent, config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule["name"],
            rule["description"],
            rule["strategy"],
            rule["priority"],
            rule["condition"],
            rule["target"],
            json.dumps(rule["config"]),
            now,
            now
        ))


# ============================================================================
# Workflow Management Functions
# ============================================================================

def create_workflow(name: str, description: str, workflow_type: str,
                   config: Dict, created_by: str = "system") -> int:
    """Create a new workflow definition."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO workflow_definitions
        (name, description, workflow_type, config, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, description, workflow_type, json.dumps(config), created_by, now, now))

    workflow_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return workflow_id


def add_workflow_step(workflow_id: int, step_number: int, agent_name: str,
                     task_description: str = None, depends_on_step: int = None,
                     parallel_group: int = 0, condition: str = None,
                     config: Dict = None) -> int:
    """Add a step to a workflow."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO workflow_steps
        (workflow_id, step_number, agent_name, task_description, depends_on_step,
         parallel_group, condition_expression, config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (workflow_id, step_number, agent_name, task_description, depends_on_step,
          parallel_group, condition, json.dumps(config) if config else None))

    step_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return step_id


def get_workflow(workflow_id: int) -> Optional[Dict]:
    """Get workflow definition with steps."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM workflow_definitions WHERE id = ?", (workflow_id,))
    workflow_row = cursor.fetchone()

    if not workflow_row:
        conn.close()
        return None

    workflow = dict(workflow_row)
    workflow['config'] = json.loads(workflow['config'])

    # Get steps
    cursor.execute("""
        SELECT * FROM workflow_steps
        WHERE workflow_id = ?
        ORDER BY step_number
    """, (workflow_id,))

    steps = []
    for row in cursor.fetchall():
        step = dict(row)
        if step['config']:
            step['config'] = json.loads(step['config'])
        steps.append(step)

    workflow['steps'] = steps
    conn.close()

    return workflow


def list_workflows(active_only: bool = True) -> List[Dict]:
    """List all workflow definitions."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM workflow_definitions"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY created_at DESC"

    cursor.execute(query)
    workflows = [dict(row) for row in cursor.fetchall()]

    for workflow in workflows:
        workflow['config'] = json.loads(workflow['config'])

    conn.close()
    return workflows


def start_workflow_execution(workflow_id: int, session_id: str,
                             input_data: Dict = None) -> int:
    """Start a new workflow execution."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO workflow_executions
        (workflow_id, session_id, status, input_data, started_at, created_at)
        VALUES (?, ?, 'running', ?, ?, ?)
    """, (workflow_id, session_id, json.dumps(input_data) if input_data else None, now, now))

    execution_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return execution_id


def update_workflow_execution(execution_id: int, status: str,
                              output_data: Dict = None, error: str = None):
    """Update workflow execution status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Calculate duration
    cursor.execute("""
        SELECT started_at FROM workflow_executions WHERE id = ?
    """, (execution_id,))

    row = cursor.fetchone()
    if row:
        started = datetime.fromisoformat(row[0])
        duration = (datetime.now() - started).total_seconds()
    else:
        duration = None

    cursor.execute("""
        UPDATE workflow_executions
        SET status = ?, output_data = ?, error_message = ?,
            completed_at = ?, duration_seconds = ?
        WHERE id = ?
    """, (status, json.dumps(output_data) if output_data else None,
          error, now if status in ['completed', 'failed', 'cancelled'] else None,
          duration, execution_id))

    conn.commit()
    conn.close()


# ============================================================================
# Routing Functions
# ============================================================================

def get_best_agent_for_task(task: str, keywords: List[str] = None) -> str:
    """Route task to best agent based on specializations and routing rules."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check routing rules first (by priority)
    cursor.execute("""
        SELECT * FROM routing_rules
        WHERE is_active = 1
        ORDER BY priority DESC
    """)

    for rule in cursor.fetchall():
        # Simplified condition matching (in production, use proper expression evaluator)
        if keywords and rule['strategy'] == 'skill_based':
            config = json.loads(rule['config']) if rule['config'] else {}
            # Simple keyword matching
            if any(kw in task.lower() for kw in keywords):
                conn.close()
                return rule['target_agent']

    # Fall back to specialization matching
    if keywords:
        cursor.execute("""
            SELECT agent_name, MAX(proficiency_level) as max_prof
            FROM agent_specializations
            WHERE is_active = 1
            GROUP BY agent_name
            ORDER BY max_prof DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        if row:
            conn.close()
            return row['agent_name']

    conn.close()
    return "Planner"  # Default fallback


def get_agent_specializations(agent_name: str) -> List[Dict]:
    """Get all specializations for an agent."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM agent_specializations
        WHERE agent_name = ? AND is_active = 1
        ORDER BY proficiency_level DESC
    """, (agent_name,))

    specializations = []
    for row in cursor.fetchall():
        spec = dict(row)
        spec['keywords'] = json.loads(spec['keywords'])
        specializations.append(spec)

    conn.close()
    return specializations


def update_agent_performance(agent_name: str, specialization_area: str,
                            success: bool, duration: float):
    """Update agent performance metrics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE agent_specializations
        SET success_rate = (success_rate * task_count + ?) / (task_count + 1),
            average_duration = (average_duration * task_count + ?) / (task_count + 1),
            task_count = task_count + 1,
            updated_at = ?
        WHERE agent_name = ? AND specialization_area = ?
    """, (1.0 if success else 0.0, duration, now, agent_name, specialization_area))

    conn.commit()
    conn.close()


# ============================================================================
# Template Functions
# ============================================================================

def list_workflow_templates(category: str = None) -> List[Dict]:
    """List workflow templates."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM workflow_templates"
    params = []

    if category:
        query += " WHERE category = ?"
        params.append(category)

    query += " ORDER BY popularity_score DESC, created_at DESC"

    cursor.execute(query, params)

    templates = []
    for row in cursor.fetchall():
        template = dict(row)
        template['template_config'] = json.loads(template['template_config'])
        templates.append(template)

    conn.close()
    return templates


def create_workflow_from_template(template_id: int, name: str,
                                  session_id: str) -> int:
    """Create and start a workflow from a template."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get template
    cursor.execute("SELECT * FROM workflow_templates WHERE id = ?", (template_id,))
    template_row = cursor.fetchone()

    if not template_row:
        conn.close()
        raise ValueError(f"Template {template_id} not found")

    template = dict(template_row)
    config = json.loads(template['template_config'])

    # Create workflow
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO workflow_definitions
        (name, description, workflow_type, config, is_template, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, 'template', ?, ?)
    """, (name, template['description'], config['type'], json.dumps(config), now, now))

    workflow_id = cursor.lastrowid

    # Create steps
    for idx, step in enumerate(config.get('steps', []), 1):
        cursor.execute("""
            INSERT INTO workflow_steps
            (workflow_id, step_number, agent_name, task_description, parallel_group)
            VALUES (?, ?, ?, ?, ?)
        """, (workflow_id, idx, step['agent'], step['task'], step.get('parallel_group', 0)))

    # Update template popularity
    cursor.execute("""
        UPDATE workflow_templates
        SET popularity_score = popularity_score + 1
        WHERE id = ?
    """, (template_id,))

    conn.commit()
    conn.close()

    return workflow_id


if __name__ == "__main__":
    init_orchestration_db()
    print("✅ Advanced orchestration database initialized!")
    print("   🔄 Workflow management enabled")
    print("   🎯 Smart routing configured")
    print("   🤝 Agent collaboration ready")
    print("   📋 Workflow templates created")
