# Pencil MCP

**MCP server for Pencil (evolus.in)** - AI-powered design tool integration for Claude Code, Cursor, and any MCP client.

Pencil already ships its own MCP server. This project proxies to it, adding custom tools and a clean Python packaging layer.

## Features

- Full feature parity with Pencil's built-in MCP server (all 13 tools)
- Custom tools on top - version info, recent files, design validation
- Installable via `pip install pencil-mcp`
- Cross-platform Python - just point to your Pencil binary
- Open source - MIT licensed

## Quick Start

### 1. Install

```bash
pip install pencil-mcp
```

### 2. Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

{
  "mcpServers": {
    "pencil": {
      "command": "pencil-mcp"
    }
  }
}

Restart Claude Desktop. You now have 15 Pencil tools + 3 custom tools.

## Available Tools

### Built-in (proxied from Pencil)

- get_editor_state - current canvas, selection, document info
- open_document - open a .pen file or create new
- batch_get - read nodes by ID or pattern
- batch_design - insert/copy/update/replace/move/delete/image ops
- get_screenshot - screenshot a node
- export_nodes - export to PNG/JPEG/WEBP/PDF
- get_variables / set_variables - design tokens & themes
- get_guidelines - load design system guides
- find_empty_space_on_canvas - layout planning
- snapshot_layout - computed layout rectangles
- replace_all_matching_properties - batch property updates
- search_all_unique_properties - find property usages

### Custom (this wrapper)

- pencil_version - binary path and availability
- pencil_list_recent_files - recent .pen files
- pencil_validate_design - schema validation (coming soon)

## How It Works

1. Spawns Pencil's native mcp-server binary as a subprocess
2. Proxies all tool calls to the real server via stdio
3. Adds custom tools alongside Pencil's
4. No reverse-engineering - clean proxying

## Development

git clone https://github.com/yourname/pencil-mcp.git
cd pencil-mcp
pip install -e ".[dev]"

Run directly:
pencil-mcp --pencil-binary /Applications/Pencil.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64

## License

MIT
