// Read-only operator status for authorized operators. Returns no secrets and no service data.
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" };

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

Deno.serve(async (req) => {
  if (req.method !== "GET") return reply(405, { error: "method not allowed" });
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(401, { error: "sign in required" });

  const url = Deno.env.get("SUPABASE_URL")!;
  const userClient = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: auth } },
  });
  const { data: userData, error: userError } = await userClient.auth.getUser();
  if (userError || !userData.user) return reply(401, { error: "invalid or expired session" });

  const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });
  const { data: allowed } = await admin
    .from("operator_allowlist")
    .select("user_id")
    .eq("user_id", userData.user.id)
    .maybeSingle();
  if (!allowed) return reply(403, { error: "not an authorized operator" });

  const [{ data: workers }, { data: commands }] = await Promise.all([
    admin.from("operator_status").select("*").order("reported_at", { ascending: false }).limit(10),
    admin
      .from("operator_commands")
      .select("id,action,status,requested_at,completed_at,reason,result")
      .order("requested_at", { ascending: false })
      .limit(25),
  ]);
  return reply(200, {
    generated_at: new Date().toISOString(),
    mode: "paper",
    live_trading: "disabled_by_design",
    workers: workers ?? [],
    recent_commands: commands ?? [],
  });
});
