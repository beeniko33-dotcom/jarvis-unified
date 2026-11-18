const SERVER_INFO = { name: "jarvis-unified-mcp", version: "0.1.0" };
const PROTOCOL_VERSION = "2025-06-18";
const TOOLS = [
  {
    name: "jarvis_health",
    description: "Read the health endpoint of the existing Jarvis Cloudflare control worker. Reports only what that endpoint actually confirms.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  },
  {
    name: "jarvis_runtime_capabilities",
    description: "Describe verified Jarvis runtime boundaries, including paper-first mode and unavailable execution features.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false }
  }
];

function jsonRpc(id, result) {
  return Response.json({ jsonrpc: "2.0", id, result }, {
    headers: { "cache-control": "no-store" }
  });
}
function rpcError(id, code, message) {
  return Response.json({ jsonrpc: "2.0", id, error: { code, message } }, {
    headers: { "cache-control": "no-store" }
  });
}
function safeEqual(a, b) {
  const left = new TextEncoder().encode(a);
  const right = new TextEncoder().encode(b);
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i++) diff |= left[i] ^ right[i];
  return diff === 0;
}
function textResult(value) {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] };
}
async function callTool(name, env) {
  if (name === "jarvis_health") {
    const target = env.JARVIS_HEALTH_URL;
    if (!target) throw new Error("health_endpoint_not_configured");
    const response = await fetch(target, {
      method: "GET",
      headers: { "accept": "application/json" },
      signal: AbortSignal.timeout(8000)
    });
    const raw = await response.text();
    let body;
    try { body = JSON.parse(raw); } catch { body = { response_text: raw.slice(0, 1000) }; }
    return { upstream_http_status: response.status, reachable: response.ok, health: body };
  }
  if (name === "jarvis_runtime_capabilities") {
    return {
      repository: "beeniko33-dotcom/jarvis-unified",
      operating_mode: "paper",
      live_trading: "disabled_by_design",
      execution_runtime: "control_plane_only",
      paper_session_execution: "disabled_pending_postgres_migration",
      remote_command_queue: ["pause_entries", "resume_entries", "engage_kill_switch", "run_paper_session"],
      command_worker_behavior: "run_paper_session is explicitly rejected; resume_entries is refused while kill switch is engaged",
      data_boundary: "This MCP release exposes health and capability metadata only. It does not expose private ledger rows, broker credentials, or trade execution.",
      source_of_truth: "Repository README and deployed control-worker health endpoint"
    };
  }
  throw new Error("unknown_tool");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") {
      return Response.json({ service: SERVER_INFO.name, status: "ok", transport: "streamable-http" }, {
        headers: { "cache-control": "no-store" }
      });
    }
    if (url.pathname !== "/mcp") return new Response("Not found", { status: 404 });
    if (request.method === "OPTIONS") return new Response(null, { status: 204 });
    if (request.method !== "POST") {
      return new Response("Streamable HTTP MCP accepts POST requests at /mcp", {
        status: 405, headers: { allow: "POST, OPTIONS", "cache-control": "no-store" }
      });
    }
    const auth = request.headers.get("authorization") || "";
    const expected = env.JARVIS_MCP_TOKEN;
    if (!expected || !auth.startsWith("Bearer ") || !safeEqual(auth.slice(7), expected)) {
      return new Response("Unauthorized: configure the static Authorization header", { status: 401, headers: { "cache-control": "no-store" } });
    }
    const contentType = request.headers.get("content-type") || "";
    if (!contentType.toLowerCase().includes("application/json")) {
      return new Response("Content-Type must be application/json", { status: 415 });
    }
    const raw = await request.text();
    if (new TextEncoder().encode(raw).length > 65536) return new Response("Request too large", { status: 413 });
    let message;
    try { message = JSON.parse(raw); } catch { return rpcError(null, -32700, "Parse error"); }
    if (!message || typeof message !== "object" || Array.isArray(message) || message.jsonrpc !== "2.0" || typeof message.method !== "string") {
      return rpcError(message?.id ?? null, -32600, "Invalid Request");
    }
    const id = Object.prototype.hasOwnProperty.call(message, "id") ? message.id : undefined;
    if (id === undefined) return new Response(null, { status: 202 });
    const params = message.params && typeof message.params === "object" ? message.params : {};
    try {
      if (message.method === "initialize") {
        return jsonRpc(id, {
          protocolVersion: PROTOCOL_VERSION,
          capabilities: { tools: { listChanged: false } },
          serverInfo: SERVER_INFO,
          instructions: "Jarvis MCP is initially read-only. Use jarvis_health and jarvis_runtime_capabilities. Trading execution is not exposed."
        });
      }
      if (message.method === "ping") return jsonRpc(id, {});
      if (message.method === "tools/list") return jsonRpc(id, { tools: TOOLS });
      if (message.method === "tools/call") {
        if (typeof params.name !== "string") return rpcError(id, -32602, "Tool name is required");
        const value = await callTool(params.name, env);
        return jsonRpc(id, { ...textResult(value), isError: false });
      }
      if (message.method === "resources/list") return jsonRpc(id, { resources: [] });
      if (message.method === "prompts/list") return jsonRpc(id, { prompts: [] });
      return rpcError(id, -32601, "Method not found");
    } catch (error) {
      const messageText = error instanceof Error ? error.message : "Tool failed";
      return jsonRpc(id, { ...textResult({ error: messageText }), isError: true });
    }
  }
};
