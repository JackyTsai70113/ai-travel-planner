# Domain Reviewers

Consumer repositories should add domain reviewers for invariants that generic
software reviewers cannot reliably infer, such as:

- Financial calculations and portfolio constraints.
- Healthcare privacy and clinical safety.
- Payments, ledger, and reconciliation rules.
- Legal or regulatory controls.
- Data provenance and scientific reproducibility.

Domain reviewers should normally be read-only. Their manifest must define:

- Exact invariants.
- Authoritative source files.
- Evidence and freshness requirements.
- Blocking conditions.
- Explicit non-responsibilities.

Copy `agent.template.yaml`, replace the placeholders, and rename the file to
`<domain>-reviewer.agent.yaml`.
