"""
AutoGen v0.4 Multi-Agent Coding System with Streamlit UI (Enhanced Edition)
===========================================================================
Advanced collaborative AI coding assistant featuring:
- Gemini 2.5 Pro (Planner/Reviewer) and Flash (Coder) models
- Structured outputs with Pydantic schemas
- Web search tool for RAG
- Human-in-the-loop approval with state persistence
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Sequence, Optional
from datetime import datetime

import streamlit as st
from pydantic import BaseModel, Field
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
# Web Search Tool (RAG)
# ============================================================================

def google_search(query: str) -> str:
    """
    Perform a web search to find information (RAG capability).

    This is a simplified implementation. In production, you should use:
    - Google Custom Search API
    - Serper API
    - Tavily Search API

    Args:
        query: The search query

    Returns:
        Search results as a formatted string
    """
    logger.info(f"Web search requested: {query}")

    # For demonstration purposes, return structured guidance
    # In production, integrate with actual search APIs
    result = f"""
    🔍 Web Search Results for: "{query}"

    [Note: This is a demonstration. Configure a real search API for production.]

    To enable real web search:
    1. Get API key from: https://programmablesearchengine.google.com/
    2. Install: pip install google-api-python-client
    3. Implement actual search call

    Simulated guidance for your query:
    - Check official documentation for latest best practices
    - Review recent Stack Overflow discussions
    - Consult GitHub repositories for implementation examples
    - Verify with current Python package documentation

    Recommended next steps:
    1. Search official Python docs
    2. Check PyPI for latest package versions
    3. Review community best practices
    """

    # Add to session state for tracking
    if "search_queries" not in st.session_state:
        st.session_state.search_queries = []
    st.session_state.search_queries.append({
        "query": query,
        "timestamp": datetime.now().isoformat()
    })

    return result


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

    # Configure genai for any direct usage
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

        # Log incoming messages to session state
        for msg in messages:
            if isinstance(msg, TextMessage) and msg.source != self.agent_name:
                # Don't log our own previous messages
                pass

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
            tool_calls_str = "\n".join([
                f"- {tc.name}({json.dumps(tc.arguments)})"
                for tc in response.content
            ])
            self._add_to_streamlit_chat(
                role="assistant",
                content=f"**[{self.agent_name}]** 🔧 Calling tools:\n{tool_calls_str}",
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
# Agent Factory Functions
# ============================================================================

def create_planner_agent() -> StreamlitAssistantAgent:
    """
    Create the Planner agent with Gemini 2.5 Pro for complex reasoning.
    Uses structured output (Pydantic) for reliable task planning.
    """
    system_message = """You are an expert Planner agent specialized in software architecture and task decomposition.

Your responsibilities:
1. Analyze user requirements thoroughly and ask clarifying questions if needed
2. Break down complex tasks into clear, ordered implementation steps
3. Identify dependencies, risks, and required technologies
4. Create a structured, actionable plan using the TaskPlan schema
5. Hand off to the Coder once you have a complete plan

Output Format: Always structure your plan using the TaskPlan schema with:
- task_summary: Brief overview
- requirements: Key requirements list
- steps: Ordered implementation steps with complexity and dependencies
- estimated_time: Time estimate
- technologies: Required libraries/frameworks
- risks: Potential challenges

Be thorough but concise. Think step-by-step and consider edge cases."""

    # Use Gemini 2.5 Pro for complex reasoning
    model_client = get_gemini_client("gemini-2.5-pro")

    return StreamlitAssistantAgent(
        name="Planner",
        model_client=model_client,
        system_message=system_message,
        handoffs=["Coder"],
        # Enable structured output
        model_client=model_client
    )


def create_coder_agent() -> StreamlitAssistantAgent:
    """
    Create the Coder agent with Gemini 2.5 Flash for fast, iterative coding.
    Includes web search tool for research and fact-checking.
    """
    system_message = """You are an expert Coder agent specialized in Python development.

Your responsibilities:
1. Implement code based on the Planner's specifications
2. Write clean, well-documented, efficient, and Pythonic code
3. Include comprehensive error handling and edge cases
4. Add type hints and docstrings
5. Use web search when you need to verify best practices or check documentation
6. Hand off to the Reviewer when code is complete

Guidelines:
- Follow PEP 8 style guide
- Use modern Python features (3.11+)
- Include example usage in docstrings
- Add inline comments for complex logic
- Consider performance and maintainability
- Use web search tool to verify library APIs and best practices

When unsure about an API or best practice, use the google_search tool to research."""

    # Use Gemini 2.5 Flash for fast, cost-effective coding
    model_client = get_gemini_client("gemini-2.5-flash")

    # Create web search tool
    search_tool = FunctionTool(
        google_search,
        description="Search the web for information, documentation, or best practices"
    )

    return StreamlitAssistantAgent(
        name="Coder",
        model_client=model_client,
        system_message=system_message,
        tools=[search_tool],
        handoffs=["Reviewer", "Planner"]
    )


def create_reviewer_agent() -> StreamlitAssistantAgent:
    """
    Create the Reviewer agent with Gemini 2.5 Pro for thorough code review.
    Uses structured output for consistent reviews and includes web search.
    """
    system_message = """You are an expert Reviewer agent specialized in code quality, security, and best practices.

Your responsibilities:
1. Review code for correctness, efficiency, security, and maintainability
2. Check for bugs, edge cases, and potential issues
3. Verify adherence to Python best practices and PEP 8
4. Ensure comprehensive error handling and input validation
5. Use web search to verify security best practices or check for known vulnerabilities
6. Provide structured feedback using the CodeReview schema
7. Either approve (hand off to User) or send back to Coder with specific feedback

Review Checklist:
- ✅ Correctness: Does it solve the problem?
- ✅ Security: Any injection risks, unsafe operations?
- ✅ Error Handling: All edge cases covered?
- ✅ Code Quality: Clean, readable, maintainable?
- ✅ Performance: Any obvious inefficiencies?
- ✅ Documentation: Clear docstrings and comments?
- ✅ Type Safety: Proper type hints?

Output Format: Use CodeReview schema with:
- overall_quality: Excellent/Good/Fair/Poor
- strengths: What's done well
- issues: Problems that must be fixed
- suggestions: Nice-to-have improvements
- security_concerns: Any security issues
- approved: true/false
- feedback_summary: Brief overall assessment

Use web search to verify security best practices when reviewing sensitive operations."""

    # Use Gemini 2.5 Pro for thorough analysis
    model_client = get_gemini_client("gemini-2.5-pro")

    # Create web search tool
    search_tool = FunctionTool(
        google_search,
        description="Search for security best practices, CVEs, or code review guidelines"
    )

    return StreamlitAssistantAgent(
        name="Reviewer",
        model_client=model_client,
        system_message=system_message,
        tools=[search_tool],
        handoffs=["Coder", "User"]
    )


# ============================================================================
# Team Setup
# ============================================================================

def create_team() -> SelectorGroupChat:
    """
    Create a SelectorGroupChat with Planner (Pro), Coder (Flash), and Reviewer (Pro).

    Uses model-optimized agents:
    - Planner & Reviewer: Gemini 2.5 Pro (complex reasoning)
    - Coder: Gemini 2.5 Flash (fast, iterative coding)

    Returns:
        Configured SelectorGroupChat team with proper termination
    """
    logger.info("Creating optimized agent team with Gemini 2.5 models...")

    planner = create_planner_agent()
    coder = create_coder_agent()
    reviewer = create_reviewer_agent()

    # Use Gemini Pro for team selector (complex decision making)
    selector_client = get_gemini_client("gemini-2.5-pro")

    team = SelectorGroupChat(
        participants=[planner, coder, reviewer],
        model_client=selector_client,
        termination_condition=lambda msg: (
            "APPROVED" in str(msg.content).upper() or
            "TERMINATE" in str(msg.content).upper() or
            (isinstance(msg, TextMessage) and '"approved": true' in msg.content.lower())
        ),
        max_turns=25  # Allow more turns for complex tasks
    )

    logger.info("Team created successfully with model optimization")
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

    if "search_queries" not in st.session_state:
        st.session_state.search_queries = []

    if "task_plans" not in st.session_state:
        st.session_state.task_plans = []


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
        """)

        st.divider()

        # API Key input
        api_key = st.text_input(
            "Google/Gemini API Key",
            type="password",
            value=st.session_state.google_api_key or "",
            help="Enter your Google Gemini API key (supports both Gemini 2.5 Pro and Flash)"
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
                    with st.spinner("Initializing AI team with Gemini 2.5..."):
                        st.session_state.team = create_team()
                        st.session_state.chat_active = True
                        st.success("✅ Team initialized with Pro + Flash models!")
                        logger.info("Team initialized from UI with Gemini 2.5")
                except Exception as e:
                    st.error(f"Error initializing team: {str(e)}")
                    logger.error(f"Team initialization error: {e}", exc_info=True)

        st.divider()

        # Clear chat
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_approval = None
            st.session_state.approval_granted = False
            st.rerun()

        # Reset team
        if st.button("🔄 Reset Team", use_container_width=True):
            st.session_state.team = None
            st.session_state.messages = []
            st.session_state.chat_active = False
            st.session_state.pending_approval = None
            st.session_state.approval_granted = False
            st.rerun()

        st.divider()

        # Enhanced stats
        st.markdown("### 📊 Session Stats")
        st.metric("Messages", len(st.session_state.messages))
        st.metric("Team Status", "🟢 Active" if st.session_state.chat_active else "🔴 Inactive")
        st.metric("Web Searches", len(st.session_state.get("search_queries", [])))

        # Show recent searches
        if st.session_state.get("search_queries"):
            with st.expander("🔍 Recent Searches"):
                for sq in st.session_state.search_queries[-5:]:
                    st.text(f"• {sq['query']}")


def render_chat_interface():
    """Render the main chat interface with enhanced features."""
    st.title("🤖 AutoGen Multi-Agent Coding Assistant")
    st.markdown("*Enhanced with Gemini 2.5 Pro + Flash | Structured Outputs | Web Search (RAG)*")

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
            st.code(code, language="python")

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
        with st.spinner("🤔 Agents are collaborating (Pro + Flash models)..."):
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
            "content": f"✅ **Collaboration complete!** Total messages: {len(result.messages)}",
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
        page_title="AutoGen Multi-Agent Coder (Enhanced)",
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
        🤖 AutoGen v0.4 | 🧠 Gemini 2.5 Pro + ⚡ Flash | 📋 Structured Outputs | 🔍 Web Search (RAG) | 🛡️ HITL Approval
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
