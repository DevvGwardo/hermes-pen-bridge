#!/bin/bash
set -e
echo "Installing pencil-mcp..."
pip install -e .
echo "Done. Add to your MCP client config:"
echo '  "pencil-mcp": { "command": "pencil-mcp" }'
