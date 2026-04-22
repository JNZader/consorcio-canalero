#!/usr/bin/env python3
"""Simple mutation testing for critical modules.

Applies mutations to source code, runs tests, checks if they catch it.
Killed = tests detected the mutation (GOOD).
Survived = tests missed the mutation (BAD — needs better tests).

Usage:
    python scripts/mutation_test.py [module_name]
    python scripts/mutation_test.py flood_prediction
    python scripts/mutation_test.py all
"""

import ast
import copy
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────

MODULES = {
    "flood_prediction": {
        "source": "app/domains/geo/ml/flood_prediction.py",
        "tests": "tests/new/test_flood_prediction.py",
    },
}


@dataclass
class Mutation:
    line: int
    original: str
    mutated: str
    kind: str

    def __str__(self) -> str:
        return f"L{self.line} [{self.kind}] {self.original.strip()!r} → {self.mutated.strip()!r}"


@dataclass
class MutationResult:
    module: str
    total: int = 0
    killed: int = 0
    survived: int = 0
    errors: int = 0
    survivors: list[Mutation] = field(default_factory=list)

    @property
    def score(self) -> float:
        return (self.killed / self.total * 100) if self.total else 0.0


# ── Mutation operators ─────────────────────────────────────────

def generate_mutations(source_lines: list[str]) -> list[Mutation]:
    """Generate mutations from source lines."""
    mutations: list[Mutation] = []

    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()

        # Skip comments, blanks, imports, decorators, docstrings
        if not stripped or stripped.startswith(("#", "import ", "from ", "@", '"""', "'''", "def ", "class ")):
            continue

        # Comparison operators
        for op, replacement, kind in [
            (" > ", " >= ", "boundary"),
            (" < ", " <= ", "boundary"),
            (" >= ", " > ", "boundary"),
            (" <= ", " < ", "boundary"),
            (" == ", " != ", "negate_cond"),
            (" != ", " == ", "negate_cond"),
        ]:
            if op in line:
                mutations.append(Mutation(i, line, line.replace(op, replacement, 1), kind))

        # Arithmetic operators
        for op, replacement, kind in [
            (" + ", " - ", "arith"),
            (" - ", " + ", "arith"),
            (" * ", " / ", "arith"),
            (" / ", " * ", "arith"),
        ]:
            if op in line and "import" not in line:
                mutations.append(Mutation(i, line, line.replace(op, replacement, 1), kind))

        # Numeric constants (change by small amount)
        import re
        # Float constants like 0.3, 0.25, 100.0
        for match in re.finditer(r'(?<!=)\b(\d+\.\d+)\b', stripped):
            val = float(match.group(1))
            if val == 0.0:
                continue
            new_val = val * 1.5 if val < 1 else val + 1
            new_line = line.replace(match.group(1), f"{new_val:.4f}".rstrip("0").rstrip("."), 1)
            if new_line != line:
                mutations.append(Mutation(i, line, new_line, "constant"))

        # Boolean: True/False swap
        if "True" in line and "import" not in line:
            mutations.append(Mutation(i, line, line.replace("True", "False", 1), "bool"))
        if "False" in line and "import" not in line:
            mutations.append(Mutation(i, line, line.replace("False", "True", 1), "bool"))

        # Return value mutations
        if "return " in stripped and "return None" not in stripped:
            indent = line[: len(line) - len(line.lstrip())]
            mutations.append(Mutation(i, line, f"{indent}return None\n", "return"))

    return mutations


def run_tests(source_path: Path, test_path: str, mutation: Mutation, source_lines: list[str]) -> str:
    """Apply mutation, run tests, restore. Returns 'killed', 'survived', or 'error'."""
    original_content = source_path.read_text()

    # Apply mutation
    mutated_lines = source_lines.copy()
    mutated_lines[mutation.line - 1] = mutation.mutated
    source_path.write_text("".join(mutated_lines))

    try:
        test_paths = test_path.split()
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *test_paths, "-x", "-q", "--no-header", "--tb=no"],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return "killed"
        else:
            return "survived"
    except subprocess.TimeoutExpired:
        return "killed"  # timeout = tests hung on bad code = detected
    except Exception:
        return "error"
    finally:
        # Always restore
        source_path.write_text(original_content)


def run_module(name: str, config: dict) -> MutationResult:
    """Run mutation testing for a single module."""
    source_path = Path(config["source"])
    test_path = config["tests"]

    if not source_path.exists():
        print(f"  ⚠ Source not found: {source_path}")
        return MutationResult(module=name)

    source_lines = source_path.read_text().splitlines(keepends=True)
    mutations = generate_mutations(source_lines)

    result = MutationResult(module=name, total=len(mutations))
    print(f"  Generated {len(mutations)} mutations")

    for idx, mutation in enumerate(mutations, 1):
        status = run_tests(source_path, test_path, mutation, source_lines)
        if status == "killed":
            result.killed += 1
            marker = "🔫"
        elif status == "survived":
            result.survived += 1
            result.survivors.append(mutation)
            marker = "🧟"
        else:
            result.errors += 1
            marker = "💥"

        progress = f"[{idx}/{len(mutations)}]"
        print(f"  {progress} {marker} {mutation}")

    return result


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target == "all":
        modules = MODULES
    elif target in MODULES:
        modules = {target: MODULES[target]}
    else:
        print(f"Unknown module: {target}")
        print(f"Available: {', '.join(MODULES.keys())}, all")
        sys.exit(1)

    results: list[MutationResult] = []

    for name, config in modules.items():
        print(f"\n{'='*60}")
        print(f"  MUTATION TESTING: {name}")
        print(f"  Source: {config['source']}")
        print(f"  Tests:  {config['tests']}")
        print(f"{'='*60}")
        result = run_module(name, config)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("  MUTATION TESTING SUMMARY")
    print(f"{'='*60}")
    print(f"{'Module':<25} {'Total':>6} {'Killed':>7} {'Survived':>9} {'Score':>7}")
    print("-" * 60)

    total_all = killed_all = survived_all = 0
    for r in results:
        total_all += r.total
        killed_all += r.killed
        survived_all += r.survived
        score_str = f"{r.score:.0f}%"
        print(f"{r.module:<25} {r.total:>6} {r.killed:>7} {r.survived:>9} {score_str:>7}")

    overall = (killed_all / total_all * 100) if total_all else 0
    print("-" * 60)
    print(f"{'TOTAL':<25} {total_all:>6} {killed_all:>7} {survived_all:>9} {overall:.0f}%")

    # Show survivors (weaknesses)
    all_survivors = [s for r in results for s in r.survivors]
    if all_survivors:
        print(f"\n{'='*60}")
        print(f"  SURVIVED MUTATIONS ({len(all_survivors)} — need better tests)")
        print(f"{'='*60}")
        for r in results:
            if r.survivors:
                print(f"\n  {r.module}:")
                for s in r.survivors:
                    print(f"    {s}")

    sys.exit(1 if survived_all > 0 else 0)


if __name__ == "__main__":
    main()
