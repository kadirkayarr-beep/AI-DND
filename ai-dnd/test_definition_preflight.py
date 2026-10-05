"""Source-only checks for functions that Python would silently overwrite."""

import ast
from pathlib import Path


class _NamespaceFunctions(ast.NodeVisitor):
    """Collect one namespace, excluding function and nested-class scopes.

    Control-flow blocks do not introduce namespaces, so definitions inside
    them belong to the enclosing module or class. Function bodies are opaque:
    local functions are not module functions or methods.
    """

    def __init__(self):
        self.functions = []

    def visit_FunctionDef(self, node):
        self.functions.append(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        # Nested classes are checked independently by the outer AST walk.
        pass


def check_test_definitions(paths):
    """Return all source errors; never import or execute a configured gate."""
    errors = []
    for file_path in paths:
        path = Path(file_path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{path}: cannot inspect test definitions: {exc}")
            continue

        namespaces = [tree] + [
            node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ]
        for node in namespaces:
            collector = _NamespaceFunctions()
            for statement in node.body:
                collector.visit(statement)
            first_lines = {}
            is_class = isinstance(node, ast.ClassDef)
            kind = "method" if is_class else "module function"
            for function in collector.functions:
                name = f"{node.name}.{function.name}" if is_class else function.name
                if function.name in first_lines:
                    errors.append(
                        f"{path}:{function.lineno}: duplicate {kind} "
                        f"{name} "
                        f"(first defined at line {first_lines[function.name]}, "
                        f"redefined at line {function.lineno}); "
                        "rename or remove the duplicate definition"
                    )
                else:
                    first_lines[function.name] = function.lineno
    return errors
