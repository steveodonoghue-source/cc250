"""
SQLite Database for Conversation Persistence

Stores conversations, skills, baselines, and cost history for the AutoGen Multi-Agent System.
Designed for local/desktop deployment with solo developers in mind.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent / "autogen_data.db"


def get_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0.0,
            is_archived BOOLEAN DEFAULT 0
        )
    """)

    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            agent TEXT,
            timestamp TEXT NOT NULL,
            image_path TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    """)

    # Skills table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            code TEXT NOT NULL,
            parameters TEXT,
            safety_notes TEXT,
            created_at TEXT NOT NULL,
            usage_count INTEGER DEFAULT 0,
            last_used TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    """)

    # Baselines table (for regression testing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            output TEXT NOT NULL,
            agent_config TEXT,
            created_at TEXT NOT NULL,
            coherence_score REAL,
            is_golden BOOLEAN DEFAULT 1
        )
    """)

    # Cost history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            agent_name TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_active ON skills(is_active, usage_count DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_history_conversation ON cost_history(conversation_id)")

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


# ============================================================================
# Conversation Operations
# ============================================================================

def save_conversation(session_id: str, title: str, messages: List[Dict], cost_tracking: Dict) -> int:
    """Save or update a conversation."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Check if conversation exists
        cursor.execute("SELECT id FROM conversations WHERE session_id = ?", (session_id,))
        existing = cursor.fetchone()

        now = datetime.now().isoformat()

        if existing:
            # Update existing
            conversation_id = existing[0]
            cursor.execute("""
                UPDATE conversations
                SET title = ?, updated_at = ?, message_count = ?, total_cost = ?
                WHERE id = ?
            """, (title, now, len(messages), cost_tracking.get('total_cost', 0.0), conversation_id))

            # Delete old messages
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO conversations (session_id, title, created_at, updated_at, message_count, total_cost)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, title, now, now, len(messages), cost_tracking.get('total_cost', 0.0)))
            conversation_id = cursor.lastrowid

        # Insert messages
        for msg in messages:
            cursor.execute("""
                INSERT INTO messages (conversation_id, role, content, agent, timestamp, image_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                conversation_id,
                msg.get('role', 'assistant'),
                msg.get('content', ''),
                msg.get('agent', 'Unknown'),
                msg.get('timestamp', now),
                msg.get('image_path')
            ))

        conn.commit()
        logger.info(f"Saved conversation {session_id} with {len(messages)} messages")
        return conversation_id

    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving conversation: {e}")
        raise
    finally:
        conn.close()


def load_conversation(session_id: str) -> Optional[Dict]:
    """Load a conversation by session ID."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get conversation
        cursor.execute("SELECT * FROM conversations WHERE session_id = ?", (session_id,))
        conv_row = cursor.fetchone()

        if not conv_row:
            return None

        # Get messages
        cursor.execute("""
            SELECT role, content, agent, timestamp, image_path
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
        """, (conv_row['id'],))

        messages = []
        for row in cursor.fetchall():
            msg = {
                'role': row['role'],
                'content': row['content'],
                'agent': row['agent'],
                'timestamp': row['timestamp']
            }
            if row['image_path']:
                msg['image_path'] = row['image_path']
            messages.append(msg)

        return {
            'id': conv_row['id'],
            'session_id': conv_row['session_id'],
            'title': conv_row['title'],
            'created_at': conv_row['created_at'],
            'updated_at': conv_row['updated_at'],
            'message_count': conv_row['message_count'],
            'total_cost': conv_row['total_cost'],
            'messages': messages
        }

    finally:
        conn.close()


def list_conversations(limit: int = 50, archived: bool = False) -> List[Dict]:
    """List recent conversations."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, session_id, title, created_at, updated_at, message_count, total_cost
            FROM conversations
            WHERE is_archived = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """, (1 if archived else 0, limit))

        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                'id': row['id'],
                'session_id': row['session_id'],
                'title': row['title'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'message_count': row['message_count'],
                'total_cost': row['total_cost']
            })

        return conversations

    finally:
        conn.close()


def delete_conversation(session_id: str):
    """Delete a conversation and all its messages."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
        logger.info(f"Deleted conversation {session_id}")
    finally:
        conn.close()


def archive_conversation(session_id: str, archived: bool = True):
    """Archive or unarchive a conversation."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE conversations
            SET is_archived = ?
            WHERE session_id = ?
        """, (1 if archived else 0, session_id))
        conn.commit()
    finally:
        conn.close()


def export_conversation_markdown(session_id: str) -> str:
    """Export conversation as Markdown."""
    conv = load_conversation(session_id)
    if not conv:
        return ""

    md = f"# {conv['title']}\n\n"
    md += f"**Created:** {conv['created_at']}\n"
    md += f"**Messages:** {conv['message_count']}\n"
    md += f"**Cost:** ${conv['total_cost']:.4f}\n\n"
    md += "---\n\n"

    for msg in conv['messages']:
        agent = msg.get('agent', 'Unknown')
        role = msg.get('role', 'assistant')
        timestamp = msg.get('timestamp', '')

        md += f"## {agent} ({role})\n"
        md += f"*{timestamp}*\n\n"
        md += f"{msg['content']}\n\n"
        md += "---\n\n"

    return md


# ============================================================================
# Skill Operations
# ============================================================================

def save_skill(tool_name: str, description: str, code: str, parameters: Dict, safety_notes: List[str]) -> int:
    """Save a generated skill."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO skills (tool_name, description, code, parameters, safety_notes, created_at, usage_count)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT usage_count FROM skills WHERE tool_name = ?), 0))
        """, (
            tool_name,
            description,
            code,
            json.dumps(parameters),
            json.dumps(safety_notes),
            now,
            tool_name
        ))

        conn.commit()
        return cursor.lastrowid

    finally:
        conn.close()


def get_skill(tool_name: str) -> Optional[Dict]:
    """Get a skill by name."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM skills WHERE tool_name = ? AND is_active = 1", (tool_name,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            'id': row['id'],
            'tool_name': row['tool_name'],
            'description': row['description'],
            'code': row['code'],
            'parameters': json.loads(row['parameters']) if row['parameters'] else {},
            'safety_notes': json.loads(row['safety_notes']) if row['safety_notes'] else [],
            'created_at': row['created_at'],
            'usage_count': row['usage_count'],
            'last_used': row['last_used']
        }

    finally:
        conn.close()


def list_skills(active_only: bool = True, limit: int = 100) -> List[Dict]:
    """List all skills."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        query = "SELECT * FROM skills"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY usage_count DESC, created_at DESC LIMIT ?"

        cursor.execute(query, (limit,))

        skills = []
        for row in cursor.fetchall():
            skills.append({
                'id': row['id'],
                'tool_name': row['tool_name'],
                'description': row['description'],
                'code': row['code'],
                'parameters': json.loads(row['parameters']) if row['parameters'] else {},
                'safety_notes': json.loads(row['safety_notes']) if row['safety_notes'] else [],
                'created_at': row['created_at'],
                'usage_count': row['usage_count'],
                'is_active': bool(row['is_active'])
            })

        return skills

    finally:
        conn.close()


def increment_skill_usage(tool_name: str):
    """Increment usage counter for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE skills
            SET usage_count = usage_count + 1, last_used = ?
            WHERE tool_name = ?
        """, (now, tool_name))
        conn.commit()
    finally:
        conn.close()


def delete_skill(tool_name: str):
    """Soft delete a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE skills SET is_active = 0 WHERE tool_name = ?", (tool_name,))
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# Baseline Operations
# ============================================================================

def save_baseline(task: str, output: str, agent_config: Dict, coherence_score: Optional[float] = None):
    """Save a regression testing baseline."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO baselines (task, output, agent_config, created_at, coherence_score)
            VALUES (?, ?, ?, ?, ?)
        """, (task, output, json.dumps(agent_config), now, coherence_score))

        conn.commit()
        return cursor.lastrowid

    finally:
        conn.close()


def get_baseline(task: str) -> Optional[Dict]:
    """Get the most recent golden baseline for a task."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM baselines
            WHERE task = ? AND is_golden = 1
            ORDER BY created_at DESC
            LIMIT 1
        """, (task,))

        row = cursor.fetchone()
        if not row:
            return None

        return {
            'id': row['id'],
            'task': row['task'],
            'output': row['output'],
            'agent_config': json.loads(row['agent_config']) if row['agent_config'] else {},
            'created_at': row['created_at'],
            'coherence_score': row['coherence_score']
        }

    finally:
        conn.close()


# ============================================================================
# Cost Tracking Operations
# ============================================================================

def save_cost_entry(conversation_id: int, agent_name: str, input_tokens: int, output_tokens: int, cost: float):
    """Save a cost tracking entry."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO cost_history (conversation_id, agent_name, input_tokens, output_tokens, cost, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (conversation_id, agent_name, input_tokens, output_tokens, cost, now))

        conn.commit()

    finally:
        conn.close()


def get_cost_summary(days: int = 7) -> Dict:
    """Get cost summary for the last N days."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        from_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        from_date = (from_date - datetime.timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                agent_name,
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                SUM(cost) as total_cost,
                COUNT(*) as call_count
            FROM cost_history
            WHERE timestamp >= ?
            GROUP BY agent_name
            ORDER BY total_cost DESC
        """, (from_date,))

        by_agent = {}
        total_cost = 0
        total_calls = 0

        for row in cursor.fetchall():
            agent = row['agent_name']
            cost = row['total_cost']
            by_agent[agent] = {
                'input_tokens': row['total_input'],
                'output_tokens': row['total_output'],
                'cost': cost,
                'calls': row['call_count']
            }
            total_cost += cost
            total_calls += row['call_count']

        return {
            'total_cost': total_cost,
            'total_calls': total_calls,
            'by_agent': by_agent,
            'days': days
        }

    finally:
        conn.close()


# Initialize database on module import
init_database()
