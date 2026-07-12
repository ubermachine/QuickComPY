#!/bin/bash
# Check if PORT environment variable is set (Render uses this)
# Since Render binds to PORT, we should bind Streamlit to it.
# The backend will run on 5000 internally.

# Start FastAPI backend in the background
python backend_py/server.py &

# Wait a second for backend
sleep 2

# Start Streamlit frontend
streamlit run streamlit/app.py --server.port ${PORT:-10000} --server.address 0.0.0.0
