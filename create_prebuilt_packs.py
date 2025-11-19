"""
Create Pre-built Skill Packs
=============================
Initializes the marketplace with example skills and skill packs for demonstration.
"""

import database as db
import database_marketplace as db_market

def create_example_skills():
    """Create example skills for the marketplace."""

    example_skills = [
        # Web Scraping Pack Skills
        {
            "tool_name": "fetch_webpage",
            "description": "Fetch and parse HTML content from a URL using requests and BeautifulSoup",
            "code": """
import requests
from bs4 import BeautifulSoup

def fetch_webpage(url: str) -> dict:
    \"\"\"Fetch and parse a webpage.\"\"\"
    response = requests.get(url, timeout=10)
    soup = BeautifulSoup(response.content, 'html.parser')

    return {
        'title': soup.title.string if soup.title else '',
        'text': soup.get_text()[:1000],
        'links': [a.get('href') for a in soup.find_all('a', href=True)][:10]
    }
""",
            "parameters": {"url": "str"},
            "safety_notes": ["Always validate URLs", "Respect robots.txt", "Rate limit requests"],
            "category": "Web Scraping"
        },
        {
            "tool_name": "extract_links",
            "description": "Extract all hyperlinks from HTML content",
            "code": """
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def extract_links(html: str, base_url: str = None) -> list:
    \"\"\"Extract all links from HTML.\"\"\"
    soup = BeautifulSoup(html, 'html.parser')
    links = []

    for a in soup.find_all('a', href=True):
        href = a.get('href')
        if base_url:
            href = urljoin(base_url, href)
        links.append({'text': a.get_text(), 'url': href})

    return links
""",
            "parameters": {"html": "str", "base_url": "str"},
            "safety_notes": ["Validate base URL", "Handle relative URLs"],
            "category": "Web Scraping"
        },

        # Data Analysis Pack Skills
        {
            "tool_name": "analyze_csv",
            "description": "Load and analyze CSV data with pandas, providing summary statistics",
            "code": """
import pandas as pd

def analyze_csv(file_path: str) -> dict:
    \"\"\"Analyze a CSV file and return statistics.\"\"\"
    df = pd.read_csv(file_path)

    return {
        'shape': df.shape,
        'columns': list(df.columns),
        'dtypes': df.dtypes.to_dict(),
        'summary': df.describe().to_dict(),
        'missing': df.isnull().sum().to_dict()
    }
""",
            "parameters": {"file_path": "str"},
            "safety_notes": ["Validate file path", "Handle large files carefully"],
            "category": "Data Analysis"
        },
        {
            "tool_name": "create_visualization",
            "description": "Create a visualization from data using matplotlib",
            "code": """
import matplotlib.pyplot as plt
import pandas as pd

def create_visualization(data: dict, chart_type: str = 'bar') -> str:
    \"\"\"Create a chart and save to file.\"\"\"
    df = pd.DataFrame(data)

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == 'bar':
        df.plot(kind='bar', ax=ax)
    elif chart_type == 'line':
        df.plot(kind='line', ax=ax)
    elif chart_type == 'scatter':
        df.plot(kind='scatter', x=df.columns[0], y=df.columns[1], ax=ax)

    output_path = 'visualization.png'
    plt.savefig(output_path)
    plt.close()

    return output_path
""",
            "parameters": {"data": "dict", "chart_type": "str"},
            "safety_notes": ["Validate chart type", "Handle plot cleanup"],
            "category": "Data Analysis"
        },

        # File Operations Pack Skills
        {
            "tool_name": "read_json_file",
            "description": "Read and parse a JSON file with error handling",
            "code": """
import json
from pathlib import Path

def read_json_file(file_path: str) -> dict:
    \"\"\"Read a JSON file safely.\"\"\"
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
""",
            "parameters": {"file_path": "str"},
            "safety_notes": ["Validate file exists", "Handle encoding issues"],
            "category": "File Operations"
        },
        {
            "tool_name": "write_json_file",
            "description": "Write data to a JSON file with pretty formatting",
            "code": """
import json
from pathlib import Path

def write_json_file(data: dict, file_path: str, indent: int = 2) -> str:
    \"\"\"Write data to JSON file.\"\"\"
    path = Path(file_path)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

    return str(path.absolute())
""",
            "parameters": {"data": "dict", "file_path": "str", "indent": "int"},
            "safety_notes": ["Validate file path", "Handle write permissions"],
            "category": "File Operations"
        },

        # API Integration Pack Skills
        {
            "tool_name": "call_rest_api",
            "description": "Make HTTP requests to REST APIs with authentication support",
            "code": """
import requests

def call_rest_api(url: str, method: str = 'GET', headers: dict = None,
                  data: dict = None, params: dict = None) -> dict:
    \"\"\"Call a REST API endpoint.\"\"\"
    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers,
        json=data,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return {
        'status_code': response.status_code,
        'headers': dict(response.headers),
        'data': response.json() if response.content else None
    }
""",
            "parameters": {"url": "str", "method": "str", "headers": "dict", "data": "dict", "params": "dict"},
            "safety_notes": ["Validate URLs", "Handle timeouts", "Secure API keys"],
            "category": "API Integration"
        },

        # Text Processing Pack Skills
        {
            "tool_name": "extract_keywords",
            "description": "Extract keywords from text using simple frequency analysis",
            "code": """
from collections import Counter
import re

def extract_keywords(text: str, top_n: int = 10, min_length: int = 4) -> list:
    \"\"\"Extract keywords from text.\"\"\"
    # Convert to lowercase and extract words
    words = re.findall(r'\\b[a-z]+\\b', text.lower())

    # Filter by length and common stopwords
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
    words = [w for w in words if len(w) >= min_length and w not in stopwords]

    # Count and return top N
    counter = Counter(words)
    return [word for word, count in counter.most_common(top_n)]
""",
            "parameters": {"text": "str", "top_n": "int", "min_length": "int"},
            "safety_notes": ["Handle large texts", "Validate input encoding"],
            "category": "Text Processing"
        },

        # Testing Pack Skills
        {
            "tool_name": "run_unit_tests",
            "description": "Run Python unit tests and return results",
            "code": """
import unittest
import sys
from io import StringIO

def run_unit_tests(test_module_path: str) -> dict:
    \"\"\"Run unit tests and return results.\"\"\"
    # Capture output
    output = StringIO()
    runner = unittest.TextTestRunner(stream=output, verbosity=2)

    # Load and run tests
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=test_module_path, pattern='test_*.py')

    result = runner.run(suite)

    return {
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'success': result.wasSuccessful(),
        'output': output.getvalue()
    }
""",
            "parameters": {"test_module_path": "str"},
            "safety_notes": ["Isolate test environment", "Handle test failures"],
            "category": "Testing"
        },

        # Database Pack Skills
        {
            "tool_name": "query_sqlite",
            "description": "Execute SQL queries on SQLite database",
            "code": """
import sqlite3
from pathlib import Path

def query_sqlite(db_path: str, query: str, params: tuple = None) -> list:
    \"\"\"Execute a SQL query on SQLite database.\"\"\"
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

    results = cursor.fetchall()
    conn.close()

    return results
""",
            "parameters": {"db_path": "str", "query": "str", "params": "tuple"},
            "safety_notes": ["Prevent SQL injection", "Validate database path"],
            "category": "Database"
        }
    ]

    created_skills = {}

    for skill in example_skills:
        try:
            # Check if skill already exists
            existing = db.list_skills(active_only=True, limit=1000)
            if any(s['tool_name'] == skill['tool_name'] for s in existing):
                print(f"⏭️  Skill already exists: {skill['tool_name']}")
                # Get skill ID for categorization
                skill_id = next(s['id'] for s in existing if s['tool_name'] == skill['tool_name'])
                created_skills[skill['tool_name']] = skill_id
                continue

            # Save skill to database
            skill_id = db.save_skill(
                tool_name=skill['tool_name'],
                description=skill['description'],
                code=skill['code'],
                parameters=skill['parameters'],
                safety_notes=skill['safety_notes']
            )

            created_skills[skill['tool_name']] = skill_id

            # Tag with category
            categories = db_market.list_categories()
            category = next((c for c in categories if c['name'] == skill['category']), None)

            if category:
                db_market.tag_skill(skill_id, category['id'])

            # Set pricing (all free for examples)
            db_market.set_skill_pricing(
                skill_id=skill_id,
                pricing_type='free',
                price=0.0
            )

            print(f"✅ Created skill: {skill['tool_name']}")

        except Exception as e:
            print(f"❌ Failed to create skill {skill['tool_name']}: {e}")

    return created_skills


def create_skill_packs(skill_ids: dict):
    """Create pre-built skill packs."""

    packs = [
        {
            "name": "Web Scraping Essentials",
            "description": "Complete toolkit for web scraping including fetching pages, extracting links, and parsing HTML content. Perfect for data collection and web automation tasks.",
            "icon": "🌐",
            "skills": ["fetch_webpage", "extract_links"],
            "pricing_type": "free",
            "price": 0.0
        },
        {
            "name": "Data Analysis Pro",
            "description": "Comprehensive data analysis tools with pandas integration, CSV analysis, and matplotlib visualizations. Ideal for data science workflows.",
            "icon": "📊",
            "skills": ["analyze_csv", "create_visualization"],
            "pricing_type": "free",
            "price": 0.0
        },
        {
            "name": "File Operations Bundle",
            "description": "Essential file handling utilities for JSON operations. Simple and reliable file I/O for your applications.",
            "icon": "📁",
            "skills": ["read_json_file", "write_json_file"],
            "pricing_type": "free",
            "price": 0.0
        },
        {
            "name": "API Integration Kit",
            "description": "Professional REST API integration tools with authentication support and error handling. Build robust API clients quickly.",
            "icon": "🔌",
            "skills": ["call_rest_api"],
            "pricing_type": "free",
            "price": 0.0
        },
        {
            "name": "Text Processing Suite",
            "description": "Advanced text analysis and processing capabilities including keyword extraction and NLP utilities.",
            "icon": "📝",
            "skills": ["extract_keywords"],
            "pricing_type": "free",
            "price": 0.0
        },
        {
            "name": "Testing & QA Pack",
            "description": "Automated testing utilities for running unit tests and generating test reports. Ensure code quality.",
            "icon": "🧪",
            "skills": ["run_unit_tests"],
            "pricing_type": "free",
            "price": 0.0
        },
        {
            "name": "Database Essentials",
            "description": "SQLite database operations with secure query execution and connection management.",
            "icon": "💾",
            "skills": ["query_sqlite"],
            "pricing_type": "free",
            "price": 0.0
        },
        {
            "name": "Full Stack Developer Pack",
            "description": "Complete toolkit for full-stack development including web scraping, API integration, database operations, and file handling. Everything you need in one bundle!",
            "icon": "🚀",
            "skills": ["fetch_webpage", "call_rest_api", "query_sqlite", "read_json_file", "write_json_file"],
            "pricing_type": "free",
            "price": 0.0
        }
    ]

    for pack in packs:
        try:
            # Check if pack already exists
            existing_packs = db_market.list_skill_packs()
            if any(p['name'] == pack['name'] for p in existing_packs):
                print(f"⏭️  Pack already exists: {pack['name']}")
                continue

            # Get skill IDs for this pack
            pack_skill_ids = []
            for skill_name in pack['skills']:
                if skill_name in skill_ids:
                    pack_skill_ids.append(skill_ids[skill_name])

            if not pack_skill_ids:
                print(f"⚠️  No skills found for pack: {pack['name']}")
                continue

            # Create the pack
            pack_id = db_market.create_skill_pack(
                name=pack['name'],
                description=pack['description'],
                skill_ids=pack_skill_ids,
                pricing_type=pack['pricing_type'],
                price=pack['price'],
                icon=pack['icon']
            )

            print(f"✅ Created pack: {pack['name']} (ID: {pack_id}, {len(pack_skill_ids)} skills)")

        except Exception as e:
            print(f"❌ Failed to create pack {pack['name']}: {e}")


def add_sample_ratings():
    """Add sample ratings to skills for demonstration."""
    try:
        skills = db.list_skills(active_only=True, limit=100)

        # Sample ratings for different users
        sample_reviews = [
            {
                "user_id": "alice_dev",
                "ratings": {
                    "fetch_webpage": (5, "Excellent! Works perfectly for my scraping needs."),
                    "analyze_csv": (5, "Super useful for quick data analysis!"),
                    "call_rest_api": (4, "Good tool, could use more auth options."),
                }
            },
            {
                "user_id": "bob_engineer",
                "ratings": {
                    "fetch_webpage": (4, "Reliable and fast."),
                    "create_visualization": (5, "Love the matplotlib integration!"),
                    "query_sqlite": (5, "Perfect for database work."),
                }
            },
            {
                "user_id": "carol_analyst",
                "ratings": {
                    "analyze_csv": (4, "Great for basic analysis."),
                    "extract_keywords": (3, "Works but could be more sophisticated."),
                    "read_json_file": (5, "Simple and reliable."),
                }
            }
        ]

        for reviewer in sample_reviews:
            user_id = reviewer['user_id']
            for skill in skills:
                skill_name = skill['tool_name']
                if skill_name in reviewer['ratings']:
                    rating, review_text = reviewer['ratings'][skill_name]
                    try:
                        db_market.add_rating(
                            skill_id=skill['id'],
                            user_id=user_id,
                            rating=rating,
                            review_text=review_text
                        )
                        print(f"✅ Added rating for {skill_name} by {user_id}")
                    except Exception as e:
                        print(f"⏭️  Rating already exists or failed: {skill_name} - {e}")

    except Exception as e:
        print(f"❌ Failed to add sample ratings: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🎁 Creating Pre-built Skill Packs")
    print("=" * 60)
    print()

    # Step 1: Create example skills
    print("Step 1: Creating example skills...")
    skill_ids = create_example_skills()
    print(f"\n✅ Created/found {len(skill_ids)} skills\n")

    # Step 2: Create skill packs
    print("Step 2: Creating skill packs...")
    create_skill_packs(skill_ids)
    print()

    # Step 3: Add sample ratings
    print("Step 3: Adding sample ratings...")
    add_sample_ratings()
    print()

    print("=" * 60)
    print("✅ Pre-built skill packs initialized!")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  📦 Skills: {len(skill_ids)}")
    print(f"  🎁 Packs: 8 skill packs created")
    print(f"  ⭐ Sample ratings added")
    print()
    print("You can now browse these in the Streamlit UI!")
