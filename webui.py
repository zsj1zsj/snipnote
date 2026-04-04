#!/usr/bin/env python3
"""SnipNote Web UI Entry Point.

This module provides the main entry point for the web interface.
"""
import argparse
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args():
    parser = argparse.ArgumentParser(description="SnipNote Web UI")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default=None)
    return parser.parse_args()


# Try to import FastAPI, fall back to old server if not available
try:
    from web.api import app
    import uvicorn

    if __name__ == "__main__":
        args = parse_args()
        if args.db:
            os.environ["SNIPNOTE_DB"] = args.db
        print(f"Starting SnipNote Web UI (FastAPI) on {args.host}:{args.port} ...")
        uvicorn.run(app, host=args.host, port=args.port, reload=False)
except ImportError:
    # Fall back to old server if FastAPI is not installed
    print("FastAPI not found, starting legacy web server...")
    from web.server import main

    if __name__ == "__main__":
        main()
