import test from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.js";

const env = { JARVIS_MCP_TOKEN: "test-token", JARVIS_HEALTH_URL: "https://health.invalid/health" };
const request = (body, headers = {}) => new Request("https://jarvis.test/mcp", {
  method: "POST",
  headers: { "content-type": "application/json", authorization: "Bearer test-token", ...headers },
  body: typeof body === "string" ? body : JSON.stringify(body),
});

test("health endpoint is public and reports transport", async () => {
  const response = await worker.fetch(new Request("https://jarvis.test/health"), env);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    service: "jarvis-unified-mcp",
    status: "ok",
    transport: "streamable-http",
  });
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("MCP endpoint rejects missing and invalid bearer tokens", async () => {
  const missing = await worker.fetch(request({ jsonrpc: "2.0", id: 1, method: "ping" }, { authorization: "" }), env);
  assert.equal(missing.status, 401);
  const invalid = await worker.fetch(request({ jsonrpc: "2.0", id: 1, method: "ping" }, { authorization: "Bearer wrong" }), env);
  assert.equal(invalid.status, 401);
});

test("MCP endpoint rejects non-JSON requests", async () => {
  const response = await worker.fetch(new Request("https://jarvis.test/mcp", {
    method: "POST",
    headers: { authorization: "Bearer test-token", "content-type": "text/plain" },
    body: "ping",
  }), env);
  assert.equal(response.status, 415);
});

test("initialize negotiates the supported protocol and advertises read-only tools", async () => {
  const response = await worker.fetch(request({
    jsonrpc: "2.0", id: 1, method: "initialize",
    params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "1" } },
  }), env);
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.result.protocolVersion, "2025-06-18");
  assert.equal(payload.result.serverInfo.name, "jarvis-unified-mcp");
  assert.match(payload.result.instructions, /read-only/i);
});

test("tools/list exposes only health and runtime capability inspection", async () => {
  const response = await worker.fetch(request({ jsonrpc: "2.0", id: 2, method: "tools/list" }), env);
  const payload = await response.json();
  assert.deepEqual(payload.result.tools.map((tool) => tool.name), [
    "jarvis_health",
    "jarvis_runtime_capabilities",
  ]);
});

test("runtime capabilities explicitly keep all trading paper-only", async () => {
  const response = await worker.fetch(request({
    jsonrpc: "2.0", id: 3, method: "tools/call",
    params: { name: "jarvis_runtime_capabilities", arguments: {} },
  }), env);
  const payload = await response.json();
  const result = JSON.parse(payload.result.content[0].text);
  assert.equal(payload.result.isError, false);
  assert.equal(result.operating_mode, "paper");
  assert.equal(result.live_trading, "disabled_by_design");
  assert.equal(result.execution_runtime, "control_plane_only");
  assert.match(result.data_boundary, /does not expose private ledger rows/i);
});

test("oversized JSON-RPC payloads are rejected", async () => {
  const oversized = JSON.stringify({ jsonrpc: "2.0", id: 4, method: "ping", padding: "x".repeat(66_000) });
  const response = await worker.fetch(request(oversized), env);
  assert.equal(response.status, 413);
});

test("unknown JSON-RPC methods return method-not-found", async () => {
  const response = await worker.fetch(request({ jsonrpc: "2.0", id: 5, method: "not/a/method" }), env);
  const payload = await response.json();
  assert.equal(payload.error.code, -32601);
});

test("invalid JSON returns a parse error", async () => {
  const response = await worker.fetch(request("{not-json"), env);
  const payload = await response.json();
  assert.equal(payload.error.code, -32700);
});
