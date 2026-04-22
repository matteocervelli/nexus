# Paperclip vs Nexus — analisi comparativa e decisione

**Data**: 2026-04-22
**Scope**: decidere fra (a) continuare Nexus, (b) forkare Paperclip, (c) adottare Paperclip upstream.
**Metodo**: lettura read-only di ~60k LOC TS Paperclip + ~4k LOC Python Nexus via 3 agent Explore paralleli.
**Verdetto**: **(a) continuare Nexus, con Paperclip runnable in parallelo come reference architetturale**.

---

## 1. Paperclip in 500 parole

**Modello mentale.** Control plane multi-company: una deploy gestisce N Companies come entità di prim'ordine. Gerarchia rigida: _Company → Initiatives → Projects → Milestones → Issues → Sub-issues_ (`doc/SPEC.md:270-273`). L'**Issue (task)** è unità atomica + unico canale di comunicazione — delega = create+assign, coordinamento = commenti (`SPEC.md:251-269, 387-395`).

**Produzione task.** **CEO agent** propone breakdown al primo heartbeat; **Board** (umano, V1 singolo) approva (`SPEC.md:318-320, 28-32`). Dopo, ogni agente nel proprio heartbeat crea/delega sub-task. Non esiste ruolo "orchestrator" dedicato: l'orchestrazione è il control plane stesso (heartbeat loop + routines engine). Wake-up tipizzati: `timer`, `assignment`, `on_demand`, `automation` (`docs/agents-runtime.md:22-28`). Event-driven + scheduled coesistono.

**Org chart e hiring.** Agent con `reportsTo`, role, title, capability free-text, adapterType, budget mensile. **Hiring governato**: CEO propone → Board approva → generata connection string out-of-band (`SPEC.md:367-376`). Board pausa/termina sottoalberi interi. Cost attribution cross-team via _billing codes_ + _request depth_ (`SPEC.md:166-173`).

**Dashboard (55 pagine).** Cabina di comando, non monitor. Approva piani CEO, assumi agenti, modifica budget, pausa sottoalberi, OrgChart, run transcripts, Routines, Approvals, Costs, Activity, Inbox, Skills, company import/export, Plugin/Adapter manager. Progressive disclosure: summary → checklist → log raw.

**Persistenza.** PostgreSQL unico store via Drizzle. **58 migrazioni, 62 schemi**. PGlite embedded in dev; Postgres/Supabase in prod. Run logs out-of-row hashati sha256. Tabelle chiave: `companies, agents, issues, goals, heartbeat_runs, budget_policies, budget_incidents, cost_events, activity_log, routines, approvals, execution_workspaces, agent_wakeup_requests, agent_task_sessions`.

**Stack.** Node 20+, pnpm, TypeScript, Express, React+Vite+shadcn, Drizzle, better-auth, WebSocket, Vitest+Playwright. Monorepo `server/, ui/, cli/, packages/{db,shared,adapters,adapter-utils,plugins}`.

**Extension points.** Contratto `ServerAdapterModule` (`packages/adapter-utils/src/types.ts:292`): `execute(ctx) → AdapterExecutionResult` + opzionali (`listSkills`, `sessionCodec`, `getConfigSchema`, `onHireApproved`, `getQuotaWindows`). Built-in: `claude_local, codex_local, cursor_local, gemini_local, opencode_local, openclaw_gateway, pi_local, hermes, process, http`. Plugin esterni caricati da `~/.paperclip/adapter-plugins.json` senza toccare core. Invocazione: **subprocess** (`runChildProcess` in `packages/adapters/claude-local/src/server/execute.ts:497`), no SDK.

**Sorprese strutturali.** Multi-company isolation route-level. Deployment modes espliciti (`local_trusted` vs `authenticated`, bind `lan/tailnet`). **Agentcompanies/v1 spec**: Company packages markdown-first, git-native, vendor-neutral (`COMPANY.md/TEAM.md/AGENTS.md/PROJECT.md/TASK.md/SKILL.md` + `.paperclip.yaml`), usabili fuori Paperclip. Crash recovery: `reapOrphanedRuns` + `reconcileStrandedAssignedIssues` a startup + ogni tick. Session resume across heartbeat. LOC heatmap: `heartbeat.ts` 5408, `issues.ts` 2573, `routines.ts` 1552, 55 UI pages 33k LOC.

---

## 2. Nexus in 500 parole

**Modello mentale.** Orchestration engine senza store proprio. Tre strati: Limen (UI) → Nexus (scheduler+spawner+budget) → Atrium (work_items+agent_registry+budget_ledger in Postgres separato). Invariant: Nexus non scrive su disco salvo log. Unità atomica: `work_item` con `type, agent_role, priority P0-P3, status, context/result JSON`. Capability classes fissate: 7 archetipi (Code/Security/Ops/Quality/Product/Intelligence/Growth). Orchestrator dichiarato ma non implementato.

**Produzione task.** **Nessun produttore autonomo.** Unico punto dove `src/nexus/` crea work_items è `budget.py:127` (notifica errore). No orchestrator, no cron, no bridge Limen. Il daemon polla coda vuota finché qualcuno non POSTa manualmente su Atrium. Issue #40 aperta.

**Org chart / hiring.** Inesistente. Agent definiti da markdown `agents/<class>/CLAUDE.md` con front-matter, sincronizzati manualmente via `nexus sync-agents`. Solo 2/7 profili creati (code, security). No `reportsTo`, no Board approval, no pause/terminate UI.

**Esecuzione.** Heartbeat loop 30s (`daemon.py:229-244`) → poll Atrium → check budget → dispatch via adapter. **4 adapter via SDK** (non subprocess): `claude_adapter.py` usa `claude_agent_sdk.query`; `openai_adapter.py` usa `openai_codex_sdk`; `process_adapter.py` + `http_adapter.py` generici. Reconcile orfani PGID-aware su restart (`daemon.py:41-131`) — production grade. Budget check fail-safe. Workflow DAG: schema + condition DSL presenti, **engine di avanzamento MISSING**. Morning digest: zero codice.

**Dashboard.** SPA in-repo `/dashboard/` (React 19 + TanStack Router/Query + Vite). **4 viste**: WorkflowFeed (152 LOC), AgentStatus (98), AuditLog (113), AuditRunDetail (167). Hit `/nexus/api/*` reali, renderano empty-state perché Atrium ritorna `[]`. **Decisioni abilitate dalla UI: zero** — solo lettura.

**Persistenza.** Nessuna locale. Atrium è store via HTTP. DTO Pydantic in `models.py`.

**Stack.** Python 3.11+, FastAPI, Pydantic frozen, httpx async. Dashboard TS/React/Vite. CLI: `start/api/health/sync-agents` (mancano `stop/restart/status/logs/doctor/update`).

**Asset non banali (~4000 LOC totali salvabili).** Contratto adapter `adapter_base.py` + 4 adapter; SSE bounded-queue (`events.py` + `api/events.py`, 118 LOC); budget check con pause + auto-notification; reconcile orfani PGID-aware; dashboard API proxy tipizzato 300 LOC/8 endpoint; SPA skeleton ~1000 LOC.

**LOC.** Backend 2968, dashboard views+routes 1064. 20 issue aperte, 37 chiuse. SPRINT-1 completato. SPRINT-2/3 + BACKLOG hanno tutto il lavoro "brain" (digest, orchestrator, profili, DAG, Limen bridge).

---

## 3. Gap analysis — Paperclip vs Nexus

Legenda: CRITICAL = bloccante missione "AI company"; HIGH = feature core mancante; MEDIUM = quality; PARITY = equivalente; NEXUS-AHEAD = Nexus meglio.

| #   | Capability                                | Paperclip                                                                                                                        | Nexus                               | Gap                                                |
| --- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- | -------------------------------------------------- |
| 1   | Goal tree (company→...→issue)             | `schema/goals.ts:12`, `issues.ts:21`                                                                                             | MISSING (work_item piatto)          | **CRITICAL**                                       |
| 2   | Autonomous proposal loop (CEO→Board)      | `SPEC.md:28-32, 318-320` + heartbeat                                                                                             | MISSING                             | **CRITICAL**                                       |
| 3   | Org chart + reportsTo + hiring governance | `schema/agents.ts:13`, `SPEC.md:367-376`                                                                                         | MISSING                             | **CRITICAL**                                       |
| 4   | Approvals HITL (tabelle + UI)             | `schema/approvals.ts`, `ui/pages/Approvals.tsx`                                                                                  | MISSING                             | **CRITICAL**                                       |
| 5   | Routines (cron-like generators)           | `schema/routines.ts:20`, `services/routines.ts` (1552 LOC)                                                                       | MISSING                             | **HIGH**                                           |
| 6   | Workflow DAG advancement                  | N/A (task tree + blockers)                                                                                                       | Schema+DSL presenti, engine MISSING | **HIGH**                                           |
| 7   | Multi-company isolation                   | route-level enforcement                                                                                                          | Single-tenant implicito             | HIGH (strategico)                                  |
| 8   | Adapter invocation                        | 10 adapter subprocess + plugin loader                                                                                            | 4 adapter SDK-based                 | **PARITY** (Nexus più pulito, Paperclip più ampio) |
| 9   | Budget policies scopabili                 | `budget_policies` + `budget_incidents` + `cost_events`                                                                           | `budget.py` ledger mensile          | **HIGH** (Paperclip più ricco)                     |
| 10  | Cost events per-invocation                | `schema/cost_events.ts:9` (input/cached/output/costCents)                                                                        | PATCH work_item result (#43 aperta) | HIGH                                               |
| 11  | Audit log immutable                       | `activity_log.ts` insert-only + run logs sha256                                                                                  | Delega ad Atrium                    | PARITY                                             |
| 12  | Session resume across heartbeat           | persisted adapter session IDs                                                                                                    | Codex adapter sì, altri no          | MEDIUM                                             |
| 13  | Crash recovery / orphan reap              | `index.ts:585-600` + ogni tick                                                                                                   | `daemon.py:41-131` PGID-aware       | **NEXUS-AHEAD**                                    |
| 14  | Realtime UI push                          | WebSocket                                                                                                                        | SSE                                 | PARITY                                             |
| 15  | Dashboard views                           | **55 pagine** (Goals/OrgChart/Routines/Approvals/Costs/Activity/Inbox/Skills/Export/Import/Plugin/Adapter/Instance/Workspace...) | **4 viste** read-only               | **CRITICAL** (gap 13:1)                            |
| 16  | Morning digest / awareness                | Inbox + heartbeat triggers                                                                                                       | MISSING (#27, #28)                  | HIGH                                               |
| 17  | Agent profiles portabili                  | `agentcompanies/v1` spec vendor-neutral                                                                                          | `agents/*/CLAUDE.md` proprietario   | HIGH                                               |
| 18  | Company export/import con secrets         | `AGENTCOMPANIES_SPEC_INVENTORY.md:68-72`                                                                                         | MISSING                             | MEDIUM                                             |
| 19  | Plugin manager UI                         | `ui/pages/PluginManager.tsx` + `plugin-loader.ts`                                                                                | MISSING                             | MEDIUM                                             |
| 20  | Execution workspace / worktree tracking   | `schema/execution_workspaces`                                                                                                    | MISSING                             | MEDIUM                                             |
| 21  | Skills layer                              | `companies-spec.md:289-301`                                                                                                      | MISSING                             | MEDIUM                                             |
| 22  | Billing codes + request depth             | `SPEC.md:166-173`                                                                                                                | MISSING                             | LOW                                                |
| 23  | Deployment modes                          | `doc/PRODUCT.md:86-92`                                                                                                           | Single mode                         | LOW                                                |
| 24  | Service CLI completo                      | `cli/` package                                                                                                                   | Parziale                            | LOW                                                |

### Dettaglio CRITICAL

**#1 Goal tree.** Paperclip modella 6 livelli di decomposizione tutti in DB con parent tracking. Un agente vede sempre "il perché" risalendo l'albero. Nexus ha `work_items` piatti: senza struttura non c'è decomposizione possibile.

**#2 Autonomous proposal.** Paperclip: al primo heartbeat CEO agent genera piano strategico, Board approva, piano diventa albero di task. Da lì il sistema è vivo da solo. Nexus: daemon a vuoto.

**#3 Org chart + hiring.** Paperclip ha `reportsTo`, CEO propone assunzioni, Board approva, connection string out-of-band. Board pausa/termina sottoalberi. Governance reale. Nexus: lista piatta.

**#4 Approvals HITL.** Paperclip: `approvals` + `approval_comments` + UI + wake-up source. Nexus: zero.

**#15 Dashboard.** 55:4 non è un numero — è la differenza fra **cabina di comando** e **monitor read-only**.

---

## 4. Le tre opzioni — analisi

### (a) Continuare Nexus

**Effort stimato** per parità con Paperclip _oggi_: 7-10 mesi.
Breakdown: orchestrator + proposal loop (3-4 sett), goal tree in Atrium (3-4 sett), org chart + approvals (4-6 sett), routines (2 sett), digest + Limen bridge (2 sett), cost events (2 sett), 5 capability classes (3 sett), dashboard expansion Goals/OrgChart/Approvals/Routines/Costs/Activity/Inbox/etc. (8-12 sett), company export/import + workspaces (3-4 sett).

**Cosa si butta**: nulla dei 4000 LOC.
**Cosa si guadagna**: stack Python omogeneo, Atrium come single source of truth, **IP 100% proprietario** allineato alla vision Adlimen.
**Quando è giusta**: quando **il sistema stesso è il prodotto** — non uno strumento ma IP strategico. È il caso: Adlimen vende la capacità di scalare one-person company verso DAO, e il motore di orchestrazione è il cuore di quella proposta.

### (b) Fork Paperclip e adattare

**Effort**: 3-5 mesi iniziali + tax continuo di fork maintenance.
Il problema centrale: sostituire Drizzle/Postgres con Atrium HTTP backing significa riscrivere ~70 service file. È l'operazione più invasiva possibile senza guadagno strategico. Fork maintenance con upstream attivo = debito tecnico crescente in TS, non in Python.

**Perché scartata**: la sostituzione DB distrugge la ragione per cui si forka.

### (c) Adottare Paperclip upstream

**Effort: 1-2 settimane per essere operativo.**

**Perché scartata**:

- Vision Adlimen = "scale one-person company → DAO": il motore di orchestrazione è IP core.
- Paperclip è un prodotto altrui con roadmap altrui (Clipmart/ClipHub in arrivo, modello multi-company SaaS-oriented).
- Costruire Nexus insegna i pattern reali che servono anche in limen-assistant, app-himalaia, futuri prodotti Adlimen.

**Quando è giusta**: quando il sistema è mezzo per altro e il time-to-value batte l'ownership. Non è il caso qui.

---

## 5. Raccomandazione: **(a) continuare Nexus**

**Decisione**: Nexus è IP strategico. Non si delega.

**Paperclip diventa**:

1. **Submodule git** (`references/paperclip` → `paperclipai/paperclip`) — lettura del codice quando serve capire come risolvono un problema.
2. **Instance runnable** su homelab (`pnpm dev` porta 3100, `PAPERCLIP_TELEMETRY_DISABLED=1`) — vederlo girare dal vivo informa le scelte di design di Nexus senza copiare cieco.
3. **Tool generale Adlimen** — anche per progetti collaterali (app-nutry, app-levero, ricerche, routine ops) se e quando utile, senza vincolo di usarlo solo per sviluppare Nexus.

**Principi operativi**:

1. Non ri-inventare il modello dati senza studiare prima gli schemi Paperclip (58 migrazioni su problema analogo).
2. Non re-implementare il contratto adapter: prendi spunto da `ServerAdapterModule` prima di estendere `adapter_base.py`.
3. Python-native: Adlimen ecosystem (Atrium, Fabrica, Thesaurus, limen-assistant) è tutto Python. Zero frizione.
4. Atrium come single source of truth. Nessun secondo store.
5. No SaaS-isms: Nexus singolo-operatore → design più semplice di Paperclip su multi-company.

**Asset Nexus che restano fondativi** (nulla da buttare):

- `adapter_base.py` + 4 adapter = infrastruttura di esecuzione
- `budget.py` = base per policies scopabili (da estendere)
- `daemon.py` reconcile orfani PGID-aware = qualitativamente migliore di quello Paperclip sul dettaglio PGID
- `events.py` + SSE = realtime funzionante
- `api/dashboard.py` = layer proxy da mantenere + espandere
- Dashboard SPA skeleton = base da allargare con viste nuove

---

## 6. Roadmap Nexus — 5 fasi per valore

Ogni fase termina in un sistema che **promette qualcosa di misurabile**.

| Fase | Nome           | Promessa a fine fase                                      | Durata   | Sprint   |
| ---- | -------------- | --------------------------------------------------------- | -------- | -------- |
| 1    | **Alive**      | "Gli do un goal, scompone e esegue da solo"               | 3-4 sett | SPRINT-3 |
| 2    | **Governed**   | "Aspetta la mia approvazione prima di spendere"           | 2 sett   | SPRINT-4 |
| 3    | **Visible**    | "Mi avvisa su Telegram senza aprire la dashboard"         | 2 sett   | SPRINT-5 |
| 4    | **Recurring**  | "Fa cose ogni giorno da solo (scan, audit, digest)"       | 2-3 sett | SPRINT-6 |
| 5    | **Expressive** | "Ha un'org chart, delega gerarchicamente, mostra i costi" | 4-6 sett | SPRINT-7 |

**Totale**: 13-17 settimane ≈ **3-4 mesi** di lavoro focused.

### Fase 1 — ALIVE (SPRINT-3)

DoD: POST goal → orchestrator propone breakdown → work_items creati → dispatch agli agenti → risultati tornano. Autonomo.

| P   | Task                                                                                                                                                    | Effort |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| P0  | Schema `goals` in Atrium (`id, parent_id, level, title, description, status, owner_agent_role`) + CRUD API + DTO                                        | 5-7g   |
| P0  | Orchestrator meta-agente — `agents/orchestrator/CLAUDE.md` + implementazione (legge goals + work_items state, genera proposte pending) — supersedes #40 | 5-7g   |
| P0  | Autonomous proposal loop nel daemon — heartbeat invoca orchestrator se goal attivo senza work_items figli                                               | 3-4g   |
| P0  | `nexus bootstrap-goal --title "X"` CLI seed                                                                                                             | 1g     |
| P0  | E2E test: seed goal → code-agent spawnato → PR aperta su repo test                                                                                      | 2-3g   |

**Nuove issue**: `[SPRINT-3|01–06] [P0] Goal tree`, `Goal CRUD`, `Orchestrator impl`, `Proposal loop`, `CLI seed`, `E2E test`.

### Fase 2 — GOVERNED (SPRINT-4)

DoD: work_items con `requires_approval=true` o cost > soglia vanno in `pending_approval`. Dashboard consente approve/reject.

| P   | Task                                                  | Effort |
| --- | ----------------------------------------------------- | ------ |
| P1  | Schema `approvals` in Atrium + wake-up source         | 2-3g   |
| P1  | `/nexus/api/approvals` (list, approve, reject)        | 2g     |
| P1  | Dashboard `/approvals` view con inline approve/reject | 3-4g   |
| P1  | Dashboard `/goals` view con albero espandibile        | 3-4g   |
| P1  | Scheduler: approval gate prima del dispatch           | 1-2g   |
| P1  | Push Limen su approval pending                        | 1g     |

**Nuove issue**: `[SPRINT-4|01–04] [P1]`.

### Fase 3 — VISIBLE (SPRINT-5)

DoD: digest mattutino su Telegram, push immediato su approval/budget/failure.

Issue esistenti riordinate: **#27, #28, #29** da SPRINT-2 → SPRINT-5.

| P   | Task                                                                                           | Effort |
| --- | ---------------------------------------------------------------------------------------------- | ------ |
| P1  | `NexusAwarenessSource` in Limen — poll `/nexus/api/status` + `/approvals?status=pending` (#27) | 2-3g   |
| P1  | Morning digest renderer — Jinja → Telegram MarkdownV2 (#28)                                    | 2-3g   |
| P1  | Telegram handlers: `/nexus-status`, `/nexus-approve <id>`, `/nexus-reject <id>` (#29)          | 3g     |
| P1  | Push Limen on budget > 80% warn / > 100% hard-stop                                             | 1-2g   |
| P1  | Push Limen on P0 work_item failure                                                             | 1g     |

### Fase 4 — RECURRING (SPRINT-6)

DoD: routine nightly security scan + weekly deps audit girano da sole.

Issue riordinate: **#30, #31, #32, #33** → SPRINT-6.

| P   | Task                                                                                                                           | Effort |
| --- | ------------------------------------------------------------------------------------------------------------------------------ | ------ |
| P2  | Schema `routines` in Atrium (`cron, target_work_item_template, concurrency_policy, catchup_policy`) + dispatcher nel heartbeat | 4-5g   |
| P2  | `/nexus/api/routines` CRUD + Dashboard view                                                                                    | 3g     |
| P2  | First routine: nightly security scan (security-agent profile) — supersedes #31 #32 #33                                         | 1-2g   |
| P2  | Second routine: weekly deps audit                                                                                              | 1-2g   |
| P2  | Workflow DAG advancement engine (#30) — valutare kill se routines coprono il caso d'uso                                        | 3-4g   |
| P2  | Cost events granulari: input/cached/output tokens per invocazione (#43)                                                        | 2-3g   |

### Fase 5 — EXPRESSIVE (SPRINT-7+)

Issue riordinate: **#35–#39** → SPRINT-7 on-demand.

| P   | Task                                                                                                           | Effort    |
| --- | -------------------------------------------------------------------------------------------------------------- | --------- |
| P3  | `reports_to` in `agent_registry` + delegazione work_item cross-agent                                           | 4-6g      |
| P3  | Dashboard `/org` (tree), `/costs` (budget_ledger), `/activity` (audit log), `/routines`                        | 8-10g     |
| P3  | Capability classes rimanenti Ops/Quality/Product/Intelligence/Growth — **1 alla volta quando serve** (#35-#39) | 2-3g cad. |

**Regola**: non creare un agent class senza un use case reale entro 2 settimane.

### Parallel tracks

| P   | Task                                                                             | Issue |
| --- | -------------------------------------------------------------------------------- | ----- |
| P2  | Subprocess PGID cleanup su timeout                                               | #44   |
| P3  | Doc adapter contract                                                             | #45   |
| P3  | Doc digest format                                                                | #47   |
| —   | **#46 workflow DAG doc**: chiudere come wontfix se workflows muoiono in SPRINT-6 | #46   |

### Issue da riordinare subito

| Issue                    | Azione                                      |
| ------------------------ | ------------------------------------------- |
| #40 Orchestrator profile | Rename + move SPRINT-3: Alive, diventa P0   |
| #27 #28 #29              | Move SPRINT-5: Visible                      |
| #30                      | Move SPRINT-6: Recurring (da rivalutare)    |
| #31 #32 #33              | Move SPRINT-6: Recurring                    |
| #35–#39                  | Move SPRINT-7: Expressive, regola on-demand |
| #41 Phase 2 SSH dispatch | Move BACKLOG (defer Phase 6)                |
| #42 Phase 3 Hetzner VPS  | Move BACKLOG (defer Phase 7)                |

---

## 7. Paperclip come tool generale Adlimen

Paperclip (`references/paperclip` @ `paperclipai/paperclip`) è runnable su homelab come piattaforma AI company per qualunque iniziativa Adlimen — non scope-limitato a Nexus.

**Use case realistici**:

- Progetti collaterali (app-nutry, app-levero, web-mccom) con CEO + Code Agent
- Company "Research" per literature review, confronti tecnici, issue su repo `llms`
- Routines Paperclip per ops settimanali (deps audit, security scan, link-rot check)
- Sperimentare Board approvals, OrgChart, Routines dal vivo prima di portare i pattern in Nexus

**Regole di boundary**:

- Paperclip e Nexus non condividono stato. Paperclip usa PGlite locale, Nexus usa Atrium.
- Se Paperclip produce schemi/pattern utili, si trascrivono a mano in `docs/paperclip-learnings.md`, no import diretto.
- `references/paperclip` è submodule read-only. Zero dipendenze di codice Nexus verso Paperclip.

**Setup minimo** (su homelab):

```bash
cd references/paperclip
pnpm install
PAPERCLIP_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 pnpm dev
# → http://localhost:3100
# Board claim → crea Company → configura 1 adapter Claude Code locale
```

---

## 8. Caveat

- Paperclip upstream è attivo (commit settimanali, 2026). `git submodule update --remote` periodicamente.
- Leggere il codice Paperclip è legittimo. Copiare: MIT license, ma l'unicità di Nexus sta nell'adattamento Adlimen (DAO-ready, Atrium-backed, Python-native, governance leggera per one-person).
- Il clone precedente (a95739) era già `paperclipai/paperclip` su `master` — la nota su fork HenkDz nell'AGENTS.md era documentazione interna upstream sull'adapter Hermes, non il checkout stesso.
