# AutoGen v0.4 Multi-Agent Coding Assistant with Streamlit

A sophisticated multi-agent AI coding assistant powered by **AutoGen v0.4** and **Google Gemini**, featuring:

- 🤖 **Three Specialized Agents**: Planner, Coder, and Reviewer working collaboratively
- 🎯 **Smart Orchestration**: SelectorGroupChat for intelligent agent coordination
- 💬 **Interactive UI**: Beautiful Streamlit interface with real-time chat
- 🔄 **State Persistence**: Resume conversations seamlessly
- 🛡️ **Human-in-the-Loop**: Approve code execution before it runs
- 📊 **Real-time Logging**: Track agent interactions and decisions

## Architecture

### Agents

1. **Planner Agent**
   - Analyzes user requirements
   - Breaks down complex tasks into actionable steps
   - Creates structured implementation plans

2. **Coder Agent**
   - Implements code based on specifications
   - Follows best practices and modern Python conventions
   - Includes error handling and documentation

3. **Reviewer Agent**
   - Reviews code quality and correctness
   - Checks for bugs, security issues, and edge cases
   - Provides constructive feedback

### Team Orchestration

Uses `SelectorGroupChat` for intelligent agent selection and handoffs, ensuring the right agent handles each task phase.

## Setup

### 1. Prerequisites

- Python 3.11+
- Google Gemini API key ([Get one here](https://aistudio.google.com/app/apikey))

### 2. Install Dependencies

The core libraries are already installed:
```bash
pip install --user streamlit python-dotenv
```

Or install all from requirements:
```bash
pip install --user -r requirements.txt
```

### 3. Configure API Key

**Option A: Streamlit Secrets (Recommended for Streamlit Cloud)**

Create `.streamlit/secrets.toml`:
```toml
GOOGLE_API_KEY = "your_api_key_here"
```

**Option B: Environment Variables**

Create `.env`:
```bash
GOOGLE_API_KEY=your_api_key_here
```

**Option C: UI Input**

Enter your API key directly in the sidebar when running the app.

## Usage

### Start the Application

```bash
streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`

### Workflow

1. **Initialize Team**: Click "🚀 Initialize Team" in the sidebar
2. **Enter Task**: Type your coding task in the chat input
3. **Collaborate**: Watch the agents plan, code, and review
4. **Approve**: Review and approve any code execution requests
5. **Iterate**: Continue the conversation or start a new task

### Example Tasks

Try asking:

- "Create a Python function to calculate the Fibonacci sequence with memoization"
- "Build a REST API endpoint for user authentication using FastAPI"
- "Write a data processing pipeline that reads CSV files and generates summary statistics"
- "Implement a binary search tree with insert, delete, and search operations"

## Features

### 🔄 State Persistence

The application maintains conversation history in `st.session_state`, allowing you to:
- Resume conversations after page refresh
- Review past agent interactions
- Track the evolution of solutions

### 🛡️ Human-in-the-Loop Approval

Before executing any generated code, the system:
1. Displays the code for review
2. Requests explicit user approval
3. Executes only after confirmation
4. Provides clear feedback on outcomes

### 📊 Real-Time Monitoring

- **Console Logging**: Detailed agent activity logs
- **Message Tracking**: All agent communications visible
- **Performance Metrics**: Message counts and team status

### 🎨 Clean UI

- **Chat Interface**: Familiar chat-based interaction
- **Agent Attribution**: Clear identification of which agent is speaking
- **Syntax Highlighting**: Code blocks with proper formatting
- **Responsive Design**: Works on desktop and tablet devices

## Project Structure

```
cc250/
├── streamlit_app.py          # Main application (single file!)
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variable template
├── README.md                 # This file
└── .streamlit/
    └── secrets.toml          # Streamlit secrets (optional)
```

## Configuration

### Model Selection

By default, the app uses `gemini-2.0-flash-exp`. To use a different model, modify the `get_gemini_model()` function:

```python
def get_gemini_model(model_name: str = "gemini-1.5-pro") -> ChatCompletionClient:
    # ... configuration
```

### Team Parameters

Customize team behavior in `create_team()`:

```python
team = SelectorGroupChat(
    participants=[planner, coder, reviewer],
    model_client=model_client,
    termination_condition=lambda msg: "APPROVED" in str(msg.content).upper(),
    max_turns=20  # Adjust max conversation turns
)
```

### Agent Prompts

Customize agent behavior by modifying system messages in:
- `create_planner_agent()`
- `create_coder_agent()`
- `create_reviewer_agent()`

## Troubleshooting

### "GOOGLE_API_KEY not found"

**Solution**: Ensure your API key is configured via one of the three methods (secrets.toml, .env, or UI input).

### "Team not initialized"

**Solution**: Click the "🚀 Initialize Team" button in the sidebar before sending messages.

### Import errors for autogen packages

**Solution**: Verify installations:
```bash
pip list | grep autogen
```

Should show:
- autogen-agentchat
- autogen-core
- autogen-ext

### Async/event loop errors

**Solution**: Streamlit handles async natively. Ensure you're using `asyncio.run()` in the `run_team()` function.

## Advanced Usage

### Custom Tools

Add custom tools to agents by extending the agent definitions:

```python
from autogen_agentchat.tools import Tool

def my_custom_tool(param: str) -> str:
    """Custom tool description."""
    return f"Processed: {param}"

coder = StreamlitAssistantAgent(
    name="Coder",
    model_client=model_client,
    system_message=system_message,
    tools=[Tool(my_custom_tool)],
    handoffs=["Reviewer"]
)
```

### State Persistence to Database

Extend state management to persist across sessions:

```python
import json

def save_state():
    with open("chat_history.json", "w") as f:
        json.dump(st.session_state.messages, f)

def load_state():
    try:
        with open("chat_history.json", "r") as f:
            st.session_state.messages = json.load(f)
    except FileNotFoundError:
        st.session_state.messages = []
```

## Performance Tips

1. **Use Gemini Flash models** for faster responses
2. **Set appropriate max_turns** to prevent long conversations
3. **Clear chat history** regularly to maintain performance
4. **Monitor API usage** to stay within quota limits

## Security Considerations

⚠️ **Important**:
- Never commit API keys to version control
- Use `.gitignore` to exclude `.env` and `secrets.toml`
- Implement rate limiting for production deployments
- Validate all user inputs before processing
- Review generated code before execution

## Contributing

This is a single-file application by design for simplicity. To extend:

1. Keep core logic in `streamlit_app.py`
2. Add helper modules for complex functionality
3. Maintain clear separation between UI and agent logic
4. Document all custom modifications

## License

This project is provided as-is for educational and development purposes.

## Resources

- [AutoGen Documentation](https://microsoft.github.io/autogen/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Google Gemini API](https://ai.google.dev/)
- [AutoGen AgentChat Guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/index.html)

## Support

For issues and questions:
- Check the troubleshooting section above
- Review AutoGen v0.4 documentation
- Consult Streamlit community forums

---

**Built with ❤️ using AutoGen v0.4 and Google Gemini**
