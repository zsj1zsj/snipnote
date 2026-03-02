#!/usr/bin/env python3
"""SnipNote Web UI Entry Point.

This module provides the main entry point for the web interface.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import FastAPI, fall back to old server if not available
try:
    from web.api import app
    import uvicorn

    if __name__ == "__main__":
        print("Starting SnipNote Web UI (FastAPI)...")
        uvicorn.run(app, host="127.0.0.1", port=8787, reload=False)
except ImportError:
    # Fall back to old server if FastAPI is not installed
    print("FastAPI not found, starting legacy web server...")
    from web.server import main

    if __name__ == "__main__":
        main()
