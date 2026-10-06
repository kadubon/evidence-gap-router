# Getting started

Install an ordinary package with Python 3.12 or newer:

```sh
python -m pip install evidence-gap-router==0.3.0
egr --version
egr demo --json
```

The demos contain artificial data. `egr check-data` checks your selected local
files without changing them. Create complete UTF-8 examples before running it;
the following Python works in both PowerShell and POSIX shells:

```python
import json
from pathlib import Path

directory = Path("入力 ファイル")
directory.mkdir(exist_ok=True)
(directory / "注文.csv").write_text(
    "order_id,amount,currency\nA-1,1200,JPY\nA-2,8.50,USD\n",
    encoding="utf-8",
)
(directory / "規則.json").write_text(
    json.dumps(
        {
            "required_columns": ["order_id", "amount", "currency"],
            "primary_key": "order_id",
            "minimum_amount": 0,
            "allowed_currencies": ["JPY", "USD"],
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
```

Save that code as `make_example.py` and run it, then quote the paths:

```sh
python make_example.py
egr check-data --data "入力 ファイル/注文.csv" --dictionary "入力 ファイル/規則.json" --json
```

The same commands work in PowerShell. Snapshot files use UTF-8. CLI JSON
escapes Unicode losslessly, including when stdout uses a legacy Windows encoding.
CSV/JSON are bounded to 1 MiB each. Duplicate keys/headers, invalid UTF-8,
nonfinite values and oversized files are rejected as complete inputs.

Exit 0 reports an action or satisfied result. Exit 2 reports a valid unresolved
domain stop or nonacceptance; argparse usage errors also use 2 on stderr.
Exit 1 reports an input or execution failure. Read `outcome`, `runner_stop`
and the domain decision together instead of using the exit code as correctness.

## Run a real callback

The [README callback](../README.md#connect-a-callback) is a complete ordinary
SDK example. Its host checker parses the actual bound content and produces an
issued check. A receipt is not an external authentication mechanism.

For a complete acquisition, check and snapshot continuation:

```python
from evidence_gap_router.sdk_example import run_continuation_example

report = run_continuation_example("continuation.json")
assert report.decision.stop_reason == "satisfied"
assert len(report.state.invalidations) == 1
assert len(report.state.attempts) == 3
```

The path stores the checkpoint after invalidation. To save the final state:

```python
from evidence_gap_router import write_json

write_json(report.state, "completed.json")
```

`egr plan INPUT.json --json` is read-only and never fetches references or
imports handler strings. See [API](api.md) for full inputs, selectors,
exact dependencies and the difference between `step`, `run` and domain stops.

## Three local-file completion examples

```python
from tempfile import TemporaryDirectory
from pathlib import Path
from evidence_gap_router.completion_example import (
    run_partial_example,
    run_pooled_example,
    run_material_continuation,
)

with TemporaryDirectory() as temporary:
    directory = Path(temporary) / "日本語 path"
    partial = run_partial_example(directory / "partial")
    assert not partial["partial"]["completion"][0]["finite_complete"]
    assert not partial["after_acquisition"]["completion"][0]["finite_complete"]
    assert partial["decision"]["stop_reason"] == "satisfied"
    pooled = run_pooled_example(directory / "pooled")
    assert pooled.decision.stop_reason == "satisfied"
    assert len(pooled.state.results) == 1
    continued = run_material_continuation(directory / "continuation")
    assert continued.decision.stop_reason == "satisfied"
    assert len(continued.state.results) == 3
    assert len(continued.state.checks) == 2  # Original PASS is retained.
```

Every callback uses finite actual file content and records known zero model
usage. No model service or experiment is needed. See [completion](completion.md)
and [migration](migration.md) before using an old state with schema 3.
