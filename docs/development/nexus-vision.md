# Nexus — AI Company Orchestration Layer

> "Vedere da solo dove riesco ad arrivare un sistema scalabile, autonomo, automatico."
> — Matteo Cervelli, 2026-04-17

## Vision

Nexus trasforma un singolo sviluppatore in un'organizzazione AI funzionale. Non è un chatbot, non è un assistant — è l'infrastruttura che permette a un solopreneur di avere la capacità operativa di un team di ingegneria.

Il sistema è proattivo per default: non aspetta comandi, ma surfacea lavoro, trova problemi, ricorda cosa un team farebbe, e delega l'esecuzione agli agenti giusti.

Decisioni architetturali correlate:

- [ADR-0001 — Do Not Use Paperclip as Nexus Core](../adr/0001-paperclip-no-go.md)
- [ADR-0002 — Introduce an Internal Nexus Board Layer](../adr/0002-internal-board-layer.md)
- [ADR-0003 — Define a Common Runtime Adapter Contract](../adr/0003-runtime-adapter-contract.md)

---

## Architettura — tre layer

```
┌─────────────────────────────────────────────┐
│  LIMEN  (human interface)                    │
│  Telegram + TUI — notifiche, approvazioni,  │
│  digest mattutino, risposta a domande        │
└──────────────────┬──────────────────────────┘
                   │ events / notifications
┌──────────────────▼──────────────────────────┐
│  NEXUS  (orchestration engine)               │
│  scheduler · spawner · budget tracker       │
│  agent profiles · work queue reader         │
└──────────────────┬──────────────────────────┘
                   │ read/write work_items
┌──────────────────▼──────────────────────────┐
│  ATRIUM  (data + state)                      │
│  work_items · agent_registry · audit_log    │
│  budget_ledger · agent_results              │
└─────────────────────────────────────────────┘
```

**Regola dura**: Nexus non ha un database proprio. Tutto lo stato vive in Atrium. Nexus è puro comportamento.

---

## Nexus — responsabilità

### 1. Work Queue (in Atrium)

Tabella `work_items`:

| campo          | tipo      | note                                                                          |
| -------------- | --------- | ----------------------------------------------------------------------------- |
| `id`           | UUID      |                                                                               |
| `type`         | enum      | `security_scan`, `test_coverage`, `bug_report`, `pr_review`, `social_post`, … |
| `agent_role`   | string    | capability class target (vedi sotto)                                          |
| `priority`     | P0–P3     |                                                                               |
| `status`       | enum      | `pending`, `running`, `done`, `failed`                                        |
| `context`      | JSON      | input per l'agente (repo, file, issue ref, …)                                 |
| `result`       | JSON      | output dopo completamento                                                     |
| `created_at`   | timestamp |                                                                               |
| `started_at`   | timestamp |                                                                               |
| `completed_at` | timestamp |                                                                               |
| `token_cost`   | int       | token consumati dall'esecuzione                                               |

Work items vengono creati da:

- Limen heartbeat (controllo periodico CI, issue aperte, findings radar)
- Input diretto via Telegram ("analizza sicurezza di questo PR")
- Risultati di altri agenti (code agent trova un bug → crea work item per bug fixer)

### 2. Agent Spawner

Nexus spawna agenti come subprocess Claude Code CLI con CLAUDE.md specializzato:

```python
# pattern concettuale — subprocess con profilo agente specializzato
async def spawn_agent(work_item: WorkItem) -> AgentResult:
    profile = AGENT_PROFILES[work_item.agent_role]
    cmd = ["claude", "--profile", profile.config_path, "-p", build_prompt(work_item)]
    proc = await asyncio.create_subprocess_shell(
        " ".join(cmd), stdout=PIPE, stderr=PIPE
    )
    stdout, _ = await proc.communicate(timeout=profile.timeout_seconds)
    return AgentResult(output=stdout, exit_code=proc.returncode)
```

Ogni agente è **ephemeral**: nasce, lavora, muore. Lo stato persiste in Atrium, non nel processo.

### 3. Workflow Engine

Nexus non è una coda piatta di work_items: è un **workflow engine** che esegue DAG di sessioni agente.

Modalità di esecuzione:

- **Serializzata**: step 1 → step 2 → step 3 (il successivo parte solo quando il precedente è completato)
- **Branching**: step N → condizione → step A oppure step B
- Ogni step esegue una persona/agente specifica

Schema (in Atrium):

- `workflows` — definizione del DAG
- `workflow_steps` — step singolo con campi `depends_on`, `condition`, `execution_backend`, `model`

### 4. Scheduler

Nexus ha due modalità di attivazione:

- **Heartbeat** (ogni N minuti): controlla work_items pending e workflows pronti ad avanzare, spawna agenti disponibili
- **Event-driven**: Limen notifica Nexus di nuovi work items (PR aperta, finding critico)

### 4. Budget Tracker

Ogni agente ha un `monthly_token_budget` in Atrium. Il ledger tiene traccia dei consumi. Quando un agente supera il budget, i suoi work items vengono messi in pausa automaticamente.

### 5. Dashboard (homegrown, inspired by selected control-plane patterns)

SPA webapp separata (progetto standalone, non in questo repo). Nexus espone endpoint JSON via FastAPI; la SPA li consuma.

Contenuti:

- Lista agenti attivi / in pausa / con budget esaurito
- Feed work_items in tempo reale (running, done, failed)
- Log decisioni e tool calls per ogni run (audit)
- Grafico token cost per agent × settimana
- Bottone "approva" / "annulla" per job che richiedono human-in-the-loop

Funzionale prima di bello.

---

## Capability Classes — i 7 archetipi

Ogni agente è un `CLAUDE.md` specializzato + subset di tool. I 25+ ruoli del team collassano in 7 classi:

### 1. Code Agent

**Ruoli**: bug finder, bug fixer, test expert, backend expert, DB expert (performance/creation), API/contract expert, library extraction expert

System prompt focus: test-first, find regressions, propose fixes with minimal blast radius.
Tools: Read, Write, Edit, Bash, Glob, Grep.
Default model: `claude-sonnet-4-6`.

### 2. Security Agent

**Ruoli**: security/hardening/vulnerability, hacker per penetration test, zero-day scanner sul sistema

System prompt focus: adversarial thinking, OWASP top 10, no-fix reporting (only find).
Tools: Bash (read-only), Glob, Grep + specializzati (bandit, semgrep, nmap wrapper).
Default model: `claude-sonnet-4-6`. Escalation: `claude-opus-4-6`.

### 3. Ops Agent

**Ruoli**: DevOps expert, hosting expert, infra & operations, disaster recovery (RTO/RPO)

System prompt focus: observability, uptime, runbooks, rollback procedures.
Tools: Bash (read + approval-gated writes), SSH wrappers.
Default model: `claude-sonnet-4-6`.

### 4. Quality Agent

**Ruoli**: standards manager, WCAG expert, verifiers (step verifiers), code quality

System prompt focus: compliance checklists, accessibility audits, standard conformance reports.
Tools: Read, Bash (linters), browser/screenshot per WCAG.
Default model: `claude-haiku-4-5` (task ripetitive e veloci).

### 5. Product Agent

**Ruoli**: frontend UX, web developer, pure designer, native app expert

System prompt focus: user experience, visual consistency, component patterns.
Tools: Read, Write, Bash, browser tools, screenshot.
Default model: `claude-sonnet-4-6`.

### 6. Intelligence Agent

**Ruoli**: ML expert, data science analyst, agent creation & prompting expert

System prompt focus: data patterns, model evaluation, prompt engineering, agent design.
Tools: Python notebooks, Bash, Read.
Default model: `claude-opus-4-6` (richiede ragionamento profondo).

### 7. Growth Agent

**Ruoli**: marketing, social media, coach per Matteo

System prompt focus: content strategy, audience targeting, personal accountability.
Tools: WebSearch, WebFetch, social API wrappers.
Default model: `claude-sonnet-4-6`.

### Orchestrator (meta-agente)

**Ruoli**: CEO/manager, document management

Non esegue lavoro diretto — legge lo stato di tutti gli agenti, prioritizza work_items, crea nuovi work_items per gap identificati. Può essere Limen stesso (heartbeat source "nexus_orchestrator").

---

## Ruoli → Capability Class mapping (lista completa)

| Ruolo originale                                            | Capability Class   |
| ---------------------------------------------------------- | ------------------ |
| Orchestratore / manager / CEO                              | Orchestrator       |
| Gestione dei documenti                                     | Orchestrator       |
| Esperto di test                                            | Code Agent         |
| Bug finder / fixer                                         | Code Agent         |
| Esperto di logiche API / contract                          | Code Agent         |
| Esperto di estrazione librerie                             | Code Agent         |
| Esperti di backend                                         | Code Agent         |
| Esperti di database (velocità / miglioramento / creazione) | Code Agent         |
| Qualità codice / sicurezza / hardening / vuln              | Security Agent     |
| Hacker per penetration test e zero-day                     | Security Agent     |
| Gestione disaster recovery RTO/RPO                         | Ops Agent          |
| Esperto di hosting                                         | Ops Agent          |
| Esperto di DevOps                                          | Ops Agent          |
| Esperti di infrastruttura e operations                     | Ops Agent          |
| Manager degli standard                                     | Quality Agent      |
| Esperto WCAG                                               | Quality Agent      |
| Verificatori vari dei vari step                            | Quality Agent      |
| Web developer                                              | Product Agent      |
| Frontend UX                                                | Product Agent      |
| Designer puro                                              | Product Agent      |
| Esperti di app native                                      | Product Agent      |
| Esperto di ML                                              | Intelligence Agent |
| Analisti data science                                      | Intelligence Agent |
| Esperto di creazione agenti e prompting                    | Intelligence Agent |
| Marketing                                                  | Growth Agent       |
| Social media                                               | Growth Agent       |
| Coach per me                                               | Growth Agent       |

---

## Proattività e visibilità

Limen heartbeat oggi controlla: calendario, reminder, liturgia, compleanni, mail.

**Estensione Nexus**: nuovo `HeartbeatSource` → `NexusAwarenessSource` che ogni mattina surfacea:

```
📋 Nexus Morning Digest — 2026-04-17

🔴 CRITICO (2)
  • CVE-2026-1234 in httpx 0.26 — Security Agent ha trovato ieri sera
  • Test coverage sceso a 68% dopo commit abc1234 — Code Agent

🟡 DA FARE (3)
  • PR #52 aperta da 3 giorni senza review
  • Issue #89 (BACKLOG) non assegnata da 2 settimane
  • limen-assistant: 5 TODO non risolti in src/limen/

🔵 IN CORSO (1)
  • Quality Agent: audit WCAG su app-himalaia (avviato 22:15, ~40min rimasti)

💡 SUGGERIMENTO
  • Hai 3 library extraction candidate in app-ratio — Library Agent potrebbe
    aprire una PR con adlimen-forms estratto (stima: 2h lavoro agente)
```

---

## Execution Model

### Fase 1 — Homelab (adesso)

- Runner primario: `homelab4change.siamese-dominant.ts.net` — macchina dedicata, nessun limite fisso di agenti paralleli
- Nexus come daemon Python (`nexus start`)
- Subprocess spawning via asyncio
- Tre tier di esecuzione: Codex CLI/SDK (task headless), Claude Code CLI `--profile` (persona operator), Anthropic/OpenAI SDK diretto (controllo programmmatico + costo esatto)
- Costo bundled per Codex e Claude Code CLI; costo esatto tracciato solo per tier SDK diretto

### Fase 2 — Runner aggiuntivi (~6 mesi)

- Dispatch SSH verso runner aggiuntivi secondo necessità
- Parallelismo aumentato orizzontalmente

### Fase 3 — Cloud burst (quando necessario)

- Hetzner VPS ephemeral per job pesanti (ML, scan grandi repo)
- Job queue Redis + worker pool
- Solo per overflow — non default

**Nota**: container/Kubernetes non necessari nelle prime due fasi. Il processo Claude Code subprocess è già il "container" — isolato, stateless, controllato.

---

## Relazione con strumenti esistenti

| Paperclip feature      | Nexus equivalent                        | Note                           |
| ---------------------- | --------------------------------------- | ------------------------------ |
| Org chart con ruoli    | Agent Registry in Atrium                | 7 capability classes + profili |
| Heartbeat scheduling   | Limen HeartbeatSource + Nexus scheduler | Già esiste la primitiva        |
| Ticket system          | `work_items` in Atrium                  | Da costruire                   |
| Budget tracking        | `budget_ledger` in Atrium               | Da costruire                   |
| Audit log immutabile   | `agent_results` in Atrium               | Da costruire                   |
| Dashboard UI           | SPA webapp separata + FastAPI JSON API  | Da costruire                   |
| "Bring your own agent" | CLAUDE.md profiles                      | Già il pattern di Claude Code  |

---

## Piano di implementazione

### Step 0 — Schema Atrium (1 giorno)

Tabelle: `work_items`, `agent_registry`, `budget_ledger`, `agent_results`, `workflows`, `workflow_steps`
API endpoints CRUD in Atrium FastAPI.

### Step 1 — Code Agent, primo citizen (2-3 giorni)

- `agents/code-agent/CLAUDE.md` — system prompt specializzato
- Nexus minimal: legge work*items pending di tipo `code*\*`, spawna, scrive risultato
- Test: "trova tutti i TODO nel repo limen-assistant e apri GitHub issues"

### Step 2 — Dashboard minima (1-2 giorni)

- SPA webapp separata (progetto standalone); Nexus espone endpoint JSON FastAPI
- Tabella work_items, stati, log
- Limen può inviare link al dashboard via comando Telegram

### Step 3 — NexusAwarenessSource in Limen heartbeat (1 giorno)

- Morning digest come da template sopra
- Proattività operativa attiva

### Step 4 — Security Agent (2-3 giorni)

- Integrazione bandit + semgrep
- Scheduled scan notturno su tutti i repo

### Step 5+ — espansione progressiva

Un capability class alla volta, quando il precedente è stabile.

---

## Nome e posizione nel repo

**Nexus** (`~/dev/services/nexus/`) — servizio separato, stesso pattern di limen-assistant e radar-agent.

Condivide:

- Atrium come backend (`:8100` o Tailscale)
- Limen come canale di notifica
- `adlimen-*` libraries

Non condivide codice diretto con Limen (dipendenza circolare da evitare).

---

## Idea: Code Agent che costruisce Nexus

Il primo lavoro del Code Agent potrebbe essere costruire Nexus stesso — bootstrapping agente. Input: questo documento. Output: struttura iniziale del repo con schema Atrium, profili agente, Nexus daemon skeleton.

Questo testa immediatamente il loop completo:

1. Matteo scrive spec (questo doc)
2. Code Agent legge spec, genera codice
3. Nexus esiste e può accettare il primo work item reale

---

_Documento creato: 2026-04-17 — da conversazione design Nexus_
_Status: DRAFT — da revisionare prima di iniziare implementazione_
