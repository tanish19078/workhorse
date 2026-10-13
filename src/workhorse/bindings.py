"""Conservative Python binding identities from the standard-library symbol table."""

import ast
import symtable


def python_bindings(source: str) -> dict[tuple[int, int], str]:
    """Map identifier positions to scope-local identities; preserve external names."""
    try:
        tree = ast.parse(source)
        root = symtable.symtable(source, "<submission>", "exec")
    except SyntaxError as exc:
        raise ValueError(f"Cannot parse Python bindings: {exc.msg}") from exc
    scope_ids = {}
    parents = {}
    slots = {}
    tables = {}

    def register(table, parent=None):
        tables[id(table)] = table  # Keep symtable's weakly cached wrappers alive.
        scope_ids[id(table)] = len(scope_ids)
        parents[id(table)] = parent
        bound = [name for name in table.get_identifiers()
                 if (table.lookup(name).is_assigned() or table.lookup(name).is_parameter()
                     or table.lookup(name).is_namespace()) and not table.lookup(name).is_imported()]
        slots[id(table)] = {name: index for index, name in enumerate(bound)}
        for child in table.get_children():
            register(child, table)

    register(root)
    result = {}
    used_children = set()
    virtual_scopes = [len(scope_ids)]
    lines = source.splitlines()

    def position(node):
        # AST columns count UTF-8 bytes; tokenize columns count Unicode characters.
        column = len(lines[node.lineno - 1].encode()[:node.col_offset].decode())
        return node.lineno, column

    def identity(table, name):
        try:
            symbol = table.lookup(name)
        except KeyError:
            return name
        if symbol.is_imported():
            return name
        owner = table
        if table is not root and symbol.is_global():
            owner = root
        elif symbol.is_free() or symbol.is_nonlocal():
            owner = parents[id(table)]
            while owner is not None:
                if name in slots[id(owner)] and owner.get_type() != "class":
                    break
                owner = parents[id(owner)]
        if owner is not None and name in slots[id(owner)]:
            return f"S{scope_ids[id(owner)]}:V{slots[id(owner)][name]}"
        return name

    def child(table, node, name):
        matches = [c for c in table.get_children() if c.get_name() == name
                   and c.get_lineno() == node.lineno and id(c) not in used_children]
        if len(matches) != 1:
            raise ValueError("Ambiguous Python scope; binding comparison declined")
        used_children.add(id(matches[0]))
        return matches[0]

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.table = root
            self.overrides = {}

        def visit_Name(self, node):
            result[position(node)] = self.overrides.get(node.id, identity(self.table, node.id))

        def visit_Global(self, node):
            import re
            line, column = position(node)
            for match in re.finditer(r"\b\w+\b", lines[line - 1][column:]):
                if match.group() in node.names:
                    result[(line, column + match.start())] = identity(self.table, match.group())

        visit_Nonlocal = visit_Global

        def declaration(self, node, name):
            line, column = position(node)
            # Name follows def/class; search only the declaration prefix.
            prefix = lines[line - 1][column:]
            import re
            match = re.search(r"(?:def|class)\s+(" + re.escape(name) + r")\b", prefix)
            if match:
                result[(line, column + match.start(1))] = identity(self.table, name)

        def visit_FunctionDef(self, node):
            self.declaration(node, node.name)
            for item in node.decorator_list + node.args.defaults + [d for d in node.args.kw_defaults if d]:
                self.visit(item)
            if node.returns:
                self.visit(node.returns)
            parameters = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            parameters += [a for a in (node.args.vararg, node.args.kwarg) if a]
            for parameter in parameters:
                if parameter.annotation:
                    self.visit(parameter.annotation)
            previous = self.table
            previous_overrides = self.overrides
            self.table = child(previous, node, node.name)
            self.overrides = {name: value for name, value in previous_overrides.items()
                              if not (name in self.table.get_identifiers() and
                                      (self.table.lookup(name).is_local() or self.table.lookup(name).is_global()))}
            for parameter in parameters:
                result[position(parameter)] = identity(self.table, parameter.arg)
            for statement in node.body:
                self.visit(statement)
            self.table = previous
            self.overrides = previous_overrides

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            self.declaration(node, node.name)
            for item in node.decorator_list + node.bases + [k.value for k in node.keywords]:
                self.visit(item)
            previous = self.table
            self.table = child(previous, node, node.name)
            for statement in node.body:
                self.visit(statement)
            self.table = previous

        def visit_Lambda(self, node):
            for item in node.args.defaults + [d for d in node.args.kw_defaults if d]:
                self.visit(item)
            previous = self.table
            previous_overrides = self.overrides
            self.table = child(previous, node, "lambda")
            self.overrides = {name: value for name, value in previous_overrides.items()
                              if not (name in self.table.get_identifiers() and
                                      (self.table.lookup(name).is_local() or self.table.lookup(name).is_global()))}
            parameters = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            parameters += [a for a in (node.args.vararg, node.args.kwarg) if a]
            for parameter in parameters:
                result[position(parameter)] = identity(self.table, parameter.arg)
            self.visit(node.body)
            self.table = previous
            self.overrides = previous_overrides

        def comprehension(self, node, name):
            if any(isinstance(n, ast.NamedExpr) for n in ast.walk(node)):
                raise ValueError("Assignment expressions inside comprehensions need manual review")
            self.visit(node.generators[0].iter)
            previous = self.table
            overrides = self.overrides
            matches = [c for c in previous.get_children() if c.get_name() == name and c.get_lineno() == node.lineno]
            if matches:
                self.table = child(previous, node, name)
            # Python 3.12+ inlines many comprehensions. Use explicit AST-local
            # target identities on every runtime instead of assuming a child table.
            scope = virtual_scopes[0]
            virtual_scopes[0] += 1
            names = []
            for generator in node.generators:
                for target in ast.walk(generator.target):
                    if isinstance(target, ast.Name) and target.id not in names:
                        names.append(target.id)
            self.overrides = {**overrides, **{n: f"C{scope}:V{i}" for i, n in enumerate(names)}}
            for index, generator in enumerate(node.generators):
                if index:
                    self.visit(generator.iter)
                self.visit(generator.target)
                for condition in generator.ifs:
                    self.visit(condition)
            if isinstance(node, ast.DictComp):
                self.visit(node.key)
                self.visit(node.value)
            else:
                self.visit(node.elt)
            self.table = previous
            self.overrides = overrides

        def visit_ListComp(self, node):
            self.comprehension(node, "listcomp")

        def visit_SetComp(self, node):
            self.comprehension(node, "setcomp")

        def visit_DictComp(self, node):
            self.comprehension(node, "dictcomp")

        def visit_GeneratorExp(self, node):
            self.comprehension(node, "genexpr")

    Visitor().visit(tree)
    return result
