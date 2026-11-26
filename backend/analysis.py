"""Static observations on an in-memory, redacted repository snapshot."""

import ast
import hashlib
import itertools
import posixpath
import re
import uuid
from bisect import bisect_right
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import PurePosixPath

LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".md": "Markdown",
    ".json": "JSON",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".css": "CSS",
    ".html": "HTML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".sql": "SQL",
}
VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}
JS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")


def _span(name, kind, first, last):
    return {"name": name, "kind": kind, "start_line": first, "end_line": last}


def _import(specifier, first, last):
    return {"specifier": specifier, "start_line": first, "end_line": last}


def _python(tree, result):
    constructors = {}
    namespaces = {}
    nodes = list(ast.walk(tree))
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            modules = (
                [base] if node.module else [base + alias.name for alias in node.names]
            )
            for specifier in modules:
                result["imports"].append(
                    _import(specifier, node.lineno, node.end_lineno)
                )
            if not node.level and node.module in {"flask", "fastapi"}:
                for alias in node.names:
                    constructors[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(
                    _import(alias.name, node.lineno, node.end_lineno)
                )
                namespaces[alias.asname or alias.name] = alias.name

    routers = set()
    for node in nodes:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(
            node.value, ast.Call
        ):
            continue
        call = node.value.func
        origin = None
        if isinstance(call, ast.Name):
            origin = constructors.get(call.id)
        elif isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name):
            origin = (namespaces.get(call.value.id), call.attr)
        if origin in {
            ("fastapi", "FastAPI"),
            ("fastapi", "APIRouter"),
            ("flask", "Flask"),
            ("flask", "Blueprint"),
        }:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            routers.update(
                target.id for target in targets if isinstance(target, ast.Name)
            )

    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    method_ids = {
        id(child)
        for node in nodes
        if isinstance(node, ast.ClassDef)
        for child in node.body
        if isinstance(child, functions)
    }
    for node in nodes:
        if not isinstance(node, (*functions, ast.ClassDef)):
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        if id(node) in method_ids:
            kind = "method"
        first = min((dec.lineno for dec in node.decorator_list), default=node.lineno)
        result["symbols"].append(_span(node.name, kind, first, node.end_lineno))
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            receiver, verb = dec.func.value, dec.func.attr
            if (
                not isinstance(receiver, ast.Name)
                or receiver.id not in routers
                or verb not in VERBS
            ):
                continue
            if (
                dec.args
                and isinstance(dec.args[0], ast.Constant)
                and isinstance(dec.args[0].value, str)
            ):
                result["routes"].append(
                    _span(
                        f"{verb.upper()} {dec.args[0].value}",
                        "route",
                        dec.lineno,
                        dec.end_lineno,
                    )
                )

    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            result["exports"] = [
                item.value
                for item in node.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            ]


@lru_cache(maxsize=3)
def _grammar(kind):
    from tree_sitter import Language

    if kind == "js":
        import tree_sitter_javascript

        return Language(tree_sitter_javascript.language())
    import tree_sitter_typescript

    factory = (
        tree_sitter_typescript.language_tsx
        if kind == "tsx"
        else tree_sitter_typescript.language_typescript
    )
    return Language(factory())


def _walk(root):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.named_children))


def _value(node):
    return node.text.decode("utf-8") if node is not None else ""


def _string(node):
    if node is not None and node.type == "string":
        value = _value(node)[1:-1]
        if "\\" not in value and "\n" not in value:
            return value
    return None


def _javascript(path, text, result):
    from tree_sitter import Parser

    kind = "js" if result["language"] == "JavaScript" else "ts"
    if path.endswith(".tsx"):
        kind = "tsx"
    root = Parser(_grammar(kind)).parse(text.encode("utf-8")).root_node
    result["parsed"] = not root.has_error
    kinds = {
        "class_declaration": "class",
        "abstract_class_declaration": "class",
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
    }
    for node in _walk(root):
        first = node.start_point.row + 1
        last = node.end_point.row + (1 if node.end_point.column else 0)
        last = max(first, last)
        symbol = kinds.get(node.type)
        field = node.child_by_field_name
        if node.type == "variable_declarator":
            value = field("value")
            if value and value.type in {
                "arrow_function",
                "function_expression",
                "generator_function",
            }:
                symbol = "function"
        if symbol and field("name"):
            result["symbols"].append(_span(_value(field("name")), symbol, first, last))
        if node.type in {"import_statement", "export_statement"}:
            spec = _string(field("source"))
            if spec:
                result["imports"].append(_import(spec, first, last))
        if node.type == "export_statement":
            declaration = field("declaration")
            if declaration is not None:
                if name := declaration.child_by_field_name("name"):
                    result["exports"].append(_value(name))
                for child in declaration.named_children:
                    if child.type == "variable_declarator":
                        result["exports"].append(
                            _value(child.child_by_field_name("name"))
                        )
            if any(child.type == "default" for child in node.children):
                result["exports"].append("default")
        if node.type == "export_specifier":
            result["exports"].append(_value(field("alias") or field("name")))
        if node.type == "call_expression":
            args = field("arguments")
            if (
                args
                and args.named_child_count == 1
                and _value(field("function")) in {"require", "import"}
            ):
                spec = _string(args.named_children[0])
                if spec:
                    result["imports"].append(_import(spec, first, last))


def analyze(path, text):
    language = LANGUAGES.get(PurePosixPath(path).suffix.lower(), "Text")
    result = {
        "language": language,
        "parsed": False,
        "symbols": [],
        "imports": [],
        "routes": [],
        "exports": [],
    }
    if language == "Python":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            return result
        _python(tree, result)
        result["parsed"] = True
    elif language in {"JavaScript", "TypeScript"}:
        _javascript(path, text, result)
    result["symbols"].sort(key=lambda item: (item["start_line"], -item["end_line"]))
    return result


def resolve_import(path, specifier, paths):
    """Resolve only paths present in this snapshot. Package aliases need project configuration."""
    available = paths if isinstance(paths, (set, frozenset, dict)) else set(paths)
    folder = posixpath.dirname(path)
    if path.endswith(".py"):
        dots = len(specifier) - len(specifier.lstrip("."))
        module = specifier[dots:].replace(".", "/")
        if dots:
            for _ in range(dots - 1):
                if not folder:
                    return None
                folder = posixpath.dirname(folder)
            bases = [posixpath.join(folder, module)]
        else:
            bases = [module, posixpath.join("src", module)]
        candidates = [
            item
            for base in bases
            for item in (base + ".py", posixpath.join(base, "__init__.py"))
        ]
    else:
        if not specifier.startswith(("./", "../")):
            return None
        base = posixpath.normpath(posixpath.join(folder, specifier))
        candidates = [base]
        if base.endswith(".js") and path.endswith((".ts", ".tsx")):
            candidates += [base[:-3] + extension for extension in (".ts", ".tsx")]
        candidates += [base + extension for extension in JS_EXTENSIONS]
        candidates += [
            posixpath.join(base, "index" + extension) for extension in JS_EXTENSIONS
        ]
    return next((item for item in candidates if item in available), None)


def chunks(repo_id, commit, path, text, analysis, max_chars=3200):
    """Partition source by syntax boundaries, then overlap bounded windows within a partition."""
    if max_chars < 32:
        raise ValueError("max_chars must be at least 32")
    if not text.strip():
        return []
    starts = [0, *(match.end() for match in re.finditer(r"\r\n|\n|\r", text))]
    boundaries = {0, len(text)}
    named = defaultdict(list)
    for symbol in analysis["symbols"]:
        first = starts[symbol["start_line"] - 1]
        last = (
            starts[symbol["end_line"]]
            if symbol["end_line"] < len(starts)
            else len(text)
        )
        named[first].append((last, symbol["name"]))
        boundaries.update((first, last))
    positions = sorted(boundaries)
    output = []
    active = []
    overlap = min(180, max_chars // 8)
    for left, right in itertools.pairwise(positions):
        active = [entry for entry in active if entry[0] > left]
        active.extend(named.get(left, []))
        symbol_name = min(active)[1] if active else None
        cursor = left
        while cursor < right:
            end = min(cursor + max_chars, right)
            if end < right:
                newline = bisect_right(starts, end) - 1
                if starts[newline] > cursor + max_chars // 2:
                    end = starts[newline]
            content = text[cursor:end]
            if content.strip():
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                key = f"{repo_id}\0{commit}\0{path}\0{cursor}\0{content_hash}"
                output.append(
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                        "content_hash": content_hash,
                        "path": path,
                        "language": analysis["language"],
                        "symbol": symbol_name,
                        "start_line": bisect_right(starts, cursor),
                        "end_line": bisect_right(starts, end - 1),
                        "text": content,
                    }
                )
            if end == right:
                break
            next_offset = end - overlap
            next_line = starts[bisect_right(starts, next_offset) - 1]
            cursor = (
                next_line
                if next_line > cursor and end - next_line <= overlap * 2
                else next_offset
            )
    return output


def impact(path, edges):
    """Return shortest observed import distances, excluding the selected file itself."""
    outgoing = defaultdict(set)
    incoming = defaultdict(set)
    for source, target in edges:
        incoming[target].add(source)
        outgoing[source].add(target)

    def distances(graph):
        queue = deque([path])
        visited = {path: 0}
        while queue:
            current = queue.popleft()
            for neighbor in sorted(graph[current]):
                if neighbor not in visited:
                    visited[neighbor] = visited[current] + 1
                    queue.append(neighbor)
        del visited[path]
        return visited

    return {"dependants": distances(incoming), "dependencies": distances(outgoing)}
