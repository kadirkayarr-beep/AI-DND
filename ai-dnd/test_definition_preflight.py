"""Source-only checks for methods that Python would silently overwrite."""

import ast
from pathlib import Path


class _ClassMethods(ast.NodeVisitor):
    """Collect one class namespace, excluding function and nested-class scopes."""

    def __init__(self):
        self.methods = []

    def visit_FunctionDef(self, node):
        self.methods.append(node)

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

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            collector = _ClassMethods()
            for statement in node.body:
                collector.visit(statement)
            first_lines = {}
            for method in collector.methods:
                if method.name in first_lines:
                    errors.append(
                        f"{path}:{method.lineno}: duplicate method "
                        f"{node.name}.{method.name} "
                        f"(first defined at line {first_lines[method.name]}, "
                        f"redefined at line {method.lineno}); "
                        "rename or remove the duplicate definition"
                    )
                else:
                    first_lines[method.name] = method.lineno
    return errors
