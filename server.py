#!/usr/bin/env python3
"""Entry point for running the MCP server."""

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Now import and expose the mcp server
from cert_speedrun.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run()
