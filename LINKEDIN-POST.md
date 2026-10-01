Stop reverse-engineering Electron app auth.

If the app already ships an MCP binary, the cleaner move is usually to spawn that binary as a subprocess and proxy stdio.

That was the unlock.

I wanted Hermes by Nous Research to control Pencil by pencil.dev from my local workflow.

At first, the tempting path was the usual one: inspect the app, trace auth, peel apart private integration details, and try to fake being the official client.

That's the wrong abstraction.

Pencil already bundles the thing I needed.

So instead of fighting the app, I let the app do its job:
→ start the bundled MCP server
→ proxy the tools
→ add the extra utilities I wanted on top
→ keep it usable from Hermes or any other MCP client

That became repo #1: hermes-pen-bridge

A Hermes-first MCP bridge for Pencil that proxies all 13 native tools and adds 7 custom .pen file utilities I kept wanting in agentic design workflows:
- validation
- design-token extraction
- layer trees
- structural diff
- batch export

MIT-licensed, unofficial. Works cleanly because it stays close to the grain of the host app instead of trying to outsmart it.

The more interesting part is that this pattern clearly generalizes.

A lot of Electron apps are going to ship local MCP capabilities. When they do, the integration story should not start with reverse-engineering. It should start with: what binary is already there, how is it launched, what goes over stdio, and how do we wrap that safely for the agent stack we actually use?

So I split that lesson into repo #2: desktop-app-mcp-proxy-pattern

The generic pattern doc — how to build MCP integrations around any Electron app with a bundled MCP binary. Discovery, transports (stdio/HTTP/WS), subprocess management, common pitfalls.

Main idea, restated:
Don't reverse-engineer the auth.
Don't rebuild the server.
Spawn the bundled binary and proxy it.

If you're working on Hermes, MCP tooling, or local agent workflows that need to reach into desktop apps, this is the direction I'd push you to explore first.

🔗 github.com/DevvGwardo/hermes-pen-bridge
🔗 github.com/DevvGwardo/desktop-app-mcp-proxy-pattern

#MCP #Hermes #OpenSource
