## ADDED Requirements

### Requirement: The ambient model is the baseline

The selector SHALL treat the model of the active agent profile as the baseline for every task, and SHALL record how that baseline was resolved.

#### Scenario: A task starts with no explicit model

- **WHEN** the selector routes a task and no baseline override is supplied
- **THEN** it records the active profile's model as the baseline and does not substitute a hardcoded default

#### Scenario: No baseline can be resolved

- **WHEN** the selector cannot resolve a baseline from a flag, the environment or the active profile
- **THEN** it refuses to route and names the missing input

### Requirement: A task is routed only with an acceptance predicate

The selector SHALL refuse to route a task that has no observable acceptance predicate.

#### Scenario: A task has no predicate

- **WHEN** a task is submitted for routing without a scenario, test command or gate
- **THEN** the selector returns `needs-scoping`, names the missing predicate, and makes no model call

### Requirement: Escalation requires recorded failure

The selector SHALL escalate a task only after its predicate has failed, and SHALL attach the failure evidence to the escalated attempt.

#### Scenario: A task passes on the baseline

- **WHEN** the baseline attempt satisfies the task's predicate
- **THEN** no higher tier is invoked and the result is recorded as passed on the baseline

#### Scenario: A task fails repeatedly

- **WHEN** a task fails its predicate after the bounded retry
- **THEN** the next tier is invoked with the failed predicate and the attempts attached

### Requirement: Stale market data is provisional

The selector SHALL mark reports provisional and refuse profile writes when the market snapshot is older than 48 hours, and SHALL refuse ranking when it is older than 7 days.

#### Scenario: The snapshot is three days old

- **WHEN** a report is generated from a snapshot between 48 hours and 7 days old
- **THEN** the report is marked provisional, profile writes are refused, and the session may continue

#### Scenario: The snapshot is eight days old

- **WHEN** a report would be generated from a snapshot older than 7 days
- **THEN** ranking is refused until a refresh or an explicit accept-stale is supplied

### Requirement: Report provenance is explicit

Every report SHALL state when it was generated, which provider supplied the data, how old the snapshot is, and which price basis each cost uses.

#### Scenario: A report is rendered

- **WHEN** any report is produced
- **THEN** it carries the generation timestamp, the provider, the snapshot age and a named price basis on every cost table

### Requirement: Live best is the headline and seven-day realised is the budget

The report SHALL use the live best offer for the available-now cost and the seven-day realised average for the monthly budget.

#### Scenario: A cost table is rendered

- **WHEN** a cost table shows a per-task or monthly figure
- **THEN** the headline uses the live best and the budget column uses the seven-day realised, each labelled in the column header

### Requirement: Provider discovery is not hardcoded

The selector SHALL select a provider adapter from configuration or the active endpoint, and SHALL fall back to a generic adapter when no registered adapter matches.

#### Scenario: The active endpoint matches a registered provider

- **WHEN** the active profile's base URL matches a registered adapter
- **THEN** that adapter is used and its capabilities are recorded in the snapshot

#### Scenario: The active endpoint is unknown

- **WHEN** no registered adapter matches the active base URL
- **THEN** the generic adapter is used and the record states that discount data is unavailable

### Requirement: Calibration separates totals from percentiles

Calibration SHALL record monthly totals, per-session percentiles, and per-call percentiles, and SHALL mark a role with no measured data as uncalibrated.

#### Scenario: Calibration runs over measured sessions

- **WHEN** calibration completes for a profile
- **THEN** it writes the monthly total, the per-session P50 and P90, and the per-call P50 and P90 with the sample size and window

#### Scenario: A role has no measured sessions

- **WHEN** calibration finds no sessions for a role
- **THEN** that role is marked uncalibrated and the report labels its numbers as illustrative

### Requirement: Profile emission preserves unrelated configuration

Emitting a profile SHALL change only the model, the matching provider entry and the optional reasoning setting, and SHALL preserve every other key, comment and persona file.

#### Scenario: A profile is emitted

- **WHEN** the selector writes a profile
- **THEN** a backup and a unified diff are produced, only the selected keys change, and the write is atomic

#### Scenario: The target profile does not exist

- **WHEN** a recommended profile is absent and the create flag was not supplied
- **THEN** no profile is created and the selector prints the command that would create it
