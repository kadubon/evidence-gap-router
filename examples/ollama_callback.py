"""Explicit artificial-document callback using the new owned campaign ledger.

Run with an ordinary installed Python and -I; this source example is outside
the wheel. Import and --help do not start or contact a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.ollama import cli  # noqa: E402
from experiments.ollama.harness import run_trial  # noqa: E402
from experiments.ollama.tasks import Document, PublicTask  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--model", choices=("gemma4:e4b", "qwen3.6:35b-a3b"), default="gemma4:e4b")
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    parser.add_argument("--key", default="example024-temperature-gemma")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", args.key):
        parser.error("key must be a bounded filename-safe new trial identity")
    cli.PROTOCOL_PATH = cli.ROOT / "protocol-v0.2.4.json"
    cli.PROTOCOL = json.loads(cli.PROTOCOL_PATH.read_text("utf-8"))
    owner = json.loads((args.directory / "private/current-owner.json").read_text("utf-8"))
    args.server_pid = owner["root"]["pid"]
    args.server_log = Path(owner["server_log"])
    task = PublicTask(
        task_id="local-example024-temperature",
        family="L1",
        question="公開仕様と今回の測定に従い、対象Aは許可されるか。未記録は偽にしない。",
        documents=(
            Document(
                "specification",
                "engineering",
                "temperature",
                "1",
                "spec-origin",
                "対象Aの許可の必要十分条件は今回の測定温度が10℃以下であること。条件を満たせば必ず許可する。その他の条件はない。",
            ),
            Document(
                "measurement",
                "inspection",
                "temperature",
                "1",
                "measurement-origin",
                "今回の対象Aの測定温度は9℃と検査当局が確認した。",
            ),
        ),
    )
    task_sha = hashlib.sha256(
        json.dumps(asdict(task), ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    output = args.directory / (args.key + "-result.json")
    if output.exists():
        record = json.loads(output.read_text("utf-8"))
        if record["public_task_sha256"] != task_sha or record["model"] != args.model:
            raise ValueError("Retained example key belongs to different inputs/model")
        print(
            json.dumps(
                {
                    "reused_retained_example": True,
                    "new_model_requests": 0,
                    "runner_stop": record["trial"]["runner_stop"],
                }
            )
        )
        return
    client = cli.client_for(args)
    checkpoint = args.directory / (args.key + "-checkpoint.json")
    before = client.summary()
    if before["blocked"]:
        raise ValueError("Example ledger is not healthy; preserve its uncertainty")
    result = run_trial(
        task,
        arm="A",
        model=args.model,
        model_digest=client.profiles[args.model].digest,
        seed=cli.PROTOCOL["development_seed"],
        client=cli.BoundClient(client, args, "example", args.key),
        checkpoint=checkpoint,
        resume=checkpoint.exists(),
        settings=cli.trial_settings(args.directory),
    )
    after = client.summary()
    record = {
        "model": args.model,
        "public_task": asdict(task),
        "public_task_sha256": task_sha,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "new_model_requests": after["calls"] - before["calls"],
        "trial": result,
        "independent_oracle_score": None,
        "scope": "Explicit artificial custom example, not a confirmation parent",
    }
    cli.write_json(output, record)
    cli.write_json(
        args.directory / "ledger-summary.json", {k: v for k, v in after.items() if k != "responses"}
    )
    print(
        json.dumps(
            {
                "new_model_requests": record["new_model_requests"],
                "answer": result["answer"],
                "runner_stop": result["runner_stop"],
                "domain_stop": result["domain_stop"],
                "pending": result["pending"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
