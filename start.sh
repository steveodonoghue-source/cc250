#!/bin/bash
# AutoGen Multi-Agent System - Startup Script
# Run this script to start the application

echo "================================================"
echo "AutoGen Multi-Agent System"
echo "================================================"
echo ""
echo "Starting Streamlit application..."
echo ""
echo "The app will open in your browser at:"
echo "  http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the application"
echo ""
echo "================================================"
echo ""

# Start Streamlit
python3 -m streamlit run streamlit_app.py

# If streamlit command fails, try direct execution
if [ $? -ne 0 ]; then
    echo "Trying alternative startup method..."
    streamlit run streamlit_app.py
fi
