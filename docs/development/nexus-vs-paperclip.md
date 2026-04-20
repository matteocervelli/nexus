# Nexus vs Paperclip

Data: 2026-04-18
Reference repo locale: `references/paperclip/`

## Scopo

Questo documento confronta `Nexus` con `Paperclip` come base di comparazione concreta, non come direzione di adozione.

La decisione architetturale resta invariata:

- `Nexus` non userà Paperclip come core
- `Atrium` resta il source of truth
- `Paperclip` viene studiato come reference implementation

Vedi anche: [ADR-0001 — Do Not Use Paperclip as Nexus Core](../adr/0001-paperclip-no-go.md).

## Snapshot rapido

### Nexus

- stato attuale: documentazione e architettura target
- modello: `Limen -> Nexus -> Atrium`
- vincolo duro: nessun database proprio
- forma prevista: daemon Python + FastAPI JSON API + SPA webapp separata + subprocess agentici (tre tier di esecuzione)

Riferimenti:

- [`CLAUDE.md`](../../CLAUDE.md)
- [`docs/development/nexus-vision.md`](./nexus-vision.md)

### Paperclip

- stato attuale: prodotto funzionante e monorepo completo
- modello: server Node.js + React UI + PostgreSQL/embedded Postgres
- forma: control plane completo con DB, UI, auth, org chart, issues, approvals, budgets, adapters

Riferimenti locali:

- [`references/paperclip/README.md`](../../references/paperclip/README.md)
- [`references/paperclip/package.json`](../../references/paperclip/package.json)
- [`references/paperclip/packages/db/src/schema/index.ts`](../../references/paperclip/packages/db/src/schema/index.ts)

## Differenza fondamentale

`Paperclip` è un **control plane completo**.

`Nexus` deve essere un **motore di orchestrazione integrato in un ecosistema più ampio**:

- `Limen` = interfaccia e presenza umana
- `Nexus` = comportamento, scheduling, spawning, policy
- `Atrium` = stato, audit, work registry, documenti, costi

Qui sta tutta la differenza: Paperclip incorpora ciò che per Nexus deve vivere in Atrium.

## Confronto per dimensione

| Dimensione      | Nexus                                             | Paperclip                                                                              | Implicazione                                    |
| --------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------- |
| Source of truth | `Atrium` esterno                                  | DB proprio (`packages/db/`)                                                            | non compatibili come core senza duplicazione    |
| Scope prodotto  | orchestration layer dentro un OS più ampio        | company control plane completo                                                         | Paperclip è più largo, Nexus più integrato      |
| Runtime model   | subprocess e adapter multipli previsti            | adapter multipli già implementati (`packages/adapters/`, `server/src/adapters/`)       | pattern riusabile                               |
| Task model      | `work_items` minimi previsti                      | `issues`, `projects`, `goals`, commenti, documenti, workspace                          | Nexus deve restare più sottile                  |
| Session/state   | ephemerality + stato in Atrium                    | persistenza esplicita (`agent_runtime_state`, `agent_task_sessions`, `heartbeat_runs`) | utile come pattern, non come schema da copiare  |
| Governance      | approvazioni e budget previsti                    | approvazioni, budget, auth, revisioni config già completi                              | copiare il concetto, non il dominio             |
| Dashboard       | SPA webapp separata + FastAPI JSON API            | UI React completa con realtime e dashboard API                                         | Nexus: SPA separata, non bundled nel daemon     |
| Workflow model  | DAG di sessioni agente (serializzato + branching) | issues/projects flat                                                                   | Nexus è un workflow engine, non una coda piatta |
| Tenancy         | singolo ecosistema Ad Limen/Limen/Atrium          | multi-company nativo                                                                   | non è una priorità per Nexus                    |

## Dove Paperclip è più maturo

Paperclip oggi ha già:

- adapter pack completo: `claude-local`, `codex-local`, `gemini-local`, `cursor-local`, `process`, `http`
- schema ricco per run, costi, approval, activity log, session state
- UI e API complete per dashboard e gestione agenti
- auth e company scoping
- test, e2e, smoke scripts, evals

Questo lo rende una buona sorgente per:

- definire il contract degli adapter
- definire il contract di heartbeat
- capire quali campi servono davvero per audit e run history
- evitare di sottostimare i casi edge di session persistence e retry

## Dove Nexus deve restare diverso

Nexus deve differire in modo esplicito su questi punti:

1. Stato
   Nessun database interno. Tutto vive in Atrium.

2. Dominio
   Il centro non è la "company" in astratto, ma il sistema `Limen/Nexus/Atrium`.

3. Proattività
   Nexus deve servire anche awareness personale, accountability e reminder invisibili, non solo task execution.

4. Superficie prodotto
   La dashboard Nexus deve essere un cockpit operativo minimale, non una piattaforma general-purpose più larga del necessario.

5. Semplificazione iniziale
   Nexus deve partire con poche primitive:
   `agent_registry`, `work_items`, `run_log`, `cost_events`, `approvals`, `digest views`.

## Cosa adottare, adattare, evitare

### Adottare quasi direttamente

- heartbeat model
- adapter abstraction
- budget-aware execution
- run-level audit log
- explicit approval gates
- environment tests per adapter

### Adattare al modello Nexus

- issues/tasks -> `work_items`
- org chart -> `agent_registry` + capability classes
- dashboard summary -> digest e cockpit di Nexus
- session persistence -> stato serializzato in Atrium, non nel DB del control plane
- activity log -> `agent_results` e run log coerenti con Atrium

### Evitare

- database ownership di Paperclip
- company-centric domain model come asse portante
- schema completo Paperclip copiato 1:1
- dashboard bundled nel daemon (la SPA è un progetto separato)
- plugin surface area troppo estesa in fase 1

## Mapping concreto

| Paperclip         | Nexus equivalente                         |
| ----------------- | ----------------------------------------- |
| `agents`          | `agent_registry`                          |
| `issues`          | `work_items`                              |
| `heartbeat_runs`  | `run_log` / `agent_results`               |
| `cost_events`     | `budget_ledger` / `cost_events` in Atrium |
| `approvals`       | `approvals` in Atrium                     |
| adapter registry  | runtime adapter contract di Nexus         |
| dashboard summary | morning digest + dashboard operativa      |

## Conclusione pratica

Paperclip è utile come **repo di confronto tecnico** e come benchmark di maturità.

Non è utile come base architetturale diretta per `Nexus`, perché:

- porta il proprio stato
- porta il proprio dominio
- spinge verso un prodotto diverso

La linea giusta è:

- studiare `Paperclip`
- estrarne pattern e contratti
- implementare un `Nexus` più sottile, più integrato, più pragmatico

Questo include esplicitamente un layer interno paperclip-like per board, governance e visibilità.

## Prossimo passo raccomandato

Dal confronto emergono due passi concreti:

1. formalizzare il board layer interno di Nexus
2. formalizzare l'`adapter contract` di Nexus

L'ADR del board layer è: [ADR-0002 — Introduce an Internal Nexus Board Layer](../adr/0002-internal-board-layer.md).

L'ADR sull'adapter contract è: [ADR-0003 — Define a Common Runtime Adapter Contract](../adr/0003-runtime-adapter-contract.md).

Questo definisce almeno:

1. interfaccia comune runtime
2. input/output di un heartbeat
3. campi minimi di stato run/sessione
4. regole di budget e timeout
5. supporto iniziale per `codex`, `claude`, `process`, `http`
