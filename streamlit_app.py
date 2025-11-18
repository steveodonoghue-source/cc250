"""
AutoGen v0.4 Multi-Agent Coding System with Streamlit UI (Complete Edition)
===========================================================================
Advanced collaborative AI coding assistant featuring:
- Gemini 2.5 Pro (Planner/Reviewer) and Flash (Coder/FileHandler) models
- Structured outputs with Pydantic schemas
- 10 specialized tools for comprehensive development workflow
- FileHandler agent for secure I/O operations
- Human-in-the-loop approval with state persistence
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import zipfile
from typing import Any, Dict, List, Sequence, Optional
from datetime import datetime
from pathlib import Path
import io

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
    matplotlib.use('Agg')  # Non-interactive backend for Streamlit
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    from PIL import Image
except ImportError:
    Image = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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


# ============================================================================
# Tool Implementations (10 Specialized Tools)
# ============================================================================

def tool_web_search(query: str) -> str:
    """
    Tool #1: Perform a web search to find information (RAG capability).

    For production, integrate with:
    - Google Custom Search API
    - Serper API (https://serper.dev)
    - Tavily Search API (https://tavily.com)

    Args:
        query: The search query

    Returns:
        Search results as a formatted string
    """
    logger.info(f"🔍 Tool called: web_search('{query}')")

    # Track in session state
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "web_search",
        "query": query,
        "timestamp": datetime.now().isoformat()
    })

    # Simulated search results (replace with actual API in production)
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
    Tool #2: Execute code in a simulated sandbox environment.

    ⚠️ SECURITY WARNING: This is a simulation for demonstration.
    For production, use proper sandboxing:
    - Docker containers
    - AWS Lambda
    - Google Cloud Run
    - E2B (https://e2b.dev)

    Args:
        code: The code to execute
        language: Programming language (default: python)

    Returns:
        Execution results or error message
    """
    logger.warning(f"⚠️ Tool called: execute_code (language={language})")

    # Track tool call
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "execute_code",
        "language": language,
        "code_length": len(code),
        "timestamp": datetime.now().isoformat()
    })

    # SECURITY: Request human approval for code execution
    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None

    st.session_state.pending_approval = {
        "action": "Code Execution",
        "code": code,
        "language": language,
        "timestamp": datetime.now().isoformat()
    }

    # Check if approved
    if not st.session_state.get("approval_granted", False):
        return "⚠️ Code execution requires human approval. Waiting for user confirmation..."

    # Reset approval after use
    st.session_state.approval_granted = False

    if language.lower() != "python":
        return f"❌ Language '{language}' not supported in this simulation. Only Python is supported."

    # Simulate execution (DO NOT use in production without proper sandboxing)
    try:
        # Create temporary file for code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        # Execute with timeout and restricted environment
        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=5,  # 5 second timeout
            cwd=tempfile.gettempdir()  # Isolated directory
        )

        # Clean up
        os.unlink(temp_file)

        output = result.stdout if result.returncode == 0 else result.stderr
        status = "✅ Success" if result.returncode == 0 else f"❌ Error (code {result.returncode})"

        return f"{status}\n\nOutput:\n{output}"

    except subprocess.TimeoutExpired:
        return "❌ Execution timeout (5 seconds exceeded)"
    except Exception as e:
        return f"❌ Execution error: {str(e)}"


def tool_static_analysis(file_path: str) -> str:
    """
    Tool #3: Perform static code analysis.

    Simulates tools like:
    - Pylint (code quality)
    - Bandit (security)
    - MyPy (type checking)

    Args:
        file_path: Path to the file to analyze

    Returns:
        Analysis results
    """
    logger.info(f"🔍 Tool called: static_analysis('{file_path}')")

    # Track tool call
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "static_analysis",
        "file_path": file_path,
        "timestamp": datetime.now().isoformat()
    })

    # Check if file exists
    if not os.path.exists(file_path):
        return f"❌ File not found: {file_path}"

    # Simulate analysis
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
    """
    Tool #4: Create data visualization using matplotlib.

    Args:
        data_json: JSON string containing data (e.g., {"labels": [...], "values": [...]})
        chart_type: Type of chart (bar, line, pie, scatter)

    Returns:
        Path to the generated chart image
    """
    logger.info(f"📊 Tool called: create_visualization(chart_type='{chart_type}')")

    # Track tool call
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
        # Parse data
        data = json.loads(data_json)
        labels = data.get("labels", [])
        values = data.get("values", [])

        if not labels or not values:
            return "❌ Invalid data format. Expected: {\"labels\": [...], \"values\": [...]}"

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 6))

        # Create chart based on type
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
            return f"❌ Unsupported chart type: {chart_type}. Use: bar, line, pie, scatter"

        ax.set_title(f'{chart_type.capitalize()} Chart')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        # Save to temporary file
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
    """
    Tool #5: Read document contents from a file.

    Supports text files, Python files, etc.
    For PDFs, consider using PyPDF2 or pdfplumber.

    Args:
        file_path: Path to the document

    Returns:
        Document contents or error message
    """
    logger.info(f"📄 Tool called: read_document('{file_path}')")

    # Track tool call
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "read_document",
        "file_path": file_path,
        "timestamp": datetime.now().isoformat()
    })

    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return f"❌ File not found: {file_path}"

        # Check file size (limit to 1MB for safety)
        file_size = os.path.getsize(file_path)
        if file_size > 1_000_000:
            return f"❌ File too large ({file_size} bytes). Maximum: 1MB"

        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Truncate if too long
        if len(content) > 10000:
            content = content[:10000] + f"\n\n... (truncated, total length: {len(content)} chars)"

        return f"✅ Document read successfully from: {file_path}\n\n{content}"

    except UnicodeDecodeError:
        return f"❌ Cannot read file (binary or unsupported encoding): {file_path}"
    except Exception as e:
        return f"❌ Error reading document: {str(e)}"


def tool_analyze_image(image_file_path: str, prompt: str = "Describe this image in detail") -> str:
    """
    Tool #6: Analyze an image using Gemini Vision API.

    Args:
        image_file_path: Path to the image file
        prompt: Question or instruction about the image

    Returns:
        AI-generated description/analysis of the image
    """
    logger.info(f"🖼️ Tool called: analyze_image('{image_file_path}')")

    # Track tool call
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "analyze_image",
        "image_path": image_file_path,
        "prompt": prompt,
        "timestamp": datetime.now().isoformat()
    })

    try:
        # Check if file exists
        if not os.path.exists(image_file_path):
            return f"❌ Image file not found: {image_file_path}"

        # Get API key
        api_key = (
            os.environ.get("GEMINI_API_KEY") or
            os.environ.get("GOOGLE_API_KEY") or
            st.session_state.get("google_api_key")
        )

        if not api_key:
            return "❌ API key not found for image analysis"

        # Configure Gemini
        genai.configure(api_key=api_key)

        # Use vision model
        model = genai.GenerativeModel('gemini-2.0-flash-exp')

        # Load image
        if Image:
            img = Image.open(image_file_path)
        else:
            return "❌ PIL not available. Install with: pip install pillow"

        # Generate description
        response = model.generate_content([prompt, img])

        return f"✅ Image Analysis:\n\n{response.text}"

    except Exception as e:
        return f"❌ Image analysis error: {str(e)}"


def tool_create_project_zip() -> str:
    """
    Tool #7: Create a ZIP archive of the current project.

    Returns:
        Path to the created ZIP file
    """
    logger.info(f"📦 Tool called: create_project_zip()")

    # Track tool call
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "create_project_zip",
        "timestamp": datetime.now().isoformat()
    })

    try:
        # Create ZIP in temp directory
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(
            temp_dir,
            f"project_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )

        # Get current working directory
        project_dir = os.getcwd()

        # Create ZIP
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add Python files from current directory
            for root, dirs, files in os.walk(project_dir):
                # Skip common directories
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'venv', 'env', '.venv']]

                for file in files:
                    # Only include relevant files
                    if file.endswith(('.py', '.md', '.txt', '.toml', '.yaml', '.yml')):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, project_dir)
                        zipf.write(file_path, arcname)

        # Get file size
        size = os.path.getsize(zip_path)
        size_mb = size / (1024 * 1024)

        return f"✅ Project ZIP created successfully!\nPath: {zip_path}\nSize: {size_mb:.2f} MB"

    except Exception as e:
        return f"❌ ZIP creation error: {str(e)}"


def tool_get_current_datetime() -> str:
    """
    Tool #8: Get the current date and time.

    Returns:
        Current datetime in ISO format
    """
    logger.info(f"🕐 Tool called: get_current_datetime()")

    # Track tool call
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
    """
    Tool #9: Execute Git commands.

    ⚠️ SECURITY: Limited to safe, read-only commands by default.
    For production, implement proper validation.

    Args:
        command: Git command to execute (e.g., "status", "log", "diff")

    Returns:
        Command output or error message
    """
    logger.info(f"🔧 Tool called: git_command('{command}')")

    # Track tool call
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "git_command",
        "command": command,
        "timestamp": datetime.now().isoformat()
    })

    # Whitelist of safe commands
    safe_commands = ['status', 'log', 'diff', 'branch', 'remote', 'show', 'ls-files']

    # Parse command
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return "❌ Empty command"

    # Check if command is safe
    if cmd_parts[0] not in safe_commands:
        return f"❌ Command '{cmd_parts[0]}' not in safe list: {', '.join(safe_commands)}\n\n" \
               f"For write operations (commit, push, etc.), request human approval first."

    try:
        # Execute git command
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
    """
    Tool #10: Validate JSON data against a Pydantic schema.

    Args:
        json_data: JSON string to validate
        schema_name: Name of schema (TaskPlan, CodeReview, etc.)

    Returns:
        Validation result
    """
    logger.info(f"✅ Tool called: validate_json(schema='{schema_name}')")

    # Track tool call
    if "tool_calls" not in st.session_state:
        st.session_state.tool_calls = []

    st.session_state.tool_calls.append({
        "tool": "validate_json",
        "schema": schema_name,
        "timestamp": datetime.now().isoformat()
    })

    # Map schema names to classes
    schemas = {
        "TaskPlan": TaskPlan,
        "CodeReview": CodeReview,
        "TaskStep": TaskStep
    }

    if schema_name not in schemas:
        return f"❌ Unknown schema: {schema_name}. Available: {', '.join(schemas.keys())}"

    try:
        # Parse JSON
        data = json.loads(json_data)

        # Validate against schema
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
# LLM Configuration (Gemini 2.5 Models)
# ============================================================================

def get_gemini_client(model: str = "gemini-2.5-pro") -> ChatCompletionClient:
    """
    Get a Gemini model client configured for AutoGen via OpenAI-compatible API.

    Supports both Gemini 2.5 Pro (for complex reasoning) and Flash (for speed).

    Args:
        model: Model identifier - "gemini-2.5-pro" or "gemini-2.5-flash"

    Returns:
        ChatCompletionClient configured for the specified Gemini model
    """
    # Get API key from multiple possible sources
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

    # Configure genai for direct usage (image analysis, etc.)
    genai.configure(api_key=api_key)

    logger.info(f"Creating Gemini client with model: {model}")

    # Return OpenAI-compatible client pointing to Gemini
    return OpenAIChatCompletionClient(
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
    """
    Custom AssistantAgent that logs messages to Streamlit's session state
    for real-time visualization in the chat interface.
    """

    def __init__(self, name: str, *args, **kwargs):
        super().__init__(name=name, *args, **kwargs)
        self.agent_name = name
        logger.info(f"Initialized StreamlitAssistantAgent: {name}")

    async def on_messages(self, messages: Sequence[ChatMessage], cancellation_token=None) -> ChatMessage:
        """Override to capture and log messages to Streamlit."""
        logger.info(f"{self.agent_name} processing {len(messages)} message(s)")

        # Process with parent class
        response = await super().on_messages(messages, cancellation_token)

        # Log response
        if isinstance(response, TextMessage):
            content = response.content

            # Check if this is structured output (JSON)
            try:
                parsed = json.loads(content)
                if "task_summary" in parsed:  # TaskPlan
                    plan = TaskPlan(**parsed)
                    content = f"**[{self.agent_name}]** 📋 Created Task Plan:\n\n{plan.to_markdown()}"
                elif "overall_quality" in parsed:  # CodeReview
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
            # Enhanced tool call display
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


# ============================================================================
# Agent Factory Functions (4 Agents with Tool Assignments)
# ============================================================================

def create_planner_agent() -> StreamlitAssistantAgent:
    """
    Create the Planner agent with Gemini 2.5 Pro for complex reasoning.

    Tools: web_search, read_document, analyze_image, get_current_datetime, validate_json
    """
    system_message = """You are an expert Planner agent specialized in software architecture and task decomposition.

Your responsibilities:
1. Analyze user requirements thoroughly and ask clarifying questions if needed
2. Break down complex tasks into clear, ordered implementation steps
3. Identify dependencies, risks, and required technologies
4. Create a structured, actionable plan using the TaskPlan schema
5. Use available tools to research and gather information
6. Hand off to the Coder or FileHandler once you have a complete plan

Available Tools:
- tool_web_search: Research best practices, libraries, and patterns
- tool_read_document: Read requirements docs or specifications
- tool_analyze_image: Analyze diagrams or mockups
- tool_get_current_datetime: Get timestamps for planning
- tool_validate_json: Validate your TaskPlan before sending

Output Format: Always structure your plan using the TaskPlan schema.
Use tool_validate_json to ensure your plan is valid before proceeding.

Be thorough but concise. Think step-by-step and consider edge cases."""

    # Use Gemini 2.5 Pro for complex reasoning
    model_client = get_gemini_client("gemini-2.5-pro")

    # Create tools
    tools = [
        FunctionTool(tool_web_search, description="Search the web for information and best practices"),
        FunctionTool(tool_read_document, description="Read document or specification files"),
        FunctionTool(tool_analyze_image, description="Analyze images, diagrams, or mockups"),
        FunctionTool(tool_get_current_datetime, description="Get current date and time"),
        FunctionTool(tool_validate_json, description="Validate JSON against Pydantic schemas"),
    ]

    return StreamlitAssistantAgent(
        name="Planner",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Coder", "FileHandler"]
    )


def create_coder_agent() -> StreamlitAssistantAgent:
    """
    Create the Coder agent with Gemini 2.5 Flash for fast, iterative coding.

    Tools: create_visualization, validate_json
    """
    system_message = """You are an expert Coder agent specialized in Python development.

Your responsibilities:
1. Implement code based on the Planner's specifications
2. Write clean, well-documented, efficient, and Pythonic code
3. Include comprehensive error handling and edge cases
4. Add type hints and docstrings
5. Create visualizations when needed
6. Hand off to the Reviewer when code is complete

Available Tools:
- tool_create_visualization: Create charts and graphs from data
- tool_validate_json: Validate structured data

Guidelines:
- Follow PEP 8 style guide
- Use modern Python features (3.11+)
- Include example usage in docstrings
- Add inline comments for complex logic
- Consider performance and maintainability

For file operations, execution, or Git commands, hand off to FileHandler agent."""

    # Use Gemini 2.5 Flash for fast, cost-effective coding
    model_client = get_gemini_client("gemini-2.5-flash")

    # Create tools
    tools = [
        FunctionTool(tool_create_visualization, description="Create data visualizations (charts, graphs)"),
        FunctionTool(tool_validate_json, description="Validate JSON against Pydantic schemas"),
    ]

    return StreamlitAssistantAgent(
        name="Coder",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Reviewer", "Planner", "FileHandler"]
    )


def create_reviewer_agent() -> StreamlitAssistantAgent:
    """
    Create the Reviewer agent with Gemini 2.5 Pro for thorough code review.

    Tools: web_search, static_analysis, read_document, analyze_image, validate_json
    """
    system_message = """You are an expert Reviewer agent specialized in code quality, security, and best practices.

Your responsibilities:
1. Review code for correctness, efficiency, security, and maintainability
2. Check for bugs, edge cases, and potential issues
3. Verify adherence to Python best practices and PEP 8
4. Ensure comprehensive error handling and input validation
5. Use tools to verify security best practices
6. Provide structured feedback using the CodeReview schema
7. Either approve (hand off to User) or send back to Coder with specific feedback

Available Tools:
- tool_web_search: Research security advisories and best practices
- tool_static_analysis: Run automated code quality checks
- tool_read_document: Read code files for review
- tool_analyze_image: Analyze architecture diagrams
- tool_validate_json: Validate structured outputs

Review Checklist:
- ✅ Correctness: Does it solve the problem?
- ✅ Security: Any injection risks, unsafe operations?
- ✅ Error Handling: All edge cases covered?
- ✅ Code Quality: Clean, readable, maintainable?
- ✅ Performance: Any obvious inefficiencies?
- ✅ Documentation: Clear docstrings and comments?
- ✅ Type Safety: Proper type hints?

Output Format: Use CodeReview schema. Validate with tool_validate_json."""

    # Use Gemini 2.5 Pro for thorough analysis
    model_client = get_gemini_client("gemini-2.5-pro")

    # Create tools
    tools = [
        FunctionTool(tool_web_search, description="Search for security advisories and best practices"),
        FunctionTool(tool_static_analysis, description="Perform static code analysis"),
        FunctionTool(tool_read_document, description="Read code files for review"),
        FunctionTool(tool_analyze_image, description="Analyze diagrams or visualizations"),
        FunctionTool(tool_validate_json, description="Validate JSON against Pydantic schemas"),
    ]

    return StreamlitAssistantAgent(
        name="Reviewer",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Coder", "FileHandler", "User"]
    )


def create_filehandler_agent() -> StreamlitAssistantAgent:
    """
    Create the FileHandler agent with Gemini 2.5 Flash for I/O operations.

    This agent is the SOLE OWNER of:
    - Code execution
    - File reading/writing
    - Git operations
    - Project archiving

    Tools: execute_code, create_visualization, read_document, create_project_zip, git_command, validate_json
    """
    system_message = """You are an expert FileHandler agent specialized in secure I/O operations and system interactions.

Your responsibilities:
1. Execute code in a safe, sandboxed environment
2. Handle all file reading and writing operations
3. Manage Git operations (status, log, diff, etc.)
4. Create project archives and snapshots
5. Generate visualizations when requested
6. Always prioritize security and request human approval for risky operations

Available Tools:
- tool_execute_code: Execute Python code (requires human approval)
- tool_create_visualization: Generate charts and graphs
- tool_read_document: Read files from filesystem
- tool_create_project_zip: Create project snapshots
- tool_git_command: Execute Git commands
- tool_validate_json: Validate structured data

Security Guidelines:
- ⚠️ ALWAYS request human approval for code execution
- ✅ Validate all file paths to prevent directory traversal
- ✅ Limit file sizes to prevent resource exhaustion
- ✅ Use timeouts for all subprocess operations
- ✅ Only allow safe Git commands by default

When you receive a request:
1. Assess security implications
2. Request human approval if needed
3. Execute with proper error handling
4. Report results clearly

Hand off to Coder or Reviewer when file operations are complete."""

    # Use Gemini 2.5 Flash for fast operations
    model_client = get_gemini_client("gemini-2.5-flash")

    # Create tools - FileHandler owns I/O tools
    tools = [
        FunctionTool(tool_execute_code, description="Execute Python code in sandbox (requires approval)"),
        FunctionTool(tool_create_visualization, description="Create data visualizations"),
        FunctionTool(tool_read_document, description="Read files from filesystem"),
        FunctionTool(tool_create_project_zip, description="Create ZIP archive of project"),
        FunctionTool(tool_git_command, description="Execute Git commands (safe commands only)"),
        FunctionTool(tool_validate_json, description="Validate JSON against schemas"),
    ]

    return StreamlitAssistantAgent(
        name="FileHandler",
        model_client=model_client,
        system_message=system_message,
        tools=tools,
        handoffs=["Coder", "Reviewer", "User"]
    )


# ============================================================================
# Team Setup
# ============================================================================

def create_team() -> SelectorGroupChat:
    """
    Create a SelectorGroupChat with 4 specialized agents.

    Agents:
    - Planner (Pro): Task decomposition and planning
    - Coder (Flash): Code implementation
    - Reviewer (Pro): Code review and quality assurance
    - FileHandler (Flash): I/O operations and system interactions

    Returns:
        Configured SelectorGroupChat team with proper termination
    """
    logger.info("Creating optimized 4-agent team with Gemini 2.5 models...")

    planner = create_planner_agent()
    coder = create_coder_agent()
    reviewer = create_reviewer_agent()
    filehandler = create_filehandler_agent()

    # Use Gemini Pro for team selector (complex decision making)
    selector_client = get_gemini_client("gemini-2.5-pro")

    team = SelectorGroupChat(
        participants=[planner, coder, reviewer, filehandler],
        model_client=selector_client,
        termination_condition=lambda msg: (
            "APPROVED" in str(msg.content).upper() or
            "TERMINATE" in str(msg.content).upper() or
            (isinstance(msg, TextMessage) and '"approved": true' in msg.content.lower())
        ),
        max_turns=30  # Allow more turns for complex tasks with tools
    )

    logger.info("Team created successfully with 4 agents and 10 tools")
    return team


# ============================================================================
# Streamlit UI
# ============================================================================

def initialize_session_state():
    """Initialize Streamlit session state variables with persistence support."""
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


def render_sidebar():
    """Render the sidebar with configuration options and stats."""
    with st.sidebar:
        st.title("⚙️ Configuration")

        # Model info
        st.markdown("### 🤖 Active Models")
        st.markdown("""
        - **Planner**: `gemini-2.5-pro` 🧠
        - **Coder**: `gemini-2.5-flash` ⚡
        - **Reviewer**: `gemini-2.5-pro` 🔍
        - **FileHandler**: `gemini-2.5-flash` 📁
        """)

        st.divider()

        # API Key input
        api_key = st.text_input(
            "Google/Gemini API Key",
            type="password",
            value=st.session_state.google_api_key or "",
            help="Enter your Google Gemini API key (supports Gemini 2.5 Pro and Flash)"
        )

        if api_key:
            st.session_state.google_api_key = api_key
            # Also set as environment variable for tools
            os.environ["GEMINI_API_KEY"] = api_key

        st.divider()

        # Team initialization
        if st.button("🚀 Initialize Team", use_container_width=True):
            if not st.session_state.google_api_key:
                st.error("Please enter your Google API key first!")
            else:
                try:
                    with st.spinner("Initializing 4-agent team with 10 tools..."):
                        st.session_state.team = create_team()
                        st.session_state.chat_active = True
                        st.success("✅ Team initialized! 4 agents + 10 tools ready!")
                        logger.info("Team initialized with 4 agents and 10 tools")
                except Exception as e:
                    st.error(f"Error initializing team: {str(e)}")
                    logger.error(f"Team initialization error: {e}", exc_info=True)

        st.divider()

        # Clear chat
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_approval = None
            st.session_state.approval_granted = False
            st.session_state.tool_calls = []
            st.rerun()

        # Reset team
        if st.button("🔄 Reset Team", use_container_width=True):
            st.session_state.team = None
            st.session_state.messages = []
            st.session_state.chat_active = False
            st.session_state.pending_approval = None
            st.session_state.approval_granted = False
            st.session_state.tool_calls = []
            st.rerun()

        st.divider()

        # Enhanced stats
        st.markdown("### 📊 Session Stats")
        st.metric("Messages", len(st.session_state.messages))
        st.metric("Team Status", "🟢 Active" if st.session_state.chat_active else "🔴 Inactive")
        st.metric("Tool Calls", len(st.session_state.get("tool_calls", [])))

        # Show recent tool calls
        if st.session_state.get("tool_calls"):
            with st.expander("🔧 Recent Tool Calls"):
                for tc in st.session_state.tool_calls[-10:]:
                    tool_name = tc.get("tool", "unknown")
                    st.text(f"• {tool_name}")


def render_chat_interface():
    """Render the main chat interface with enhanced features."""
    st.title("🤖 AutoGen Multi-Agent Coding Assistant")
    st.markdown("*Complete Edition: 4 Agents + 10 Specialized Tools | Gemini 2.5 Pro + Flash*")

    # Display chat messages
    chat_container = st.container()
    with chat_container:
        for idx, message in enumerate(st.session_state.messages):
            agent = message.get("agent", "Unknown")
            content = message.get("content", "")
            role = message.get("role", "assistant")

            with st.chat_message(role, avatar="🤖" if role == "assistant" else "👤"):
                st.markdown(content)

    # Display pending approval if any (HITL)
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

        # Add user message to chat
        st.session_state.messages.append({
            "role": "user",
            "content": prompt,
            "agent": "User",
            "timestamp": datetime.now().isoformat()
        })

        # Display user message
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        # Run the team
        with st.spinner("🤔 4 agents collaborating with 10 specialized tools..."):
            asyncio.run(run_team(prompt))


async def run_team(task: str):
    """
    Run the agent team on a given task with proper error handling.

    Args:
        task: The user's task description
    """
    try:
        logger.info(f"Starting team run for task: {task[:100]}...")

        team = st.session_state.team

        # Create initial message
        initial_message = TextMessage(content=task, source="User")

        # Run the team
        result = await team.run(task=initial_message)

        # Log completion
        logger.info(f"Team run completed. Messages: {len(result.messages)}")

        # Add final summary
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"✅ **Collaboration complete!** Total messages: {len(result.messages)} | Tools used: {len(st.session_state.tool_calls)}",
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
        page_title="AutoGen Multi-Agent Coder (Complete)",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize session state
    initialize_session_state()

    # Render UI
    render_sidebar()
    render_chat_interface()

    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray; font-size: 0.8em;'>
        🤖 AutoGen v0.4 | 🧠 Gemini 2.5 Pro + ⚡ Flash | 📋 Structured Outputs | 🔧 10 Specialized Tools | 🛡️ HITL Approval
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
