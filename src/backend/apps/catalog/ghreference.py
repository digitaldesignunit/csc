#!/usr/bin/env python3.13
"""
The component reference of the Grasshopper interface, read from the sources
of a release (plan P11 stage 3, decision 8.118 C-5; conventions of 8.112).

A source is only ever PARSED with ``ast``: it is never imported, executed or
evaluated. Values are read with ``ast.literal_eval`` on the syntax tree of an
assignment, which accepts constants and containers of constants and nothing
else. A source that does not parse is skipped with a note, never an error.

What a source says, by the conventions of the ``DDU_CSC_*.py`` files:

* name, nickname, category, subcategory, description: the module-level
  ``ghenv.Component.<Field> = '...'`` assignments;
* outputs: the module-level ``OUTPUTS = [(name, nickname, description), ...]``
  (the order is the order RunScript returns them in, 8.112); ``outputs_declared``
  says whether the source has an ``OUTPUTS`` at all, so "no outputs" (declared
  and empty) is told apart from "not declared" (a 0.5 source);
* inputs: the parameters of ``RunScript`` after ``self``, each with the
  ``self.InputParams[i].Description = '...'`` that ``BeforeRunScript`` sets;
* version: the ``Version:`` line of the class docstring.

Pure functions over text; no network, no database.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import ast
import re
from typing import Any, Dict, List, Optional

COMPONENT_FIELDS = ('Name', 'NickName', 'Category', 'SubCategory', 'Description')
VERSION_LINE_RE = re.compile(r'^\s*Version:\s*(\S+)\s*$', re.M | re.I)


def _literal(node: ast.AST) -> Any:
    """The value of a literal node, or None when it is anything else."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def _text(value: Any) -> str:
    return ' '.join(value.split()) if isinstance(value, str) else ''


def _is_ghenv_field(target: ast.AST) -> Optional[str]:
    """``ghenv.Component.<Field>`` -> the field name."""
    if (isinstance(target, ast.Attribute)
            and target.attr in COMPONENT_FIELDS
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == 'Component'
            and isinstance(target.value.value, ast.Name)
            and target.value.value.id == 'ghenv'):
        return target.attr
    return None


def _input_description_index(target: ast.AST) -> Optional[int]:
    """``self.InputParams[i].Description`` -> i."""
    if not (isinstance(target, ast.Attribute) and target.attr == 'Description'):
        return None
    sub = target.value
    if not (isinstance(sub, ast.Subscript)
            and isinstance(sub.value, ast.Attribute)
            and sub.value.attr == 'InputParams'):
        return None
    index = _literal(sub.slice)
    return index if isinstance(index, int) and index >= 0 else None


def _outputs(value: Any) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not isinstance(value, (list, tuple)):
        return rows
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) >= 1:
            name = _text(item[0])
            if not name:
                continue
            rows.append({
                'name': name,
                'nickname': _text(item[1]) if len(item) > 1 else name,
                'description': _text(item[2]) if len(item) > 2 else '',
            })
    return rows


def parse_source(filename: str, text: str) -> Dict[str, Any]:
    """The reference entry of one source, or ``{'file': ..., 'skipped': note}``."""
    stem = filename.rsplit('.', 1)[0]
    try:
        tree = ast.parse(text, filename=filename)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        return {'file': filename, 'skipped': f'not parsed: {type(exc).__name__}'}

    fields: Dict[str, str] = {}
    outputs: List[Dict[str, str]] = []
    outputs_declared = False
    descriptions: Dict[int, str] = {}
    parameters: List[str] = []
    version = ''

    for node in tree.body:                    # module level only
        if isinstance(node, ast.Assign):
            for target in node.targets:
                field = _is_ghenv_field(target)
                if field:
                    fields[field] = _text(_literal(node.value))
                elif isinstance(target, ast.Name) and target.id == 'OUTPUTS':
                    outputs = _outputs(_literal(node.value))
                    outputs_declared = True
        elif (isinstance(node, ast.AnnAssign) and node.value is not None
                and isinstance(node.target, ast.Name)
                and node.target.id == 'OUTPUTS'):
            outputs = _outputs(_literal(node.value))
            outputs_declared = True
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ''
            match = VERSION_LINE_RE.search(doc)
            if match and not version:
                version = match.group(1)
            for item in node.body:
                if not isinstance(item, ast.FunctionDef):
                    continue
                if item.name == 'RunScript':
                    parameters = [a.arg for a in item.args.args][1:]
                elif item.name == 'BeforeRunScript':
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Assign):
                            for target in sub.targets:
                                index = _input_description_index(target)
                                if index is not None:
                                    descriptions[index] = _text(_literal(sub.value))

    if not fields.get('Name') and not outputs and not parameters:
        return {'file': filename, 'skipped': 'not a component source'}
    return {
        'file': filename,
        'name': fields.get('Name') or stem,
        'nickname': fields.get('NickName') or fields.get('Name') or stem,
        'category': fields.get('Category', ''),
        'subcategory': fields.get('SubCategory', ''),
        'description': fields.get('Description', ''),
        'version': version,
        'inputs': [
            {'name': name, 'description': descriptions.get(i, '')}
            for i, name in enumerate(parameters)
        ],
        'outputs': outputs,
        'outputs_declared': outputs_declared,
    }


def _sort_key(entry: Dict[str, Any]):
    """The page's order: by subcategory (they start with a number), then name."""
    return (entry.get('subcategory') or '~', (entry.get('name') or '').lower())


def build_reference(ref: str, parsed: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The one JSON the page reads: the components of a release, the sources
    that were skipped and why."""
    components = sorted((p for p in parsed if 'skipped' not in p), key=_sort_key)
    skipped = [{'file': p['file'], 'note': p['skipped']}
               for p in parsed if 'skipped' in p]
    return {'ref': ref, 'components': components, 'skipped': skipped}
