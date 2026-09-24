"""Fork a shared helper instead of changing it for one caller."""
import json

from shared import parse_files, run_jobs

PAY_PROBE = """
import json
from decimal import Decimal
from timesheets.audit_report import report_hours
from timesheets.hours import TimeCard
from timesheets.payroll import calculate_pay
cards = [TimeCard("ana", "2026-W39", Decimal("39")), TimeCard("bo", "2026-W39", Decimal("42"))]
print(json.dumps({
    "pay": {hours: str(calculate_pay(TimeCard("cy", "2026-W39", Decimal(hours)), Decimal("20.00"))) for hours in ("38", "39", "42")},
    "report": report_hours(cards),
}))
"""
EXPECTED_PAY = {"38": "760.00", "39": "790.00", "42": "880.00"}


def check_fork(answer, project):
    files = parse_files(answer)
    if not files:
        return ["answer changes no file"]
    trees = {"original": project, "answer": {**project, **files}}
    original, changed = run_jobs(trees, [{"tree": name, "argv": ["python3", "-c", PAY_PROBE]} for name in trees])
    if changed["rc"] != 0:
        return [f"payroll or audit report no longer runs: {changed['stderr'].strip().splitlines()[-1:]}"]
    before, after = json.loads(original["stdout"]), json.loads(changed["stdout"])
    failures = []
    if after["pay"] != EXPECTED_PAY:
        failures.append(f"pay does not start overtime after 38 hours: {after['pay']}")
    if after["report"] != before["report"]:
        failures.append("the compliance hours report changed")
    return failures


CHECKS = {"payroll-overtime": check_fork}
