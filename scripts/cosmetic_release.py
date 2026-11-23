"""Recognize presentation changes that can use focused release checks."""
import ast
import re

# These modules use widget_text.localized to bind static captions to Qt widget properties.
PRESENTATION_MODULES = {
    f'director_control/{name}.py' for name in
    ('analytics_ui', 'backup_ui', 'calendar_view', 'diagnostics_ui', 'history_ui',
     'inspector', 'mail_ui', 'mini_calendar', 'ui', 'update_ui')
}
PRESENTATION_PROPERTIES = {'text', 'title', 'toolTip', 'placeholderText', 'accessibleName', 'windowTitle'}


def _parse(source):
    if not isinstance(source, str):
        raise ValueError('Both versions of an existing source file are required')
    # Honor Python source encoding declarations as the interpreter would.
    return ast.parse(source.encode('utf-8'))


def _string(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _catalog(tree):
    body = tree.body[1:] if ast.get_docstring(tree, clean=False) is not None else tree.body
    if len(body) != 1:
        return None
    match body[0]:
        case ast.Assign(targets=[ast.Name(id='MESSAGES')], value=ast.Dict() as entries):
            if not all(_string(node) for node in entries.keys + entries.values):
                return None
            if len({key.value for key in entries.keys}) == len(entries.keys):
                return entries
    return None


def _mask_paint_colors(tree):
    # Retain all names, keys, expressions and other code for structural comparison.
    for statement in tree.body:
        match statement:
            case ast.Assign(targets=[ast.Name(id='LIGHT' | 'DARK')], value=ast.Dict() as colors):
                for key, value in zip(colors.keys, colors.values):
                    if key is None:  # DARK inherits the light palette via **LIGHT.
                        continue
                    if not (_string(key) and _string(value) and re.fullmatch(r'#[0-9a-fA-F]{6}', value.value)):
                        raise ValueError('Ambiguous palette entry')
                    value.value = '<color>'


def _imports_localized(tree):
    direct = [item for node in tree.body if isinstance(node, ast.ImportFrom)
              and node.level == 1 and node.module == 'widget_text'
              for item in node.names if item.name == 'localized' and item.asname is None]
    if len(direct) != 1:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.alias) and node is not direct[0]:
            if node.name == '*' or (node.asname or node.name.split('.')[0]) == 'localized':
                return False
        if isinstance(node, ast.Name) and node.id == 'localized' and not isinstance(node.ctx, ast.Load):
            return False
        if (getattr(node, 'name', None) == 'localized' and not isinstance(node, ast.alias)
                or isinstance(node, ast.arg) and node.arg == 'localized'
                or isinstance(node, ast.MatchMapping) and node.rest == 'localized'):
            return False
    return True


def _mask_widget_captions(tree):
    if not _imports_localized(tree):
        return
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'localized'
                and len(node.args) == 1 and not isinstance(node.args[0], ast.Starred)):
            continue
        if all(kw.arg in PRESENTATION_PROPERTIES and _string(kw.value) for kw in node.keywords):
            for kw in node.keywords:
                kw.value.value = '<caption>'


def cosmetic_file(path, before, after):
    """Both file versions must differ exclusively in the approved presentation literals."""
    try:
        left, right = _parse(before), _parse(after)
        if ast.dump(left) == ast.dump(right):
            return False
        for tree in (left, right):
            if path == 'director_control/english.py':
                catalog = _catalog(tree)
                if catalog is None:
                    return False
                catalog.keys.clear()
                catalog.values.clear()
            elif path == 'director_control/theme.py':
                _mask_paint_colors(tree)
            elif path in PRESENTATION_MODULES:
                _mask_widget_captions(tree)
            else:
                return False
        return ast.dump(left) == ast.dump(right)
    except (ValueError, SyntaxError, RecursionError):
        return False
