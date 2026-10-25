from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
CHANGE_NAME = "define-klaro-mvp"
CHANGES = ROOT / "openspec" / "changes"
CAPABILITIES = ("questionnaires", "abuse-protection")


def verification_artifact() -> Path:
    active = CHANGES / CHANGE_NAME / "verification.md"
    if active.is_file():
        return active
    archived = list((CHANGES / "archive").glob(f"*-{CHANGE_NAME}/verification.md"))
    assert len(archived) == 1, f"Expected one verification artifact, found {archived}"
    return archived[0]


def specification_scenarios(capability: str) -> set[str]:
    spec = (ROOT / "openspec" / "specs" / capability / "spec.md").read_text()
    return set(re.findall(r"^#### Scenario: (.+)$", spec, re.MULTILINE))


def matrix_rows() -> dict[str, dict[str, list[str]]]:
    rows: dict[str, dict[str, list[str]]] = defaultdict(dict)
    matrix = verification_artifact().read_text()
    for line in matrix.splitlines():
        if not any(line.startswith(f"| {capability} |") for capability in CAPABILITIES):
            continue
        cells = [cell.strip() for cell in line.split("|")]
        capability, scenario, references = cells[1], cells[2], cells[3]
        assert scenario not in rows[capability], f"Duplicate matrix scenario: {scenario}"
        tests = re.findall(r"`([^`]+)`", references)
        assert tests, f"No executable test for {capability}: {scenario}"
        rows[capability][scenario] = tests
    return rows


def test_every_spec_scenario_has_valid_executable_coverage() -> None:
    matrix = matrix_rows()
    assert set(matrix) == set(CAPABILITIES)
    function_cache: dict[Path, set[str]] = {}
    scenario_count = 0

    for capability in CAPABILITIES:
        expected = specification_scenarios(capability)
        actual = set(matrix[capability])
        assert actual == expected, (
            f"Scenario mismatch for {capability}: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
        scenario_count += len(expected)
        for scenario, nodes in matrix[capability].items():
            for node in nodes:
                filename, separator, function = node.partition("::")
                path = ROOT / filename
                assert path.is_file(), f"Missing test file for {scenario}: {path}"
                assert separator and function.startswith("test_"), (
                    f"Coverage must name a test function for {scenario}: {node}"
                )
                if path not in function_cache:
                    tree = ast.parse(path.read_text(), filename=str(path))
                    function_cache[path] = {
                        item.name
                        for item in ast.walk(tree)
                        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
                    }
                assert function in function_cache[path], (
                    f"Missing test function for {scenario}: {node}"
                )

    assert scenario_count == 57
