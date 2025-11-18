# Quick Start Guide

Get up and running with the AutoGen Multi-Agent Coding Assistant in 5 minutes!

## Prerequisites

- Python 3.11+ installed
- Google Gemini API key ([Get one free here](https://aistudio.google.com/app/apikey))

## Installation

### Step 1: Verify Setup

All core libraries should already be installed. Verify by running:

```bash
python verify_setup.py
```

You should see:
```
✅ streamlit
✅ autogen-agentchat
✅ autogen-core
✅ autogen-ext
✅ google-generativeai
✅ python-dotenv
✅ Python version is compatible (3.11+)
🎉 All checks passed!
```

If any packages are missing, install them:

```bash
pip install --user -r requirements.txt
```

### Step 2: Configure API Key

Choose **one** of these methods:

#### Method A: UI Input (Easiest)
1. Start the app (see Step 3)
2. Enter your API key in the sidebar
3. Click "Initialize Team"

#### Method B: Streamlit Secrets (Recommended)
1. Create `.streamlit/secrets.toml`:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

2. Edit the file and add your key:
   ```toml
   GOOGLE_API_KEY = "your_actual_api_key_here"
   ```

#### Method C: Environment Variable
1. Create `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit and add your key:
   ```
   GOOGLE_API_KEY=your_actual_api_key_here
   ```

### Step 3: Launch the Application

```bash
streamlit run streamlit_app.py
```

The app will open at: **http://localhost:8501**

## First Use

1. **Initialize Team**: Click the "🚀 Initialize Team" button in the sidebar

2. **Start Chatting**: Enter a coding task in the chat input, for example:
   ```
   Create a Python function to validate email addresses using regex
   ```

3. **Watch the Magic**: The three agents (Planner, Coder, Reviewer) will collaborate:
   - **Planner** breaks down the task
   - **Coder** implements the solution
   - **Reviewer** checks the code quality

4. **Approve Code**: If code execution is required, you'll be prompted to approve

5. **Iterate**: Continue the conversation or start a new task

## Example Tasks to Try

### Easy
```
Write a function to check if a string is a palindrome
```

### Medium
```
Create a class for a simple banking system with deposit, withdraw, and balance methods
```

### Advanced
```
Implement a decorator that caches function results and tracks hit/miss statistics
```

### Real-World
```
Build a FastAPI endpoint that accepts JSON data, validates it with Pydantic,
and stores it in a SQLite database
```

## Tips for Best Results

1. **Be Specific**: Provide clear requirements and constraints
2. **Iterate**: Ask follow-up questions to refine the solution
3. **Review Carefully**: Always review generated code before approval
4. **Save Work**: Use the chat history to track your session

## Troubleshooting

### "Team not initialized"
→ Click "🚀 Initialize Team" in the sidebar

### "GOOGLE_API_KEY not found"
→ Set your API key using one of the three methods above

### App won't start
→ Verify all packages are installed: `python verify_setup.py`

### Agents not responding
→ Check your API key is valid and you have quota remaining

### Want to start fresh?
→ Click "🗑️ Clear Chat" or "🔄 Reset Team" in the sidebar

## Project Structure

```
cc250/
├── streamlit_app.py           # 👈 Main application
├── requirements.txt           # Package dependencies
├── verify_setup.py           # Setup verification
├── README.md                 # Full documentation
├── QUICKSTART.md            # This file
├── .env.example             # Environment template
├── .gitignore              # Git ignore rules
└── .streamlit/
    ├── config.toml         # Streamlit configuration
    └── secrets.toml.example # Secrets template
```

## What's Next?

- Read the full [README.md](README.md) for advanced usage
- Customize agent behavior by editing `streamlit_app.py`
- Add custom tools for your specific use case
- Deploy to [Streamlit Cloud](https://streamlit.io/cloud) for free

## Need Help?

- Check the [README.md](README.md) for detailed documentation
- Review the AutoGen v0.4 docs: https://microsoft.github.io/autogen/
- Consult Streamlit docs: https://docs.streamlit.io/

---

**Happy Coding! 🚀**
