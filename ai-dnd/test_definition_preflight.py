"""Source-only checks for functions that Python would silently overwrite."""

import ast
from pathlib import Path


def _same_reference(value, reference):
    if isinstance(reference, str):
        return isinstance(value, ast.Name) and value.id == reference
    return (isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.attr == reference.attr
            and value.value.id == reference.value.id)


def _preserves_function(value, name):
    """Recognize identity assignments and explicit decorator-style wrapping.

    This is a syntax allowance, not proof that a decorator returns a callable.
    Arbitrary expressions merely mentioning the old function are not exempt.
    """
    if _same_reference(value, name):
        return True
    if not isinstance(value, ast.Call) or not value.args:
        return False
    other_parts = [value.func, *value.args[1:], *value.keywords]
    if any(_same_reference(node, name)
           for part in other_parts for node in ast.walk(part)):
        return False
    return _preserves_function(value.args[0], name)


class _NamespaceFunctions(ast.NodeVisitor):
    """Collect ordered definitions and bindings in one lexical namespace.

    Control-flow blocks do not introduce namespaces, so definitions inside
    them belong to the enclosing module or class. Function bodies are opaque:
    local functions are not module functions or methods.
    """

    def __init__(self, collect_attributes=False):
        self.events = []
        self.collect_attributes = collect_attributes

    def visit_FunctionDef(self, node):
        self.events.append((node.name, node, "definition", False))

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        # Nested classes are checked independently by the outer AST walk.
        self.events.append((node.name, node, "class binding", False))

    def visit_Lambda(self, node):
        pass

    def visit_ListComp(self, node):
        # Iteration variables are local, but walrus assignments bind in the
        # enclosing namespace. Inspect expressions, never iteration targets.
        for generator in node.generators:
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            operation = "deletion" if isinstance(node.ctx, ast.Del) else "assignment"
            self.events.append((node.id, node, operation, False))

    def visit_Attribute(self, node):
        if (self.collect_attributes and isinstance(node.value, ast.Name)
                and isinstance(node.ctx, (ast.Store, ast.Del))):
            operation = "deletion" if isinstance(node.ctx, ast.Del) else "assignment"
            self.events.append((node, node, operation, False))
        self.visit(node.value)

    def _assignment(self, targets, value, node):
        if value is not None:
            self.visit(value)
        for target in targets:
            if isinstance(target, ast.Name):
                preserves = (len(targets) == 1
                             and _preserves_function(value, target.id))
                self.events.append((target.id, node, "assignment", preserves))
            elif (self.collect_attributes and isinstance(target, ast.Attribute)
                  and isinstance(target.value, ast.Name)):
                preserves = (len(targets) == 1
                             and _preserves_function(value, target))
                self.events.append((target, node, "assignment", preserves))
            else:
                self.visit(target)

    def visit_Assign(self, node):
        self._assignment(node.targets, node.value, node)

    def visit_AnnAssign(self, node):
        # A bare annotation does not replace an existing value.
        if node.value is not None:
            self._assignment([node.target], node.value, node)

    def visit_AugAssign(self, node):
        self.visit(node.value)
        self.visit(node.target)

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.events.append((name, node, "import binding", False))

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.events.append(
                (alias.asname or alias.name, node, "import binding", False)
            )

    def visit_ExceptHandler(self, node):
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.events.append((node.name, node, "exception binding", False))
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node):
        if node.pattern is not None:
            self.visit(node.pattern)
        if node.name:
            self.events.append((node.name, node, "pattern binding", False))

    def visit_MatchStar(self, node):
        if node.name:
            self.events.append((node.name, node, "pattern binding", False))

    def visit_MatchMapping(self, node):
        self.generic_visit(node)
        if node.rest:
            self.events.append((node.rest, node, "pattern binding", False))


def _check_class_writes(tree, path):
    """Check module-scope writes through local class names and simple aliases.

    Resolve only bare names introduced by a module-level class statement,
    or single-name assignments A = C (including valued annotations and alias
    chains), including statements inside control-flow blocks. Resolved names
    share class identity: rebinding one does not invalidate other aliases.
    Every other binding/deletion invalidates that name; wildcard imports clear
    all resolutions. Bare annotations do not bind. Do not resolve tuple/chained
    assignments, nested attributes, inheritance, imports, setattr/delattr,
    walrus assignments, decorators, or calls.
    Function and class bodies remain opaque here, preserving runtime patch
    fixtures. This is conservative source order, not execution/reachability.
    """
    collector = _NamespaceFunctions(collect_attributes=True)
    for statement in tree.body:
        collector.visit(statement)
    classes = {}
    errors = []
    for binding, statement, operation, preserves in collector.events:
        if isinstance(binding, ast.Attribute):
            methods = classes.get(binding.value.id, {})
            first = methods.get(binding.attr)
            if first is not None and not preserves:
                errors.append(
                    f"{path}:{statement.lineno}: attribute {operation} overwrites "
                    f"method {binding.value.id}.{binding.attr} "
                    f"(first defined at line {first}, "
                    f"rebound at line {statement.lineno}); "
                    "use a distinct name or explicit decorator assignment"
                )
        elif operation == "class binding":
            methods = _NamespaceFunctions()
            for child in statement.body:
                methods.visit(child)
            first_lines = {}
            for name, definition, action, _ in methods.events:
                if action == "definition":
                    first_lines.setdefault(name, definition.lineno)
            classes[binding] = first_lines
        elif binding == "*":
            classes.clear()
        else:
            value = getattr(statement, "value", None)
            simple_assignment = (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id == binding
            ) or (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == binding
            )
            if (operation == "assignment" and simple_assignment
                    and isinstance(value, ast.Name) and value.id in classes):
                classes[binding] = classes[value.id]
            else:
                classes.pop(binding, None)
    return errors


def check_test_definitions(paths):
    """Return source errors without importing or executing configured gates.

    Protect every module function and class method after its first definition.
    Control-flow branches are scanned conservatively in source order, without
    proving reachability. New-name aliases, same-name identity assignments, and
    single-target decorator wrapping (f = wrapper(f, ...)) are allowed. Tuple,
    chained, augmented, and unrelated assignments are not decorator allowances.
    Imports (including uncertain wildcard imports) cannot replace protected
    names. Direct module-scope writes/deletions to methods on currently bound
    same-module classes and simple module-level class aliases are also checked,
    with the same identity/wrapping allowances. Other bindings invalidate alias
    resolution without affecting existing aliases to the original class.
    Inherited methods, nested attribute paths,
    function-local/runtime patches, unrelated object attributes, comprehension
    locals, and subscripts are outside this source-only policy.
    """
    errors = []
    for file_path in paths:
        path = Path(file_path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{path}: cannot inspect test definitions: {exc}")
            continue

        errors.extend(_check_class_writes(tree, path))
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
            for binding, statement, operation, preserves in collector.events:
                affected = list(first_lines) if binding == "*" else [binding]
                if operation == "definition" and binding not in first_lines:
                    first_lines[binding] = statement.lineno
                    continue
                for local_name in affected:
                    if local_name not in first_lines or preserves:
                        continue
                    name = f"{node.name}.{local_name}" if is_class else local_name
                    if operation != "definition":
                        errors.append(
                            f"{path}:{statement.lineno}: {operation} overwrites "
                            f"{kind} {name} "
                            f"(first defined at line {first_lines[local_name]}, "
                            f"rebound at line {statement.lineno}); "
                            "use a distinct name or explicit decorator assignment"
                        )
                        continue
                    errors.append(
                        f"{path}:{statement.lineno}: duplicate {kind} "
                        f"{name} "
                        f"(first defined at line {first_lines[local_name]}, "
                        f"redefined at line {statement.lineno}); "
                        "rename or remove the duplicate definition"
                    )
    return errors
