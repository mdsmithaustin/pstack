import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    app = Path(__file__).with_name("app.py")
    checks = 0

    def invoke(path, request, expected, exit_code=0):
        nonlocal checks
        before = path.read_bytes() if path.exists() else None
        result = subprocess.run([sys.executable, "-B", str(app), "--state", str(path)],
                                input=json.dumps(request), text=True, capture_output=True)
        actual = json.loads(result.stdout)
        if result.returncode != exit_code or actual != expected:
            raise RuntimeError(f"Unexpected result for {request}: {result.returncode} {actual} {result.stderr}")
        if exit_code and (path.read_bytes() if path.exists() else None) != before:
            raise RuntimeError(f"Rejected request changed state: {request}")
        checks += 1

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reminders.json"
        invoke(path, {"action": "create", "series_id": "tea", "occurrence_date": "2026-01-01", "cadence_days": 7},
               {"series_id": "tea", "status": "active", "cadence_days": 7})
        invoke(path, {"action": "create", "series_id": "tea", "occurrence_date": "2026-01-01", "cadence_days": 7},
               {"series_id": "tea", "status": "active", "cadence_days": 7})
        invoke(path, {"action": "skip", "series_id": "tea", "occurrence_date": "2026-01-08"},
               {"series_id": "tea", "occurrence_date": "2026-01-08", "status": "skipped"})
        invoke(path, {"action": "skip", "series_id": "tea", "occurrence_date": "2026-01-08"},
               {"series_id": "tea", "occurrence_date": "2026-01-08", "status": "skipped"})
        for action in ("deliver", "cancel"):
            invoke(path, {"action": action, "series_id": "tea", "occurrence_date": "2026-01-08"},
                   {"error": "occurrence_closed"}, 2)
        invoke(path, {"action": "deliver", "series_id": "tea", "occurrence_date": "2026-01-15"},
               {"series_id": "tea", "occurrence_date": "2026-01-15", "status": "delivered"})
        invoke(path, {"action": "skip", "series_id": "tea", "occurrence_date": "2026-01-15"},
               {"error": "occurrence_closed"}, 2)
        invoke(path, {"action": "list", "occurrence_date": "2026-01-15"}, {"occurrences": [
            {"series_id": "tea", "occurrence_date": "2026-01-01", "status": "pending"},
            {"series_id": "tea", "occurrence_date": "2026-01-08", "status": "skipped"},
            {"series_id": "tea", "occurrence_date": "2026-01-15", "status": "delivered"}]})

        invoke(path, {"action": "create", "series_id": "milk", "occurrence_date": "2026-01-01", "cadence_days": 3},
               {"series_id": "milk", "status": "active", "cadence_days": 3})
        invoke(path, {"action": "cancel", "series_id": "milk", "occurrence_date": "2026-01-13"},
               {"series_id": "milk", "occurrence_date": "2026-01-13", "status": "cancelled"})
        invoke(path, {"action": "deliver", "series_id": "milk", "occurrence_date": "2026-01-16"},
               {"series_id": "milk", "occurrence_date": "2026-01-16", "status": "delivered"})
        invoke(path, {"action": "skip", "series_id": "milk", "occurrence_date": "2026-01-19"},
               {"series_id": "milk", "occurrence_date": "2026-01-19", "status": "skipped"})
        invoke(path, {"action": "deliver", "series_id": "milk", "occurrence_date": "2026-01-16"},
               {"series_id": "milk", "occurrence_date": "2026-01-16", "status": "delivered"})
        invoke(path, {"action": "skip", "series_id": "milk", "occurrence_date": "2026-01-19"},
               {"series_id": "milk", "occurrence_date": "2026-01-19", "status": "skipped"})
        invoke(path, {"action": "end_series", "series_id": "milk", "occurrence_date": "2026-01-08"},
               {"series_id": "milk", "status": "ended", "ended_on": "2026-01-08"})
        invoke(path, {"action": "end_series", "series_id": "milk", "occurrence_date": "2026-01-08"},
               {"series_id": "milk", "status": "ended", "ended_on": "2026-01-08"})
        invoke(path, {"action": "end_series", "series_id": "milk", "occurrence_date": "2026-01-09"},
               {"error": "series_ended"}, 2)
        invoke(path, {"action": "create", "series_id": "milk", "occurrence_date": "2026-01-01", "cadence_days": 3},
               {"error": "series_ended"}, 2)
        invoke(path, {"action": "deliver", "series_id": "milk", "occurrence_date": "2026-01-22"},
               {"error": "series_ended"}, 2)
        invoke(path, {"action": "cancel", "series_id": "milk", "occurrence_date": "2026-01-13"},
               {"series_id": "milk", "occurrence_date": "2026-01-13", "status": "cancelled"})
        for action in ("deliver", "skip"):
            invoke(path, {"action": action, "series_id": "milk", "occurrence_date": "2026-01-13"},
                   {"error": "occurrence_closed"}, 2)
        invoke(path, {"action": "skip", "series_id": "milk", "occurrence_date": "2026-01-07"},
               {"series_id": "milk", "occurrence_date": "2026-01-07", "status": "skipped"})
        invoke(path, {"action": "list", "occurrence_date": "2026-01-20"}, {"occurrences": [
            {"series_id": "milk", "occurrence_date": "2026-01-01", "status": "pending"},
            {"series_id": "tea", "occurrence_date": "2026-01-01", "status": "pending"},
            {"series_id": "milk", "occurrence_date": "2026-01-04", "status": "pending"},
            {"series_id": "milk", "occurrence_date": "2026-01-07", "status": "skipped"},
            {"series_id": "tea", "occurrence_date": "2026-01-08", "status": "skipped"},
            {"series_id": "milk", "occurrence_date": "2026-01-10", "status": "cancelled"},
            {"series_id": "milk", "occurrence_date": "2026-01-13", "status": "cancelled"},
            {"series_id": "tea", "occurrence_date": "2026-01-15", "status": "delivered"},
            {"series_id": "milk", "occurrence_date": "2026-01-16", "status": "delivered"},
            {"series_id": "milk", "occurrence_date": "2026-01-19", "status": "skipped"}]})

        invoke(path, {"action": "skip", "series_id": "tea", "occurrence_date": "2026-01-22", "cadence_days": 7},
               {"error": "invalid_request"}, 2)
        invoke(path, {"action": "end_series", "series_id": "missing", "occurrence_date": "2026-01-01"},
               {"error": "missing_series"}, 2)
        invoke(path, {"action": "end_series", "series_id": "tea", "occurrence_date": "2025-12-31"},
               {"error": "invalid_occurrence"}, 2)
        invoke(path, {"action": "skip", "series_id": "tea", "occurrence_date": "2026-01-09"},
               {"error": "invalid_occurrence"}, 2)

        legacy = Path(directory) / "legacy.json"
        legacy.write_text(json.dumps({"series": {"tea": {"start_date": "2026-01-01", "cadence_days": 7,
                                                           "occurrences": {"2026-01-08": "cancelled"}}}}))
        invoke(legacy, {"action": "skip", "series_id": "tea", "occurrence_date": "2026-01-15"},
               {"series_id": "tea", "occurrence_date": "2026-01-15", "status": "skipped"})
        invoke(legacy, {"action": "list", "occurrence_date": "2026-01-15"}, {"occurrences": [
            {"series_id": "tea", "occurrence_date": "2026-01-01", "status": "pending"},
            {"series_id": "tea", "occurrence_date": "2026-01-08", "status": "cancelled"},
            {"series_id": "tea", "occurrence_date": "2026-01-15", "status": "skipped"}]})

        boundary = Path(directory) / "boundary.json"
        invoke(boundary, {"action": "create", "series_id": "water", "occurrence_date": "2026-01-01", "cadence_days": 2},
               {"series_id": "water", "status": "active", "cadence_days": 2})
        invoke(boundary, {"action": "list", "occurrence_date": "2026-01-05"}, {"occurrences": [
            {"series_id": "water", "occurrence_date": "2026-01-01", "status": "pending"},
            {"series_id": "water", "occurrence_date": "2026-01-03", "status": "pending"},
            {"series_id": "water", "occurrence_date": "2026-01-05", "status": "pending"}]})
        invoke(boundary, {"action": "end_series", "series_id": "water", "occurrence_date": "2026-01-05"},
               {"series_id": "water", "status": "ended", "ended_on": "2026-01-05"})
        invoke(boundary, {"action": "deliver", "series_id": "water", "occurrence_date": "2026-01-05"},
               {"error": "occurrence_closed"}, 2)
        invoke(boundary, {"action": "deliver", "series_id": "water", "occurrence_date": "2026-01-07"},
               {"error": "series_ended"}, 2)
        invoke(boundary, {"action": "end_series", "series_id": "water", "occurrence_date": "2026-01-05", "cadence_days": 2},
               {"error": "invalid_request"}, 2)

        ending = Path(directory) / "ending.json"
        invoke(ending, {"action": "create", "series_id": "bread", "occurrence_date": "2026-01-01", "cadence_days": 7},
               {"series_id": "bread", "status": "active", "cadence_days": 7})
        invoke(ending, {"action": "end_series", "series_id": "bread", "occurrence_date": "2026-01-12"},
               {"series_id": "bread", "status": "ended", "ended_on": "2026-01-12"})
        invoke(ending, {"action": "list", "occurrence_date": "2026-01-20"}, {"occurrences": [
            {"series_id": "bread", "occurrence_date": "2026-01-01", "status": "pending"},
            {"series_id": "bread", "occurrence_date": "2026-01-08", "status": "pending"}]})

    print(f"{checks} checks passed")


if __name__ == "__main__":
    main()
