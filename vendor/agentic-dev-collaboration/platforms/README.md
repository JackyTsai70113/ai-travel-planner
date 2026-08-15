# Platform Profiles

Platform profiles are risk and validation overlays. They do not replace project
commands or platform documentation.

A consumer repository should:

1. Replace generic change surfaces with actual paths.
2. Replace generic checks with exact deterministic commands.
3. Declare supported versions, browsers, devices, and environments.
4. Add domain-specific reviewers only when risk requires them.
5. Keep shared contract checks in the cross-platform profile.

The orchestrator selects profiles from the task envelope's platform impact
matrix.
