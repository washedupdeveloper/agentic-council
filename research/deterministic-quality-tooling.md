# Deterministic Quality-Analysis Tooling: A Per-Category × Per-Language Matrix and Normalization Pipeline

**Purpose.** Ground specialist code-review agents (security, performance, readability/maintainability, correctness/testing, architecture, dependencies/supply-chain, documentation, error-handling/reliability, accessibility, compliance/licensing) in *deterministic, automatable signals* produced by real analyzers, so that a hybrid score is not pure-LLM judgment. LLM scores are noisy, gameable, and non-reproducible; analyzer output is reproducible given pinned inputs. This document specifies **which tool produces which signal, how to run it, how to parse it, how to extract a number, and how to normalize heterogeneous numbers into a stable 0–100 per-category score that is byte-for-byte reproducible in CI.**

Target polyglot codebase: **Python, JavaScript/TypeScript, Go, Rust, Java.** The matrix is organized so a language column can be filled in incrementally without touching the scoring math.

---

## 0. Design principles

1. **Canonical intermediate = SARIF where possible.** SARIF v2.1.0 is the lowest-common-denominator machine format for findings-based tools (semgrep, CodeQL, gosec, Bandit, Trivy, Grype, golangci-lint, osv-scanner, ruff, ESLint). Normalize everything to a common finding record `{tool, rule_id, severity, file, line, weight}` before scoring. Non-SARIF tools are adapted with a tiny parser (JSON/CSV/plain).
2. **Two signal families.** *Findings* (discrete issues with severity) and *metrics* (scalars like coverage %, MI, mutation score, complexity). They normalize differently.
3. **Density, not raw counts.** Absolute counts punish large repos; use **severity-weighted findings per KLOC**. Metrics are bounded and normalized by threshold curves.
4. **Version-pin everything.** Tool version, rule-pack version, analyzer config, vulnerability DB. A score is only valid with its manifest.
5. **Determinism beats coverage.** If a tool is non-deterministic (live credential verification, network-dependent advisories, benchmark timing), either run it offline with pinned data or exclude it from the scored path and report it as advisory.
6. **No single tool is the truth.** Per category, combine multiple tools with a **weighted geometric mean** so one very bad tool cannot be diluted by many good ones.

---

## 1. Score model

### 1.1 Severity weights (findings)

Map each finding to a weight `w`. Defaults (configurable per repo):

| Severity label | Weight `w` |
|---|---|
| critical / blocker | 10 |
| high / error | 5 |
| medium / warning | 2 |
| low / note | 1 |
| info / style | 0.25 |

SARIF `result.level` (`error`/`warning`/`note`) and tool-native severities both map onto this table. Some tools expose a numeric CVSS/EPSS; keep those as *ordering hints* but bucket into the table so the score stays stable.

### 1.2 Findings density

For tool `t` on codebase slice with `KLOC` thousand lines of code:

```
raw_t = ( Σ_{f ∈ findings_t} w_f ) / KLOC
```

`KLOC` is computed once, deterministically, by the same loc counter for all tools (recommend `cloc --json` or `tokei --output json`; both are deterministic and language-aware). **Pin the loc tool version** — KLOC is the denominator and any drift moves every score.

### 1.3 Hill (saturating logistic) normalization — for findings density

```
score_t = 100 / ( 1 + (raw_t / d*)^k )
```

- `d*` = **reference density**: the density at which the tool scores 50. Calibrate per tool from a baseline scan of known-good code (see §6.1).
- `k` = **steepness** (default 1.0–1.5). Higher `k` = harsher near the reference point.

Properties: monotone decreasing, bounded in (0, 100], no hard cutoff, and *interpretable*: `raw = d*` → 50; `raw = 0` → 100; `raw = 3·d*` → ~10. This avoids the cliff behavior of pass/fail thresholds while still being fully deterministic.

Alternative simpler curve if you prefer linear: `score_t = 100 · max(0, 1 − raw_t / d_max)` with `d_max` = density that maps to 0. Hill is preferred because it never hits exactly 0 and degrades gracefully.

### 1.4 Threshold-curve normalization — for bounded metrics

For a metric `x` with a "bad" end `x_bad` and a "good" end `x_good`:

```
score_t = 100 · clamp( (x − x_bad) / (x_good − x_bad), 0, 1 )
```

where `x_good > x_bad` for "higher is better" metrics (coverage, mutation score, MI) and reversed for "lower is better" (max cyclomatic complexity, duplication %, a11y violation count). Optionally piecewise anchors for nonlinearity:

| Coverage | score |
|---|---|
| 0% | 0 |
| 50% | 40 |
| 80% | 80 |
| 90% | 95 |
| 100% | 100 |

Piecewise-linear interpolation between anchors is deterministic and easy to review.

### 1.5 Combining tools within a category

Weighted **geometric mean** (penalizes the worst tool; prevents dilution):

```
score_cat = exp( Σ_t α_t · ln( max(score_t, ε) ) )      with Σ α_t = 1, ε = 1
```

Weights `α_t` default to equal within a category and are set per tool in the manifest. Geometric mean means a category cannot be "saved" by good lint if SAST is failing.

### 1.6 Hard caps / gates (optional but recommended)

Deterministic overrides that match real-world policy:

- Any **critical** secret or critical CVE in a shipped dependency → cap category at ≤ 30.
- Any **critical** SAST finding with a published exploit → cap security at ≤ 40.
- Build/test failing → correctness category = 0 (binary gate), regardless of coverage.

Caps are applied *after* the geometric mean and are pure functions of the finding set.

### 1.7 Cross-language aggregation

```
score_cat(repo) = Σ_l ( KLOC_l / KLOC_total ) · score_cat,l
```

Weighted by language share so a 20-line Go helper doesn't outvote 200 KLOC of Python. Store per-language scores alongside the aggregate — that is also the hook for adding languages incrementally: an unfilled language column simply has weight 0 until tools are wired in.

### 1.8 Hybrid with the LLM reviewer

The deterministic score is the **anchor**, not the answer:

```
final = β · score_det + (1 − β) · score_llm
```

- `β` = confidence weight, derived from **analyzer coverage of the category** (how many of the category's expected tools ran successfully and produced parseable output) and from repo size. A category with no tooling → `β` small → lean on LLM; a category with strong tooling → `β` large.
- **Constrained deviation:** allow the LLM to move the score by at most ±X points unless it cites concrete file:line evidence that a deterministic tool missed (a real bug, an architectural smell no tool encodes). Log every deviation with its justification → auditable.
- **Cost control:** feed the LLM only (a) the deterministic findings above a severity floor and (b) a deterministic sample of unflagged files, instead of the whole repo.

---

## 2. Category × Language matrix

Legend for **Signal**: `F` = findings list (severity-weighted density), `M` = scalar metric (threshold curve). **Cost** is order-of-magnitude for a ~100 KLOC repo on CI hardware: `S` < 10 s, `M` 10 s–2 min, `L` > 2 min.

### 2.1 Security / SAST

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | False-positive notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **Semgrep** (CE/OSS) | Py, JS/TS, Go, Rust, Java, +30 | `pipx install semgrep==<ver>` or Docker by digest | `semgrep scan --config p/ci --json --json-output=out.json --sarif-output=out.sarif --metrics=off --disable-version-check .` | JSON, SARIF, text, junit-xml | Parse `results[]`: each has `check_id`, `extra.severity` (ERROR/WARNING/INFO), `extra.metadata.confidence`, `path`, `start.line`. `extra.metadata.precision` ∈ {very-high, high, medium, low} → use to down-weight. | M | Rule-dependent; `--config auto` pulls remote rules (non-deterministic) → **pin a rule commit/config file**. Generic/pattern rules FP more than taint rules. | docs.semgrep.dev |
| **CodeQL** | Py, JS/TS, Go, Java (+C/C++, C#, Ruby, Swift) | Download CLI bundle, pin release tag; DB build needs language toolchains | `codeql database create db --language=<lang> --command=<build>` then `codeql database analyze db <suite>.qls --format=sarif-latest --output=out.sarif --ram=... --threads=...` | SARIF, CSV | SARIF `runs[].results[]`: `ruleId`, `level` (`error`/`warning`/`note`), `properties.security-severity` (0–10 float when present). Map security-severity → weight bucket. | L | Low FP for security queries; needs a successful build (source must compile). Slow; run on schedule/nightly, not per-push. | docs.github.com/code-security/codeql-cli |
| **Bandit** | Python | `pip install bandit==<ver>` | `bandit -r . -f json -o bandit.json -c bandit.yaml --exit-zero` | JSON, SARIF (newer), CSV, XML | `results[]`: `test_id` (e.g. B301), `issue_severity` (LOW/MEDIUM/HIGH), `issue_confidence`. `metrics._totals.loc` gives LOC for a self-contained denominator. | S | Known noisy on `assert`, `subprocess`, `try/except/pass`; use `-ll` (medium+) and a `# nosec` baseline. | bandit.readthedocs.io |
| **gosec** | Go | `go install github.com/securego/gosec/v2/cmd/gosec@vX.Y.Z` | `gosec -fmt=json -out=gosec.json -no-fail ./...` (SARIF: `-fmt=sarif`) | JSON, SARIF, sonarqube, junit-xml | `Issues[]`: `severity` (LOW/MEDIUM/HIGH), `confidence`, `rule_id` (G101…). `Stats` gives files/lines/Nosec for denominator. | S | `G104` (unhandled error) and `G304` (file path) are common noise; suppress via `--exclude-rules` with justification tracked. | pkg.go.dev/github.com/securego/gosec |
| **gitleaks** | all (text/git) | Single Go binary; pin release + rules TOML | `gitleaks detect --source . --config .gitleaks.toml --report-format json --report-path gl.json --redact --exit-code 0` | JSON, SARIF | Array of findings: `RuleID`, `Entropy`, `File`, `Line`, `Fingerprint`. Named-vendor rules (aws-access-token) → high weight; `generic-api-key` (entropy) → low weight. | S | Entropy rules FP on fixtures/UUIDs/hashes. Use `Fingerprint` allowlist for reviewed-safe hits, never value-based allowlists. | github.com/gitleaks/gitleaks |
| **TruffleHog** | all (git/history, S3, etc.) | Binary / `install.sh`, pin version | `trufflehog git file://. --only-verified --json --no-update > th.json` | JSON-lines | Each line: `Verified` (bool), `DetectorName`, `Raw`. `--only-verified` makes it **network-dependent** → run as advisory or offline without `--only-verified`. | M | Very low FP *with* verification, but verification = live API calls = non-deterministic. Exclude from scored path or pin to `--no-verification` for determinism. | github.com/trufflesecurity/trufflehog |
| **Trivy** | all (deps, IaC, containers) | Binary / package, pin version; **pin DB** | `trivy fs --scanners vuln,secret,misconfig --format json --output trivy.json --severity HIGH,CRITICAL --exit-code 0 --skip-db-update --db-repository ... .` | JSON, SARIF, CycloneDX, SPDX, table | `Results[].Vulnerabilities[]`: `VulnerabilityID`, `Severity`, `PkgName`, `FixedVersion`, `CVSS`. `Results[].Misconfigurations[]` for IaC. | M | Depends on DB freshness; pin DB to make reproducible. `UNKNOWN` severity is common early — filter it. | trivy.dev |
| **Grype** | all (images, dirs, SBOMs) | Binary / brew / winget, pin version; pin DB | `grype dir:. -o json --file grype.json` (or `grype sbom:sbom.json -o sarif`) | JSON, SARIF, CycloneDX, table | `matches[]`: `vulnerability.severity`, `.id`, `.epss[].epss`, `.knownExploited`, `artifact.name`. Grype exposes a **RISK** score (0–10) combining CVSS+EPSS → excellent numeric signal. | M | Fewer FPs when `--fail-on` + fix-state filtering used. EOL-distro warnings. | oss.anchore.com |

**SAST composite signal:** weighted geometric mean of `score_semgrep`, `score_bandit`/`gosec` (per language), `score_codeql`, plus a **secrets sub-score** (gitleaks). Trivy/Grype overlap with §2.6 but their *secret* and *misconfig* scanners belong here.

---

### 2.2 Readability / Maintainability / Complexity

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **ruff** | Python | `pip install ruff==<ver>` | `ruff check --output-format=json --statistics .` | JSON, SARIF, json-lines, junit, github | JSON array: `code` (e.g. E501, F401), `message`, `filename`, `location.row`. Severity is **rule-code-derived** (no severity field) → maintain a code→weight map; `--statistics` gives per-rule counts directly. | S | Very low FP (largely style); disable noisy rules explicitly in `pyproject.toml`. | docs.astral.sh/ruff |
| **pylint** | Python | `pip install pylint==<ver>` | `pylint --output-format=json2 --recursive=y . > pylint.json` | JSON, text | JSON: `type` (convention/refactor/warning/error/fatal), `symbol`, `message-id`, `line`. Also emits a **0–10 score** in text mode (`rated at X/10`) → `x·10` is already a bounded metric. | S–M | Style-heavy; tune `.pylintrc`. The 0–10 score is useful as a ready-made metric. | pylint.readthedocs.io |
| **radon** | Python | `pip install radon==<ver>` | `radon cc -s -j . > cc.json` ; `radon mi -s -j . > mi.json` | JSON, XML, text | `cc`: per-block `complexity` (int), `rank` (A–F). Aggregate: **max CC**, mean CC, count of blocks > 10. `mi`: per-file Maintainability Index 0–100 (A/B/C). | S | MI is a heuristic composite (Halstead volume × CC × LLOC); treat as coarse. `--json` does **not** include the summary even with `-s` — compute aggregates yourself. | radon.readthedocs.io |
| **lizard** | Py, JS/TS, Go, Rust, Java, C/C++, +15 | `pip install lizard==<ver>` | `lizard -l python -C 10 -w .` / `lizard --csv .` | CSV, XML, HTML, text | CSV columns: `NLOC, CCN, token, PARAM, length, location, file, function, long_name, start, end`. **CCN per function** is the signal → max/mean CCN, count > threshold. | S | Language-agnostic, low FP; CCN calc is token-based, occasionally over/under-counts lambdas. Great polyglot baseline. | github.com/terryyin/lizard |
| **ESLint** | JS/TS | `npm i -D eslint@<ver>` | `eslint . -f json -o eslint.json` | JSON, SARIF (`@microsoft/eslint-formatter-sarif`), stylish | Array per file: `messages[]` with `ruleId`, `severity` (1 warn / 2 error), `line`. | S–M | Rule-set-dependent; `eslint:recommended` is low FP. Config drift is the main risk → commit config, hash it. | eslint.org |
| **typescript-eslint** | TS | `npm i -D typescript-eslint@<ver>` | via `eslint` config | JSON (same as ESLint) | Same extraction; `@typescript-eslint/*` rules add type-aware findings. Type-aware rules require `parserOptions.project` → slower. | M | Type-aware rules need `tsconfig`; FP moderate. | typescript-eslint.io |
| **golangci-lint** | Go | `go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@vX` | `golangci-lint run --output.json.path=gl.json --output.text.path=stdout --timeout 5m ./...` | JSON, SARIF, checkstyle, code-climate, junit, tab, html | JSON `Issues[]`: `FromLinter`, `Text`, `Severity` (`error`/`warning`), `Pos`. `--show-stats`/`--output.text` add per-linter counts. | M | Aggregates many linters → tune `.golangci.yml`; `govet`+`staticcheck`+`errcheck` are the high-value core. | golangci-lint.run |
| **clippy** | Rust | `rustup component add clippy` (pin toolchain) | `cargo clippy --workspace --all-targets --message-format=json -- -D warnings` | JSON-lines (rustc schema) | One JSON object per line; keep `reason=="compiler-message"`; fields `message.level` (error/warning/note/help), `message.code.code` (lint id), primary span `file_name`,`line_start`. | M | `clippy::pedantic`/`nursery` are noisy; default + `correctness` are low FP. `-D warnings` turns warnings into errors (affects exit code only). | doc.rust-lang.org/clippy |
| **PMD + CPD** | Java (PMD), many (CPD) | Download release / package; pin version | `pmd check -d src -R rulesets/java/quickstart.xml -f json -r pmd.json` ; `pmd cpd -d src --minimum-tokens 100 -f csv -r cpd.csv` | JSON, XML, CSV, sarif, text | PMD: `files[].violations[]` with `rule`, `priority` (1–5, 1 highest). `CyclomaticComplexity` rule reports methods ≥ 10 by default; `classReportLevel` default 80. CPD: `duplication` blocks with `lines`, `tokens`. | M | PMD priority map is your severity table. CPD is token-based (whitespace/comments ignored). | docs.pmd-code.org |
| **SonarQube / SonarCloud** | Py, JS/TS, Go, Java (+C/C++) | Server + `sonar-scanner`; **version-locked server** | `sonar-scanner` against a pinned server; or `sonar-scanner` CLI | JSON via Web API, SARIF-ish | Web API `/api/measures/component` returns numeric measures: `complexity`, `cognitive_complexity`, `code_smells`, `sqale_index`, `maintainability_rating` (A–E), `reliability_rating`. Excellent ready-made metrics but **heavy** and server stateful → determinism requires pinned server + same quality profile. | L | Server setup + quality profile drift is the reproducibility risk. Good as an *aggregator* rather than a raw signal. | docs.sonarsource.com |

**Composite:** max/mean CC (lizard or radon), duplication % (CPD/jscpd), weighted lint density, MI. Convert each to 0–100 via threshold curves, geometric-mean.

---

### 2.3 Performance

Performance is the hardest to make deterministic. **Rule: only benchmark-derived *relative regressions against a pinned baseline* enter the score; absolute timings do not.**

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP / determinism notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **hyperfine** | any CLI/process | package / cargo / binary, pin version | `hyperfine --warmup 3 --runs 10 --export-json hf.json 'cmd'` | JSON, CSV, Markdown | `results[].mean`, `.median`, `.stddev`, `.min`, `.max`, `.user`, `.system`. Signal: **ratio vs. pinned baseline** (`mean/baseline_mean`), not absolute. | M | Timing noise; require `--runs`, discard outliers, compare only on same CI runner class. | github.com/sharkdp/hyperfine |
| **pyperf** | Python | `pip install pyperf==<ver>` | `pyperf run -o perf.json bench.py` / `pyperf compare_to baseline.json --table` | JSON | `pyperf compare_to` yields per-benchmark mean ratio + confidence; `--fail` with a threshold is a deterministic gate. | M | Controls CPU frequency; still noisy on shared runners. Use dedicated runners. | pyperf.readthedocs.io |
| **pytest-benchmark** | Python | `pip install pytest-benchmark==<ver>` | `pytest --benchmark-json=bench.json` | JSON | `benchmarks[].stats` (`mean`,`median`,`min`,`max`,`stddev`) + `--benchmark-compare` regression detection. | M | Same noise caveats. | pytest-benchmark.readthedocs.io |
| **k6** | any (HTTP) | Binary / package, pin version | `k6 run --out json=k6.json script.js` ; `k6 run --summary-export=summary.json script.js` | JSON, CSV, summary JSON | `metrics.http_req_duration` (`avg`,`p(95)`,`p(99)`,`max`), `http_req_failed` rate, `iterations`, `vus`. Signal: p95/p99 latency and error-rate vs. thresholds. | M–L | Load tests need a stable environment; run in isolation. | grafana.com/docs/k6 |
| **vegeta** | any (HTTP) | `go install github.com/tsenart/vegeta/v12@vX` | `vegeta attack -rate=50 -duration=30s -targets=t.txt \| vegeta report -type=json > veg.json` | JSON, text, HDR histogram | Report JSON: `latencies` (`mean`,`p50`,`p95`,`p99`,`max`), `success`, `requests`, `rate`. | M | Rate-based; deterministic given fixed rate/duration and a pinned target. | github.com/tsenart/vegeta |
| **hey** | any (HTTP) | `go install github.com/rakyll/hey@latest` | `hey -n 5000 -c 50 -o csv URL` | text, CSV | `-o csv` per-request latency; summary has `Requests/sec`, `Average`, `P95`, `P99`. | S–M | Simpler than k6/vegeta; good smoke load. | github.com/rakyll/hey |
| **pprof** | Go (+others via profiles) | part of Go toolchain | `go test -bench=. -cpuprofile cpu.out` then `go tool pprof -top -nodecount=20 cpu.out` | text, protobuf, SVG | `pprof -top` lists hot functions with flat/cum %; `-traces`. Signal: **regression in top-N hot functions** or allocation count (`-benchmem` → `allocs/op`, `B/op`). | M | Profile of a benchmark, deterministic given same input. Compare `allocs/op`/`ns/op` from `go test -bench` output (stable-ish) rather than wall clock. | pkg.go.dev/runtime/pprof |
| **flamegraph** (`cargo-flamegraph` / `inferno`) | Rust, Go, C/C++, any perf | `cargo install flamegraph` | `cargo flamegraph --bench x` or `perf record` + `inferno-flamegraph` | SVG | Visual; **not a numeric signal** by itself. Use `cargo bench`/`perf stat` counters for numbers; flamegraph for human/LLM explanation only. | L | Non-deterministic rendering; keep out of the score. | github.com/flamegraph-rs/flamegraph |
| **JMH** | Java (JVM) | Maven/Gradle plugin, pin JMH version | `java -jar benchmarks.jar -rf json -rff jmh.json` | JSON, CSV, text | Per-benchmark: `primaryMetric.score` (ops/time), `.scoreError`, `.scoreUnit`, secondary metrics. Signal: score ratio vs. pinned baseline, with `scoreError` as noise band. | L | Properly warmed up → low variance; the gold standard for JVM microbenchmarks. | openjdk.org/projects/code-tools/jmh |
| **criterion.rs** | Rust | dev-dependency, pin version | `cargo bench -- --save-baseline main` then `cargo criterion --message-format=json` | JSON-lines, HTML, raw.json | `--message-format=json`: `reason=="benchmark-complete"`, `typical.estimate`, `mean`, `median`, `slope`, `change.mean.estimate` (%), `outliers`. `target/criterion/**/estimates.json` also parseable. **`change` is the regression signal.** | L | Bootstrap CIs; needs stable runner. `change` vs. saved baseline is exactly the deterministic gate you want. | criterion-rs.github.io |
| **Lighthouse** | web/JS frontends | `npm i -g lighthouse@<ver>` | `lighthouse URL --output=json --output-path=lh.json --chrome-flags="--headless"` | JSON, HTML | `categories.performance.score` (0–1), `categories.accessibility.score`, plus `audits.*.numericValue` (LCP, TBT, CLS, FCP, TTI). **Ready-made 0–1 scores.** | M–L | Needs a browser + stable server; run against a pinned build. | developer.chrome.com/docs/lighthouse |

**Composite:** geometric mean of (a) Lighthouse perf score if web, (b) benchmark-regression score (100 if no regression, degrading with `%` regression), (c) hot-path allocation counters. **If no benchmark baseline is pinned, the performance category must report `β`-low and defer to the LLM** — never score absolute wall-clock across machines.

---

### 2.4 Correctness / Testing

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **coverage.py** | Python | `pip install coverage==<ver>` | `coverage run -m pytest && coverage json -o cov.json --fail-under=80` | JSON, XML, LCOV | `totals.percent_covered`, `totals.percent_covered_display`, per-file. `--fail-under` exits 2 below threshold (deterministic gate). `coverage report --format=total` prints a single number. | M | Line vs branch coverage (`--branch`). Coverage % alone is gameable → pair with mutation. | coverage.readthedocs.io |
| **pytest** | Python | `pip install pytest==<ver>` | `pytest -q --junitxml=junit.xml --tb=short` | JUnit XML, text, `--json-report` | Pass/fail/skip/error counts from JUnit XML (`testsuite` attrs). Signal: pass rate, failing count (binary gate). | M | Flaky tests are the reproducibility enemy → pin `pytest-randomly` seed or disable it. | docs.pytest.org |
| **jest** | JS/TS | `npm i -D jest@<ver>` | `jest --json --outputFile=jest.json --coverage --coverageReporters=json-summary` | JSON, JUnit | `numPassedTests`, `numFailedTests`, `numTotalTests`, `testResults[]`. Coverage: `coverage-summary.json` → `total.lines.pct`. | M | Snapshots make tests brittle; treat snapshot churn as signal, not noise. | jestjs.io |
| **vitest** | JS/TS | `npm i -D vitest@<ver>` | `vitest run --reporter=json --outputFile=vitest.json --coverage` | JSON, JUnit | Similar shape; `testResults[].assertionResults[].status`. | M | Same as jest. | vitest.dev |
| **go test** | Go | toolchain | `go test -json ./... > gotest.json` ; coverage: `go test -coverprofile=cover.out -covermode=count ./...` then `go tool cover -func=cover.out` | JSON-lines, text | `-json`: events `action` ∈ {pass,fail,skip}, per-test. Coverage: `go tool cover -func` → `total: (statements) X%`. | M | Built-in, deterministic. | pkg.go.dev/cmd/go |
| **cargo test / tarpaulin** | Rust | toolchain / `cargo install cargo-tarpaulin` | `cargo test -- -Z unstable-options --format json` (nightly) ; `cargo tarpaulin --out json --out lcov --output-dir cov` | JSON, LCOV, XML | tarpaulin JSON: `summary.covered`, `summary.coverable`, `summary.percent`, plus per-file. Recent versions add summary coverage/covered/coverable to the JSON report. | M–L | tarpaulin is Linux-centric; on Windows/macOS prefer `llvm-cov` (`cargo llvm-cov --json`). | github.com/xd009642/tarpaulin |
| **JaCoCo** | Java | Maven/Gradle plugin, pin version | `mvn test jacoco:report` → `target/site/jacoco/jacoco.xml` (or `jacoco.csv`) | XML, CSV, HTML | XML `counter` elements (`INSTRUCTION`,`BRANCH`,`LINE`,`METHOD`,`CLASS`) with `missed`/`covered`. Coverage = covered/(missed+covered). | M | Standard, deterministic. | jacoco.org |
| **mutmut** | Python | `pip install mutmut==<ver>` | `mutmut run --paths-to-mutate src` then `mutmut results --json` | JSON, text | `statistics`: `total`, `killed`, `survived`, `timeout`, `suspicious`. Mutation score = killed / (total − equivalent). | L | Slow; scope to core modules. Equivalent mutants inflate the denominator → allow a skip list. | mutmut.readthedocs.io |
| **Stryker** | JS/TS (+C#/.NET, Scala) | `npm i -D @stryker-mutator/core@<ver>` | `npx stryker run` (config `stryker.conf.json`) | JSON, HTML, clear-text | `mutation.json`: `mutationScore` (0–100), per-file scores, `killed/survived/timeout/noCoverage`. `thresholds.{high,low,break}` gate the exit code (`break` → non-zero). | L | `coverageAnalysis: perTest` gives 3–5× speedup. | stryker-mutator.io |
| **go-mutesting** | Go | `go install github.com/zimmski/go-mutesting/cmd/go-mutesting@latest` | `go-mutesting ./...` | text (JSON via wrapper) | Parses killed/lived mutants from text; mutation score = killed/(killed+lived). Less mature than alternatives. | L | Text-only output is fragile → parse carefully or wrap. | github.com/zimmski/go-mutesting |
| **cargo-mutants** | Rust | `cargo install cargo-mutants` | `cargo mutants --json` ; writes `mutants.out/outcomes.json` | JSON | `outcomes.json` lists every mutant with outcome ∈ {caught, missed, unviable, timeout}. **Caught rate = caught/(caught+missed)**; `unviable` excluded, `timeout` flagged. Also `--list --json` for the mutant inventory. | L | Unviable mutants are inconclusive → excluded from denominator. Very clean JSON. | mutants.rs |
| **PIT (pitest)** | Java | Maven/Gradle plugin, pin version | `mvn org.pitest:pitest-maven:mutationCoverage` → `target/pit-reports/mutations.xml` | XML, HTML, CSV | `mutations.xml`: `<mutation status="KILLED|SURVIVED|NO_COVERAGE|TIMED_OUT|NON_VIABLE|RUN_ERROR">`. Mutation score = killed/(killed+survived) (exclude non-viable). `--mutationThreshold` gates build. | L | Needs good unit tests; scope via `targetClasses`/`targetTests`. | pitest.org |

**Composite:** coverage metric (threshold curve) × mutation score metric (threshold curve), with a **binary gate** for build/test failure → 0. Coverage alone is heavily gameable; mutation testing is the anti-gaming signal and should carry meaningful weight.

---

### 2.5 Architecture

Architecture tools encode *intended structure* as rules; the signal is **violations of declared rules** plus **cycle/instability metrics**.

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **import-linter** | Python | `pip install import-linter==<ver>` | `lint-imports --config pyproject.toml` (or `.importlinter`) | text, exit code | Reports `kept`/`broken` per contract (layers, forbidden, independence, acyclic-siblings, protected). Signal: broken-contract count (weighted by contract type) — deterministic integer. | S | FP only if the declared architecture is wrong; contracts are explicit → zero ambiguity. | import-linter.readthedocs.io |
| **madge** | JS/TS | `npm i -D madge@<ver>` | `madge --json --circular src > madge.json` ; `madge --image graph.svg src` | JSON, DOT, SVG | `--json` emits dependency graph; `--circular` emits array of cycles. Signal: **cycle count**, max cycle length, module count. | S–M | Needs a resolvable entry/tsconfig; `--extensions ts,tsx` for TS. | github.com/pahen/madge |
| **dependency-cruiser** | JS/TS | `npm i -D dependency-cruiser@<ver>` | `depcruise src --config .dependency-cruiser.js --output-type json --output-to depcruise.json` | JSON, DOT, Mermaid, D2, HTML | JSON: `modules[]` + `summary.violations[]` (each with rule `name`, `severity` ∈ error/warn/info). Signal: **violations by severity** + cycle detection rules. Baseline mode: `--output-type baseline` freezes known violations. | M | Rules are explicit → low FP. `recommended` config is a good start. | github.com/sverweij/dependency-cruiser |
| **jdeps** | Java | part of JDK | `jdeps -s -R --jdk-internals --multi-release base app.jar` ; `jdeps -dotoutput dot/ app.jar` | text, DOT | Text: `pkg -> pkg` lines. Signal: **count of JDK-internal API dependencies** (`--jdk-internals`), afferent/efferent coupling counts, package cycle detection (build the graph from DOT). | S–M | Text output needs parsing; DOT gives a clean graph. | docs.oracle.com/en/java/javase/.../jdeps.html |
| **ArchUnit** | Java | test-scope dependency, pin version | JUnit test with `ArchRule` (runs under `mvn test`) | test results (JUnit XML) | Rules are Java code; failures surface as test failures → parse JUnit XML. Signal: number of violated architecture rules. | M | Very explicit; zero FP by construction, but rules must be written. | archunit.org |
| **pydeps** | Python | `pip install pydeps==<ver>` | `pydeps --show-deps --no-show --json -o pydeps.json mypkg` | JSON, SVG, DOT | JSON dependency graph; compute cycles and coupling from it. Signal: cycle count, fan-in/fan-out. | S–M | Needs importable package; dynamic imports missed. | github.com/thebjorn/pydeps |

**Composite:** broken-contract/violation count (Hill-normalized by KLOC) + cycle count + coupling metrics. Architecture is mostly **rule-based and deterministic** — high `β` when rules exist, low `β` (LLM territory) when they don't.

---

### 2.6 Dependencies / Supply-chain

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **pip-audit** | Python | `pipx install pip-audit==<ver>` | `pip-audit -f json -o pipaudit.json --requirement requirements.txt` | JSON, CycloneDX, SARIF | `dependencies[].vulns[]`: `id` (GHSA/PYSEC/CVE), `fix_versions`, `aliases`. Signal: count by severity (severity via OSV/CVSS lookup — join on id). | M | Uses OSV/PyPI advisories; pin the advisory DB snapshot for determinism (`--disable-pip` + cache). | pypi.org/project/pip-audit |
| **npm audit** | JS/TS | npm (pin Node) | `npm audit --json > npm-audit.json` | JSON | `metadata.vulnerabilities` (`info`,`low`,`moderate`,`high`,`critical`), `vulnerabilities{}` per package. Signal: counts by severity. | S–M | Requires a lockfile; dev-dependency noise → `--omit=dev` or `--production`. | docs.npmjs.com/cli/commands/npm-audit |
| **osv-scanner** | Py, JS/TS, Go, Rust, Java, + | Binary / `go install github.com/google/osv-scanner/v2/cmd/osv-scanner@vX` | `osv-scanner scan source -r --format json . > osv.json` (SARIF: `--format sarif`) | JSON, SARIF, table, html | `results[].packages[].vulnerabilities[]`: `id`, `aliases`, and (with groups) severity. Signal: counts by severity/CVSS. Supports SBOM input (`--sbom`). | M | OSV DB freshness → pin. `--call-analysis` (Go/Rust) cuts FPs by checking reachability. | github.com/google/osv-scanner |
| **govulncheck** | Go | `go install golang.org/x/vuln/cmd/govulncheck@latest` | `govulncheck -json ./... > govulncheck.json` | JSON (streaming), text, SARIF | Streaming JSON: `config` message then `finding` messages with `osv`, `fixed_version`, `trace[]` (call stack). **Reachability-aware** → findings where the vulnerable symbol is actually called. Signal: count of *called* vulns (weight high) vs. merely *imported*. | M | Lower FP than module-level scanners because it does symbol-level call analysis. | pkg.go.dev/golang.org/x/vuln |
| **cargo-audit** | Rust | `cargo install cargo-audit` | `cargo audit --json > cargo-audit.json` | JSON | `vulnerabilities.list[]`: `advisory.id`, `advisory.severity`, `package.name/version`, `versions.patched`. Signal: counts by severity. | M | Uses RustSec DB → pin/offline (`--stale`, `--db`). | rustsec.org |
| **Syft** | all | Binary, pin version | `syft dir:. -o cyclonedx-json=syft.cdx.json -o spdx-json=syft.spdx.json` | CycloneDX, SPDX, Syft JSON | SBOM inventory (no vulnerabilities itself). Signal: **component count**, license inventory, presence/absence of SBOM (compliance). Feeds Grype/OSV. | S–M | Deterministic; the SBOM is the reproducibility anchor for the whole category. | github.com/anchore/syft |
| **CycloneDX / SPDX** | all | `cyclonedx-bom`, `spdx-sbom-generator`, or Syft/Trivy output | `cyclonedx-py -o bom.json` etc. | CycloneDX, SPDX | SBOM presence + completeness (all lockfiles covered). Signal: binary (SBOM present / complete) + component count. | S | Format-only; value comes from scanning the SBOM downstream. | cyclonedx.org / spdx.dev |
| **Dependabot** | all (GitHub) | GitHub App / config | `.github/dependabot.yml` | alerts via API | GitHub Security alerts API → counts by severity. Signal: **open alert counts** and **mean age of open alerts**. | S | Server-side; pin by snapshotting the alert set at scan time for determinism. | docs.github.com/code-security/dependabot |

**Composite:** weighted vuln counts by severity (from Trivy/Grype/OSV/govulncheck, deduped by advisory ID), plus **reachability weighting** (called > imported), plus SBOM completeness as a compliance gate.

**Deduplication is mandatory:** the same CVE appears in Trivy, Grype, npm audit, and OSV. Dedupe on the **set of alias IDs** (`CVE-…`, `GHSA-…`) before counting, or the score double-counts.

---

### 2.7 License / Compliance

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **ScanCode Toolkit** | all | `pip install scancode-toolkit==<ver>` | `scancode -clipeu --json-pp scan.json --license-score 90 .` | JSON, YAML, HTML, CycloneDX, SPDX | `files[].license_detections[]` with `license_expression`, `matches[].score` (0–100), `match_coverage`. Package-level: `packages[].declared_license_expression`. Signal: **count of copyleft/unknown licenses**, detection confidence. | L | Most accurate license engine (full-text diff vs. regex), but slow. `--license-score` raises the bar and cuts low-confidence matches. | github.com/nexb/scancode-toolkit |
| **licensee** | all | `gem install licensee` | `licensee detect .` / `licensee detect --json .` | JSON, text | Detects the repo's own license + confidence. Signal: license match confidence; feeds a policy check (allow/deny list). | S | Repo-level only (not per-file). | github.com/licensee/licensee |
| **reuse** | all | `pipx install reuse==<ver>` | `reuse lint` / `reuse lint --json` | JSON, plain (Markdown), lines | Checks REUSE spec compliance: bad/deprecated/missing/unused licenses, files without SPDX headers. **Exit 0 = compliant, 1 = non-compliant.** Signal: count of non-compliant files (from `--json`). | S–M | Header-based; false "missing" if headers aren't used. Deterministic and fast. | reuse.readthedocs.io |
| **FOSSA** | all | SaaS CLI (`fossa-cli`) | `fossa analyze` then `fossa test` | JSON via API | SaaS: dependency license + policy violations, `fossa test` exit code gates. Signal: policy-violation counts. | M | SaaS → network-dependent and account-stateful; snapshot results for determinism or keep advisory. | fossa.com |
| **pip-licenses** | Python | `pip install pip-licenses` | `pip-licenses --format=json --with-urls > licenses.json` | JSON, CSV, Markdown | Per-package license strings. Signal: count of packages under denied licenses (join against policy allow-list). | S | License string quality varies by package metadata. | pypi.org/project/pip-licenses |
| **license-checker** | JS/TS | `npm i -g license-checker` | `license-checker --json > licenses.json` | JSON | Per-package license + path. Signal: count under denied licenses. | S | Reads package metadata. | npmjs.com/package/license-checker |

**Composite:** policy-violation count (denied license in a shipped dependency → high weight; unknown → medium), plus REUSE/SPDX-header compliance rate. License policy is a **binary-ish gate** in practice: a single GPL/AGPL in a proprietary product is critical.

---

### 2.8 Documentation

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **pydocstyle** | Python | `pip install pydocstyle==<ver>` | `pydocstyle --add-ignore=D1 --count .` or via `ruff` rule set `D` | text, JSON (newer) | `--count` prints total violations. Via ruff `--statistics` gives per-rule counts. Signal: docstring violations per KLOC. | S | `D1` (missing docstrings) is noisy on private code; scope to public API. | pydocstyle.readthedocs.io |
| **interrogate** | Python | `pip install interrogate==<ver>` | `interrogate -vv --generate-badge . --fail-under 80` | text, JSON? (badge SVG) | Prints **docstring coverage %** (a ready-made 0–100 metric) and lists undocumented items. Signal: coverage %. | S | Coverage ≠ quality; pair with pydocstyle for style and LLM for substance. | interrogate.readthedocs.io |
| **eslint-plugin-jsdoc** | JS/TS | `npm i -D eslint-plugin-jsdoc@<ver>` | via eslint | JSON (ESLint) | Rules like `require-jsdoc`, `require-param` emit findings with `ruleId`, `severity`. | S | Requires jsdoc to be the convention; otherwise high FP → disable `require-jsdoc` and keep `require-param`. | github.com/gajus/eslint-plugin-jsdoc |
| **golint / godoclint** | Go | `go install golang.org/x/lint/golint@latest` (deprecated) / `golangci-lint` `godoclint` linter | via golangci-lint | JSON | Findings for missing/malformed doc comments. `golint` is deprecated; use `godoclint`/`revive` inside golangci-lint. | S | `golint` unmaintained → prefer golangci-lint. | pkg.go.dev/golang.org/x/lint |
| **cargo-doc** | Rust | `rustup component add rustdoc` | `cargo doc --no-deps` (warnings) ; `RUSTDOCFLAGS="-D warnings" cargo doc` | text | Rustdoc warnings: broken intra-doc links, missing docs (`#![warn(missing_docs)]`). Signal: warning count (rustc JSON via `--message-format=json`). | M | Only as good as `missing_docs` lints enabled. | doc.rust-lang.org/rustdoc |
| **Vale** | prose (Markdown/AsciiDoc/comments) | binary, pin version + styles | `vale --output=JSON . > vale.json` | JSON, text, SARIF | JSON: per-file `Alerts[]` with `Severity` (error/warning/suggestion), `Rule`, `Line`. Signal: weighted alert density in docs. | S–M | Style-guide-dependent; Google/Microsoft styles are opinionated. | vale.sh |
| **markdownlint** | Markdown | `npm i -g markdownlint-cli2` | `markdownlint-cli2 "**/*.md" --json` | JSON | Array of rule violations with `ruleNames`, `lineNumber`. Signal: violations per doc KLOC. | S | Mostly style; low weight. | github.com/DavidAnson/markdownlint-cli2 |

**Composite:** docstring/API coverage % (interrogate), docstring style density (pydocstyle/ruff-D), prose lint (Vale/markdownlint). Documentation *substance* (is the doc actually correct/useful?) remains LLM territory — deterministic tools only measure presence/shape. `β` should be low here.

---

### 2.9 Accessibility

| Tool | Languages | Install / pin | Invocation | Output | Signal extraction | Cost | FP notes | Docs |
|---|---|---|---|---|---|---|---|---|
| **axe-core CLI** | web (HTML/JS) | `npm i -g @axe-core/cli@<ver>` (needs a browser) | `axe URL --stdout --tags wcag2a,wcag2aa,wcag21aa,wcag22aa --exit` | JSON | `violations[]`: `id`, `impact` (critical/serious/moderate/minor), `description`, `nodes[]` (`target`, `failureSummary`). Also `passes[]`. Signal: counts by impact. | M | Rules ~100+, low FP by design (axe explicitly avoids likely-FPs). Needs a rendered page + pinned build. | github.com/dequelabs/axe-core-npm |
| **pa11y** | web | `npm i -g pa11y@<ver>` | `pa11y URL --standard WCAG2AA --reporter json > pa11y.json` | JSON, CSV, HTML, TSV, CLI | JSON array of issues with `type` (error/warning/notice), `code` (e.g. `WCAG2AA.Principle1...`), `selector`, `context`. `--threshold N` allows up to N issues before non-zero exit. | M | Default runner is HTML CodeSniffer; `--runner axe` uses axe-core. `WCAG2AA` covers 2.0/2.1; WCAG 2.2 needs `--runner axe`. | github.com/pa11y/pa11y |
| **pa11y-ci** | web (batch) | `npm i -g pa11y-ci` | `pa11y-ci --json > pa11yci.json` | JSON | Batch of URLs → aggregated issue counts. Signal: total violations across pages. | M | Good for whole-site scans. | github.com/pa11y/pa11y-ci |
| **Lighthouse (a11y)** | web | see §2.3 | `lighthouse URL --only-categories=accessibility --output=json` | JSON | `categories.accessibility.score` (0–1) → ×100. Ready-made metric. | M–L | Aggregated score hides individual rules; keep axe/pa11y for detail. | developer.chrome.com/docs/lighthouse |

**Composite:** axe/pa11y impact-weighted violation density (Hill-normalized per page) + Lighthouse a11y score (metric). Accessibility is deterministic *given a rendered page* — the reproducibility risk is the build under test; pin it.

---

### 2.10 Error-handling / Reliability

No single-purpose analyzer; this category is assembled from cross-cutting signals.

| Signal source | Languages | How to extract | Weight |
|---|---|---|---|
| **Lint rules for error handling** | Go (`errcheck`, `err113`, `nilerr`), Rust (`clippy::unwrap_used`, `expect_used`, `panic`), Java (`PMD` errorprone / `EmptyCatchBlock`), Python (`ruff` `BLE`/`TRY`/`B902`), JS/TS (`@typescript-eslint/no-floating-promises`, `no-misused-promises`) | Run the language linter with the error-handling rule group enabled; count findings by severity | High |
| **Swallowed exceptions / empty catch** | all | PMD `EmptyCatchBlock`; ruff `S110`/`TRY`; semgrep rules (e.g. `python.lang.best-practices.empty-except`); gosec `G104` | High |
| **Panic/unwrap density** | Rust | `cargo clippy -- -W clippy::unwrap_used -W clippy::expect_used` → count from JSON | High |
| **Error-path test coverage** | all | Coverage tools with branch coverage; low branch coverage on error paths = reliability risk | Medium |
| **Timeout/retry/backoff presence** | all | Semgrep custom rules or CodeQL queries | Medium |
| **Resource-leak rules** | Go (`bodyclose`, `sqlclosecheck`), Java (PMD `CloseResource`), Python (`SIM115`), Rust (RAII, low risk) | golangci-lint / PMD / ruff counts | Medium |

**Composite:** geometric mean of error-handling-rule density across the language linters + branch coverage on error paths. Reliability is a **linter-aggregation** category: reuse the §2.2 tool runs but select the error-handling rule subset, so it costs nothing extra if §2.2 already runs.

---

## 3. Coverage matrix (which tool covers which category × language)

`●●` strong / first-class · `●` adequate · `○` partial/community · `—` not applicable. This is the map for **incremental per-language rollout**: fill a cell, add the tool to the manifest, its weight goes from 0 to `α`.

| Category | Python | JS/TS | Go | Rust | Java |
|---|---|---|---|---|---|
| Security/SAST | ●● semgrep, bandit, codeql | ●● semgrep, codeql, eslint-security | ●● gosec, semgrep, codeql | ●● semgrep, clippy-security | ●● codeql, semgrep, PMD-security |
| Secrets | ●● gitleaks/trufflehog | ●● | ●● | ●● | ●● |
| Maintainability | ●● ruff, pylint, radon, lizard | ●● eslint, ts-eslint, lizard | ●● golangci-lint, lizard | ●● clippy, lizard | ●● PMD, CPD, lizard |
| Performance | ● pyperf, pytest-benchmark | ● k6, lighthouse | ●● go bench/pprof | ●● criterion | ●● JMH |
| Testing | ●● pytest, coverage.py, mutmut | ●● jest/vitest, stryker | ●● go test, go-mutesting | ●● cargo test, tarpaulin, cargo-mutants | ●● jacoco, PIT |
| Dependencies | ●● pip-audit, osv | ●● npm audit, osv | ●● govulncheck, osv | ●● cargo-audit, osv | ●● osv, Trivy |
| License | ●● scancode, reuse | ●● scancode, licensee | ●● scancode | ●● scancode | ●● scancode |
| Docs | ●● pydocstyle, interrogate | ●● eslint-plugin-jsdoc | ● golangci (godoclint) | ●● cargo-doc | ● PMD-comments |
| Accessibility | ○ (web frontends only) | ●● axe, pa11y, lighthouse | ○ | — | ○ |
| Architecture | ●● import-linter, pydeps | ●● madge, dependency-cruiser | ● (internal/ + go-arch rules) | ● (modularity lints) | ●● jdeps, ArchUnit |
| Error-handling | ●● ruff TRY/BLE, semgrep | ●● ts-eslint | ●● golangci errcheck | ●● clippy unwrap | ● PMD errorprone |

---

## 4. Parsing pipeline (concrete)

```
scan/
  manifest.json          # pinned tool versions, configs (sha256), DB versions, KLOC, loc-tool version
  raw/                   # untouched tool output (json/sarif/csv)
  findings.ndjson        # canonical, deduped: {tool, rule_id, severity, weight, file, line, category, lang}
  metrics.json           # canonical scalars: {coverage:.., mutation:.., mi:.., cc_max:.., lighthouse:.., ...}
  scores.json            # {category: {lang: score, tools: {...}}, aggregate: {...}}
```

1. **Run each tool** → `raw/`. Exit codes captured; a tool that fails to run is recorded as `status: "error"` (lowers `β`, never silently scores 100).
2. **Parse** into canonical findings and metrics (§2 tables give the exact fields).
3. **Dedupe** findings by `(tool-family, rule_id, file, line)` and, for vulnerabilities, by the **sorted alias-ID set**.
4. **Weight** via the severity table (§1.1).
5. **Density**: divide by KLOC from the pinned loc tool.
6. **Normalize** per tool: Hill for findings, threshold curve for metrics.
7. **Combine** per category with weighted geometric mean; apply caps/gates.
8. **Aggregate** across languages by KLOC weight.
9. **Emit** `scores.json` with a full breakdown so any number can be traced to findings.

Reference parser shapes (field paths) are in §2. Recommended glue language: Python (all analyzers emit JSON; `pyproject`/`requirements` already present in polyglot repos). Use `jq` for quick extraction and Python for the aggregation.

---

## 5. Normalization summary (the math in one place)

| Input kind | Formula | Parameters to calibrate |
|---|---|---|
| Findings density `raw_t` | `score = 100 / (1 + (raw_t/d*)^k)` | `d*` (50-point density), `k` (steepness) |
| Higher-is-better metric | `score = 100·clamp((x−x_bad)/(x_good−x_bad),0,1)` or piecewise anchors | `x_bad`, `x_good`, anchors |
| Lower-is-better metric | `score = 100·clamp((x_bad−x)/(x_bad−x_good),0,1)` | same |
| Within-category combine | `exp(Σ α_t·ln(max(score_t,ε)))` | `α_t`, `ε=1` |
| Gate/cap | `min(score, cap)` on trigger | cap values |
| Cross-language | `Σ_l (KLOC_l/KLOC)·score_l` | KLOC from pinned loc tool |
| Hybrid | `β·score_det + (1−β)·score_llm` | `β` from analyzer coverage |

**Why Hill over a threshold cliff:** a repo at 9.9 findings/KLOC and one at 10.1 must not differ by 40 points. Hill gives a continuous, defensible curve; the *gate* (hard cap for criticals) is the only step function, and it is explicit policy.

**Why geometric mean over arithmetic:** one broken security tool should not be rescued by five passing lint tools. Geometric mean makes the worst member dominate, which matches "a chain is as strong as its weakest link."

---

## 6. Determinism and reproducibility in CI

1. **Pin tool versions.** Exact versions in lockfiles (`package-lock.json`, `requirements.txt`, `go.mod` tool directives, `Cargo.lock`, Maven plugin versions). Container images referenced **by digest**, not tag.
2. **Pin rules/configs and hash them.** Semgrep config, CodeQL query pack, `.golangci.yml`, `pyproject.toml` ruff config, PMD ruleset, `.dependency-cruiser.js`, import-linter contracts, `stryker.conf.json`, mutmut config. Store `sha256` of each in `manifest.json`. A config change is a scored change → reviewable.
3. **Pin vulnerability/license databases.** Trivy `--skip-db-update` + pinned `--db-repository`; Grype `--db-auto-update=false` + imported DB; OSV offline snapshot; RustSec/`cargo-audit --db`; pip-audit cache. **The DB version goes in the manifest.**
4. **Offline the non-deterministic.** TruffleHog `--only-verified` (live API) and FOSSA (SaaS) are network/state-dependent → run as **advisory**, exclude from the scored path, or pin to a snapshot.
5. **Canonical ordering.** Sort findings by a stable key `(file, line, rule_id, tool)` before hashing/serializing. Never include timestamps, absolute paths, hostnames, or durations in the scored payload.
6. **Fixed inputs for dynamic tools.** Benchmarks: pinned input data, `--warmup`/`--runs`, dedicated runners, compare only ratios to a **committed baseline**. Mutation: seed and scope pinned. Property/fuzz tests: fixed seed.
7. **SARIF as the merge point.** Tools that emit SARIF converge into one ingest path → dedupe and weight once.
8. **Double-run assertion.** CI runs the pipeline twice on the same commit and asserts `scores.json` is byte-identical (after canonical ordering). Any drift fails the build — this is the strongest reproducibility guarantee and it catches flaky tools automatically.
9. **Manifest = the contract.** `score(commit, manifest) → score`. Changing a tool, rule, DB, or weight produces a *new* score lineage; store the manifest hash alongside the score.
10. **Baselines for ratchets.** Freeze a `baseline.json` per repo; the score can be reported as absolute **and** as delta-vs-baseline. Ratchet gates ("must not get worse") are deterministic and avoid the false precision of absolute thresholds on day one.

---

## 7. Calibrating the free parameters

The only judgment calls are `d*`, `k`, `x_bad`, `x_good`, `α_t`, and `β`. Calibrate once, deterministically:

1. **Baseline scan** a known-good and a known-bad revision (or the repo's own history: last release vs. current main).
2. For each findings tool, set `d*` = the density observed on the known-good revision, so known-good ≈ 50 and known-bad lands low. Set `k` from how sharply you want to punish.
3. For metrics, set `x_bad`/`x_good` from industry defaults: coverage `x_good=90`, `x_bad=0`; mutation `x_good=80`, `x_bad=0`; MI `x_good=85`, `x_bad=10`; max-CC `x_good=10`, `x_bad=50`.
4. `α_t`: start equal; reweight only with evidence (a tool's findings must be shown to correlate with real defects).
5. `β`: map analyzer-coverage to a weight, e.g. `β = min(1, tools_ran_and_parsed / tools_expected)` per category, floored so LLM always has some influence.

Record the calibration inputs and outputs in the manifest so a score is always reproducible *and* its parameters are auditable.

---

## 8. Gaps and limitations (be honest with the LLM)

- **Performance** cannot be scored deterministically across heterogeneous CI runners; only *relative regression vs. a pinned baseline on the same runner class* is meaningful. Absolute timings must not enter the score.
- **Documentation substance** (accuracy, usefulness) is not measurable by linters — only presence/shape. Low `β`; LLM must carry this.
- **Architecture** is only as good as the declared rules; without import-linter/dependency-cruiser/ArchUnit rules there is no deterministic signal, only LLM judgment.
- **Error-handling** has no single analyzer; it is an aggregation of linter rules, so its quality inherits the language linter's rule coverage.
- **Accessibility** requires a rendered, pinned build; SPAs with dynamic content may need axe-core inside Playwright rather than the static CLI.
- **Vulnerability scanners** disagree on severity and coverage; dedupe by alias set and pin the DB, or counts will drift between runs and between tools.
- **LLM gameability**: if the LLM sees the deterministic score, it may anchor to it. Either hide the number and give it only findings, or explicitly allow bounded deviation with evidence (§1.8).
- **Coverage gaming**: coverage % alone rewards trivial tests; mutation testing is the counterweight and must be weighted meaningfully where affordable.
- **Tool maturity varies**: go-mutesting (text-only output) and golint (deprecated) are weaker links; prefer golangci-lint `godoclint` and alternative mutation tooling where possible.

---

## Sources

- Semgrep CLI output formats — https://docs.semgrep.dev/getting-started/cli ; https://docs.semgrep.dev/customize-semgrep-ce
- CodeQL CLI `database analyze` (SARIF/CSV) — https://docs.github.com/en/code-security/codeql-cli/codeql-cli-manual/database-analyze ; SARIF output — https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli/sarif-output
- Bandit JSON formatter & man page — https://bandit.readthedocs.io/en/latest/formatters/json.html ; https://bandit.readthedocs.io/en/latest/man/bandit.html
- gosec usage & output formats — https://pkg.go.dev/github.com/securego/gosec/v2
- gitleaks / TruffleHog secret scanning — https://github.com/gitleaks/gitleaks ; https://github.com/trufflesecurity/trufflehog
- Trivy filesystem CLI & formats — https://trivy.dev/docs/v0.53/guide/references/configuration/cli/trivy_filesystem
- Grype output formats & interpreting results — https://oss.anchore.com/docs/guides/vulnerability/ ; https://oss.anchore.com/docs/guides/vulnerability/getting-started
- Radon command-line usage (cc/mi/json) — https://radon.readthedocs.io/en/latest/commandline.html ; https://radon.readthedocs.io/en/latest/api.html
- Lizard CSV output format — https://github.com/terryyin/lizard ; https://deepwiki.com/terryyin/lizard/5.1-csv-output-format
- golangci-lint output configuration & CLI — https://golangci-lint.run/docs/configuration/cli/ ; https://golangci-lint.run/docs/configuration/file/
- Clippy JSON diagnostics — https://doc.rust-lang.org/clippy ; rustc JSON message format (community parse example) — https://docs.rs/betterhook/latest/src/betterhook/builtins/clippy.rs.html
- PMD rulesets, CyclomaticComplexity, CPD report formats — https://docs.pmd-code.org/pmd-doc-7.27.0/pmd_userdocs_cpd_report_formats.html ; https://pmd.github.io/pmd/pmd_rules_java_design.html ; https://docs.pmd-code.org/pmd-doc-7.23.0/pmd_userdocs_configuring_rules.html
- Ruff JSON output & statistics — https://latchkey.dev/learn/command-reference/ruff-output-format-json ; https://docs.astral.sh/ruff
- coverage.py json/report/`--fail-under` — https://coverage.readthedocs.io/en/latest/commands/cmd_json.html ; https://coverage.readthedocs.io/en/latest/commands/cmd_reporting.html
- cargo-tarpaulin flags & JSON output — https://github.com/xd009642/tarpaulin ; https://docs.rs/crate/cargo-tarpaulin/latest
- cargo-mutants outcomes & JSON — https://mutants.rs/using-results.html ; https://mutants.rs/mutants-out.html ; https://mutants.rs/list.html
- Stryker thresholds & reporters — https://stryker-mutator.io (config/threshold semantics as documented across the Stryker handbook)
- OSV-Scanner JSON/SARIF output — https://github.com/google/osv-scanner/blob/main/docs/output.md ; https://pkg.go.dev/github.com/google/osv-scanner/v2
- govulncheck JSON stream — https://pkg.go.dev/golang.org/x/vuln/internal/govulncheck
- ScanCode Toolkit — https://github.com/nexb/scancode-toolkit ; license detection updates — https://scancode-toolkit.readthedocs.io/en/latest/explanation/scancode-license-detection-updates.html ; configuring scans — https://scancode-toolkit.readthedocs.io/en/latest/tutorials/configuring-scan-detection.html
- REUSE `reuse lint` (JSON, exit codes) — https://reuse.readthedocs.io/en/stable/man/reuse-lint.html ; https://reuse.readthedocs.io/en/stable/readme.html
- import-linter contract types & layers — https://import-linter.readthedocs.io/en/stable/contract_types/ ; https://import-linter.readthedocs.io/en/stable/contract_types/layers/
- dependency-cruiser rules reference & JSON — https://github.com/sverweij/dependency-cruiser/blob/main/doc/rules-reference.md
- jdeps command — https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html ; https://dev.java/learn/jvm/tools/core/jdeps
- axe-core CLI / pa11y — https://github.com/dequelabs/axe-core-npm ; https://github.com/pa11y/pa11y ; https://github.com/pa11y/pa11y-ci
- Lighthouse — https://developer.chrome.com/docs/lighthouse
- Criterion.rs JSON message format & output — https://criterion-rs.github.io/book/cargo_criterion/external_tools.html ; https://bheisler.github.io/criterion.rs/book/user_guide/command_line_output.html
- hyperfine — https://github.com/sharkdp/hyperfine ; k6 — https://grafana.com/docs/k6 ; vegeta — https://github.com/tsenart/vegeta ; hey — https://github.com/rakyll/hey ; JMH — https://openjdk.org/projects/code-tools/jmh ; pyperf — https://pyperf.readthedocs.io ; pytest-benchmark — https://pytest-benchmark.readthedocs.io
- Syft / Grype SBOM + vuln pipeline — https://github.com/anchore/syft
- SonarQube measures API — https://docs.sonarsource.com
