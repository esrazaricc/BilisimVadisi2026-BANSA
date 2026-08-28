from pathlib import Path

from scripts.run_kuveyt_post_sync_pipeline import (
    PipelineStep,
    build_steps,
    restore_database_backup,
)


def test_pipeline_does_not_reclassify_all_records():
    steps = build_steps(
        "Kuveyt Türk",
        40,
    )
    scripts = [
        step.script
        for step in steps
    ]

    assert scripts[0] == "classify_campaign_records.py"
    assert "--only-unclassified-current" in steps[0].extra_args


def test_pipeline_step_order():
    steps = build_steps(
        "Kuveyt Türk",
        40,
    )

    assert [
        step.script
        for step in steps
    ] == [
        "classify_campaign_records.py",
        "apply_campaign_classification_overrides.py",
        "check_kuveyt_classification_after_overrides.py",
        "extract_comparison_fields.py",
        "check_kuveyt_third_fixes.py",
        "check_kuveyt_final_three.py",
        "audit_kuveyt_nonfinance_extraction.py",
    ]
    assert "--only-unclassified-current" in steps[0].extra_args


def test_bank_argument_is_passed_to_every_step():
    steps = build_steps(
        "Kuveyt Türk",
        40,
    )

    for step in steps:
        assert "--bank" in step.extra_args
        index = step.extra_args.index("--bank")
        assert (
            step.extra_args[index + 1]
            == "Kuveyt Türk"
        )


def test_audit_limit_is_passed_only_to_audit():
    steps = build_steps(
        "Kuveyt Türk",
        25,
    )

    audit = steps[-1]
    assert (
        audit.script
        == "audit_kuveyt_nonfinance_extraction.py"
    )
    assert "--limit" in audit.extra_args
    index = audit.extra_args.index("--limit")
    assert audit.extra_args[index + 1] == "25"

    for step in steps[:-1]:
        assert "--limit" not in step.extra_args


def test_restore_database_backup(tmp_path):
    backup = tmp_path / "backup.db"
    database = tmp_path / "data" / "campaigns.db"

    backup.write_bytes(b"known-good-database")
    restore_database_backup(
        backup,
        database,
    )

    assert (
        database.read_bytes()
        == b"known-good-database"
    )


def test_pipeline_step_is_immutable():
    step = PipelineStep(
        "Test",
        "test.py",
        ("--bank", "Kuveyt Türk"),
    )

    assert step.script == "test.py"
