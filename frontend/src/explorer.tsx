import { useEffect, useRef, useState } from "react";
import { Link as LinkIcon, Copy, FileCode2, Folder, X } from "lucide-react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/python/python.contribution";
import "monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution";
import "monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution";
import "monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution";
import Worker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { api, errorText, type Repo } from "./api";
import { Button, Loading, Notice } from "./ui";
self.MonacoEnvironment = { getWorker: () => new Worker() };
export type Selection = {
  path: string;
  start?: number;
  end?: number;
  sha?: string;
};
type Tree = { files: string[]; dirs: Map<string, Tree> };
function entries(paths: string[]): Tree {
  const root: Tree = { files: [], dirs: new Map() };
  for (const path of paths) {
    let node = root;
    const segments = path.split("/");
    for (const dir of segments.slice(0, -1)) {
      if (!node.dirs.has(dir))
        node.dirs.set(dir, { files: [], dirs: new Map() });
      node = node.dirs.get(dir)!;
    }
    node.files.push(path);
  }
  return root;
}
function TreeView({
  node,
  select,
  expanded,
  selected,
}: {
  node: Tree;
  select: (p: string) => void;
  expanded: boolean;
  selected?: string;
}) {
  return (
    <>
      {[...node.dirs]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([dir, child]) => (
          <details open={expanded || undefined} key={dir}>
            <summary>
              <Folder size={14} />
              {dir}
            </summary>
            <div className="tree-indent">
              <TreeView
                node={child}
                select={select}
                expanded={expanded}
                selected={selected}
              />
            </div>
          </details>
        ))}
      {node.files.sort().map((p) => (
        <button
          className={p === selected ? "selected" : ""}
          key={p}
          onClick={() => select(p)}
          title={p}
        >
          <FileCode2 size={14} />
          {p.split("/").at(-1)}
        </button>
      ))}
    </>
  );
}
function Code({
  text,
  language,
  selection,
}: {
  text: string;
  language: string;
  selection: Selection;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const editor = monaco.editor.create(ref.current, {
      value: text,
      language: language.toLowerCase(),
      readOnly: true,
      domReadOnly: true,
      theme: "vs-dark",
      automaticLayout: true,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      fontSize: 13,
      wordWrap: "on",
      ariaLabel: "Source of " + selection.path,
    });
    if (selection.start) {
      editor.createDecorationsCollection([
        {
          range: new monaco.Range(
            selection.start,
            1,
            selection.end || selection.start,
            1,
          ),
          options: { isWholeLine: true, className: "source-highlight" },
        },
      ]);
      editor.revealLineInCenter(selection.start);
    }
    const model = editor.getModel();
    return () => {
      editor.dispose();
      model?.dispose();
    };
  }, [text, language, selection]);
  return <div ref={ref} className="monaco-pane" />;
}
export default function Explorer({
  repo,
  selection,
  select,
  ask,
  notify,
}: {
  repo: Repo;
  selection: Selection | null;
  select: (p: Selection | null) => void;
  ask: (p: string) => void;
  notify: (m: string) => void;
}) {
  const [query, setQuery] = useState(""),
    [tabs, setTabs] = useState<string[]>([]),
    [file, setFile] = useState<{
      path: string;
      text: string;
      language: string;
    } | null>(null),
    [error, setError] = useState("");
  const path = selection?.path;
  useEffect(() => {
    if (!path) return;
    setTabs((old) => (old.includes(path) ? old : [...old, path]));
    let active = true;
    setFile(null);
    setError("");
    api<{ path: string; text: string; language: string }>(
      "/repos/" + repo.id + "/file?path=" + encodeURIComponent(path),
    )
      .then((v) => active && setFile(v))
      .catch((e) => active && setError(errorText(e)));
    return () => {
      active = false;
    };
  }, [path, repo.id, repo.sha]);
  const tree = entries(
    repo.files
      .map((f) => f.path)
      .filter((p) => p.toLowerCase().includes(query.toLowerCase())),
  );
  return (
    <>
      <div className="explorer-layout">
        <aside className="tree">
          <input
            aria-label="Filter repository files"
            placeholder="Find a file…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <TreeView
            node={tree}
            select={(p) => select({ path: p })}
            expanded={!!query}
            selected={path}
          />
        </aside>
        <section className="code-panel">
          <div className="tabs">
            {tabs.map((p) => (
              <span key={p} className={p === path ? "active" : ""}>
                <button onClick={() => select({ path: p })}>
                  {p.split("/").at(-1)}
                </button>
                <button
                  aria-label={"Close " + p}
                  onClick={() => {
                    const left = tabs.filter((t) => t !== p);
                    setTabs(left);
                    if (p === path)
                      select(left.length ? { path: left.at(-1)! } : null);
                  }}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
          {!path ? (
            <div className="empty">
              Select an indexed file to read its source.
            </div>
          ) : error ? (
            <Notice>{error}</Notice>
          ) : file?.path !== path ? (
            <Loading label="Fetching source" />
          ) : (
            <>
              <div className="code-meta">
                <code>{path}</code>
                <small>
                  {file.language} ·{" "}
                  {repo.files.find((f) => f.path === path)?.lines} lines
                </small>
              </div>
              <div className="code-actions">
                <Button
                  variant="quiet"
                  onClick={() =>
                    navigator.clipboard
                      .writeText(file.text)
                      .then(() => notify("Source copied"))
                      .catch(() => notify("Clipboard permission is required"))
                  }
                >
                  <Copy size={14} />
                  Copy
                </Button>
                <Button asChild variant="quiet">
                  <a
                    target="_blank"
                    rel="noreferrer"
                    href={
                      repo.url.replace(/\.git\/?$|\/$/g, "") +
                      "/blob/" +
                      repo.sha +
                      "/" +
                      path.split("/").map(encodeURIComponent).join("/") +
                      (selection?.start ? "#L" + selection.start : "")
                    }
                  >
                    <LinkIcon size={14} />
                    GitHub
                  </a>
                </Button>
                <Button variant="quiet" onClick={() => ask(path)}>
                  Ask about file
                </Button>
              </div>
              <Code
                text={file.text}
                language={file.language}
                selection={selection!}
              />
            </>
          )}
        </section>
      </div>
    </>
  );
}
