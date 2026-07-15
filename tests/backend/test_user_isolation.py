"""The service-role backend bypasses RLS, so app-level scoping is the only guard.

Every SELECT / UPDATE / DELETE that touches a per-user table (user_profile,
o1_evidence, outreach_log, session_artifacts, trace_log) must filter on
user_id -- otherwise one tenant's immigration evidence is one guessed row id
away from another tenant's service-role connection.

The Postgres/Supabase data-access surface lives in three places:
backend/services/*.py (evidence_service, market_service), backend/routers
(account.py's export/delete), and paperpilot/supabase_client.py (the shared
psycopg helpers). paperpilot/outreach/*.py was checked too, but every query
there runs against ClickHouse for the legacy Streamlit app (a separate
database that never uses the service-role Postgres connection this task is
about), so it is out of scope here.

Scanning approach: a naive regex over quoted string literals produces both
false positives (a query's WHERE clause commonly lives in a second, adjacent
Python string literal, or behind an f-string placeholder resolved from a
local variable) and false negatives (an English docstring or a "%s"-style
column name like "updated_at" can look like a SQL keyword to a substring
match). `_sql_statements` instead walks each function's AST, folds adjacent
string literals and simple f-string variables the way Python itself would at
compile/run time, and only classifies a resolved string as SQL if it starts
with a real keyword at a word boundary.
"""

from __future__ import annotations

import ast
import inspect
import re

import pytest

from backend.routers import account
from backend.services import evidence_service, market_service
from paperpilot import supabase_client

PER_USER_TABLES = [
    "o1_evidence",
    "outreach_log",
    "user_profile",
    "session_artifacts",
    "trace_log",
]

# account.py is the export/delete path; supabase_client.py is the shared
# helper layer both services and account.py sit on top of.
MODULES = [evidence_service, market_service, account, supabase_client]

_SQL_START = re.compile(r"^\s*(SELECT|DELETE|UPDATE)\b", re.IGNORECASE)


def _resolve(node: ast.AST, ctx: dict) -> str | None:
    """Best-effort reconstruction of the string a node evaluates to.

    Handles the patterns actually used in this codebase: adjacent literals
    folded into one f-string by the parser, `+`-concatenation, a bare
    reference to an already-assigned local string/list variable, and
    `"<sep>".join(list_var)` for the common `where = [...]; " AND
    ".join(where)` pattern. Anything else resolves to the "<expr>" sentinel
    so the surrounding literal text is preserved without inventing content.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                resolved = _resolve(v.value, ctx)
                parts.append(resolved if resolved is not None else "<expr>")
            else:
                parts.append("<expr>")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve(node.left, ctx)
        right = _resolve(node.right, ctx)
        return (left if left is not None else "<expr>") + (
            right if right is not None else "<expr>"
        )
    if isinstance(node, ast.Name):
        return ctx["strs"].get(node.id)
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "join"
            and isinstance(func.value, ast.Constant)
            and isinstance(func.value.value, str)
            and len(node.args) == 1
        ):
            sep = func.value.value
            arg = node.args[0]
            items = None
            if isinstance(arg, ast.Name) and arg.id in ctx["lists"]:
                items = ctx["lists"][arg.id]
            elif isinstance(arg, ast.List) and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str)
                for e in arg.elts
            ):
                items = [e.value for e in arg.elts]
            if items is not None:
                return sep.join(items)
        return None
    return None


def _collect_var_context(func: ast.AST) -> dict:
    """First (base) string/list-of-strings assignment per local name.

    Only the first assignment to a name is kept: every WHERE-clause builder
    in this codebase starts with the required `user_id = %s` term and only
    ever *adds* more conditions afterward (e.g. an optional `criterion`
    filter), so the base assignment is the maximally-permissive form worth
    checking.
    """
    ctx: dict = {"strs": {}, "lists": {}}

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, ast.Assign)
                and len(child.targets) == 1
                and isinstance(child.targets[0], ast.Name)
            ):
                name = child.targets[0].id
                value = child.value
                if name not in ctx["strs"]:
                    resolved = _resolve(value, ctx)
                    if resolved is not None:
                        ctx["strs"][name] = resolved
                if name not in ctx["lists"] and isinstance(value, ast.List):
                    if all(
                        isinstance(e, ast.Constant) and isinstance(e.value, str)
                        for e in value.elts
                    ):
                        ctx["lists"][name] = [e.value for e in value.elts]
            walk(child)

    walk(func)
    return ctx


def _sql_statements(module) -> list[tuple[str, str]]:
    """Return (function_name, resolved_sql) for every SQL-shaped literal."""
    src = inspect.getsource(module)
    tree = ast.parse(src)
    found: list[tuple[str, str]] = []

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        ctx = _collect_var_context(func)
        candidates: list[str] = []

        class _Collector(ast.NodeVisitor):
            def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
                resolved = _resolve(node, ctx)
                if resolved is not None:
                    candidates.append(resolved)

            def visit_Constant(self, node: ast.Constant) -> None:
                if isinstance(node.value, str):
                    candidates.append(node.value)

            def visit_BinOp(self, node: ast.BinOp) -> None:
                if isinstance(node.op, ast.Add):
                    resolved = _resolve(node, ctx)
                    if resolved is not None:
                        candidates.append(resolved)
                        return  # avoid double-counting the operands
                self.generic_visit(node)

        _Collector().visit(func)
        for text in candidates:
            # Real SQL literals in this codebase never contain a raw newline
            # (each source-level fragment is its own single-line string);
            # requiring that plus a keyword-at-word-boundary match rules out
            # multi-line docstrings and identifiers like "updated_at" that
            # merely start with a keyword substring.
            if "\n" not in text and _SQL_START.match(text):
                found.append((module.__name__, text))
    return found


@pytest.mark.parametrize("module", MODULES)
def test_every_per_user_query_filters_by_user_id(module):
    """No SELECT/UPDATE/DELETE touches a per-user table without scoping to user_id."""
    offenders = []
    statements = _sql_statements(module)
    assert statements, f"scan found zero SQL statements in {module.__name__}"
    for mod_name, sql in statements:
        collapsed = " ".join(sql.split()).lower()
        touches_user_table = any(t in collapsed for t in PER_USER_TABLES)
        if touches_user_table and "user_id" not in collapsed:
            offenders.append(f"{mod_name}: {collapsed[:120]}")
    assert not offenders, "unscoped queries against per-user tables:\n" + "\n".join(
        offenders
    )


def test_scan_covers_known_per_user_queries():
    """Guard against the scan silently matching nothing (a false green bar).

    Each module is known, by manual reading, to contain at least this many
    SELECT/UPDATE/DELETE statements against a per-user table. If the scan
    finds fewer, it stopped matching real code and the test above would pass
    for the wrong reason rather than because isolation actually holds.
    """
    minimum_hits = {
        evidence_service: 5,  # _fetch_one, list_evidence, count_satisfied_criteria,
        # update_evidence, delete_evidence, _find_user_profile_by_id
        market_service: 2,  # get_profile, list_outreach_log
        account: 3,  # user_profile, o1_evidence, outreach_log, session_artifacts
        supabase_client: 5,  # fetch_traces, fetch_artifacts, fetch_artifact_content,
        # session_owner (x2), user_cost_usd, user_event_count
    }
    for module, minimum in minimum_hits.items():
        statements = _sql_statements(module)
        hits = [
            sql
            for _mod_name, sql in statements
            if any(t in " ".join(sql.split()).lower() for t in PER_USER_TABLES)
        ]
        assert len(hits) >= minimum, (
            f"{module.__name__}: expected at least {minimum} per-user-table "
            f"queries, scan found {len(hits)}: {hits}"
        )
