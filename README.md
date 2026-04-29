# pencil-mcp

> **Unofficial.** Community wrapper around the MCP server bundled with [Pencil](https://www.pencil.dev/) by High Agency, Inc. Not affiliated with or endorsed by High Agency. "Pencil" is their trademark; this project uses the name as a descriptor only.

A **hybrid MCP server** that spawns Pencil's bundled MCP binary and layers extra developer tools on top — file validation, design-token extraction, layer trees, structural diffs, and batch export.

Pencil already ships an MCP server out of the box. This project does **not** replace it; it proxies all 13 native tools and adds 7 utility tools that are convenient when scripting against `.pen` files from outside the app.

## Architecture

```
[MCP client] ─stdio MCP─► [pencil-mcp (Python)] ─stdio MCP─► [Pencil's bundled binary] ─WS─► [Pencil app]
                              │
                              └── 7 custom local tools (file utils, no app needed)
```

1. Spawns Pencil's own MCP binary (`mcp-server-darwin-arm64`) as a subprocess
2. Forwards all standard MCP tool calls (`batch_get`, `batch_design`, `get_editor_state`, …)
3. Handles 7 custom tools locally (validate / token extract / layer tree / diff / batch export / version / list recent)
4. Relies on Pencil's stored credentials — no extra auth setup

## Native tools (proxied from Pencil)

`batch_design`, `batch_get`, `export_nodes`, `find_empty_space_on_canvas`, `get_editor_state`, `get_guidelines`, `get_screenshot`, `get_variables`, `open_document`, `replace_all_matching_properties`, `search_all_unique_properties`, `set_variables`, `snapshot_layout`

## Custom tools (added by this server)

| Tool | Purpose |
|------|---------|
| `pencil_version` | Show binary path and server status |
| `pencil_list_recent_files` | List recent `.pen` files from Pencil's config |
| `pencil_validate_file` | Validate a `.pen` file's structure |
| `pencil_extract_design_tokens` | Extract colors, fonts, spacing, variables |
| `pencil_list_layers` | Hierarchical tree of all elements |
| `pencil_diff_files` | Structural diff between two `.pen` files |
| `pencil_batch_export` | Batch export to PNG/SVG via native `batch_export` |

## Installation

### Prerequisites
- macOS (Pencil ships an arm64 binary — Linux/Windows untested)
- [Pencil](https://www.pencil.dev/) installed at `/Applications/Pencil.app` (you need a valid Pencil account/license)
- Python 3.11+

### Setup
```bash
git clone <this repo>
cd pencil-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### MCP client config

```yaml
mcp_servers:
  pencil:
    command: pencil-mcp
    args:
      - --pencil-binary
      - /Applications/Pencil.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64
```

Restart your MCP client. All 20 tools (13 native + 7 custom) appear automatically.

## Usage

```bash
pencil_version
pencil_list_recent_files
pencil_validate_file --path "/path/to/file.pen"
pencil_extract_design_tokens --path "/path/to/file.pen"
pencil_list_layers --path "/path/to/file.pen" --max_depth 10
pencil_diff_files --path_a "v1.pen" --path_b "v2.pen"
pencil_batch_export --paths '["a.pen","b.pen"]' --format png --scale 2
```

## Open-source alternative

If you want a fully open-source design tool with built-in MCP (no closed-source binary in the loop), see [OpenPencil](https://openpencil.dev/) (MIT-licensed Figma-compatible alternative) or [ZSeven-W/openpencil](https://github.com/ZSeven-W/openpencil).

## License & disclaimers

- **Wrapper code:** MIT (see `LICENSE`)
- **Pencil's binary and `.pen` file format:** proprietary to High Agency, Inc. This project does **not** redistribute Pencil's binary, source, or assets. Users must install Pencil themselves and comply with [pencil.dev's Terms of Use](https://www.pencil.dev/terms-of-use).
- This is an independent community project. No affiliation with or endorsement by High Agency, Inc.

## Related design pattern

The proxy approach used here is documented as a generic skill at [desktop-app-mcp-proxy-pattern](https://github.com/<your-handle>/desktop-app-mcp-proxy-pattern) — applies to any Electron app that bundles its own MCP binary.
