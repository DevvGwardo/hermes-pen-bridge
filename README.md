# Pencil MCP Server

A **hybrid MCP server** that exposes Pencil (by Evolus) design tool's built-in 13 tools via the Model Context Protocol, plus 7 custom developer tools for working with `.pen` files and design systems.

## Architecture

```
[Claude Desktop / Any MCP Client]
            ↓ (stdio MCP)
    ┌─────────────────────┐
    │  pencil-mcp (Python)│ ← 15 tools (13 native + 7 custom)
    └──────────┬──────────┘
               │ spawns
    ┌──────────▼──────────┐
    │  Pencil binary      │
    │  mcp-server-darwin  │ → WebSocket → Pencil main app
    └─────────────────────┘
```

The server:
1. **Spawns Pencil's own MCP binary** (`mcp-server-darwin-arm64`) as a subprocess
2. **Forwards** all standard MCP tool calls to Pencil (batch_get, batch_design, get_editor_state, etc.)
3. **Handles locally** custom tools for file operations, validation, token extraction, diffing, and batch export
4. **Keeps Pencil authenticated** via its stored credentials (no extra setup)

## Features

### Native Pencil Tools (proxied)
- `batch_design` — apply batch design changes
- `batch_get` — batch fetch multiple document properties
- `export_nodes` — export elements
- `find_empty_space_on_canvas` — collision/gap detection
- `get_editor_state` — current editor and document info
- `get_guidelines` — canvas guidelines
- `get_screenshot` — canvas/in-page screenshots
- `get_variables` — document variable definitions
- `open_document` — open a .pen file
- `replace_all_matching_properties` — mass property replacement
- `search_all_unique_properties` — search for properties
- `set_variables` — update document variables
- `snapshot_layout` — capture layout state

### Custom Tools (server-side)
| Tool | Purpose |
|------|---------|
| `pencil_version` | Show binary path and server status |
| `pencil_list_recent_files` | List recent .pen files from Pencil's config |
| `pencil_validate_file` | Validate a .pen file's structure |
| `pencil_extract_design_tokens` | Extract colors, fonts, spacing, and variables |
| `pencil_list_layers` | Hierarchical tree of all elements in a document |
| `pencil_diff_files` | Structural diff between two .pen files |
| `pencil_batch_export` | Export multiple .pen files to PNG/SVG |

## Installation

### Prerequisites
- macOS (Pencil is macOS-only)
- Pencil by Evolus installed at `/Applications/Pencil.app`
- Python 3.11+
- `mcp` SDK: `pip install mcp`

### Setup
```bash
cd pencil-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install mcp
```

### Claude Desktop / Hermes

Add to your MCP server config:

```yaml
mcp_servers:
  pencil:
    command: "/full/path/to/pencil-mcp/pencil_mcp/server.py"
    args: ["--pencil-binary", "/Applications/Pencil.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64"]
```

Restart Claude Desktop. All 15 tools appear automatically.

## Usage Examples

### Check server status
```bash
pencil_version
```

### List recent Pencil files
```bash
pencil_list_recent_files
```

### Validate a .pen file
```bash
pencil_validate_file --path "/path/to/file.pen"
```

### Extract design tokens
```bash
pencil_extract_design_tokens --path "/path/to/file.pen"
```

Output includes all unique colors (with variable references resolved), font stacks, spacing values, and document-level variables.

### View document layer tree
```bash
pencil_list_layers --path "/path/to/file.pen" --max_depth 10
```

Returns hierarchical paths like `/frame[Sf9oC]/text[0I0FC]`.

### Diff two versions
```bash
pencil_diff_files --path_a "v1.pen" --path_b "v2.pen"
```

Shows count of added, removed, modified, and unchanged elements.

### Batch export
```bash
pencil_batch_export --paths ["a.pen","b.pen"] --format png --scale 2
```

Uses Pencil's native `batch_export` under the hood.

## Development

### Run directly
```bash
python pencil_mcp/server.py --pencil-binary /Applications/Pencil.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64
```

### Add a custom tool

Edit `pencil_mcp/server.py`:

```python
async def tool_my_feature(args: dict) -> List[TextContent]:
    # implement
    return [TextContent(type="text", text="result")]

CUSTOM_TOOLS["my_feature"] = tool_my_feature
CUSTOM_TOOL_DEFS.append(Tool(...))
```

## License

MIT (wrapper code only; Pencil is proprietary).

