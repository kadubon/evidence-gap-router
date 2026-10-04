# Security policy

The supported initial line is 0.1.x. Report a potential vulnerability through
the repository's [private security-advisory form](https://github.com/kadubon/evidence-gap-router/security/advisories/new)
when available. If private reporting is unavailable, open an issue requesting a
private contact without including exploit details or secrets. No response-time
or incident-response service level is promised.

The core handles bounded, strict JSON and host-selected records. Evidence
content, source names, references and handler IDs are data. It never follows a
URL/path reference, imports an ID as a function or derives permission from
untrusted text. A reference's SHA-256 binds content identity only.

The host must protect verifier records, callback registration, policy, execution
credentials, resource measurements and state ownership. CLI planning input is
operator-selected local material: its policy field is not an authenticated
policy source for a remote service. A host accepting untrusted evidence must
keep its own policy outside that evidence and call the SDK with trusted policy.
Before constructing a `CheckResult`, the host binds the actual checker identity
to a trusted verifier ID. An ID string is not authentication. Acquisition
callbacks cannot introduce new checks; new checks belong to issued verification
attempts for their exact target digest.

The packaged demo reads artificial local files. Its explicit callback mapping
is an integration example, not a sandbox. Callbacks may have side effects; the
host owns access control, isolation, timeouts, network restrictions and secret
redaction. Exceptions/invalid returns leave actual cost and effects unknown and
stop further automatic work. No exactly-once execution, concurrency reservation,
crash recovery, semantic truth detection or statistical independence is promised.

Do not pass sensitive evidence or callback exception details to a public output
channel without host-side review. No telemetry, external model access or runtime
network access is required by the router or packaged demo.
