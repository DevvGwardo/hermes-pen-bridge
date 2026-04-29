#!/usr/bin/env python3
"""hermes-pen-bridge — MCP bridge for the Pencil design tool.

Unofficial wrapper. Not affiliated with High Agency, Inc. ("Pencil" is their
trademark, used here descriptively only).

Architecture:
  - Spawns Pencil's bundled mcp-server-darwin-arm64 as a subprocess
  - Forwards all standard tool calls through (MCP proxy)
  - Handles custom local tools (validation, tokens, batch ops, etc.)
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ToolAnnotations

DEFAULT_BINARY = (
    "/Applications/Pencil.app/Contents/Resources/app.asar.unpacked/"
    "out/mcp-server-darwin-arm64"
)

def find_pencil_binary() -> str:
    env = os.environ.get("PENCIL_MCP_BINARY")
    if env and Path(env).exists():
        return env
    default = Path(DEFAULT_BINARY)
    if default.exists():
        return str(default)
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if Path(p, "pencil-mcp-server").exists():
            return str(Path(p, "pencil-mcp-server"))
    raise RuntimeError("Pencil binary not found. Set PENCIL_MCP_BINARY.")

# ─────────────────────────────────────────────────────────────────────────────
# Pencil subprocess manager
# ─────────────────────────────────────────────────────────────────────────────

class PencilProcess:
    def __init__(self, binary: str):
        self.binary = binary
        self.proc = None
        self._next_id = 1
        self._pending = {}

    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(
            self.binary, "--app", "desktop",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        asyncio.create_task(self._stderr_logger())
        asyncio.create_task(self._reader())
        await asyncio.sleep(1.5)  # let Pencil connect via WebSocket

    async def _stderr_logger(self):
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break
            sys.stderr.write(f"[Pencil] {line.decode(errors='replace')}")

    async def _reader(self):
        assert self.proc and self.proc.stdout
        buf = b""
        try:
            while True:
                chunk = await self.proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode())
                    except json.JSONDecodeError:
                        continue
                    rid = msg.get("id")
                    if rid is not None and rid in self._pending:
                        fut = self._pending.pop(rid)
                        if not fut.done():
                            fut.set_result(msg)
        except Exception as e:
            sys.stderr.write(f"[pencil-reader] error: {e}\n")

    def _next_req_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    async def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        assert self.proc and self.proc.stdin
        req_id = self._next_req_id()
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut
        try:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            await self.proc.stdin.drain()
        except Exception as e:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"Write to Pencil failed: {e}") from e
        try:
            return await asyncio.wait_for(fut, timeout=20)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"Timeout on {method} (id={req_id})")

    async def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except Exception:
                self.proc.kill()
                await self.proc.wait()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared by custom tools
# ─────────────────────────────────────────────────────────────────────────────

def parse_pen_file(path: str) -> dict:
    """Parse a .pen file (ZIP or plain JSON). Returns doc dict and asset list."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            # Try standard entry
            if "doc.json" in zf.namelist():
                doc = json.loads(zf.read("doc.json").decode("utf-8"))
                assets = [n for n in zf.namelist() if n != "doc.json"]
                return {"doc": doc, "assets": assets}
            for name in zf.namelist():
                if name.endswith(".json"):
                    doc = json.loads(zf.read(name).decode("utf-8"))
                    return {"doc": doc, "assets": zf.namelist()}
            raise ValueError("No JSON document found in .pen file")
    else:
        with open(p) as f:
            return {"doc": json.load(f), "assets": []}

def validate_pen_doc(doc: dict) -> List[str]:
    """Validate a parsed Pencil document structure. Returns error list."""
    errors = []
    if not isinstance(doc, dict):
        return ["Document root must be a JSON object"]
    if "children" not in doc:
        errors.append("Missing required field: children")
    children = doc.get("children", [])
    if not isinstance(children, list):
        errors.append("children must be an array")
    # Check each page/element for required fields
    seen_ids = set()
    def walk(node, depth=0):
        node_id = node.get("id")
        if node_id:
            if node_id in seen_ids:
                errors.append(f"Duplicate element id: {node_id}")
            else:
                seen_ids.add(node_id)
        # Required fields per node type
        for field in ["type", "id"]:
            if field not in node:
                errors.append(f"Node missing '{field}' at depth {depth}")
        for child in node.get("children", []):
            walk(child, depth + 1)
    for child in children:
        walk(child)
    return errors

def extract_design_tokens(doc: dict) -> dict:
    """Extract colors, fonts, spacing, and variables from a Pencil document."""
    result = {"colors": [], "fonts": [], "spacing": [], "variables": {}}
    color_usage = defaultdict(int)
    font_usage = defaultdict(int)
    spacing_usage = defaultdict(int)

    def norm_color(v):
        if isinstance(v, str):
            return {"type": "literal", "value": v}
        return {"type": "complex", "value": json.dumps(v, sort_keys=True)}

    def walk(node):
        for attr in ["fill", "stroke", "color", "backgroundColor"]:
            if attr in node:
                val = node[attr]
                key = json.dumps(norm_color(val), sort_keys=True)
                color_usage[key] += 1
        for attr in ["fontFamily", "fontSize", "fontWeight", "fontStyle"]:
            if attr in node:
                font_usage[str(node[attr])] += 1
        for attr in ["width", "height", "x", "y", "padding", "gap", "margin", "cornerRadius"]:
            if attr in node:
                val = node[attr]
                if isinstance(val, (int, float)):
                    spacing_usage[val] += 1
        for child in node.get("children", []):
            walk(child)

    for page in doc.get("children", []):
        walk(page)

    result["colors"] = sorted(
        [{"definition": json.loads(k), "usage_count": v} for k, v in color_usage.items()],
        key=lambda x: -x["usage_count"]
    )
    result["fonts"] = sorted(
        [{"value": k, "usage_count": v} for k, v in font_usage.items()],
        key=lambda x: -x["usage_count"]
    )
    result["spacing"] = sorted(
        [{"value": k, "usage_count": v} for k, v in spacing_usage.items()],
        key=lambda x: -x["usage_count"]
    )
    # Document-level variables
    result["variables"] = doc.get("variables", {})
    return result

def flatten_doc_tree(doc: dict, max_depth: int = 5) -> List[dict]:
    """Return flat list of all elements with path info."""
    flat = []
    def walk(node, path="", depth=0):
        nid = node.get("id", "(no-id)")
        ntype = node.get("type", "unknown")
        name = node.get("name", "")
        flat.append({
            "path": f"{path}/{ntype}[{nid}]" if path else f"/{ntype}[{nid}]",
            "id": nid,
            "type": ntype,
            "name": name,
            "properties": {k: v for k, v in node.items() if k not in ("children","id","type","x","y","width","height","layout")},
        })
        if depth >= max_depth or not node.get("children"):
            return
        for i, child in enumerate(node.get("children", [])):
            walk(child, f"{path}/{ntype}[{nid}]" if path else f"/{ntype}[{nid}]", depth + 1)
    for child in doc.get("children", []):
        walk(child)
    return flat

# ─────────────────────────────────────────────────────────────────────────────
# Custom tool definitions & handlers
# ─────────────────────────────────────────────────────────────────────────────

CUSTOM_TOOLS = {}

CUSTOM_TOOL_DEFS = [
    Tool(
        name="pencil_validate_file",
        description="Validate a .pen file's structure and report errors/warnings.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to .pen file (absolute or ~)"}
            },
            "required": ["path"],
        },
        annotations=ToolAnnotations(title="Validate .pen file", readOnlyHint=True),
    ),
    Tool(
        name="pencil_extract_design_tokens",
        description="Extract design tokens (colors, fonts, spacing, variables) from a .pen file.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to .pen file"},
                "include_variables": {"type": "boolean", "description": "Include raw variable definitions", "default": True}
            },
            "required": ["path"],
        },
        annotations=ToolAnnotations(title="Design Token Extraction", readOnlyHint=True),
    ),
    Tool(
        name="pencil_list_layers",
        description="Return a flat list/tree view of all layers and elements in a .pen file.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to .pen file"},
                "max_depth": {"type": "integer", "description": "Max recursion depth", "default": 10}
            },
            "required": ["path"],
        },
        annotations=ToolAnnotations(title="Layer Tree", readOnlyHint=True),
    ),
    Tool(
        name="pencil_batch_export",
        description="Export one or more .pen files to PNG/SVG using Pencil's native batch export.",
        inputSchema={
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "List of .pen file paths"},
                "format": {"type": "string", "enum": ["png", "svg"], "description": "Export format", "default": "png"},
                "output_dir": {"type": "string", "description": "Output directory (default: same dir as source)"},
                "scale": {"type": "number", "description": "Export scale factor (1 = 1x)", "default": 1.0}
            },
            "required": ["paths"],
        },
        annotations=ToolAnnotations(title="Batch Export", readOnlyHint=True),
    ),
    Tool(
        name="pencil_diff_files",
        description="Compare two .pen files at the structural level. Shows added/removed/changed elements.",
        inputSchema={
            "type": "object",
            "properties": {
                "path_a": {"type": "string", "description": "First .pen file path"},
                "path_b": {"type": "string", "description": "Second .pen file path"},
                "compare_properties": {"type": "boolean", "description": "Deep compare properties", "default": True}
            },
            "required": ["path_a", "path_b"],
        },
        annotations=ToolAnnotations(title="File Diff", readOnlyHint=True),
    ),
    Tool(
        name="pencil_version",
        description="Pencil binary path and integration status.",
        inputSchema={"type": "object", "properties": {}},
        annotations=ToolAnnotations(title="Pencil Version", readOnlyHint=True),
    ),
    Tool(
        name="pencil_list_recent_files",
        description="List recent .pen files from Pencil config.",
        inputSchema={"type": "object", "properties": {}},
        annotations=ToolAnnotations(title="Recent Files", readOnlyHint=True),
    ),
]

# Register custom tool handlers
async def _pencil_validate(args: dict) -> List[TextContent]:
    path = args.get("path", "")
    try:
        parsed = parse_pen_file(path)
    except Exception as e:
        return [TextContent(type="text", text=f"ERROR: {e}")]
    errors = validate_pen_doc(parsed["doc"])
    if errors:
        return [TextContent(type="text", text="Validation errors:\n" + "\n".join(f"  - {e}" for e in errors))]
    info = {
        "valid": True,
        "elements": sum(1 for _ in flatten_doc_tree(parsed["doc"])),
        "assets": len(parsed["assets"]),
        "variables": len(parsed["doc"].get("variables", {})),
    }
    return [TextContent(type="text", text=json.dumps(info, indent=2))]

async def _pencil_extract_tokens(args: dict) -> List[TextContent]:
    path = args.get("path", "")
    try:
        parsed = parse_pen_file(path)
    except Exception as e:
        return [TextContent(type="text", text=f"ERROR: {e}")]
    tokens = extract_design_tokens(parsed["doc"])
    # Trim variables if not requested
    if not args.get("include_variables", True):
        tokens["variables"] = {}
    return [TextContent(type="text", text=json.dumps(tokens, indent=2))]

async def _pencil_list_layers(args: dict) -> List[TextContent]:
    path = args.get("path", "")
    max_depth = args.get("max_depth", 10)
    try:
        parsed = parse_pen_file(path)
    except Exception as e:
        return [TextContent(type="text", text=f"ERROR: {e}")]
    flat = flatten_doc_tree(parsed["doc"], max_depth=max_depth)
    summary = {
        "path": path,
        "total_elements": len(flat),
        "elements": flat[:200],  # limit output
    }
    if len(flat) > 200:
        summary["truncated"] = True
        summary["showing"] = "first 200 of " + str(len(flat))
    return [TextContent(type="text", text=json.dumps(summary, indent=2))]

async def _pencil_batch_export(args: dict) -> List[TextContent]:
    paths = args.get("paths", [])
    fmt = args.get("format", "png")
    output_dir = args.get("output_dir", None)
    scale = args.get("scale", 1.0)
    # Use Pencil's native batch_export tool
    # Format params per Pencil's API
    results = []
    for path in paths:
        try:
            resp = await pencil.request("batch_export", {
                "files": [path],
                "format": fmt,
                "outputDir": output_dir or str(Path(path).parent),
                "scale": scale,
            })
            results.append({"file": path, "status": "ok", "result": resp.get("result", {})})
        except Exception as e:
            results.append({"file": path, "status": "error", "error": str(e)})
    return [TextContent(type="text", text=json.dumps(results, indent=2))]

async def _pencil_diff_files(args: dict) -> List[TextContent]:
    a_path = args.get("path_a", "")
    b_path = args.get("path_b", "")
    try:
        a = parse_pen_file(a_path)
        b = parse_pen_file(b_path)
    except Exception as e:
        return [TextContent(type="text", text=f"ERROR: {e}")]
    diff = {"added": [], "removed": [], "modified": [], "unchanged": []}
    a_flat = {e["id"]: e for e in flatten_doc_tree(a["doc"])}
    b_flat = {e["id"]: e for e in flatten_doc_tree(b["doc"])}
    all_ids = set(a_flat) | set(b_flat)
    for eid in all_ids:
        if eid not in a_flat:
            diff["added"].append(b_flat[eid])
        elif eid not in b_flat:
            diff["removed"].append(a_flat[eid])
        elif a_flat[eid] != b_flat[eid]:
            diff["modified"].append({"id": eid, "before": a_flat[eid], "after": b_flat[eid]})
        else:
            diff["unchanged"].append(eid)
    summary = {
        "file_a": a_path,
        "file_b": b_path,
        "summary": {k: len(v) for k, v in diff.items()},
        "details": diff,
    }
    return [TextContent(type="text", text=json.dumps(summary, indent=2))]

async def _pencil_version(args: dict) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "binary": find_pencil_binary(),
        "status": "running",
        "server": "hermes-pen-bridge v0.1.0"
    }, indent=2))]

async def _pencil_list_recent(args: dict) -> List[TextContent]:
    cfg = Path.home() / "Library/Application Support/Pencil/config.json"
    if not cfg.exists():
        return [TextContent(type="text", text="Pencil config not found")]
    with open(cfg) as f:
        data = json.load(f)
    return [TextContent(type="text", text=json.dumps({
        "recentFiles": data.get("recentFiles", [])
    }, indent=2))]

CUSTOM_TOOLS.update({
    "pencil_validate_file": _pencil_validate,
    "pencil_extract_design_tokens": _pencil_extract_tokens,
    "pencil_list_layers": _pencil_list_layers,
    "pencil_batch_export": _pencil_batch_export,
    "pencil_diff_files": _pencil_diff_files,
    "pencil_version": _pencil_version,
    "pencil_list_recent_files": _pencil_list_recent,
})

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

pencil: Optional[PencilProcess] = None

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pencil-binary", default=DEFAULT_BINARY)
    args = parser.parse_args()

    binary = find_pencil_binary()
    sys.stderr.write(f"[server] using Pencil binary: {binary}\n")

    global pencil
    pencil = PencilProcess(binary)
    await pencil.start()

    server = Server("hermes-pen-bridge")
    server._pencil = pencil  # type: ignore

    @server.list_tools()
    async def _list_tools() -> List[Tool]:
        try:
            resp = await pencil.request("tools/list", {})
            native_raw = resp.get("result", {}).get("tools", [])
            native = [
                Tool(
                    name=t["name"],
                    description=t.get("description", ""),
                    inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
                    annotations=ToolAnnotations(title=t.get("name"), readOnlyHint=True),
                )
                for t in native_raw
            ]
        except Exception as e:
            sys.stderr.write(f"[server] list_tools error: {e}\n")
            native = []
        return native + CUSTOM_TOOL_DEFS

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any] | None = None) -> List[TextContent]:
        arguments = arguments or {}
        try:
            if name in CUSTOM_TOOLS:
                return await CUSTOM_TOOLS[name](arguments)
            return await pencil_call(name, arguments)
        except Exception as e:
            return [TextContent(type="text", text=f"ERROR: {e}")]

    async def pencil_call(name: str, args: Dict[str, Any]) -> List[TextContent]:
        resp = await pencil.request("tools/call", {"name": name, "arguments": args})
        result = resp.get("result", {})
        content = result.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return [TextContent(type="text", text="\n".join(texts))]

    try:
        async with stdio_server() as (rs, ws):
            await server.run(
                rs, ws,
                InitializationOptions(
                    server_name="hermes-pen-bridge",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        NotificationOptions(prompts_changed=False, resources_changed=False, tools_changed=False),
                        {},
                    ),
                ),
                raise_exceptions=False,
            )
    except Exception as e:
        sys.stderr.write(f"[server] fatal: {e}\n")
        raise
    finally:
        await pencil.stop()

def cli():
    """Synchronous entrypoint for console_scripts."""
    asyncio.run(main())

if __name__ == "__main__":
    cli()
