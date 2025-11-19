"""
Example Python Client for AutoGen Multi-Agent API

Demonstrates how to use the API programmatically for:
- Starting agent tasks
- Polling for results
- Managing conversations
- Working with skills
"""

import requests
import time
import json
from typing import Dict, Any, Optional

class AutoGenAPI:
    """Python client for AutoGen Multi-Agent API."""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        """
        Initialize API client.

        Args:
            base_url: Base URL of the API server
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers['X-API-Key'] = api_key

    def health_check(self) -> Dict[str, Any]:
        """Check API health status."""
        response = requests.get(f"{self.base_url}/api/v1/health", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def start_chat(
        self,
        message: str,
        gemini_api_key: str,
        session_id: Optional[str] = None,
        max_turns: int = 40
    ) -> Dict[str, Any]:
        """
        Start a new agent task.

        Args:
            message: User message to send to agents
            gemini_api_key: Google Gemini API key
            session_id: Optional session ID for conversation continuity
            max_turns: Maximum agent turns (default: 40)

        Returns:
            Dict with task_id and session_id
        """
        payload = {
            "message": message,
            "api_key": gemini_api_key,
            "session_id": session_id,
            "max_turns": max_turns
        }

        response = requests.post(
            f"{self.base_url}/api/v1/chat",
            json=payload,
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get status of a task.

        Args:
            task_id: Task ID returned from start_chat()

        Returns:
            Dict with task status, messages, cost, etc.
        """
        response = requests.get(
            f"{self.base_url}/api/v1/tasks/{task_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 2,
        timeout: int = 300,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Wait for task to complete, polling at regular intervals.

        Args:
            task_id: Task ID to wait for
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait
            verbose: Print status updates

        Returns:
            Final task status

        Raises:
            TimeoutError: If task doesn't complete within timeout
        """
        start_time = time.time()

        while True:
            status = self.get_task_status(task_id)

            if verbose:
                print(f"[{status['status'].upper()}] {status.get('progress', 'In progress...')}")

            if status['status'] in ['completed', 'failed']:
                return status

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

            time.sleep(poll_interval)

    def list_conversations(self, limit: int = 50) -> list:
        """List saved conversations."""
        response = requests.get(
            f"{self.base_url}/api/v1/conversations",
            params={"limit": limit},
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_conversation(self, session_id: str) -> Dict[str, Any]:
        """Get conversation details including full message history."""
        response = requests.get(
            f"{self.base_url}/api/v1/conversations/{session_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def delete_conversation(self, session_id: str) -> Dict[str, Any]:
        """Delete a conversation."""
        response = requests.delete(
            f"{self.base_url}/api/v1/conversations/{session_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def export_conversation(self, session_id: str) -> str:
        """Export conversation as Markdown."""
        response = requests.get(
            f"{self.base_url}/api/v1/conversations/{session_id}/export",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()['markdown']

    def list_skills(self, active_only: bool = True, limit: int = 100) -> list:
        """List available skills."""
        response = requests.get(
            f"{self.base_url}/api/v1/skills",
            params={"active_only": active_only, "limit": limit},
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def register_skill(
        self,
        tool_name: str,
        description: str,
        code: str,
        parameters: Dict[str, Any],
        safety_notes: list
    ) -> Dict[str, Any]:
        """Register a new skill."""
        payload = {
            "tool_name": tool_name,
            "description": description,
            "code": code,
            "parameters": parameters,
            "safety_notes": safety_notes
        }

        response = requests.post(
            f"{self.base_url}/api/v1/skills",
            json=payload,
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_cost_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get cost summary for the last N days."""
        response = requests.get(
            f"{self.base_url}/api/v1/cost/summary",
            params={"days": days},
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()


# ============================================================================
# Example Usage
# ============================================================================

def example_basic_chat():
    """Example: Basic chat interaction."""
    print("=" * 60)
    print("Example 1: Basic Chat")
    print("=" * 60)

    # Initialize client
    client = AutoGenAPI()

    # Check health
    health = client.health_check()
    print(f"✅ API Status: {health['status']}")
    print()

    # Start a chat
    print("Starting chat task...")
    result = client.start_chat(
        message="Create a Python function to calculate fibonacci numbers",
        gemini_api_key="YOUR_GEMINI_API_KEY_HERE"  # Replace with actual key
    )

    task_id = result['task_id']
    session_id = result['session_id']
    print(f"✅ Task ID: {task_id}")
    print(f"✅ Session ID: {session_id}")
    print()

    # Wait for completion
    print("Waiting for agents to complete task...")
    final_status = client.wait_for_completion(task_id, verbose=True)

    print()
    print(f"✅ Task completed!")
    print(f"   Messages: {len(final_status['messages'])}")
    print(f"   Cost: ${final_status['cost']:.4f}")
    print()


def example_conversation_continuity():
    """Example: Continue a conversation."""
    print("=" * 60)
    print("Example 2: Conversation Continuity")
    print("=" * 60)

    client = AutoGenAPI()

    # First message
    print("Message 1: Create a function...")
    result1 = client.start_chat(
        message="Create a function to sort a list",
        gemini_api_key="YOUR_GEMINI_API_KEY_HERE"
    )
    session_id = result1['session_id']

    status1 = client.wait_for_completion(result1['task_id'], verbose=False)
    print(f"✅ Completed - {len(status1['messages'])} messages")
    print()

    # Follow-up message in same session
    print("Message 2: Add error handling...")
    result2 = client.start_chat(
        message="Add error handling to the function",
        gemini_api_key="YOUR_GEMINI_API_KEY_HERE",
        session_id=session_id  # Same session!
    )

    status2 = client.wait_for_completion(result2['task_id'], verbose=False)
    print(f"✅ Completed - {len(status2['messages'])} messages")
    print()


def example_conversation_management():
    """Example: List and export conversations."""
    print("=" * 60)
    print("Example 3: Conversation Management")
    print("=" * 60)

    client = AutoGenAPI()

    # List conversations
    conversations = client.list_conversations(limit=10)
    print(f"Found {len(conversations)} conversations:")
    for conv in conversations[:5]:
        print(f"  • {conv['title'][:40]} ({conv['message_count']} msgs, ${conv['total_cost']:.3f})")
    print()

    # Export first conversation
    if conversations:
        session_id = conversations[0]['session_id']
        markdown = client.export_conversation(session_id)
        print(f"Exported conversation as Markdown ({len(markdown)} chars)")
        print(markdown[:200] + "...")
        print()


def example_skills():
    """Example: Work with skills."""
    print("=" * 60)
    print("Example 4: Skills Management")
    print("=" * 60)

    client = AutoGenAPI()

    # Register a new skill
    print("Registering new skill...")
    skill = client.register_skill(
        tool_name="tool_reverse_string",
        description="Reverse a string",
        code="def tool_reverse_string(text: str) -> str:\n    return text[::-1]",
        parameters={"text": "str"},
        safety_notes=["Simple operation, no security concerns"]
    )
    print(f"✅ Registered: {skill['tool_name']}")
    print()

    # List skills
    skills = client.list_skills()
    print(f"Found {len(skills)} skills:")
    for s in skills:
        print(f"  • {s['tool_name']}: {s['description']}")
    print()


def example_cost_tracking():
    """Example: Get cost summary."""
    print("=" * 60)
    print("Example 5: Cost Tracking")
    print("=" * 60)

    client = AutoGenAPI()

    summary = client.get_cost_summary(days=7)
    print(f"Last 7 days:")
    print(f"  Total Cost: ${summary.get('total_cost', 0):.2f}")
    print(f"  Total Calls: {summary.get('total_calls', 0)}")
    print()

    if summary.get('by_agent'):
        print("By Agent:")
        for agent, stats in summary['by_agent'].items():
            print(f"  • {agent}: ${stats['cost']:.4f} ({stats['calls']} calls)")
    print()


if __name__ == "__main__":
    print()
    print("=" * 60)
    print("AutoGen Multi-Agent API - Python Client Examples")
    print("=" * 60)
    print()
    print("NOTE: Replace 'YOUR_GEMINI_API_KEY_HERE' with your actual key")
    print()

    # Uncomment the examples you want to run:

    # example_basic_chat()
    # example_conversation_continuity()
    # example_conversation_management()
    # example_skills()
    # example_cost_tracking()

    print("To run these examples:")
    print("1. Start the API server: python api.py")
    print("2. Uncomment an example above")
    print("3. Replace YOUR_GEMINI_API_KEY_HERE with your key")
    print("4. Run: python api_client_example.py")
    print()
