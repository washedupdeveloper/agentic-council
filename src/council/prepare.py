"""Resolve a change into the evidence a review will use.

This is the effect shell around the pure request and prompt decisions: it reads
git, the repository configuration, the baseline, the prompt and caller-supplied
references. It writes nothing; `run` owns the run directory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .agents import AgentOptions, resolve
from .base import resolve_base
from .baseline import load as load_baseline
from .baseline import load_at as load_baseline_at
from .domain.changes import file_sections
from .config import CONFIG_NAME
from .config import load as load_config
from .domain.config import Config, ConfigError, parse as parse_config
from .domain.baseline import Baseline
from .domain.scope import Scope, ScopeError
from .planning import Prepared, prompt_for, reader, rules_block
from .domain.prompt import PromptError, instrument_digest
from .reference import FetchError, fetch
from .repo import ReviewError, diff, output
from .repo import root as repo_root
from .request import ReviewRequest


def default_prompt() -> Path:
    """The instrument ships with the tool.

    It is deliberately not read from the repository under review: a prompt
    supplied by the code being judged could ask the reviewer to report nothing,
    and the verdict would look exactly like a clean change.
    """
    return Path(__file__).parent / "prompts" / "reviewer.md"


def _load_baseline(request: ReviewRequest, root: Path, base: str) -> Baseline | None:
    """Load the policy file before the expensive work; CI reads the base blob."""
    if request.baseline is None:
        return None
    if request.baseline_from_base:
        return load_baseline_at(root, base, str(request.baseline))
    path = request.baseline if request.baseline.is_absolute() else root / request.baseline
    return load_baseline(path)


def _baseline_changed(request: ReviewRequest, patch: str) -> bool:
    """Whether the committed baseline is itself part of the reviewed diff."""
    if request.baseline is None or not request.baseline_from_base:
        return False
    rel = str(request.baseline).replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return any(section.path == rel for section in file_sections(patch))


def _staged_config(root: Path) -> Config | None:
    """The index copy of council.toml, so a staged review judges its own rules."""
    rel = CONFIG_NAME
    try:
        text = output(root, "show", f":{rel}")
    except ReviewError:
        return None
    try:
        return parse_config(text, name=rel)
    except ConfigError as exc:
        raise ReviewError(f"the staged {rel} is not usable: {exc}") from exc


def prepare(request: ReviewRequest) -> Prepared:
    """Resolve the change and build the prompt, writing nothing.

    This is an application step, not a pure decision: it reads git, the
    repository configuration, the baseline, the prompt and any caller-supplied
    references. It loads the cheap policy inputs and validates the change and
    prompt before fetching references, so a cheap failure never pays for a
    network call.
    """
    root = repo_root(request.repo)
    try:
        request.validate()
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
    if request.staged:
        staged_config = _staged_config(root)
        config = staged_config if staged_config is not None else Config()
    else:
        config = load_config(root / CONFIG_NAME)
    try:
        scope = Scope.create(request.include, request.exclude)
    except ScopeError as exc:
        raise ReviewError(str(exc)) from exc
    base = resolve_base(root, request.base)
    baseline = _load_baseline(request, root, base)
    head = output(root, "rev-parse", "HEAD").strip()
    change = diff(root, base, staged=request.staged)
    if _baseline_changed(request, change.patch) and not request.allow_baseline_change:
        raise ReviewError(
            "the baseline file is changed in this diff; refusing to use a "
            "baseline the change itself can edit (use --allow-baseline-change "
            "only for a deliberate maintenance change)")
    rule_docs = {rule.doc for rule in config.rules}
    changed_docs = {section.path for section in file_sections(change.patch)}
    protected = set(rule_docs & changed_docs)
    if CONFIG_NAME in changed_docs:
        protected.add(CONFIG_NAME)
    if protected and not request.allow_rules_change:
        raise ReviewError(
            "the change edits the rule configuration or governing rule document(s): "
            + ", ".join(sorted(protected))
            + "; refusing to use rules the change itself can rewrite "
              "(use --allow-rules-change only for a deliberate maintenance change)")
    # `git` decodes with surrogateescape so a non-UTF-8 path stays readable; a
    # non-UTF-8 *content* byte becomes a lone surrogate, which cannot be encoded
    # into the prompt. Replace those bytes once, here, so the prompt is valid.
    patch = change.patch.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    if scope.includes or scope.excludes:
        patch, scope_ignored = scope.filter_patch(patch)
    else:
        scope_ignored = ()
    diff_sha256 = hashlib.sha256(patch.encode("utf-8")).hexdigest()

    if not patch.strip():
        if scope_ignored:
            names = ", ".join(item.path for item in scope_ignored[:5])
            more = f", +{len(scope_ignored) - 5} more" if len(scope_ignored) > 5 else ""
            raise ReviewError(
                f"the change has no reviewable text in scope; ignored "
                f"{len(scope_ignored)} file(s): {names}{more}")
        if change.skipped:
            names = ", ".join(item.path for item in change.skipped[:5])
            more = f", +{len(change.skipped) - 5} more" if len(change.skipped) > 5 else ""
            raise ReviewError(
                f"the change has no reviewable text; skipped {len(change.skipped)} "
                f"file(s): {names}{more}")
        raise ReviewError("the change is empty: base and head are the same")

    prompt_file = request.prompt if request.prompt is not None else default_prompt()
    try:
        if not prompt_file.is_file():
            raise ReviewError(f"no reviewer prompt at {prompt_file}: a review needs an instrument")
        template = prompt_file.read_text(encoding="utf-8")
    except ReviewError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise ReviewError(f"cannot read the reviewer prompt at {prompt_file}: {exc}") from exc
    try:
        adapter = resolve(request.agent)
        options = AgentOptions(binary=request.reviewer or adapter.default_binary,
                               profile=request.profile,
                               reasoning=request.reasoning, stream=request.stream,
                               idle_timeout=request.idle_timeout,
                               sandbox=request.sandbox)
        identity = adapter.identity(options)
    except ValueError as exc:
        raise ReviewError(str(exc)) from exc
    digest = instrument_digest(template, agent=request.agent, profile=request.profile,
                               agent_fingerprint=identity.sha256 or None,
                               reasoning=request.reasoning)

    try:
        references = tuple(fetch(url) for url in request.context_urls)
    except FetchError as exc:
        raise ReviewError(str(exc)) from exc

    changed = tuple(section.path for section in file_sections(patch))
    rule_reader = reader(root)
    if request.staged:
        def staged_reader(rel: str) -> str | None:
            try:
                index = output(root, "ls-files", "-s", "--", rel).strip()
                if index.startswith("120000"):
                    return None
                return output(root, "show", f":{rel}")
            except ReviewError:
                return None
        rule_reader = staged_reader
    try:
        rules_text, rules = rules_block(root, config.rules, changed, read=rule_reader)
    except PromptError as exc:
        raise ReviewError(f"the reviewer prompt is not usable: {exc}") from exc

    try:
        fitted = prompt_for(template, base, patch, root, request.context_depth,
                            references, rules_text)
    except PromptError as exc:
        raise ReviewError(f"the reviewer prompt is not usable: {exc}") from exc
    prompt_bytes = fitted.bytes
    sliced = prompt_bytes > request.max_prompt_bytes and not request.allow_large_prompt
    return Prepared(root, config, baseline, base, head, patch, change.skipped,
                    scope_ignored, references, prompt_file, template, digest,
                    fitted.prompt, prompt_bytes, sliced, fitted.context, diff_sha256,
                    identity.source, identity.sha256,
                    agent=request.agent, agent_config=identity.source,
                    agent_config_sha256=identity.sha256, reviewer=options.binary,
                    rules=rules, rules_text=rules_text)
