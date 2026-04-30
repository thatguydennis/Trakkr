# MVP Operations Runbook

## Scheduled Pipeline

Primary command:

```bash
./ops/run_mvp_pipeline.sh
```

Recommended schedule:
- Weekly full run for public dashboard snapshot refresh.
- Daily monitor check for freshness and pointer health.

Example cron:

```bash
# Weekly pipeline run (Sunday 2:00 AM)
0 2 * * 0 cd /path/to/project && ./ops/run_mvp_pipeline.sh >> logs/pipeline.log 2>&1

# Daily monitor check (6:00 AM)
0 6 * * * cd /path/to/project && source .venv/bin/activate && python3 ops/monitor_pipeline.py >> logs/monitor.log 2>&1
```

## Publish Gate

`ops/run_mvp_pipeline.sh` invokes `ops/quality_gate.py` and fails if:
- forecast outputs are empty
- positive rate is out of expected operating range

If gate fails, do not publish that run.

## Alerting

Current alerting is process-exit based:
- non-zero exit code from `quality_gate.py` or `monitor_pipeline.py` should trigger external alerting in scheduler/CI.

Suggested integration:
- GitHub Actions failure notification
- Slack webhook from CI

## Rollback

To serve a prior known-good snapshot:

```bash
source .venv/bin/activate
python3 ops/rollback_latest.py --pipeline forecast --run-id <previous_run_id>
```

Rollback only changes `data/artifacts/latest/<pipeline>.json` pointer.

## Incident Response Checklist

1. Confirm failure stage from logs (`clean_data`, `model`, `backtest`, `forecast`, `quality_gate`).
2. Validate source data freshness in `data/raw`.
3. Re-run failing stage locally with `.venv` activated.
4. If still failing, rollback `forecast` pointer to prior run.
5. Record incident summary and root cause in project issue tracker.
