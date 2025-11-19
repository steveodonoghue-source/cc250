"""
Database Extensions for Skill Marketplace

Adds marketplace features:
- Skill categories and tags
- Ratings and reviews
- Versioning
- Dependencies
- Pricing and licensing
- Download/install tracking
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Use same DB path as main database
DB_PATH = Path(__file__).parent / "autogen_data.db"


def get_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_marketplace_tables():
    """
    Initialize marketplace-specific tables.

    This extends the existing database schema with marketplace features
    without modifying the core tables.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ========================================================================
    # 1. Skill Categories Table
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            icon TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # ========================================================================
    # 2. Skill Tags (Many-to-Many with Skills)
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_tags (
            skill_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (skill_id, category_id),
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES skill_categories (id) ON DELETE CASCADE
        )
    """)

    # ========================================================================
    # 3. Skill Ratings and Reviews
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
            review_text TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE,
            UNIQUE(skill_id, user_id)
        )
    """)

    # ========================================================================
    # 4. Skill Versions
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            code TEXT NOT NULL,
            parameters TEXT,
            changelog TEXT,
            is_breaking BOOLEAN DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE,
            UNIQUE(skill_id, version)
        )
    """)

    # ========================================================================
    # 5. Skill Dependencies
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            depends_on_skill_id INTEGER NOT NULL,
            min_version TEXT,
            max_version TEXT,
            is_required BOOLEAN DEFAULT 1,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on_skill_id) REFERENCES skills (id) ON DELETE CASCADE,
            UNIQUE(skill_id, depends_on_skill_id)
        )
    """)

    # ========================================================================
    # 6. Skill Pricing
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            pricing_type TEXT NOT NULL CHECK (pricing_type IN ('free', 'one_time', 'subscription', 'pay_per_use')),
            price REAL DEFAULT 0.0,
            currency TEXT DEFAULT 'USD',
            billing_period TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # ========================================================================
    # 7. Skill Downloads/Installs
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_installs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            installed_at TEXT NOT NULL,
            last_used TEXT,
            install_count INTEGER DEFAULT 1,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE,
            UNIQUE(skill_id, user_id)
        )
    """)

    # ========================================================================
    # 8. Skill Packs (Bundles)
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_packs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            icon TEXT,
            pricing_type TEXT CHECK (pricing_type IN ('free', 'paid')),
            price REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    """)

    # ========================================================================
    # 9. Skill Pack Contents (Many-to-Many)
    # ========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_pack_contents (
            pack_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            PRIMARY KEY (pack_id, skill_id),
            FOREIGN KEY (pack_id) REFERENCES skill_packs (id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE
        )
    """)

    # ========================================================================
    # Create Indexes for Performance
    # ========================================================================
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_tags_skill ON skill_tags(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_tags_category ON skill_tags(category_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_ratings_skill ON skill_ratings(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_ratings_user ON skill_ratings(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_dependencies_skill ON skill_dependencies(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_pricing_skill ON skill_pricing(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_installs_skill ON skill_installs(skill_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_installs_user ON skill_installs(user_id)")

    conn.commit()
    conn.close()
    logger.info("Marketplace tables initialized successfully")


# ============================================================================
# Skill Category Operations
# ============================================================================

def create_category(name: str, description: str = "", icon: str = "") -> int:
    """Create a skill category."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO skill_categories (name, description, icon, created_at)
            VALUES (?, ?, ?, ?)
        """, (name, description, icon, now))

        conn.commit()
        return cursor.lastrowid

    except sqlite3.IntegrityError:
        # Category already exists
        cursor.execute("SELECT id FROM skill_categories WHERE name = ?", (name,))
        return cursor.fetchone()[0]
    finally:
        conn.close()


def list_categories() -> List[Dict]:
    """List all categories."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM skill_categories ORDER BY name")
    categories = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return categories


def tag_skill(skill_id: int, category_id: int):
    """Tag a skill with a category."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR IGNORE INTO skill_tags (skill_id, category_id)
            VALUES (?, ?)
        """, (skill_id, category_id))

        conn.commit()
    finally:
        conn.close()


def get_skill_categories(skill_id: int) -> List[Dict]:
    """Get categories for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.*
        FROM skill_categories c
        JOIN skill_tags st ON c.id = st.category_id
        WHERE st.skill_id = ?
    """, (skill_id,))

    categories = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return categories


# ============================================================================
# Skill Rating Operations
# ============================================================================

def add_rating(skill_id: int, user_id: str, rating: int, review_text: str = "") -> int:
    """Add or update a rating for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO skill_ratings (skill_id, user_id, rating, review_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_id, user_id) DO UPDATE SET
                rating = excluded.rating,
                review_text = excluded.review_text,
                updated_at = excluded.updated_at
        """, (skill_id, user_id, rating, review_text, now, now))

        conn.commit()
        return cursor.lastrowid

    finally:
        conn.close()


def get_skill_rating_summary(skill_id: int) -> Dict:
    """Get rating summary for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as review_count,
            AVG(rating) as average_rating,
            SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) as five_star,
            SUM(CASE WHEN rating = 4 THEN 1 ELSE 0 END) as four_star,
            SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END) as three_star,
            SUM(CASE WHEN rating = 2 THEN 1 ELSE 0 END) as two_star,
            SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as one_star
        FROM skill_ratings
        WHERE skill_id = ?
    """, (skill_id,))

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else {
        'review_count': 0,
        'average_rating': 0.0,
        'five_star': 0,
        'four_star': 0,
        'three_star': 0,
        'two_star': 0,
        'one_star': 0
    }


def get_skill_reviews(skill_id: int, limit: int = 10) -> List[Dict]:
    """Get recent reviews for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM skill_ratings
        WHERE skill_id = ? AND review_text != ''
        ORDER BY created_at DESC
        LIMIT ?
    """, (skill_id, limit))

    reviews = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reviews


# ============================================================================
# Skill Versioning Operations
# ============================================================================

def save_skill_version(skill_id: int, version: str, code: str, parameters: Dict,
                       changelog: str = "", is_breaking: bool = False) -> int:
    """Save a new version of a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO skill_versions (skill_id, version, code, parameters, changelog, is_breaking, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (skill_id, version, code, json.dumps(parameters), changelog, is_breaking, now))

        conn.commit()
        return cursor.lastrowid

    finally:
        conn.close()


def get_skill_versions(skill_id: int) -> List[Dict]:
    """Get all versions of a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM skill_versions
        WHERE skill_id = ?
        ORDER BY created_at DESC
    """, (skill_id,))

    versions = [dict(row) for row in cursor.fetchall()]

    # Parse parameters JSON
    for v in versions:
        v['parameters'] = json.loads(v['parameters']) if v['parameters'] else {}

    conn.close()
    return versions


# ============================================================================
# Skill Dependency Operations
# ============================================================================

def add_dependency(skill_id: int, depends_on_skill_id: int, min_version: str = None,
                   max_version: str = None, is_required: bool = True):
    """Add a dependency between skills."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR IGNORE INTO skill_dependencies
            (skill_id, depends_on_skill_id, min_version, max_version, is_required)
            VALUES (?, ?, ?, ?, ?)
        """, (skill_id, depends_on_skill_id, min_version, max_version, is_required))

        conn.commit()
    finally:
        conn.close()


def get_skill_dependencies(skill_id: int) -> List[Dict]:
    """Get dependencies for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            sd.*,
            s.tool_name as dependency_name,
            s.description as dependency_description
        FROM skill_dependencies sd
        JOIN skills s ON sd.depends_on_skill_id = s.id
        WHERE sd.skill_id = ?
    """, (skill_id,))

    deps = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return deps


# ============================================================================
# Skill Pricing Operations
# ============================================================================

def set_skill_pricing(skill_id: int, pricing_type: str, price: float = 0.0,
                     currency: str = "USD", billing_period: str = None) -> int:
    """Set pricing for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        # Deactivate old pricing
        cursor.execute("""
            UPDATE skill_pricing SET is_active = 0 WHERE skill_id = ?
        """, (skill_id,))

        # Insert new pricing
        cursor.execute("""
            INSERT INTO skill_pricing (skill_id, pricing_type, price, currency, billing_period, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (skill_id, pricing_type, price, currency, billing_period, now))

        conn.commit()
        return cursor.lastrowid

    finally:
        conn.close()


def get_skill_pricing(skill_id: int) -> Optional[Dict]:
    """Get active pricing for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM skill_pricing
        WHERE skill_id = ? AND is_active = 1
        ORDER BY created_at DESC
        LIMIT 1
    """, (skill_id,))

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


# ============================================================================
# Skill Install Tracking
# ============================================================================

def track_install(skill_id: int, user_id: str = "default_user"):
    """Track a skill installation."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO skill_installs (skill_id, user_id, installed_at, last_used, install_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(skill_id, user_id) DO UPDATE SET
                install_count = install_count + 1,
                last_used = excluded.last_used
        """, (skill_id, user_id, now, now))

        conn.commit()
    finally:
        conn.close()


def get_install_count(skill_id: int) -> int:
    """Get total install count for a skill."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT SUM(install_count) as total
        FROM skill_installs
        WHERE skill_id = ?
    """, (skill_id,))

    row = cursor.fetchone()
    conn.close()

    return row['total'] if row and row['total'] else 0


# ============================================================================
# Skill Pack Operations
# ============================================================================

def create_skill_pack(name: str, description: str, skill_ids: List[int],
                     pricing_type: str = "free", price: float = 0.0, icon: str = "") -> int:
    """Create a skill pack (bundle)."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()

        # Create pack
        cursor.execute("""
            INSERT INTO skill_packs (name, description, icon, pricing_type, price, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, icon, pricing_type, price, now))

        pack_id = cursor.lastrowid

        # Add skills to pack
        for skill_id in skill_ids:
            cursor.execute("""
                INSERT INTO skill_pack_contents (pack_id, skill_id)
                VALUES (?, ?)
            """, (pack_id, skill_id))

        conn.commit()
        return pack_id

    finally:
        conn.close()


def list_skill_packs() -> List[Dict]:
    """List all skill packs."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            sp.*,
            COUNT(spc.skill_id) as skill_count
        FROM skill_packs sp
        LEFT JOIN skill_pack_contents spc ON sp.id = spc.pack_id
        WHERE sp.is_active = 1
        GROUP BY sp.id
        ORDER BY sp.created_at DESC
    """)

    packs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return packs


def get_pack_skills(pack_id: int) -> List[Dict]:
    """Get all skills in a pack."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.*
        FROM skills s
        JOIN skill_pack_contents spc ON s.id = spc.skill_id
        WHERE spc.pack_id = ?
    """, (pack_id,))

    skills = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return skills


# ============================================================================
# Enhanced Skill Listing with Marketplace Data
# ============================================================================

def list_skills_with_marketplace_data(limit: int = 100, category_id: int = None,
                                      min_rating: float = None) -> List[Dict]:
    """List skills with marketplace metadata."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            s.*,
            COALESCE(AVG(sr.rating), 0) as average_rating,
            COUNT(DISTINCT sr.id) as review_count,
            COALESCE(SUM(si.install_count), 0) as install_count,
            sp.pricing_type,
            sp.price
        FROM skills s
        LEFT JOIN skill_ratings sr ON s.id = sr.skill_id
        LEFT JOIN skill_installs si ON s.id = si.skill_id
        LEFT JOIN skill_pricing sp ON s.id = sp.skill_id AND sp.is_active = 1
    """

    where_clauses = ["s.is_active = 1"]
    params = []

    if category_id:
        query += " JOIN skill_tags st ON s.id = st.skill_id"
        where_clauses.append("st.category_id = ?")
        params.append(category_id)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += """
        GROUP BY s.id
    """

    if min_rating:
        query += " HAVING average_rating >= ?"
        params.append(min_rating)

    query += " ORDER BY s.usage_count DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)

    skills = []
    for row in cursor.fetchall():
        skill = dict(row)
        # Parse JSON fields
        skill['parameters'] = json.loads(skill['parameters']) if skill['parameters'] else {}
        skill['safety_notes'] = json.loads(skill['safety_notes']) if skill['safety_notes'] else []
        skills.append(skill)

    conn.close()
    return skills


# ============================================================================
# Initialization Helper
# ============================================================================

def init_with_default_categories():
    """Initialize marketplace tables with default categories."""
    init_marketplace_tables()

    # Create default categories
    default_categories = [
        ("Web Scraping", "Tools for extracting data from websites", "🌐"),
        ("Data Analysis", "Tools for analyzing and processing data", "📊"),
        ("File Operations", "Tools for file manipulation and I/O", "📁"),
        ("API Integration", "Tools for working with APIs", "🔌"),
        ("Testing", "Tools for testing and validation", "🧪"),
        ("DevOps", "Tools for deployment and operations", "⚙️"),
        ("Machine Learning", "Tools for ML and AI tasks", "🤖"),
        ("Text Processing", "Tools for text manipulation", "📝"),
        ("Image Processing", "Tools for image manipulation", "🖼️"),
        ("Database", "Tools for database operations", "💾")
    ]

    for name, desc, icon in default_categories:
        try:
            create_category(name, desc, icon)
            logger.info(f"Created category: {name}")
        except Exception as e:
            logger.warning(f"Category {name} may already exist: {e}")


if __name__ == "__main__":
    # Run initialization
    logging.basicConfig(level=logging.INFO)
    init_with_default_categories()
    print("✅ Marketplace database initialized with default categories!")
