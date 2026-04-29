#!/bin/bash
set -e
echo "Installing hermes-pen-bridge..."
pip install -e .
echo "Done. Add to your MCP client config:"
echo '  "pen-bridge": { "command": "hermes-pen-bridge" }'
