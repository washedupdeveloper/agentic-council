# build-scope Specification

## Purpose

Which files a check is allowed to see. Every check declares the subtrees its command
opens, so an edit outside that declaration leaves the derivation unchanged and Nix serves
it from the store; a scope narrower than what the command reads fails the gate instead of
passing while it read less. The mutation campaign is bounded the same way: its scheduling
may change, what it proves may not.

## Requirements

### Requirement: A check's input is a superset of what it reads

Every check MUST declare the subtrees its command opens, and that declaration MUST
include every path the command reads. An edit outside a check's declaration MUST
leave its derivation unchanged.

#### Scenario: An edit outside a check's inputs

- **WHEN** a file is edited that a check does not read
- **THEN** that check's derivation is unchanged and Nix substitutes it from the store

#### Scenario: A scope omits a path the command reads

- **WHEN** a scope list omits a path its check opens
- **THEN** the gate fails, naming the missing path, before the check can pass blind

#### Scenario: A scope names a path that is not there

- **WHEN** a scope list names a path that does not exist
- **THEN** evaluation fails and names it

#### Scenario: A check runs the suite

- **WHEN** a check's command executes pytest or the claims registry
- **THEN** its scope is the suite scope, never a narrower one

### Requirement: The mutation campaign proves the same thing faster

Every mutation in the registry MUST be scored against the full suite, and the
campaign MUST fail when any mutation survives. Concurrency MAY be used and MUST
NOT change the verdict.

#### Scenario: A mutation survives

- **WHEN** a mutation does not break the suite
- **THEN** the campaign fails and names it

#### Scenario: The campaign runs concurrently

- **WHEN** the campaign scores its mutants across a pool of workers
- **THEN** every mutant is still scored against the full suite and the verdict
  equals the serial campaign's
