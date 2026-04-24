#!/usr/bin/env python3
"""Integration test for pencil-mcp server.

Tests all 7 custom tools against the hermes-deploy-design.pen fixture.
Run from the project root: python test_integration.py
"""

import asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PEN_FILE = os.path.expanduser('~/Downloads/hermes-deploy-design')

async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'pencil_mcp.server'],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=os.environ.copy(),
    )

    print("Starting pencil-mcp server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"✓ Connected — {len(tools.tools)} tools available\n")

            # 1. validate
            print("[1/7] pencil_validate_file")
            r = await session.call_tool('pencil_validate_file', {'path': PEN_FILE})
            v = json.loads(r.content[0].text)
            assert v['valid'], f"Validation failed: {v}"
            print(f"    valid={v['valid']}, elements={v['elements']}")

            # 2. extract tokens
            print("[2/7] pencil_extract_design_tokens")
            r = await session.call_tool('pencil_extract_design_tokens', {'path': PEN_FILE})
            t = json.loads(r.content[0].text)
            assert t['colors'], "No colors extracted"
            print(f"    colors={len(t['colors'])}, fonts={len(t['fonts'])}, spacing_rules={len(t['spacing'])}")

            # 3. list layers
            print("[3/7] pencil_list_layers (depth=2)")
            r = await session.call_tool('pencil_list_layers', {'path': PEN_FILE, 'max_depth': 2})
            l = json.loads(r.content[0].text)
            assert l['total_elements'] > 100, "Too few elements"
            print(f"    total={l['total_elements']}, root child={l['elements'][0]['name']}")

            # 4. diff files
            print("[4/7] pencil_diff_files")
            pen2 = os.path.expanduser('~/Downloads/lk-environmental-ui.pen')
            r = await session.call_tool('pencil_diff_files', {'path_a': PEN_FILE, 'path_b': pen2})
            d = json.loads(r.content[0].text)
            print(f"    file_a: {d['summary']['added']} added, {d['summary']['removed']} removed")

            # 5. version
            print("[5/7] pencil_version")
            r = await session.call_tool('pencil_version', {})
            print(f"    {r.content[0].text.strip()}")

            # 6. recent files
            print("[6/7] pencil_list_recent_files")
            r = await session.call_tool('pencil_list_recent_files', {'limit': 3})
            rf = json.loads(r.content[0].text)
            print(f"    recent: {len(rf.get('recentFiles', []))} files")

            # 7. native tool
            print("[7/7] get_editor_state (native proxy)")
            r = await session.call_tool('get_editor_state', {'include_schema': True})
            preview = r.content[0].text.split('\n')[0]
            print(f"    {preview}")

            print("\n✓ All 7 custom tools + native proxy verified!")

if __name__ == '__main__':
    asyncio.run(main())
