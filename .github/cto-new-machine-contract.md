# cto.new planned engineering contract

cto.new is the planned engineering and code-quality lane for this repository. It is issue/task driven, not a background repair carrier.

Before editing:
- require a genuine actionable GitHub issue/task intentionally handed to cto.new;
- verify the live supported cto.new GitHub App identity. The verified PR creator is `cto-new[bot]` (GitHub App user ID 140088366); reject lookalike identities;
- compute/confirm the work fingerprint as repository + problem category + affected path/control + source PR/SHA where applicable;
- verify no active Kilo or other implementation owner already holds that fingerprint or an overlapping mutation surface;
- verify the actionable issue has label `autonomy:cto-task` and a current `autonomy-lease:v1` marker whose owner is `cto`; preserve that issue URL in the implementation PR body so trusted admission can correlate the task and lease;
- if this is a Kilo fallback, require a durable ownership-transfer record and proof that the previous Kilo writing path is inactive.

Allowed work includes technical debt, refactoring, maintainability, test coverage, documentation/code consistency, performance improvements, non-emergency hardening, small approved backlog engineering and bounded architecture clean-up.

cto.new must not choose dependency versions, bypass protected policy, weaken tests or security controls, merge its own PRs, use generic GitHub issues as programme ledgers, or compete with an active Kilo implementation fingerprint.

If the actionable issue, lease marker or exact verified `cto-new[bot]` PR identity cannot be proven, fail closed and report the integration blocker instead of making an admission guess.
