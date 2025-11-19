"""
Cost Optimization Database Module
===================================
Extends the core database with cost tracking, budget management, and optimization features.

Features:
- Budget tracking and alerts
- Per-agent cost monitoring
- Model selection and pricing
- Token usage analytics
- Cost predictions
- Caching layer
"""

import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Use same database as core system
DB_PATH = Path(__file__).parent / "agent_skills.db"


def init_cost_optimization_db():
    """Initialize cost optimization tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1: Budget Configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budget_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget_type TEXT NOT NULL CHECK (budget_type IN ('daily', 'weekly', 'monthly', 'per_session')),
            budget_limit REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            alert_threshold REAL DEFAULT 0.8,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Table 2: Agent Model Configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_model_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT UNIQUE NOT NULL,
            model_name TEXT NOT NULL,
            max_tokens INTEGER DEFAULT 8192,
            temperature REAL DEFAULT 0.7,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Table 3: Model Pricing
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT UNIQUE NOT NULL,
            input_price_per_million REAL NOT NULL,
            output_price_per_million REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            is_active BOOLEAN DEFAULT 1,
            updated_at TEXT NOT NULL
        )
    """)

    # Table 4: Cost Tracking (per API call)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            agent_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            estimated_cost REAL NOT NULL,
            actual_cost REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (agent_name) REFERENCES agent_model_config (agent_name)
        )
    """)

    # Table 5: Session Budget Tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            budget_limit REAL NOT NULL,
            current_spend REAL DEFAULT 0.0,
            alert_sent BOOLEAN DEFAULT 0,
            budget_exceeded BOOLEAN DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Table 6: Response Cache (to reduce API calls)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS response_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT UNIQUE NOT NULL,
            agent_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            response_text TEXT NOT NULL,
            tokens_saved INTEGER DEFAULT 0,
            hit_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)

    # Table 7: Cost Alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL CHECK (alert_type IN ('threshold', 'budget_exceeded', 'anomaly')),
            session_id TEXT,
            message TEXT NOT NULL,
            current_spend REAL NOT NULL,
            budget_limit REAL,
            acknowledged BOOLEAN DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_tracking_session ON cost_tracking(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_tracking_agent ON cost_tracking(agent_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_tracking_created ON cost_tracking(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_key ON response_cache(cache_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON response_cache(expires_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_budgets_id ON session_budgets(session_id)")

    conn.commit()

    # Initialize default model pricing (Gemini 2.0)
    initialize_default_pricing(cursor)

    # Initialize default agent configurations
    initialize_default_agent_configs(cursor)

    conn.commit()
    conn.close()


def initialize_default_pricing(cursor):
    """Initialize default model pricing for Gemini models."""
    default_pricing = [
        # Gemini 2.0 Flash (fast, cheap)
        ("gemini-2.0-flash-exp", 0.0, 0.0),  # Free during experimental

        # Gemini 2.5 Pro (powerful, more expensive)
        ("gemini-2.5-pro", 0.0, 0.0),  # Free during experimental

        # Future pricing placeholders
        ("gemini-flash-production", 0.075, 0.30),  # Example future pricing
        ("gemini-pro-production", 1.25, 5.00),  # Example future pricing
    ]

    now = datetime.now().isoformat()

    for model_name, input_price, output_price in default_pricing:
        cursor.execute("""
            INSERT OR IGNORE INTO model_pricing
            (model_name, input_price_per_million, output_price_per_million, updated_at)
            VALUES (?, ?, ?, ?)
        """, (model_name, input_price, output_price, now))


def initialize_default_agent_configs(cursor):
    """Initialize default model configurations for each agent."""
    default_configs = [
        # Agent Name, Model, Max Tokens, Temperature
        ("Planner", "gemini-2.5-pro", 8192, 0.7),
        ("Coder", "gemini-2.0-flash-exp", 8192, 0.5),
        ("FileHandler", "gemini-2.0-flash-exp", 4096, 0.3),
        ("Reviewer", "gemini-2.5-pro", 8192, 0.6),
        ("SkillGenerator", "gemini-2.5-pro", 8192, 0.7),
        ("Executor", "gemini-2.0-flash-exp", 4096, 0.5),
    ]

    now = datetime.now().isoformat()

    for agent_name, model_name, max_tokens, temperature in default_configs:
        cursor.execute("""
            INSERT OR IGNORE INTO agent_model_config
            (agent_name, model_name, max_tokens, temperature, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (agent_name, model_name, max_tokens, temperature, now, now))


# ============================================================================
# Budget Management Functions
# ============================================================================

def set_budget(budget_type: str, budget_limit: float, alert_threshold: float = 0.8) -> int:
    """
    Set a budget configuration.

    Args:
        budget_type: 'daily', 'weekly', 'monthly', or 'per_session'
        budget_limit: Maximum budget in USD
        alert_threshold: Threshold (0-1) for sending alerts

    Returns:
        Budget config ID
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Deactivate existing budgets of same type
    cursor.execute("""
        UPDATE budget_config
        SET is_active = 0
        WHERE budget_type = ? AND is_active = 1
    """, (budget_type,))

    # Insert new budget
    cursor.execute("""
        INSERT INTO budget_config
        (budget_type, budget_limit, alert_threshold, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (budget_type, budget_limit, alert_threshold, now, now))

    budget_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return budget_id


def get_active_budget(budget_type: str) -> Optional[Dict]:
    """Get active budget configuration."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM budget_config
        WHERE budget_type = ? AND is_active = 1
        ORDER BY created_at DESC LIMIT 1
    """, (budget_type,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'id': row[0],
            'budget_type': row[1],
            'budget_limit': row[2],
            'currency': row[3],
            'alert_threshold': row[4],
            'is_active': row[5],
            'created_at': row[6],
            'updated_at': row[7]
        }
    return None


# ============================================================================
# Agent Model Configuration
# ============================================================================

def set_agent_model(agent_name: str, model_name: str, max_tokens: int = 8192,
                   temperature: float = 0.7) -> int:
    """
    Configure which model an agent should use.

    Args:
        agent_name: Name of the agent
        model_name: Model to use (e.g., 'gemini-2.0-flash-exp')
        max_tokens: Maximum tokens for this agent
        temperature: Model temperature (0-1)

    Returns:
        Config ID
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO agent_model_config
        (agent_name, model_name, max_tokens, temperature, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (agent_name, model_name, max_tokens, temperature, now, now))

    config_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return config_id


def get_agent_model_config(agent_name: str) -> Optional[Dict]:
    """Get model configuration for an agent."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM agent_model_config
        WHERE agent_name = ? AND is_active = 1
    """, (agent_name,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'id': row[0],
            'agent_name': row[1],
            'model_name': row[2],
            'max_tokens': row[3],
            'temperature': row[4],
            'is_active': row[5],
            'created_at': row[6],
            'updated_at': row[7]
        }
    return None


def list_agent_configs() -> List[Dict]:
    """List all agent model configurations."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM agent_model_config WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()

    return [{
        'id': row[0],
        'agent_name': row[1],
        'model_name': row[2],
        'max_tokens': row[3],
        'temperature': row[4],
        'is_active': row[5],
        'created_at': row[6],
        'updated_at': row[7]
    } for row in rows]


# ============================================================================
# Cost Tracking Functions
# ============================================================================

def track_cost(session_id: str, agent_name: str, model_name: str,
              input_tokens: int, output_tokens: int) -> Tuple[int, float]:
    """
    Track cost for an API call.

    Returns:
        (tracking_id, estimated_cost)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get pricing
    cursor.execute("""
        SELECT input_price_per_million, output_price_per_million
        FROM model_pricing WHERE model_name = ?
    """, (model_name,))

    pricing_row = cursor.fetchone()

    if pricing_row:
        input_price, output_price = pricing_row
        estimated_cost = (
            (input_tokens / 1_000_000 * input_price) +
            (output_tokens / 1_000_000 * output_price)
        )
    else:
        estimated_cost = 0.0  # Free or unknown pricing

    total_tokens = input_tokens + output_tokens
    now = datetime.now().isoformat()

    # Track the cost
    cursor.execute("""
        INSERT INTO cost_tracking
        (session_id, agent_name, model_name, input_tokens, output_tokens,
         total_tokens, estimated_cost, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, agent_name, model_name, input_tokens, output_tokens,
          total_tokens, estimated_cost, now))

    tracking_id = cursor.lastrowid

    # Update session budget
    cursor.execute("""
        INSERT OR IGNORE INTO session_budgets
        (session_id, budget_limit, created_at, updated_at)
        VALUES (?, 1000.0, ?, ?)
    """, (session_id, now, now))

    cursor.execute("""
        UPDATE session_budgets
        SET current_spend = current_spend + ?,
            updated_at = ?
        WHERE session_id = ?
    """, (estimated_cost, now, session_id))

    # Check if budget exceeded
    cursor.execute("""
        SELECT budget_limit, current_spend, alert_sent
        FROM session_budgets WHERE session_id = ?
    """, (session_id,))

    budget_row = cursor.fetchone()
    if budget_row:
        budget_limit, current_spend, alert_sent = budget_row

        # Check threshold
        if current_spend >= budget_limit * 0.8 and not alert_sent:
            create_alert(
                cursor,
                alert_type='threshold',
                session_id=session_id,
                message=f"Warning: 80% of budget reached (${current_spend:.4f} / ${budget_limit:.2f})",
                current_spend=current_spend,
                budget_limit=budget_limit
            )
            cursor.execute("""
                UPDATE session_budgets SET alert_sent = 1 WHERE session_id = ?
            """, (session_id,))

        # Check exceeded
        if current_spend >= budget_limit:
            create_alert(
                cursor,
                alert_type='budget_exceeded',
                session_id=session_id,
                message=f"Budget exceeded! (${current_spend:.4f} / ${budget_limit:.2f})",
                current_spend=current_spend,
                budget_limit=budget_limit
            )
            cursor.execute("""
                UPDATE session_budgets SET budget_exceeded = 1 WHERE session_id = ?
            """, (session_id,))

    conn.commit()
    conn.close()

    return tracking_id, estimated_cost


def get_session_cost_summary(session_id: str) -> Dict:
    """Get cost summary for a session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as call_count,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(total_tokens) as total_tokens,
            SUM(estimated_cost) as total_cost
        FROM cost_tracking
        WHERE session_id = ?
    """, (session_id,))

    row = cursor.fetchone()

    # Get per-agent breakdown
    cursor.execute("""
        SELECT
            agent_name,
            COUNT(*) as calls,
            SUM(total_tokens) as tokens,
            SUM(estimated_cost) as cost
        FROM cost_tracking
        WHERE session_id = ?
        GROUP BY agent_name
        ORDER BY cost DESC
    """, (session_id,))

    agent_breakdown = [{
        'agent_name': r[0],
        'calls': r[1],
        'tokens': r[2],
        'cost': r[3]
    } for r in cursor.fetchall()]

    # Get budget info
    cursor.execute("""
        SELECT budget_limit, current_spend, budget_exceeded
        FROM session_budgets WHERE session_id = ?
    """, (session_id,))

    budget_row = cursor.fetchone()
    budget_info = None
    if budget_row:
        budget_info = {
            'budget_limit': budget_row[0],
            'current_spend': budget_row[1],
            'budget_exceeded': budget_row[2],
            'percentage_used': (budget_row[1] / budget_row[0] * 100) if budget_row[0] > 0 else 0
        }

    conn.close()

    return {
        'session_id': session_id,
        'call_count': row[0] or 0,
        'total_input_tokens': row[1] or 0,
        'total_output_tokens': row[2] or 0,
        'total_tokens': row[3] or 0,
        'total_cost': row[4] or 0.0,
        'agent_breakdown': agent_breakdown,
        'budget_info': budget_info
    }


def get_cost_analytics(days: int = 7) -> Dict:
    """Get cost analytics for the last N days."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    from datetime import timedelta
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    # Total stats
    cursor.execute("""
        SELECT
            COUNT(*) as total_calls,
            SUM(total_tokens) as total_tokens,
            SUM(estimated_cost) as total_cost,
            AVG(estimated_cost) as avg_cost_per_call
        FROM cost_tracking
        WHERE created_at >= ?
    """, (cutoff_date,))

    total_row = cursor.fetchone()

    # Per-agent stats
    cursor.execute("""
        SELECT
            agent_name,
            COUNT(*) as calls,
            SUM(total_tokens) as tokens,
            SUM(estimated_cost) as cost
        FROM cost_tracking
        WHERE created_at >= ?
        GROUP BY agent_name
        ORDER BY cost DESC
    """, (cutoff_date,))

    agent_stats = [{
        'agent_name': r[0],
        'calls': r[1],
        'tokens': r[2],
        'cost': r[3]
    } for r in cursor.fetchall()]

    # Per-model stats
    cursor.execute("""
        SELECT
            model_name,
            COUNT(*) as calls,
            SUM(total_tokens) as tokens,
            SUM(estimated_cost) as cost
        FROM cost_tracking
        WHERE created_at >= ?
        GROUP BY model_name
        ORDER BY cost DESC
    """, (cutoff_date,))

    model_stats = [{
        'model_name': r[0],
        'calls': r[1],
        'tokens': r[2],
        'cost': r[3]
    } for r in cursor.fetchall()]

    conn.close()

    return {
        'period_days': days,
        'total_calls': total_row[0] or 0,
        'total_tokens': total_row[1] or 0,
        'total_cost': total_row[2] or 0.0,
        'avg_cost_per_call': total_row[3] or 0.0,
        'by_agent': agent_stats,
        'by_model': model_stats
    }


# ============================================================================
# Cache Functions
# ============================================================================

def cache_response(cache_key: str, agent_name: str, model_name: str,
                  prompt_hash: str, response_text: str, ttl_hours: int = 24) -> int:
    """Cache a response to reduce API calls."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    from datetime import timedelta
    now = datetime.now()
    expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
    now_iso = now.isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO response_cache
        (cache_key, agent_name, model_name, prompt_hash, response_text,
         tokens_saved, hit_count, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
    """, (cache_key, agent_name, model_name, prompt_hash, response_text,
          now_iso, expires_at))

    cache_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return cache_id


def get_cached_response(cache_key: str) -> Optional[Dict]:
    """Get cached response if available and not expired."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        SELECT * FROM response_cache
        WHERE cache_key = ? AND expires_at > ?
    """, (cache_key, now))

    row = cursor.fetchone()

    if row:
        # Increment hit count
        cursor.execute("""
            UPDATE response_cache
            SET hit_count = hit_count + 1
            WHERE cache_key = ?
        """, (cache_key,))
        conn.commit()

    conn.close()

    if row:
        return {
            'id': row[0],
            'cache_key': row[1],
            'agent_name': row[2],
            'model_name': row[3],
            'prompt_hash': row[4],
            'response_text': row[5],
            'tokens_saved': row[6],
            'hit_count': row[7],
            'created_at': row[8],
            'expires_at': row[9]
        }
    return None


def get_cache_stats() -> Dict:
    """Get cache performance statistics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total_entries,
            SUM(hit_count) as total_hits,
            SUM(tokens_saved) as total_tokens_saved
        FROM response_cache
    """)

    row = cursor.fetchone()
    conn.close()

    return {
        'total_entries': row[0] or 0,
        'total_hits': row[1] or 0,
        'total_tokens_saved': row[2] or 0
    }


# ============================================================================
# Alert Functions
# ============================================================================

def create_alert(cursor, alert_type: str, session_id: str, message: str,
                current_spend: float, budget_limit: Optional[float] = None):
    """Create a cost alert."""
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO cost_alerts
        (alert_type, session_id, message, current_spend, budget_limit, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (alert_type, session_id, message, current_spend, budget_limit, now))


def get_unacknowledged_alerts(session_id: Optional[str] = None) -> List[Dict]:
    """Get unacknowledged alerts."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if session_id:
        cursor.execute("""
            SELECT * FROM cost_alerts
            WHERE session_id = ? AND acknowledged = 0
            ORDER BY created_at DESC
        """, (session_id,))
    else:
        cursor.execute("""
            SELECT * FROM cost_alerts
            WHERE acknowledged = 0
            ORDER BY created_at DESC
        """)

    rows = cursor.fetchall()
    conn.close()

    return [{
        'id': row[0],
        'alert_type': row[1],
        'session_id': row[2],
        'message': row[3],
        'current_spend': row[4],
        'budget_limit': row[5],
        'acknowledged': row[6],
        'created_at': row[7]
    } for row in rows]


def acknowledge_alert(alert_id: int):
    """Mark an alert as acknowledged."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE cost_alerts SET acknowledged = 1 WHERE id = ?
    """, (alert_id,))

    conn.commit()
    conn.close()


# ============================================================================
# Initialization
# ============================================================================

if __name__ == "__main__":
    init_cost_optimization_db()
    print("✅ Cost optimization database initialized!")
    print(f"   📊 Budget tracking enabled")
    print(f"   ⚙️  Agent model configurations set")
    print(f"   💰 Model pricing initialized (Gemini 2.0)")
    print(f"   📈 Cost analytics ready")
