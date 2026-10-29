"""'Element', not 'piece' (decision 8.183): no text a user reads from the
backend says 'piece' or 'pieces'. The check reads the string literals of the
backend and the docstrings that become API documentation (routes, tools,
models); comments, other docstrings, log lines, identifiers and the cron
scripts are not user text.

Allowed: a word that is a key or a code value (``'piece'``, ``'pieces'``), part
of an id or a path, and 'piece' in another sense ('a piece of software').
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / 'src' / 'backend'
WORD = re.compile(r'\b[Pp]ieces?\b')
SKIP_DIRS = {'__pycache__', 'migration06'}
SKIP_FILES = {'main_geometry.py', 'main_component_map.py'}
OTHER_SENSE = re.compile(r'piece of (software|information|data|text|code|work|advice|paper)', re.I)
LOG_NAMES = {'log', 'logger', 'logging', 'print'}
ROUTE = re.compile(r'\b(router|mcp|app|server|api_router)\b\.|\btool\b')


class _Collector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.nodes: list[ast.Constant] = []
        self.docs: set[int] = set()

    def _doc(self, node, in_scope: bool) -> None:
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            self.docs.add(id(body[0].value))
            if in_scope:
                self.nodes.append(body[0].value)

    def visit_Module(self, node):
        self._doc(node, False)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._doc(node, any(ROUTE.search(ast.unparse(d)) for d in node.decorator_list))
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        bases = ' '.join(ast.unparse(b) for b in node.bases)
        self._doc(node, bool(re.search(r'BaseModel|_Block|_Document|RootModel', bases)))
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None)
        if name in LOG_NAMES:
            return
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and id(node) not in self.docs:
            self.nodes.append(node)


def piece_texts(source: str) -> list[tuple[int, str]]:
    """The user texts of a source that say 'piece': (line, text)."""
    collector = _Collector()
    collector.visit(ast.parse(source))
    found = []
    for node in collector.nodes:
        text = node.value
        if not isinstance(text, str) or not WORD.search(text):
            continue
        if re.fullmatch(r'\s*[Pp]ieces?\s*', text):                     # a key or a code value
            continue
        if re.search(r'[-_/][Pp]ieces?\b|\b[Pp]ieces?[-_/]', text):     # part of an id or a path
            continue
        if OTHER_SENSE.search(text):
            continue
        found.append((node.lineno, ' '.join(text.split())[:100]))
    return found


def test_no_text_of_the_backend_says_piece():
    problems = []
    for path in sorted(BACKEND.rglob('*.py')):
        if SKIP_DIRS & set(path.parts) or path.name in SKIP_FILES:
            continue
        source = path.read_text(encoding='utf-8')
        if not WORD.search(source):
            continue
        for line, text in piece_texts(source):
            problems.append(f'{path.relative_to(BACKEND).as_posix()}:{line}: {text}')
    assert not problems, 'say "element" instead:\n' + '\n'.join(problems)


def test_the_check_sees_a_message_a_route_docstring_and_a_description():
    assert piece_texts("raise ValueError('a piece cannot be cut')")
    assert piece_texts("x = Field(None, description='the pieces of a batch')")
    assert piece_texts(
        "@router.get('/x')\nasync def route():\n    \"\"\"Every piece the caller may see.\"\"\"\n")
    assert piece_texts("class M(BaseModel):\n    \"\"\"One piece on the map.\"\"\"\n")


def test_the_check_lets_a_key_an_id_a_comment_a_log_line_and_other_code_pass():
    assert not piece_texts("row = {'piece': 1, 'pieces': 2}")
    assert not piece_texts("path = '/schema/similar-pieces'")
    assert not piece_texts("# the piece is public\nx = 1")
    assert not piece_texts("log.info('the piece is public')")
    assert not piece_texts("def helper():\n    \"\"\"The piece is public.\"\"\"\n")
    assert not piece_texts("note = 'This piece of software is free'")
