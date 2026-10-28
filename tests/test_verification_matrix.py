from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
# Implemented but not yet archived changes, in implementation order. Every change is
# archived, so the main specs alone define the expected scenarios.
IMPLEMENTED_DELTAS: tuple[str, ...] = ()
CHANGES = ROOT / "openspec" / "changes"
CAPABILITIES = ("questionnaires", "abuse-protection")


def verification_artifact() -> Path:
    return ROOT / "tests" / "scenario-coverage.md"


def requirements(text: str) -> dict[str, str]:
    return {
        section.splitlines()[0]: section.strip()
        for section in re.split(r"^### Requirement: ", text, flags=re.MULTILINE)[1:]
    }


def apply_delta(sections: dict[str, str], delta: str) -> None:
    parts = re.split(
        r"^## (ADDED|MODIFIED|REMOVED|RENAMED) Requirements\s*$", delta, flags=re.MULTILINE
    )
    for operation, block in zip(parts[1::2], parts[2::2], strict=True):
        assert operation in {"ADDED", "MODIFIED"}, f"Unsupported delta operation: {operation}"
        sections.update(requirements(block))


def effective_spec(capability: str, main: str) -> str:
    sections = requirements(main)
    for change_name in IMPLEMENTED_DELTAS:
        delta = CHANGES / change_name / "specs" / capability / "spec.md"
        if delta.is_file():
            apply_delta(sections, delta.read_text())
    return "\n".join(f"### Requirement: {section}" for section in sections.values())


def specification_scenarios(capability: str) -> set[str]:
    spec = (ROOT / "openspec" / "specs" / capability / "spec.md").read_text()
    return set(re.findall(r"^#### Scenario: (.+)$", effective_spec(capability, spec), re.MULTILINE))


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

    for capability in CAPABILITIES:
        expected = specification_scenarios(capability)
        actual = set(matrix[capability])
        assert actual == expected, (
            f"Scenario mismatch for {capability}: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
        for scenario, nodes in matrix[capability].items():
            for node in nodes:
                filename, separator, function = node.partition("::")
                path = ROOT / filename
                assert path.is_file(), f"Missing test file for {scenario}: {path}"
                message = f"Coverage must name a test function for {scenario}: {node}"
                assert separator, message
                assert function.startswith("test_"), message
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


def test_every_listed_delta_is_active_or_archived() -> None:
    # Archived deltas are already part of the main specs and are skipped; a name that
    # is neither active nor archived is a typo or a renamed change.
    for change_name in IMPLEMENTED_DELTAS:
        active = (CHANGES / change_name).is_dir()
        archived = any((CHANGES / "archive").glob(f"????-??-??-{change_name}"))
        assert active != archived, f"{change_name} must be exactly one of active or archived"


def test_coverage_is_unchanged_after_simulated_spec_sync() -> None:
    for capability in CAPABILITIES:
        main = (ROOT / "openspec" / "specs" / capability / "spec.md").read_text()
        synchronized = effective_spec(capability, main)
        assert effective_spec(capability, synchronized) == synchronized
        assert set(re.findall(r"^#### Scenario: (.+)$", synchronized, re.MULTILINE)) == set(
            matrix_rows()[capability]
        )
