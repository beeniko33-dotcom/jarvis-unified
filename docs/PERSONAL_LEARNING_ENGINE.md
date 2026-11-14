# Jarvis Unified — Personal Learning & Adaptive Intelligence

**Product direction:** a private, personal-use Jarvis that learns the owner's working preferences and improves its research workflow from accumulated experience.

**Status:** prototype design specification. This does not authorize autonomous live trading, self-modifying risk controls, or automatic strategy promotion.

## 1. What Jarvis should learn

Jarvis has four distinct learning domains. Keep them separate so a preference is never confused with market truth.

### A. Personal interaction and personality memory
Learn durable, useful preferences from explicit feedback and repeated choices:
- preferred tone, verbosity, explanation depth and report format;
- preferred markets, instruments, sessions, research questions and dashboard layout;
- alert thresholds and notification preferences;
- how the owner wants uncertainty, risk and failed experiments explained.

Store each memory with provenance (explicit user feedback, repeated choice, or inferred candidate), confidence, timestamps, and a review/expiry policy. Explicit corrections override inferred preferences. Ask before turning sensitive or ambiguous observations into durable memories. Provide inspect, correct, export and delete controls.

### B. Workflow and operational learning
Learn which research workflows, data checks, reports and tools are useful:
- remember completed tasks, outcomes, failures and operator corrections;
- identify repeated manual steps and suggest automations;
- improve retry/backoff recommendations from observed operational history;
- distinguish transient failures from persistent defects.

Operational memories must never be treated as evidence that a market-data source is authentic.

### C. Research and strategy learning
Learn from historical and paper-trading outcomes:
- maintain versioned experiments with hypothesis, dataset IDs/hashes, time range, strategy/config version and costs;
- measure net performance after spread, fees, slippage assumptions and rejected/missed signals;
- use chronological train/validation/test splits and walk-forward evaluation;
- track drawdown, tail loss, exposure, turnover, sample size and uncertainty, not only win rate or profit;
- compare against simple baselines and preserve losing experiments to prevent repeated mistakes;
- detect data leakage, regime sensitivity, overfitting and insufficient sample sizes.

Synthetic data is useful for software tests and scenario exploration only. Label it as synthetic and never mix its results into real historical or forward evidence.

### D. Self-reflection and planning
At the end of a session or scheduled research cycle, generate a concise reflection:
1. What did Jarvis attempt?
2. What happened, based on recorded facts?
3. What did the owner correct or prefer?
4. What appears to have improved or regressed?
5. What uncertainty or missing data remains?
6. What is the next low-risk experiment?

Reflections create candidate memories and research proposals, not automatic changes to execution policy.

## 2. Personality model

Use a stable core personality with an adaptive preference profile.

Core traits:
- calm, precise, proactive and respectful;
- curious and analytical, but explicit about uncertainty;
- candid about losses, errors and limitations;
- never boastful, manipulative, or falsely confident;
- concise by default, detailed when the task warrants it;
- treats the owner as decision-maker.

Adaptable traits:
- preferred communication style and level of detail;
- preferred workflow and presentation;
- research priorities and alert preferences.

The personality layer must not change risk limits, provenance rules, safety boundaries, or factual standards.

## 3. Proposed architecture

User feedback + task history + paper outcomes
                  |
          Event / Feedback Store
                  |
        Memory & Preference Service
          |                 |
   Personal profile    Research experience store
          |                 |
          +---- Reflection / Learner ----+
                                         |
                               Candidate recommendations
                                         |
                              Evaluation & policy gates
                                         |
                          Owner review / explicit approval
                                         |
                   Versioned preference or strategy registry

Suggested modules (adapt names to repository conventions after code-level design):
- core/learning/events.py — typed, append-only learning events.
- core/learning/memory_store.py — durable personal memories and lifecycle.
- core/learning/preference_model.py — explicit and inferred preference ranking.
- research/experience_store.py — strategy experiments and outcome attribution.
- research/reflection.py — factual session summaries and candidate lessons.
- research/evaluation.py — chronological and walk-forward evaluation.
- core/learning/approval.py — approval and version-promotion gates.
- apps/api/learning.py and dashboard views — inspect, correct, approve and export.

Storage should be local-first and durable (SQLite is suitable for the prototype). Keep learning records separate from the immutable execution/audit ledger. Version schemas and migrations. Do not store secrets, credentials, account tokens or unnecessary personal data in memory.

## 4. Learning loop

1. Observe: record task context, data provenance labels, configuration version and outcome.
2. Attribute: connect outcomes to the correct strategy, dataset and execution assumptions.
3. Reflect: summarize patterns with evidence links and uncertainty.
4. Propose: create a candidate preference update, workflow improvement or strategy experiment.
5. Evaluate: run tests and out-of-sample evaluation in an isolated research environment.
6. Review: show the owner what would change, why, evidence, risks and rollback.
7. Promote: apply only approved changes; retain version history and one-step rollback.

Explicit preference updates may be applied immediately when the owner directly requests them. Inferred preference changes should be tentative until confirmed or repeatedly supported.

## 5. Hard safety and integrity boundaries

- No self-modification of risk limits, kill switch, broker adapters, execution permissions, provenance verifier, or evidence-credit rules.
- No autonomous live orders, account access, credential handling, or wallet access.
- Keep the paper kill switch and central risk gate authoritative.
- Learner has read-only access to execution and audit records; it cannot rewrite them.
- No strategy is promoted based on in-sample results alone.
- Strategy changes remain research candidates until tests, chronological holdout and owner approval pass.
- Market data retains its original source/provenance label throughout every derived dataset and report.
- The model must state when it lacks enough observations; do not manufacture confidence from small samples.
- Keep a complete audit of memory additions, corrections, deletions, model/version changes and approvals.

## 6. Prototype acceptance criteria

### Personal learning
- [ ] Explicit user correction updates the preference profile and takes precedence over inference.
- [ ] Repeated choices can create low-confidence suggestions, never silent high-confidence facts.
- [ ] Jarvis can recall preferences across restarts.
- [ ] Owner can inspect, edit, export and delete personal memories.
- [ ] Memory records expose source, confidence, timestamps and expiry/review status.
- [ ] A reflection report cites underlying recorded events and separates facts from hypotheses.

### Research learning
- [ ] Every experiment has immutable dataset/config/strategy identifiers.
- [ ] Chronological split prevents future-data leakage.
- [ ] Reports include costs, drawdown, sample size and uncertainty.
- [ ] Losing and abandoned experiments remain searchable.
- [ ] Synthetic results are visibly segregated from historical and forward observations.
- [ ] Candidate strategy changes cannot affect running paper execution without explicit approval.

### Safety
- [ ] Tests prove the learner cannot write to risk settings or execution permissions.
- [ ] Tests prove the learner cannot modify the audit ledger or provenance status.
- [ ] Tests prove no live broker adapter or credential interface is reachable.
- [ ] Every promoted change is versioned, reviewable and reversible.

## 7. Delivery sequence

1. Implement typed learning events and local SQLite memory store.
2. Add explicit preference capture, corrections and inspect/export/delete controls.
3. Add session reflection based only on recorded facts.
4. Add strategy experiment registry and attribution for paper outcomes.
5. Add chronological evaluation and candidate recommendation workflow.
6. Integrate personality profile into reports and assistant responses.
7. Add dashboard/API controls and isolation tests.
8. Demonstrate learning across restarts using a deterministic offline fixture.

## 8. Success definition

Jarvis should become more familiar with how its owner works, more consistent at remembering useful lessons, better at organizing research, and more disciplined at evaluating strategy ideas. It must also become better at saying "I don't know yet."

The objective is **adaptive assistance with evidence and owner control**, not an unrestricted self-modifying trading agent.
