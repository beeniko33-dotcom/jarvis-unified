import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const ALLOWED_ORIGINS = new Set(["https://jarvis-control-panel.pages.dev"]);
const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };
const MAX_BODY_BYTES = 8192;
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

function cors(req: Request) {
  const origin = req.headers.get("origin") ?? "";
  const permitted = ALLOWED_ORIGINS.has(origin)
    || /^https:\/\/[a-z0-9-]+\.jarvis-control-panel\.pages\.dev$/.test(origin);
  return permitted ? {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "authorization, apikey, content-type, x-client-info",
    "access-control-max-age": "86400",
    "vary": "Origin",
  } : {};
}

function reply(req: Request, status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...cors(req) } });
}

function decodeBase58(value: string): Uint8Array {
  if (!value || value.length > 44) throw new Error("invalid_wallet_address");
  let number = 0n;
  for (const char of value) {
    const digit = B58.indexOf(char);
    if (digit < 0) throw new Error("invalid_wallet_address");
    number = number * 58n + BigInt(digit);
  }
  const bytes: number[] = [];
  while (number > 0n) {
    bytes.push(Number(number & 255n));
    number >>= 8n;
  }
  bytes.reverse();
  let leading = 0;
  while (leading < value.length && value[leading] === "1") leading++;
  const result = new Uint8Array(leading + bytes.length);
  result.set(bytes, leading);
  if (result.length !== 32) throw new Error("wallet_public_key_must_be_32_bytes");
  return result;
}

function decodeBase64(value: string): Uint8Array {
  if (!value || value.length > 256 || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) throw new Error("invalid_signature_encoding");
  const binary = atob(value);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function sha256(value: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", value);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { status: 200, headers: cors(req) });
  if (req.method !== "POST") return reply(req, 405, { error: "method not allowed" });

  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(req, 401, { error: "sign in required" });
  const url = Deno.env.get("SUPABASE_URL");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  let secretKeys: Record<string,string> = {};\n  try { secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}"); } catch { /* use the legacy service-role fallback */ }\n  const serviceKey = secretKeys.default ?? Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anon || !serviceKey) return reply(req, 503, { error: "wallet service is not configured" });

  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return reply(req, 413, { error: "request too large" });
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("invalid");
  } catch {
    return reply(req, 400, { error: "invalid JSON" });
  }

  const userClient = createClient(url, anon, {
    global: { headers: { Authorization: auth } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userError } = await userClient.auth.getUser(auth.slice("Bearer ".length));
  if (userError || !userData.user) return reply(req, 401, { error: "invalid or expired session" });
  const userId = userData.user.id;
  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

  if (body.action === "get_wallet") {
    if (Object.keys(body).some((key) => key !== "action")) return reply(req, 400, { error: "unexpected field" });
    const { data, error } = await admin.rpc("jarvis_solana_get_wallet", { p_user_id: userId });
    if (error) return reply(req, 503, { error: "wallet status unavailable" });
    return reply(req, 200, data);
  }

  if (body.action === "create_challenge") {
    if (Object.keys(body).some((key) => key !== "action")) return reply(req, 400, { error: "unexpected field" });
    const random = crypto.getRandomValues(new Uint8Array(32));
    const nonce = [...random].map((b) => b.toString(16).padStart(2, "0")).join("");
    const issued = new Date();
    const expires = new Date(issued.getTime() + 3 * 60 * 1000);
    const message = [
      "Jarvis Unified — Solana Devnet wallet verification",
      "Network: Solana Devnet",
      "Account: " + userId,
      "Nonce: " + nonce,
      "Issued: " + issued.toISOString(),
      "Expires: " + expires.toISOString(),
      "Purpose: prove control of this public wallet only. No funds will be transferred. No token will be minted.",
    ].join("\n");
    const { data, error } = await admin.rpc("jarvis_solana_create_wallet_challenge", {
      p_user_id: userId,
      p_nonce: nonce,
      p_message: message,
      p_expires_at: expires.toISOString(),
    });
    if (error) return reply(req, 503, { error: "wallet challenge could not be created" });
    return reply(req, 200, data);
  }

  if (body.action === "verify_wallet") {
    const allowed = ["action", "challenge_id", "nonce", "wallet_address", "signature"];
    if (Object.keys(body).some((key) => !allowed.includes(key))) return reply(req, 400, { error: "unexpected field" });
    const { challenge_id, nonce, wallet_address, signature } = body;
    if (typeof challenge_id !== "string" || !/^[0-9a-f-]{36}$/i.test(challenge_id)
        || typeof nonce !== "string" || !/^[0-9a-f]{64}$/.test(nonce)
        || typeof wallet_address !== "string" || typeof signature !== "string") {
      return reply(req, 400, { error: "wallet proof fields are invalid" });
    }
    const { data: challenge, error: challengeError } = await admin.rpc("jarvis_solana_get_wallet_challenge", {
      p_user_id: userId, p_challenge_id: challenge_id, p_nonce: nonce,
    });
    if (challengeError || !challenge || challenge.consumed_at || new Date(challenge.expires_at).getTime() <= Date.now()) {
      return reply(req, 400, { error: "wallet challenge expired or already used" });
    }
    try {
      const publicKey = decodeBase58(wallet_address);
      const signatureBytes = decodeBase64(signature);
      if (signatureBytes.length !== 64) return reply(req, 400, { error: "signature must be 64 bytes" });
      const key = await crypto.subtle.importKey("raw", publicKey, { name: "Ed25519" }, false, ["verify"]);
      const valid = await crypto.subtle.verify(
        { name: "Ed25519" },
        key,
        signatureBytes,
        new TextEncoder().encode(challenge.message),
      );
      if (!valid) return reply(req, 403, { error: "wallet signature verification failed" });
      const signatureHash = await sha256(signatureBytes);
      const { data, error } = await admin.rpc("jarvis_solana_complete_wallet_link", {
        p_user_id: userId,
        p_challenge_id: challenge_id,
        p_nonce: nonce,
        p_wallet_address: wallet_address,
        p_signature_hash: signatureHash,
      });
      if (error) {
        if (error.code === "23505") return reply(req, 409, { error: "wallet is already linked to another Jarvis account" });
        return reply(req, 400, { error: "wallet link could not be completed" });
      }
      return reply(req, 200, data);
    } catch (error) {
      return reply(req, 400, { error: error instanceof Error ? error.message : "wallet signature invalid" });
    }
  }

  return reply(req, 400, { error: "unknown action" });
});
