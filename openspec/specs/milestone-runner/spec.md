# milestone-runner Specification

## Purpose
Turns an OpenSpec change into executed, evidenced tasks: one prompt per task from the
change, required `collab/<task>.md` evidence, a predicate before the tick, and a PATH shim
that stops before a commit, a push or a profile change.

## Requirements

### Requirement: The runner uses the OpenSpec change as the brief

The runner MUST read the change, its tasks and its routing map, and MUST NOT
substitute a competing prose brief.

#### Scenario: A task is dispatched

- **WHEN** the runner dispatches a task
- **THEN** the prompt names the change and the task id and the worker writes `collab/<task>.md`

### Requirement: The runner stops before irreversible actions

The runner MAY read, run tests and write workspace files without approval, and
MUST stop before a commit, a push or a profile change.

#### Scenario: A task passes

- **WHEN** a task's predicate passes
- **THEN** the runner records the evidence and ticks the task, and does not commit or push

#### Scenario: A profile change is required

- **WHEN** a worker attempts a profile change
- **THEN** the shim refuses it, the task is not accepted, and the owner command is printed

### Requirement: A task is complete only after its predicate passes

The runner MUST run the task's acceptance predicate and MUST tick the task only
after it passes.

#### Scenario: A predicate fails

- **WHEN** a task's predicate fails
- **THEN** the task remains unticked, the failure is recorded, and the run stops

### Requirement: Every task records evidence

The runner MUST require a `collab/<task>.md` evidence file before it runs the
predicate.

#### Scenario: Evidence is missing

- **WHEN** a worker returns without `collab/<task>.md`
- **THEN** the task is not accepted and the run stops

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
