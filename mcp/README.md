# Jarvis Unified MCP

A minimal, stateless Model Context Protocol server for Jarvis Unified, deployed as a separate Cloudflare Worker. It uses Streamable HTTP at `/mcp` and does not modify the existing control worker.

## Initial tools

- `jarvis_health`: calls the existing control worker's public `/health` endpoint.
- `jarvis_runtime_capabilities`: reports repository-verified runtime and safety boundaries.

This first release is read-only. It does not read private database tables, expose credentials, enqueue commands, start paper sessions, or execute live trades.

## Configuration

Required Worker secrets:
- `JARVIS_MCP_TOKEN`: a dedicated bearer token; do not reuse collector, ingest, Supabase, or GitHub credentials.

Required variable:
- `JARVIS_HEALTH_URL`: the existing control worker's `/health` URL.

## Connect

- MCP URL: `https://jarvis-unified-mcp.<your-workers-dev-subdomain>.workers.dev/mcp`
- Header name: `Authorization`
- Header value: `Bearer <JARVIS_MCP_TOKEN>`

## Protocol

Stateless JSON-RPC over Streamable HTTP. Supports `initialize`, `ping`, `tools/list`, `tools/call`, `resources/list`, and `prompts/list`. Requires authenticated POST requests and enforces a 64 KiB request limit.

## Local smoke test

After setting `JARVIS_MCP_TOKEN` and `JARVIS_HEALTH_URL` in the local Worker environment:

```sh
curl -i https://<worker-host>/health
curl -i https://<worker-host>/mcp \
  -H 'Authorization: Bearer <JARVIS_MCP_TOKEN>' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke-test","version":"1.0"}}}'
```

Keep the MCP token private. Rotate it by updating the Cloudflare Worker secret.
