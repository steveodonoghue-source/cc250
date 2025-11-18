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
from autogen_agentchat.messages import (
    ChatMessage,
    TextMessage,
    ToolCallMessage,
    ToolCallResultMessage,
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
    """Tool #1: Web search (RAG capability)."""
    logger.info(f"🔍 Tool called: web_search('{query}')")

    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "web_search",
        "query": query,
        "timestamp": datetime.now().isoformat()
    })

    result = f"""
    🔍 Web Search Results for: "{query}"

    [Simulated Results - Configure real search API for production]

    Top Results:
    1. Official Documentation - Latest best practices and API references
    2. Stack Overflow - Community solutions and common patterns
    3. GitHub Repositories - Implementation examples and code samples
    4. Recent Blog Posts - Current trends and recommendations

    Suggested Next Steps:
    - Verify information against official documentation
    - Check for recent security advisories
    - Review community consensus on best practices

    To enable real search, configure one of:
    - Google Custom Search: https://programmablesearchengine.google.com/
    - Serper API: https://serper.dev
    - Tavily: https://tavily.com
    """

    return result


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
        elif isinstance(response, ToolCallMessage):
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
- tool_read_document: Read specifications
- tool_analyze_image: Analyze diagrams
- tool_get_current_datetime: Get timestamps
- tool_validate_json: Validate your TaskPlan

Always structure your plan using the TaskPlan schema and validate it."""

    model_client = get_gemini_client("gemini-2.5-pro", agent_name="Planner")

    tools = [
        FunctionTool(tool_web_search, description="Search the web for information"),
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


# ============================================================================
# Team Setup
# ============================================================================

def create_team() -> SelectorGroupChat:
    """Create SelectorGroupChat with 5 agents including SkillGenerator."""
    logger.info("Creating 5-agent team with cost tracking and skill generation...")

    planner = create_planner_agent()
    coder = create_coder_agent()
    reviewer = create_reviewer_agent()
    filehandler = create_filehandler_agent()
    skillgenerator = create_skill_generator_agent()

    # Use Gemini Pro for team selector
    selector_client = get_gemini_client("gemini-2.5-pro", agent_name="TeamSelector")

    team = SelectorGroupChat(
        participants=[planner, coder, reviewer, filehandler, skillgenerator],
        model_client=selector_client,
        termination_condition=lambda msg: (
            "APPROVED" in str(msg.content).upper() or
            "TERMINATE" in str(msg.content).upper() or
            (isinstance(msg, TextMessage) and '"approved": true' in msg.content.lower())
        ),
        max_turns=35  # More turns for skill generation workflows
    )

    # Store FileHandler reference for potential skill registration
    st.session_state.filehandler_agent = filehandler

    logger.info("Team created with 5 agents, cost tracking, and dynamic skill generation")
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


def render_sidebar():
    """Render sidebar with configuration and cost monitoring."""
    with st.sidebar:
        st.title("⚙️ Configuration")

        # Model info
        st.markdown("### 🤖 Active Agents")
        st.markdown("""
        - **Planner**: `gemini-2.5-pro` 🧠
        - **Coder**: `gemini-2.5-flash` ⚡
        - **Reviewer**: `gemini-2.5-pro` 🔍
        - **FileHandler**: `gemini-2.5-flash` 📁
        - **SkillGenerator**: `gemini-2.5-pro` 🧠 **NEW!**
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

        # Session stats
        st.markdown("### 📊 Session Stats")
        st.metric("Messages", len(st.session_state.messages))
        st.metric("Tool Calls", len(st.session_state.tool_calls))
        st.metric("Team Status", "🟢 Active" if st.session_state.chat_active else "🔴 Inactive")

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

            with st.chat_message(role, avatar="🤖" if role == "assistant" else "👤"):
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
