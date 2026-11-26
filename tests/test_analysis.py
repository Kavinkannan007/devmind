import unittest

from backend.analysis import analyze, chunks, impact, resolve_import


class AnalysisTests(unittest.TestCase):
    def test_python_declarations_routes_exports_and_lines(self):
        text = """from fastapi import FastAPI as API
from . import model
app = API()
__all__ = ['fetch']
@app.get('/items')
async def fetch():
    return model.items
class Storage:
    def save(self): pass
"""
        observed = analyze("api.py", text)
        self.assertTrue(observed["parsed"])
        self.assertEqual(
            observed["symbols"],
            [
                {"name": "fetch", "kind": "function", "start_line": 5, "end_line": 7},
                {"name": "Storage", "kind": "class", "start_line": 8, "end_line": 9},
                {"name": "save", "kind": "method", "start_line": 9, "end_line": 9},
            ],
        )
        self.assertEqual(observed["routes"][0]["name"], "GET /items")
        self.assertEqual(observed["exports"], ["fetch"])
        self.assertEqual(
            [entry["specifier"] for entry in observed["imports"]], ["fastapi", ".model"]
        )

    def test_syntax_errors_and_plain_text(self):
        for path, text in [("file.py", "def fn("), ("notes.md", "# notes")]:
            self.assertFalse(analyze(path, text)["parsed"])
            self.assertEqual(
                chunks("r", "c", path, text, analyze(path, text))[0]["text"], text
            )

    def test_tree_sitter_js_ts_jsx(self):
        for path, source in [
            ("app.js", "export const run = () => require('./lib');"),
            ("app.ts", "export const run = (): string => require('./lib');"),
            ("app.tsx", "import './lib'; export const run = () => <div/>;"),
        ]:
            with self.subTest(path=path):
                result = analyze(path, source)
                self.assertTrue(result["parsed"])
                self.assertEqual(result["symbols"][0]["name"], "run")
                self.assertEqual(result["imports"][0]["specifier"], "./lib")
                self.assertEqual(result["exports"], ["run"])

    def test_chunk_identity_coverage_cap_and_line_numbers(self):
        text = (
            'from .lib import read\r\n\r\ndef run():\r\n    return "'
            + "猫" * 160
            + '"\r\n'
        )
        observed = analyze("a.py", text)

        def split(commit):
            return chunks("repo", commit, "a.py", text, observed, max_chars=40)

        rows = split("one")
        self.assertEqual(rows, split("one"))
        self.assertNotEqual(rows[0]["id"], split("two")[0]["id"])
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        for row in rows:
            self.assertLessEqual(len(row["text"]), 40)
            cited = "".join(
                text.splitlines(keepends=True)[row["start_line"] - 1 : row["end_line"]]
            )
            self.assertIn(row["text"], cited)
        self.assertTrue(any(row["symbol"] == "run" for row in rows))
        self.assertEqual(rows[-1]["end_line"], 4)

    def test_relative_imports(self):
        files = {
            "src/pkg/util.py",
            "src/ui/index.tsx",
            "src/types.ts",
            "src/pkg/__init__.py",
        }
        self.assertEqual(
            resolve_import("src/pkg/api.py", ".util", files), "src/pkg/util.py"
        )
        self.assertEqual(
            resolve_import("server.py", "pkg.util", files), "src/pkg/util.py"
        )
        self.assertEqual(
            resolve_import("src/api.ts", "./ui", files), "src/ui/index.tsx"
        )
        self.assertEqual(
            resolve_import("src/api.ts", "./types.js", files), "src/types.ts"
        )
        self.assertIsNone(resolve_import("src/api.ts", "@org/library", files))
        self.assertIsNone(resolve_import("pkg/a.py", "...util", files))

    def test_cycle_safe_shortest_paths(self):
        graph = [("a", "b"), ("b", "c"), ("c", "a"), ("d", "b"), ("a", "a")]
        self.assertEqual(
            impact("b", graph),
            {
                "dependencies": {"c": 1, "a": 2},
                "dependants": {"a": 1, "d": 1, "c": 2},
            },
        )
