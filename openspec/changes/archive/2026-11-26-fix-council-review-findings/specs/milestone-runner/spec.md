# Spec Delta

## ADDED Requirements

### Requirement: Acceptance predicates run under the guarded PATH

A task predicate MUST run with the same PATH shim as the worker, so a predicate
cannot commit, push, or change a profile after the worker was refused.

#### Scenario: A predicate attempts a commit

- **WHEN** a predicate runs `git commit` through the task's PATH
- **THEN** the shim refuses the commit and the predicate fails

#### Scenario: A predicate runs an ordinary command

- **WHEN** a predicate runs a command that is not a guarded operation
- **THEN** the command runs normally and its exit status decides the task

### Requirement: Every listed predicate is kept

The task parser MUST preserve every command in a verify list, including a mix of
quoted and unquoted commands, and MUST NOT treat a `#` inside a quoted value as
the start of a comment.

#### Scenario: A verify list mixes quoting styles

- **WHEN** a routing entry lists `["test -f a", test -f b]`
- **THEN** both commands are present in the task and both run before the tick

#### Scenario: A predicate contains a quoted hash

- **WHEN** a verify command contains `#` inside quotes
- **THEN** the parser keeps the hash and the full command reaches the predicate shell