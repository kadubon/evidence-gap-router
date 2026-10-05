"""The installed package contains the full runnable callback migration example."""

from evidence_gap_router.sdk_example import run_callback_example

report = run_callback_example()
print(report.decision.stop_reason)
