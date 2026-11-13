# Jarvis Unified — paper-only prototype release plan

**Purpose:** allow a production-like prototype to be deployed and hands-on tested before the Level 3 forward-evidence period is complete.

This plan separates three different outcomes:

1. **Prototype release candidate:** engineering checks pass and the application is ready for controlled paper-only deployment.
2. **Operational prototype:** the deployed service is monitored, recoverable and usable for owner testing and final adjustments.
3. **Level 3 / Level 4 certification:** evidence, independent review and maturity gates are complete. A deployed prototype is not automatically certified.

## 1. Non-negotiable operating boundary

- Paper mode only; kill switch engaged by default.
- Deriv public market-data WebSocket only for the initial EURUSD feed.
- No account authentication, PAT, OAuth, OTP, wallet access, proposal, buy, sell or broker execution.
- Deriv and MT5 execution adapters remain disabled.
- No secrets or broker credentials are provisioned on the prototype host.
- All orders, fills, positions, costs and PnL are simulated in the paper ledger.
- Any configuration or runtime state that enables live execution blocks release.

The public Deriv endpoint is read-only market data. It is not a source of authenticated per-tick signatures. Until the provider-verification design has been implemented and independently accepted, collected ticks remain unverified candidates and do not count toward Level 3.

## 2. Release-candidate engineering gates

Before deployment, record the exact source commit and verify:

- CI passes on the exact release commit; a queued or started run is not a pass.
- Unit, integration, paper replay, risk-gate, kill-switch, crash/restart and data-integrity tests pass.
- The default runtime is paper-only and no live adapter can be constructed.
- The paper ledger reconciles cash, equity, open positions, fills, fees and modeled slippage.
- API/dashboard surfaces are read-only where intended and are not exposed publicly without authentication.
- Scraper and remote-fetch features remain isolated from trading execution and enforce SSRF protections.
- Security-critical changes have independent review; author self-approval is not sufficient.
- The build, dependencies and configuration are pinned and recorded.

A stress-test count, synthetic replay or green CI run is software evidence only; it is not a trading-performance result.

## 3. Production-like host requirements

- Dedicated Linux host or equivalent persistent runtime; never use an ephemeral CI runner for ongoing collection.
- Dedicated unprivileged service account.
- Persistent encrypted volume for SQLite databases, WAL files, logs and backups.
- UTC time synchronization and monitored clock drift.
- Outbound network allow-list limited to the approved public market-data hostname and required system services.
- No public inbound listener unless the dashboard/API has an independently reviewed authentication and network-control design.
- Supervisor with bounded restart policy, health checks, log rotation and a documented stop/rollback procedure.
- Disk, process, feed freshness, audit-chain, backup-age and restore-failure alerts.
- Immutable or append-only off-host backups and a successful restore drill before treating the host as operational.

## 4. Deployment and owner-testing sequence

1. Deploy the exact reviewed paper-only release candidate.
2. Verify the running commit, configuration, process identity, paper mode and disabled broker adapters.
3. Verify public market-data connection, symbol mapping, timestamps and raw-payload retention. Mark observations unverified until the provenance gate is accepted.
4. Verify simulated order lifecycle, partial fills, cancellations, position reconciliation, risk limits, kill switch and restart recovery.
5. Verify dashboard, reports, audit history, logs, alerts, backup and restore.
6. Conduct owner testing against the deployed prototype and record defects with timestamps, build SHA and reproduction steps.
7. Apply final adjustments on a new release candidate; rerun the relevant test suite and record the new commit.
8. Keep the previous known-good release available for rollback.

Owner testing may happen immediately after deployment. It does not need to wait for the Level 3 observation period.

## 5. Level 3 evidence remains a separate gate

The Level 3 clock starts only after the approved provider-provenance mechanism is implemented, independently reviewed and operationally accepted. At that point:

- collect real forward paper observations with trusted timestamps and provenance;
- preserve raw provider payloads, session evidence, collector build and append-only audit linkage;
- maintain the separate paper execution ledger and reconcile every fill, fee, position and PnL change;
- require 30 consecutive UTC calendar days; outages and missing days break the streak;
- publish sample size, win rate, expectancy, profit factor, drawdown, slippage, fees and rejected-entry rate, including losing periods;
- obtain independent review and sign-off.

No historical replay, synthetic test, CI fixture, heartbeat, unverified candidate or owner acceptance test can be substituted for this evidence.

## 6. Level 4 operational acceptance

Level 4 follows Level 3. It additionally requires production hardening, alert routing, incident response, kill-switch drills, tested backup/restore, security review, operational ownership and independent release approval.

This release plan does not authorize live trading. Any future live-execution discussion requires a separate explicit decision and safety review.

## 7. Release record

For each candidate, retain:

- release tag and exact Git commit SHA;
- CI run URL and completed conclusion;
- dependency lockfile and configuration checksum;
- host/runtime version and deployment timestamp in UTC;
- paper-mode and adapter-disablement verification;
- backup/restore test evidence;
- owner-test findings and resolved defects;
- rollback target and operator.

**Current status:** plan only. No host is provisioned and no deployment is performed by this document.
