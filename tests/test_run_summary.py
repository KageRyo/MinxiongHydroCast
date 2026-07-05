import json

from floodcasttw.io.run_summary import (
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)


def test_default_run_summary_path():
    assert str(default_run_summary_path("demo")) == "data/processed/run_summaries/demo.json"


def test_record_run_writes_summary_and_jsonl_log(tmp_path):
    started_at, start_timer = start_run()
    summary = build_run_summary(
        pipeline="demo",
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        mode="demo",
        row_counts={"records": 2},
    )
    summary_output = tmp_path / "summary.json"
    log_output = tmp_path / "run_logs.jsonl"

    record_run(summary_output=summary_output, log_output=log_output, summary=summary)

    written_summary = json.loads(summary_output.read_text(encoding="utf-8"))
    written_log = json.loads(log_output.read_text(encoding="utf-8").strip())
    assert written_summary["pipeline"] == "demo"
    assert written_summary["row_counts"]["records"] == 2
    assert written_log["event"] == "run_completed"
    assert written_log["status"] == "ok"
