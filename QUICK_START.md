# 🚀 Quick Start Guide - AutoGen Multi-Agent System

This guide provides **three easy ways** to run the application, from simplest to most advanced.

---

## 📋 Table of Contents

- [Option 1: One-Click Startup Scripts](#option-1-one-click-startup-scripts-easiest) ⭐ **RECOMMENDED**
- [Option 2: Docker Container](#option-2-docker-container-advanced)
- [Option 3: Desktop Shortcut](#option-3-desktop-shortcut-ultimate-convenience)

---

## Option 1: One-Click Startup Scripts ⭐ EASIEST

**Perfect for beginners!** Just double-click to run.

### First Time Setup (One-Time Only)

#### Windows:
1. Double-click `setup.bat`
2. Wait for installation (2-3 minutes)
3. When you see "Setup Complete!", close the window

#### Mac/Linux:
1. Open Terminal
2. Navigate to project folder:
   ```bash
   cd /path/to/cc250
   ```
3. Run setup:
   ```bash
   ./setup.sh
   ```
4. Wait for "Setup Complete!"

### Running the App (Every Time)

#### Windows:
- Double-click `start.bat`
- Browser opens automatically at `http://localhost:8501`

#### Mac/Linux:
- Double-click `start.sh` (or run `./start.sh` in Terminal)
- Browser opens automatically at `http://localhost:8501`

### Stopping the App
- Press `Ctrl+C` in the terminal window
- Or close the terminal window

---

## Option 2: Docker Container (Advanced)

**Perfect for: Developers, production deployments, or if you want everything isolated**

### Prerequisites
- Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Make sure Docker is running (look for whale icon in system tray)

### Method A: Docker Compose (Recommended)

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

Access the app at: `http://localhost:8501`

### Method B: Docker Commands

```bash
# Build the image
docker build -t autogen-app .

# Run the container
docker run -d -p 8501:8501 --name autogen autogen-app

# View logs
docker logs -f autogen

# Stop and remove
docker stop autogen
docker rm autogen
```

### Benefits of Docker:
- ✅ No Python installation needed
- ✅ Consistent environment across all machines
- ✅ Easy to share with team members
- ✅ No conflicts with other Python projects
- ✅ One command to start everything

---

## Option 3: Desktop Shortcut (Ultimate Convenience)

Create a desktop icon that starts the app with one click!

### Windows Desktop Shortcut

1. **Right-click on Desktop** → New → Shortcut
2. **Location:** Browse to `start.bat` in your project folder
3. **Name:** `AutoGen Multi-Agent System`
4. Click **Finish**
5. **Optional: Custom Icon**
   - Right-click shortcut → Properties
   - Click "Change Icon"
   - Choose an icon (or download a robot icon)

### Mac Desktop Shortcut

1. **Open TextEdit**
2. **Format** → Make Plain Text
3. **Paste this code:**
   ```bash
   #!/bin/bash
   cd /path/to/cc250
   ./start.sh
   ```
4. **Replace** `/path/to/cc250` with your actual project path
5. **Save as:** `AutoGen.command` on your Desktop
6. **Make executable:**
   ```bash
   chmod +x ~/Desktop/AutoGen.command
   ```
7. Double-click to run!

### Linux Desktop Shortcut

1. **Create file:** `~/Desktop/autogen.desktop`
2. **Add this content:**
   ```desktop
   [Desktop Entry]
   Version=1.0
   Type=Application
   Name=AutoGen Multi-Agent System
   Exec=/path/to/cc250/start.sh
   Terminal=true
   Icon=robot
   ```
3. **Replace** `/path/to/cc250` with your actual path
4. **Make executable:**
   ```bash
   chmod +x ~/Desktop/autogen.desktop
   ```

---

## 🔧 Troubleshooting

### Issue: "Python not found"
**Solution:** Install Python 3.8+ from [python.org](https://python.org)

### Issue: "Port 8501 already in use"
**Solution:**
- Stop any other Streamlit apps
- Or edit `start.bat`/`start.sh` to use port 8502:
  ```bash
  streamlit run streamlit_app.py --server.port 8502
  ```

### Issue: Scripts won't run (Mac/Linux)
**Solution:** Make them executable:
```bash
chmod +x setup.sh start.sh
```

### Issue: Docker build fails
**Solution:**
- Make sure Docker Desktop is running
- Try: `docker system prune` to clean up
- Restart Docker Desktop

### Issue: Database errors
**Solution:** Delete all `.db` files and run setup again

---

## 📁 Project Structure

```
cc250/
├── setup.bat           # Windows setup (one-time)
├── setup.sh            # Mac/Linux setup (one-time)
├── start.bat           # Windows startup
├── start.sh            # Mac/Linux startup
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker image definition
├── docker-compose.yml  # Docker orchestration
├── streamlit_app.py    # Main UI application
├── api.py              # REST API (optional)
├── database*.py        # Database modules
└── *.db                # SQLite databases (auto-created)
```

---

## 🎯 What's Included

Once running, you'll have access to:

- ✅ **Skill Library** - Create and manage agent skills
- ✅ **Marketplace** - Browse and install pre-built skills
- ✅ **Cost Optimization** - Track API usage and costs
- ✅ **Orchestration** - Multi-agent workflows
- ✅ **Testing & Quality** - Code safety and quality scoring
- ✅ **Integration Hub** - GitHub, Slack, webhooks, export/import

**Total:** 42 database tables, 15 UI tabs, 69 API endpoints

**Tests:** 92 comprehensive tests with 100% pass rate

---

## 💡 Which Option Should I Choose?

| Your Situation | Best Option |
|----------------|-------------|
| I'm new to programming | **Option 1** (Startup Scripts) |
| I want simplicity | **Option 1** (Startup Scripts) |
| I use this app often | **Option 3** (Desktop Shortcut) |
| I'm a developer | **Option 2** (Docker) |
| I need production deployment | **Option 2** (Docker) |
| I work on multiple projects | **Option 2** (Docker) |

---

## 🆘 Need More Help?

1. **Detailed Setup:** See the beginner's guide in previous documentation
2. **API Documentation:** Run `python api.py` to start the REST API
3. **Testing:** Run `pytest` to verify all 92 tests pass
4. **Database Schema:** Check individual `database*.py` files

---

## 🎉 Quick Test

After starting the app:

1. Go to **Skill Library** tab
2. Create a skill called `hello_world`
3. Code: `def greet(): return "Hello!"`
4. Click **Save Skill**
5. See it appear in "Existing Skills" ✅

**Success!** Your system is working perfectly.

---

**Made simpler with ❤️ - No more complex setup!**
