import "jsr:@supabase/functions-js/edge-runtime.d.ts";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const INGEST_TOKEN = Deno.env.get("JARVIS_INGEST_TOKEN") ?? "";
const ALLOWED_PROVIDERS = new Set(["biquote", "deriv", "twelvedata"]);
const MAX_BODY_BYTES = 512 * 1024;
function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {status, headers: {"content-type":"application/json","cache-control":"no-store"}});
}
function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  const record = value as Record<string, unknown>;
  return "{" + Object.keys(record).sort().map(k => JSON.stringify(k)+":"+canonical(record[k])).join(",") + "}";
}
async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,"0")).join("");
}
function positive(value: unknown, field: string): number {
  const n=Number(value); if (!Number.isFinite(n)||n<=0) throw new Error(field+"_invalid"); return n;
}
function tokenMatches(supplied: string, expected: string): boolean {
  const a = new TextEncoder().encode(supplied), b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
  return difference === 0;
}
Deno.serve(async (req: Request) => {
  if(req.method!=="POST") return json({error:"method_not_allowed"},405);
  if(!SUPABASE_URL||!SERVICE_ROLE_KEY||!INGEST_TOKEN) return json({error:"server_not_configured"},503);
  if(!tokenMatches(req.headers.get("x-jarvis-ingest-token")??"",INGEST_TOKEN)) return json({error:"unauthorized_ingest_source"},401);
  if(Number(req.headers.get("content-length")??"0")>MAX_BODY_BYTES) return json({error:"payload_too_large"},413);
  let body: Record<string,unknown>;
  try { const raw=await req.text(); if(new TextEncoder().encode(raw).byteLength>MAX_BODY_BYTES)return json({error:"payload_too_large"},413); body=JSON.parse(raw); }
  catch { return json({error:"invalid_json"},400); }
  const provider=String(body.provider??"").toLowerCase();
  if(!ALLOWED_PROVIDERS.has(provider))return json({error:"provider_not_allowed"},400);
  if(!Array.isArray(body.observations)||body.observations.length<1||body.observations.length>100)return json({error:"observations_must_contain_1_to_100_items"},400);
  const receivedAt=new Date(), normalized=[];
  try {
    for(const input of body.observations) {
      if(!input||typeof input!=="object"||Array.isArray(input))throw new Error("observation_invalid");
      const item=input as Record<string,unknown>, symbol=String(item.symbol??"").trim().toUpperCase(), eventDate=new Date(String(item.event_time??""));
      if(!/^[A-Z0-9._-]{3,24}$/.test(symbol)||!Number.isFinite(eventDate.getTime()))throw new Error("symbol_or_event_time_invalid");
      const allowedSymbols: Record<string,string[]> = {
        biquote:["EURUSD"],
        deriv:["FRXEURUSD","FRXGBPUSD","FRXUSDJPY","FRXAUDUSD","FRXUSDCAD","FRXUSDCHF","FRXNZDUSD"],
        twelvedata:["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD"],
      };
      if(!allowedSymbols[provider].includes(symbol))throw new Error("provider_symbol_not_allowed");
      const bid=positive(item.bid,"bid"),ask=positive(item.ask,"ask"),mid=positive(item.mid,"mid");
      if(ask<bid||mid<bid||mid>ask)throw new Error("quote_relationship_invalid");
      const age=(receivedAt.getTime()-eventDate.getTime())/1000,sourceId=provider+":"+symbol;
      const values={bid:String(bid),ask:String(ask),mid:String(mid),spread:String(ask-bid),provider,
        provider_timestamp:eventDate.toISOString(),collector_received_at:receivedAt.toISOString(),quote_age_seconds:age,
        raw_payload:item.raw_payload??null,source_label:typeof item.source_label==="string"?item.source_label.slice(0,128):null,
        market_state:typeof item.market_state==="string"?item.market_state.slice(0,32):null,
        trust_classification:"candidate_unverified",provenance_verified:false,evidence_credit:false};
      const hashInput=canonical({sourceId,symbol,timeframe:"tick",eventTime:eventDate.toISOString(),
        bid:String(bid),ask:String(ask),mid:String(mid),rawPayload:item.raw_payload??null,
        sourceLabel:values.source_label});
      const hash=await sha256(hashInput);
      normalized.push({source_id:sourceId,event_time:eventDate.toISOString(),received_at:receivedAt.toISOString(),
        symbol,timeframe:"tick",schema_version:1,content_hash:hash,values_json:values,out_of_order:false,
        stale:age>120||age< -30,clock_skew:age< -30});
    }
  } catch(e) { return json({error:e instanceof Error?e.message:"observation_invalid"},400); }
  const upstream=await fetch(SUPABASE_URL.replace(/\/$/,"")+"/rest/v1/rpc/jarvis_ingest_market_observations",{
    method:"POST",headers:{apikey:SERVICE_ROLE_KEY,authorization:"Bearer "+SERVICE_ROLE_KEY,"content-type":"application/json"},
    body:JSON.stringify({p_observations:normalized})});
  if(!upstream.ok)return json({error:"observation_persistence_failed",upstream_status:upstream.status},502);
  const result=await upstream.json();
  return json({...result,provider,accepted_as:"candidate_unverified"},202);
});