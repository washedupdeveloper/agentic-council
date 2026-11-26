# Design

## The decision

Gate one system; keep the other declared.

| Option | Cost | Verdict |
|---|---|---|
| Gate both systems | Two full gate runs per push | Rejected — the arm leg has no failure history to justify it |
| Remove `aarch64-linux` from the flake | One run, but the package no longer evaluates for arm | Rejected — a Pi consumer breaks, and a declared platform is a promise |
| Gate one, declare both, name the switch | One run, arm still builds on demand | **Adopted** |

## Why the comment is load-bearing

A matrix of one looks like an oversight, so the next reader either re-adds a leg
to be safe or deletes the leftover wording. Both are wrong. The comment says
which entry to add and states that nothing else changes, which turns a judgement
call back into an edit.

## Why a test asserts the pointer

The governance test previously asserted `"ubuntu-24.04-arm" in gate`. Deleting
the arm leg naively would have left that assertion vacuous or failing. The test
now asserts the matrix holds exactly `ubuntu-24.04` **and** that the arm label is
still named, so the pointer cannot be dropped while tidying up.

## What is not claimed

No run tests arm. The flake evaluates it, which is what `systems` means, and the
gate's own name says `x86_64-linux` so no reader mistakes green for two systems.

