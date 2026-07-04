#!/usr/bin/env python3
# cli/__main__.py — Command-line interface for python-pro linter.

from __future__ import annotations

from argparse import ArgumentParser, Namespace, _SubParsersAction
from asyncio import run
from json import dumps
from pathlib import Path
from sys import exit, stderr

from cli.linters import run_linters
from cli.models import FileReport, LinterResult, LintError
from cli.pipeline import DeterministicPipeline, PipelineResult


class CLI:
    """Command-line interface for python-pro linter."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _build_report(
        file_path: str,
        results: list[LinterResult],
    ) -> FileReport:
        """Build FileReport from linter results."""
        return FileReport(file=file_path, results=results)

    @staticmethod
    def _print_compact(report: FileReport) -> int:
        """Print errors in compact format."""
        error: LintError
        for error in report.all_errors():
            print(error.compact)
        return 1 if report.has_errors else 0

    @staticmethod
    def _print_json(report: FileReport) -> int:
        """Print errors in JSON format."""
        data: dict[str, object] = {
            "file": report.file,
            "total_errors": report.total_errors,
            "results": [
                {
                    "linter": r.linter,
                    "success": r.success,
                    "errors": [
                        {
                            "line": e.line,
                            "col": e.col,
                            "code": e.code,
                            "message": e.message,
                        }
                        for e in r.errors
                    ],
                }
                for r in report.results
            ],
        }
        print(dumps(data, indent=2))
        return 1 if report.has_errors else 0

    @staticmethod
    async def _lint(args: Namespace) -> int:
        """Run linters on a file."""
        file_path: str = args.file
        if not Path(file_path).exists():
            print(f"Error: {file_path} not found", file=stderr)
            return 2

        linters: list[str] | None = args.linters.split(",") if args.linters else None
        results: list[LinterResult] = await run_linters(
            file_path,
            linters,
        )
        report: FileReport = CLI._build_report(file_path, results)

        if args.json:
            return CLI._print_json(report)
        return CLI._print_compact(report)

    @staticmethod
    async def _fix(args: Namespace) -> int:
        """Run the full deterministic pipeline, then report only the residue."""
        file_path: str = args.file
        if not Path(file_path).exists():
            print(f"Error: {file_path} not found", file=stderr)
            return 2

        linters: list[str] | None = args.linters.split(",") if args.linters else None
        result: PipelineResult = await DeterministicPipeline.run(
            file_path,
            linters,
        )

        if args.json:
            print(
                dumps(
                    {
                        "file": result.file,
                        "changed": result.outcome.changed,
                        "codemods": result.outcome.codemods,
                        "stages": result.outcome.stages,
                        "residual": result.residual_count,
                        "remaining": [line.strip() for line in result.residue_lines()],
                    },
                    indent=2,
                )
            )
            return 1 if result.residual_count else 0

        stages: str = (
            ", ".join(name for name, ok in result.outcome.stages.items() if ok)
            or "none"
        )
        codemods: str = ", ".join(result.outcome.codemods) or "none"
        print(
            f"auto-fix: stages[{stages}] codemods[{codemods}] "
            f"changed={result.outcome.changed}"
        )
        summary: str = result.summary()
        print(summary or f"{file_path}: clean after auto-fix")
        return 1 if result.residual_count else 0

    @staticmethod
    async def _check(args: Namespace) -> int:
        """Check syntax of a file."""
        file_path: str = args.file
        if not Path(file_path).exists():
            print(f"Error: {file_path} not found", file=stderr)
            return 2

        try:
            compile(Path(file_path).read_text(), file_path, "exec")
            print(f"{file_path}: syntax OK")
            return 0
        except SyntaxError as exc:
            print(f"{file_path}: {exc}")
            return 1


def main() -> None:
    """Entry point for python-pro CLI."""
    parser: ArgumentParser = ArgumentParser(
        prog="python-pro",
        description="Python code quality CLI",
    )
    sub: _SubParsersAction[ArgumentParser] = parser.add_subparsers(
        dest="command", required=True
    )

    lint_p: ArgumentParser = sub.add_parser(
        "lint",
        help="Run linters on file",
    )
    lint_p.add_argument("file", help="Python file to lint")
    lint_p.add_argument(
        "--json",
        action="store_true",
        help="JSON output",
    )
    lint_p.add_argument(
        "--linters",
        help="Comma-separated linter list",
    )

    fix_p: ArgumentParser = sub.add_parser(
        "fix",
        help="Auto-fix and lint",
    )
    fix_p.add_argument("file", help="Python file to fix")
    fix_p.add_argument(
        "--json",
        action="store_true",
        help="JSON output",
    )
    fix_p.add_argument(
        "--linters",
        help="Comma-separated linter list",
    )

    check_p: ArgumentParser = sub.add_parser(
        "check",
        help="Syntax check only",
    )
    check_p.add_argument("file", help="Python file to check")

    args: Namespace = parser.parse_args()

    match args.command:
        case "lint":
            exit_code: int = run(CLI._lint(args))
        case "fix":
            exit_code = run(CLI._fix(args))
        case "check":
            exit_code = run(CLI._check(args))
        case _:
            exit_code = 2

    exit(exit_code)


if __name__ == "__main__":
    main()
