# Hermes Agent — Native Extension Points for a Scored, Iterative Multi-Specialist Code-Review Loop

**Repo investigated:** a local `hermes-agent` checkout (git rev `93c9360a8`)
**Docs:** https://hermes-agent.nousresearch.com/docs (index: `/docs/llms.txt`; source markdown lives in `website/docs/`)
**Host:** Windows 11, bash/MSYS shell.

---

## 0. TL;DR — the recommended native architecture

There is **no single "register a review orchestrator" API** in Hermes. The scored, iterative, multi-specialist loop is assembled from four first-class primitives that already exist:

1. **Orchestrator session** running **`/goal`** with a **completion contract** whose `verification` field *is* the SCORE threshold, plus **deterministic quality gates** (`/goal gate add`) that mechanically check the score file.
2. **Specialist reviewers** spawned as **one `delegate_task` batch** (one task per specialist), each carrying the diff/artifact in `context` and a **JSON-Schema `output_schema`** that enforces a uniform findings record.
3. **Score aggregation + iteration**: the orchestrator computes a weighted SCORE, writes it to a workspace file, and `/goal`'s judge/gate decides continue vs done; the turn budget bounds the loop.
4. **Durable variant** when the loop must survive restarts / cross profiles: a **Kanban Swarm** (`hermes kanban swarm`) with one card per specialist, a verifier card gated on all of them, and `--goal` cards for iterate-until-done.

`/loop` is the right tool for *timer-driven polling* inside a session, **not** for the scored loop (which is judge/evidence-driven → `/goal`). Bot Mode gives persistent specialist personas; cron/kanban give durability.

> **Critical schema caveat:** `delegate_task`'s `output_schema` is validated as **JSON only** (`tools/delegation_output_schema.py:87` calls `json.loads`). A YAML findings document will **fail** validation. Design the canonical exchange record as **JSON Schema**, have children return JSON, and have the orchestrator serialize to YAML for the human-facing / cross-agent exchange file.

---

## 1. `/loop` — timer-driven in-session wakeups

### 1.1 Syntax and parsing

Source: `hermes_cli/loops.py`.

```
/loop [interval] <prompt> [--times N] [--until <condition>]
/loop every 5m <prompt>            # "every" sugar
/loop 10m /recap                   # loop a slash command
/loop keep fixing tests until green   # no interval → self-paced
/loop 5m watch the queue --until queue is empty
/loop status | pause | resume | stop | clear | cancel | help
```

- Alias `/proactive` (docs `website/docs/user-guide/features/loops.md:84`; reference `website/docs/reference/slash-commands.md:57`).
- Parser: `parse_loop_args()` (`hermes_cli/loops.py:84`); interval token parser `parse_interval_token()` (`:71`) accepts `30s` / `5m` / `2h` / `1h30m` (compound units). **A bare number is not an interval** (`:74`) — it collides with prompt text.
- Flags pulled before the front parse so an interval-looking token inside `--until` cannot confuse it (`:95-111`). `--times N` must be a positive int; `--until` consumes to end of line.
- Surface-agnostic dispatcher: `dispatch_loop_command(mgr, args, route=...)` (`:661`) returns `{"output", "created"}`.

### 1.2 Two cadence modes

- **Fixed interval** — interval supplied; `LoopState.mode="interval"`.
- **Self-paced** — interval omitted; `mode="self_paced"`, starts at the floor, doubles the delay while the agent's reply digest is unchanged, snaps back to the floor on any change. Change detection is `_digest_response()` (`:375`) — whitespace-normalized with clock/date/duration tokens stripped, SHA-256.

### 1.3 Configuration — all `loops.*` keys

Resolved by `_loops_config()` → `load_config().get("loops")` (`:140`); readers `min_interval_seconds()` `:158`, `max_ticks_default()` `:162`, `self_paced_floor_seconds()` `:166`, `self_paced_ceiling_seconds()` `:170`. Documented in `website/docs/user-guide/features/loops.md:104`.

```yaml
# ~/.hermes/config.yaml
loops:
  min_interval_seconds: 30        # floor for fixed intervals (clamped >= 5). default 30
  max_ticks: 100                  # backstop budget; 0 = unlimited. default 100
  self_paced_floor_seconds: 60    # self-paced start (floor 10). default 60
  self_paced_ceiling_seconds: 900 # self-paced max backoff. default 900
```

Defaults/constants: `DEFAULT_MIN_INTERVAL_SECONDS=30` (`:24`), `DEFAULT_MAX_TICKS=100` (`:26`), `DEFAULT_SELF_PACED_FLOOR_SECONDS=60` (`:29`), `DEFAULT_SELF_PACED_CEILING_SECONDS=900` (`:30`).

### 1.4 How a tick injects a prompt

- `LoopManager.fire_tick()` (`:505`) claims a due tick, increments `ticks_fired`, sets `awaiting_response=True`, and returns the message to inject.
  - If the loop's stored prompt starts with `/`, the **raw slash command** is injected verbatim (`:523`).
  - Otherwise the wakeup template wraps it: `WAKEUP_PROMPT_TEMPLATE` (`:44`) or `WAKEUP_PROMPT_WITH_UNTIL_TEMPLATE` (`:56`), which instructs the agent to re-check current state fresh and end with `LOOP_COMPLETE` when done.
- **Gateway driver:** `GatewayGoalsMixin._loop_wakeup_watcher()` (`gateway/run_goals.py:463`) — a gateway-wide 15 s ticker scans persisted `loop:*` rows (`list_active_loops()`), skips busy sessions and sessions with an active non-parked `/goal`, and injects each due wakeup as an **internal** synthetic `MessageEvent` via `adapter.handle_message(...)` (`:453`). Slash-command loops dispatch through the command path and are completed immediately (`:456`).
- **CLI/TUI** drive their own schedulers (loops set there carry no `route`, so the gateway watcher ignores them: `:393`).

### 1.5 `LOOP_COMPLETE` handling

- Marker constant `LOOP_COMPLETE_MARKER="LOOP_COMPLETE"` (`:33`); regex `_LOOP_COMPLETE_RE` (`:35`) matches the marker **on its own line**, tolerating surrounding whitespace and trailing `.`/`!`.
- `response_signals_complete()` (`:370`) is checked first in `complete_tick()` (`:563`).

### 1.6 The `--until` judge — which model, fail-open, configuration

- In `complete_tick()` (`:567-582`), if `until` is set and the response is non-empty, the loop calls **`hermes_cli.goals.judge_goal(s.until, last_response)`** — i.e. the **same auxiliary judge that powers `/goal`**, on the `goal_judge` auxiliary task.
- Verdicts: `done` → stop the loop (`_stop("done", …)`); `blocked` → **pause** (stop condition judged unachievable) (`:578`).
- **Fail-open:** any exception from `judge_goal` is caught and treated as `continue` (`:573-574`). A broken judge never wedges the loop.
- Configuration: `auxiliary.goal_judge.*` in `config.yaml` applies (provider, model, `max_tokens`, `timeout`, `extra_body`, `reasoning_effort`). See §2.3.

### 1.7 Stop precedence in `complete_tick()` (`:549`)

1. Agent self-stop marker (`LOOP_COMPLETE`).
2. `--until` judge (done → stop, blocked → pause).
3. `--times N` user cap → done.
4. `loops.max_ticks` backstop → **pause** (recoverable), not done (`:590`).
5. Else reschedule (self-paced backoff or fixed interval).

### 1.8 State, lifecycle, interactions

- Persisted per session in `SessionDB.state_meta` key `loop:<session_id>` (`_meta_key` `:239`).
- `migrate_loop_to_session()` (`:335`) carries a loop across context-compression session rotation (#33618).
- **One loop per session**; a new `/loop` replaces it (docs `loops.md:98`).
- `goal_blocks_loop_tick()` (`:613`): an active, non-parked `/goal` defers loop ticks (goal owns the idle boundary).
- Ctrl+C on a wakeup pauses the loop (docs `loops.md:99`).

---

## 2. `/goal` and `/subgoal` — the judge-driven Ralph loop

Source: `hermes_cli/goals.py`; command handler `hermes_cli/goal_command.py` (`dispatch_goal_command`); gateway glue `gateway/slash_commands_goals.py` and `gateway/run_goals.py`.

### 2.1 Commands

`/goal <text>` (set/kick), `/goal -- <text>` (literal control-word text), `/goal draft <text>`, `/goal show`, `/goal status`, `/goal pause`, `/goal resume`, `/goal clear`, `/goal wait <pid>`, `/goal unwait`, `/goal gate add|list|remove|clear`.
`/subgoal <text>` / `/subgoal` (list) / `/subgoal remove <N>` / `/subgoal clear`.
(`website/docs/user-guide/features/goals.md:56`; reference `slash-commands.md:54-55`.)

### 2.2 How goal completion is evaluated

`GoalManager.evaluate_after_turn()` (`hermes_cli/goals.py:1479`) runs after every turn:

1. If parked on a wait barrier → quiesce, no turn burned (`:1492`).
2. Increment `turns_used`.
3. **Gates run before the judge** (`_check_gates()` `:1301`): deterministic shell commands; a failing gate short-circuits judging and its bounded output tail becomes the continuation prompt.
4. Else call `judge_goal()`.
5. Apply verdict: `done` → mark done; `blocked` → pause with reason; `wait` → park; `continue` → schedule continuation. Budget/parse/transport failure backstops pause.

`judge_goal()` (`:893`) builds a strict prompt (`JUDGE_SYSTEM_PROMPT` `:113`; user templates `:186`/`:195`/`:214`) and calls the auxiliary model via `_call_goal_judge_llm()` (`:877`) → `call_llm(task="goal_judge", ...)`. It returns `(verdict, reason, parse_failed, wait_directive, transport_failed)`; verdict ∈ `done | blocked | continue | wait | skipped`.

### 2.3 Judge model + configuration

```yaml
# ~/.hermes/config.yaml
goals:
  max_turns: 20                      # continuation-turn budget; default 20 (DEFAULT_MAX_TURNS, goals.py:32)

auxiliary:
  goal_judge:
    provider: openrouter             # or nous, main, gemini, ... ; "auto" = best available
    model: google/gemini-3-flash-preview
    max_tokens: 4096                 # DEFAULT_JUDGE_MAX_TOKENS (goals.py:37); 200 truncated reasoning models
    timeout: 30                      # DEFAULT_JUDGE_TIMEOUT (goals.py:33)
    # extra_body / reasoning_effort accepted (routed through call_llm)
```

Readers: `_goal_judge_setting()` (`:752`), `_goal_judge_max_tokens()` (`:766`), `_goal_judge_timeout()` (`:770`). Config hint string `_JUDGE_CONFIG_HINT` (`:1082`).

**Fail-open:** every judge failure path returns `continue` (`:946-953`). The turn budget is the real backstop. Persistent failures auto-pause: `DEFAULT_MAX_CONSECUTIVE_PARSE_FAILURES=3` (`:43`), `DEFAULT_MAX_CONSECUTIVE_TRANSPORT_FAILURES=5` (`:46`).

### 2.4 Completion contracts (the key lever for scoring)

Five optional fields (`_CONTRACT_FIELDS` `:265`): `outcome`, `verification`, `constraints`, `boundaries`, `stop_when`. `GoalContract` dataclass `:286`; `parse_contract()` `:312` (inline `field: value` lines); `draft_contract()` `:1043` (aux model expands a one-liner). When a contract is set, the **judge requires concrete evidence of the `verification` criterion** and refuses on a violated constraint (`JUDGE_USER_PROMPT_WITH_CONTRACT_TEMPLATE` `:214`).

### 2.5 `/subgoal`

`add_subgoal()` (`:1220`); the continuation prompt and the judge prompt both include the numbered criteria, and the goal is not DONE until the objective **and every subgoal** are met (`JUDGE_USER_PROMPT_WITH_SUBGOALS_TEMPLATE` `:195`).

### 2.6 Quality gates

`GoalGate` dataclass (`:343`); `add_gate()` (`:1262`); `_check_gates()` (`:1301`); `run_gate()` (`:396`). Defaults `DEFAULT_GATE_TIMEOUT_SECONDS=300`, `DEFAULT_GATE_MAX_RETRIES=3` (`:51-52`). Gates persist with the goal in `state_meta`, run in the session workspace (`_gate_workspace()` `:374`), and every boundary re-executes a failed gate. Exhausted retries → auto-pause.

### 2.7 Wait barriers

`wait_on(pid)` `:1367`, `wait_on_session(id)` `:1378`, `wait_for_seconds(n)` `:1387`; `is_waiting()` `:1408` auto-clears. Judge `wait` verdicts park without burning a turn; pid/session barriers cap at 30 min (`_MAX_BARRIER_WAIT_S` `:55`).

### 2.8 How `/goal` differs from `/loop`

| | `/goal` | `/loop` |
|---|---|---|
| Trigger | Judge verdict after each turn | Timer / self-paced |
| Question answered | "Is this objective achieved?" | "Re-run this prompt on a cadence" |
| Stop | Judge done / budget / gates | `LOOP_COMPLETE` / `--until` judge / `--times` / `max_ticks` / user |
| Shared | Same `goal_judge` aux task, same `state_meta` store; an active goal **defers** loop ticks (`goal_blocks_loop_tick`) | |

Both feed a plain **user-role** continuation/wakeup message — no system-prompt mutation, so prompt caching is preserved (`goals.py:5-6`; `loops.md:96`).

---

## 3. Bot Mode — profiles as bots, messaging, groups

Docs: `website/docs/user-guide/bot-mode.md`. Source: `tools/bot_mode_dm.py`, `gateway/bot_loop_guard.py`, `cron/bot_chat_delivery.py`.

### 3.1 A Bot *is* a profile

A Bot is a Hermes profile under `~/.hermes/profiles/<name>/` (own `config.yaml`, `.env`, `SOUL.md`, skills, memory, sessions, cron). CLI parity: `hermes -p <bot> chat` opens the same agent. Bot Mode is a desktop UI over that primitive (no new storage/daemon). Bot routines are cron jobs namespaced `[bot:<name>] <routine>`.

### 3.2 Bot-to-bot messaging — the `message_agent` tool

Source `tools/bot_mode_dm.py` (`message_agent_tool_schema` `:67`; `message_agent_tool` `:201`; `message_agent_authorized` `:123`; `ensure_message_agent_tool` `:140`).

- A Bot messages a teammate by calling `message_agent(target="researcher", message="…")`.
- Target resolves against the live roster: profile name (matched first), friendly name / Bot Mode title, or `@`-handle. `@hermes` always means the primary Bot. Ambiguous friendly names are refused.
- The sender's attribution `Message from 🤖 <friendly> (@<handle>):` is prefixed automatically.
- **Delivery is fire-and-forget**: the tool returns `status: queued` + a `delivery_id` (+ `process_id`), and the teammate's reply arrives later as a background completion notification. On surfaces that cannot receive completions (api_server, one-shot) the ack carries `reply_delivery: poll` and the sender retrieves via `process(action="wait", session_id=…)`.
- **Typed failure reasons** end-to-end: `provider_auth_or_access`, `provider_quota_limit`, `provider_rate_limit`, `provider_server_error`, `context_overflow`, `missing_config`, `model_unavailable`, `runtime_offline`, `queued_expired`, `delivery_timeout`, `target_busy`, `unknown`.
- **Structured messages:** the tool signature takes a **plain `message` string** — there is no schema/typed-payload field. Structured content must be embedded in the string (e.g. a fenced YAML/JSON block) and parsed by the receiver. There is no native typed bot-to-bot envelope.

### 3.3 What makes a session a "Bot Chat" (enablement gate)

Three conditions must hold before the protocol section and `message_agent` are injected (docs `bot-mode.md:199`):

1. `agent.bot_mode_protocol: true` (master switch, default on) — `agent:` in config.yaml.
2. The session is titled **exactly `Bot Chat`**.
3. At least one profile on the install carries `ui_meta: {hermes-bots: {}}` in its `profile.yaml`.

On a headless install (gateway + Telegram, no desktop) nothing writes markers 2–3, so `message_agent` is unreachable. Manual enablement:

```bash
hermes -p <bot> chat -c "Bot Chat" --create-if-missing
```
```yaml
# ~/.hermes/profiles/<any-bot>/profile.yaml
ui_meta:
  hermes-bots: {}
```

### 3.4 Group chats

- Rooms of **2–6 Bots**; one visible transcript; `@name` mentions; up to **3 serial rounds** per user message (hard caps: 10 messages/send, 3 rounds).
- `@all` / `@everyone` broadcast; `@user` escalation (needs-you badge); `@hermes` = primary Bot.
- Durable room log; when all members live on one gateway the gateway owns turn scheduling through a durable driver (`groups.capabilities` reports `driver: true`).
- Plugins observe member work via the `on_room_member_activity` hook (docs `bot-mode.md:176`, `features/hooks.md`).
- Room authority takeover via JSON-RPC `groups.promote` / `groups.demote` (operator recovery, not atomic).

### 3.5 Cross-machine

- Desktop relay (Settings → Connections) couriers messages between connected gateways while a Desktop is running.
- Headless machine-to-machine: register a **peer** (`hermes peer add <name> --url … --key <API_SERVER_KEY>`; `hermes peer dm`, `hermes peer run`, `hermes peer status/stop`). `message_agent` then accepts peer targets (`target="spark/researcher"`). Peer names/URLs live under `bot_peers`; key in `~/.hermes/.env` as `HERMES_PEER_<NAME>_KEY`.

---

## 4. `delegate_task` — the full contract

Source: `tools/delegate_tool.py` (+ siblings `delegate_tool_config.py`, `delegate_tool_child_run.py`, `delegate_tool_tasks.py`, `delegate_tool_results.py`, `delegation_output_schema.py`). Docs: `website/docs/user-guide/features/delegation.md`.

### 4.1 Input contract

Tool schema `DELEGATE_TASK_SCHEMA` (`tools/delegate_tool.py:682`); handler `delegate_task()` (`:474`).

Per-task (`tasks[]` item, `required: ["goal"]`):
- `goal` (string) — self-contained objective.
- `context` (string) — everything the child needs (it knows nothing of the parent's conversation).
- `output_schema` (object) — optional JSON Schema; appended to the child's context as an OUTPUT CONTRACT and validated by the parent.
- `images` (array, max 8) — local paths or http(s)/data URLs; native multimodal for vision children, path hints otherwise (`_MAX_TASK_IMAGES` in `delegate_tool_tasks.py`).
- `group` (string) — result-delivery bucket, only advertised when `delegation.independent_completions: true`.

Top-level: `tasks` (or legacy `goal`/`context`/`output_schema`), `action` (`spawn|list|steer|stop`), `subagent_id`, `message`.
Internal-only kwargs: `max_iterations` (**ignored** — `delegation.max_iterations` from config is authoritative, `:517-523`), `role` (**legacy, ignored** — capability is depth-derived, `:220-225`), `background` (deprecated; top-level model-facing calls always run in the background, `_model_background_value` `:768`), `credentials_cfg` (per-call routing owner, used by `/review` → `auxiliary.review`).

### 4.2 Output contract

Per-task result entry built by `_build_result_entry()` (`tools/delegate_tool_child_run.py:552`):
`task_index`, `status` (`completed|interrupted|failed`), `summary`, `api_calls`, `duration_seconds`, `model`, `exit_reason` (`completed|max_iterations|interrupted|error`), `truncated` (= `exit_reason == "max_iterations"`), `tokens{input,output}`, `tool_trace`, `cost_usd`, `cost_status`, plus conditionally `error`, `failure_reason`, `worktree`, `missed_steer`, `unread_completions`, `orphaned_processes`.

### 4.3 `output_schema` / `schema_valid` / `schema_errors`

`_validate_child_output_schema()` (`delegate_tool_child_run.py:478`) → `validate_output()` (`delegation_output_schema.py:87`):
- Validates the child's final answer with **`jsonschema`** against the supplied schema.
- **Exactly one bounded retry** turn carrying the validation errors verbatim; the schema is never re-pasted (`:492-518`; `build_retry_message()` `:109`).
- Result entry gains `schema_valid` (bool), and on failure `schema_errors` (list) + `schema_retries` + a `schema_note` (`:628-640`). **A contract miss does NOT fail the run** — the child's raw text is still `summary`, marked unvalidated. Prose/code fences around otherwise-valid JSON are tolerated (`extract_json_candidate()` `:60`).
- **YAML is not accepted** by the validator (`json.loads` at `:94`). Use JSON Schema + JSON payloads.

### 4.4 Concurrency and depth

- `delegation.max_concurrent_children` — `_get_max_concurrent_children()` (`tools/delegate_tool_config.py:93`): default **10**, floor 1, **no ceiling**; env `DELEGATION_MAX_CONCURRENT_CHILDREN`. Batches over the limit return a tool error (not truncated). Background delegations share the same cap (`_get_max_async_children` `:121`).
- `delegation.max_spawn_depth` — `_get_max_spawn_depth()` (`:151`): default **1** (flat), floor 1, no ceiling. `delegation.orchestrator_enabled` (default true) is the kill switch (`:165`).
- **Roles are depth-derived, not model-chosen**: a child is `orchestrator` iff `orchestrator_enabled` and `child_depth < max_spawn_depth` (`delegate_tool.py:220-225`); the `role` arg is legacy. Depth limit check at `:506-513`.
- `delegation.oneshot_max_children` (default 2) caps total children in one-shot/`-q` sessions (`delegate_tool_config.py:85`).
- Other keys: `max_iterations` (250), `model`/`provider`/`base_url`/`api_key`/`api_mode`, `request_overrides`, `fallback_providers`, `subagent_auto_approve`, `worktree_isolation`, `independent_completions`, `inherit_mcp_toolsets`, `child_timeout_seconds`, `compression_threshold_tokens`, `surface_child_process_notifications`.

### 4.5 Background delivery semantics

- Top-level model-facing delegations **always run in the background**; the tool returns a dispatch handle (`live_transcripts`, `subagent_ids`, `delegation_id`) immediately and the consolidated result re-enters the conversation as a new message **between turns**. Orchestrator subagents (depth>0) wait in-turn to synthesize.
- `delegation.independent_completions: true` → per-task/per-`group` completion messages; the dispatch handle lists `units[]` (`delegation_id`, `group`, `task_indexes`).
- Durable completion event stored in the active profile's `state.db` before publish; a crash before delivery restores the pending event (at-least-once delivery). Bounded, profile-local.
- **`/stop` / session close / reset ends background children** (and synchronous descendants), each returning `status="interrupted"` with partial output.

### 4.6 The "not durable" caveat (explicit)

Docs `delegation.md:556` ("Background completion durability is not durable execution") and `:565`:
- A process restart does **not** resume a running child; its attempt is recorded `unknown` (side effects unprovable).
- Background children are killed by `/stop`, session close/reset, or process exit (whole tree).
- Leaf children cannot call `delegate_task`, `clarify`, `memory`, `send_message`, `cronjob`; orchestrator children retain `delegate_task` only.
- For durable execution use **`cronjob`** or **`terminal(background=True, notify_on_complete=True)`** (docs `:565-568`).

### 4.7 `/review` (single-reviewer primitive)

`agent/review_engine.py` — `start_review()` (`:158`) snapshots the last 10 user/assistant messages (`DEFAULT_CONTEXT_MESSAGES=10`), builds a reviewer briefing (`build_review_task()` `:99`), and dispatches via `delegate_task(goal, context, background=True, credentials_cfg=…)`. Model routing `auxiliary.review` (`_load_review_credentials_cfg()` `:139`). This is the *single*-reviewer path; for multi-specialist use the `tasks=[...]` batch directly.

---

## 5. Custom extension points

### 5.1 Custom slash commands

- **Built-in registry:** `hermes_cli/commands.py` — `CommandDef` (`:45`), `COMMAND_REGISTRY` (`:83`), derived autocomplete/help/alias tables (`:386-477`). Add a built-in command here.
- **Plugin-registered in-session command:** `ctx.register_command(name, handler, description="", args_hint="")` (`hermes_cli/plugins.py:678`). Handler receives the raw args string; may be sync or async. Works in CLI **and** gateway. **Built-ins always win** — a plugin cannot shadow `help`, `model`, `new`, etc. (registration silently rejected with a warning).
- **Plugin CLI subcommand:** `ctx.register_cli_command(name, help, setup_fn, handler_fn)` (`plugins.py:664`).
- **Quick commands (config, no code):** `quick_commands.<name>` with `type: exec` (shell) or `type: alias` (targets another slash command) — docs `slash-commands.md:163`.
- **Skills as dynamic slash commands:** any installed skill is exposed as `/<skill-name>`; `/skill <name>` is the fallback when the name is taken by a built-in (`slash-commands.md:14`).

### 5.2 Custom tools

- Plugin tool: `ctx.register_tool(name, toolset, schema, handler, check_fn=…, override=False)` (`hermes_cli/plugins.py:457`). Handler signature `def h(args: dict, **kwargs) -> str` returning a JSON string, never raising. `check_fn` hides the tool when it returns false. `override=True` replaces a built-in but requires operator consent (`plugins.entries.<id>.allow_tool_override: true` or the `tools.override` capability).
- Core tool registration: `registry.register(...)` in `tools/registry.py:666`; see docs `website/docs/developer-guide/adding-tools.md`.
- `ctx.dispatch_tool(name, args, *, parent_agent=None)` (`plugins.py:705`) — invoke any registered tool (including `delegate_task`, `kanban_*`, `terminal`) with the parent-agent context wired.

### 5.3 Plugins

Docs: `website/docs/developer-guide/plugins/index.md` (Build a Plugin). Shape: `~/.hermes/plugins/<name>/` with `plugin.yaml` + `__init__.py` defining `register(ctx)`. Commands: `hermes plugins install|enable|list|doctor|validate|capabilities`. Manifest v2 adds `manifest_version`, `api_version`, `requires_plugins`, `python_dependencies`, `config_schema`, `capabilities`, `provides_locales`.
- **Hooks:** `ctx.register_hook(name, cb)` (`plugins.py:976`) — `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`, `pre/post_api_request`, `pre/post_auxiliary_call`, `on_session_start/end/finalize/reset`, `gateway_platform_event`, `kanban_task_claimed/completed/blocked`. `pre_llm_call` can inject context; `pre_tool_call` can block/approve.
- **Middleware:** `ctx.register_middleware(kind, cb)` (`plugins.py:980`) — `tool_request`, `llm_request`, `tool_execution`, `llm_execution` (`hermes_cli/middleware.py:VALID_MIDDLEWARE`).
- **Plugin skills:** `ctx.register_skill(name, path)` (`plugins.py:1057`) — read-only, namespaced `plugin:skill`.
- `ctx.profile_name` and `ctx.dispatch_tool` are the session-agnostic APIs (work in gateway/cron/kanban worker; `ctx._cli_ref` is None there).
- **No core-override:** monkey-patching `AIAgent`/modules is refused at admission (`hermes plugins validate`, "no core override").

### 5.4 MCP servers

Config `mcp_servers.<name>` (docs `website/docs/reference/mcp-config-reference.md`): stdio (`command`/`args`/`env`) or HTTP (`url`/`headers`/`auth: oauth`/`client_cert`); per-server `enabled`, `timeout`, `trust` (`full|untrusted`), `tools.include`/`exclude`/`resources`/`prompts`, `lazy`. Tools register as `mcp__<server>__<tool>`. Reload with `/reload-mcp`. Guide: `website/docs/user-guide/features/mcp.md`, `guides/use-mcp-with-hermes.md`.

### 5.5 Can a custom "review orchestrator" be registered?

**Yes — via composition, not a dedicated API.** The viable seams, in order of fidelity to a "native orchestrator":
1. **A profile** (`hermes profile create reviewer-orchestrator --description "…"`) whose `SOUL.md`/config encode the orchestrator persona and whose enabled toolsets include `delegation` (+ `kanban`, `memory`). This is the closest thing to "an orchestrator agent".
2. **A skill** (`SKILL.md`) that encodes the multi-specialist review procedure + rubrics; loadable by any agent, attachable to cron jobs (`--skill`) and kanban cards (`--skill`).
3. **A plugin** registering a `/review-orchestrator` slash command + tools + hooks/middleware, driving `ctx.dispatch_tool("delegate_task", …)`.
4. **An MCP server** exposing a `review_orchestrate` tool.
5. **A kanban orchestrator profile** (recommended for durability) — see §7.

### 5.6 Skills (`SKILL.md`) and profiles as specialist personas

- Skills: `SKILL.md` with YAML frontmatter (`name`, `description` whose first 57 chars are a self-contained trigger) + markdown body. Docs `website/docs/developer-guide/creating-skills.md`, `user-guide/features/skills.md`. Skills are the natural home for a specialist's **rubric** and review conventions; `agent/review_engine.py` even tells reviewers to load the parent's skills and treat their standards as binding (`review_engine.py:118-127`).
- Profiles encode personas: `~/.hermes/profiles/<name>/{config.yaml, .env, SOUL.md, skills/, memories/, state.db}`. `SOUL.md` = personality/instructions. `hermes profile create <name> --description "<role>"`, `hermes profile describe <name> --text|--auto` (used by the kanban decomposer to route). Per-profile model pin. `hermes -p <name> chat`.

---

## 6. Cron and Kanban — when durable multi-worker orchestration is needed

### 6.1 Cron

Source: `cron/jobs.py`, `cron/scheduler.py`, `tools/cronjob_tools.py`. Docs: `website/docs/user-guide/features/cron.md`, `developer-guide/cron-internals.md`.
- Agent-facing tool: `cronjob_manage` (actions `create|list|update|pause|resume|run|remove`; `tools/cronjob_tools.py:642`).
- Runs in **fresh isolated agent sessions**, outside any chat; survives restarts; jobs in `~/.hermes/cron/jobs.json`; outputs in `cron/output/<job_id>/`.
- Attach skills (`--skill`, repeatable) and `enabled_toolsets`; `workdir`; delivery targets (`origin|local|<platform>|bot-chat[:profile]|all`); `context_from=[job_ids]` chaining; `continuity=true`; `no_agent` script mode; webhook event triggers.
- Relevant config `cron.*`: `model`, `model_provider`, `preflight`, `max_parallel_jobs`, `allow_agent_scheduling` (default **false** — cron runs cannot recursively schedule), `catch_up_missed`, `failure_nudge_threshold`, `wrap_response`, `mirror_delivery`, timeouts.
- **No built-in goal-mode** in cron — for iterate-until-done, use `/goal` (session) or kanban `--goal` cards.

### 6.2 Kanban

Source: `hermes_cli/kanban*.py`, `tools/kanban_tools.py`, `gateway/kanban_watchers*.py`. Docs: `website/docs/user-guide/features/kanban.md`.
- Durable SQLite board `~/.hermes/kanban.db` (per-board `~/.hermes/kanban/boards/<slug>/kanban.db`); tasks are rows; profiles are named workers; every handoff is a row.
- Dispatcher runs **inside the gateway** (`kanban.dispatch_in_gateway: true`, tick 60 s) and spawns the assigned profile as an OS-process worker with the `kanban_*` toolset.
- Worker tools: `kanban_show`, `kanban_list`, `kanban_complete`, `kanban_request_review`, `kanban_request_changes`, `kanban_block`, `kanban_heartbeat`, `kanban_comment`, `kanban_create`, `kanban_link`, `kanban_unblock`, attachments.
- **Goal-mode cards:** `hermes kanban create "…" --goal --goal-max-turns N` runs the same Ralph engine as `/goal` *inside the worker session* (`hermes_cli/goals.py:1625 run_kanban_goal_loop`); judge unreachable → handoff allowed (fail-open).
- **Swarm helper:** `hermes kanban swarm "<root>" --workers a,b,c --verifier v --synthesizer s` builds a durable root + N parallel workers + verifier (gated on all workers) + synthesizer (gated on verifier) atomically (`hermes_cli/kanban_swarm.py`).
- Config `kanban.*`: `dispatch_in_gateway`, `dispatch_interval_seconds`, `review_dispatch`, `max_in_progress`, `max_in_progress_per_profile`, `auto_decompose`, `orchestrator_profile`, `default_assignee`, `auto_subscribe_on_create`, `failure_limit`, `max_retries`, `dispatch_stale_timeout_seconds`, `dispatch_profiles`.

### 6.3 When to pick which

| Need | Primitive |
|---|---|
| Iterate one task in this chat until done | `/goal` |
| Poll on a cadence in this chat | `/loop` |
| Short reasoning fan-out, result returns to parent | `delegate_task` |
| Survive restarts / cross profile / human-in-the-loop / audit | Kanban |
| Unattended schedule | cron |

---

## 7. Recommended native architecture for the scored iterative multi-specialist review loop

### 7.1 Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR SESSION  (/goal with completion contract + quality gate)      │
│  goal text: "Run specialist reviews until the aggregate SCORE >= 0.90"     │
│  contract:  verification = "scripts/score_reviews.py exits 0 against        │
│             reviews/latest.json (SCORE>=0.90, no CRITICAL open)"           │
│  gate:      /goal gate add scripts/score_reviews.py                        │
│  budget:    goals.max_turns (default 20)                                    │
└───────────────▲───────────────────────────────────────────┬────────────────┘
                │ continuation (judge says continue)          │ delegate_task(tasks=[...])
                │                                             ▼
        ┌───────┴───────────┐                     ┌────────────────────────────────┐
        │ /goal JUDGE        │                     │ SPECIALIST BATCH (parallel)     │
        │ (auxiliary.goal_    │                     │  security · performance ·       │
        │  judge model)      │                     │  readability · correctness ·    │
        └────────────────────┘                     │  architecture  (each one child) │
                ▲                                   │  each with output_schema =      │
                │                                   │  uniform findings JSON Schema   │
        ┌───────┴───────────┐                       └───────────────┬────────────────┘
        │ QUALITY GATE       │                                       │ consolidated result
        │ scripts/score_     │◀──── reviews/latest.json ◀────────────┘  (schema_valid findings)
        │ reviews.py         │
        └────────────────────┘
```

### 7.2 Layer A — Orchestrator = `/goal` + contract + gate

- Set the standing objective with an explicit contract so the judge requires **evidence**, not vibes:
  ```
  /goal Drive specialist code review of the current diff to SCORE >= 0.90
  verify: scripts/score_reviews.py exits 0 reading reviews/latest.json (SCORE >= 0.90 and no open CRITICAL finding)
  constraints: do not modify source under review; only add reviews/*.yaml
  boundaries: only the files in the diff and reviews/
  stop when: a specialist reports a blocker that needs human input
  ```
  Inline `field: value` lines are parsed by `parse_contract()` (`goals.py:312`); or use `/goal draft <text>` to have the aux model draft it (`draft_contract()` `:1043`).
- Add the deterministic gate: `/goal gate add scripts/score_reviews.py`. Gates run **before** the judge each turn (`goals.py:1500`), so a red score is deterministic evidence the loop is not done and its output drives the next iteration.
- Tune the judge: `auxiliary.goal_judge.{provider,model,max_tokens,timeout}` (§2.3); `goals.max_turns` bounds iterations.
- Why `/goal` and not `/loop`: the loop's satisfaction is evidence/judge-driven, which is exactly `/goal`'s model. `/loop` is for timer polling (e.g. a `/loop 5m /recap` heartbeat while the goal runs — they coexist: an active goal defers loop ticks, `loops.py:613`).

### 7.3 Layer B — Specialists = one `delegate_task` batch with `output_schema`

- One task per specialist; each carries the diff/artifact in `context` and its **rubric** (ideally a skill the specialist is told to load). Uniform contract:
  ```json
  {
    "name": "review_findings",
    "schema": {
      "type": "object",
      "required": ["specialist", "target", "score", "verdict", "findings"],
      "properties": {
        "specialist": {"type": "string"},
        "target": {"type": "object", "properties": {"repo": {"type": "string"}, "ref": {"type": "string"}, "sha": {"type": "string"}}, "required": ["repo", "ref"]},
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "verdict": {"type": "string", "enum": ["pass", "pass_with_notes", "changes_required", "blocked"]},
        "findings": {"type": "array", "items": {
          "type": "object",
          "required": ["id", "severity", "category", "title", "evidence"],
          "properties": {
            "id": {"type": "string"},
            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
            "category": {"type": "string"},
            "file": {"type": "string"}, "line": {"type": "integer"},
            "title": {"type": "string"}, "evidence": {"type": "string"},
            "recommendation": {"type": "string"}, "confidence": {"type": "number"}
          }
        }},
        "summary": {"type": "string"}
      }
    }
  }
  ```
- **Keep it forgiving** (require only fields you read — docs `delegation.md:78`). The parent validates with `jsonschema`, gets `schema_valid`/`schema_errors`, and one bounded correction retry happens automatically. A miss never discards the child's work.
- **YAML caveat:** the validator is JSON-only. If the team insists on YAML on the wire, either (a) have the child emit JSON and let the orchestrator write `reviews/<specialist>.yaml` via `execute_code`/`write_file`, or (b) drop `output_schema` for the child and parse YAML from `summary` yourself (losing automatic validation). Recommended: **(a)**.
- Concurrency: `delegation.max_concurrent_children` (default 10) — enough for 5–7 specialists; batches over the limit error. `delegation.max_spawn_depth` stays 1 unless specialists must themselves fan out.
- Model cost split: pin `delegation.model` to a cheaper reviewer model while the orchestrator stays on a frontier model (docs `delegation.md:277`). For a stronger reviewer, pin `auxiliary.review` instead (used by `/review`).

### 7.4 Layer C — Scoring and iteration

1. Orchestrator collects the batch result (one consolidated message, or per-task with `delegation.independent_completions: true`).
2. It normalizes each specialist's `schema_valid` payload, computes a weighted aggregate **SCORE** (e.g. severity-weighted: `100 - Σ weight(severity)`), and writes `reviews/latest.json` (+ `reviews/<specialist>.yaml`).
3. `scripts/score_reviews.py` exits 0 iff SCORE ≥ threshold and no open CRITICAL. This is the **quality gate** the `/goal` loop runs before the judge.
4. If the gate fails, its bounded output tail becomes the continuation prompt (`goals.py:1342`), so the orchestrator iterates against the actual failing specialists — dispatch a new round (specialists re-review after fixes, receiving prior findings as `context`).
5. Loop terminates on: gate passes + judge `done`; `goals.max_turns`; a specialist `blocked` → orchestrator pauses for human input; or the user preempts.
6. **Grounding:** instruct each specialist (via its rubric/`context`) to cite file/line and to return `evidence` — the judge is deliberately conservative and requires concrete evidence for `verification` (`goals.py:214`).

### 7.5 Layer D — Durable variant (survive restarts / cross profile / human-in-the-loop)

Replace Layers A–C's in-session loop with a **Kanban Swarm**:
- `hermes kanban swarm "Review the diff to SCORE>=0.90" --workers security,performance,readability,correctness,architecture --verifier score-verifier --synthesizer orchestrator`
- The root/blackboard card holds shared context as structured JSON comments; worker cards run one specialist each (attach each specialist's rubric with `--skill`); the verifier card is gated on all workers; the synthesizer runs after.
- Use `--goal --goal-max-turns N` on the verifier/synthesizer cards for iterate-until-done (the same Ralph engine, `run_kanban_goal_loop`).
- Per-card model override (`--model/--provider` or `hermes kanban set-model`) for cost split; `kanban.max_in_progress_per_profile` for pacing.
- Every handoff is a durable row; workers write structured handoff via `kanban_complete(summary=…, metadata={changed_files, verification, residual_risk, …})` (recommended shape, docs `kanban.md:534`).
- Observe transitions centrally via the `kanban_task_claimed/completed/blocked` plugin hooks.

### 7.6 Precise integration points to hook into

| Concern | File / function / config key |
|---|---|
| Orchestrator loop engine | `hermes_cli/goals.py::GoalManager.evaluate_after_turn` (`:1479`); `judge_goal` (`:893`) |
| Completion contract / scoring definition | `hermes_cli/goals.py::GoalContract` (`:286`), `parse_contract` (`:312`), `draft_contract` (`:1043`) |
| Deterministic score gate | `hermes_cli/goals.py::GoalGate` (`:343`), `run_gate` (`:396`); config via `/goal gate add` |
| Judge model routing | `auxiliary.goal_judge.{provider,model,max_tokens,timeout}`; `_goal_judge_setting` (`:752`) |
| Iteration budget | `goals.max_turns` (`:32`) |
| Specialist spawn + schema | `tools/delegate_tool.py::delegate_task` (`:474`), `DELEGATE_TASK_SCHEMA` (`:682`); `tools/delegation_output_schema.py::validate_output` (`:87`) |
| Result parsing | `tools/delegate_tool_child_run.py::_build_result_entry` (`:552`) → `schema_valid`/`schema_errors` |
| Concurrency / depth | `delegation.max_concurrent_children`, `delegation.max_spawn_depth`, `delegation.orchestrator_enabled`, `delegation.independent_completions` (`tools/delegate_tool_config.py:93,151,165,110`) |
| Specialist model routing | `delegation.model`/`provider`; `auxiliary.review` (per-reviewer pin, `agent/review_engine.py:139`) |
| Timer heartbeat alongside | `hermes_cli/loops.py::LoopManager` (`:386`); config `loops.*` |
| Slash command (custom) | `hermes_cli/commands.py::COMMAND_REGISTRY` (`:83`); plugin `ctx.register_command` (`hermes_cli/plugins.py:678`) |
| Custom tool | `ctx.register_tool` (`hermes_cli/plugins.py:457`); core `tools/registry.py::registry.register` (`:666`) |
| Hooks / middleware | `ctx.register_hook` (`plugins.py:976`), `ctx.register_middleware` (`plugins.py:980`), `hermes_cli/middleware.py` |
| Specialist personas | profiles `~/.hermes/profiles/<n>/SOUL.md` + `--description`; skills `SKILL.md` |
| Durable orchestration | `hermes_cli/kanban_swarm.py`; `hermes_cli/goals.py::run_kanban_goal_loop` (`:1625`); `kanban.*` config |
| Durable schedule | `tools/cronjob_tools.py`; `cron.*` config |
| Bot-to-bot specialists | `tools/bot_mode_dm.py::message_agent_tool` (`:201`); `agent.bot_mode_protocol` |

---

## 8. Hard limits and caveats (read before designing)

1. **`/loop` and `/goal` are session-bound.** State lives in `SessionDB.state_meta` keyed `loop:<session_id>` / `goal:<session_id>`. One loop and one goal per session. They survive `/resume` and context compression (migration helpers) and the gateway watcher re-fires persisted loops after a restart, but they belong to a chat session — not a fleet. Use cron/kanban for durable multi-worker work.
2. **Delegate children are non-durable.** Process restart → attempt recorded `unknown`, no resume; `/stop`, session close/reset, or process exit kills the whole tree; child background processes are killed at child finish (unless `process_manage(action="handoff")`, ≤3/child). Background *completion delivery* is at-least-once, but that is **not** durable execution (docs `delegation.md:556`).
3. **`output_schema` validates JSON only.** `json.loads` at `delegation_output_schema.py:94`; YAML fails. Design the uniform findings record as JSON Schema + JSON payloads; serialize to YAML yourself.
4. **Leaf children cannot delegate** (and cannot `clarify`, `memory`, `send_message`, `cronjob`). Nested orchestration needs `max_spawn_depth >= 2` + `orchestrator_enabled`.
5. **`delegation.max_concurrent_children` default 10, no ceiling** — cost multiplies linearly; batches over the limit are refused, not truncated.
6. **Judge is fail-open** (`continue` on any error). Under-iteration is possible; the turn budget / gates are the real backstop. Persistent judge failure auto-pauses after 3 parse failures or 5 transport failures.
7. **`/loop --until` runs the judge once per tick and is fail-open** — a broken judge keeps the loop running until `max_ticks` (which pauses, not stops).
8. **Bot-to-bot messaging is string-based and fire-and-forget.** `message_agent` has no typed payload field; `status: queued` means durably admitted, not delivered. Requires a `Bot Chat`-titled session + `agent.bot_mode_protocol` + a `ui_meta: {hermes-bots: {}}` profile marker; headless installs must set these by hand.
9. **Cron cannot recursively schedule by default** (`cron.allow_agent_scheduling: false`); cron sessions are isolated and cannot create more cron jobs.
10. **Kanban is single-host by design**; the dashboard plugin REST surface is unauthenticated by default (localhost only). Cross-machine needs `hermes peer` / api_server.
11. **Plugin slash commands cannot shadow built-ins**, and `ctx._cli_ref` is `None` in gateway / cron / kanban-worker sessions — use `ctx.profile_name` + `ctx.dispatch_tool`.
12. **Plugins must be enabled** and use the documented directory layout; monkey-patching core internals is refused (no core override).

---

## 9. Source & documentation index

### Source files (in that checkout)
- `hermes_cli/loops.py` — `/loop` engine, config keys, tick injection, `--until` judge hook.
- `hermes_cli/goals.py` — `/goal` engine, judge, contracts, gates, wait barriers, kanban goal loop.
- `hermes_cli/goal_command.py` — `/goal` dispatch (set/draft/show/pause/resume/clear/wait/gate).
- `gateway/slash_commands_goals.py` — `/goal`, `/subgoal`, `/loop`, `/review`, `/heartbeat` gateway handlers.
- `gateway/run_goals.py` — post-turn goal/loop hooks, `_loop_wakeup_watcher`.
- `tools/delegate_tool.py`, `tools/delegate_tool_config.py`, `tools/delegate_tool_child_run.py`, `tools/delegate_tool_tasks.py`, `tools/delegation_output_schema.py` — delegation contract.
- `agent/review_engine.py` — `/review` single-reviewer dispatch.
- `tools/bot_mode_dm.py` — `message_agent`.
- `hermes_cli/plugins.py` — `PluginContext` (`register_tool` :457, `register_command` :678, `dispatch_tool` :705, `register_hook` :976, `register_middleware` :980, `register_skill` :1057).
- `hermes_cli/commands.py` — `COMMAND_REGISTRY`.
- `hermes_cli/middleware.py` — `VALID_MIDDLEWARE`.
- `tools/registry.py` — core tool registry.
- `tools/cronjob_tools.py`, `cron/jobs.py`, `cron/scheduler.py` — cron.
- `hermes_cli/kanban*.py`, `tools/kanban_tools.py`, `gateway/kanban_watchers*.py` — kanban.

### Doc URLs (source markdown under `website/docs/`)
- Loops: https://hermes-agent.nousresearch.com/docs/user-guide/features/loops
- Goals: https://hermes-agent.nousresearch.com/docs/user-guide/features/goals
- Delegation: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- Delegation patterns guide: https://hermes-agent.nousresearch.com/docs/guides/delegation-patterns
- Bot Mode: https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode
- Profiles: https://hermes-agent.nousresearch.com/docs/user-guide/profiles
- Cron: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron
- Kanban: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- Kanban tutorial: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-tutorial
- Plugins: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
- Adding tools: https://hermes-agent.nousresearch.com/docs/developer-guide/adding-tools
- Creating skills: https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills
- Hooks: https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
- Middleware: https://hermes-agent.nousresearch.com/docs/developer-guide/middleware
- MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- MCP config reference: https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference
- Slash commands reference: https://hermes-agent.nousresearch.com/docs/reference/slash-commands
- Subagent lifecycle API: https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api
- GitHub PR review agent guide: https://hermes-agent.nousresearch.com/docs/guides/github-pr-review-agent
- Docs index: https://hermes-agent.nousresearch.com/docs/llms.txt
