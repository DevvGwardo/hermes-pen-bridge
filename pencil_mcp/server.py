#!/usr/bin/env python3
"""Main MCP server entry point.
Proxies unknown tools to Pencil's built-in MCP server and adds custom tools.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
    ToolAnnotation,
)

# ── Paths ──────────────────────────────────────────────────────────────────

DEFAULT_PENCIL_BINARY = (
    "/Applications/Pencil.app/Contents/Resources/app.asar.unpacked/"
    "out/mcp-server-darwin-arm64"
)

def get_pencil_binary() -> str:
    """Resolve the Pencil MCP binary path."""
    env_path = os.environ.get("PENCIL_MCP_BINARY")
    if env_path and Path(env_path).exists():
        return env_path

    default = Path(DEFAULT_PENCIL_BINARY)
    if default.exists():
        return str(default)

    for dirname in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(dirname) / "pencil-mcp-server"
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "Pencil MCP binary not found. Install Pencil or set PENCIL_MCP_BINARY."
    )

# ── Proxy Logic ─────────────────────────────────────────────────────────────

class PencilProxy:
    """Manages subprocess running Pencil's built-in MCP server."""

    def __init__(self, binary_path: str):
        self.binary_path = binary_path
        self.proc: Optional[subprocess.Popen] = None
        self._request_id = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            self.binary_path,
            "--app", "desktop",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        asyncio.create_task(self._log_stderr())
        await asyncio.sleep(2)
        await self._send_raw({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })

    async def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def _log_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break
            sys.stderr.write(f"[Pencil] {line.decode(errors='replace')}")
            sys.stderr.flush()

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        buffer = b""
        while True:
            chunk = await self.proc.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue
                req_id = msg.get("id")
                if req_id in self._pending:
                    self._pending.pop(req_id).set_result(msg)

    async def _send_raw(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        assert self.proc and self.proc.stdin
        msg_id = self._request_id
        self._request_id += 1
        msg["id"] = msg_id
        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self.proc.stdin.drain()
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise RuntimeError(f"Pencil MCP request timed out (id={msg_id})")

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resp = await self._send_raw({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        result = resp.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return {"content": "\n".join(texts), "isError": False}
        return {"content": str(result), "isError": False}

    async def list_tools(self) -> list:
        resp = await self._send_raw({"jsonrpc": "2.0", "method": "tools/list", "params": {}})
        return resp.get("result", {}).get("tools", [])

# ── Custom Tools ────────────────────────────────────────────────────────────

CUSTOM_TOOLS = {}

async def tool_pencil_version() -> CallToolResult:
    binary = get_pencil_binary()
    result = {"binary": binary, "status": "available"}
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])

async def tool_pencil_list_recent_files() -> CallToolResult:
    config_path = Path.home() / "Library/Application Support/Pencil/config.json"
    if not config_path.exists():
        return CallToolResult(
            content=[TextContent(type="text", text="Pencil config not found")],
            isError=True,
        )
    with open(config_path) as f:
        config = json.load(f)
    recent = config.get("recentFiles", [])
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps({"recentFiles": recent}, indent=2))]
    )

CUSTOM_TOOLS = {
    "pencil_version": tool_pencil_version,
    "pencil_list_recent_files": tool_pencil_list_recent_files,
}

# ── MCP Server ───────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Pencil MCP Server")
    parser.add_argument(
        "--pencil-binary",
        default=DEFAULT_PENCIL_BINARY,
        help="Path to Pencil mcp-server binary",
    )
    args = parser.parse_args()

    binary_path = get_pencil_binary()
    proxy = PencilProxy(binary_path)
    await proxy.start()

    server = Server("pencil-mcp")
    server._proxy = proxy  # type: ignore

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        pencil_tools = await proxy.list_tools()
        custom = [
            Tool(
                name="pencil_version",
                description="Return the Pencil MCP binary version and path.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="pencil_list_recent_files",
                description="List recently opened .pen files from Pencil config.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]
        return pencil_tools + custom

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None = None) -> list[TextContent]:
        arguments = arguments or {}

        if name in CUSTOM_TOOLS:
            result = await CUSTOM_TOOLS[name](**arguments)
            return [TextContent(type="text", text=result.content[0].text if result.content else "")]

        resp = await proxy.call_tool(name, arguments)
        return [TextContent(type="text", text=resp.get("content", str(resp)))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="pencil-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    read_stream, write_stream, server.NOTIFICATION_OPTIONS
                ),
            ),
        )

    await proxy.stop()

if __name__ == "__main__":
    asyncio.run(main())
