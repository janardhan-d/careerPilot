"""
CareerPilot — Server Launcher & Watchdog
"""
import sys
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, log_level="warning")
