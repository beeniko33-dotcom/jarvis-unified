"""Cloudflare-hosted Jarvis command controller.

This first migration stage owns the remote command queue and heartbeat only.
Paper-session execution remains disabled until the persistent account and execution
engine have been migrated from local SQLite/files into durable Postgres transactions.
"""
import json
import traceback
from datetime import datetime, timezone
from urllib.parse import quote

from workers import WorkerEntrypoint, Response, fetch

WORKER_ID = "cloudflare-control-worker"
ALLOWED_ACTIONS = {"pause_entries", "resume_entries", "engage_kill_switch", "run_paper_session"}
DEFAULT_STATE = {"entries_paused": True, "kill_switch_engaged": True, "last_paper_session_date": None}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Default(WorkerEntrypoint):
    def _headers(self, prefer=None):
        headers = {
            "apikey": self.env.SUPABASE_SECRET_KEY,
            "content-type": "application/json",
        }
        if prefer:
            headers["prefer"] = prefer
        return headers

    async def _db(self, method, path, payload=None, prefer=None):
        url = self.env.SUPABASE_URL.rstrip("/") + "/rest/v1" + path
        options = {"method": method, "headers": self._headers(prefer)}
        if payload is not None:
            options["body"] = json.dumps(payload, separators=(",", ":"))
        response = await fetch(url, options)
        raw = await response.text()
        if not response.ok:
            # Never log response bodies: database errors can contain sensitive context.
            raise RuntimeError("supabase_http_" + str(response.status))
        return json.loads(raw) if raw else None

    async def _load_state(self):
        rows = await self._db(
            "GET",
            "/operator_status?worker_id=eq." + quote(WORKER_ID) +
            "&select=details,kill_switch_engaged,entries_paused,last_paper_session_date&limit=1",
        )
        if not rows:
            return dict(DEFAULT_STATE)
        row = rows[0]
        details = row.get("details") or {}
        saved = details.get("control_state") if isinstance(details, dict) else None
        state = dict(DEFAULT_STATE)
        if isinstance(saved, dict):
            if isinstance(saved.get("entries_paused"), bool):
                state["entries_paused"] = saved["entries_paused"]
            if isinstance(saved.get("kill_switch_engaged"), bool):
                state["kill_switch_engaged"] = saved["kill_switch_engaged"]
            if isinstance(saved.get("last_paper_session_date"), str) or saved.get("last_paper_session_date") is None:
                state["last_paper_session_date"] = saved.get("last_paper_session_date")
        # Existing status columns are a second fail-closed source of truth.
        if isinstance(row.get("entries_paused"), bool):
            state["entries_paused"] = state["entries_paused"] or row["entries_paused"]
        if isinstance(row.get("kill_switch_engaged"), bool):
            state["kill_switch_engaged"] = state["kill_switch_engaged"] or row["kill_switch_engaged"]
        return state

    async def _save_heartbeat(self, state, processed):
        health = "blocked" if state["kill_switch_engaged"] else (
            "degraded" if state["entries_paused"] else "healthy"
        )
        details = {
            "worker_type": "cloudflare-python-worker",
            "runtime_stage": "control-plane-only",
            "paper_session_execution": "disabled_pending_postgres_migration",
            "processed": processed,
            "control_state": state,
        }
        await self._db(
            "POST",
            "/operator_status?on_conflict=worker_id",
            {
                "worker_id": WORKER_ID,
                "reported_at": utc_now(),
                "health": health,
                "mode": "paper",
                "kill_switch_engaged": state["kill_switch_engaged"],
                "entries_paused": state["entries_paused"],
                "last_paper_session_date": state["last_paper_session_date"],
                "details": details,
            },
            "resolution=merge-duplicates,return=minimal",
        )

    async def _finish(self, command_id, status, result):
        await self._db(
            "PATCH",
            "/operator_commands?id=eq." + quote(command_id),
            {"status": status, "completed_at": utc_now(), "result": result},
            "return=minimal",
        )

    async def _process(self):
        if not getattr(self.env, "SUPABASE_URL", None) or not getattr(self.env, "SUPABASE_SECRET_KEY", None):
            raise RuntimeError("worker_secrets_not_configured")
        state = await self._load_state()
        pending = await self._db(
            "GET",
            "/operator_commands?status=eq.pending&order=requested_at.asc&limit=10&select=id,action",
        ) or []
        processed = 0
        for command in pending:
            command_id = command.get("id")
            action = command.get("action")
            if not isinstance(command_id, str) or action not in ALLOWED_ACTIONS:
                continue
            claimed = await self._db(
                "PATCH",
                "/operator_commands?id=eq." + quote(command_id) + "&status=eq.pending",
                {"status": "claimed", "claimed_by": WORKER_ID, "claimed_at": utc_now()},
                "return=representation",
            ) or []
            if not claimed:
                continue

            if action == "pause_entries":
                state["entries_paused"] = True
                result = {"entries_paused": True, "kill_switch_engaged": state["kill_switch_engaged"]}
                status = "completed"
            elif action == "engage_kill_switch":
                state["kill_switch_engaged"] = True
                state["entries_paused"] = True
                result = {"entries_paused": True, "kill_switch_engaged": True}
                status = "completed"
            elif action == "resume_entries":
                if state["kill_switch_engaged"]:
                    result = {"reason": "kill switch is engaged; resume refused"}
                    status = "rejected"
                else:
                    state["entries_paused"] = False
                    result = {"entries_paused": False, "kill_switch_engaged": False}
                    status = "completed"
            else:
                # Do not claim that a synthetic local paper-session script ran in this runtime.
                result = {"reason": "paper session runtime migration is not complete; no session was run"}
                status = "rejected"

            await self._finish(command_id, status, result)
            processed += 1

        await self._save_heartbeat(state, processed)
        return {"worker_id": WORKER_ID, "processed": processed, "health": (
            "blocked" if state["kill_switch_engaged"] else
            "degraded" if state["entries_paused"] else "healthy"
        )}

    async def fetch(self, request):
        path = request.url.split("?", 1)[0].rstrip("/")
        if path.endswith("/health"):
            if request.method != "GET":
                return Response("method not allowed", status=405)
            return Response.json({
                "service": WORKER_ID,
                "runtime_stage": "control-and-market-data-ingress",
                "market_data_ingress": "token_protected_supabase_function_proxy",
                "signal_ingress": "token_protected_supabase_function_proxy",
                "ingest_token_configured": bool(getattr(self.env, "JARVIS_INGEST_TOKEN", None)),
                "paper_session_execution": "disabled_pending_postgres_migration",
                "mode": "paper",
                "live_trading": "disabled_by_design",
            })
        if path.endswith("/market-data") or path.endswith("/signals"):
            if request.method != "POST":
                return Response("method not allowed", status=405)
            ingest_function = "signal-ingest" if path.endswith("/signals") else "market-data-ingest"
            max_bytes = 16 * 1024 if path.endswith("/signals") else 512 * 1024
            collector_token = getattr(self.env, "JARVIS_COLLECTOR_TOKEN", None)
            if not collector_token:
                return Response("collector authentication not configured", status=503)
            supplied = request.headers.get("authorization", "")
            expected = "Bearer " + collector_token
            if len(supplied) != len(expected):
                return Response("unauthorized", status=401)
            token_diff = 0
            for left, right in zip(supplied.encode("utf-8"), expected.encode("utf-8")):
                token_diff |= left ^ right
            if token_diff:
                return Response("unauthorized", status=401)
            if (not getattr(self.env, "SUPABASE_URL", None)
                    or not getattr(self.env, "SUPABASE_SECRET_KEY", None)
                    or not getattr(self.env, "JARVIS_INGEST_TOKEN", None)):
                return Response("ingress not configured", status=503)
            raw = await request.text()
            if len(raw.encode("utf-8")) > max_bytes:
                return Response("payload too large", status=413)
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                return Response("invalid JSON", status=400)
            if not isinstance(payload, dict):
                return Response("JSON object required", status=400)
            target = self.env.SUPABASE_URL.rstrip("/") + "/functions/v1/" + ingest_function
            upstream = await fetch(target, {
                "method": "POST",
                "headers": {
                    **self._headers(),
                    "x-jarvis-ingest-token": self.env.JARVIS_INGEST_TOKEN,
                },
                "body": raw,
            })
            body = await upstream.text()
            return Response(body, status=upstream.status, headers={
                "content-type": "application/json",
                "cache-control": "no-store",
            })
        if request.method != "GET":
            return Response("method not allowed", status=405)
        return Response("Jarvis worker is running. Use /health, POST /market-data or POST /signals.", status=200)

    async def scheduled(self, controller, env, ctx):
        try:
            result = await self._process()
            print(json.dumps({"event": "cron_complete", **result}, separators=(",", ":")))
        except Exception as exc:
            # Error type only; never emit URLs, headers, payloads, or exception messages.
            frames = traceback.extract_tb(exc.__traceback__)[-5:]
            safe_frames = [{"file": frame.filename.rsplit("/", 1)[-1], "line": frame.lineno, "function": frame.name} for frame in frames]
            print(json.dumps({"event": "cron_failed", "error_type": type(exc).__name__, "frames": safe_frames}, separators=(",", ":")))
