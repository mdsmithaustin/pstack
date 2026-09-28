"""Merge only the same decision.

Each case names two entry functions. The oracle follows every project symbol an
entry reaches through names, imports, and module attributes. Two entries that
reach a common symbol, or where one reaches the other, share a decision."""
import ast
import json
from pathlib import PurePosixPath

from shared import is_test_path, parse_files, parse_python, review_names, run_jobs

PAYROLL = ("payroll.pay", "net_pay")
INVOICE = ("invoicing.totals", "invoice_total")
CREDIT = ("invoicing.totals", "credit_note_total")
PROBES = {
    "payroll-invoice-rounding": """
import json
from decimal import Decimal
from invoicing.totals import invoice_total
from payroll.pay import net_pay
print(json.dumps({
    "net_pay": [str(net_pay(Decimal(gross), Decimal("0.20"), Decimal("0.05"))) for gross in ("3000.00", "1000.10", "2345.67", "999.99")],
    "invoice_total": [str(invoice_total(lines, Decimal("0.20"))) for lines in (
        [(Decimal("19.99"), 3)],
        [(Decimal("0.125"), 1), (Decimal("10.00"), 2)],
        [(Decimal("33.335"), 1)],
    )],
}))
""",
    "invoice-credit-rounding": """
import json
from decimal import Decimal
from invoicing.totals import credit_note_total, invoice_total
cases = ([(Decimal("19.99"), 3)], [(Decimal("0.125"), 1), (Decimal("10.00"), 2)], [(Decimal("33.335"), 1)], [(Decimal("2.5"), 1)])
print(json.dumps({
    "invoice_total": [str(invoice_total(lines, Decimal("0.20"))) for lines in cases],
    "credit_note_total": [str(credit_note_total(lines, Decimal("0.20"))) for lines in cases],
}))
""",
}


def module_name(path):
    parts = list(PurePosixPath(path).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class Program:
    """Top-level definitions and import bindings of every non-test module."""

    def __init__(self, tree):
        self.defs, self.bindings = {}, {}
        for path, body in tree.items():
            if not path.endswith(".py") or is_test_path(path):
                continue
            name = module_name(path)
            module = parse_python(path, body)
            defs, bindings = {}, {}
            for node in module.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defs[node.name] = node
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    defs.update((target.id, node) for target in targets if isinstance(target, ast.Name))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        bindings[alias.asname or alias.name.split(".")[0]] = ("module", alias.name if alias.asname else alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        package = name.split(".")[: len(name.split(".")) - node.level]
                        base = ".".join(package + ([base] if base else []))
                    for alias in node.names:
                        bindings[alias.asname or alias.name] = ("from", base, alias.name)
            self.defs[name], self.bindings[name] = defs, bindings

    def resolve(self, module, name, depth=0):
        """The (module, name) definition, or ("module", name) module, that `name` means in `module`."""
        if depth > 20 or module not in self.defs:
            return None
        if name in self.defs[module]:
            return (module, name)
        binding = self.bindings[module].get(name)
        if binding is None:
            return None
        if binding[0] == "module":
            return ("module", binding[1]) if binding[1] in self.defs else None
        _, base, member = binding
        if f"{base}.{member}" in self.defs:
            return ("module", f"{base}.{member}")
        return self.resolve(base, member, depth + 1)

    def reach(self, entry):
        seen, queue = set(), [entry]
        while queue:
            module, name = queue.pop()
            node = self.defs.get(module, {}).get(name)
            if node is None:
                continue
            for child in ast.walk(node):
                target = None
                if isinstance(child, ast.Name):
                    target = self.resolve(module, child.id)
                elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                    owner = self.resolve(module, child.value.id)
                    if owner and owner[0] == "module":
                        target = self.resolve(owner[1], child.attr)
                if target and target[0] != "module" and target != entry and target not in seen:
                    seen.add(target)
                    queue.append(target)
        return seen


def shared_decision(tree, first, second):
    program = Program(tree)
    first_reach, second_reach = program.reach(first), program.reach(second)
    common = first_reach & second_reach
    common |= {entry for entry, other in ((first, second_reach), (second, first_reach)) if entry in other}
    return sorted(f"{module}.{name}" for module, name in common)


def behavior_changes(case, project, tree):
    trees = {"original": project, "answer": tree}
    before, after = run_jobs(trees, [{"tree": name, "argv": ["python3", "-c", PROBES[case]]} for name in trees])
    if after["rc"] != 0:
        return [f"the totals no longer run: {after['stderr'].strip().splitlines()[-1:]}"]
    before, after = json.loads(before["stdout"]), json.loads(after["stdout"])
    return [f"{entry} results changed from {before[entry]} to {after[entry]}" for entry in before if before[entry] != after[entry]]


def check_separate(answer, project):
    tree = {**project, **parse_files(answer)}
    failures = behavior_changes("payroll-invoice-rounding", project, tree)
    common = shared_decision(tree, PAYROLL, INVOICE)
    if common:
        failures.append(f"net_pay and invoice_total share {', '.join(common)}")
    return failures


def check_merged(answer, project):
    tree = {**project, **parse_files(answer)}
    failures = behavior_changes("invoice-credit-rounding", project, tree)
    if not shared_decision(tree, INVOICE, CREDIT):
        failures.append("invoice_total and credit_note_total still repeat the rounding")
    return failures


def check_billing_monthly_limit(answer, project):
    """The two look-alike validators the pull request keeps apart."""
    return review_names(answer, (r"validate_monthly_limit", r"validate_charge_amount"))


CHECKS = {
    "payroll-invoice-rounding": check_separate,
    "invoice-credit-rounding": check_merged,
    "billing-monthly-limit": check_billing_monthly_limit,
}
