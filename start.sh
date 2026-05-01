#!/bin/bash

# Start MCP servers in background
npx -y @modelcontextprotocol/server-fetch &
npx -y @modelcontextprotocol/server-filesystem /home/render &

# Change to backend directory since main.py is there
cd backend

# Start FastAPI
uvicorn main:app --host 0.0.0.0 --port 10000
