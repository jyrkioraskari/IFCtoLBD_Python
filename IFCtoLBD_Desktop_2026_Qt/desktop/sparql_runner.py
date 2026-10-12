"""SPARQL query execution against the latest generated RDF output."""

from __future__ import annotations

from dataclasses import dataclass

MAX_RESULT_ROWS = 1_000

DEFAULT_SPARQL_QUERY = """\
PREFIX bot: <https://w3id.org/bot#>

SELECT ?element WHERE {
  ?element a bot:Element .
}
LIMIT 100
"""


@dataclass(frozen=True, slots=True)
class SparqlTableResult:
    """Structured SPARQL result suitable for a real table widget."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    message: str = ""
    truncated: bool = False


def run_sparql_query(output_file: str, query_text: str) -> SparqlTableResult:
    """Run ``query_text`` and return structured, display-independent results."""
    from rdflib import Graph

    graph = Graph()
    graph.parse(output_file)
    results = graph.query(query_text)
    if getattr(results, "type", None) == "ASK":
        value = "true" if bool(results) else "false"
        return SparqlTableResult(("Result",), ((value,),), "ASK query result")
    variables = list(getattr(results, "vars", None) or [])
    if not variables:
        return SparqlTableResult(
            (), (), "The query did not produce tabular results."
        )
    columns = tuple(str(variable) for variable in variables)
    rows: list[tuple[str, ...]] = []
    truncated = False
    for index, row in enumerate(results):
        if index >= MAX_RESULT_ROWS:
            truncated = True
            break
        rows.append(tuple("" if value is None else str(value) for value in row))

    message = f"{len(rows)} row(s)"
    if truncated:
        message += f" · limited to {MAX_RESULT_ROWS:,} rows"
    return SparqlTableResult(columns, tuple(rows), message, truncated)
