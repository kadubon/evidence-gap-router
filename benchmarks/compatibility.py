"""Historical workers require their original SDK; this is not a schema-3 benchmark."""


def require_original_sdk() -> None:
    import evidence_gap_router as sdk

    if sdk.__version__ not in {"0.2.1", "0.2.2"}:
        raise ValueError(
            "Historical benchmark requires its original tag, wheel and harness; "
            "no v0.3.0 experiment or measurement is authorized."
        )
