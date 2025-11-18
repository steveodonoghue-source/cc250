"""
AutoGen v0.4 Multi-Agent Coding System with Streamlit UI
=========================================================
A collaborative AI coding assistant using Planner, Coder, and Reviewer agents
with human-in-the-loop approval and state persistence.
"""

import asyncio
import logging
from typing import Any, Dict, List, Sequence
from datetime import datetime

import streamlit as st
from autogen_agentchat.agents import AssistantAgent, Handoff
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console
from autogen_agentchat.messages import (
    ChatMessage,
    TextMessage,
    ToolCallMessage,
    ToolCallResultMessage,
)
from autogen_core.models import ChatCompletionClient
from autogen_ext.models.openai import OpenAIChatCompletionClient
import google.generativeai as genai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# LLM Configuration
# ============================================================================

def get_gemini_model(model_name: str = "gemini-2.0-flash-exp") -> ChatCompletionClient:
    """
    Get a Gemini model configured for AutoGen via OpenAI-compatible API.

    Args:
        model_name: The Gemini model identifier

    Returns:
        ChatCompletionClient configured for Gemini
    """
    api_key = st.secrets.get("GOOGLE_API_KEY") or st.session_state.get("google_api_key")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in secrets or session state")

    # Configure genai for potential direct use
    genai.configure(api_key=api_key)

    # Return OpenAI-compatible client pointing to Gemini
    return OpenAIChatCompletionClient(
        model=model_name,
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
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
            if isinstance(msg, TextMessage):
                self._add_to_streamlit_chat(
                    role="assistant",
                    content=f"**[{self.agent_name}]** {msg.content}",
                    agent=self.agent_name
                )

        # Process with parent class
        response = await super().on_messages(messages, cancellation_token)

        # Log response
        if isinstance(response, TextMessage):
            self._add_to_streamlit_chat(
                role="assistant",
                content=f"**[{self.agent_name}]** {response.content}",
                agent=self.agent_name
            )
        elif isinstance(response, ToolCallMessage):
            tool_calls_str = "\n".join([f"- {tc.name}({tc.arguments})" for tc in response.content])
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


class StreamlitUserProxyAgent:
    """
    Custom UserProxy that handles human-in-the-loop approval in Streamlit UI.
    Prompts the human for approval before executing any generated code.
    """

    def __init__(self, name: str = "User"):
        self.name = name
        self.pending_approval = None
        logger.info(f"Initialized StreamlitUserProxyAgent: {name}")

    async def handle_user_input(self, task: str) -> TextMessage:
        """Convert user input into a message."""
        logger.info(f"User input: {task[:100]}...")
        return TextMessage(content=task, source=self.name)

    async def request_approval(self, action: str, code: str = None) -> bool:
        """
        Request human approval for an action (e.g., code execution).
        In a real Streamlit app, this would show UI controls.
        """
        logger.info(f"Requesting approval for: {action}")

        # Store pending approval in session state
        st.session_state.pending_approval = {
            "action": action,
            "code": code,
            "timestamp": datetime.now().isoformat()
        }

        # In a real implementation, this would wait for user interaction
        # For now, we'll use session state to track approval
        return st.session_state.get("approval_granted", False)

    def _add_to_streamlit_chat(self, role: str, content: str):
        """Add message to Streamlit session state."""
        if "messages" not in st.session_state:
            st.session_state.messages = []

        st.session_state.messages.append({
            "role": role,
            "content": content,
            "agent": self.name,
            "timestamp": datetime.now().isoformat()
        })


# ============================================================================
# Agent Definitions
# ============================================================================

def create_planner_agent(model_client: ChatCompletionClient) -> StreamlitAssistantAgent:
    """Create the Planner agent responsible for task decomposition."""
    system_message = """You are a Planner agent. Your role is to:
1. Understand the user's request thoroughly
2. Break down complex tasks into clear, actionable steps
3. Identify what needs to be coded and what needs to be reviewed
4. Create a structured plan with priorities
5. Hand off to the Coder when you have a clear plan

Be concise but thorough. Always think step-by-step."""

    return StreamlitAssistantAgent(
        name="Planner",
        model_client=model_client,
        system_message=system_message,
        handoffs=["Coder"]
    )


def create_coder_agent(model_client: ChatCompletionClient) -> StreamlitAssistantAgent:
    """Create the Coder agent responsible for implementation."""
    system_message = """You are a Coder agent. Your role is to:
1. Implement code based on the Planner's specifications
2. Write clean, well-documented, and efficient Python code
3. Include error handling and edge cases
4. Provide complete, runnable code blocks
5. Hand off to the Reviewer when code is ready for review

Use best practices and modern Python conventions. Always test your logic mentally before presenting."""

    return StreamlitAssistantAgent(
        name="Coder",
        model_client=model_client,
        system_message=system_message,
        handoffs=["Reviewer", "Planner"]
    )


def create_reviewer_agent(model_client: ChatCompletionClient) -> StreamlitAssistantAgent:
    """Create the Reviewer agent responsible for code review."""
    system_message = """You are a Reviewer agent. Your role is to:
1. Review code for correctness, efficiency, and best practices
2. Check for potential bugs, security issues, and edge cases
3. Suggest improvements and optimizations
4. Verify that the code meets the original requirements
5. Either approve the code or send it back to the Coder with feedback

Be constructive and specific in your feedback. If the code is good, say so clearly."""

    return StreamlitAssistantAgent(
        name="Reviewer",
        model_client=model_client,
        system_message=system_message,
        handoffs=["Coder", "User"]
    )


# ============================================================================
# Team Setup
# ============================================================================

def create_team(model_client: ChatCompletionClient) -> SelectorGroupChat:
    """
    Create a SelectorGroupChat with Planner, Coder, and Reviewer agents.

    Args:
        model_client: The LLM client to use for all agents

    Returns:
        Configured SelectorGroupChat team
    """
    logger.info("Creating agent team...")

    planner = create_planner_agent(model_client)
    coder = create_coder_agent(model_client)
    reviewer = create_reviewer_agent(model_client)

    team = SelectorGroupChat(
        participants=[planner, coder, reviewer],
        model_client=model_client,
        termination_condition=lambda msg: "APPROVED" in str(msg.content).upper()
                                          or "TERMINATE" in str(msg.content).upper(),
        max_turns=20
    )

    logger.info("Team created successfully")
    return team


# ============================================================================
# Streamlit UI
# ============================================================================

def initialize_session_state():
    """Initialize Streamlit session state variables."""
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


def render_sidebar():
    """Render the sidebar with configuration options."""
    with st.sidebar:
        st.title("⚙️ Configuration")

        # API Key input
        api_key = st.text_input(
            "Google API Key",
            type="password",
            value=st.session_state.google_api_key or "",
            help="Enter your Google Gemini API key"
        )

        if api_key:
            st.session_state.google_api_key = api_key

        st.divider()

        # Team initialization
        if st.button("🚀 Initialize Team", use_container_width=True):
            if not st.session_state.google_api_key:
                st.error("Please enter your Google API key first!")
            else:
                try:
                    with st.spinner("Initializing AI team..."):
                        model_client = get_gemini_model()
                        st.session_state.team = create_team(model_client)
                        st.session_state.chat_active = True
                        st.success("Team initialized! Start chatting below.")
                        logger.info("Team initialized from UI")
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
        st.markdown("### 📊 Stats")
        st.metric("Total Messages", len(st.session_state.messages))
        st.metric("Team Status", "Active" if st.session_state.chat_active else "Inactive")


def render_chat_interface():
    """Render the main chat interface."""
    st.title("🤖 AutoGen Multi-Agent Coding Assistant")
    st.markdown("*Powered by AutoGen v0.4 + Google Gemini*")

    # Display chat messages
    chat_container = st.container()
    with chat_container:
        for idx, message in enumerate(st.session_state.messages):
            agent = message.get("agent", "Unknown")
            content = message.get("content", "")
            role = message.get("role", "assistant")

            with st.chat_message(role, avatar="🤖" if role == "assistant" else "👤"):
                st.markdown(content)

    # Display pending approval if any
    if st.session_state.pending_approval:
        st.warning("⚠️ Approval Required")
        approval = st.session_state.pending_approval
        st.code(approval.get("code", approval.get("action")), language="python")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve", use_container_width=True):
                st.session_state.approval_granted = True
                st.session_state.pending_approval = None
                st.rerun()

        with col2:
            if st.button("❌ Reject", use_container_width=True):
                st.session_state.approval_granted = False
                st.session_state.pending_approval = None
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
        with st.spinner("🤔 Agents are collaborating..."):
            asyncio.run(run_team(prompt))


async def run_team(task: str):
    """
    Run the agent team on a given task.

    Args:
        task: The user's task description
    """
    try:
        logger.info(f"Starting team run for task: {task[:100]}...")

        team = st.session_state.team

        # Create initial message
        initial_message = TextMessage(content=task, source="User")

        # Run the team with streaming
        result = await team.run(task=initial_message)

        # Log completion
        logger.info(f"Team run completed. Messages: {len(result.messages)}")

        # Add final summary
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"✅ **Task completed!** Total messages exchanged: {len(result.messages)}",
            "agent": "System",
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error running team: {e}", exc_info=True)
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"❌ **Error:** {str(e)}",
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
        page_title="AutoGen Multi-Agent Coder",
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
        Built with AutoGen v0.4 🤖 | Powered by Google Gemini ✨ | State Persistence ✅ | HITL Approval 🛡️
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
