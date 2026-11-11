# Architecture — Jarvis Unified

## High-level design

```
                    +-------------------+
                    |   Interfaces      |
                    | Telegram / Web /  |
                    | Mobile / MCP      |
                    +---------+---------+
                              |
                    +---------v---------+
                    |   Core Services   |
                    | Status API        |
                    | Orchestrator      |
                    +---------+---------+
                              |
          +-------------------+-------------------+
          |                   |                   |
+---------v--------+  +-------v--------+  +-------v--------+
|   Brain / AI     |  |   Signals      |  |   Risk Engine  |
| Agents + Memory  |  | Generators     |  | Hard limits    |
+---------+--------+  +-------+--------+  +-------+--------+
          |                   |                   |
          +-------------------+-------------------+
                              |
                    +---------v---------+
                    |  Broker Adapters  |
                    | Paper / Deriv /   |
                    | MT5 / Future      |
                    +-------------------+

                    +-------------------+
                    | packages/scraper  |  (independent)
                    +-------------------+
```

## Key design decisions

### 1. Broker adapters
Strategies and the brain never talk to a broker directly. They call a common interface. This allows:
- Paper mode as the safe default
- Easy addition of new brokers later
- Consistent risk enforcement

### 2. Central risk authority
All order requests pass through the risk engine. Even AI recommendations are filtered. Hard limits cannot be overridden by strategies.

### 3. Independent scraper package
The scraper lives under `packages/scraper` and retains its own configuration, scheduling, storage, and extensibility. It can feed the signal engine but is not required for core trading operation.

### 4. Paper-first execution
`JARVIS_MODE=paper` is the default. Enabling any live or demo broker requires explicit configuration and (later) an unlock mechanism.

## Next implementation steps

1. Define the common broker interface
2. Implement PaperBroker fully
3. Port risk rules from the Deriv system
4. Bring over status API patterns from ecosystem
5. Add minimal main.py entry point
