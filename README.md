# hermes-pen-bridge

> **Unofficial.** Community MCP bridge for the [Pencil](https://www.pencil.dev/) design tool, built primarily for [Hermes](https://github.com/NousResearch) but compatible with any MCP client. Not affiliated with or endorsed by High Agency, Inc. "Pencil" is their trademark; this project uses the name descriptively only.

A **hybrid MCP server** that spawns Pencil's bundled MCP binary and layers extra developer tools on top — file validation, design-token extraction, layer trees, structural diffs, and batch export.

Pencil already ships an MCP server out of the box. This project doesn't replace it — it proxies all 13 native tools through unchanged and adds 7 utility tools that are convenient when scripting against `.pen` files from outside the app.

## Architecture

```
[MCP client] ─stdio MCP─► [hermes-pen-bridge] ─stdio MCP─► [Pencil's bundled binary] ─WS─► [Pencil app]
                              │
                              └── 7 custom local tools (file utils)
```

1. Spawns Pencil's own MCP binary (`mcp-server-darwin-arm64`) as a subprocess
2. Forwards all standard MCP tool calls (`batch_get`, `batch_design`, `get_editor_state`, …)
3. Handles 7 custom tools locally
4. Relies on Pencil's stored credentials — no extra auth setup

## Why "for Hermes"?

Hermes (Nous Research's local agent) is the primary audience — it's where this was first used. The server itself is provider-agnostic standard MCP and works fine with Claude Desktop, Cursor, Claude Code, and any other MCP client. The "Hermes-first" framing is about who we're solving for, not a technical lock-in.

## Native tools (proxied)

`batch_design`, `batch_get`, `export_nodes`, `find_empty_space_on_canvas`, `get_editor_state`, `get_guidelines`, `get_screenshot`, `get_variables`, `open_document`, `replace_all_matching_properties`, `search_all_unique_properties`, `set_variables`, `snapshot_layout`

## Custom tools

| Tool | Purpose |
|------|---------|
| `pencil_version` | Show binary path and server status |
| `pencil_list_recent_files` | List recent `.pen` files from Pencil's config |
| `pencil_validate_file` | Validate a `.pen` file's structure |
| `pencil_extract_design_tokens` | Extract colors, fonts, spacing, variables |
| `pencil_list_layers` | Hierarchical tree of all elements |
| `pencil_diff_files` | Structural diff between two `.pen` files |
| `pencil_batch_export` | Batch export to PNG/SVG |

(Tool names retain the `pencil_` prefix because they operate on `.pen` files — descriptive, not a brand claim.)

## Installation

### Prerequisites
- macOS (Pencil ships an arm64 binary)
- [Pencil](https://www.pencil.dev/) installed at `/Applications/Pencil.app` with a valid account/license
- Python 3.11+

### Setup
```bash
git clone https://github.com/devvgwardo/hermes-pen-bridge
cd hermes-pen-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## MCP client configs

### Hermes (`~/.hermes/config.yaml`)
```yaml
mcp_servers:
  pen-bridge:
    command: hermes-pen-bridge
    args:
      - --pencil-binary
      - /Applications/Pencil.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64
    tools: all
```

### Claude Desktop / Cursor / Claude Code
```json
{
  "mcpServers": {
    "pen-bridge": {
      "command": "hermes-pen-bridge",
      "args": ["--pencil-binary", "/Applications/Pencil.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64"]
    }
  }
}
```

Restart the client. All 20 tools (13 native + 7 custom) appear automatically.

## Usage

```text
pencil_version
pencil_list_recent_files
pencil_validate_file --path "/path/to/file.pen"
pencil_extract_design_tokens --path "/path/to/file.pen"
pencil_list_layers --path "/path/to/file.pen" --max_depth 10
pencil_diff_files --path_a "v1.pen" --path_b "v2.pen"
pencil_batch_export --paths '["a.pen","b.pen"]' --format png --scale 2
```

## Open-source alternative

If you want a fully open-source design tool with built-in MCP (no closed-source binary in the loop), see [OpenPencil](https://openpencil.dev/) or [ZSeven-W/openpencil](https://github.com/ZSeven-W/openpencil).

## License & disclaimers

- **Wrapper code:** MIT (see `LICENSE`)
- **Pencil's binary and `.pen` file format:** proprietary to High Agency, Inc. This project does not redistribute Pencil's binary, source, or assets. Users must install Pencil themselves and comply with [pencil.dev's Terms of Use](https://www.pencil.dev/terms-of-use).
- This is an independent community project. No affiliation with or endorsement by High Agency, Inc.

## Related: the design pattern

The proxy approach used here is documented as a generic skill at [desktop-app-mcp-proxy-pattern](https://github.com/devvgwardo/desktop-app-mcp-proxy-pattern) — applies to any Electron app that bundles its own MCP binary.
