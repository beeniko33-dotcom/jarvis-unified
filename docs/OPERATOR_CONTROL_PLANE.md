# Operator control plane

Status: paper-only. Live trading is **not** a command and cannot be enabled from the panel,
Telegram or any remote path. The database constraint, the worker's fixed action table and the
Edge Function validation each refuse it independently.

## Components

| Part | Where it runs | What it can do |
| --- | --- | --- |
| `apps/control_panel/` | Any static host (public Storage bucket recommended) | Signs in, shows status, queues four confirmed actions |
| `supabase/functions/status` | Supabase Edge Function | Read-only status for allowlisted operators |
| `supabase/functions/control` | Supabase Edge Function | Validates and queues one of four actions |
| `public.operator_*` tables | Supabase Postgres, RLS on, no browser grants | Allowlist, command queue, worker health |
| `research/control_worker.py` | Your machine, with the service-role key in its environment | Executes the four actions locally, fail-closed |

Actions: `pause_entries`, `resume_entries`, `engage_kill_switch`, `run_paper_session`.

## Fail-closed defaults

- No state file means entries are paused and the kill switch is engaged.
- Remote commands can engage the kill switch but can never release it.
- `resume_entries` is refused while the kill switch is engaged.
- `run_paper_session` runs at most once per UTC day, with a fixed command line.
- A command is claimed atomically, so two workers cannot both run it.

## One-time setup

1. **Sign in once.** Open the panel and enter your email. The sign-in link creates your user.
2. **Authorize yourself.** In the Supabase dashboard, open Authentication, then Users, and copy your
   user UID. Then, in the SQL editor, run:

   ```sql
   insert into public.operator_allowlist (user_id, note)
   values ('YOUR-USER-UID', 'owner');
   ```

   Nobody else can add operators from the browser. Only the project owner can run this.
3. **Set the Auth site URL.** In Authentication settings, set the site URL and redirect URL to the
   address where you host the panel, so the sign-in link returns there.
4. **Host the panel.** Create a public Storage bucket named `control-panel` and upload
   `apps/control_panel/index.html` and `manifest.webmanifest`. The panel contains no secrets.
   Open the bucket's URL on your phone and choose "Add to Home Screen".

## Running the local worker

The service-role key belongs in the worker machine's environment only. Never put it in the panel,
the repo or a chat.

```bash
export SUPABASE_URL="https://zythldptlplyutphgxpg.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="...from your secret manager..."

# Once, locally, after you have reviewed the state of the paper account:
python -m research.control_worker --release-kill-switch

# Then run continuously (or schedule --once every minute):
python -m research.control_worker --interval 15
```

Entries stay paused after a kill-switch release until you send `resume_entries` from the panel.

## What the panel shows

Worker health, kill-switch and entry state, the last paper-session date, heartbeat age, and the
recent command log with results. It shows "Live trading: disabled by design" and has no control for it.

## Limits

- **Telegram and native store apps are not built yet.** The panel is an installable web app.
  A Telegram feedback bot would reuse the same `status` function and the same four actions.
- **A crashed paper session is not retried automatically** (see `docs/PERSISTENT_ACCOUNT_CONTINUITY.md`).
- **Heartbeats only prove the worker is running.** They are not market-data evidence and do not
  count toward the Level 3 gate (0 / 30 days).
- **Edge Functions are deployed but not yet exercised end to end from this build environment**,
  because outbound access to the project host is blocked by the sandbox proxy. Verify with a real
  sign-in before relying on it.
