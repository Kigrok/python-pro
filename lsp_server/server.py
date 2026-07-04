#!/usr/bin/env python3
# lsp_server/server.py — python-pro language server: live standard diagnostics over LSP.

from __future__ import annotations

from pathlib import Path
from sys import path as _sys_path

# Bootstrap: allow importing the plugin's cli package when launched standalone.
_ROOT: Path = Path(__file__).resolve().parent.parent
_sys_path.insert(0, str(_ROOT))

from tempfile import NamedTemporaryFile  # noqa: E402

from lsprotocol.types import (  # noqa: E402
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    Position,
    PublishDiagnosticsParams,
    Range,
)
from pygls.lsp.server import LanguageServer  # noqa: E402

from cli.validator import PythonProValidator, ValidationReport  # noqa: E402

server: LanguageServer = LanguageServer("python-pro-lsp", "0.4.0")


def _line_range(source: str, line_1based: int) -> Range:
    """Build a full-line LSP range (0-based) for a 1-based validator line."""
    idx: int = max(line_1based - 1, 0)
    lines: list[str] = source.splitlines()
    length: int = len(lines[idx]) if 0 <= idx < len(lines) else 0
    return Range(
        start=Position(line=idx, character=0),
        end=Position(line=idx, character=max(length, 1)),
    )


def _diagnostics(source: str) -> list[Diagnostic]:
    """Validate source text against the python-pro standard and map to diagnostics."""
    tmp_path: Path
    with NamedTemporaryFile(
        "w",
        suffix=".py",
        delete=False,
        encoding="utf-8",
    ) as handle:
        handle.write(source)
        tmp_path = Path(handle.name)
    try:
        report: ValidationReport = PythonProValidator.validate(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    out: list[Diagnostic] = []
    issue: object
    for issue in report.issues:
        severity: DiagnosticSeverity = (
            DiagnosticSeverity.Error
            if issue.severity == "error"
            else DiagnosticSeverity.Warning
        )
        out.append(
            Diagnostic(
                range=_line_range(source, issue.line),
                message=issue.message,
                severity=severity,
                source="python-pro",
                code=str(issue.rule),
            ),
        )
    return out


def _publish(ls: LanguageServer, uri: str) -> None:
    """Validate the current document text and publish diagnostics for a URI."""
    source: str = ls.workspace.get_text_document(uri).source
    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=uri, diagnostics=_diagnostics(source)),
    )


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: DidOpenTextDocumentParams) -> None:
    """Publish diagnostics when a document opens."""
    _publish(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: LanguageServer, params: DidChangeTextDocumentParams) -> None:
    """Publish diagnostics on every change."""
    _publish(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: LanguageServer, params: DidSaveTextDocumentParams) -> None:
    """Publish diagnostics on save."""
    _publish(ls, params.text_document.uri)


def main() -> None:
    """Run the language server over stdio."""
    server.start_io()


if __name__ == "__main__":
    main()
