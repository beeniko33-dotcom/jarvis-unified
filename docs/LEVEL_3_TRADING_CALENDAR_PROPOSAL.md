# Level 3 streak definition vs. weekly market closure — decision proposal

**Status: PROPOSED. Not accepted. No gate or evidence logic is changed by this document.**
Date: 2026-11-15. Decision owner: repository owner; independent reviewer required before any gate change.

## 1. Finding

`ForwardEvidenceStore.report()` (`research/forward_validation.py`) computes the Level 3 streak as the number of
**consecutive calendar UTC days that each contain at least one verified observation**, and reports
`missing_days_break_streak: true`. It has no concept of market closure.

EURUSD spot does not trade all week. It closes on Friday evening (UTC) and reopens on Sunday evening (UTC), so a
UTC Saturday contains no ticks at all. The Deriv response recorded in `docs/HOST_PROVISIONING_CHECKLIST.md` also showed
the feed closed until Monday 2026-11-16 00:00:00 (provider time), which would leave Sunday empty as well.

Consequence: **a 30-consecutive-UTC-day streak cannot be reached with EURUSD spot data, however good the collector,
host or provenance verifier is.** The best case is 6 days (Sunday to Friday, if the feed ticks on Sunday evening);
on a feed that reopens Monday it is 5.

### How this was checked (2026-11-15)

A throwaway scratch SQLite database (not the evidence store, not committed) was given one verified-flagged row per UTC day
for 60 days and `report(30)` was read for `latest_consecutive_verified_utc_day_streak`:

| Days with a row | Streak reported |
|---|---|
| every day (24/7 feed) | 60 |
| every day except Saturday | 4 (window ended mid-week; capped at 6 in any week) |
| every day except Saturday and Sunday | 3 (capped at 5 in any week) |

The streak is pure date arithmetic over the `utc_day` column, so the result does not depend on provenance or provider.

Related effects:

- The runbook alert "missed UTC observation day" would fire every weekend even though nothing is wrong.
- A day currently counts if it has **one** verified observation. A collector that was up for a single tick would
  credit the day.

## 2. Why this is a policy decision and not a quiet fix

The streak definition decides what "30 days of evidence" means. Loosening it incorrectly (for example, treating any
day without data as closed) would let outages pass as closures. Any change must keep a missed *trading* day fatal.

## 3. Options

| Option | Definition | Calendar time to complete | Trade-off |
|---|---|---|---|
| **A. Fixed trading calendar (recommended)** | 30 consecutive *expected trading days*, taken from a versioned calendar file committed to the repo and bound into the store configuration hash. Listed closure days are exempt; every other day must have verified coverage. | About 42 calendar days (6 trading weeks) | Longer than "30 days", but honest and reachable. |
| B. 24/7 instrument | Keep calendar-day streak, switch to an instrument that ticks every day | 30 calendar days | Changes strategy scope. A synthetic index is not EURUSD market evidence; crypto is a different market and needs its own provider review. |
| C. Closure from provider signal | Exempt days where the provider itself reports market-closed | About 42 calendar days | Needs an authenticated closure signal. Unauthenticated `MarketIsClosed` messages could mask outages. Not recommended until provenance exists. |

A shorter *calendar* time is not available under any option that keeps the evidence meaningful.

## 4. Requirements for the implementation PR (not part of this PR)

If Option A is chosen, a separate PR must:

1. Add a calendar file (UTC dates, closures, reduced-hours days) with a version and SHA-256, and include both in the
   store configuration so it cannot change mid-run (a change forces a new database, as today).
2. Make absence of data on a listed trading day break the streak; make absence on a listed closure day neutral.
3. Add a minimum coverage rule per trading day (proposed: observations in at least 90 percent of the expected hourly
   slots, owner to confirm), replacing the one-observation rule.
4. Keep every existing guard unchanged: freshness window, hash chain, forced `provenance_verified=False` unless a
   reviewed verifier exists, no backfill.
5. Add tests: weekend neutral; missed Tuesday fatal; unlisted gap fatal; calendar change rejected; holiday handled;
   one-tick day not credited.
6. Update `docs/MATURITY.md` and `docs/LEVEL_3_FORWARD_VALIDATION.md` wording from "30 consecutive calendar days"
   to the accepted definition, and receive independent review before merge.

## 5. Decision record

| Decision | Choice (A / B / C / defer) | Name | Date |
|---|---|---|---|
| Streak definition | | | |
| Per-day minimum coverage | | | |
| Independent reviewer sign-off | | | |

Until a decision is recorded and implemented, the verified-day count stays 0 and Level 3 stays uncertified.
