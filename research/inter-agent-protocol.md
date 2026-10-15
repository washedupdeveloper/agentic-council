# A Uniform YAML Inter-Agent Message Schema for Multi-Agent Code Review

**Grounded survey of agent-to-agent protocol standards + a recommended envelope design**

Version 1.0 · Schema `review.msg/v1` · Status: proposal

---

## 0. Executive summary

A multi-agent code-review system (specialist review bots + an orchestrator that loops until a
satisfaction score threshold is met) needs **one** message shape that every agent can parse and
iterate over. We surveyed the field — Google A2A, [AN] MCP, ACP (Zed), AGNTCY ACP/OASF, the
[OI] Agent Protocol, FIPA-ACL, JSON-RPC 2.0, CloudEvents, and AG-UI — and extracted the recurring
design lessons. The recommended design is a **single YAML envelope** that borrows:

- **Correlation + thread semantics** from JSON-RPC 2.0 (`id`), FIPA-ACL (`conversation-id`,
  `reply-with`, `in-reply-to`) and A2A (`Task.id` + `contextId`) [6][12][1].
- **A typed `type`/performative field** from FIPA-ACL's performatives and A2A's method taxonomy —
  this is what lets the orchestrator distinguish a `finding` from a `score` from a `control` [12][1].
- **A `phase` field** to encode the review lifecycle (intake → review → aggregate → fix → verify),
  which none of the surveyed specs model directly; it is the review domain's own contribution.
- **Explicit termination signals** (`satisfied | continue | blocked | escalate`) as first-class
  control messages, because the loop's stopping condition is a message, not an implicit side effect.
- **Event-envelope discipline** from CloudEvents (`specversion`, `id`, `source`, `type`, `subject`,
  `time`) [14][15].
- **Capability discovery** from A2A Agent Cards and MCP `initialize` [1][4].

Validation: **Pydantic v2 as the single source of truth**, emitting **JSON Schema Draft 2020-12**,
with YAML parsed to data and validated against that schema. Versioning is additive/minor-friendly
with a `schema_version` field and a `extensions` escape hatch [17][18].

---

## Part 1 — Survey of existing standards and lessons

### 1.1 Google A2A (Agent2Agent)

- **Envelope fields.** A2A wraps everything in **JSON-RPC 2.0** over HTTP(S): `jsonrpc`, `id`,
  `method`, `params` / `result` / `error` [1][2]. The domain objects are `Task` (`id`, `sessionId`
  or `contextId`, `status`, `artifacts`, `history`), `Message` (`role` = user/agent, `parts[]`,
  `messageId`, `taskId`, `contextId`, `kind`), and `Part` (`TextPart` | `FilePart` | `DataPart`) [1][2].
  `TaskStatus` carries a `state` (`TaskState` enum), an optional `message`, and a `timestamp` [2].
- **Transport.** HTTP(S) only; three equal transports — JSON-RPC 2.0, gRPC (protobuf), and
  HTTP+JSON/REST — plus SSE for streaming (`message/stream`, `tasks/resubscribe`) [1].
- **Request / response / notification / error.** Requests and responses are JSON-RPC objects;
  streaming is SSE carrying complete JSON-RPC response objects. Errors use standard JSON-RPC codes
  `-32700…-32603` plus an A2A-specific range `-32000…-32099` [1][2].
- **Correlation IDs.** `Task.id` (client-generated UUID) is the unit of correlation; `sessionId`/
  `contextId` groups related tasks; `Message.messageId` identifies a message; `referenceTaskIds`
  link follow-ups to prior tasks [2].
- **Capability discovery.** The **Agent Card** (typically `/.well-known/agent-card.json`):
  `name`, `description`, `url`, `version`, `protocolVersion`, `capabilities`
  (`streaming`, `pushNotifications`, `extendedAgentCard`), `skills[]`
  (`id`, `name`, `description`, `tags`, `examples`, `inputModes`, `outputModes`),
  `defaultInputModes`, `defaultOutputModes`, `securitySchemes`, `security`, and optional JWS
  `signatures` [1][3].
- **Lesson for us.** Task-as-unit-of-work + a self-describing capability manifest is exactly what a
  review orchestrator needs for discovery. But A2A's `TaskState` is a *transport lifecycle*, not a
  *review phase* — we must add our own `phase`.

### 1.2 [AN] MCP (Model Context Protocol)

- **Envelope fields.** Strict JSON-RPC 2.0: `jsonrpc: "2.0"`, `id`, `method`, `params`, and
  `result` XOR `error`. MCP tightens base JSON-RPC: `id` MUST be a string/number and **never null**,
  unique per session; UTF-8 only [4][5].
- **Transport.** Two official transports: **stdio** (newline-delimited JSON, agent as subprocess;
  stderr reserved for logs) and **Streamable HTTP** (POST `/mcp`, optional SSE stream back;
  `Mcp-Session-Id` header) [4][5].
- **Request / response / notification / error.** Three shapes distinguished purely by field
  presence: request (id + method), response (id + result XOR error), notification (method, **no id**,
  never answered). MCP adds application-level errors via `result.isError: true` — distinct from
  protocol-level `error.code` — so an LLM can read a tool failure and retry [4][5].
- **Correlation IDs.** The JSON-RPC `id`; cancellation via `$/cancelRequest` referencing the
  original id; progress via `progressToken` [4][5].
- **Capability discovery.** Mandatory `initialize` → `initialized` handshake: both sides exchange
  `protocolVersion`, `clientInfo`/`serverInfo`, and `capabilities` (e.g. `tools`, `resources`,
  `prompts`, `logging`); `notifications/*/list_changed` signal capability drift [4][5].
- **Lesson for us.** The request/response/notification trichotomy driven by *field presence*, and
  the two-tier error model (transport error vs. semantic failure payload), are directly portable.

### 1.3 ACP — Agent Client Protocol (Zed)

- **Envelope fields.** JSON-RPC 2.0 methods and notifications. Core methods: `initialize`,
  `authenticate`, `session/new`, `session/load`, `session/prompt`, `session/cancel`,
  `session/update` (notification), `session/request_permission` [7][8].
- **Transport.** Bidirectional **stdio** (editor spawns the agent as a subprocess), UTF-8,
  newline-delimited; remote/Streamable HTTP is a draft [7][8].
- **Request / response / notification / error.** "Methods" = request/response pairs; "notifications"
  are one-way and "never receive responses (success or error)". `session/prompt` returns a
  `stopReason` enum (`end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`).
  Cancellation is **not** an error — it is a semantic `cancelled` stop reason [7][8].
- **Correlation IDs.** `sessionId` groups a conversation; `toolCallId`/`messageId` track streaming
  updates; `session/cancel` interrupts the current turn [7].
- **Capability discovery.** `initialize` negotiates `protocolVersion` (a single integer, bumped only
  on breaking changes) **and** capabilities in both directions (`clientCapabilities`,
  `agentCapabilities`); an omitted capability means unsupported; **adding** a capability is
  non-breaking [7][8].
- **Lesson for us.** Integer major-version + capability flags + "cancellation is a result, not an
  error" are all worth copying. So is stable-ID streaming updates (`session/update`).

### 1.4 AGNTCY (Agent Connect Protocol + OASF + directory)

- **Envelope fields.** ACP is specified as **OpenAPI 3.1.1**; objects include `Agent`,
  `AgentACPDescriptor`, `Thread`, `Run` (thread runs / stateless runs), and `Model` [9].
- **Transport.** REST/HTTP (OpenAPI-defined endpoints: search agents, get agent, create threads,
  create runs, stream runs) [9].
- **Request / response / notification / error.** HTTP verbs + status codes; long-running runs
  support streaming and webhook callbacks; `interrupts` allow a run to pause and request input,
  then resume [9][10].
- **Correlation IDs.** Thread id + run id; `Run` creation returns an id used to poll/stream results [9].
- **Capability discovery.** The **ACP descriptor** declares the agent's config/input/output/
  interrupt schemas; the **OASF** (Open Agentic Schema Framework) provides a shared attribute
  dictionary and an **Agent Directory Service** for discovery; agents can be identified by DID,
  Okta, A2A id, etc. Note: AGNTCY has marked ACP **deprecated in favour of A2A** in OASF [9][10].
- **Lesson for us.** A shared *vocabulary/dictionary* (OASF) is the FIPA "ontology" idea revived —
  the antidote to semantic drift. Our `category` enum and severity scale are a small in-band
  ontology.

### 1.5 [OI] Agent Protocol (a.k.a. "Agent Protocol")

- **Envelope fields.** REST resources: `Run` (`run_id`, `status`, `thread_id`, `assistant_id`,
  timestamps), `Thread`, `Message`, and an `Agent` introspection record [11].
- **Transport.** HTTP + SSE; streaming primitives defined in CDDL (source of truth) with generated
  TS/Python bindings; also WebSocket upgrade for bidirectional streams [11].
- **Request / response / notification / error.** Run lifecycle `status`
  (`queued`, `in_progress`, `requires_action`, `cancelling`, `cancelled`, `failed`, `completed`,
  `incomplete`, `expired`); `requires_action` is the human-in-the-loop pause; streaming events for
  tool/run lifecycle, state snapshots, checkpoints, custom events [11].
- **Correlation IDs.** `thread_id` (multi-turn grouping) + `run_id` (single execution) + `event-id`
  for replay [11].
- **Capability discovery.** `GET /agents/{agent_id}/schemas` returns input/output/state/config
  schemas **in JSON Schema**; `POST /agents/search` lists agents by metadata [11].
- **Lesson for us.** Thread vs. run separation, an explicit `requires_action`/interrupt state, and
  schemas-as-introspection are all directly applicable. Our `thread_id` + `message_id` mirrors
  thread + run.

### 1.6 FIPA-ACL performatives

- **Envelope fields.** `:performative`, `:sender`, `:receiver`, `:reply-to`, `:content`,
  `:language`, `:encoding`, `:ontology`, `:protocol`, `:conversation-id`, `:reply-with`,
  `:in-reply-to`, `:reply-by` [12][13]. The FIPA *envelope* (transport metadata) separately carries
  `to`, `from`, `acl-representation`, `date`, `payload-length`, `payload-encoding`, `received`,
  `security-object` [12].
- **Transport.** Agent Communication Channel / Message Transport Service (abstract; typically
  IIOP/HTTP in the JADE era) [12].
- **Request / response / notification / error.** Expressed as **communicative acts** (~20):
  `inform`, `request`, `query-if`, `query-ref`, `propose`, `accept-proposal`, `reject-proposal`,
  `agree`, `refuse`, `confirm`, `disconfirm`, `cfp`, `subscribe`, `cancel`, `failure`,
  `not-understood` [12][13]. Interaction protocols (FIPA-Request, Contract-Net, Subscribe/Notify)
  are the sanctioned message *sequences* [13].
- **Correlation IDs.** `:conversation-id` (dialogue thread), `:reply-with` (token to reply with),
  `:in-reply-to` (the token being answered), `:reply-by` (deadline) [12].
- **Capability discovery.** Via the Agent Management System / Directory Facilitator (yellow pages)
  rather than an in-band card [12].
- **Lesson for us.** FIPA is the richest prior art: an explicit **performative** (intent verb), a
  **conversation id + reply-with/in-reply-to** triple, an **ontology** slot, and a **reply-by**
  deadline. Its documented failure mode — dropping the ontology causes *semantic drift* — is
  exactly why we keep a controlled `category`/`severity` vocabulary [13].

### 1.7 JSON-RPC 2.0

- **Envelope fields.** `jsonrpc`, `id`, `method`, `params`; response `id` + (`result` XOR `error`);
  error object `{code, message, data?}`. Notifications omit `id` [4][6].
- **Transport.** Transport-agnostic (stdio, HTTP, WebSocket…) [6].
- **Request / response / notification / error.** The canonical trichotomy; reserved error codes
  `-32700` parse, `-32600` invalid request, `-32601` method not found, `-32602` invalid params,
  `-32603` internal; `-32000…-32099` implementation-defined [6].
- **Correlation IDs.** `id` echoed from request into response.
- **Capability discovery.** None (out of scope).
- **Lesson for us.** Keep the id-echo correlation and the structured error object; but a
  review system is *asynchronous and many-to-many*, so we generalize `method` into `type` and add
  `thread_id` so a reply can find its conversation even across processes.

### 1.8 CloudEvents

- **Envelope fields.** REQUIRED `id`, `source`, `specversion`, `type`; OPTIONAL `datacontenttype`,
  `dataschema`, `subject`, `time`; plus arbitrary **extension** attributes [14][15].
- **Transport.** Protocol bindings (HTTP, AMQP, MQTT, Kafka, NATS…); structured or binary mode;
  JSON event format maps attributes to top-level JSON members and payload to `data` [14][15].
- **Request / response / notification / error.** Pure **notification** model — CloudEvents are
  facts that happened; no built-in request/response or error semantics [14].
- **Correlation IDs.** `source` + `id` uniquely identify an event; duplicates are defined as equal
  `(source, id)` pairs. `subject` qualifies sub-structure of the source [14][15].
- **Capability discovery.** None.
- **Lesson for us.** Separate **envelope/context attributes** (routing, filterable) from **payload**
  (`data`). Keep a `specversion`-style version field and a `subject`-style pointer to the artifact
  under discussion. Use `(source, id)` for idempotency.

### 1.9 AG-UI (Agent–User Interaction Protocol) — adjacent, but instructive

- **Envelope fields.** Every event: `type` (SCREAMING_SNAKE_CASE), `messageId`, `timestamp`,
  optional `rawEvent`. ~16–30 typed events in families: lifecycle, text, tool calls, state,
  activity, reasoning, special [16].
- **Transport.** Transport-agnostic; typically SSE (also WebSocket/binary) [16].
- **Request / response / notification / error.** Event stream bracketed by `RUN_STARTED` …
  `RUN_FINISHED` / `RUN_ERROR`; state via `STATE_SNAPSHOT` (full) + `STATE_DELTA` (RFC 6902 JSON
  Patch) [16].
- **Correlation IDs.** `threadId`, `runId`, `parentRunId` (append-only branching log), `messageId`,
  `toolCallId` [16].
- **Capability discovery.** `RunAgentInput.tools` declares tools; no agent card [16].
- **Lesson for us.** **Snapshot + delta** is a superb pattern for propagating the evolving findings
  set without resending everything each loop. `parentRunId` gives us cheap iteration ancestry.

### 1.10 Cross-cutting lessons

| Concern | Best prior art | What we take |
|---|---|---|
| Envelope vs. payload | CloudEvents [14] | Context fields flat + `payload`/`data` nested |
| Intent verb | FIPA performatives [12][13] | `type` enum (request/finding/score/…/control) |
| Correlation | FIPA `conversation-id`+`reply-with` [12]; JSON-RPC `id` [6] | `message_id` + `correlation_id` + `thread_id` |
| Lifecycle/phase | A2A `TaskState` [1]; [OI] `Run.status` [11] | `phase` enum (review-domain specific) |
| Termination | ACP `stopReason` [7]; [OI] terminal status [11] | `control` message with `termination` signal |
| Capability discovery | A2A Agent Card [1][3]; MCP `initialize` [4] | `capabilities` block + registry |
| Version negotiation | ACP integer `protocolVersion` [7]; CloudEvents `specversion` [14] | `schema_version` + capability flags |
| Error model | JSON-RPC codes [6]; MCP `isError` [4] | `status` + structured `error` object |
| Idempotency | CloudEvents `(source,id)` [14] | `(from, message_id)` dedupe |
| Streaming state | AG-UI snapshot+delta [16] | optional `findings_delta` in aggregate messages |
| Shared vocabulary | FIPA ontology [13]; OASF [10] | controlled `category`/`severity` enums |

---

## Part 2 — Recommended YAML envelope design

### 2.1 Design principles

1. **One shape for everything.** Every message — intake, finding, score, control — is the same
   envelope with the same required keys. A consumer can iterate a `findings:` list without knowing
   the message type first.
2. **Context flat, payload nested.** Routing/control metadata lives at the top level (filterable,
   cheap to parse); domain content lives under `payload`. (CloudEvents' split [14].)
3. **Explicit intent and phase.** `type` says *what kind of act*; `phase` says *where in the review
   loop*. (FIPA performative [12] + review-domain lifecycle.)
4. **Correlation is first-class.** `message_id` (identity), `correlation_id` (reply linkage),
   `thread_id` (conversation/review session). (FIPA triple [12].)
5. **Termination is a message.** The loop stops because the orchestrator emits a `control` message
   with `termination: satisfied`, never because a side effect happened.
6. **Forward-compatible by default.** `schema_version` + `capabilities` + an `extensions` map;
   unknown keys tolerated; enums extensible via `x-` prefixed values. (ACP [7].)
7. **Machine-first, human-readable second.** YAML for operator legibility; the same bytes are
   valid JSON after parse, so JSON Schema validates them.

### 2.2 The envelope

```yaml
# ---- Context / envelope (routing & control) ----
schema_version: "review.msg/v1"      # schema identity + major version
message_id: "msg-0f3a…"              # ULID/UUID; unique per (from)
correlation_id: "msg-…"              # message_id this is a reply to (null for unsolicited)
thread_id: "rev-2026-10-05-pr1842"   # review session; groups all related messages
from: "security-reviewer"            # agent id (or "orchestrator")
to: "orchestrator"                   # agent id | "broadcast"
type: "finding"                      # request|response|finding|score|vote|control|heartbeat
phase: "review"                      # intake|review|aggregate|fix|verify
timestamp: "2026-10-05T09:14:03Z"    # RFC 3339 UTC
priority: "normal"                   # low|normal|high|critical
status: "ok"                         # ok|partial|error|blocked|skipped
subject:                             # artifact refs under review
  repo: "acme/payments-api"
  commit: "9f2c1ab…"
  base_commit: "3d10ee7…"
  files:
    - path: "src/auth/session.py"
      lines: [118, 142]              # inclusive 1-based range
subject_hash: "sha256:…"             # content hash for idempotency/caching
capabilities:                        # sender's declared capabilities (discovery)
  languages: ["python", "typescript"]
  checks: ["sast", "deps", "secrets", "style", "logic"]
  produces: ["findings", "scores"]
payload: {}                          # type-specific body (see §2.4)
findings: []                         # structured findings (finding/aggregate messages)
scores: {}                           # per-category + weights + aggregate
metrics: {}                          # timing/token/coverage counters
artifacts: []                        # produced files/diffs/reports
actions: []                          # requested or performed next steps
error: null                          # {code, message, detail} when status == error
extensions: {}                       # namespaced escape hatch; unknown keys tolerated
```

### 2.3 Field rationale

| Field | Type | Required | Rationale / precedent |
|---|---|---|---|
| `schema_version` | string | ✔ | CloudEvents `specversion` [14]; ACP integer version [7]. `review.msg/v1` = name + major. |
| `message_id` | string | ✔ | JSON-RPC `id` [6], A2A `messageId` [1]. ULID gives sortable uniqueness. |
| `correlation_id` | string\|null | ✔ | FIPA `:in-reply-to` [12]; JSON-RPC id-echo [6]. Enables request→response pairing. |
| `thread_id` | string | ✔ | FIPA `:conversation-id` [12]; A2A `contextId` [1]; [OI] `thread_id` [11]. Groups one review. |
| `from` | string | ✔ | FIPA `:sender` [12]; CloudEvents `source` [14]. Agent id. |
| `to` | string | ✔ | FIPA `:receiver` [12]. Single id or `broadcast`. |
| `type` | enum | ✔ | FIPA performative [12] + A2A method category [1]. The intent verb. |
| `phase` | enum | ✔ | Review-domain lifecycle; no direct precedent, closest is A2A `TaskState` [1]. |
| `timestamp` | RFC3339 | ✔ | CloudEvents `time` [15]; A2A `TaskStatus.timestamp` [2]. |
| `priority` | enum | ○ | Scheduling hint; FIPA has no analog; useful for fix ordering. |
| `status` | enum | ✔ | [OI] `Run.status` [11]; MCP `isError` [4]. Outcome of *this* message. |
| `subject` | object | ○ | CloudEvents `subject` [14] generalized to artifact refs (repo/commit/file/line). |
| `subject_hash` | string | ○ | Idempotency key (CloudEvents `(source,id)` idea [14]). |
| `capabilities` | object | ○ | A2A Agent Card [1][3]; MCP `initialize` [4]. Inline discovery. |
| `payload` | object | ○ | CloudEvents `data` [14]. Type-specific body. |
| `findings` | array | ○ | The iterable core. Each element is a structured finding (§2.5). |
| `scores` | object | ○ | Per-category scores + weights + aggregate (§2.6). |
| `metrics` | object | ○ | Cost/coverage telemetry; [OI] `usage`-style [11]. |
| `artifacts` | array | ○ | A2A `Artifact` [1]; diffs/reports produced. |
| `actions` | array | ○ | Requested next steps; FIPA `request` content [12]. |
| `error` | object\|null | ○ | JSON-RPC error object [6] — `{code, message, detail}`. |
| `extensions` | object | ○ | CloudEvents extensions [14]; ACP forward-compat [7]. |

### 2.4 `type` values and their payloads

| `type` | Direction | Meaning | Key payload fields |
|---|---|---|---|
| `request` | orchestrator → specialist | "review this artifact" | `payload.task`, `payload.scope`, `payload.deadline` |
| `response` | specialist → orchestrator | acknowledgement / result wrapper | `payload.ack_for`, `payload.accepted` |
| `finding` | specialist → orchestrator | one or many findings | `findings[]` |
| `score` | specialist/orchestrator → * | per-category scores | `scores{}` |
| `vote` | specialist → orchestrator | approve/reject a fix | `payload.vote`, `payload.rationale` |
| `control` | orchestrator → * | loop control / termination | `payload.termination`, `payload.reason` |
| `heartbeat` | any → any | liveness + progress | `payload.progress`, `metrics.elapsed_ms` |

`phase` values: `intake` → `review` → `aggregate` → `fix` → `verify` (then back to `review`/`aggregate`
if not satisfied). This is the loop's state machine.

### 2.5 The `findings[]` element

```yaml
findings:
  - id: "F-0007"
    category: "security"          # security|correctness|performance|style|deps|secrets|api|test
    severity: "high"              # info|low|medium|high|critical
    confidence: 0.86              # 0.0–1.0
    location:
      file: "src/auth/session.py"
      lines: [118, 142]
      symbol: "create_session"
    evidence: |                   # verbatim snippet / citation
      token = request.args["token"]  # unsanitized, flows into SQL below
    rule_id: "SAST-SQLI-004"      # originating rule/check (traceability)
    suggested_fix: |
      Use a parameterized query and validate the token against the session store.
    references:
      - "CWE-89"
      - "https://cwe.mitre.org/data/definitions/89.html"
    status: "open"                # open|accepted|rejected|fixed|wontfix
```

Controlled `category`/`severity` enums are the small in-band **ontology** FIPA demanded [13];
without them, two reviewers mean different things by "critical" (semantic drift) [13].

### 2.6 The `scores{}` object

```yaml
scores:
  scale: "0-10"
  categories:
    security:      { score: 6.5, weight: 0.35, confidence: 0.9 }
    correctness:   { score: 8.0, weight: 0.30, confidence: 0.85 }
    performance:   { score: 7.2, weight: 0.15, confidence: 0.7 }
    style:         { score: 9.0, weight: 0.10, confidence: 0.95 }
    tests:         { score: 5.0, weight: 0.10, confidence: 0.8 }
  aggregate: 6.94                 # Σ(score×weight); threshold comparison uses this
  threshold: 8.0
  satisfied: false                # aggregate >= threshold AND no critical open finding
  by_agent:                       # per-specialist breakdown for audit
    security-reviewer: 6.5
    correctness-reviewer: 8.0
```

`aggregate` is a **weighted mean**, but `satisfied` is deliberately a compound predicate:
`aggregate >= threshold AND no open finding with severity in {high, critical}`. This prevents a
high average from masking one blocking defect.

### 2.7 Orchestrator aggregation and specialist consumption

**Orchestrator loop (pseudo):**

```text
thread_id = new_review(pr)
emit request(phase=intake, to=broadcast)           # fan-out
collect responses; for each specialist, request a review
loop:
  findings = collect(type==finding)                 # may use findings_delta
  scores   = collect(type==score)
  agg      = weighted_mean(scores)                  # §2.6
  blocking = any(f.severity in {high,critical} and f.status==open for f in findings)
  if agg >= threshold and not blocking:
      emit control(termination=satisfied)
      break
  if no progress in N iterations:
      emit control(termination=blocked, reason="no score movement")
      break
  emit request(phase=fix, actions=[...])            # ask a fixer agent
  verify = collect(type==finding, phase=verify)
  # repeat
```

**Specialist consumption/production:** a specialist reads `subject` to fetch the diff, runs its
checks, and emits **one** `finding` message per batch (or a single message carrying many findings)
plus a `score` message. It sets `correlation_id = request.message_id`, reuses the request's
`thread_id`, and echoes `subject`. It never needs to know the loop's internals — it only needs the
envelope.

### 2.8 Termination / control signals

```yaml
type: control
payload:
  termination: "satisfied"   # satisfied|continue|blocked|escalate
  reason: "aggregate 8.4 >= threshold 8.0 and no open high/critical findings"
  iterations: 3
  final_scores: { aggregate: 8.4, threshold: 8.0 }
```

- `satisfied` — stop, success.
- `continue` — explicit "keep going" (used when a human/orchestrator policy overrides a borderline score).
- `blocked` — cannot proceed (missing artifact, tool failure, no score movement).
- `escalate` — hand off to a human or a stronger agent (FIPA `failure`/`not-understood` [12]).

Every `control` message MUST carry `termination`; it is the single field the loop watches.

---

## Part 3 — Schema validation & evolution

### 3.1 Choosing the representation

| Option | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| **JSON Schema** (Draft 2020-12) | Universal, language-agnostic, `ajv`/`jsonschema`/`yamale` support, validates YAML after parse; OpenAPI-compatible [17][18] | No cross-field arithmetic by default; `additionalProperties:false` must be opted into | **Emit this** as the interchange artifact |
| **Pydantic v2** | Runtime validation + typed models; `model_json_schema()` emits Draft 2020-12 [17]; Python-native, good errors | Python-only at authoring time | **Source of truth** for authoring |
| **CUE** | Order-independent unification, cross-field constraints, defaults, `cue vet data.yaml` validates YAML directly; closed definitions catch unknown keys [18][19] | Steeper learning curve; Go-centric; smaller ecosystem | Optional *lint* layer for complex invariants |

**Recommendation:** author in **Pydantic v2**, generate **JSON Schema Draft 2020-12**, and validate
every inbound/outbound message against that schema. Add **CUE** only if/when cross-field invariants
(e.g. `limits >= requests`-style rules like `aggregate == Σ(score×weight)`) become worth a second
tool. This gives a Python implementation *and* a language-neutral contract from one source.

### 3.2 How to validate a YAML message

```python
import yaml, json
from jsonschema import Draft202012Validator

schema = json.load(open("review-msg.schema.json"))
validator = Draft202012Validator(schema)

def validate_message(text: str) -> dict:
    data = yaml.safe_load(text)          # YAML -> plain data (JSON-compatible)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        raise ValueError(
            "\n".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors)
        )
    return data
```

Pydantic-native path (same schema, runtime types):

```python
from pydantic import TypeAdapter
Envelope = TypeAdapter(ReviewEnvelope)     # ReviewEnvelope: BaseModel
msg = Envelope.model_validate(yaml.safe_load(text))
```

Single source of truth (generate the contract from the models):

```python
import json
from review_schema import ReviewEnvelope
json.dump(ReviewEnvelope.model_json_schema(), open("review-msg.schema.json", "w"), indent=2)
```

The reverse (JSON Schema → Pydantic) is possible with `datamodel-code-generator` [17], but pick
**one** direction and generate the other; do not hand-maintain both.

### 3.3 Versioning and evolution without breaking agents

1. **Version the schema in the payload** (`schema_version: "review.msg/v1"`), CloudEvents-style [14].
   The major number bumps only on breaking changes (ACP's rule [7]).
2. **Additive-by-default.** New optional fields, new enum members, new `type`/`phase` values are
   **minor** changes; consumers MUST ignore unknown fields. Set `additionalProperties: true` at the
   envelope root (tolerance) while keeping it `false` inside `findings[]` (strictness where it
   matters) — the CUE "closed definition" idea applied selectively [19].
3. **Capability flags over version checks.** Agents advertise what they understand in
   `capabilities`; a producer degrades gracefully rather than refusing an unknown version (ACP
   pattern [7]).
4. **Extension namespaces.** Anything experimental goes under `extensions.<vendor>.*`; promote to
   core only after two consumers rely on it (CloudEvents extensions [14]).
5. **Deprecation window.** Mark fields `deprecated` in JSON Schema (`"deprecated": true`), keep
   accepting them for one major cycle, log a warning.
6. **Golden-file tests.** Keep a corpus of valid/invalid messages; run schema validation in CI on
   every schema change so drift is caught before agents diverge [18].

---

## Part 4 — Concrete examples

### 4.1 Intake request (orchestrator → all specialists)

```yaml
schema_version: "review.msg/v1"
message_id: "01J8Z6K7Q9X2M4P0R1S2T3U4V5"
correlation_id: null
thread_id: "rev-2026-10-05-pr1842"
from: "orchestrator"
to: "broadcast"
type: "request"
phase: "intake"
timestamp: "2026-10-05T09:00:00Z"
priority: "high"
status: "ok"
subject:
  repo: "acme/payments-api"
  commit: "9f2c1ab7c3e4f5a6b7c8d9e0f1a2b3c4d5e6f708"
  base_commit: "3d10ee7a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"
  files:
    - path: "src/auth/session.py"
      lines: [100, 180]
    - path: "src/db/query.py"
      lines: [1, 90]
payload:
  task: "review"
  scope: ["security", "correctness", "performance", "style", "tests"]
  deadline: "2026-10-05T09:10:00Z"
  instructions: "Flag only issues introduced or worsened by this commit."
actions:
  - action: "review"
    target: "security-reviewer"
  - action: "review"
    target: "correctness-reviewer"
extensions: {}
```

### 4.2 Per-specialist finding set (security-reviewer → orchestrator)

```yaml
schema_version: "review.msg/v1"
message_id: "01J8Z6M2A7B8C9D0E1F2G3H4J5"
correlation_id: "01J8Z6K7Q9X2M4P0R1S2T3U4V5"
thread_id: "rev-2026-10-05-pr1842"
from: "security-reviewer"
to: "orchestrator"
type: "finding"
phase: "review"
timestamp: "2026-10-05T09:04:12Z"
priority: "high"
status: "ok"
subject:
  repo: "acme/payments-api"
  commit: "9f2c1ab7c3e4f5a6b7c8d9e0f1a2b3c4d5e6f708"
  files:
    - path: "src/auth/session.py"
      lines: [118, 142]
findings:
  - id: "F-0007"
    category: "security"
    severity: "high"
    confidence: 0.86
    location:
      file: "src/auth/session.py"
      lines: [118, 142]
      symbol: "create_session"
    evidence: |
      token = request.args["token"]
      cursor.execute(f"SELECT * FROM sessions WHERE token = '{token}'")
    rule_id: "SAST-SQLI-004"
    suggested_fix: |
      Use a parameterized query:
        cursor.execute("SELECT * FROM sessions WHERE token = %s", (token,))
    references:
      - "CWE-89"
      - "https://cwe.mitre.org/data/definitions/89.html"
    status: "open"
  - id: "F-0008"
    category: "secrets"
    severity: "critical"
    confidence: 0.97
    location:
      file: "src/auth/session.py"
      lines: [131, 131]
    evidence: |
      SIGNING_KEY = "sk_live_51H8x...redacted-pattern-match"
    rule_id: "SECRETS-001"
    suggested_fix: "Move to environment/secret manager and rotate the key."
    references:
      - "CWE-798"
    status: "open"
metrics:
  files_scanned: 2
  duration_ms: 4812
  tokens_used: 1290
```

### 4.3 Score report (security-reviewer → orchestrator)

```yaml
schema_version: "review.msg/v1"
message_id: "01J8Z6M3K8L9M0N1P2Q3R4S5T6"
correlation_id: "01J8Z6K7Q9X2M4P0R1S2T3U4V5"
thread_id: "rev-2026-10-05-pr1842"
from: "security-reviewer"
to: "orchestrator"
type: "score"
phase: "review"
timestamp: "2026-10-05T09:04:15Z"
priority: "normal"
status: "ok"
scores:
  scale: "0-10"
  categories:
    security: { score: 6.5, weight: 0.35, confidence: 0.9 }
  aggregate: 6.5
  threshold: 8.0
  satisfied: false
payload:
  rationale: "One critical secret exposure and one high-severity SQL injection."
```

### 4.4 Orchestrator aggregation (orchestrator → all)

```yaml
schema_version: "review.msg/v1"
message_id: "01J8Z6M9V0W1X2Y3Z4A5B6C7D8"
correlation_id: null
thread_id: "rev-2026-10-05-pr1842"
from: "orchestrator"
to: "broadcast"
type: "score"
phase: "aggregate"
timestamp: "2026-10-05T09:05:00Z"
priority: "high"
status: "ok"
findings_count: 5
scores:
  scale: "0-10"
  categories:
    security:    { score: 6.5, weight: 0.35, confidence: 0.9 }
    correctness: { score: 8.0, weight: 0.30, confidence: 0.85 }
    performance: { score: 7.2, weight: 0.15, confidence: 0.7 }
    style:       { score: 9.0, weight: 0.10, confidence: 0.95 }
    tests:       { score: 5.0, weight: 0.10, confidence: 0.8 }
  aggregate: 6.94
  threshold: 8.0
  satisfied: false
  by_agent:
    security-reviewer: 6.5
    correctness-reviewer: 8.0
    performance-reviewer: 7.2
    style-reviewer: 9.0
    test-reviewer: 5.0
payload:
  decision: "continue"
  reason: "aggregate 6.94 < threshold 8.0; 1 critical + 1 high open finding"
actions:
  - action: "fix"
    target: "fixer-agent"
    findings: ["F-0007", "F-0008"]
```

### 4.5 Fix request (orchestrator → fixer)

```yaml
schema_version: "review.msg/v1"
message_id: "01J8Z6N5E6F7G8H9J0K1L2M3N4"
correlation_id: "01J8Z6M9V0W1X2Y3Z4A5B6C7D8"
thread_id: "rev-2026-10-05-pr1842"
from: "orchestrator"
to: "fixer-agent"
type: "request"
phase: "fix"
timestamp: "2026-10-05T09:05:01Z"
priority: "critical"
status: "ok"
subject:
  repo: "acme/payments-api"
  commit: "9f2c1ab7c3e4f5a6b7c8d9e0f1a2b3c4d5e6f708"
payload:
  task: "fix"
  findings: ["F-0007", "F-0008"]
  instructions: |
    Fix the SQL injection in create_session and remove the hard-coded signing key.
    Do not change unrelated behavior.
  deadline: "2026-10-05T09:15:00Z"
actions:
  - action: "apply_fix"
    finding: "F-0007"
  - action: "apply_fix"
    finding: "F-0008"
```

### 4.6 Verification result (verifier → orchestrator)

```yaml
schema_version: "review.msg/v1"
message_id: "01J8Z6P1Q2R3S4T5U6V7W8X9Y0"
correlation_id: "01J8Z6N5E6F7G8H9J0K1L2M3N4"
thread_id: "rev-2026-10-05-pr1842"
from: "verifier-agent"
to: "orchestrator"
type: "finding"
phase: "verify"
timestamp: "2026-10-05T09:12:40Z"
priority: "normal"
status: "ok"
subject:
  repo: "acme/payments-api"
  commit: "c4f9e2d8b1a0f3e5d7c9b2a4f6e8d0c2b4a6f8e0"
findings:
  - id: "F-0007"
    category: "security"
    severity: "high"
    confidence: 0.95
    location: { file: "src/auth/session.py", lines: [118, 122] }
    evidence: "Query is now parameterized; injection no longer reachable."
    suggested_fix: null
    references: ["CWE-89"]
    status: "fixed"
  - id: "F-0008"
    category: "secrets"
    severity: "critical"
    confidence: 0.99
    location: { file: "src/auth/session.py", lines: [131, 131] }
    evidence: "Key removed; loaded from os.environ['SESSION_SIGNING_KEY']."
    suggested_fix: null
    references: ["CWE-798"]
    status: "fixed"
scores:
  scale: "0-10"
  categories:
    security: { score: 9.2, weight: 0.35, confidence: 0.95 }
  aggregate: 9.2
  threshold: 8.0
  satisfied: true
```

### 4.7 Terminate message (orchestrator → all)

```yaml
schema_version: "review.msg/v1"
message_id: "01J8Z6Q7R8S9T0U1V2W3X4Y5Z6"
correlation_id: null
thread_id: "rev-2026-10-05-pr1842"
from: "orchestrator"
to: "broadcast"
type: "control"
phase: "aggregate"
timestamp: "2026-10-05T09:13:00Z"
priority: "normal"
status: "ok"
scores:
  aggregate: 8.41
  threshold: 8.0
  satisfied: true
payload:
  termination: "satisfied"
  reason: "aggregate 8.41 >= 8.0 and no open high/critical findings after verification"
  iterations: 3
  final_scores:
    security: 9.2
    correctness: 8.3
    performance: 8.1
    style: 9.0
    tests: 7.4
  aggregate: 8.41
  threshold: 8.0
```

---

## Sources

1. Agent2Agent (A2A) Protocol — Official Specification v0.3.0. https://a2a-protocol.org/v0.3.0/specification/
2. Agent2Agent (A2A) Protocol Specification v0.2.4 (Task/Message/TaskState objects). https://a2a-protocol.org/v0.2.4/specification
3. A2A Agent Card Specification — field reference (capabilities, skills, securitySchemes). https://stacka2a.dev/learn/agent-card-spec
4. MCP server JSON-RPC 2.0 — protocol messages and lifecycle. https://alivemcp.com/seo/mcp-server-json-rpc
5. MCP JSON-RPC Wire Format: Messages Under the Hood (Ginger Labs). https://gingerlabs.ai/blog/json-rpc-mcp-messages
6. JSON-RPC 2.0 Specification. https://www.jsonrpc.org/specification
7. Agent Client Protocol (ACP) — Protocol Specification (Zed). https://deepwiki.com/zed-industries/agent-client-protocol/2-protocol-specification
8. Agent Client Protocol (ACP) — Editor to Agent Standard. https://infragap.com/agent-client-protocol
9. AGNTCY Agent Connect Protocol Specification. https://spec.acp.agntcy.org/
10. AGNTCY Open Agentic Schema Framework (OASF) attribute dictionary. https://github.com/agntcy/oasf/blob/main/schema/dictionary.json
11. Agent Protocol (runs, threads, store, streaming) — langchain-ai/agent-protocol. https://github.com/langchain-ai/agent-protocol
12. FIPA ACL Message Structure and Envelope (JADE/FIPA tutorial). https://jade.tilab.com/papers/JADETutorialIEEE/JADETutorial_FIPA.pdf
13. Heritage of FIPA-ACL and Speech Acts (performatives, ontology, interaction protocols). https://ai-engineering.academy/learn/16-multi-agent-and-swarms/02-fipa-acl-heritage
14. CloudEvents Specification v1.0.3 (required/optional attributes, extensions). https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md
15. CloudEvents JSON Event Format (attribute → JSON mapping). https://github.com/cloudevents/spec/blob/main/cloudevents/formats/json-format.md
16. AG-UI: Agent User Interaction Protocol (event families, state snapshot/delta). https://ai.zenheart.site/tech/07-interoperability/ag-ui.html
17. Pydantic v2 — JSON Schema generation (Draft 2020-12). https://pydantic.dev/docs/validation/2.12/concepts/json_schema/
18. YAML Schema Validation: JSON Schema vs CUE. https://theproductguy.in/blogs/yaml-schema-validation
19. CUE: typed configuration language with lattice unification. https://hivebook.wiki/wiki/cue-typed-configuration-language-with-lattice-unification
20. io.Intelligence Agent Protocol (thread/run/message REST + SSE contract). https://docs-ai.interop.io/api-reference/ai-server/agent-protocol
