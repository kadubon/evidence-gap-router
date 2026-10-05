# Security policy

The supported current line is 0.2.x. Use the repository's
[private security advisory form](https://github.com/kadubon/evidence-gap-router/security/advisories/new)
when available. Otherwise request a private contact in an issue without including
secrets or exploit details. No response-time service level is promised.

Schema validation, issued-receipt consistency and authentic evidence are distinct.
The host owns policy, checker registration, callbacks, state, resource measurement
and credentials. A checker ID in a result is not authentication. Host registration
binds actual Python checker identity to permitted role/revision/purpose; evidence
text cannot change that policy or grant execution permission.

Issued verification bases pin exact targets, acceptance fingerprints, finite
used dependencies and resolution purpose. Generic PASS cannot resolve a named
contradiction; acquisition cannot withdraw or replace negative checks. Strict,
immutable records and validated APIs do not prevent a malicious trusted host
from constructing or rewriting its own state. Do not describe host snapshots as
cryptographically authenticated execution history.

Callback views disclose only explicitly selected material. They do not prevent
same-process Python code from reading globals, files or other data, and do not
prove secrecy or statistical independence. The host must enforce real isolation,
external authentication, access control, timeout and resource controls as needed.
The finite runner preserves callback uncertainty and never automatically retries
an unknown effect; it is not crash recovery or exactly-once execution.

CLI planning input is bounded local operator material. References are not fetched
and handler strings are not imported. A service receiving untrusted evidence must
supply host policy separately. `check-data` intentionally reads only selected local
files, rejects ambiguous/bounded input and does not overwrite them. This is not a
sandboxed filesystem service. Malformed or failed callbacks retain state and costs.

Review evidence, original files, exception messages and reports before publishing
sensitive content. No telemetry, model/API key or network service is required by
the router, installed examples or normal offline checks. Migration preserves
legacy uncertainty and history; it does not authenticate old records or invent
missing verification bases.
