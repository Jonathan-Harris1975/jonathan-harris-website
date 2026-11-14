# Monthly Website repair execution

RAMS reads the exact unified Website audit and sends immutable bounded task plans to the default-branch Audit remediation handoff workflow. The existing Autonomy R2 credentials and target Kilo trigger are used. Kilo pushes only the declared fix branch; native branch automation owns PR publication and merge.

The worker verifies source digest, exact target SHA and the declared scope, then reserves one external handoff with a conditional shared repository writer lease. Trusted admission rejects changes outside the plan and requires its exact Python unittest regression file. Production readiness runs those regression tests in addition to the canonical build.

RAMS retains repair ownership until required exact-head checks, native merge, the deployed commit marker and Website deployed integration all verify the repair. Missing evidence or uncertain external writes stay unresolved. A real external-writer acceptance run is required after the worker is deployed.
