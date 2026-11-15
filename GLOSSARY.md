# Glossary

One meaning per term. If code and prose disagree, the glossary is wrong until the
code changes; a second name for the same thing is a defect.

| Term | Meaning |
|---|---|
| **Review** | One request to judge one change. It ends in exactly one verdict and, unless planned or ephemeral, one run directory. |
| **Change** | The text between a base revision and a head revision, plus the files the tool could not include. A change is not a commit range in the domain; it is the diff the reviewer sees. |
| **Base / head** | The revisions that bound the change. `head` is the revision the review describes; `base` is the merge base the caller asked for. |
| **Unit** | One prompt-sized slice of a change. A unit exists only when the full prompt exceeds the budget; every unit is either reviewed or named as unreviewed. |
| **Window** | A unit that is a line range of one hunk rather than a whole file: the only way to review a file too large to send. Windows are disjoint, taken at depth 0, and cost one sample each. |
| **Sample** | One reviewer answer to one prompt. A sample can fail; a failed sample is evidence of missing evidence, never a silent omission. |
| **Attempt** | One try inside a sample. A sample records every attempt's failure and the last raw answer. |
| **Finding** | A claim about the change, paired with the state its proof reached. A finding is the domain's atom; it is not a model opinion once adjudicated. |
| **Claim** | The sentence a finding asserts, and the thing a caller can agree or disagree with. The reviewer proposes it; the proof settles it. |
| **Proof** | A check named by a finding. A proof kind is one registered executor (`present`, `absent`, `command`, `repro`, `json`, `diff`, …); it returns an outcome, not a boolean. `repro` passes only when its command fails. |
| **State** | `PROVEN`, `REFUTED`, `UNSETTLED` or `UNRUNNABLE`. `PROVEN` is the only failing state; `UNRUNNABLE` means the check could not be made, not that the claim is false. |
| **Verdict** | `PASS`, `FAIL` or `INCOMPLETE`. It is a pure function of finding states and missing evidence, never a numeric threshold. |
| **Agreement** | Whether the samples that answered describe the same blocking set. `null` when any sample has no usable answer; never computed from the survivors. |
| **Evidence** | The artefacts that justify a verdict: samples, proof outcomes, the diff digest, the prompt digest and the reason. Evidence is not the reviewer's prose alone. |
| **Run** | The directory that holds one review's evidence. It is claimed exclusively before the first sample and either kept or removed after the verdict. |
| **Plan** | What a review would send and how it would slice it, without calling a reviewer or writing a run. |
| **Instrument** | The reviewer prompt, the profile and the profile's own configuration. Its digest identifies the instrument independently of the answer; the model is part of it because the profile file's bytes are hashed. |
| **Policy** | What the caller permits: allowed proof tools, timeout, sandbox. A repository may narrow a policy, never widen it. |
| **Baseline** | A committed, expiring list of proven blocking findings a team has explicitly accepted. It is applied after the evidence verdict and can never suppress missing evidence. |
| **Accepted risk** | One baseline entry: a fingerprint, owner, reason and expiry for a finding the team chooses not to block on. |
| **Scope** | The caller-owned include/exclude globs applied to changed paths before the prompt is built. It is not repository configuration. |
| **Staged** | A review of the index against the base, not the working tree. Untracked and unstaged edits are deliberately not in the change. |
| **Scope ignored** | A changed path the scope removed, recorded with its reason and matching pattern. It is not a skipped file and not a finding. |
| **Gate result** | The verdict after baseline policy: `verdict` in `verdict.json` may differ from `evidence_verdict`. A gate result is not a finding state. |
| **Fingerprint** | The stable identity of a finding for baseline matching: dimension, severity, file, normalized claim and canonical proof. A changed severity or proof is a new identity. |
| **Domain kernel** | The pure decision modules: run-id validation, configuration parsing, adjudication, baseline policy, scope matching, proof identity and sandbox argv construction. They take literals and return values; they do not read, write, spawn or wait. |
| **Effect shell** | The adapters that read git, files, the environment and child processes, and write runs. Effects are allowed here, named in one list, and never imported by the kernel. |
| **Adapter** | A concrete module at an effect seam: `repo`, `runner`, `proofs`, `pr`, `doctor`, `config`, `baseline`, `paths`, `sample`, `sandbox`, `cli`, `version`. An adapter may import the kernel; the kernel may not import an adapter. |
| **Start failure** | The review could not begin: exit 3, no run directory, no model call. A review that ran and is missing evidence is `INCOMPLETE` (exit 2), not a start failure. |
