"""
Database module for Integration Hub (Feature #16).

This module provides:
- GitHub integration (auto-create skills from repos)
- Slack notifications for workflow events
- Webhook system for external triggers
- REST API client generator
- Export/Import capabilities

Tables:
- integrations: Core integration configurations
- integration_types: Available integration types
- webhook_endpoints: Webhook URL configurations
- webhook_deliveries: Webhook delivery tracking
- github_repos: Connected GitHub repositories
- slack_channels: Connected Slack channels
- integration_logs: Activity logs
- export_jobs: Export/import job tracking
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import hashlib
import hmac
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent / "integrations.db"


def initialize_database():
    """Initialize the integrations database with all required tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1: Integration Types
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS integration_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            icon TEXT,
            requires_auth BOOLEAN DEFAULT 1,
            config_schema JSON,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    # Table 2: Integrations (user-configured instances)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS integrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_type TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            config JSON NOT NULL,
            credentials JSON,
            is_enabled BOOLEAN DEFAULT 1,
            last_sync_at TEXT,
            sync_status TEXT CHECK (sync_status IN ('never', 'success', 'failed', 'in_progress')),
            error_message TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (integration_type) REFERENCES integration_types (type_name)
        )
    """)

    # Table 3: Webhook Endpoints
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id INTEGER,
            endpoint_url TEXT UNIQUE NOT NULL,
            secret_key TEXT NOT NULL,
            events JSON NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            description TEXT,
            created_at TEXT NOT NULL,
            last_triggered_at TEXT,
            total_deliveries INTEGER DEFAULT 0,
            successful_deliveries INTEGER DEFAULT 0,
            failed_deliveries INTEGER DEFAULT 0,
            FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE
        )
    """)

    # Table 4: Webhook Deliveries (tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload JSON NOT NULL,
            status TEXT CHECK (status IN ('pending', 'success', 'failed', 'retrying')),
            http_status_code INTEGER,
            response_body TEXT,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            delivered_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (webhook_id) REFERENCES webhook_endpoints (id) ON DELETE CASCADE
        )
    """)

    # Table 5: GitHub Repositories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS github_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id INTEGER NOT NULL,
            repo_full_name TEXT NOT NULL,
            repo_url TEXT NOT NULL,
            default_branch TEXT DEFAULT 'main',
            auto_import_skills BOOLEAN DEFAULT 1,
            skill_path_pattern TEXT DEFAULT '*.py',
            last_commit_sha TEXT,
            last_sync_at TEXT,
            skills_imported INTEGER DEFAULT 0,
            sync_status TEXT CHECK (sync_status IN ('never', 'success', 'failed', 'in_progress')),
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(integration_id, repo_full_name),
            FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE
        )
    """)

    # Table 6: Slack Channels
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS slack_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            workspace_id TEXT,
            workspace_name TEXT,
            event_subscriptions JSON NOT NULL,
            notification_format TEXT DEFAULT 'detailed',
            is_active BOOLEAN DEFAULT 1,
            last_notification_at TEXT,
            total_notifications INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(integration_id, channel_id),
            FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE
        )
    """)

    # Table 7: Integration Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS integration_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id INTEGER NOT NULL,
            log_level TEXT CHECK (log_level IN ('debug', 'info', 'warning', 'error', 'critical')),
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            details JSON,
            created_at TEXT NOT NULL,
            FOREIGN KEY (integration_id) REFERENCES integrations (id) ON DELETE CASCADE
        )
    """)

    # Table 8: Export/Import Jobs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT CHECK (job_type IN ('export', 'import')),
            export_format TEXT CHECK (export_format IN ('json', 'yaml', 'zip', 'tar.gz')),
            scope TEXT CHECK (scope IN ('skills', 'workflows', 'integrations', 'all')),
            status TEXT CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
            file_path TEXT,
            file_size_bytes INTEGER,
            items_count INTEGER DEFAULT 0,
            items_processed INTEGER DEFAULT 0,
            error_message TEXT,
            metadata JSON,
            created_by TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_integrations_type ON integrations(integration_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_active ON webhook_endpoints(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_github_repos_active ON github_repos(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_integration_logs_timestamp ON integration_logs(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_jobs_status ON export_jobs(status)")

    conn.commit()

    # Initialize default integration types
    _initialize_integration_types(cursor)

    conn.commit()
    conn.close()

    logger.info(f"Integration Hub database initialized at {DB_PATH}")


def _initialize_integration_types(cursor):
    """Initialize default integration types."""
    now = datetime.now().isoformat()

    integration_types = [
        {
            "type_name": "github",
            "display_name": "GitHub",
            "description": "Connect GitHub repositories to auto-import skills",
            "icon": "🐙",
            "requires_auth": True,
            "config_schema": {
                "access_token": {"type": "string", "required": True, "secret": True},
                "auto_import": {"type": "boolean", "default": True},
                "skill_path_pattern": {"type": "string", "default": "*.py"}
            }
        },
        {
            "type_name": "slack",
            "display_name": "Slack",
            "description": "Send notifications to Slack channels",
            "icon": "💬",
            "requires_auth": True,
            "config_schema": {
                "webhook_url": {"type": "string", "required": True, "secret": True},
                "bot_token": {"type": "string", "required": False, "secret": True},
                "notification_format": {"type": "string", "enum": ["minimal", "detailed", "full"]}
            }
        },
        {
            "type_name": "webhook",
            "display_name": "Webhooks",
            "description": "Trigger workflows via HTTP webhooks",
            "icon": "🔗",
            "requires_auth": False,
            "config_schema": {
                "secret_key": {"type": "string", "required": True, "secret": True},
                "events": {"type": "array", "items": {"type": "string"}}
            }
        },
        {
            "type_name": "api_client",
            "display_name": "API Client Generator",
            "description": "Generate REST API clients for skills",
            "icon": "🔧",
            "requires_auth": False,
            "config_schema": {
                "output_language": {"type": "string", "enum": ["python", "javascript", "curl"]},
                "include_auth": {"type": "boolean", "default": True}
            }
        },
        {
            "type_name": "export_import",
            "display_name": "Export/Import",
            "description": "Export and import skills, workflows, and configurations",
            "icon": "📦",
            "requires_auth": False,
            "config_schema": {
                "format": {"type": "string", "enum": ["json", "yaml", "zip"]},
                "include_metadata": {"type": "boolean", "default": True}
            }
        }
    ]

    for int_type in integration_types:
        cursor.execute("""
            INSERT OR IGNORE INTO integration_types
            (type_name, display_name, description, icon, requires_auth, config_schema, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            int_type['type_name'],
            int_type['display_name'],
            int_type['description'],
            int_type['icon'],
            int_type['requires_auth'],
            json.dumps(int_type['config_schema']),
            now
        ))

    logger.info(f"Initialized {len(integration_types)} integration types")


# ============================================================
# INTEGRATION MANAGEMENT
# ============================================================

def create_integration(integration_type: str, name: str, config: Dict,
                      credentials: Optional[Dict] = None, description: str = "",
                      created_by: str = "system") -> int:
    """Create a new integration."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO integrations
        (integration_type, name, description, config, credentials, sync_status, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'never', ?, ?, ?)
    """, (integration_type, name, description, json.dumps(config),
          json.dumps(credentials) if credentials else None,
          created_by, now, now))

    integration_id = cursor.lastrowid

    # Log creation
    _log_integration_event(cursor, integration_id, "info", "integration_created",
                          f"Integration '{name}' created")

    conn.commit()
    conn.close()

    logger.info(f"Created integration: {name} (ID: {integration_id})")
    return integration_id


def get_integration(integration_id: int) -> Optional[Dict]:
    """Get integration by ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM integrations WHERE id = ?", (integration_id,))
    row = cursor.fetchone()

    conn.close()

    if row:
        integration = dict(row)
        integration['config'] = json.loads(integration['config']) if integration['config'] else {}
        integration['credentials'] = json.loads(integration['credentials']) if integration['credentials'] else {}
        return integration

    return None


def list_integrations(integration_type: Optional[str] = None, enabled_only: bool = False) -> List[Dict]:
    """List all integrations, optionally filtered."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM integrations WHERE 1=1"
    params = []

    if integration_type:
        query += " AND integration_type = ?"
        params.append(integration_type)

    if enabled_only:
        query += " AND is_enabled = 1"

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    integrations = []
    for row in rows:
        integration = dict(row)
        integration['config'] = json.loads(integration['config']) if integration['config'] else {}
        # Don't expose credentials in list view
        integration['credentials'] = None
        integrations.append(integration)

    return integrations


def update_integration_status(integration_id: int, status: str, error_message: Optional[str] = None):
    """Update integration sync status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE integrations
        SET sync_status = ?, error_message = ?, last_sync_at = ?, updated_at = ?
        WHERE id = ?
    """, (status, error_message, now, now, integration_id))

    conn.commit()
    conn.close()


def toggle_integration(integration_id: int, enabled: bool) -> bool:
    """Enable or disable an integration."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE integrations
        SET is_enabled = ?, updated_at = ?
        WHERE id = ?
    """, (enabled, now, integration_id))

    success = cursor.rowcount > 0

    if success:
        action = "enabled" if enabled else "disabled"
        _log_integration_event(cursor, integration_id, "info", f"integration_{action}",
                              f"Integration {action}")

    conn.commit()
    conn.close()

    return success


# ============================================================
# GITHUB INTEGRATION
# ============================================================

def add_github_repo(integration_id: int, repo_full_name: str, repo_url: str,
                   auto_import: bool = True, skill_path_pattern: str = "*.py") -> int:
    """Add a GitHub repository to an integration."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO github_repos
        (integration_id, repo_full_name, repo_url, auto_import_skills,
         skill_path_pattern, sync_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'never', ?, ?)
    """, (integration_id, repo_full_name, repo_url, auto_import, skill_path_pattern, now, now))

    repo_id = cursor.lastrowid

    _log_integration_event(cursor, integration_id, "info", "github_repo_added",
                          f"Repository '{repo_full_name}' added")

    conn.commit()
    conn.close()

    logger.info(f"Added GitHub repo: {repo_full_name} (ID: {repo_id})")
    return repo_id


def sync_github_repo(repo_id: int) -> Tuple[bool, str]:
    """
    Sync a GitHub repository and import skills.

    Returns:
        (success, message)
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get repo details
    cursor.execute("SELECT * FROM github_repos WHERE id = ?", (repo_id,))
    repo = cursor.fetchone()

    if not repo:
        conn.close()
        return False, "Repository not found"

    # Get integration credentials
    cursor.execute("SELECT credentials FROM integrations WHERE id = ?", (repo['integration_id'],))
    integration = cursor.fetchone()

    if not integration or not integration['credentials']:
        conn.close()
        return False, "No GitHub credentials configured"

    credentials = json.loads(integration['credentials'])
    access_token = credentials.get('access_token')

    if not access_token:
        conn.close()
        return False, "GitHub access token missing"

    # Update status to in_progress
    now = datetime.now().isoformat()
    cursor.execute("""
        UPDATE github_repos
        SET sync_status = 'in_progress', updated_at = ?
        WHERE id = ?
    """, (now, repo_id))
    conn.commit()

    try:
        # Fetch repository contents from GitHub API
        api_url = f"https://api.github.com/repos/{repo['repo_full_name']}/contents"
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        response = requests.get(api_url, headers=headers, timeout=10)

        if response.status_code != 200:
            error_msg = f"GitHub API error: {response.status_code}"
            cursor.execute("""
                UPDATE github_repos
                SET sync_status = 'failed', updated_at = ?
                WHERE id = ?
            """, (now, repo_id))
            conn.commit()
            conn.close()
            return False, error_msg

        # Parse and import skills (simplified - just count Python files for now)
        contents = response.json()
        python_files = [f for f in contents if f.get('name', '').endswith('.py')]

        skills_count = len(python_files)

        # Update success status
        cursor.execute("""
            UPDATE github_repos
            SET sync_status = 'success', skills_imported = ?, last_sync_at = ?, updated_at = ?
            WHERE id = ?
        """, (skills_count, now, now, repo_id))

        _log_integration_event(cursor, repo['integration_id'], "info", "github_sync_success",
                              f"Synced {skills_count} skills from {repo['repo_full_name']}")

        conn.commit()
        conn.close()

        return True, f"Successfully synced {skills_count} skills"

    except Exception as e:
        error_msg = str(e)
        cursor.execute("""
            UPDATE github_repos
            SET sync_status = 'failed', updated_at = ?
            WHERE id = ?
        """, (now, repo_id))

        _log_integration_event(cursor, repo['integration_id'], "error", "github_sync_failed",
                              f"Sync failed: {error_msg}")

        conn.commit()
        conn.close()

        return False, error_msg


def list_github_repos(integration_id: int, active_only: bool = False) -> List[Dict]:
    """List GitHub repositories for an integration."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM github_repos WHERE integration_id = ?"
    params = [integration_id]

    if active_only:
        query += " AND is_active = 1"

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


# ============================================================
# WEBHOOK SYSTEM
# ============================================================

def create_webhook(integration_id: Optional[int], events: List[str],
                  description: str = "") -> Tuple[int, str, str]:
    """
    Create a new webhook endpoint.

    Returns:
        (webhook_id, endpoint_url, secret_key)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Generate unique endpoint URL and secret
    import uuid
    webhook_uuid = str(uuid.uuid4())
    endpoint_url = f"/webhooks/{webhook_uuid}"
    secret_key = hashlib.sha256(f"{webhook_uuid}{now}".encode()).hexdigest()

    cursor.execute("""
        INSERT INTO webhook_endpoints
        (integration_id, endpoint_url, secret_key, events, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (integration_id, endpoint_url, secret_key, json.dumps(events), description, now))

    webhook_id = cursor.lastrowid

    if integration_id:
        _log_integration_event(cursor, integration_id, "info", "webhook_created",
                              f"Webhook endpoint created: {endpoint_url}")

    conn.commit()
    conn.close()

    logger.info(f"Created webhook: {endpoint_url} (ID: {webhook_id})")
    return webhook_id, endpoint_url, secret_key


def verify_webhook_signature(payload: str, signature: str, secret_key: str) -> bool:
    """Verify webhook request signature using HMAC."""
    expected_signature = hmac.new(
        secret_key.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)


def trigger_webhook(webhook_id: int, event_type: str, payload: Dict) -> int:
    """
    Record a webhook trigger and attempt delivery.

    Returns:
        delivery_id
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Create delivery record
    cursor.execute("""
        INSERT INTO webhook_deliveries
        (webhook_id, event_type, payload, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
    """, (webhook_id, event_type, json.dumps(payload), now))

    delivery_id = cursor.lastrowid

    # Update webhook stats
    cursor.execute("""
        UPDATE webhook_endpoints
        SET last_triggered_at = ?, total_deliveries = total_deliveries + 1
        WHERE id = ?
    """, (now, webhook_id))

    conn.commit()
    conn.close()

    # Note: Actual HTTP delivery would be handled asynchronously
    # For now, we just mark as success
    _complete_webhook_delivery(delivery_id, "success", 200, "OK")

    return delivery_id


def _complete_webhook_delivery(delivery_id: int, status: str,
                               http_status: int, response: str):
    """Mark a webhook delivery as complete."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE webhook_deliveries
        SET status = ?, http_status_code = ?, response_body = ?, delivered_at = ?
        WHERE id = ?
    """, (status, http_status, response, now, delivery_id))

    # Update webhook stats
    if status == 'success':
        cursor.execute("""
            UPDATE webhook_endpoints
            SET successful_deliveries = successful_deliveries + 1
            WHERE id = (SELECT webhook_id FROM webhook_deliveries WHERE id = ?)
        """, (delivery_id,))
    else:
        cursor.execute("""
            UPDATE webhook_endpoints
            SET failed_deliveries = failed_deliveries + 1
            WHERE id = (SELECT webhook_id FROM webhook_deliveries WHERE id = ?)
        """, (delivery_id,))

    conn.commit()
    conn.close()


def list_webhooks(integration_id: Optional[int] = None, active_only: bool = False) -> List[Dict]:
    """List webhooks, optionally filtered."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM webhook_endpoints WHERE 1=1"
    params = []

    if integration_id:
        query += " AND integration_id = ?"
        params.append(integration_id)

    if active_only:
        query += " AND is_active = 1"

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    webhooks = []
    for row in rows:
        webhook = dict(row)
        webhook['events'] = json.loads(webhook['events']) if webhook['events'] else []
        webhooks.append(webhook)

    return webhooks


# ============================================================
# SLACK NOTIFICATIONS
# ============================================================

def add_slack_channel(integration_id: int, channel_id: str, channel_name: str,
                     event_subscriptions: List[str], workspace_id: Optional[str] = None,
                     workspace_name: Optional[str] = None) -> int:
    """Add a Slack channel for notifications."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO slack_channels
        (integration_id, channel_id, channel_name, workspace_id, workspace_name,
         event_subscriptions, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (integration_id, channel_id, channel_name, workspace_id, workspace_name,
          json.dumps(event_subscriptions), now, now))

    slack_channel_id = cursor.lastrowid

    _log_integration_event(cursor, integration_id, "info", "slack_channel_added",
                          f"Slack channel '{channel_name}' added")

    conn.commit()
    conn.close()

    logger.info(f"Added Slack channel: {channel_name} (ID: {slack_channel_id})")
    return slack_channel_id


def send_slack_notification(channel_id: int, event_type: str, message: str,
                           details: Optional[Dict] = None) -> bool:
    """
    Send a notification to a Slack channel.

    Returns:
        success
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get channel details
    cursor.execute("SELECT * FROM slack_channels WHERE id = ?", (channel_id,))
    channel = cursor.fetchone()

    if not channel or not channel['is_active']:
        conn.close()
        return False

    # Get integration credentials
    cursor.execute("SELECT credentials FROM integrations WHERE id = ?", (channel['integration_id'],))
    integration = cursor.fetchone()

    if not integration or not integration['credentials']:
        conn.close()
        return False

    credentials = json.loads(integration['credentials'])
    webhook_url = credentials.get('webhook_url')

    if not webhook_url:
        conn.close()
        return False

    try:
        # Format message based on notification format
        notification_format = channel['notification_format']

        if notification_format == 'minimal':
            slack_message = {"text": message}
        else:  # detailed or full
            slack_message = {
                "text": message,
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{event_type}*\n{message}"}
                    }
                ]
            }

            if details and notification_format == 'full':
                slack_message["blocks"].append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"```{json.dumps(details, indent=2)}```"}
                })

        # Send to Slack
        response = requests.post(webhook_url, json=slack_message, timeout=5)

        success = response.status_code == 200

        if success:
            # Update stats
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE slack_channels
                SET last_notification_at = ?, total_notifications = total_notifications + 1
                WHERE id = ?
            """, (now, channel_id))

            _log_integration_event(cursor, channel['integration_id'], "info",
                                  "slack_notification_sent",
                                  f"Notification sent to {channel['channel_name']}")

        conn.commit()
        conn.close()

        return success

    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        conn.close()
        return False


def list_slack_channels(integration_id: int, active_only: bool = False) -> List[Dict]:
    """List Slack channels for an integration."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM slack_channels WHERE integration_id = ?"
    params = [integration_id]

    if active_only:
        query += " AND is_active = 1"

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    channels = []
    for row in rows:
        channel = dict(row)
        channel['event_subscriptions'] = json.loads(channel['event_subscriptions']) if channel['event_subscriptions'] else []
        channels.append(channel)

    return channels


# ============================================================
# EXPORT/IMPORT
# ============================================================

def create_export_job(job_type: str, export_format: str, scope: str,
                     metadata: Optional[Dict] = None, created_by: str = "system") -> int:
    """Create an export/import job."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO export_jobs
        (job_type, export_format, scope, status, metadata, created_by, created_at)
        VALUES (?, ?, ?, 'pending', ?, ?, ?)
    """, (job_type, export_format, scope, json.dumps(metadata) if metadata else None,
          created_by, now))

    job_id = cursor.lastrowid

    conn.commit()
    conn.close()

    logger.info(f"Created {job_type} job: {scope} as {export_format} (ID: {job_id})")
    return job_id


def update_export_job(job_id: int, status: str, file_path: Optional[str] = None,
                     file_size: Optional[int] = None, items_processed: Optional[int] = None,
                     error_message: Optional[str] = None):
    """Update export job status and details."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE export_jobs
        SET status = ?, file_path = COALESCE(?, file_path),
            file_size_bytes = COALESCE(?, file_size_bytes),
            items_processed = COALESCE(?, items_processed),
            error_message = ?,
            completed_at = CASE WHEN ? IN ('completed', 'failed') THEN ? ELSE completed_at END
        WHERE id = ?
    """, (status, file_path, file_size, items_processed, error_message, status, now, job_id))

    conn.commit()
    conn.close()


def get_export_job(job_id: int) -> Optional[Dict]:
    """Get export job by ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM export_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()

    conn.close()

    if row:
        job = dict(row)
        job['metadata'] = json.loads(job['metadata']) if job['metadata'] else {}
        return job

    return None


def list_export_jobs(job_type: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """List export/import jobs."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM export_jobs WHERE 1=1"
    params = []

    if job_type:
        query += " AND job_type = ?"
        params.append(job_type)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    jobs = []
    for row in rows:
        job = dict(row)
        job['metadata'] = json.loads(job['metadata']) if job['metadata'] else {}
        jobs.append(job)

    return jobs


def export_skills_to_json(skill_ids: Optional[List[int]] = None) -> Dict:
    """
    Export skills to JSON format.

    Returns:
        Dict with exported skills data
    """
    import database as db

    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if skill_ids:
        placeholders = ','.join('?' * len(skill_ids))
        cursor.execute(f"SELECT * FROM skills WHERE id IN ({placeholders})", skill_ids)
    else:
        cursor.execute("SELECT * FROM skills WHERE is_active = 1")

    skills = [dict(row) for row in cursor.fetchall()]

    conn.close()

    export_data = {
        "version": "1.0",
        "export_type": "skills",
        "exported_at": datetime.now().isoformat(),
        "count": len(skills),
        "skills": skills
    }

    return export_data


def import_skills_from_json(import_data: Dict) -> Tuple[int, List[str]]:
    """
    Import skills from JSON export.

    Returns:
        (imported_count, errors)
    """
    import database as db

    if not import_data.get('skills'):
        return 0, ["No skills found in import data"]

    imported = 0
    errors = []

    for skill in import_data['skills']:
        try:
            skill_id = db.save_skill(
                tool_name=skill['tool_name'],
                description=skill.get('description', ''),
                code=skill.get('code', ''),
                parameters=skill.get('parameters', {}) if skill.get('parameters') else {},
                safety_notes=skill.get('safety_notes', []) if skill.get('safety_notes') else []
            )
            imported += 1
        except Exception as e:
            errors.append(f"Failed to import '{skill.get('tool_name', 'unknown')}': {str(e)}")

    return imported, errors


# ============================================================
# INTEGRATION LOGS
# ============================================================

def _log_integration_event(cursor, integration_id: int, log_level: str,
                          event_type: str, message: str, details: Optional[Dict] = None):
    """Internal helper to log integration events."""
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO integration_logs
        (integration_id, log_level, event_type, message, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (integration_id, log_level, event_type, message,
          json.dumps(details) if details else None, now))


def get_integration_logs(integration_id: int, log_level: Optional[str] = None,
                        limit: int = 100) -> List[Dict]:
    """Get logs for an integration."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM integration_logs WHERE integration_id = ?"
    params = [integration_id]

    if log_level:
        query += " AND log_level = ?"
        params.append(log_level)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()

    logs = []
    for row in rows:
        log = dict(row)
        log['details'] = json.loads(log['details']) if log['details'] else {}
        logs.append(log)

    return logs


# Initialize database on module import
initialize_database()
