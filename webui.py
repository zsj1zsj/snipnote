#!/usr/bin/env python3
"""Backward compatibility wrapper for Web UI.

This module provides backward compatibility for the webui.py entry point.
"""
# Re-export main from web module
from web.server import main

if __name__ == "__main__":
    main()
