"""
AutoGen v0.4 Multi-Agent Coding System - Production Edition
============================================================
Advanced collaborative AI coding assistant featuring:
- Gemini 2.5 Pro (Planner/Reviewer/SkillGenerator) and Flash (Coder/FileHandler)
- 10+ specialized tools with dynamic skill generation
- Distributed code execution via Redis Queue (RQ)
- Real-time cost monitoring and alerting
- Human-in-the-loop approval with state persistence
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import zipfile
from typing import Any, Dict, List, Sequence, Optional, Callable
from datetime import datetime
from pathlib import Path
import io
import inspect

import streamlit as st
from pydantic import BaseModel, Field, ValidationError
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
import database as db
import database_marketplace as db_market
import database_cost_optimization as db_cost
import database_orchestration as db_orch
import database_testing_quality as db_test
from autogen_agentchat.messages import (
    ChatMessage,
    TextMessage,
    ToolCallSummaryMessage,
)
from autogen_core.models import ChatCompletionClient
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
import google.generativeai as genai

# Optional imports for tools
try:
    import requests
except ImportError:
    requests = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    from PIL import Image
except ImportError:
    Image = None

# Redis Queue imports
try:
    from redis import Redis
    from rq import Queue
    from rq.job import Job
    redis_available = True
except ImportError:
    redis_available = False
    Redis = None
    Queue = None
    Job = None

# ChromaDB and RAG imports
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    chromadb_available = True
except ImportError:
    chromadb_available = False
    chromadb = None
    Settings = None
    SentenceTransformer = None

# Document processing imports
try:
    from PyPDF2 import PdfReader
    pdf_available = True
except ImportError:
    pdf_available = False
    PdfReader = None

try:
    from docx import Document as DocxDocument
    docx_available = True
except ImportError:
    docx_available = False
    DocxDocument = None

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    text_splitter_available = True
except ImportError:
    text_splitter_available = False
    RecursiveCharacterTextSplitter = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Cost Tracking Configuration
# ============================================================================

# Gemini 2.5 pricing (approximate, update with actual prices)
PRICING = {
    "gemini-2.5-pro": {
        "input": 0.00125 / 1000,   # $0.00125 per 1K input tokens
        "output": 0.00500 / 1000,  # $0.00500 per 1K output tokens
    },
    "gemini-2.5-flash": {
        "input": 0.00010 / 1000,   # $0.00010 per 1K input tokens
        "output": 0.00040 / 1000,  # $0.00040 per 1K output tokens
    },
    "gemini-2.0-flash-exp": {  # Fallback for image analysis
        "input": 0.00010 / 1000,
        "output": 0.00040 / 1000,
    }
}

COST_ALERT_THRESHOLD = 1.00  # Alert when cost exceeds $1.00

# ============================================================================
# ChromaDB Configuration and Initialization
# ============================================================================

CHROMA_PERSIST_DIR = "./chroma_db"  # Directory for persistent storage
CHROMA_COLLECTION_NAME = "default_knowledge"  # Default collection name

def get_chroma_client():
    """Initialize and return ChromaDB client with persistence."""
    if not chromadb_available:
        logger.warning("ChromaDB not available")
        return None

    try:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        logger.info(f"ChromaDB client initialized with persistence at {CHROMA_PERSIST_DIR}")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB: {e}")
        return None

def get_chroma_collection(client, collection_name: str = CHROMA_COLLECTION_NAME):
    """Get or create a ChromaDB collection."""
    if not client:
        return None

    try:
        # Get or create collection
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Long-term knowledge base for agents"}
        )
        logger.info(f"ChromaDB collection '{collection_name}' ready with {collection.count()} documents")
        return collection
    except Exception as e:
        logger.error(f"Failed to get/create collection: {e}")
        return None

def get_embedding_model():
    """Initialize and return sentence transformer model for embeddings."""
    if not chromadb_available or not SentenceTransformer:
        return None

    try:
        # Use a lightweight but effective model
        model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Embedding model loaded: all-MiniLM-L6-v2")
        return model
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        return None

# ============================================================================
# Pydantic Schemas for Structured Outputs
# ============================================================================

class TaskStep(BaseModel):
    """A single step in the task plan."""
    step_number: int = Field(..., description="Sequential step number")
    description: str = Field(..., description="What needs to be done in this step")
    estimated_complexity: str = Field(..., description="Low, Medium, or High")
    dependencies: List[int] = Field(default_factory=list, description="Step numbers this depends on")


class TaskPlan(BaseModel):
    """Structured plan for implementing a coding task."""
    task_summary: str = Field(..., description="Brief summary of the overall task")
    requirements: List[str] = Field(..., description="Key requirements identified")
    steps: List[TaskStep] = Field(..., description="Ordered list of implementation steps")
    estimated_time: str = Field(..., description="Estimated total time (e.g., '30 minutes')")
    technologies: List[str] = Field(default_factory=list, description="Technologies/libraries needed")
    risks: List[str] = Field(default_factory=list, description="Potential risks or challenges")

    def to_markdown(self) -> str:
        """Convert plan to markdown format for display."""
        md = f"# Task Plan: {self.task_summary}\n\n"
        md += f"**Estimated Time:** {self.estimated_time}\n\n"

        if self.technologies:
            md += f"**Technologies:** {', '.join(self.technologies)}\n\n"

        md += "## Requirements\n"
        for req in self.requirements:
            md += f"- {req}\n"

        md += "\n## Implementation Steps\n"
        for step in self.steps:
            md += f"\n### Step {step.step_number}: {step.description}\n"
            md += f"- **Complexity:** {step.estimated_complexity}\n"
            if step.dependencies:
                md += f"- **Depends on:** Steps {', '.join(map(str, step.dependencies))}\n"

        if self.risks:
            md += "\n## Risks & Challenges\n"
            for risk in self.risks:
                md += f"- {risk}\n"

        return md


class CodeReview(BaseModel):
    """Structured code review output."""
    overall_quality: str = Field(..., description="Excellent, Good, Fair, or Poor")
    strengths: List[str] = Field(..., description="What's done well")
    issues: List[str] = Field(default_factory=list, description="Problems found")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")
    security_concerns: List[str] = Field(default_factory=list, description="Security issues")
    approved: bool = Field(..., description="Whether code is approved")
    feedback_summary: str = Field(..., description="Overall feedback in 1-2 sentences")


class SkillDefinition(BaseModel):
    """Definition for a dynamically generated skill/tool."""
    tool_name: str = Field(..., description="Name of the tool function")
    description: str = Field(..., description="What the tool does")
    parameters: Dict[str, str] = Field(..., description="Parameter names and types")
    code: str = Field(..., description="Complete Python function code")
    safety_notes: List[str] = Field(default_factory=list, description="Security considerations")


class TestComparison(BaseModel):
    """Comparison result between baseline and new test run."""
    coherence_score: int = Field(..., description="Coherence score from 1-10", ge=1, le=10)
    differences_found: List[str] = Field(default_factory=list, description="List of differences identified")
    improvements: List[str] = Field(default_factory=list, description="Improvements over baseline")
    regressions: List[str] = Field(default_factory=list, description="Regressions from baseline")
    critique: str = Field(..., description="Natural language critique and analysis")
    recommendation: str = Field(..., description="Accept or Reject recommendation")


# ============================================================================
# Cost Tracking Wrapper for ChatCompletionClient
# ============================================================================

class CostTrackingChatClient(OpenAIChatCompletionClient):
    """
    Wrapper around OpenAIChatCompletionClient that tracks token usage and costs.

    Intercepts LLM responses to extract token counts and calculates costs based
    on the model's pricing.
    """

    def __init__(self, agent_name: str, model: str, *args, **kwargs):
        super().__init__(model=model, *args, **kwargs)
        self.agent_name = agent_name
        self.model = model
        logger.info(f"Created CostTrackingChatClient for {agent_name} using {model}")

    async def create(self, messages: Sequence[Any], *args, **kwargs) -> Any:
        """Override create to track token usage."""
        # Call parent implementation
        response = await super().create(messages, *args, **kwargs)

        # Extract token usage from response
        try:
            # Response structure varies, try to extract usage info
            usage = getattr(response, 'usage', None)

            if usage:
                input_tokens = getattr(usage, 'prompt_tokens', 0)
                output_tokens = getattr(usage, 'completion_tokens', 0)
                total_tokens = getattr(usage, 'total_tokens', input_tokens + output_tokens)

                # Calculate cost
                model_pricing = PRICING.get(self.model, PRICING["gemini-2.5-flash"])
                input_cost = input_tokens * model_pricing["input"]
                output_cost = output_tokens * model_pricing["output"]
                total_cost = input_cost + output_cost

                # Track in session state
                self._track_usage(input_tokens, output_tokens, total_cost)

                logger.info(
                    f"[{self.agent_name}] Tokens: {input_tokens} in, {output_tokens} out, "
                    f"${total_cost:.6f}"
                )
        except Exception as e:
            logger.warning(f"Could not extract token usage: {e}")

        return response

    def _track_usage(self, input_tokens: int, output_tokens: int, cost: float):
        """Track usage in session state."""
        if "cost_tracking" not in st.session_state:
            st.session_state.cost_tracking = {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost": 0.0,
                "by_agent": {},
                "history": []
            }

        # Update totals
        st.session_state.cost_tracking["total_input_tokens"] += input_tokens
        st.session_state.cost_tracking["total_output_tokens"] += output_tokens
        st.session_state.cost_tracking["total_cost"] += cost

        # Update per-agent tracking
        if self.agent_name not in st.session_state.cost_tracking["by_agent"]:
            st.session_state.cost_tracking["by_agent"][self.agent_name] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "calls": 0
            }

        agent_stats = st.session_state.cost_tracking["by_agent"][self.agent_name]
        agent_stats["input_tokens"] += input_tokens
        agent_stats["output_tokens"] += output_tokens
        agent_stats["cost"] += cost
        agent_stats["calls"] += 1

        # Add to history
        st.session_state.cost_tracking["history"].append({
            "timestamp": datetime.now().isoformat(),
            "agent": self.agent_name,
            "model": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost
        })


# ============================================================================
# Redis Queue Setup for Distributed Execution
# ============================================================================

def get_redis_queue():
    """Get or create Redis Queue connection."""
    if not redis_available:
        return None

    try:
        # Try to connect to Redis (assumes Redis running on localhost:6379)
        redis_conn = Redis(host='localhost', port=6379, db=0, socket_connect_timeout=1)
        redis_conn.ping()  # Test connection

        # Create RQ queue
        queue = Queue('code_execution', connection=redis_conn)
        logger.info("Successfully connected to Redis Queue")
        return queue
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


def execute_code_worker(code: str, language: str = "python") -> Dict[str, Any]:
    """
    Worker function for RQ to execute code in isolation.

    This runs in a separate process managed by RQ worker.

    Args:
        code: Code to execute
        language: Programming language

    Returns:
        Dict with status, output, and error information
    """
    if language.lower() != "python":
        return {
            "status": "error",
            "output": "",
            "error": f"Language '{language}' not supported"
        }

    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        # Execute with timeout
        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=10,  # 10 second timeout for worker
            cwd=tempfile.gettempdir()
        )

        # Clean up
        os.unlink(temp_file)

        return {
            "status": "success" if result.returncode == 0 else "error",
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else "",
            "returncode": result.returncode
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "output": "",
            "error": "Execution timeout (10 seconds exceeded)"
        }
    except Exception as e:
        return {
            "status": "error",
            "output": "",
            "error": str(e)
        }


def poll_job_result(job_id: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Poll RQ job for result.

    Args:
        job_id: RQ job ID
        timeout: Maximum time to wait in seconds

    Returns:
        Job result or timeout error
    """
    if not redis_available:
        return {"status": "error", "error": "Redis not available"}

    try:
        redis_conn = Redis(host='localhost', port=6379, db=0)
        job = Job.fetch(job_id, connection=redis_conn)

        # Wait for job to complete (with timeout)
        import time
        start_time = time.time()

        while not job.is_finished and not job.is_failed:
            if time.time() - start_time > timeout:
                return {
                    "status": "timeout",
                    "error": f"Job did not complete within {timeout} seconds"
                }
            time.sleep(0.5)
            job.refresh()

        if job.is_failed:
            return {
                "status": "error",
                "error": f"Job failed: {job.exc_info}"
            }

        return job.result

    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# Tool Implementations (10 Original + Job Polling)
# ============================================================================

def tool_web_search(query: str) -> str:
    """
    Tool #1: Hybrid Web Search and RAG (ChromaDB + Web).

    NEW BEHAVIOR:
    - First queries ChromaDB for internal knowledge
    - If insufficient, performs external web search
    - Combines both results for comprehensive retrieval
    """
    logger.info(f"🔍 Tool called: web_search('{query}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "web_search",
        "query": query,
        "timestamp": datetime.now().isoformat()
    })

    results = []
    internal_results = []

    # 1. INTERNAL KNOWLEDGE RETRIEVAL (ChromaDB)
    try:
        if chromadb_available and "chroma_client" in st.session_state:
            client = st.session_state.chroma_client
            collection = get_chroma_collection(client)

            if collection and collection.count() > 0:
                # Query ChromaDB with embedding
                embedding_model = st.session_state.get("embedding_model")
                if embedding_model:
                    query_embedding = embedding_model.encode([query])[0].tolist()

                    chroma_results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(5, collection.count())
                    )

                    if chroma_results and chroma_results['documents']:
                        internal_results = chroma_results['documents'][0]
                        logger.info(f"Found {len(internal_results)} internal knowledge results")
    except Exception as e:
        logger.error(f"ChromaDB query error: {e}")

    # Build result string
    result_parts = [f"🔍 Hybrid Search Results for: \"{query}\"\n"]

    # Add internal results if found
    if internal_results:
        result_parts.append("\n📚 INTERNAL KNOWLEDGE BASE:\n")
        for idx, doc in enumerate(internal_results, 1):
            # Truncate long documents
            doc_preview = doc[:200] + "..." if len(doc) > 200 else doc
            result_parts.append(f"{idx}. {doc_preview}\n")
        result_parts.append("\n")

    # 2. EXTERNAL WEB SEARCH (if needed)
    if len(internal_results) < 3:
        result_parts.append("🌐 EXTERNAL WEB SEARCH:\n")
        result_parts.append("[Simulated - Configure real search API for production]\n\n")
        result_parts.append("Top External Results:\n")
        result_parts.append("1. Official Documentation - Latest best practices and API references\n")
        result_parts.append("2. Stack Overflow - Community solutions and common patterns\n")
        result_parts.append("3. GitHub Repositories - Implementation examples\n")
        result_parts.append("4. Recent Blog Posts - Current trends and recommendations\n\n")

    # Add recommendations
    result_parts.append("💡 RECOMMENDATIONS:\n")
    if internal_results:
        result_parts.append("✓ Found relevant internal knowledge - prioritize these sources\n")
    result_parts.append("- Verify information against official documentation\n")
    result_parts.append("- Cross-reference with multiple sources\n")
    result_parts.append("- Check for recent updates and security advisories\n")

    return "".join(result_parts)


def tool_execute_code(code: str, language: str = "python") -> str:
    """
    Tool #2: Execute code via Redis Queue (distributed execution).

    NEW BEHAVIOR:
    - Enqueues code to RQ worker
    - Returns job ID for polling
    - Requires HITL approval first
    """
    logger.warning(f"⚠️ Tool called: execute_code (language={language})")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "execute_code",
        "language": language,
        "code_length": len(code),
        "timestamp": datetime.now().isoformat()
    })

    # SECURITY: Request human approval
    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None

    st.session_state.pending_approval = {
        "action": "Code Execution (Distributed)",
        "code": code,
        "language": language,
        "timestamp": datetime.now().isoformat()
    }

    if not st.session_state.get("approval_granted", False):
        return "⚠️ Code execution requires human approval. Waiting for user confirmation..."

    # Reset approval
    st.session_state.approval_granted = False

    # Try to use RQ if available, fallback to local execution
    queue = get_redis_queue()

    if queue:
        # Enqueue to RQ worker
        try:
            job = queue.enqueue(execute_code_worker, code, language, job_timeout=30)
            logger.info(f"Code enqueued to RQ worker: {job.id}")

            return f"""✅ Code execution job enqueued to distributed worker!

Job ID: {job.id}

To get results, use tool_poll_job_result with this job ID.
The FileHandler agent will automatically poll for results."""

        except Exception as e:
            logger.error(f"RQ enqueue failed: {e}")
            return f"❌ Failed to enqueue job: {str(e)}\n\nFalling back to local execution..."

    # Fallback: Local execution (original behavior)
    logger.warning("Redis not available, executing locally")

    if language.lower() != "python":
        return f"❌ Language '{language}' not supported. Only Python is supported."

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=tempfile.gettempdir()
        )

        os.unlink(temp_file)

        output = result.stdout if result.returncode == 0 else result.stderr
        status = "✅ Success" if result.returncode == 0 else f"❌ Error (code {result.returncode})"

        return f"{status}\n\nOutput:\n{output}"

    except subprocess.TimeoutExpired:
        return "❌ Execution timeout (5 seconds exceeded)"
    except Exception as e:
        return f"❌ Execution error: {str(e)}"


def tool_poll_job_result(job_id: str) -> str:
    """
    Tool #11: Poll RQ job for execution results.

    Used by FileHandler to get results from distributed code execution.
    """
    logger.info(f"📊 Tool called: poll_job_result('{job_id}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "poll_job_result",
        "job_id": job_id,
        "timestamp": datetime.now().isoformat()
    })

    result = poll_job_result(job_id, timeout=30)

    if result.get("status") == "success":
        return f"""✅ Job completed successfully!

Output:
{result.get('output', '')}
"""
    elif result.get("status") == "timeout":
        return f"""⏱️ Job is still running or timed out.

Error: {result.get('error', 'Unknown')}

Try polling again or increase timeout."""
    else:
        error = result.get('error', 'Unknown error')
        return f"""❌ Job failed!

Error:
{error}

Output:
{result.get('output', '')}
"""


def tool_static_analysis(file_path: str) -> str:
    """Tool #3: Static code analysis."""
    logger.info(f"🔍 Tool called: static_analysis('{file_path}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "static_analysis",
        "file_path": file_path,
        "timestamp": datetime.now().isoformat()
    })

    if not os.path.exists(file_path):
        return f"❌ File not found: {file_path}"

    result = f"""
    📊 Static Analysis Report for: {file_path}

    Code Quality (Simulated):
    ✅ PEP 8 Compliance: 95/100
    ✅ Complexity: Low (Cyclomatic complexity: 3)
    ✅ Maintainability Index: 85/100

    Security Scan (Simulated):
    ✅ No SQL injection vulnerabilities detected
    ✅ No hardcoded secrets found
    ⚠️  Consider input validation on line 42

    Type Checking (Simulated):
    ✅ All type hints valid
    ℹ️  Consider adding type hints to 2 functions

    Recommendations:
    1. Add docstrings to public functions
    2. Increase test coverage (current: simulated 75%)
    3. Consider breaking down large functions (>50 lines)

    Overall Score: 85/100 (Good)

    [Note: This is a simulation. For production, integrate actual tools like Pylint, Bandit, MyPy]
    """

    return result


def tool_create_visualization(data_json: str, chart_type: str = "bar") -> str:
    """Tool #4: Create data visualization."""
    logger.info(f"📊 Tool called: create_visualization(chart_type='{chart_type}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "create_visualization",
        "chart_type": chart_type,
        "timestamp": datetime.now().isoformat()
    })

    if plt is None:
        return "❌ Matplotlib not available. Install with: pip install matplotlib"

    try:
        data = json.loads(data_json)
        labels = data.get("labels", [])
        values = data.get("values", [])

        if not labels or not values:
            return "❌ Invalid data format. Expected: {\"labels\": [...], \"values\": [...]}"

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type.lower() == "bar":
            ax.bar(labels, values)
            ax.set_ylabel('Value')
        elif chart_type.lower() == "line":
            ax.plot(labels, values, marker='o')
            ax.set_ylabel('Value')
        elif chart_type.lower() == "pie":
            ax.pie(values, labels=labels, autopct='%1.1f%%')
        elif chart_type.lower() == "scatter":
            ax.scatter(range(len(values)), values)
            ax.set_xticks(range(len(values)))
            ax.set_xticklabels(labels)
        else:
            return f"❌ Unsupported chart type: {chart_type}"

        ax.set_title(f'{chart_type.capitalize()} Chart')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        temp_dir = tempfile.gettempdir()
        chart_path = os.path.join(temp_dir, f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close()

        return f"✅ Chart created successfully!\nPath: {chart_path}\n\n[Chart saved and ready for viewing]"

    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON data: {str(e)}"
    except Exception as e:
        return f"❌ Visualization error: {str(e)}"


def tool_read_document(file_path: str) -> str:
    """Tool #5: Read document contents."""
    logger.info(f"📄 Tool called: read_document('{file_path}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "read_document",
        "file_path": file_path,
        "timestamp": datetime.now().isoformat()
    })

    try:
        if not os.path.exists(file_path):
            return f"❌ File not found: {file_path}"

        file_size = os.path.getsize(file_path)
        if file_size > 1_000_000:
            return f"❌ File too large ({file_size} bytes). Maximum: 1MB"

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if len(content) > 10000:
            content = content[:10000] + f"\n\n... (truncated, total length: {len(content)} chars)"

        return f"✅ Document read successfully from: {file_path}\n\n{content}"

    except UnicodeDecodeError:
        return f"❌ Cannot read file (binary or unsupported encoding): {file_path}"
    except Exception as e:
        return f"❌ Error reading document: {str(e)}"


def tool_analyze_image(image_file_path: str, prompt: str = "Describe this image in detail") -> str:
    """Tool #6: Analyze image using Gemini Vision."""
    logger.info(f"🖼️ Tool called: analyze_image('{image_file_path}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "analyze_image",
        "image_path": image_file_path,
        "prompt": prompt,
        "timestamp": datetime.now().isoformat()
    })

    try:
        if not os.path.exists(image_file_path):
            return f"❌ Image file not found: {image_file_path}"

        api_key = (
            os.environ.get("GEMINI_API_KEY") or
            os.environ.get("GOOGLE_API_KEY") or
            st.session_state.get("google_api_key")
        )

        if not api_key:
            return "❌ API key not found for image analysis"

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')

        if Image:
            img = Image.open(image_file_path)
        else:
            return "❌ PIL not available. Install with: pip install pillow"

        response = model.generate_content([prompt, img])

        return f"✅ Image Analysis:\n\n{response.text}"

    except Exception as e:
        return f"❌ Image analysis error: {str(e)}"


def tool_create_project_zip() -> str:
    """Tool #7: Create ZIP archive."""
    logger.info(f"📦 Tool called: create_project_zip()")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "create_project_zip",
        "timestamp": datetime.now().isoformat()
    })

    try:
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(
            temp_dir,
            f"project_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )

        project_dir = os.getcwd()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(project_dir):
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'venv', 'env', '.venv']]

                for file in files:
                    if file.endswith(('.py', '.md', '.txt', '.toml', '.yaml', '.yml')):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, project_dir)
                        zipf.write(file_path, arcname)

        size = os.path.getsize(zip_path)
        size_mb = size / (1024 * 1024)

        return f"✅ Project ZIP created successfully!\nPath: {zip_path}\nSize: {size_mb:.2f} MB"

    except Exception as e:
        return f"❌ ZIP creation error: {str(e)}"


def tool_get_current_datetime() -> str:
    """Tool #8: Get current datetime."""
    logger.info(f"🕐 Tool called: get_current_datetime()")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "get_current_datetime",
        "timestamp": datetime.now().isoformat()
    })

    now = datetime.now()

    return f"""
    📅 Current Date and Time:

    ISO Format: {now.isoformat()}
    Human Readable: {now.strftime('%A, %B %d, %Y at %I:%M:%S %p')}
    Unix Timestamp: {now.timestamp()}
    UTC: {datetime.utcnow().isoformat()}Z
    """


def tool_git_command(command: str) -> str:
    """Tool #9: Execute Git commands."""
    logger.info(f"🔧 Tool called: git_command('{command}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "git_command",
        "command": command,
        "timestamp": datetime.now().isoformat()
    })

    safe_commands = ['status', 'log', 'diff', 'branch', 'remote', 'show', 'ls-files']

    cmd_parts = command.strip().split()
    if not cmd_parts:
        return "❌ Empty command"

    if cmd_parts[0] not in safe_commands:
        return f"❌ Command '{cmd_parts[0]}' not in safe list: {', '.join(safe_commands)}"

    try:
        result = subprocess.run(
            ['git'] + cmd_parts,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=os.getcwd()
        )

        output = result.stdout if result.returncode == 0 else result.stderr
        status = "✅ Success" if result.returncode == 0 else f"❌ Error (code {result.returncode})"

        return f"{status}\n\nCommand: git {command}\n\nOutput:\n{output}"

    except subprocess.TimeoutExpired:
        return "❌ Command timeout (10 seconds exceeded)"
    except FileNotFoundError:
        return "❌ Git not found. Please install Git."
    except Exception as e:
        return f"❌ Git command error: {str(e)}"


def tool_validate_json(json_data: str, schema_name: str = "TaskPlan") -> str:
    """Tool #10: Validate JSON against Pydantic schemas."""
    logger.info(f"✅ Tool called: validate_json(schema='{schema_name}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "validate_json",
        "schema": schema_name,
        "timestamp": datetime.now().isoformat()
    })

    schemas = {
        "TaskPlan": TaskPlan,
        "CodeReview": CodeReview,
        "TaskStep": TaskStep,
        "SkillDefinition": SkillDefinition
    }

    if schema_name not in schemas:
        return f"❌ Unknown schema: {schema_name}. Available: {', '.join(schemas.keys())}"

    try:
        data = json.loads(json_data)
        schema_class = schemas[schema_name]
        validated = schema_class(**data)

        return f"✅ JSON is valid for schema '{schema_name}'!\n\nValidated data:\n{validated.model_dump_json(indent=2)}"

    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON: {str(e)}"
    except ValidationError as e:
        return f"❌ Schema validation failed:\n{str(e)}"
    except Exception as e:
        return f"❌ Validation error: {str(e)}"


def tool_ingest_document(file_path: str, collection_name: str = "default_knowledge") -> str:
    """
    Tool #12: Ingest document into ChromaDB for long-term knowledge.

    ENHANCED for Feature #5 (ChromaDB RAG):
    - Reads document (txt, md, py, pdf, docx)
    - Chunks text with smart overlap
    - Generates embeddings with metadata
    - Stores with rich metadata: file type, date, page numbers, hierarchy
    - Enables source citation and metadata filtering

    Args:
        file_path: Path to document file
        collection_name: ChromaDB collection name (default: "default_knowledge")

    Returns:
        Success message with chunk count and metadata info
    """
    logger.info(f"📥 Tool called: ingest_document('{file_path}', collection='{collection_name}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "ingest_document",
        "file_path": file_path,
        "collection": collection_name,
        "timestamp": datetime.now().isoformat()
    })

    if not chromadb_available:
        return "❌ ChromaDB not available. Install chromadb and sentence-transformers."

    try:
        # Read document content
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"

        content = ""
        file_ext = path.suffix.lower()
        page_contents = []  # For PDF page tracking

        # Get file metadata
        file_size = path.stat().st_size
        ingestion_date = datetime.now().isoformat()
        file_name = path.name

        # Text-based files
        if file_ext in ['.txt', '.md', '.py', '.json', '.yaml', '.yml', '.sh', '.bash']:
            content = path.read_text(encoding='utf-8')
            file_type = "code" if file_ext in ['.py', '.sh', '.bash', '.json', '.yaml', '.yml'] else "text"
        # PDF files (with page tracking)
        elif file_ext == '.pdf':
            if not pdf_available:
                return "❌ PDF support not available. Install PyPDF2."
            pdf_reader = PdfReader(str(path))
            file_type = "pdf"
            # Track page numbers for better citations
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                page_text = page.extract_text()
                page_contents.append({
                    "text": page_text,
                    "page_number": page_num
                })
            content = "\n\n".join([p["text"] for p in page_contents])
        # DOCX files
        elif file_ext == '.docx':
            if not docx_available:
                return "❌ DOCX support not available. Install python-docx."
            doc = DocxDocument(str(path))
            file_type = "docx"
            content = "\n\n".join([paragraph.text for paragraph in doc.paragraphs])
        else:
            return f"❌ Unsupported file type: {file_ext}. Supported: txt, md, py, pdf, docx"

        if not content.strip():
            return f"❌ No content extracted from {file_path}"

        # Enhanced chunking with better overlap for context preservation
        if text_splitter_available and RecursiveCharacterTextSplitter:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=800,  # Increased for better context
                chunk_overlap=100,  # More overlap for continuity
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""]  # Smarter splitting
            )
            chunks = splitter.split_text(content)
        else:
            # Simple chunking if langchain not available
            chunk_size = 800
            overlap = 100
            chunks = []
            for i in range(0, len(content), chunk_size - overlap):
                chunks.append(content[i:i+chunk_size])

        # Get ChromaDB client and collection
        client = st.session_state.get("chroma_client")
        if not client:
            client = get_chroma_client()
            if client:
                st.session_state.chroma_client = client

        if not client:
            return "❌ Failed to initialize ChromaDB client"

        collection = get_chroma_collection(client, collection_name)
        if not collection:
            return f"❌ Failed to get/create collection: {collection_name}"

        # Generate embeddings and store
        embedding_model = st.session_state.get("embedding_model")
        if not embedding_model:
            embedding_model = get_embedding_model()
            if embedding_model:
                st.session_state.embedding_model = embedding_model

        if not embedding_model:
            return "❌ Failed to load embedding model"

        # Enhanced metadata for each chunk
        metadatas = []
        for i, chunk in enumerate(chunks):
            metadata = {
                "source": file_path,
                "file_name": file_name,
                "file_type": file_type,
                "file_extension": file_ext,
                "file_size_bytes": file_size,
                "ingestion_date": ingestion_date,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "chunk_length": len(chunk),
                "collection": collection_name
            }

            # Add page number for PDFs
            if page_contents:
                # Estimate which page this chunk is from
                char_position = content.find(chunk[:50])  # Find chunk in full content
                chars_per_page = len(content) / len(page_contents)
                estimated_page = int(char_position / chars_per_page) + 1
                metadata["page_number"] = min(estimated_page, len(page_contents))

            # Add document hierarchy hints for code files
            if file_type == "code":
                if "def " in chunk or "class " in chunk:
                    metadata["contains_definition"] = True
                if "import " in chunk:
                    metadata["contains_imports"] = True

            metadatas.append(metadata)

        # Add chunks to collection with unique IDs
        timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        chunk_ids = [f"{path.stem}_{timestamp_suffix}_chunk_{i}" for i in range(len(chunks))]
        embeddings = embedding_model.encode(chunks).tolist()

        collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=chunk_ids,
            metadatas=metadatas
        )

        logger.info(f"Ingested {len(chunks)} chunks from {file_path} with enhanced metadata")

        return f"""✅ Document ingested successfully with enhanced metadata!

📄 File: {file_name}
📦 Chunks: {len(chunks)} (800 chars each, 100 char overlap)
🏷️  Type: {file_type}
📊 Size: {file_size / 1024:.1f} KB
📚 Collection: {collection_name}
🔢 Total documents in collection: {collection.count()}

✨ Enhanced features:
- Rich metadata (type, date, size, page numbers)
- Source citations enabled
- Metadata filtering ready
- Better chunking with context preservation

Use tool_query_knowledge() for advanced RAG with citations!"""

    except Exception as e:
        logger.error(f"Document ingestion error: {e}")
        return f"❌ Ingestion failed: {str(e)}"


def tool_query_knowledge(
    query: str,
    collection_name: str = "default_knowledge",
    n_results: int = 5,
    filter_file_type: str = None,
    include_citations: bool = True
) -> str:
    """
    Tool #13: Advanced RAG query with citations and hybrid search.

    NEW TOOL for Feature #5 (Enhanced ChromaDB RAG):
    - Hybrid search: Semantic (embeddings) + Keyword matching
    - Source citations with metadata (file, page, type)
    - Metadata filtering (by file type, date, etc.)
    - Re-ranking for better result quality
    - Detailed provenance tracking

    Args:
        query: Search query
        collection_name: ChromaDB collection to search
        n_results: Number of results to return (default: 5)
        filter_file_type: Filter by file type (e.g., "pdf", "code", "text")
        include_citations: Include source citations (default: True)

    Returns:
        Search results with citations and metadata
    """
    logger.info(f"🔎 Tool called: query_knowledge('{query}', collection='{collection_name}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "query_knowledge",
        "query": query,
        "collection": collection_name,
        "filter_file_type": filter_file_type,
        "timestamp": datetime.now().isoformat()
    })

    if not chromadb_available:
        return "❌ ChromaDB not available. Install chromadb and sentence-transformers."

    try:
        # Get ChromaDB client and collection
        client = st.session_state.get("chroma_client")
        if not client:
            client = get_chroma_client()
            if client:
                st.session_state.chroma_client = client

        if not client:
            return "❌ Failed to initialize ChromaDB client"

        collection = get_chroma_collection(client, collection_name)
        if not collection:
            return f"❌ Collection '{collection_name}' not found. Ingest documents first."

        if collection.count() == 0:
            return f"❌ Collection '{collection_name}' is empty. Ingest documents first."

        # Get embedding model
        embedding_model = st.session_state.get("embedding_model")
        if not embedding_model:
            embedding_model = get_embedding_model()
            if embedding_model:
                st.session_state.embedding_model = embedding_model

        if not embedding_model:
            return "❌ Failed to load embedding model"

        # Build metadata filter if specified
        where_filter = None
        if filter_file_type:
            where_filter = {"file_type": filter_file_type}

        # 1. SEMANTIC SEARCH (Embedding-based)
        query_embedding = embedding_model.encode([query])[0].tolist()

        semantic_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results * 2, collection.count()),  # Get more for re-ranking
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )

        # 2. KEYWORD SEARCH (Simple BM25-style scoring)
        # Query for keyword matches
        query_terms = query.lower().split()
        all_docs = collection.get(
            where=where_filter,
            include=["documents", "metadatas"]
        )

        # Score documents by keyword matches
        keyword_scores = {}
        if all_docs and all_docs["documents"]:
            for idx, doc in enumerate(all_docs["documents"]):
                doc_lower = doc.lower()
                score = sum(1 for term in query_terms if term in doc_lower)
                if score > 0:
                    keyword_scores[idx] = score

        # 3. HYBRID FUSION (Combine semantic + keyword)
        # Use Reciprocal Rank Fusion (RRF)
        combined_scores = {}

        # Add semantic scores (using distance - lower is better)
        if semantic_results and semantic_results["documents"]:
            for rank, (doc, metadata, distance) in enumerate(zip(
                semantic_results["documents"][0],
                semantic_results["metadatas"][0],
                semantic_results["distances"][0]
            ), start=1):
                doc_id = metadata.get("source", "") + str(metadata.get("chunk_index", 0))
                # RRF score: 1 / (k + rank), where k=60 is standard
                combined_scores[doc_id] = combined_scores.get(doc_id, 0) + (1 / (60 + rank))
                # Store document for later retrieval
                if doc_id not in st.session_state.get("_rag_cache", {}):
                    if "_rag_cache" not in st.session_state:
                        st.session_state._rag_cache = {}
                    st.session_state._rag_cache[doc_id] = {
                        "document": doc,
                        "metadata": metadata,
                        "semantic_distance": distance
                    }

        # Add keyword scores
        for idx, kw_score in keyword_scores.items():
            if idx < len(all_docs["metadatas"]):
                metadata = all_docs["metadatas"][idx]
                doc_id = metadata.get("source", "") + str(metadata.get("chunk_index", 0))
                # Normalize keyword score and add to combined
                combined_scores[doc_id] = combined_scores.get(doc_id, 0) + (kw_score / 10)

        # 4. RE-RANK by combined score
        sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        top_results = sorted_results[:n_results]

        # 5. FORMAT RESULTS WITH CITATIONS
        if not top_results:
            return f"❌ No results found for query: '{query}'"

        result_parts = [f"🔎 Knowledge Base Search Results for: \"{query}\"\n"]
        result_parts.append(f"📚 Collection: {collection_name}")
        result_parts.append(f"📊 Found {len(top_results)} relevant results\n")

        if filter_file_type:
            result_parts.append(f"🔍 Filtered by type: {filter_file_type}\n")

        for idx, (doc_id, score) in enumerate(top_results, 1):
            cache_entry = st.session_state._rag_cache.get(doc_id, {})
            doc_text = cache_entry.get("document", "")
            metadata = cache_entry.get("metadata", {})

            # Truncate long documents
            doc_preview = doc_text[:400] + "..." if len(doc_text) > 400 else doc_text

            result_parts.append(f"\n{'='*60}")
            result_parts.append(f"\n📄 Result {idx} (Relevance: {score:.3f})")
            result_parts.append(f"\n{'-'*60}")
            result_parts.append(f"\n{doc_preview}\n")

            # Add citations if enabled
            if include_citations and metadata:
                result_parts.append(f"\n📌 Citation:")
                result_parts.append(f"   Source: {metadata.get('file_name', 'Unknown')}")

                if metadata.get("page_number"):
                    result_parts.append(f"   Page: {metadata['page_number']}")

                result_parts.append(f"   Type: {metadata.get('file_type', 'Unknown')}")
                result_parts.append(f"   Chunk: {metadata.get('chunk_index', 0) + 1}/{metadata.get('total_chunks', '?')}")

                if metadata.get("ingestion_date"):
                    date_str = metadata['ingestion_date'][:10]  # Just date part
                    result_parts.append(f"   Indexed: {date_str}")

                result_parts.append(f"   Full path: {metadata.get('source', 'Unknown')}")

        result_parts.append(f"\n{'='*60}")
        result_parts.append(f"\n\n💡 Search Details:")
        result_parts.append(f"   - Hybrid search: Semantic (embeddings) + Keyword matching")
        result_parts.append(f"   - Re-ranked using Reciprocal Rank Fusion (RRF)")
        result_parts.append(f"   - Total documents in collection: {collection.count()}")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Knowledge query error: {e}")
        return f"❌ Query failed: {str(e)}"


# ============================================================================
# LLM Configuration with Cost Tracking
# ============================================================================

def get_gemini_client(model: str = "gemini-2.5-pro", agent_name: str = "Unknown") -> ChatCompletionClient:
    """
    Get Gemini model client with cost tracking.

    NEW: Returns CostTrackingChatClient wrapper for token/cost monitoring.
    """
    api_key = (
        os.environ.get("GEMINI_API_KEY") or
        os.environ.get("GOOGLE_API_KEY") or
        st.secrets.get("GEMINI_API_KEY") or
        st.secrets.get("GOOGLE_API_KEY") or
        st.session_state.get("google_api_key")
    )

    if not api_key:
        raise ValueError(
            "API key not found. Set GEMINI_API_KEY environment variable, "
            "add to .streamlit/secrets.toml, or enter in the UI."
        )

    genai.configure(api_key=api_key)

    logger.info(f"Creating cost-tracking Gemini client: {model} for {agent_name}")

    return CostTrackingChatClient(
        agent_name=agent_name,
        model=model,
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model_capabilities={
            "vision": True,
            "function_calling": True,
            "json_output": True
        }
    )


# ============================================================================
# Custom Streamlit-Integrated Agents
# ============================================================================

class StreamlitAssistantAgent(AssistantAgent):
    """Custom AssistantAgent with Streamlit integration and cost tracking."""

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name=name, *args, **kwargs)
        self.agent_name = name
        logger.info(f"Initialized StreamlitAssistantAgent: {name}")

    async def on_messages(self, messages: Sequence[ChatMessage], cancellation_token=None) -> ChatMessage:
        """Override to capture and log messages."""
        logger.info(f"{self.agent_name} processing {len(messages)} message(s)")

        response = await super().on_messages(messages, cancellation_token)

        if isinstance(response, TextMessage):
            content = response.content

            try:
                parsed = json.loads(content)
                if "task_summary" in parsed:
                    plan = TaskPlan(**parsed)
                    content = f"**[{self.agent_name}]** 📋 Created Task Plan:\n\n{plan.to_markdown()}"
                elif "overall_quality" in parsed:
                    review = CodeReview(**parsed)
                    content = f"**[{self.agent_name}]** ✅ Code Review Complete:\n\n"
                    content += f"**Quality:** {review.overall_quality}\n\n"
                    content += f"**Approved:** {'✅ Yes' if review.approved else '❌ No'}\n\n"
                    content += f"**Feedback:** {review.feedback_summary}\n\n"
                    if review.strengths:
                        content += "**Strengths:**\n" + "\n".join(f"- {s}" for s in review.strengths) + "\n\n"
                    if review.issues:
                        content += "**Issues:**\n" + "\n".join(f"- {i}" for i in review.issues) + "\n\n"
                    if review.suggestions:
                        content += "**Suggestions:**\n" + "\n".join(f"- {s}" for s in review.suggestions)
                elif "tool_name" in parsed:
                    skill = SkillDefinition(**parsed)
                    content = f"**[{self.agent_name}]** 🧠 Generated New Skill:\n\n"
                    content += f"**Tool Name:** `{skill.tool_name}`\n"
                    content += f"**Description:** {skill.description}\n\n"
                    content += "**Code:**\n```python\n" + skill.code + "\n```\n\n"
                    if skill.safety_notes:
                        content += "**Safety Notes:**\n" + "\n".join(f"- {note}" for note in skill.safety_notes)
                else:
                    content = f"**[{self.agent_name}]** {content}"
            except (json.JSONDecodeError, Exception):
                content = f"**[{self.agent_name}]** {content}"

            self._add_to_streamlit_chat(
                role="assistant",
                content=content,
                agent=self.agent_name
            )
        elif isinstance(response, ToolCallSummaryMessage):
            tool_calls_display = []
            for tc in response.content:
                tool_name = tc.name
                args_str = json.dumps(tc.arguments, indent=2) if tc.arguments else "{}"
                tool_calls_display.append(f"🔧 **{tool_name}**\n```json\n{args_str}\n```")

            self._add_to_streamlit_chat(
                role="assistant",
                content=f"**[{self.agent_name}]** Calling {len(response.content)} tool(s):\n\n" + "\n\n".join(tool_calls_display),
                agent=self.agent_name
            )

        return response

    def _add_to_streamlit_chat(self, role: str, content: str, agent: str):
        """Add message to Streamlit session state."""
        if "messages" not in st.session_state:
            st.session_state.messages = []

        st.session_state.messages.append({
            "role": role,
            "content": content,
            "agent": agent,
            "timestamp": datetime.now().isoformat()
        })


class DynamicFileHandlerAgent(StreamlitAssistantAgent):
    """
    Enhanced FileHandler with dynamic skill registration capability.

    Can register new tools at runtime when SkillGenerator creates them.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dynamic_tools = []  # Track dynamically added tools

    def register_new_skill(self, skill_def: SkillDefinition) -> str:
        """
        Dynamically register a new tool/skill.

        SECURITY: This should only be called after Reviewer approval!

        Args:
            skill_def: SkillDefinition with tool code

        Returns:
            Success or error message
        """
        logger.warning(f"⚠️ Attempting dynamic skill registration: {skill_def.tool_name}")

        try:
            # Create isolated namespace for exec
            namespace = {}

            # Execute the code to define the function
            exec(skill_def.code, namespace)

            # Extract the function
            tool_func = namespace.get(skill_def.tool_name)

            if not tool_func or not callable(tool_func):
                return f"❌ Function '{skill_def.tool_name}' not found or not callable in generated code"

            # Create FunctionTool wrapper
            new_tool = FunctionTool(
                tool_func,
                description=skill_def.description
            )

            # Add to agent's tool list
            if not hasattr(self, '_tools'):
                self._tools = []

            self._tools.append(new_tool)
            self.dynamic_tools.append({
                "name": skill_def.tool_name,
                "description": skill_def.description,
                "registered_at": datetime.now().isoformat()
            })

            logger.info(f"✅ Successfully registered skill: {skill_def.tool_name}")

            return f"""✅ New skill registered successfully!

Tool Name: {skill_def.tool_name}
Description: {skill_def.description}

The tool is now available for use by FileHandler agent.
Total dynamic tools registered: {len(self.dynamic_tools)}
"""

        except Exception as e:
            logger.error(f"Failed to register skill: {e}", exc_info=True)
            return f"❌ Failed to register skill: {str(e)}"


# ============================================================================
# Agent Factory Functions (5 Agents)
# ============================================================================

def create_planner_agent() -> StreamlitAssistantAgent:
    """Create Planner agent with cost tracking."""
    system_message = """You are an expert Planner agent specialized in software architecture and task decomposition.

Your responsibilities:
1. Analyze user requirements thoroughly
2. Break down complex tasks into clear, ordered steps
3. Identify dependencies, risks, and required technologies
4. Create structured plans using the TaskPlan schema
5. Use available tools to research and gather information
6. Hand off to the Coder or FileHandler once you have a complete plan

Available Tools:
- tool_web_search: Research best practices
- tool_query_knowledge: Query internal knowledge base with citations (ENHANCED RAG)
- tool_ingest_document: Ingest documents into knowledge base
- tool_read_document: Read specifications
- tool_analyze_image: Analyze diagrams
- tool_get_current_datetime: Get timestamps
- tool_validate_json: Validate your TaskPlan

Always structure your plan using the TaskPlan schema and validate it."""

    model_client = get_gemini_client("gemini-2.5-pro", agent_name="Planner")

    tools = [
        FunctionTool(tool_web_search, description="Search the web for information"),
        FunctionTool(tool_query_knowledge, description="Query internal knowledge base with hybrid search and citations"),
        FunctionTool(tool_ingest_document, description="Ingest documents into knowledge base with rich metadata"),
        FunctionTool(tool_read_document, description="Read document files"),
        FunctionTool(tool_analyze_image, description="Analyze images and diagrams"),
        FunctionTool(tool_get_current_datetime, description="Get current date and time"),
        FunctionTool(tool_validate_json, description="Validate JSON schemas"),
    ]

    return StreamlitAssistantAgent(
        name="Planner",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Coder", "FileHandler", "SkillGenerator"]
    )


def create_coder_agent() -> StreamlitAssistantAgent:
    """Create Coder agent with cost tracking."""
    system_message = """You are an expert Coder agent specialized in Python development.

Your responsibilities:
1. Implement code based on Planner's specifications
2. Write clean, well-documented, efficient Python code
3. Include comprehensive error handling
4. Add type hints and docstrings
5. Create visualizations when needed
6. Hand off to Reviewer when code is complete

Available Tools:
- tool_create_visualization: Create charts and graphs
- tool_validate_json: Validate structured data

For file operations or execution, hand off to FileHandler.
If you need a capability that doesn't exist, request SkillGenerator to create it."""

    model_client = get_gemini_client("gemini-2.5-flash", agent_name="Coder")

    tools = [
        FunctionTool(tool_create_visualization, description="Create data visualizations"),
        FunctionTool(tool_validate_json, description="Validate JSON schemas"),
    ]

    return StreamlitAssistantAgent(
        name="Coder",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Reviewer", "Planner", "FileHandler", "SkillGenerator"]
    )


def create_reviewer_agent() -> StreamlitAssistantAgent:
    """Create Reviewer agent with cost tracking."""
    system_message = """You are an expert Reviewer agent specialized in code quality and security.

Your responsibilities:
1. Review code for correctness, efficiency, security
2. Check for bugs, edge cases, and potential issues
3. Verify adherence to Python best practices
4. Use tools to verify security best practices
5. Provide structured feedback using CodeReview schema
6. **CRITICAL**: Review and approve dynamically generated skills from SkillGenerator before FileHandler registers them
7. Either approve or send back to Coder/SkillGenerator with feedback

Available Tools:
- tool_web_search: Research security advisories
- tool_query_knowledge: Query internal knowledge base for security best practices
- tool_static_analysis: Run code quality checks
- tool_read_document: Read code files
- tool_analyze_image: Analyze diagrams
- tool_validate_json: Validate structured outputs

When reviewing dynamically generated skills:
- Check for security vulnerabilities
- Verify no malicious code (file deletion, network access, etc.)
- Ensure proper error handling
- Confirm it solves the intended problem

Use CodeReview schema for all reviews."""

    model_client = get_gemini_client("gemini-2.5-pro", agent_name="Reviewer")

    tools = [
        FunctionTool(tool_web_search, description="Search for security information"),
        FunctionTool(tool_query_knowledge, description="Query knowledge base for security best practices with citations"),
        FunctionTool(tool_static_analysis, description="Perform static analysis"),
        FunctionTool(tool_read_document, description="Read code files"),
        FunctionTool(tool_analyze_image, description="Analyze diagrams"),
        FunctionTool(tool_validate_json, description="Validate JSON schemas"),
    ]

    return StreamlitAssistantAgent(
        name="Reviewer",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Coder", "FileHandler", "SkillGenerator", "User"]
    )


def create_filehandler_agent() -> DynamicFileHandlerAgent:
    """Create FileHandler agent with dynamic skill registration."""
    system_message = """You are an expert FileHandler agent specialized in secure I/O operations.

Your responsibilities:
1. Execute code in distributed environment (RQ workers)
2. Poll job results from distributed execution
3. Handle all file reading and writing operations
4. Manage Git operations
5. Create project archives
6. Register dynamically generated skills (after Reviewer approval)
7. Prioritize security and request human approval for risky operations

Available Tools:
- tool_execute_code: Execute code via RQ (requires HITL approval, returns job ID)
- tool_poll_job_result: Poll RQ job for results
- tool_ingest_document: Ingest documents into knowledge base with metadata
- tool_create_visualization: Generate charts
- tool_read_document: Read files
- tool_create_project_zip: Create ZIP archives
- tool_git_command: Execute Git commands
- tool_validate_json: Validate JSON

**IMPORTANT for distributed execution:**
1. When executing code, tool_execute_code returns a job ID
2. Use tool_poll_job_result with the job ID to get results
3. You may need to poll multiple times until job completes

**IMPORTANT for skill registration:**
1. Only register skills that have been approved by Reviewer
2. Never register skills with security concerns
3. Inform the team when new skills are available

Security Guidelines:
- ALWAYS request human approval for code execution
- Validate all file paths
- Limit file sizes
- Use timeouts
- Only allow safe Git commands"""

    model_client = get_gemini_client("gemini-2.5-flash", agent_name="FileHandler")

    tools = [
        FunctionTool(tool_execute_code, description="Execute code via RQ (returns job ID)"),
        FunctionTool(tool_poll_job_result, description="Poll RQ job for results"),
        FunctionTool(tool_ingest_document, description="Ingest documents into knowledge base with rich metadata"),
        FunctionTool(tool_create_visualization, description="Create visualizations"),
        FunctionTool(tool_read_document, description="Read files"),
        FunctionTool(tool_create_project_zip, description="Create ZIP archives"),
        FunctionTool(tool_git_command, description="Execute Git commands"),
        FunctionTool(tool_validate_json, description="Validate JSON schemas"),
    ]

    return DynamicFileHandlerAgent(
        name="FileHandler",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Coder", "Reviewer", "User"]
    )


def create_skill_generator_agent() -> StreamlitAssistantAgent:
    """
    Create SkillGenerator agent for automated skill/tool creation.

    NEW AGENT: Analyzes failures and generates new tools dynamically.
    """
    system_message = """You are an expert SkillGenerator agent specialized in creating new tools and capabilities.

Your unique role:
1. Analyze agent failures or capability gaps
2. Generate clean, safe Python code for new tools
3. Create tools following the standard function signature pattern
4. Include comprehensive docstrings with type hints
5. Consider security implications
6. Output SkillDefinition schema for review
7. Hand off to Reviewer for approval before registration

**Tool Creation Guidelines:**

Function Signature Pattern:
```python
def tool_name(param1: str, param2: int = 0) -> str:
    \"\"\"
    Brief description of what the tool does.

    Args:
        param1: Description of parameter
        param2: Description with default

    Returns:
        Description of return value
    \"\"\"
    # Implementation
    return result
```

Safety Requirements:
- No file deletion or destructive operations
- No network access unless explicitly needed
- Proper error handling
- Input validation
- Timeout protection where applicable

Output Format:
Always use SkillDefinition schema:
{
    "tool_name": "tool_example",
    "description": "What it does",
    "parameters": {"param1": "str", "param2": "int"},
    "code": "complete Python function code",
    "safety_notes": ["List of security considerations"]
}

After generating, validate with tool_validate_json and hand off to Reviewer."""

    model_client = get_gemini_client("gemini-2.5-pro", agent_name="SkillGenerator")

    tools = [
        FunctionTool(tool_web_search, description="Research best practices"),
        FunctionTool(tool_query_knowledge, description="Query knowledge base for existing patterns and examples"),
        FunctionTool(tool_read_document, description="Read existing tool code for reference"),
        FunctionTool(tool_validate_json, description="Validate SkillDefinition schema"),
    ]

    return StreamlitAssistantAgent(
        name="SkillGenerator",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Reviewer"]
    )


def create_testing_agent() -> StreamlitAssistantAgent:
    """
    Create Testing agent for regression testing and comparison.

    NEW AGENT: Compares test outputs against baselines and provides quality scores.
    """
    system_message = """You are an expert Testing agent specialized in regression testing and output comparison.

Your unique role:
1. Compare current agent outputs against saved baselines
2. Analyze differences, improvements, and regressions
3. Provide coherence scores (1-10) for output quality
4. Generate natural language critiques of discrepancies
5. Recommend Accept or Reject based on analysis
6. Output TestComparison schema with structured results

**Comparison Guidelines:**

Scoring Criteria (1-10):
- 10: Perfect match or significant improvement
- 8-9: Minor improvements, no regressions
- 6-7: Equivalent quality, minor differences
- 4-5: Some regressions but acceptable
- 1-3: Major regressions, unacceptable quality

Focus Areas:
- Correctness: Does the output solve the problem?
- Completeness: Are all requirements addressed?
- Code quality: Best practices, security, readability
- Documentation: Clear comments and explanations
- Edge cases: Proper handling of corner cases

When comparing outputs:
1. Extract key elements (code, explanations, structure)
2. Identify functional differences vs. stylistic changes
3. Assess impact of changes (positive/negative)
4. Consider context: improvements may justify differences
5. Be objective: flag real issues, ignore cosmetic changes

**Output Format:**
Always structure your analysis using the TestComparison schema:
{
  "coherence_score": 8,
  "differences_found": ["list of differences"],
  "improvements": ["list of improvements over baseline"],
  "regressions": ["list of regressions from baseline"],
  "critique": "detailed natural language analysis",
  "recommendation": "Accept" or "Reject"
}

Remember: Minor differences are acceptable if quality is maintained or improved.
Major regressions (security issues, incorrect logic, missing functionality) should result in rejection.
"""

    model_client = get_gemini_client("gemini-2.5-pro", agent_name="Testing")

    # Testing agent has minimal tools - focus on analysis
    tools = [
        FunctionTool(tool_validate_json, description="Validate JSON against schemas")
    ]

    return StreamlitAssistantAgent(
        name="Testing",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["User"]  # Report results to user
    )


# ============================================================================
# Team Setup
# ============================================================================

def create_team() -> SelectorGroupChat:
    """Create SelectorGroupChat with 6 agents including SkillGenerator and Testing."""
    logger.info("Creating 6-agent team with RAG, cost tracking, skill generation, and testing...")

    planner = create_planner_agent()
    coder = create_coder_agent()
    reviewer = create_reviewer_agent()
    filehandler = create_filehandler_agent()
    skillgenerator = create_skill_generator_agent()
    testing = create_testing_agent()

    # Use Gemini Pro for team selector
    selector_client = get_gemini_client("gemini-2.5-pro", agent_name="TeamSelector")

    team = SelectorGroupChat(
        participants=[planner, coder, reviewer, filehandler, skillgenerator, testing],
        model_client=selector_client,
        termination_condition=lambda msg: (
            "APPROVED" in str(msg.content).upper() or
            "TERMINATE" in str(msg.content).upper() or
            (isinstance(msg, TextMessage) and '"approved": true' in msg.content.lower())
        ),
        max_turns=40  # More turns for testing and skill generation workflows
    )

    # Store references for special operations
    st.session_state.filehandler_agent = filehandler
    st.session_state.testing_agent = testing

    # Initialize ChromaDB and embedding model
    if chromadb_available and "chroma_client" not in st.session_state:
        st.session_state.chroma_client = get_chroma_client()
        st.session_state.embedding_model = get_embedding_model()

    logger.info("Team created with 6 agents, RAG, cost tracking, and regression testing")
    return team


# ============================================================================
# Streamlit UI with Cost Monitoring
# ============================================================================

def initialize_session_state():
    """Initialize Streamlit session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "team" not in st.session_state:
        st.session_state.team = None

    if "google_api_key" not in st.session_state:
        st.session_state.google_api_key = None

    if "chat_active" not in st.session_state:
        st.session_state.chat_active = False

    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None

    if "approval_granted" not in st.session_state:
        st.session_state.approval_granted = False

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    if "cost_tracking" not in st.session_state:
        st.session_state.cost_tracking = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0,
            "by_agent": {},
            "history": []
        }

    if "filehandler_agent" not in st.session_state:
        st.session_state.filehandler_agent = None

    # New state for regression testing
    if "baselines" not in st.session_state:
        st.session_state.baselines = {}  # {name: {"prompt": str, "output": str, "messages": list}}

    if "regression_mode" not in st.session_state:
        st.session_state.regression_mode = False

    if "current_baseline" not in st.session_state:
        st.session_state.current_baseline = None

    # New state for multimodal
    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = []

    if "chroma_client" not in st.session_state:
        st.session_state.chroma_client = None

    if "embedding_model" not in st.session_state:
        st.session_state.embedding_model = None

    if "testing_agent" not in st.session_state:
        st.session_state.testing_agent = None


def render_sidebar():
    """Render sidebar with configuration, cost monitoring, and regression testing."""
    with st.sidebar:
        st.title("⚙️ Configuration")

        # Model info
        st.markdown("### 🤖 Active Agents (6)")
        st.markdown("""
        - **Planner**: `gemini-2.5-pro` 🧠
        - **Coder**: `gemini-2.5-flash` ⚡
        - **Reviewer**: `gemini-2.5-pro` 🔍
        - **FileHandler**: `gemini-2.5-flash` 📁
        - **SkillGenerator**: `gemini-2.5-pro` 🧠
        - **Testing**: `gemini-2.5-pro` 🧪 **NEW!**
        """)

        st.divider()

        # API Key input
        api_key = st.text_input(
            "Google/Gemini API Key",
            type="password",
            value=st.session_state.google_api_key or "",
            help="Enter your Google Gemini API key"
        )

        if api_key:
            st.session_state.google_api_key = api_key
            os.environ["GEMINI_API_KEY"] = api_key

        st.divider()

        # Team initialization
        if st.button("🚀 Initialize Team", use_container_width=True):
            if not st.session_state.google_api_key:
                st.error("Please enter your Google API key first!")
            else:
                try:
                    with st.spinner("Initializing 5-agent team..."):
                        st.session_state.team = create_team()
                        st.session_state.chat_active = True
                        st.success("✅ Team initialized! 5 agents + RQ + Cost tracking ready!")
                        logger.info("Team initialized with all features")
                except Exception as e:
                    st.error(f"Error initializing team: {str(e)}")
                    logger.error(f"Team initialization error: {e}", exc_info=True)

        st.divider()

        # Conversation Management Section
        st.markdown("### 💾 Conversations")

        # Save current conversation
        if st.session_state.messages and st.button("💾 Save Current Session", use_container_width=True):
            try:
                # Generate session ID if not exists
                if "current_session_id" not in st.session_state:
                    st.session_state.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Generate title from first message
                first_msg = next((m for m in st.session_state.messages if m['role'] == 'user'), None)
                title = first_msg['content'][:50] + "..." if first_msg else "Untitled Session"

                db.save_conversation(
                    session_id=st.session_state.current_session_id,
                    title=title,
                    messages=st.session_state.messages,
                    cost_tracking=st.session_state.cost_tracking
                )
                st.success(f"✅ Saved: {title}")
            except Exception as e:
                st.error(f"Error saving: {e}")

        # List recent conversations
        conversations = db.list_conversations(limit=10)

        if conversations:
            st.markdown("**Recent Sessions:**")
            for conv in conversations[:5]:  # Show top 5
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    # Load button
                    if st.button(
                        f"{conv['title'][:30]}...",
                        key=f"load_{conv['session_id']}",
                        help=f"{conv['message_count']} msgs, ${conv['total_cost']:.3f}"
                    ):
                        try:
                            loaded = db.load_conversation(conv['session_id'])
                            if loaded:
                                st.session_state.messages = loaded['messages']
                                st.session_state.current_session_id = conv['session_id']
                                # Restore cost if available
                                if 'total_cost' in loaded:
                                    st.session_state.cost_tracking['total_cost'] = loaded['total_cost']
                                st.success(f"✅ Loaded: {conv['title'][:20]}...")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error loading: {e}")

                with col2:
                    # Export button
                    if st.button("📤", key=f"export_{conv['session_id']}", help="Export as Markdown"):
                        md_content = db.export_conversation_markdown(conv['session_id'])
                        st.download_button(
                            "⬇️ Download MD",
                            md_content,
                            file_name=f"{conv['session_id']}.md",
                            mime="text/markdown",
                            key=f"download_{conv['session_id']}"
                        )

                with col3:
                    # Delete button
                    if st.button("🗑️", key=f"del_{conv['session_id']}", help="Delete conversation"):
                        db.delete_conversation(conv['session_id'])
                        st.rerun()

        else:
            st.info("No saved conversations yet")

        # View all conversations
        if len(conversations) > 5:
            with st.expander(f"📚 All Conversations ({len(conversations)})"):
                for conv in conversations[5:]:
                    st.text(f"• {conv['title'][:40]} ({conv['message_count']} msgs)")

        st.divider()

        # Cost Monitoring Section
        st.markdown("### 💰 Cost Monitoring")

        cost_data = st.session_state.cost_tracking
        total_cost = cost_data["total_cost"]
        total_tokens = cost_data["total_input_tokens"] + cost_data["total_output_tokens"]

        # Alert if over threshold
        if total_cost > COST_ALERT_THRESHOLD:
            st.error(f"⚠️ COST ALERT: ${total_cost:.4f} exceeds ${COST_ALERT_THRESHOLD:.2f} threshold!")

        st.metric("Total Cost", f"${total_cost:.4f}")
        st.metric("Total Tokens", f"{total_tokens:,}")
        st.metric("Input Tokens", f"{cost_data['total_input_tokens']:,}")
        st.metric("Output Tokens", f"{cost_data['total_output_tokens']:,}")

        # Per-agent breakdown
        if cost_data["by_agent"]:
            with st.expander("📊 Cost by Agent"):
                for agent_name, stats in cost_data["by_agent"].items():
                    st.markdown(f"**{agent_name}**")
                    st.text(f"Calls: {stats['calls']}")
                    st.text(f"Cost: ${stats['cost']:.4f}")
                    st.text(f"Tokens: {stats['input_tokens'] + stats['output_tokens']:,}")
                    st.markdown("---")

        st.divider()

        # Redis Queue Status
        st.markdown("### 🚀 Distributed Execution")
        queue = get_redis_queue()
        if queue:
            st.success("✅ Redis Queue Connected")
            try:
                job_count = len(queue)
                st.metric("Queued Jobs", job_count)
            except:
                st.info("Queue accessible")
        else:
            st.warning("⚠️ Redis not available (falling back to local execution)")

        st.divider()

        # Clear/Reset buttons
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_approval = None
            st.session_state.approval_granted = False
            st.session_state.tool_calls = []
            st.rerun()

        if st.button("🔄 Reset All", use_container_width=True):
            st.session_state.team = None
            st.session_state.messages = []
            st.session_state.chat_active = False
            st.session_state.pending_approval = None
            st.session_state.approval_granted = False
            st.session_state.tool_calls = []
            st.session_state.cost_tracking = {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost": 0.0,
                "by_agent": {},
                "history": []
            }
            st.rerun()

        st.divider()

        # Agent Performance Dashboard
        st.markdown("### 📊 Agent Performance")

        if st.session_state.messages:
            # Calculate agent metrics
            agent_stats = {}
            for msg in st.session_state.messages:
                agent = msg.get('agent', 'Unknown')
                if agent not in agent_stats:
                    agent_stats[agent] = {
                        'messages': 0,
                        'tokens': 0,
                        'cost': 0.0
                    }
                agent_stats[agent]['messages'] += 1

            # Add cost data
            for agent_name, stats in cost_data.get("by_agent", {}).items():
                if agent_name in agent_stats:
                    agent_stats[agent_name]['tokens'] = stats.get('input_tokens', 0) + stats.get('output_tokens', 0)
                    agent_stats[agent_name]['cost'] = stats.get('cost', 0.0)

            # Display metrics
            if agent_stats:
                # Top performer by activity
                top_agent = max(agent_stats.items(), key=lambda x: x[1]['messages'])
                st.metric(
                    "Most Active Agent",
                    top_agent[0],
                    f"{top_agent[1]['messages']} msgs"
                )

                # Agent breakdown
                with st.expander("🤖 Agent Breakdown", expanded=False):
                    for agent, stats in sorted(agent_stats.items(), key=lambda x: x[1]['messages'], reverse=True):
                        st.markdown(f"**{agent}**")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.caption(f"📝 {stats['messages']}")
                        with col2:
                            if stats['cost'] > 0:
                                st.caption(f"💰 ${stats['cost']:.4f}")
                        with col3:
                            if stats['tokens'] > 0:
                                st.caption(f"🔢 {stats['tokens']:,}")
                        st.markdown("---")

                # Efficiency metrics
                total_msgs = sum(s['messages'] for s in agent_stats.values())
                if total_cost > 0 and total_msgs > 0:
                    avg_cost_per_msg = total_cost / total_msgs
                    st.metric("Avg Cost/Message", f"${avg_cost_per_msg:.4f}")

        # Historical performance
        with st.expander("📈 Historical Performance"):
            try:
                # Get cost summary from database
                cost_summary_7d = db.get_cost_summary(days=7)

                if cost_summary_7d and cost_summary_7d['total_cost'] > 0:
                    st.markdown("**Last 7 Days**")
                    st.metric("Total Spend", f"${cost_summary_7d['total_cost']:.2f}")
                    st.metric("API Calls", cost_summary_7d['total_calls'])

                    # Cost by agent (historical)
                    if cost_summary_7d.get('by_agent'):
                        st.markdown("**Top Agents (Cost)**")
                        for agent, stats in sorted(
                            cost_summary_7d['by_agent'].items(),
                            key=lambda x: x[1]['cost'],
                            reverse=True
                        )[:3]:
                            st.text(f"{agent}: ${stats['cost']:.3f}")
                else:
                    st.info("No historical data yet")

            except Exception as e:
                st.caption(f"Historical data unavailable: {e}")

        st.divider()

        # Skill Library Browser (Feature #6 - Enhanced with Marketplace)
        st.markdown("### 🧠 Skill Marketplace")

        # Tab selection for Skills vs Skill Packs
        marketplace_tab1, marketplace_tab2 = st.tabs(["📦 Skills", "🎁 Skill Packs"])

        with marketplace_tab1:
            # Get all skills from marketplace database (with ratings, pricing, installs)
            try:
                # Get categories for filter
                all_categories = db_market.list_categories()

                # Category filter
                category_options = ["All Categories"] + [cat['name'] for cat in all_categories]
                selected_category = st.selectbox(
                    "🏷️ Filter by Category",
                    category_options,
                    key="category_filter"
                )

                # Get category ID if selected
                category_id = None
                if selected_category != "All Categories":
                    category_id = next((cat['id'] for cat in all_categories if cat['name'] == selected_category), None)

                # Search/filter bar
                search_term = st.text_input(
                    "🔍 Search Skills",
                    placeholder="Search by name or description...",
                    key="skill_search"
                )

                # Get skills with marketplace data
                all_skills = db_market.list_skills_with_marketplace_data(
                    limit=100,
                    category_id=category_id
                )

                # Filter skills by search term
                if search_term:
                    filtered_skills = [
                        s for s in all_skills
                        if search_term.lower() in s['tool_name'].lower()
                        or search_term.lower() in s['description'].lower()
                    ]
                else:
                    filtered_skills = all_skills

                # Display skill count
                st.caption(f"📚 {len(filtered_skills)} skills available")

                # Display skills
                if filtered_skills:
                    # Sort options
                    sort_by = st.selectbox(
                        "Sort by",
                        ["Rating", "Installs", "Name", "Usage Count", "Date Added"],
                        key="skill_sort"
                    )

                    # Sort skills
                    if sort_by == "Rating":
                        sorted_skills = sorted(filtered_skills, key=lambda x: x.get('average_rating', 0), reverse=True)
                    elif sort_by == "Installs":
                        sorted_skills = sorted(filtered_skills, key=lambda x: x.get('install_count', 0), reverse=True)
                    elif sort_by == "Usage Count":
                        sorted_skills = sorted(filtered_skills, key=lambda x: x.get('usage_count', 0), reverse=True)
                    elif sort_by == "Date Added":
                        sorted_skills = sorted(filtered_skills, key=lambda x: x.get('created_at', ''), reverse=True)
                    else:  # Name
                        sorted_skills = sorted(filtered_skills, key=lambda x: x['tool_name'])

                    # Display top skills in cards
                    with st.expander(f"📦 Browse Skills ({len(sorted_skills)})", expanded=True):
                        for skill in sorted_skills[:20]:  # Show top 20
                            with st.container():
                                # Skill header with marketplace badges
                                col1, col2, col3, col4 = st.columns([3, 1, 1, 0.5])

                                with col1:
                                    st.markdown(f"**{skill['tool_name']}**")
                                    st.caption(skill['description'][:60] + "..." if len(skill['description']) > 60 else skill['description'])

                                with col2:
                                    # Rating display
                                    avg_rating = skill.get('average_rating', 0)
                                    review_count = skill.get('review_count', 0)
                                    if avg_rating > 0:
                                        stars = "⭐" * int(round(avg_rating))
                                        st.caption(f"{stars} {avg_rating:.1f} ({review_count})")
                                    else:
                                        st.caption("No ratings yet")

                                with col3:
                                    # Install count and pricing
                                    install_count = skill.get('install_count', 0)
                                    pricing_type = skill.get('pricing_type', 'free')
                                    price = skill.get('price', 0.0)

                                    st.caption(f"📥 {install_count} installs")
                                    if pricing_type == 'free' or not pricing_type:
                                        st.caption("💚 FREE")
                                    else:
                                        st.caption(f"💰 ${price:.2f}")

                                with col4:
                                    # Quick actions
                                    if st.button("👁️", key=f"view_{skill['id']}", help="View details"):
                                        st.session_state[f"view_skill_{skill['id']}"] = True

                                # Expanded details (if view button clicked)
                                if st.session_state.get(f"view_skill_{skill['id']}", False):
                                    st.markdown("**Description:**")
                                    st.text(skill['description'])

                                    # Marketplace metadata row
                                    meta_col1, meta_col2, meta_col3 = st.columns(3)
                                    with meta_col1:
                                        st.metric("Installs", skill.get('install_count', 0))
                                    with meta_col2:
                                        st.metric("Usage", skill.get('usage_count', 0))
                                    with meta_col3:
                                        avg_rating = skill.get('average_rating', 0)
                                        st.metric("Rating", f"{avg_rating:.1f}⭐" if avg_rating > 0 else "N/A")

                                    # Rating & Reviews Section
                                    with st.expander("⭐ Ratings & Reviews", expanded=False):
                                        # Get rating summary
                                        rating_summary = db_market.get_skill_rating_summary(skill['id'])

                                        if rating_summary['review_count'] > 0:
                                            # Star distribution
                                            st.markdown("**Rating Distribution:**")
                                            total_reviews = rating_summary['review_count']
                                            for star in [5, 4, 3, 2, 1]:
                                                count = rating_summary.get(f'{["", "one", "two", "three", "four", "five"][star]}_star', 0)
                                                percentage = (count / total_reviews * 100) if total_reviews > 0 else 0
                                                st.progress(percentage / 100, text=f"{star}⭐ ({count})")

                                            st.markdown("---")

                                            # Display reviews
                                            st.markdown("**Recent Reviews:**")
                                            reviews = db_market.get_skill_reviews(skill['id'], limit=5)
                                            for review in reviews:
                                                stars = "⭐" * review['rating']
                                                st.text(f"{stars} - {review['user_id']}")
                                                if review.get('review_text'):
                                                    st.caption(review['review_text'])
                                                st.caption(f"Posted: {review['created_at'][:10]}")
                                                st.markdown("---")
                                        else:
                                            st.info("No reviews yet. Be the first to rate this skill!")

                                        # Add rating form
                                        st.markdown("**Rate this skill:**")
                                        rating_value = st.slider(
                                            "Your rating",
                                            min_value=1,
                                            max_value=5,
                                            value=5,
                                            key=f"rating_slider_{skill['id']}"
                                        )
                                        review_text = st.text_area(
                                            "Your review (optional)",
                                            placeholder="Share your experience with this skill...",
                                            key=f"review_text_{skill['id']}"
                                        )
                                        if st.button("Submit Rating", key=f"submit_rating_{skill['id']}"):
                                            try:
                                                user_id = st.session_state.get('user_id', 'streamlit_user')
                                                db_market.add_rating(
                                                    skill_id=skill['id'],
                                                    user_id=user_id,
                                                    rating=rating_value,
                                                    review_text=review_text
                                                )
                                                st.success("✅ Rating submitted!")
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Failed to submit rating: {e}")

                                    st.markdown("**Parameters:**")
                                    params = skill.get('parameters', {})
                                    if params:
                                        for param, ptype in params.items():
                                            st.text(f"  • {param}: {ptype}")
                                    else:
                                        st.text("  No parameters")

                                    # Code preview
                                    with st.expander("💻 View Code"):
                                        st.code(skill['code'], language='python')

                                    # Safety notes
                                    if skill.get('safety_notes'):
                                        with st.expander("⚠️ Safety Notes"):
                                            for note in skill['safety_notes']:
                                                st.text(f"• {note}")

                                    # Metadata
                                    st.caption(f"Created: {skill.get('created_at', 'Unknown')[:10]}")

                                    # Action buttons
                                    col_act1, col_act2, col_act3 = st.columns(3)

                                    with col_act1:
                                        # Export skill as JSON
                                        skill_json = {
                                            "tool_name": skill['tool_name'],
                                            "description": skill['description'],
                                            "parameters": skill['parameters'],
                                            "code": skill['code'],
                                            "safety_notes": skill['safety_notes']
                                        }
                                        st.download_button(
                                            "📥 Export",
                                            data=str(skill_json),
                                            file_name=f"{skill['tool_name']}.json",
                                            mime="application/json",
                                            key=f"export_{skill['id']}",
                                            help="Export skill for sharing"
                                        )

                                    with col_act2:
                                        # Copy to clipboard (show code)
                                        if st.button("📋 Copy", key=f"copy_{skill['id']}", help="Copy code"):
                                            st.code(skill['code'], language='python')
                                            st.success("Code displayed above!")

                                    with col_act3:
                                        # Delete skill
                                        if st.button("🗑️ Delete", key=f"delete_{skill['id']}", help="Delete skill"):
                                            try:
                                                db.delete_skill(skill['tool_name'])
                                                st.success(f"Deleted: {skill['tool_name']}")
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Delete failed: {e}")

                                    # Close button
                                    if st.button("✖️ Close", key=f"close_{skill['id']}"):
                                        st.session_state[f"view_skill_{skill['id']}"] = False
                                        st.rerun()

                                st.markdown("---")

                else:
                    st.info("No skills found. Agents will generate skills dynamically as needed.")

                # Quick actions
                st.markdown("**Quick Actions:**")
                col_qa1, col_qa2 = st.columns(2)

                with col_qa1:
                    # Import skill from JSON
                    uploaded_skill = st.file_uploader(
                        "📤 Import Skill",
                        type=['json'],
                        key="import_skill",
                        help="Import a skill from JSON file"
                    )

                    if uploaded_skill:
                        try:
                            import json
                            skill_data = json.load(uploaded_skill)

                            # Validate required fields
                            required = ['tool_name', 'description', 'code', 'parameters', 'safety_notes']
                            if all(k in skill_data for k in required):
                                # Save to database
                                db.save_skill(
                                    tool_name=skill_data['tool_name'],
                                    description=skill_data['description'],
                                    code=skill_data['code'],
                                    parameters=skill_data['parameters'],
                                    safety_notes=skill_data['safety_notes']
                                )
                                st.success(f"✅ Imported: {skill_data['tool_name']}")
                                st.rerun()
                            else:
                                st.error("Invalid skill format. Missing required fields.")
                        except Exception as e:
                            st.error(f"Import failed: {e}")

                with col_qa2:
                    # Refresh skills list
                    if st.button("🔄 Refresh", use_container_width=True, help="Reload skills from database"):
                        st.rerun()

            except Exception as e:
                st.error(f"Skill library error: {e}")
                st.caption("Skills can be viewed once generated by SkillGenerator agent")

        # Skill Packs Tab
        with marketplace_tab2:
            try:
                st.markdown("#### 🎁 Skill Packs - Curated Bundles")
                st.caption("Pre-configured skill bundles for common tasks")

                # Get all skill packs
                all_packs = db_market.list_skill_packs()

                if all_packs:
                    for pack in all_packs:
                        with st.container():
                            # Pack header
                            pack_col1, pack_col2, pack_col3 = st.columns([3, 1, 1])

                            with pack_col1:
                                icon = pack.get('icon', '📦')
                                st.markdown(f"{icon} **{pack['name']}**")
                                st.caption(pack['description'][:80] + "..." if len(pack['description']) > 80 else pack['description'])

                            with pack_col2:
                                # Pricing
                                pricing_type = pack.get('pricing_type', 'free')
                                price = pack.get('price', 0.0)
                                if pricing_type == 'free':
                                    st.caption("💚 FREE")
                                else:
                                    st.caption(f"💰 ${price:.2f}")

                            with pack_col3:
                                # View pack button
                                if st.button("👁️", key=f"view_pack_{pack['id']}", help="View pack details"):
                                    st.session_state[f"view_pack_{pack['id']}"] = True

                            # Expanded pack details
                            if st.session_state.get(f"view_pack_{pack['id']}", False):
                                st.markdown("**Description:**")
                                st.text(pack['description'])

                                # Get skills in this pack
                                pack_skills = db_market.get_skill_pack_skills(pack['id'])

                                st.markdown(f"**Included Skills ({len(pack_skills)}):**")
                                for skill in pack_skills:
                                    st.text(f"  • {skill['tool_name']} - {skill['description'][:50]}...")

                                # Action buttons
                                pack_act_col1, pack_act_col2 = st.columns(2)

                                with pack_act_col1:
                                    if st.button("📥 Install Pack", key=f"install_pack_{pack['id']}", use_container_width=True):
                                        try:
                                            # Track install for each skill in pack
                                            for skill in pack_skills:
                                                db_market.track_install(skill['id'], user_id='streamlit_user')
                                            st.success(f"✅ Installed {len(pack_skills)} skills from {pack['name']}")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Installation failed: {e}")

                                with pack_act_col2:
                                    if st.button("✖️ Close", key=f"close_pack_{pack['id']}", use_container_width=True):
                                        st.session_state[f"view_pack_{pack['id']}"] = False
                                        st.rerun()

                                st.markdown("---")

                            st.markdown("---")

                else:
                    st.info("No skill packs available yet. Check back soon!")

                # Create custom pack section
                with st.expander("➕ Create Custom Pack"):
                    pack_name = st.text_input("Pack Name", key="new_pack_name")
                    pack_desc = st.text_area("Pack Description", key="new_pack_desc")
                    pack_icon = st.text_input("Icon (emoji)", value="📦", key="new_pack_icon")

                    # Skill selection
                    all_skills_for_pack = db.list_skills(active_only=True, limit=100)
                    skill_options = {s['tool_name']: s['id'] for s in all_skills_for_pack}

                    selected_skills = st.multiselect(
                        "Select Skills for Pack",
                        options=list(skill_options.keys()),
                        key="pack_skills_select"
                    )

                    # Pricing
                    pack_pricing = st.radio("Pricing Type", ["free", "paid"], key="pack_pricing")
                    pack_price = 0.0
                    if pack_pricing == "paid":
                        pack_price = st.number_input("Price ($)", min_value=0.0, value=9.99, key="pack_price")

                    if st.button("Create Pack", key="create_pack_btn"):
                        if pack_name and pack_desc and selected_skills:
                            try:
                                skill_ids = [skill_options[name] for name in selected_skills]
                                pack_id = db_market.create_skill_pack(
                                    name=pack_name,
                                    description=pack_desc,
                                    skill_ids=skill_ids,
                                    pricing_type=pack_pricing,
                                    price=pack_price,
                                    icon=pack_icon
                                )
                                st.success(f"✅ Created pack: {pack_name} (ID: {pack_id})")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to create pack: {e}")
                        else:
                            st.warning("Please fill in all fields and select at least one skill")

            except Exception as e:
                st.error(f"Skill packs error: {e}")

        st.divider()

        # Cost Optimization (Feature #2)
        st.markdown("### 💰 Cost Optimization")

        # Create tabs for different cost features
        cost_tab1, cost_tab2, cost_tab3 = st.tabs(["💵 Budget", "⚙️ Agents", "📊 Analytics"])

        with cost_tab1:
            st.markdown("#### Budget Management")

            # Get current session ID
            current_session_id = st.session_state.get('session_id', 'default_session')

            # Set session budget
            with st.expander("➕ Set Session Budget"):
                session_budget = st.number_input(
                    "Session Budget ($)",
                    min_value=0.0,
                    value=10.0,
                    step=1.0,
                    key="session_budget_input"
                )
                alert_threshold = st.slider(
                    "Alert Threshold (%)",
                    min_value=0,
                    max_value=100,
                    value=80,
                    key="alert_threshold_input"
                )
                if st.button("Set Budget", key="set_budget_btn"):
                    try:
                        budget_id = db_cost.set_budget(
                            budget_type='per_session',
                            budget_limit=session_budget,
                            alert_threshold=alert_threshold / 100
                        )
                        st.success(f"✅ Budget set: ${session_budget:.2f}")
                    except Exception as e:
                        st.error(f"Failed to set budget: {e}")

            # Display current session cost
            try:
                cost_summary = db_cost.get_session_cost_summary(current_session_id)

                # Main cost metrics
                col_cost1, col_cost2 = st.columns(2)
                with col_cost1:
                    total_cost = cost_summary.get('total_cost', 0.0)
                    st.metric("Total Cost", f"${total_cost:.4f}")

                with col_cost2:
                    call_count = cost_summary.get('call_count', 0)
                    st.metric("API Calls", call_count)

                # Budget status
                budget_info = cost_summary.get('budget_info')
                if budget_info:
                    budget_limit = budget_info['budget_limit']
                    current_spend = budget_info['current_spend']
                    percentage_used = budget_info['percentage_used']

                    st.progress(
                        min(percentage_used / 100, 1.0),
                        text=f"Budget Used: {percentage_used:.1f}% (${current_spend:.4f} / ${budget_limit:.2f})"
                    )

                    if budget_info['budget_exceeded']:
                        st.error("⚠️ Budget exceeded!")
                else:
                    st.info("No budget set for this session")

                # Token usage breakdown
                st.markdown("**Token Usage:**")
                token_col1, token_col2 = st.columns(2)
                with token_col1:
                    st.caption(f"Input: {cost_summary.get('total_input_tokens', 0):,}")
                with token_col2:
                    st.caption(f"Output: {cost_summary.get('total_output_tokens', 0):,}")

            except Exception as e:
                st.error(f"Cost tracking error: {e}")

            # Cost alerts
            try:
                alerts = db_cost.get_unacknowledged_alerts(current_session_id)
                if alerts:
                    st.markdown("**⚠️ Active Alerts:**")
                    for alert in alerts[:3]:  # Show top 3
                        alert_type = alert['alert_type']
                        message = alert['message']
                        alert_id = alert['id']

                        alert_container = st.container()
                        with alert_container:
                            alert_col1, alert_col2 = st.columns([4, 1])
                            with alert_col1:
                                if alert_type == 'budget_exceeded':
                                    st.error(message)
                                else:
                                    st.warning(message)
                            with alert_col2:
                                if st.button("✓", key=f"ack_alert_{alert_id}", help="Acknowledge"):
                                    db_cost.acknowledge_alert(alert_id)
                                    st.rerun()
            except Exception as e:
                st.caption(f"Alert check error: {e}")

        with cost_tab2:
            st.markdown("#### Agent Model Configuration")
            st.caption("Configure which model each agent uses")

            try:
                # Get current agent configurations
                agent_configs = db_cost.list_agent_configs()

                # Display current configurations
                st.markdown("**Current Configuration:**")
                for config in agent_configs:
                    agent_name = config['agent_name']
                    model_name = config['model_name']
                    max_tokens = config['max_tokens']
                    temperature = config['temperature']

                    with st.expander(f"{agent_name} - {model_name}"):
                        st.text(f"Model: {model_name}")
                        st.text(f"Max Tokens: {max_tokens}")
                        st.text(f"Temperature: {temperature}")

                        # Edit configuration
                        new_model = st.selectbox(
                            "Model",
                            ["gemini-2.0-flash-exp", "gemini-2.5-pro"],
                            index=0 if "flash" in model_name.lower() else 1,
                            key=f"model_{agent_name}"
                        )
                        new_max_tokens = st.number_input(
                            "Max Tokens",
                            min_value=1024,
                            max_value=32768,
                            value=max_tokens,
                            step=1024,
                            key=f"max_tokens_{agent_name}"
                        )
                        new_temperature = st.slider(
                            "Temperature",
                            min_value=0.0,
                            max_value=1.0,
                            value=float(temperature),
                            step=0.1,
                            key=f"temp_{agent_name}"
                        )

                        if st.button("Update", key=f"update_{agent_name}"):
                            try:
                                db_cost.set_agent_model(
                                    agent_name=agent_name,
                                    model_name=new_model,
                                    max_tokens=new_max_tokens,
                                    temperature=new_temperature
                                )
                                st.success(f"✅ Updated {agent_name}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Update failed: {e}")

                # Model pricing info
                st.markdown("**Model Pricing:**")
                st.caption("💚 gemini-2.0-flash-exp: FREE (experimental)")
                st.caption("💚 gemini-2.5-pro: FREE (experimental)")
                st.caption("⚠️ Pricing may change when models go to production")

            except Exception as e:
                st.error(f"Agent config error: {e}")

        with cost_tab3:
            st.markdown("#### Cost Analytics")

            # Time period selector
            days = st.selectbox(
                "Time Period",
                [1, 7, 14, 30],
                index=1,
                format_func=lambda x: f"Last {x} day{'s' if x > 1 else ''}",
                key="analytics_days"
            )

            try:
                analytics = db_cost.get_cost_analytics(days=days)

                # Total metrics
                st.markdown(f"**Last {days} Day{'s' if days > 1 else ''}:**")
                metric_col1, metric_col2, metric_col3 = st.columns(3)

                with metric_col1:
                    st.metric("Total Cost", f"${analytics['total_cost']:.4f}")
                with metric_col2:
                    st.metric("Total Calls", f"{analytics['total_calls']:,}")
                with metric_col3:
                    st.metric("Total Tokens", f"{analytics['total_tokens']:,}")

                # Cost by agent
                if analytics['by_agent']:
                    st.markdown("**Cost by Agent:**")
                    for agent_stat in analytics['by_agent']:
                        agent_name = agent_stat['agent_name']
                        cost = agent_stat['cost']
                        calls = agent_stat['calls']
                        tokens = agent_stat['tokens']

                        st.text(f"{agent_name}: ${cost:.4f} ({calls} calls, {tokens:,} tokens)")

                # Cost by model
                if analytics['by_model']:
                    st.markdown("**Cost by Model:**")
                    for model_stat in analytics['by_model']:
                        model_name = model_stat['model_name']
                        cost = model_stat['cost']
                        calls = model_stat['calls']

                        st.text(f"{model_name}: ${cost:.4f} ({calls} calls)")

                # Cache statistics
                cache_stats = db_cost.get_cache_stats()
                if cache_stats['total_entries'] > 0:
                    st.markdown("**Cache Performance:**")
                    st.text(f"Cached Responses: {cache_stats['total_entries']}")
                    st.text(f"Cache Hits: {cache_stats['total_hits']}")
                    st.text(f"Tokens Saved: {cache_stats['total_tokens_saved']:,}")

            except Exception as e:
                st.error(f"Analytics error: {e}")

        st.divider()

        # Advanced Orchestration (Feature #10)
        st.markdown("### 🔄 Advanced Orchestration")

        orch_tab1, orch_tab2, orch_tab3 = st.tabs(["🔀 Workflows", "📋 Templates", "🎯 Routing"])

        with orch_tab1:
            st.markdown("#### Workflow Management")

            try:
                # List workflows
                workflows = db_orch.list_workflows(active_only=True)

                if workflows:
                    workflow_names = {w['name']: w['id'] for w in workflows}
                    selected_workflow_name = st.selectbox(
                        "Select Workflow",
                        ["Create New..."] + list(workflow_names.keys()),
                        key="workflow_select"
                    )

                    if selected_workflow_name != "Create New...":
                        workflow_id = workflow_names[selected_workflow_name]
                        workflow = db_orch.get_workflow(workflow_id)

                        if workflow:
                            st.markdown(f"**{workflow['name']}**")
                            st.caption(workflow['description'])
                            st.text(f"Type: {workflow['workflow_type']}")
                            st.text(f"Steps: {len(workflow.get('steps', []))}")

                            # Show steps
                            if workflow.get('steps'):
                                with st.expander("View Steps"):
                                    for step in workflow['steps']:
                                        st.text(f"Step {step['step_number']}: {step['agent_name']}")
                                        if step['task_description']:
                                            st.caption(step['task_description'])
                else:
                    st.info("No workflows created yet")

                # Create new workflow
                with st.expander("➕ Create Workflow"):
                    wf_name = st.text_input("Workflow Name", key="new_wf_name")
                    wf_desc = st.text_area("Description", key="new_wf_desc")
                    wf_type = st.selectbox("Type", ["sequential", "parallel", "conditional", "hybrid"], key="new_wf_type")

                    if st.button("Create", key="create_wf_btn"):
                        if wf_name:
                            try:
                                wf_id = db_orch.create_workflow(
                                    name=wf_name,
                                    description=wf_desc,
                                    workflow_type=wf_type,
                                    config={"type": wf_type, "steps": []},
                                    created_by="streamlit_user"
                                )
                                st.success(f"✅ Created workflow: {wf_name} (ID: {wf_id})")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed: {e}")

            except Exception as e:
                st.error(f"Workflow error: {e}")

        with orch_tab2:
            st.markdown("#### Workflow Templates")

            try:
                templates = db_orch.list_workflow_templates()

                if templates:
                    for template in templates[:5]:  # Show top 5
                        with st.expander(f"{template['name']} - {template['complexity_level']}"):
                            st.text(template['description'])
                            st.caption(f"Category: {template.get('category', 'N/A')}")
                            st.caption(f"Use case: {template.get('use_case', 'N/A')}")
                            st.caption(f"Duration: {template.get('estimated_duration', 'N/A')}")

                            if st.button("Use Template", key=f"use_template_{template['id']}"):
                                st.info("Template ready to use via API")
                else:
                    st.info("No templates available")

            except Exception as e:
                st.error(f"Template error: {e}")

        with orch_tab3:
            st.markdown("#### Smart Task Routing")

            try:
                # Show agent specializations
                agents = ["Planner", "Coder", "FileHandler", "Reviewer", "SkillGenerator", "Executor"]

                selected_agent = st.selectbox("View Agent Specializations", agents, key="agent_spec_select")

                if selected_agent:
                    specs = db_orch.get_agent_specializations(selected_agent)

                    if specs:
                        st.markdown(f"**{selected_agent} Specializations:**")
                        for spec in specs:
                            prof_stars = "⭐" * spec['proficiency_level']
                            st.text(f"{spec['specialization_area']}: {prof_stars}")
                            st.caption(f"Success Rate: {spec['success_rate']*100:.0f}% | Tasks: {spec['task_count']}")

            except Exception as e:
                st.error(f"Routing error: {e}")

        st.divider()

        # Skill Testing & Quality (Feature #11)
        st.markdown("### 🧪 Testing & Quality")

        test_tab1, test_tab2, test_tab3 = st.tabs(["🔍 Safety", "📊 Quality", "🏆 Leaderboard"])

        with test_tab1:
            st.markdown("#### Safety Analysis")

            try:
                # Get skills for testing
                all_skills = db.list_skills(active_only=True, limit=100)

                if all_skills:
                    skill_names = {s['tool_name']: s for s in all_skills}
                    selected_skill = st.selectbox(
                        "Select Skill to Analyze",
                        list(skill_names.keys()),
                        key="safety_skill_select"
                    )

                    if selected_skill and st.button("Run Safety Check", key="run_safety"):
                        skill = skill_names[selected_skill]
                        try:
                            risk_level, issues = db_test.check_code_safety(
                                skill_id=skill['id'],
                                code=skill['code']
                            )

                            # Display results
                            risk_colors = {
                                "none": "🟢",
                                "low": "🟡",
                                "medium": "🟠",
                                "high": "🔴",
                                "critical": "🚨"
                            }

                            st.markdown(f"**Risk Level:** {risk_colors.get(risk_level, '⚪')} {risk_level.upper()}")
                            st.metric("Issues Found", len(issues))

                            if issues:
                                st.markdown("**Security Issues:**")
                                for issue in issues[:5]:  # Show top 5
                                    st.warning(f"Line {issue['line']}: {issue['pattern']}")
                                    st.caption(issue['recommendation'])
                            else:
                                st.success("✅ No safety issues detected!")

                        except Exception as e:
                            st.error(f"Safety check failed: {e}")

            except Exception as e:
                st.error(f"Safety analysis error: {e}")

        with test_tab2:
            st.markdown("#### Quality Scores")

            try:
                all_skills = db.list_skills(active_only=True, limit=100)

                if all_skills:
                    skill_names = {s['tool_name']: s for s in all_skills}
                    selected_skill_q = st.selectbox(
                        "Select Skill for Quality Report",
                        list(skill_names.keys()),
                        key="quality_skill_select"
                    )

                    if selected_skill_q and st.button("Calculate Quality Score", key="calc_quality"):
                        skill = skill_names[selected_skill_q]
                        try:
                            scores = db_test.calculate_quality_score(skill_id=skill['id'])

                            # Display scores
                            st.markdown("**Quality Breakdown:**")

                            score_col1, score_col2 = st.columns(2)
                            with score_col1:
                                st.metric("Overall Score", f"{scores['overall_score']:.1f}/100")
                                st.metric("Test Score", f"{scores['test_score']:.1f}/100")
                            with score_col2:
                                st.metric("Safety Score", f"{scores['safety_score']:.1f}/100")
                                st.metric("Documentation", f"{scores['documentation_score']:.1f}/100")

                            # Certification badge
                            cert_level = scores['certification_level']
                            cert_badges = {
                                "platinum": "🏆 PLATINUM",
                                "gold": "🥇 GOLD",
                                "silver": "🥈 SILVER",
                                "bronze": "🥉 BRONZE",
                                "uncertified": "⚪ UNCERTIFIED"
                            }

                            st.markdown(f"**Certification:** {cert_badges.get(cert_level, cert_level.upper())}")

                        except Exception as e:
                            st.error(f"Quality calculation failed: {e}")

            except Exception as e:
                st.error(f"Quality scoring error: {e}")

        with test_tab3:
            st.markdown("#### Quality Leaderboard")

            try:
                # Get leaderboard from database
                import sqlite3
                conn = sqlite3.connect(db_test.DB_PATH)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT qs.overall_score, qs.certification_level, s.tool_name
                    FROM quality_scores qs
                    JOIN skills s ON qs.skill_id = s.id
                    ORDER BY qs.overall_score DESC
                    LIMIT 10
                """)

                leaderboard = cursor.fetchall()
                conn.close()

                if leaderboard:
                    st.markdown("**Top 10 Skills by Quality:**")
                    for idx, entry in enumerate(leaderboard, 1):
                        cert_emoji = {
                            "platinum": "🏆",
                            "gold": "🥇",
                            "silver": "🥈",
                            "bronze": "🥉",
                            "uncertified": "⚪"
                        }.get(entry['certification_level'], "")

                        st.text(f"{idx}. {cert_emoji} {entry['tool_name']} - {entry['overall_score']:.1f}/100")
                else:
                    st.info("No quality scores calculated yet")

            except Exception as e:
                st.error(f"Leaderboard error: {e}")

        st.divider()

        # Integration Hub (Feature #16)
        st.markdown("### 🔗 Integration Hub")

        import database_integrations as db_int

        int_tab1, int_tab2, int_tab3, int_tab4 = st.tabs(["🐙 GitHub", "💬 Slack", "🔗 Webhooks", "📦 Export/Import"])

        with int_tab1:
            st.markdown("#### GitHub Integration")

            try:
                # List existing GitHub integrations
                github_integrations = db_int.list_integrations(integration_type="github", enabled_only=True)

                if github_integrations:
                    selected_github = st.selectbox(
                        "Select GitHub Integration",
                        [i['name'] for i in github_integrations],
                        key="github_int_select"
                    )

                    if selected_github:
                        integration = next(i for i in github_integrations if i['name'] == selected_github)

                        # List repositories
                        repos = db_int.list_github_repos(integration['id'], active_only=True)

                        if repos:
                            st.markdown("**Connected Repositories:**")
                            for repo in repos:
                                with st.expander(f"📁 {repo['repo_full_name']}"):
                                    st.text(f"Status: {repo['sync_status']}")
                                    st.text(f"Skills Imported: {repo['skills_imported']}")
                                    st.text(f"Last Sync: {repo['last_sync_at'] or 'Never'}")

                                    if st.button(f"Sync Now", key=f"sync_repo_{repo['id']}"):
                                        with st.spinner("Syncing..."):
                                            success, message = db_int.sync_github_repo(repo['id'])
                                            if success:
                                                st.success(message)
                                            else:
                                                st.error(message)
                        else:
                            st.info("No repositories connected yet")

                        # Add new repository
                        with st.expander("➕ Add Repository"):
                            repo_name = st.text_input("Repository (owner/repo)", key="new_repo_name")
                            repo_url = st.text_input("Repository URL", key="new_repo_url")

                            if st.button("Add Repository", key="add_repo_btn"):
                                if repo_name and repo_url:
                                    repo_id = db_int.add_github_repo(
                                        integration_id=integration['id'],
                                        repo_full_name=repo_name,
                                        repo_url=repo_url
                                    )
                                    st.success(f"Repository added! ID: {repo_id}")
                                    st.rerun()
                else:
                    st.info("No GitHub integrations configured")
                    with st.expander("➕ Create GitHub Integration"):
                        st.markdown("Create a GitHub integration via API:")
                        st.code("""
POST /api/v1/integrations
{
  "integration_type": "github",
  "name": "My GitHub",
  "config": {},
  "credentials": {"access_token": "YOUR_TOKEN"}
}
                        """, language="json")

            except Exception as e:
                st.error(f"GitHub integration error: {e}")

        with int_tab2:
            st.markdown("#### Slack Notifications")

            try:
                slack_integrations = db_int.list_integrations(integration_type="slack", enabled_only=True)

                if slack_integrations:
                    selected_slack = st.selectbox(
                        "Select Slack Integration",
                        [i['name'] for i in slack_integrations],
                        key="slack_int_select"
                    )

                    if selected_slack:
                        integration = next(i for i in slack_integrations if i['name'] == selected_slack)

                        # List channels
                        channels = db_int.list_slack_channels(integration['id'], active_only=True)

                        if channels:
                            st.markdown("**Connected Channels:**")
                            for channel in channels:
                                with st.expander(f"💬 {channel['channel_name']}"):
                                    st.text(f"Channel ID: {channel['channel_id']}")
                                    st.text(f"Workspace: {channel['workspace_name'] or 'N/A'}")
                                    st.text(f"Total Notifications: {channel['total_notifications']}")
                                    st.text(f"Last Notification: {channel['last_notification_at'] or 'Never'}")

                                    # Send test notification
                                    if st.button("Send Test", key=f"test_slack_{channel['id']}"):
                                        success = db_int.send_slack_notification(
                                            channel_id=channel['id'],
                                            event_type="test",
                                            message="🧪 Test notification from Integration Hub!"
                                        )
                                        if success:
                                            st.success("Test notification sent!")
                                        else:
                                            st.error("Failed to send notification")
                        else:
                            st.info("No Slack channels connected yet")
                else:
                    st.info("No Slack integrations configured")
                    with st.expander("➕ Create Slack Integration"):
                        st.markdown("Create a Slack integration via API:")
                        st.code("""
POST /api/v1/integrations
{
  "integration_type": "slack",
  "name": "My Slack",
  "config": {},
  "credentials": {"webhook_url": "YOUR_WEBHOOK_URL"}
}
                        """, language="json")

            except Exception as e:
                st.error(f"Slack integration error: {e}")

        with int_tab3:
            st.markdown("#### Webhook Endpoints")

            try:
                webhooks = db_int.list_webhooks(active_only=True)

                if webhooks:
                    st.markdown("**Active Webhooks:**")
                    for webhook in webhooks[:10]:
                        with st.expander(f"🔗 {webhook['endpoint_url']}"):
                            st.text(f"Webhook ID: {webhook['id']}")
                            st.text(f"Events: {', '.join(webhook['events'])}")
                            st.text(f"Total Deliveries: {webhook['total_deliveries']}")
                            st.text(f"Successful: {webhook['successful_deliveries']}")
                            st.text(f"Failed: {webhook['failed_deliveries']}")
                            st.text(f"Last Triggered: {webhook['last_triggered_at'] or 'Never'}")

                            # Test webhook
                            if st.button("Trigger Test", key=f"test_webhook_{webhook['id']}"):
                                delivery_id = db_int.trigger_webhook(
                                    webhook_id=webhook['id'],
                                    event_type="test",
                                    payload={"message": "Test webhook trigger"}
                                )
                                st.success(f"Webhook triggered! Delivery ID: {delivery_id}")
                else:
                    st.info("No webhooks configured")

                # Create new webhook
                with st.expander("➕ Create Webhook"):
                    st.markdown("Create a webhook via API:")
                    st.code("""
POST /api/v1/integrations/webhooks
{
  "events": ["skill_created", "workflow_completed"],
  "description": "My webhook"
}
                    """, language="json")

            except Exception as e:
                st.error(f"Webhook error: {e}")

        with int_tab4:
            st.markdown("#### Export/Import")

            try:
                # Export section
                st.markdown("**Export Data:**")

                export_scope = st.selectbox(
                    "What to export?",
                    ["skills", "workflows", "integrations", "all"],
                    key="export_scope"
                )

                export_format = st.selectbox(
                    "Export format?",
                    ["json", "yaml", "zip"],
                    key="export_format"
                )

                if st.button("Create Export", key="create_export_btn"):
                    job_id = db_int.create_export_job(
                        job_type="export",
                        export_format=export_format,
                        scope=export_scope
                    )
                    st.success(f"Export job created! Job ID: {job_id}")
                    st.info("Check export status via API: GET /api/v1/integrations/export/{job_id}")

                st.divider()

                # Recent export jobs
                st.markdown("**Recent Export Jobs:**")
                export_jobs = db_int.list_export_jobs(job_type="export", limit=10)

                if export_jobs:
                    for job in export_jobs:
                        status_emoji = {
                            "pending": "⏳",
                            "processing": "⚙️",
                            "completed": "✅",
                            "failed": "❌"
                        }.get(job['status'], "")

                        st.text(f"{status_emoji} Job #{job['id']}: {job['scope']} as {job['export_format']} - {job['status']}")
                        if job['file_path']:
                            st.caption(f"File: {job['file_path']} ({job['file_size_bytes']} bytes)")
                else:
                    st.info("No export jobs yet")

                st.divider()

                # Import section
                st.markdown("**Import Data:**")
                st.info("Import skills from JSON via API: POST /api/v1/integrations/import/skills")

            except Exception as e:
                st.error(f"Export/Import error: {e}")

        st.divider()

        # Session stats
        st.markdown("### 📈 Session Stats")
        st.metric("Total Messages", len(st.session_state.messages))
        st.metric("Tool Calls", len(st.session_state.tool_calls))
        st.metric("Team Status", "🟢 Active" if st.session_state.chat_active else "🔴 Inactive")

        # Uploaded files count
        if st.session_state.uploaded_files:
            st.metric("Uploaded Files", len(st.session_state.uploaded_files))

        # Dynamic skills
        if st.session_state.filehandler_agent and hasattr(st.session_state.filehandler_agent, 'dynamic_tools'):
            dynamic_count = len(st.session_state.filehandler_agent.dynamic_tools)
            if dynamic_count > 0:
                st.metric("Dynamic Skills", dynamic_count)
                with st.expander("🧠 Generated Skills"):
                    for skill in st.session_state.filehandler_agent.dynamic_tools:
                        st.text(f"• {skill['name']}")


def render_chat_interface():
    """Render main chat interface."""
    st.title("🤖 AutoGen Multi-Agent System - Production Edition")
    st.markdown("*5 Agents | RQ Distributed Execution | Real-Time Cost Monitoring | Dynamic Skill Generation*")

    # Cost alert banner
    if st.session_state.cost_tracking["total_cost"] > COST_ALERT_THRESHOLD:
        st.error(f"""
        ⚠️ **COST ALERT**: Session cost ${st.session_state.cost_tracking['total_cost']:.4f}
        exceeds threshold of ${COST_ALERT_THRESHOLD:.2f}!

        Consider resetting the session or monitoring usage.
        """)

    # Display chat messages
    chat_container = st.container()
    with chat_container:
        for idx, message in enumerate(st.session_state.messages):
            agent = message.get("agent", "Unknown")
            content = message.get("content", "")
            role = message.get("role", "assistant")
            image_path = message.get("image_path")

            with st.chat_message(role, avatar="🤖" if role == "assistant" else "👤"):
                # Display image if present
                if image_path:
                    try:
                        st.image(image_path, caption=content, use_container_width=True)
                    except:
                        st.markdown(content)
                else:
                    st.markdown(content)

    # HITL Approval
    if st.session_state.pending_approval:
        st.warning("⚠️ Human Approval Required")
        approval = st.session_state.pending_approval

        st.markdown("**Action:** " + approval.get("action", "Code Execution"))

        code = approval.get("code", approval.get("action"))
        if code:
            language = approval.get("language", "python")
            st.code(code, language=language)

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Approve", use_container_width=True, type="primary"):
                st.session_state.approval_granted = True
                st.session_state.pending_approval = None
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "✅ **User approved the action.**",
                    "agent": "System",
                    "timestamp": datetime.now().isoformat()
                })
                st.rerun()

        with col2:
            if st.button("❌ Reject", use_container_width=True):
                st.session_state.approval_granted = False
                st.session_state.pending_approval = None
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "❌ **User rejected the action.**",
                    "agent": "System",
                    "timestamp": datetime.now().isoformat()
                })
                st.rerun()

    # File uploader for multimodal input
    st.markdown("### 📎 Upload Files (Optional)")
    uploaded_files = st.file_uploader(
        "Upload images, PDFs, or documents for analysis",
        type=['png', 'jpg', 'jpeg', 'pdf', 'docx', 'txt', 'md', 'py', 'json', 'csv'],
        accept_multiple_files=True,
        help="Images will be analyzed, documents will be ingested into knowledge base"
    )

    if uploaded_files:
        # Process new uploads
        for uploaded_file in uploaded_files:
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"

            # Check if already processed
            already_processed = any(f['id'] == file_id for f in st.session_state.uploaded_files)

            if not already_processed and st.session_state.chat_active:
                # Save file temporarily
                import tempfile
                import os

                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_path = tmp_file.name

                # Determine file type and process
                file_type = uploaded_file.type
                file_name = uploaded_file.name

                if file_type.startswith('image/'):
                    # Process image with tool_analyze_image
                    st.session_state.messages.append({
                        "role": "user",
                        "content": f"🖼️ **Uploaded image:** {file_name}",
                        "agent": "User",
                        "timestamp": datetime.now().isoformat(),
                        "image_path": tmp_path
                    })

                    # Analyze image
                    with st.spinner(f"Analyzing {file_name}..."):
                        analysis_result = tool_analyze_image(tmp_path)

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"**Image Analysis ({file_name}):**\n\n{analysis_result}",
                        "agent": "Vision",
                        "timestamp": datetime.now().isoformat()
                    })

                else:
                    # Ingest document into ChromaDB
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"📄 **Ingesting document:** {file_name}",
                        "agent": "System",
                        "timestamp": datetime.now().isoformat()
                    })

                    ingest_result = tool_ingest_document(tmp_path)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"**Document Ingested ({file_name}):**\n\n{ingest_result}",
                        "agent": "FileHandler",
                        "timestamp": datetime.now().isoformat()
                    })

                # Track uploaded file
                st.session_state.uploaded_files.append({
                    'id': file_id,
                    'name': file_name,
                    'type': file_type,
                    'size': uploaded_file.size,
                    'path': tmp_path,
                    'timestamp': datetime.now().isoformat()
                })

                # Clean up temp file for non-image files
                if not file_type.startswith('image/'):
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass

        # Show uploaded files
        if st.session_state.uploaded_files:
            with st.expander(f"📁 Uploaded Files ({len(st.session_state.uploaded_files)})", expanded=False):
                for file_info in st.session_state.uploaded_files:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.text(f"📄 {file_info['name']}")
                    with col2:
                        size_kb = file_info['size'] / 1024
                        st.caption(f"{size_kb:.1f} KB")
                    with col3:
                        file_type_icon = "🖼️" if file_info['type'].startswith('image/') else "📄"
                        st.caption(file_type_icon)

    st.divider()

    # Chat input
    if prompt := st.chat_input("Describe your coding task...", disabled=not st.session_state.chat_active):
        if not st.session_state.team:
            st.error("Please initialize the team first!")
            return

        st.session_state.messages.append({
            "role": "user",
            "content": prompt,
            "agent": "User",
            "timestamp": datetime.now().isoformat()
        })

        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        with st.spinner("🤔 5 agents collaborating with distributed execution..."):
            asyncio.run(run_team(prompt))


async def run_team(task: str):
    """Run the agent team on a task."""
    try:
        logger.info(f"Starting team run for task: {task[:100]}...")

        team = st.session_state.team
        initial_message = TextMessage(content=task, source="User")

        result = await team.run(task=initial_message)

        logger.info(f"Team run completed. Messages: {len(result.messages)}")

        # Add completion summary with cost
        cost = st.session_state.cost_tracking["total_cost"]
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"✅ **Collaboration complete!** Messages: {len(result.messages)} | Cost: ${cost:.4f}",
            "agent": "System",
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error running team: {e}", exc_info=True)
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"❌ **Error:** {str(e)}\n\nPlease check your API key and try again.",
            "agent": "System",
            "timestamp": datetime.now().isoformat()
        })

    finally:
        # Auto-save conversation after each interaction
        try:
            if st.session_state.messages:
                if "current_session_id" not in st.session_state:
                    st.session_state.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

                first_msg = next((m for m in st.session_state.messages if m['role'] == 'user'), None)
                title = first_msg['content'][:50] + "..." if first_msg else "Untitled Session"

                db.save_conversation(
                    session_id=st.session_state.current_session_id,
                    title=title,
                    messages=st.session_state.messages,
                    cost_tracking=st.session_state.cost_tracking
                )
                logger.info(f"Auto-saved conversation: {st.session_state.current_session_id}")
        except Exception as save_error:
            logger.error(f"Auto-save failed: {save_error}")

        st.rerun()


# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main application entry point."""
    st.set_page_config(
        page_title="AutoGen Production System",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    initialize_session_state()
    render_sidebar()
    render_chat_interface()

    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray; font-size: 0.8em;'>
        🤖 AutoGen v0.4 Production | 🧠 5 Agents + Skill Generation | 🚀 RQ Distributed Execution | 💰 Real-Time Cost Tracking
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
