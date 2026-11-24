"""The communication and dependency rules are repository artifacts, not prose."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dependabot_checks_actions_and_python_weekly() -> None:
    text = read(".github/dependabot.yml")
    assert 'package-ecosystem: "github-actions"' in text
    assert 'package-ecosystem: "pip"' in text
    assert text.count('interval: "weekly"') == 2


def test_the_nix_dependency_workflow_is_weekly_and_opens_a_pr() -> None:
    text = read(".github/workflows/dependencies.yml")
    assert 'cron: "0 6 * * 1"' in text
    assert "nix flake update" in text
    assert "gh pr create" in text
    assert "auto_merge" not in text.lower()
    assert "gh pr merge" not in text.lower()


def test_agents_makes_the_openspec_change_the_brief() -> None:
    text = read("AGENTS.md")
    assert "openspec/changes/" in text
    assert "subagent" in text.lower()
    assert "chat is a short pointer" in text.lower()


def test_the_review_action_defaults_to_auto_sampling() -> None:
    text = read(".github/actions/council/action.yml")
    samples = text.split("  samples:", 1)[1].split("  context-depth:", 1)[0]
    assert 'default: ""' in samples
    assert 'if [ -n "$SAMPLES" ]; then args+=(--samples "$SAMPLES"); fi' in text
    assert '--samples "${{ inputs.samples }}"' not in text


def test_the_review_action_exposes_strict_proofs() -> None:
    text = read(".github/actions/council/action.yml")
    assert "require-executed-proofs:" in text
    assert "REQUIRE_EXECUTED: ${{ inputs.require-executed-proofs }}" in text
    assert ('if [ "$REQUIRE_EXECUTED" = "true" ]; then '
            'args+=(--require-executed-proofs); fi') in text


def test_the_review_workflow_defaults_to_auto_sampling() -> None:
    text = read(".github/workflows/council.yml")
    samples = text.split("      samples:", 1)[1].split("      time-budget:", 1)[0]
    assert 'default: ""' in samples


def test_the_gate_runs_x86_64_and_documents_how_to_add_arm() -> None:
    """One gated system, with the arm leg named and one edit away."""
    gate = read(".github/workflows/gate.yml")
    assert "system: [ubuntu-24.04]" in gate
    assert "ubuntu-24.04-arm" in gate
    assert "matrix:" in gate
    flake = read("flake.nix")
    assert '"x86_64-linux"' in flake
    assert '"aarch64-linux"' in flake


def test_the_review_action_exposes_the_single_sample_opt_in() -> None:
    text = read(".github/actions/council/action.yml")
    assert "allow-single-sample:" in text
    assert "ALLOW_SINGLE_SAMPLE" in text
    assert 'if [ "$ALLOW_SINGLE_SAMPLE" = "true" ] && [ "$SAMPLES" = "1" ]; then' in text



def test_the_review_action_manifest_is_valid_yaml() -> None:
    data = yaml.safe_load(read(".github/actions/council/action.yml"))
    assert isinstance(data, dict)
    assert data["runs"]["using"] == "composite"
    assert data["inputs"]["samples"]["default"] == ""


def test_the_review_action_passes_inputs_as_data() -> None:
    data = yaml.safe_load(read(".github/actions/council/action.yml"))
    for index, step in enumerate(data["runs"]["steps"]):
        script = step.get("run", "")
        assert "${{ inputs." not in script, f"step {index} interpolates an input into Bash"


def test_the_review_action_exposes_the_rule_change_opt_in() -> None:
    text = read(".github/actions/council/action.yml")
    assert "allow-rules-change:" in text
    assert "ALLOW_RULES_CHANGE" in text
    assert 'args+=(--allow-rules-change)' in text
