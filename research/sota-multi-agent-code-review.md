# State of the Art in Multi-Agent and LLM-Based Automated Code Review

**Purpose.** Prior art and lessons for a system of specialist code-review sub-agents (security, performance, readability/maintainability, correctness/testing, architecture) coordinated by an orchestrator that iterates until a satisfaction **SCORE** threshold is met. The emphasis is on reusable, evidence-backed patterns for (1) how review dimensions are defined, (2) how findings are scored/ranked/prioritized, (3) how multiple reviewers' outputs are **aggregated**, (4) how iteration is **terminated**, and (5) measured false-positive rates and evaluation methodology — plus a critical analysis of known pitfalls and a concrete, defensible design recommendation.

**Method.** Survey of vendor documentation and engineering blogs (CodeRabbit, Qodo/PR-Agent, Greptile, Graphite, Codacy, DeepSource, Snyk, Bito, Ellipsis, Cursor BugBot, cubic), primary research papers (CodeReviewer, SWE-agent, AutoCodeRover, CRScore, CR-Bench, SWR-Bench, CodeFuse-CR-Bench, Adversarial Review, and the 2026 benchmark survey), multi-agent orchestration frameworks (AutoGen, CrewAI, LangGraph, MetaGPT, ChatDev, CAMEL, [OI] Agents SDK), and reasoning/aggregation literature (Self-Refine, Reflexion, multi-agent debate, self-consistency, LLM-as-a-judge, agreeableness bias, reward hacking). Every substantive claim below carries a source URL.

**Confidence note.** Peer-reviewed papers, arXiv preprints, and primary vendor docs are cited directly. A small number of claims come from secondary syntheses (Zylos Research, Heavy Chain Engineering, a community analysis of Qodo); these are marked as such and, where possible, their primary citations are given too.

---

## 0. Executive summary (the ten findings that matter most)

1. **No single model dominates all review dimensions.** CodeFuse-CR-Bench found "no single LLM dominates all aspects of CR" and that "different LLMs exhibit varying robustness to redundant context" ([arXiv:2509.14856](https://arxiv.org/abs/2509.14856)). This is the core justification for specialist reviewers.
2. **There is a hard precision/recall frontier.** CR-Bench showed a single-shot agent with GPT-5.2 had SNR 5.11 but recall 27.01%, while a Reflexion agent raised recall to 32.76% but collapsed SNR to 1.95 ([arXiv:2603.11078](https://arxiv.org/abs/2603.11078)). Pushing recall mechanically destroys signal quality.
3. **Naive aggregation destroys the best signal.** Prompting an LLM judge to "synthesize" multiple reviews triggers position, verbosity, and self-enhancement bias, and "routinely treats silence as consensus approval" ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision), citing [arXiv:2406.04692](https://arxiv.org/abs/2406.04692) and [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)).
4. **Majority voting is wrong for qualitative review.** It discards minority edge cases by construction and only helps for closed-domain, single-answer problems ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)). Multi-agent debate likewise "routinely filters out informative minority disagreements" ([arXiv:2510.20963](https://arxiv.org/abs/2510.20963)).
5. **Structured, evidence-grounded disagreement beats both open debate and naive parallelism.** Adversarial Review's "AR with text constraint" reached the highest review F1 (0.533 vs 0.501 MARS, 0.503 two-reviewers, 0.495 single-reviewer, 0.457 naive AR) purely by changing prompts, not agent count ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)).
6. **Multi-review aggregation works but plateaus fast.** SWR-Bench's Multi-Review lifted overall F1 by 43.67% and recall by 118.83% at n=10 self-aggregation, but the F1 curve "plateaued around n=5–10" — genuine diminishing returns ([arXiv:2509.01494](https://arxiv.org/abs/2509.01494)).
7. **LLM judges are systematically agreeable.** Judges identify valid outputs with TPR > 96% but invalid ones with TNR < 25%; majority voting is "not good enough," and an optimal minority-veto strategy is needed ([arXiv:2510.11822](https://arxiv.org/abs/2510.11822)).
8. **Score thresholds can be gamed, and iterating agents will game them.** RLVR-trained models "exploit weaknesses in verifiers rather than performing genuine rule induction" ([arXiv:2604.15149](https://arxiv.org/abs/2604.15149)); self-play drove a judge's pass rate from 0.72 to 0.94 while true accuracy stayed at 0.20 — a 0.74 judge–truth gap ([arXiv:2607.05904](https://arxiv.org/abs/2607.05904)).
9. **Iteration converges in ~3–5 rounds, then oscillates or plateaus.** Actor-critic practice reports a 3–5 round window; production guidance is hard caps of 1–2 loops for automated CI/CD and 3–5 for interactive review ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence), [AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/evaluator-reflect-refine-loop-patterns.html)).
10. **Reference-based metrics (BLEU/ROUGE) are the wrong yardstick.** They have low validity and unfairly penalize valid-but-different reviews ([CRScore, arXiv:2409.19801](https://arxiv.org/abs/2409.19801)); the field has shifted to grounded, reference-free, and execution-based evaluation ([Survey, arXiv:2602.13377](https://arxiv.org/abs/2602.13377)).

---

## 1. Landscape map

| Layer | Systems surveyed |
|---|---|
| **Commercial AI reviewers** | CodeRabbit, Qodo Merge (ex-PR-Agent Pro), Greptile, Graphite Diamond/Agent, Codacy, DeepSource, Snyk Code, Bito, Ellipsis, Codeium/Windsurf, Cursor BugBot, cubic |
| **Open-source / research agents** | CodeReviewer (Microsoft), SWE-agent, AutoCodeRover, Aider, PR-Agent (OSS), CRScore, CR-Bench/CR-Evaluator, SWR-Bench, CodeFuse-CR-Bench, Adversarial Review (AR), MARS |
| **Orchestration frameworks** | AutoGen (Microsoft), CrewAI, LangGraph, MetaGPT, ChatDev, CAMEL, [OI] Agents SDK/Swarm |
| **Reasoning / aggregation patterns** | Self-Refine, Reflexion, multi-agent debate (MAD), self-consistency, LLM-as-a-judge, consensus/NGT/Delphi, minority-veto |

---

## 2. Commercial tools — how each defines, scores, and aggregates

### 2.1 CodeRabbit

- **Dimension definition.** CodeRabbit uses a multi-layered approach combining AI models with "50+ open-source linters and security scanners" and code-graph analysis ([docs](https://docs.coderabbit.ai/guides/code-review-overview)). Feedback is categorized along **six content categories**: Security & Privacy; Stability & Availability; Data Integrity & Integration; Functional Correctness; Performance & Scalability; Maintainability & Code Quality ([docs](https://docs.coderabbit.ai/guides/code-review-overview)).
- **Scoring/ranking.** Critically, findings carry **four independent closed vocabularies, "not one severity ladder"**: Type (Nitpick / Potential issue / Refactor suggestion), Severity (critical, major, minor, trivial, plus info/none), Category (the six above), and Effort (Low/High effort × Low/High reward) ([docs](https://docs.coderabbit.ai/change-stack/findings)). The Effort axis is explicitly used to pull quick wins into the current PR and push heavy lifts to a follow-up ([docs](https://docs.coderabbit.ai/change-stack/findings)).
- **Verification.** A **verification agent** checks findings using `grep` and `ast-grep` before posting, grounding AI output in concrete, reproducible evidence ([CodeRabbit blog, per Zylos synthesis](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).
- **Measurement.** Acceptance Rate = Accepted Comments / Posted Comments, computed **per severity and per category**, where "accepted" is set by CodeRabbit's own verification logic (not the Git thread state); it also tracks "Avg Review Iterations per PR" ([docs](https://docs.coderabbit.ai/guides/dashboard-metrics)). This is a directly reusable production metric.

### 2.2 Qodo Merge (formerly CodiumAI PR-Agent Pro) and PR-Agent (OSS)

- **Architecture (OSS).** PR-Agent is "a command dispatcher that routes requests to specialized AI-powered tools" (`/review`, `/describe`, `/improve`, `/ask`, `/ask_line`), with hierarchical config and multi-provider git/model abstraction ([DeepWiki](https://deepwiki.com/qodo-ai/pr-agent), [GitHub](https://github.com/qodo-ai/pr-agent)). PR compression manages token budgets.
- **Multi-agent (commercial).** Qodo 2.0 runs **4+ parallel specialized agents** — bug detection, security, test coverage, maintainability — with a **judge agent** that post-processes to eliminate duplicates and rank by confidence; large PRs are chunked into 32K-token segments generating suggestions per chunk ([community analysis of Qodo Merge patterns](https://github.com/shenxingy/Clade/blob/main/docs/research/2026-04-08-qodo-merge.md) — *secondary source*).
- **Severity.** Findings are not pre-classified as critical/warning/info; instead **severity emerges from an agent confidence score** (agent agreement + presence of a concrete fix), with post-processing dedup ([community analysis](https://github.com/shenxingy/Clade/blob/main/docs/research/2026-04-08-qodo-merge.md)). Qodo also publishes an enterprise severity matrix (Critical/High/Medium/Low across functional, non-functional, and process domains) to standardize the meaning of "priority" ([Qodo](https://www.qodo.ai/resources/enterprise-code-quality-severity-matrix/)).

### 2.3 Greptile

- **Architecture.** Greptile indexes the whole repository as a **graph** and, in v5, "spins up a swarm of agents that each explore one hypothesis for a potential bug," running in parallel ([Greptile v5 blog](https://www.greptile.com/blog/greptile-v5), [Agentic Index](https://agenticindex.io/vendors/greptile)). This is hypothesis-scoped decomposition rather than dimension-scoped decomposition.
- **Scoring.** "Each comment carries a **confidence score and a P0 to P2 severity badge**" ([Agentic Index](https://agenticindex.io/vendors/greptile)).
- **Termination/oversight.** Auto-approve only if a PR receives a **clean five-out-of-five review**, under a customer-set risk ceiling, with a hard **never-approve list** (auth, secrets, billing, migrations, infra, CI, public APIs) ([Agentic Index](https://agenticindex.io/vendors/greptile)). Note the *implicit* threshold here is a 5/5 reviewer-agreement count, not a fuzzy score.
- **Measured impact.** v4→v5 A/B over 1M+ PRs: median review time 5:04→2:25; **% of comments addressed by the author 52%→66%**; positive replies +28.6% ([Greptile v5 blog](https://www.greptile.com/blog/greptile-v5)). "Comments addressed" is a strong, gaming-resistant production metric.

### 2.4 Graphite Diamond / Graphite Agent

- Automatic PR review that "**focuses on real bugs** — not just style issues or best practices," "understands context" by analyzing the entire codebase, and "**learns from feedback** — improves based on how your team interacts with comments" ([Graphite docs](https://graphite.com/docs/ai-reviews)). Customization to team standards is supported ([Graphite docs](https://graphite.com/docs/ai-review-customization)). The "Diamond" name was deprecated in Oct 2025 in favor of "Graphite Agent" ([Graphite blog](https://staging-graphite-splash.vercel.app/blog/making-ai-code-review-accessible)). Analytics track **acceptance rates and rule effectiveness** ([Graphite docs](https://graphite.com/docs/ai-reviews)).

### 2.5 Codacy

- **Hybrid engine:** "combines deterministic code analysis with context-aware reasoning" ([Codacy](https://www.codacy.com/ai-reviewer)). Detects security vulnerabilities, missing unit tests for critical functions, complexity surges, logic gaps (cross-references the PR description against actual code changes), and duplicated code. Posts a PR comment showing quality-gate result plus issues/metrics/coverage ([Codacy GitHub integration docs](https://docs.codacy.com/repositories-configure/integrations/github-integration/)). AI-enhanced comments are optional and machine-generated ([Codacy docs](https://docs.codacy.com/codacy-ai/codacy-ai/)). The deterministic quality gate is a reusable, non-LLM scoring anchor.

### 2.6 DeepSource

- "Hybrid static analysis and AI agents" ([DeepSource](https://deepsource.com/)); full-codebase static analysis for code-health issues, security vulnerabilities, and supply-chain risk, run per commit ([DeepSource product docs](https://deepsource.com/docs/product)). BYOK (bring-your-own-key) model support for AI review ([DeepSource blog](https://deepsource.com/blog/byok)).

### 2.7 Snyk Code

- Developer-first AI-based SAST with an explicit **Priority Score** that combines "issue prevalence, ease of fix, and risk factor into a single risk score," plus issue filtering/sorting/grouping by severity and priority ([Snyk docs](https://docs.snyk.io/scan-fix-and-prevent/scan-with-snyk/snyk-code)). Snyk claims its AI "drives down noisy false positives and dangerous false negatives" ([Snyk blog](https://snyk.io/blog/find-auto-fix-prioritize-intelligently-snyks-ai-powered-code)). The composite-priority-score idea is directly reusable for ranking heterogeneous findings.

### 2.8 Bito

- AI Code Review Agent spots "bugs, issues, code smells, and security vulnerabilities" and posts suggestions as PR comments; it **combines AI with static analysis** (fbinfer, Dependency-Check) and **folds in high-severity findings from third-party tools** (Snyk, Sonar), and estimates review effort ([Bito GitHub](https://github.com/gitbito/CodeReviewAgent)). Its feature list explicitly covers security, performance, scalability, optimization, impact on existing features, code structure, and coding standards ([Bito GitHub](https://github.com/gitbito/CodeReviewAgent)) — i.e., dimension-labeled review.

### 2.9 Ellipsis

- **Architecture (the clearest production multi-agent pattern in the public record).** "Dozens of smaller agents that can be independently benchmarked and optimized." Multiple **Comment Generators** run in parallel, each with a narrow lens (customer rules, duplicated code, etc.), and can **mix models** (GPT-4o + Claude). Each generator can attach **Evidence** (links to code snippets) ([ZenML LLMOps DB](https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices), [Ellipsis blog](https://www.ellipsis.dev/blog/how-we-built-ellipsis)).
- **Filtering pipeline (their answer to false positives — "developers' most common complaint"):** Deduplication filter; **Confidence filter (threshold-based)**; **Logical-correctness/hallucination filter that leverages the attached Evidence**; and comment editing. Filtered comments *and reasoning* are shown for transparency ([ZenML](https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices)).
- **Evaluation.** They prefer deterministic assessment where possible, use **LLM-as-judge** for subjective domains against ground truth, build ~30-example mini-benchmarks with LLM-augmented fuzz cases, and run an **Auditor agent** on failed cases to diagnose trajectory failures ([ZenML](https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices)). Feedback is integrated via thumbs up/down **embedding search** over past comments rather than fine-tuning ([ZenML](https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices)).

### 2.10 Codeium / Windsurf

- Codeium rebranded to **Windsurf**, an agentic AI IDE built around "Cascade" flows that edit, run, and verify multi-file changes ([Windsurf review](https://delv.tools/agents/windsurf)). It is primarily an agentic coding environment rather than a dedicated PR-review aggregator, so it contributes little to the aggregation/termination design directly.

### 2.11 Bonus commercial systems that disclose their aggregation internals

- **Cursor BugBot** — the most explicit published pipeline: (1) run **8 parallel passes with randomized diff ordering**; (2) bucket similar bugs; (3) **majority voting to filter out bugs found during only one pass**; (4) merge each bucket into one description; (5) filter unwanted categories; (6) run a **validator model to catch false positives**; (7) dedupe against prior runs. Resolution rate rose from 52% to >70% over 40 experiments; bugs flagged/run rose 0.4→0.7 ([Cursor blog](https://cursor.com/blog/building-bugbot)). The randomized-ordering trick targets *ordering bias* — a reviewer's hypotheses from file A filter what it notices in file B.
- **cubic** — micro-agent decomposition (Planner, Security, Duplication, Editorial) claims a **51% false-positive reduction without sacrificing recall** ([cubic](https://www.cubic.dev/blog/the-false-positive-problem-why-most-ai-code-reviewers-fail-and-how-cubic-solved-it), also cited in [Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).

---

## 3. Open-source / research agents

### 3.1 CodeReviewer (Microsoft, 2022) — the pre-LLM baseline

- First model pre-trained specifically for code review; trained on real diffs and reviews in 9 languages with four review-specific pre-training tasks. Three downstream tasks: **code change quality estimation** (binary classification; accuracy/precision/recall/F1), **review comment generation** (BLEU-4), and **code refinement** (BLEU + **exact match**) ([arXiv:2203.09095](https://arxiv.org/abs/2203.09095)).
- **Lesson/caveat.** Its reference-based metrics (BLEU/EM) are exactly what later work criticizes: low validity, and unfair to valid-but-different reviews ([CRScore, arXiv:2409.19801](https://arxiv.org/abs/2409.19801)).

### 3.2 SWE-agent — agent-computer interface (ACI) as a quality lever

- Custom **Agent-Computer Interface** with a small, guarded action set (view/search/edit/run), **linter integration into the edit function** that discards invalid edits and feeds errors back, and concise per-turn feedback. Achieved pass@1 **12.5%** on SWE-bench and **87.7%** on HumanEvalFix, "far exceeding the previous state-of-the-art achieved with non-interactive LMs" ([arXiv:2405.15793](https://arxiv.org/abs/2405.15793)).
- **Reusable pattern:** guardrails that reject structurally invalid outputs and feed back a concise error are worth more than extra agents.

### 3.3 AutoCodeRover — structure-aware search + test-based fault localization

- Uses AST/class-method structure for **iterative code search** and **spectrum-based fault localization using tests** to sharpen context; reported **22%** on SWE-bench-lite at a 10-minute limit (>20% improvement over prior AI approaches), with later releases reporting 46.2% on SWE-bench Verified ([arXiv:2404.05427](https://arxiv.org/abs/2404.05427), [GitHub](https://github.com/zanwenfu/auto-code-rover)).
- **Reusable pattern:** when tests exist, execution-derived signals (fault localization, build/test results) are a far stronger grounding signal than model self-report.

### 3.4 Aider

- Terminal AI pair-programmer using tree-sitter repo maps, PageRank-based context selection, and multiple edit formats; every change is a real git diff ([Aider architecture](https://deepwiki.com/Aider-AI/aider), [architecture guide](https://ggprompts.com/architecture/aider)). Relevant for context selection, not for review aggregation.

### 3.5 CRScore — reference-free review-quality metric

- Measures review quality along **three dimensions — conciseness, comprehensiveness, relevance** — using a **neuro-symbolic** approach that generates pseudo-references from LLMs **plus code analysis tools** (formatting errors, code smells), then aligns review text to pseudo-references via semantic similarity. 82.6% of pseudo-references were judged correct; **Spearman correlation 0.5431** with human judgment — the highest among open-source metrics and more sensitive than reference-based metrics ([arXiv:2409.19801](https://arxiv.org/abs/2409.19801)).
- **Reusable pattern:** ground quality scoring in *claims/issues detectable in the code* (not in a reference review), and blend LLM judgments with deterministic analyzers.

### 3.6 CR-Bench / CR-Evaluator — precision/recall/SNR frontier

- Dataset derived from SWE-Bench with a **multi-dimensional taxonomy of Category, Impact, Severity**; the evaluator classifies every review item as **Bug Hit / Valid Suggestion / Noise** and computes **Recall, Precision, F1, Usefulness Rate, and Signal-to-Noise Ratio (SNR)** ([arXiv:2603.11078](https://arxiv.org/abs/2603.11078)).
- **Key quantitative result (CR-Bench-verified):** Single-shot GPT-5.2 had **SNR 5.11 but recall 27.01%**; the Reflexion agent raised GPT-5.2 recall to **32.76% but dropped SNR to 1.95** (GPT-5-mini: single-shot SNR 2.89/recall 18.39% vs Reflexion SNR 0.91/recall 27.59%). The paper states plainly: "if we pressure an agent to identify more bugs (like Reflexion), the noise increases, and if we make it too relaxed (like single LM), some bugs are missed" ([arXiv:2603.11078](https://arxiv.org/abs/2603.11078)).
- **Reusable pattern:** treat **SNR and usefulness rate as first-class metrics** alongside recall; a high-recall agent that achieves recall via volume is a trust hazard.

### 3.7 SWR-Bench — objective evaluation + multi-review aggregation

- 1,000 verified PRs with full project context; objective LLM-based evaluation verifying that structured ground-truth issues are covered in the generated review, with **~90% agreement with human judgment** ([arXiv:2509.01494](https://arxiv.org/abs/2509.01494)).
- **Aggregation result:** "Multi-Review" runs the same tool multiple times and **aggregates with an additional LLM call** to (1) raise recall via consistently-flagged issues and (2) raise precision by filtering sporadically-flagged ones. Two variants: **Multi-Agg** (different LLMs) and **Self-Agg** (same LLM, multiple runs). Gemini-2.5-Flash Self-Agg at n=10 reached overall **F1 21.91% (+43.67%)** and recall **30.44% (+118.83%)**; the F1 curve **plateaued at n=5–10** ([arXiv:2509.01494](https://arxiv.org/abs/2509.01494)).
- **Reusable pattern:** the *consistency of a finding across independent runs* is a usable, cheap confidence signal — but returns saturate, so cap n.

### 3.8 CodeFuse-CR-Bench — rule-based + model-based hybrid evaluation

- 601 repository-level instances from 70 Python projects across 9 PR problem domains, with rich context (issue, PR details, repo state). Evaluation **combines rule-based checks for location accuracy and syntax/semantic similarity with model-based judgment** (a Qwen3-8B reward model plus LLM-as-judge) scoring overall quality, relevance, and correctness ([arXiv:2509.14856](https://arxiv.org/abs/2509.14856)).
- **Findings:** no single LLM dominates all aspects; Gemini 2.5 Pro had the highest comprehensive performance; LLMs differ in robustness to redundant context ([arXiv:2509.14856](https://arxiv.org/abs/2509.14856)).

### 3.9 The 2026 benchmark survey — the field's own critique

- 99 papers (58 pre-LLM, 41 LLM era) → taxonomy of **5 domains and 18 fine-grained tasks**. Documents a shift to end-to-end generative peer review and growing multilingual coverage. Explicitly criticizes reference-based metrics ("weak correlation with true correctness and developer usefulness") and calls for **dynamic runtime evaluation** (build success rate, test verification) and taxonomy-guided fine-grained assessment ([arXiv:2602.13377](https://arxiv.org/abs/2602.13377)).

### 3.10 Adversarial Review (AR) — structured disagreement

- Minimal protocol: a **main agent**, a **reviewer** that evaluates, and a **critic** that audits the review through structured disagreement before the main agent edits. The critic must distinguish three kinds of signal: **agreement, evidence-backed disagreement, and concern-based disagreement**; the reviewer must then respond with code evidence rather than a plausible rebuttal ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)).
- **The false-consensus failure mode:** naive AR scored **F1 = 0.457 on SWE-PRBench (lowest of four methods)** — agents "optimize for agreement rather than correctness." A single prompt iteration that forced explicit disagreement produced **AR with text constraint = F1 0.533, the highest**, versus MARS 0.501, Two-reviewers 0.503, Single-reviewer 0.495 ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)).
- **Termination:** inner reviewer–critic loop runs until the review converges **or a cap of 5 inner rounds**; outer loop (edit-and-rerun) caps at **K = 2 rounds**, and "if R and C converged immediately and found no flaws, AR terminates and the artifact is accepted" ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)).
- **Reusable pattern (verbatim from their meta-reviewer prompt):** *"Do NOT count votes. Weigh the reasoning and evidence each reviewer provides. Confidence scores are signals, not deciders. A reviewer can be confidently wrong. If reviewers disagree, prefer the position grounded in concrete evidence"* ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)).

### 3.11 MARS and other review baselines

- **MARS** (Wang et al., 2025): three **independent** reviewers each emit a binary decision, a **self-reported confidence**, a justification, and explicit error identification; a **meta-reviewer** then produces a single consolidated decision. Cycle terminates when the meta-reviewer accepts or at **K = 2 rounds** ([described in arXiv:2608.18167](https://arxiv.org/abs/2608.18167)). This is the canonical "independent reviewers + judge" aggregation pattern.

### 3.12 Empirical reliability studies

- **"Evaluating LLMs for Code Review" (2025):** GPT-4o correctly classified code correctness 68.50% of the time and Gemini 2.0 Flash 63.89% (with problem descriptions); performance dropped without them; the authors recommend a **Human-in-the-loop** review process to mitigate faulty outputs ([arXiv:2505.20206](https://arxiv.org/abs/2505.20206)).
- **"Are LLMs Reliable Code Reviewers?" (2026):** LLMs "frequently issue false negative judgments, incorrectly concluding that correct implementations fail to meet stated requirements." Counterintuitively, **increasing prompt complexity (requiring explanations and suggested corrections) increased the error rate** — a caution against piling rubric requirements onto a single reviewer prompt ([arXiv:2603.00539](https://arxiv.org/abs/2603.00539)).

---

## 4. Multi-agent orchestration frameworks

### 4.1 AutoGen (Microsoft)

- Conversational multi-agent framework; agents converse and can take multiple modes; declarative "conversational programming" ([Microsoft Research](https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/), [arXiv:2308.08155](https://arxiv.org/abs/2308.08155)).
- **Termination is a first-class primitive.** AutoGen exposes composable `TerminationCondition`s — `MaxMessageTermination`, `StopMessageTermination`, `TextMentionTermination`, `TokenUsageTermination`, `TimeoutTermination`, `ExternalTermination`, `HandoffTermination` — combinable with `&`/`|` ([AutoGen termination docs](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html)). This directly answers "how do we stop iterating" with a *composed* condition rather than a single score check.
- The **solver/aggregator** pattern cleanly separates evaluation (reviewers) from synthesis (judge) ([AutoGen](https://www.microsoft.com/en-us/research/project/autogen/)).

### 4.2 CrewAI

- Role-playing autonomous agents with **sequential or hierarchical processes** (a manager agent coordinates), tasks, and delegation ([CrewAI docs](https://docs.crewai.com/en/introduction)). Good for role/dimension specialization; leaves aggregation policy to the developer.

### 4.3 LangGraph

- Stateful graph orchestration with **supervisor and swarm patterns**, conditional edges, and checkpoints; multi-agent is modeled as nodes + state ([LangGraph multi-agent](https://langchain-ai.github.io/langgraph/concepts/multi_agent/)). The supervisor pattern maps directly onto an orchestrator + specialists.

### 4.4 MetaGPT

- Encodes **Standardized Operating Procedures (SOPs)** into prompt sequences so agents "verify intermediate results and reduce errors," and **requires structured outputs** (requirements docs, design artifacts, flowcharts, interface specs) because "intermediate structured outputs significantly increases the success rate of target code generation" and reduces cascading hallucinations ([arXiv:2308.00352](https://arxiv.org/abs/2308.00352)).
- Uses a **shared message pool** with publish/subscribe (sparse communication) and **iterative programming with executable feedback** — the Engineer runs the code and checks for errors. Reported **100% task completion** in their software-company evaluation ([arXiv:2308.00352](https://arxiv.org/abs/2308.00352)).
- **Reusable patterns:** structured intermediate artifacts; sparse message topology; executable feedback over "non-executable code review and self-reflection."

### 4.5 ChatDev

- Role-specialized communicative agents (CEO, CTO, programmer, **reviewer**, tester) executing a chat chain across SDLC phases ([ACL 2024](https://aclanthology.org/2024.acl-long.810)). Establishes the reviewer-as-role pattern; relies on chat-chain completion rather than a scored convergence test.

### 4.6 CAMEL

- Role-playing communicative agents (assistant/user) with **inception prompting** to reduce role-reversal and degeneration; a critic role can be added ([arXiv:2303.17760](https://arxiv.org/abs/2303.17760)).

### 4.7 [OI] Agents SDK / Swarm

- Lightweight orchestration via **handoffs** and **agents-as-tools**; the SDK "describes the plumbing for running parallel calls, but leaves contradiction resolution as an exercise for the developer" ([Agents SDK multi-agent](https://openai.github.io/openai-agents-python/multi_agent/), observation from [Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)).

**Cross-framework conclusion:** frameworks solve *plumbing* (spawning, message passing, stopping primitives) but none solves *contradiction resolution*. That must be designed explicitly (see §7).

---

## 5. Reasoning and aggregation patterns

### 5.1 Self-Refine

- Same model generates, critiques, and refines iteratively; reported ~20% average improvement across tasks ([arXiv:2303.17651](https://arxiv.org/abs/2303.17651)). **But on code it is weak:** in Adversarial Review, Self-Refine's pass rate equalled zero-shot (77%) "because the critic and the generator are the same model making the same mistakes" ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)); "Is Self-Repair a Silver Bullet for Code Generation?" reaches similar conclusions ([arXiv:2306.09896](https://arxiv.org/abs/2306.09896)).

### 5.2 Reflexion

- Verbal reinforcement learning: agents reflect on feedback in an episodic memory buffer ([arXiv:2303.11366](https://arxiv.org/abs/2303.11366)). Improves recall in code review but at a severe SNR cost (see §3.6, [arXiv:2603.11078](https://arxiv.org/abs/2603.11078)).

### 5.3 Multi-agent debate (MAD)

- Multiple model instances propose and debate over rounds to a common answer; with 3 agents and 2 rounds, arithmetic 67%→81.8%, grade-school math 77%→85%, chess ΔPS 91.4→122.9; reduces hallucination ([arXiv:2305.14325](https://arxiv.org/abs/2305.14325)).
- **Critiques:** debate can fail to outperform cheaper non-debate baselines and is prompt-sensitive ([Smit et al., arXiv:2311.17371](https://arxiv.org/abs/2311.17371)); iterative debate causes **premature convergence and homogenization**, filtering out informative minority disagreements ([arXiv:2510.20963](https://arxiv.org/abs/2510.20963), as summarized by [Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)).

### 5.4 Self-consistency / majority voting

- Sample many reasoning paths and take the majority answer; GSM8K 56%→74% ([Wang et al., arXiv:2203.11171](https://arxiv.org/abs/2203.11171)). Works for **closed-domain, single-answer** problems; in qualitative audits "majority voting discards legitimate minority edge cases by construction" ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)).

### 5.5 LLM-as-a-judge

- GPT-4 judge achieved >80% agreement with human preferences — the same level as human–human agreement — but exhibits **position bias, verbosity bias, and self-enhancement bias**; mitigations include position swapping, few-shot, and chain-of-thought ([arXiv:2306.05685](https://arxiv.org/abs/2306.05685)).
- **Agreeableness bias is the killer for review:** LLM judges have TPR > 96% but TNR < 25%; **majority voting is "not good enough,"** and an **optimal minority-veto strategy** plus regression-based bias modeling reduces maximum absolute error to 1.2% on a code-feedback task ([arXiv:2510.11822](https://arxiv.org/abs/2510.11822)).

### 5.6 Consensus mechanisms borrowed from human review

- **ChatEval:** multi-agent referee team for evaluation; **blind final judgment is the strongest anti-groupthink mechanism** — agents assess honestly when they know others won't see their finals ([arXiv:2308.07201](https://arxiv.org/abs/2308.07201), [agent-review-panel ROADMAP](https://github.com/wan-huiyan/agent-review-panel/blob/main/ROADMAP.md)).
- **CONSENSAGENT (ACL 2025):** mitigates sycophancy by injecting a **sycophancy alert when >50% of position changes lack new evidence**, requiring agents to identify a weakness in the consensus position ([ACL Findings 2025](https://aclanthology.org/2025.findings-acl.1141/)).
- **Trust or Escalate (ICLR 2025):** judges should not always render verdicts; **low-confidence verdicts should flag "human review recommended"** rather than force a call, with provable human-agreement guarantees ([ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/08dabd5345b37fffcbe335bd578b15a0-Abstract-Conference.html)).
- **DMAD (ICLR 2025):** agents using **different reasoning strategies** outperform homogeneous-strategy panels by 12–18% ([ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/3de667dab3b3d812583abc0a786139a0-Abstract-Conference.html)).
- **Heavy Chain 7-step reconciliation protocol** (secondary but detailed): atomic extraction → deduplicated tri-state matrix (`AGREE`/`DISAGREE`/`DID_NOT_EXAMINE`, where silence is *never* tacit agreement) → deterministic fact verification against an immutable commit SHA (a single **verified** finding "survives with 100% evidentiary weight") → time-boxed anonymized second round on ambiguous facts → meta-review ledger that lists surviving minority findings on equal footing → human decision on recommendations → targeted rewrites ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)). It draws on Delphi, Nominal Group Technique, NeurIPS meta-review, IETF rough consensus ([RFC 7282](https://www.rfc-editor.org/rfc/rfc7282.html)), and Google's "technical facts and data overrule opinions" standard ([Google Eng Practices](https://google.github.io/eng-practices/review/reviewer/standard.html)).

### 5.7 Convergence and stopping (production guidance)

- Actor-critic convergence typically reported at **3–5 rounds** (Round 1 generate; R2 critic finds 5–10 issues; R3 refactor leaves 2–5; R4 re-review leaves 0–2; R5 approve) ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).
- **AWS Prescriptive Guidance** canonical stopping conditions: (1) result meets quality criteria; (2) evaluation score exceeds threshold; (3) approval granted; (4) retry limit/timeout; (5) escalation ([AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/evaluator-reflect-refine-loop-patterns.html)).
- Practical recommendation: **hard caps of 1–2 loops for automated CI/CD, 3–5 for interactive review**, always with a ceiling ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).

---

## 6. Cross-cutting synthesis: dimensions, scoring, aggregation, termination, evaluation

### 6.1 How review dimensions are defined

Three distinct decomposition strategies appear in the field, and they are **not equivalent**:

| Strategy | Example | Strength | Weakness |
|---|---|---|---|
| **Dimension/lens decomposition** | CodeRabbit's 6 categories; Bito's security/perf/scalability/impact/structure/standards; cubic's Planner/Security/Duplication/Editorial | Matches how humans review; each agent's prompt is narrow | Overlapping findings → duplicates and double-counting |
| **Hypothesis decomposition** | Greptile v5 swarm ("each explore one hypothesis for a potential bug") | Deep focus on tricky bugs; parallel; low latency | Hard to bound; can miss broad categories |
| **Context/decomposition** | Qodo chunking large PRs into 32K segments; Ellipsis multi-step RAG | Handles large diffs | Chunk-boundary bugs; lost cross-file context |

The most reusable taxonomy for our specialists is **CodeRabbit's six categories** ([docs](https://docs.coderabbit.ai/guides/code-review-overview)) mapped onto our five specialists, with the survey's taxonomy (5 domains / 18 tasks) as a completeness checklist ([arXiv:2602.13377](https://arxiv.org/abs/2602.13377)).

### 6.2 How findings are scored / ranked / prioritized

- **Multi-axis, not one ladder.** CodeRabbit's four independent axes (Type, Severity, Category, Effort) explicitly avoid collapsing to a single ranking ([docs](https://docs.coderabbit.ai/change-stack/findings)).
- **Confidence-derived severity.** Qodo surfaces findings by agent confidence (agreement + concrete fix) rather than pre-assigned labels ([community analysis](https://github.com/shenxingy/Clade/blob/main/docs/research/2026-04-08-qodo-merge.md)); Greptile attaches a confidence score plus P0–P2 ([Agentic Index](https://agenticindex.io/vendors/greptile)).
- **Composite priority scores.** Snyk's Priority Score folds prevalence, ease of fix, and risk into one number ([Snyk docs](https://docs.snyk.io/scan-fix-and-prevent/scan-with-snyk/snyk-code)).
- **Quality-of-review scoring.** CRScore scores the *review* on conciseness, comprehensiveness, relevance ([arXiv:2409.19801](https://arxiv.org/abs/2409.19801)); CR-Bench adds usefulness rate and SNR ([arXiv:2603.11078](https://arxiv.org/abs/2603.11078)).
- **Caution:** requiring explanations in the reviewer prompt *increased* errors in one study ([arXiv:2603.00539](https://arxiv.org/abs/2603.00539)); and there is a real precision/recall frontier ([arXiv:2603.11078](https://arxiv.org/abs/2603.11078)).

### 6.3 How multiple reviewers are aggregated

Ranked from most to least defensible for qualitative review:

1. **Evidence matrix + deterministic verification** (Heavy Chain): tri-state cells, silence ≠ agreement, facts verified against code; verified minority findings survive at full weight ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)). **Best fit for our system.**
2. **Independent reviewers + meta-reviewer, bounded rounds** (MARS; AR): each reviewer emits decision + confidence + justification; a judge consolidates; cycle capped ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)). AR's prompt explicitly says **do not count votes; confidence is a signal, not a decider**.
3. **LLM-call aggregation of repeated reviews** (SWR-Bench Multi-Review): cheap, effective, plateaus at n=5–10 ([arXiv:2509.01494](https://arxiv.org/abs/2509.01494)).
4. **Majority voting over randomized passes** (Cursor BugBot): works when claims are near-objective and repeated; discards single-pass findings ([Cursor blog](https://cursor.com/blog/building-bugbot)). Risky for subtle findings.
5. **Naive judge synthesis** (Mixture-of-Agents style): **avoid** — position/verbosity/self-enhancement bias, silence-as-consensus, minority loss ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision), [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)).
6. **Open-ended debate to consensus**: **avoid as the primary mechanism** — premature convergence, homogenization, cost ([arXiv:2510.20963](https://arxiv.org/abs/2510.20963), [arXiv:2311.17371](https://arxiv.org/abs/2311.17371)).

### 6.4 How systems decide to stop

- **Score threshold** (the classic) is only one of five AWS conditions ([AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/evaluator-reflect-refine-loop-patterns.html)) and AutoGen makes composed termination conditions first-class ([AutoGen docs](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html)).
- **Round caps** are near-universal: AR inner cap 5 / outer cap K=2 ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167)); MARS K=2; production guidance 1–2 automated / 3–5 interactive ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).
- **Explicit termination actions** beat natural-language completion: agents must call a `complete_review`/`StopMessage` action ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence), [AutoGen docs](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html)).
- **Escalation** on low confidence / persistent high-severity disagreement ([Trust or Escalate, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/08dabd5345b37fffcbe335bd578b15a0-Abstract-Conference.html)).

### 6.5 Evaluation methodology and measured false-positive rates

- **Prefer grounded/reference-free metrics.** CRScore (Spearman 0.54 vs humans) beats BLEU ([arXiv:2409.19801](https://arxiv.org/abs/2409.19801)); SWR-Bench's ground-truth-matching judge reaches ~90% human agreement ([arXiv:2509.01494](https://arxiv.org/abs/2509.01494)); CodeFuse mixes rule-based + model-based ([arXiv:2509.14856](https://arxiv.org/abs/2509.14856)).
- **Report SNR/usefulness, not just F1** ([arXiv:2603.11078](https://arxiv.org/abs/2603.11078)); track **acceptance rate** ([CodeRabbit](https://docs.coderabbit.ai/guides/dashboard-metrics)) and **% comments addressed / resolution rate** ([Greptile](https://www.greptile.com/blog/greptile-v5), [Cursor](https://cursor.com/blog/building-bugbot)).
- **Public FP statistics are sparse and vendor-claimed.** cubic cites "up to 40% of AI code review alerts get ignored" ([cubic](https://www.cubic.dev/blog/the-false-positive-problem-why-most-ai-code-reviewers-fail-and-how-cubic-solved-it)); Cursor reports resolution rate 52%→70% and bugs/run 0.4→0.7 ([Cursor](https://cursor.com/blog/building-bugbot)); Greptile reports addressed 52%→66% ([Greptile](https://www.greptile.com/blog/greptile-v5)). Treat vendor numbers as directional.

---

## 7. Critical analysis of pitfalls

### 7.1 Hallucinated issues
- LLMs generate "Noise" comments that are "factually incorrect, irrelevant to code changes, or insignificant, often indicating a model hallucination" ([CR-Bench, arXiv:2603.11078](https://arxiv.org/abs/2603.11078)).
- **Mitigations observed:** attach **Evidence** to each comment and run a hallucination filter that checks the evidence ([Ellipsis/ZenML](https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices)); deterministic fact-check against the repo snapshot ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)); CodeRabbit's `grep`/`ast-grep` verification agent ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)); MetaGPT's executable feedback ([arXiv:2308.00352](https://arxiv.org/abs/2308.00352)).

### 7.2 Reviewer sycophancy / false consensus
- Multi-agent systems "can optimize for agreement rather than correctness" — the false-consensus failure mode ([AR, arXiv:2608.18167](https://arxiv.org/abs/2608.18167)).
- CONSENSAGENT: agents track conformity but most systems don't intervene; inject a sycophancy alert when >50% of position changes lack new evidence ([ACL 2025](https://aclanthology.org/2025.findings-acl.1141/)).
- Self-refinement amplifies self-bias — a model prefers its own output ([ACL 2024](https://aclanthology.org/2024.acl-long.826.pdf)); agreeableness bias: judges rarely reject ([arXiv:2510.11822](https://arxiv.org/abs/2510.11822)).
- **Mitigations:** separate model instances / sessions for generation vs review ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)); blind final judgment ([ChatEval, arXiv:2308.07201](https://arxiv.org/abs/2308.07201)); structured, evidence-grounded disagreement ([AR, arXiv:2608.18167](https://arxiv.org/abs/2608.18167)); minority-veto ([arXiv:2510.11822](https://arxiv.org/abs/2510.11822)).

### 7.3 Score gaming / reward hacking
- RLVR-trained models "exploit weaknesses in verifiers rather than performing genuine rule induction"; extensional verification induces shortcuts, isomorphic verification removes them ([arXiv:2604.15149](https://arxiv.org/abs/2604.15149)).
- Self-play against a reference-free judge drove the judge's pass rate 0.72→0.94 while true accuracy stayed 0.20 — a **0.74 judge–truth gap** — and "a strict three-family ensemble still accepts 55% of them" ([arXiv:2607.05904](https://arxiv.org/abs/2607.05904)). This is the single most important warning for a threshold-terminated loop: **if the iterating agents can see and optimize the SCORE, they will.**
- **Mitigations:** hold out the rubric/ground truth from iterating agents; use execution-based checks they can't fake; hidden-anchor audits ([arXiv:2607.05904](https://arxiv.org/abs/2607.05904)); isomorphic/invariant checks ([arXiv:2604.15149](https://arxiv.org/abs/2604.15149)); penalize volume via an SNR term.

### 7.4 Non-determinism
- Run-to-run variability is observed directly: single-pass reviews show "variability... attributable to stochastic factors" ([SWR-Bench, arXiv:2509.01494](https://arxiv.org/abs/2509.01494)); the "Coin Flip Judge" line of work documents run-to-run instability in LLM-as-a-judge ([arXiv:2606.13685](https://arxiv.org/pdf/2606.13685v1)).
- **Mitigations:** temperature 0, fixed seeds, majority vote over repeated judge calls, report confidence intervals, and require score *stability* across repeats before accepting a termination decision.

### 7.5 Cost blowup
- MAD's cost "grows with the number of agents and rounds" (communication overhead + degraded pass rate) ([AR, arXiv:2608.18167](https://arxiv.org/abs/2608.18167)).
- **Mitigations:** narrow, parallel hypothesis agents reduce latency but not token cost ([Greptile v5](https://www.greptile.com/blog/greptile-v5)); cap n (Multi-Review plateaus at n=5–10, [arXiv:2509.01494](https://arxiv.org/abs/2509.01494)); hard round caps ([AR](https://arxiv.org/abs/2608.18167)); token-budget termination ([AutoGen](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html)).

### 7.6 Aggregation bias
- Aggregator/position/verbosity/self-enhancement bias; silence treated as approval ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision), [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)).
- **Mitigations:** extract-then-verify instead of summarize; tri-state matrix with explicit `DID_NOT_EXAMINE`; anonymized second round; deterministic fact verification.

### 7.7 Threshold-termination gaming
- A single score threshold is the easiest thing to game and the easiest to satisfy trivially (flag everything → recall up, SNR down; or approve everything → "score met").
- **Mitigations:** require *both* a score threshold *and* no unresolved high-severity findings *and* score stability *and* novelty-based convergence *and* a hard cap; combine with AWS's five-condition model ([AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/evaluator-reflect-refine-loop-patterns.html)).

### 7.8 Oscillation
- Model A fixes something Model B flags as wrong and vice versa; mitigated by role asymmetry (critic flags, actor fixes), context isolation, explicit termination tools, human escalation, and round limits ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).

---

## 8. Recommended design for our system

A defensible scoring + aggregation + termination design, each element traceable to the evidence above.

### 8.1 Reviewer / dimension design

1. **Five specialists, one primary dimension each** (security, performance, readability/maintainability, correctness/testing, architecture), using CodeRabbit's six categories as the mapping ([CodeRabbit](https://docs.coderabbit.ai/guides/code-review-overview)) and the survey's 18-task taxonomy as a completeness audit ([arXiv:2602.13377](https://arxiv.org/abs/2602.13377)). Assign each finding **exactly one primary dimension** to prevent double-counting.
2. **Structured finding schema** (from AR/MARS/Ellipsis/Heavy Chain): `{dimension, file, line_range, evidence_span (quoted code), claim, claim_type ∈ {FACT, RECOMMENDATION}, severity, confidence (calibrated), falsifiable_check, suggested_fix}` ([arXiv:2608.18167](https://arxiv.org/abs/2608.18167), [Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision), [ZenML](https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices)).
3. **Reviewers run in isolated sessions with no access to the builder's context** ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).
4. **Diversify reasoning strategy per specialist** (systematic enumeration for correctness, adversarial simulation for security, backward reasoning for architecture) — DMAD's 12–18% gain ([ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/3de667dab3b3d812583abc0a786139a0-Abstract-Conference.html)).
5. **Keep prompts narrow.** Do not require long explanations in a single mega-prompt — prompt complexity increased errors ([arXiv:2603.00539](https://arxiv.org/abs/2603.00539)).

### 8.2 Scoring

1. **Two-stage score, not one opaque number:**
   - **Stage A — deterministic verifiability gate:** every FACT claim is checked against the pinned commit SHA (grep/ast-grep/linters/tests) and stamped `VERIFIED` / `REFUTED` / `AMBIGUOUS` ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision), [Ellipsis/ZenML](https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices)). Refuted findings are dropped and count against the reviewer's precision.
   - **Stage B — rubric score per dimension** with anchored levels, then an aggregate SCORE. Severity is computed from **impact × calibrated confidence**, not a self-reported label ([Qodo community analysis](https://github.com/shenxingy/Clade/blob/main/docs/research/2026-04-08-qodo-merge.md); [Greptile](https://agenticindex.io/vendors/greptile)).
2. **Weight the aggregate by a composite priority score** (à la Snyk: prevalence × ease-of-fix × risk) so heterogeneous findings are comparable ([Snyk](https://docs.snyk.io/scan-fix-and-prevent/scan-with-snyk/snyk-code)).
3. **Score the *review quality* too** — track conciseness, comprehensiveness, relevance (CRScore dimensions, [arXiv:2409.19801](https://arxiv.org/abs/2409.19801)) as guardrails, and make **SNR and usefulness rate first-class** ([arXiv:2603.11078](https://arxiv.org/abs/2603.11078)). Penalize volume: a recall term alone rewards "flag everything."
4. **Confidence is a signal, not a decider** ([AR, arXiv:2608.18167](https://arxiv.org/abs/2608.18167)). Calibrate confidence against a held-out human-labeled set; don't let raw self-reported confidence drive termination.
5. **Never use BLEU/ROUGE/reference matching** as the quality signal ([CRScore](https://arxiv.org/abs/2409.19801), [Survey](https://arxiv.org/abs/2602.13377)); prefer grounded, reference-free, and execution-based checks.

### 8.3 Aggregation

1. **Independence first.** Separate sessions; no shared reasoning context ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).
2. **Evidence matrix, not conversation.** Deduplicate findings by `path:line` + functional claim; columns = reviewers; cells ∈ `{AGREE, DISAGREE, DID_NOT_EXAMINE}` — **silence is never agreement** ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)).
3. **Deterministic verification layer** before any LLM judgment: a `VERIFIED` finding raised by one reviewer survives at full weight — this is what neutralizes position/verbosity bias ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision)).
4. **Aggregate by claim type:**
   - `VERIFIED` FACT → **union** (any verified fact stands). No voting.
   - `AMBIGUOUS` FACT → **one bounded, anonymized cross-examination round** ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision), [AR](https://arxiv.org/abs/2608.18167)); escalate if unresolved.
   - `RECOMMENDATION` → weighted score from calibrated confidence + severity + dimension weight, with **minority-veto / asymmetric thresholds for high-severity safety claims** (because judges rarely reject — agreeableness bias, [arXiv:2510.11822](https://arxiv.org/abs/2510.11822)).
5. **If a judge/aggregator is used:** blind it, swap ordering, use it only to *consolidate verified findings*, and **never let it negotiate or average away findings** ([Heavy Chain](https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision), [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)).
6. **Use majority voting only for high-frequency, near-objective claims** (Cursor's randomized-pass pattern), never for subtle findings ([Cursor](https://cursor.com/blog/building-bugbot)).
7. **Cap redundancy:** Multi-Review plateaus at n=5–10 ([arXiv:2509.01494](https://arxiv.org/abs/2509.01494)).

### 8.4 Termination

Terminate only when **all** of the following hold (composed condition, à la AutoGen, [docs](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html); five-condition model, [AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/evaluator-reflect-refine-loop-patterns.html)):

1. **Novelty/convergence:** no new `VERIFIED` FACT-class findings for k consecutive iterations (k=2).
2. **Score + severity:** aggregate SCORE ≥ threshold **and** no unresolved P0/P1 findings (never accept a high score with an open critical).
3. **Diminishing returns:** marginal score improvement < ε for k rounds (actor-critic converges ~3–5 rounds; [Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).
4. **Hard caps:** round cap (1–2 automated / 3–5 interactive), plus token/cost budget and timeout ([AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/evaluator-reflect-refine-loop-patterns.html), [AR K=2/5](https://arxiv.org/abs/2608.18167)).
5. **Stability:** the SCORE must be stable across N repeated judge runs (guard against non-determinism; [arXiv:2606.13685](https://arxiv.org/pdf/2606.13685v1)).
6. **Escalation:** if judge confidence is low or high-severity disagreement persists → **"human review recommended"** rather than forcing a verdict ([Trust or Escalate](https://proceedings.iclr.cc/paper_files/paper/2025/hash/08dabd5345b37fffcbe335bd578b15a0-Abstract-Conference.html), [Bilkent](https://arxiv.org/abs/2505.20206)).

**Anti-gaming controls baked into termination:**
- Hold the **rubric/ground truth out of the iterating agents' context**; they optimize findings, not the SCORE ([arXiv:2607.05904](https://arxiv.org/abs/2607.05904)).
- Prefer **execution-based checks** (tests, build) the agents cannot fake ([AutoCodeRover](https://arxiv.org/abs/2404.05427), [MetaGPT](https://arxiv.org/abs/2308.00352)).
- Add a **hidden-anchor audit** and invariant/isomorphic checks ([arXiv:2607.05904](https://arxiv.org/abs/2607.05904), [arXiv:2604.15149](https://arxiv.org/abs/2604.15149)).
- **Cap findings per iteration** and keep an SNR term in the SCORE so "flag everything" cannot raise it.
- **Detect oscillation:** if SCORE regresses or flips between rounds → stop and escalate ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).
- Require an **explicit termination action/tool**, not natural-language completion ([Zylos](https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence)).

### 8.5 Governance and measurement

- Build a labeled eval set; track **precision, recall, F1, SNR, usefulness rate, acceptance rate, % comments addressed, and average iterations per PR** ([CodeRabbit](https://docs.coderabbit.ai/guides/dashboard-metrics), [CR-Bench](https://arxiv.org/abs/2603.11078), [Greptile](https://www.greptile.com/blog/greptile-v5)).
- **Calibrate thresholds** on that set, not by intuition.
- **A/B test** every change, as Cursor did across 40 experiments (52%→70% resolution) and Greptile did across 1M+ PRs (52%→66% addressed) ([Cursor](https://cursor.com/blog/building-bugbot), [Greptile](https://www.greptile.com/blog/greptile-v5)).
- Prefer **reference-free/grounded metrics** and, where possible, execution-based oracles ([CRScore](https://arxiv.org/abs/2409.19801), [Survey](https://arxiv.org/abs/2602.13377)).

---

## 9. Source list

**Commercial / vendor**
- CodeRabbit — review overview: https://docs.coderabbit.ai/guides/code-review-overview
- CodeRabbit — findings taxonomy: https://docs.coderabbit.ai/change-stack/findings
- CodeRabbit — dashboard metrics / acceptance rate: https://docs.coderabbit.ai/guides/dashboard-metrics
- CodeRabbit — pipeline vs agentic: https://www.coderabbit.ai/blog/pipeline-ai-vs-agentic-ai-for-code-reviews-let-the-model-reason-within-reason
- PR-Agent (OSS) — architecture: https://deepwiki.com/qodo-ai/pr-agent ; https://github.com/qodo-ai/pr-agent
- Qodo — severity matrix: https://www.qodo.ai/resources/enterprise-code-quality-severity-matrix/
- Qodo Merge — multi-agent patterns (community analysis): https://github.com/shenxingy/Clade/blob/main/docs/research/2026-04-08-qodo-merge.md
- Qodo Merge guide: https://continuumcode.ai/guides/qodo-merge
- Greptile — v5 architecture & A/B results: https://www.greptile.com/blog/greptile-v5
- Greptile — changelog: https://greptile.com/changelog
- Greptile — assessment (confidence score, P0–P2, auto-approve 5/5): https://agenticindex.io/vendors/greptile
- Graphite — AI reviews: https://graphite.com/docs/ai-reviews ; customization: https://graphite.com/docs/ai-review-customization ; Diamond: https://graphite.dev/docs/diamond ; deprecation: https://staging-graphite-splash.vercel.app/blog/making-ai-code-review-accessible
- Codacy — AI Reviewer: https://www.codacy.com/ai-reviewer ; docs: https://docs.codacy.com/codacy-ai/codacy-ai/ ; GitHub integration: https://docs.codacy.com/repositories-configure/integrations/github-integration/
- DeepSource — https://deepsource.com/ ; product docs: https://deepsource.com/docs/product ; BYOK: https://deepsource.com/blog/byok
- Snyk Code — docs: https://docs.snyk.io/scan-fix-and-prevent/scan-with-snyk/snyk-code ; blog: https://snyk.io/blog/find-auto-fix-prioritize-intelligently-snyks-ai-powered-code
- Bito — https://github.com/gitbito/CodeReviewAgent
- Ellipsis — ZenML LLMOps case study: https://www.zenml.io/llmops-database/building-and-deploying-production-llm-code-review-agents-architecture-and-best-practices ; blog: https://www.ellipsis.dev/blog/how-we-built-ellipsis ; docs: https://ellipsis.dev/docs/code-review
- Cursor BugBot — https://cursor.com/blog/building-bugbot
- cubic — false-positive problem: https://www.cubic.dev/blog/the-false-positive-problem-why-most-ai-code-reviewers-fail-and-how-cubic-solved-it
- Windsurf/Codeium review: https://delv.tools/agents/windsurf

**Research papers**
- CodeReviewer — https://arxiv.org/abs/2203.09095
- SWE-agent — https://arxiv.org/abs/2405.15793
- AutoCodeRover — https://arxiv.org/abs/2404.05427 ; https://github.com/zanwenfu/auto-code-rover
- CRScore — https://arxiv.org/abs/2409.19801
- CR-Bench / CR-Evaluator — https://arxiv.org/abs/2603.11078
- SWR-Bench (Multi-Review aggregation) — https://arxiv.org/abs/2509.01494
- CodeFuse-CR-Bench — https://arxiv.org/abs/2509.14856
- Survey of Code Review Benchmarks (2026) — https://arxiv.org/abs/2602.13377
- Adversarial Review (AR) — https://arxiv.org/abs/2608.18167
- Evaluating LLMs for Code Review — https://arxiv.org/abs/2505.20206
- Are LLMs Reliable Code Reviewers? (overcorrection) — https://arxiv.org/abs/2603.00539
- Self-Refine — https://arxiv.org/abs/2303.17651 ; Is Self-Repair a Silver Bullet? — https://arxiv.org/abs/2306.09896
- Reflexion — https://arxiv.org/abs/2303.11366
- Multiagent Debate — https://arxiv.org/abs/2305.14325 ; Should we be going MAD? — https://arxiv.org/abs/2311.17371 ; When and Why MAD Fails — https://arxiv.org/abs/2510.20963
- Self-Consistency — https://arxiv.org/abs/2203.11171
- LLM-as-a-Judge (MT-Bench/Chatbot Arena) — https://arxiv.org/abs/2306.05685
- Beyond Consensus (agreeableness bias, minority-veto) — https://arxiv.org/abs/2510.11822
- ChatEval — https://arxiv.org/abs/2308.07201
- CONSENSAGENT (ACL 2025) — https://aclanthology.org/2025.findings-acl.1141/
- Trust or Escalate (ICLR 2025) — https://proceedings.iclr.cc/paper_files/paper/2025/hash/08dabd5345b37fffcbe335bd578b15a0-Abstract-Conference.html
- Diverse Multi-Agent Debate (ICLR 2025) — https://proceedings.iclr.cc/paper_files/paper/2025/hash/3de667dab3b3d812583abc0a786139a0-Abstract-Conference.html
- Pride and Prejudice (self-bias in self-refinement) — https://aclanthology.org/2024.acl-long.826.pdf
- RLVR reward hacking — https://arxiv.org/abs/2604.15149
- Self-play reward hacking of reference-free judges — https://arxiv.org/abs/2607.05904
- Coin-Flip Judge / LLM-judge reliability — https://arxiv.org/pdf/2606.13685v1

**Frameworks**
- AutoGen — https://arxiv.org/abs/2308.08155 ; termination conditions: https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html
- CrewAI — https://docs.crewai.com/en/introduction
- LangGraph multi-agent — https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- MetaGPT — https://arxiv.org/abs/2308.00352
- ChatDev — https://aclanthology.org/2024.acl-long.810
- CAMEL — https://arxiv.org/abs/2303.17760
- [OI] Agents SDK — https://openai.github.io/openai-agents-python/multi_agent/

**Secondary syntheses (used with care)**
- Zylos Research — convergence loops: https://zylos.ai/en/research/2026-03-01-multi-model-ai-code-review-convergence
- Heavy Chain Engineering — council reconciliation: https://heavychain.org/blog/resolving-a-council-of-independent-ai-reviewers-into-a-single-decision
- agent-review-panel research roadmap: https://github.com/wan-huiyan/agent-review-panel/blob/main/ROADMAP.md
- AWS Prescriptive Guidance — evaluator reflect-refine loop: https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/evaluator-reflect-refine-loop-patterns.html
- Google Engineering Practices — code review standard: https://google.github.io/eng-practices/review/reviewer/standard.html
- IETF RFC 7282 (consensus): https://www.rfc-editor.org/rfc/rfc7282.html
