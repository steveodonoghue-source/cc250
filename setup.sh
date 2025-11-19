#!/bin/bash
# AutoGen Multi-Agent System - One-Time Setup Script
# This script installs dependencies and initializes all databases

echo "================================================"
echo "AutoGen Multi-Agent System - Setup"
echo "================================================"
echo ""

# Check if Python is installed
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null
then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Found Python $PYTHON_VERSION"
echo ""

# Check if pip is installed
echo "Checking pip installation..."
if ! command -v pip3 &> /dev/null
then
    echo "❌ pip is not installed. Please install pip."
    exit 1
fi

echo "✅ pip is installed"
echo ""

# Install dependencies
echo "Installing Python packages..."
echo "This may take a few minutes..."
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies."
    exit 1
fi

echo ""
echo "✅ All packages installed successfully"
echo ""

# Initialize databases
echo "Initializing databases..."
python3 -c "
import database
import database_marketplace
import database_cost
import database_orchestration
import database_testing
import database_integrations
print('✅ All databases initialized successfully!')
"

if [ $? -ne 0 ]; then
    echo "❌ Failed to initialize databases."
    exit 1
fi

echo ""
echo "================================================"
echo "✅ Setup Complete!"
echo "================================================"
echo ""
echo "You can now run the application with:"
echo "  ./start.sh"
echo ""
echo "Or on Windows:"
echo "  start.bat"
echo ""
