import { useMemo, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  MarkerType,
  type Edge as FlowEdge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Repo } from "./api";
import { Button } from "./ui";
export default function Graph({
  repo,
  open,
  distances,
  focusPath,
}: {
  repo: Repo;
  open: (p: string) => void;
  distances?: Record<string, number>;
  focusPath?: string;
}) {
  const [query, setQuery] = useState(""),
    [focus, setFocus] = useState(""),
    [selected, setSelected] = useState(""),
    [kind, setKind] = useState("all"),
    [limit, setLimit] = useState(50);
  const all = useMemo(() => {
    const files = new Set(repo.files.map((f) => f.path)),
      owner = new Map<string, string>();
    const edges = repo.edges.map((e) => ({ ...e }));
    for (const s of repo.symbols) {
      const key = s.path + "::" + s.name + "@" + s.start_line;
      owner.set(key, s.path);
      edges.push({
        source: s.path,
        target: key,
        line: s.start_line,
        kind: s.kind,
      });
    }
    const names = [
      ...new Set([...files, ...edges.flatMap((e) => [e.source, e.target])]),
    ];
    return { files, owner, edges, names };
  }, [repo]);
  const kinds = [...new Set(all.edges.map((e) => e.kind))];
  const possible = all.edges.filter(
    (e) =>
      (kind === "all" || e.kind === kind) &&
      (!distances ||
        ((e.source === focusPath || Object.hasOwn(distances, e.source)) &&
          (e.target === focusPath || Object.hasOwn(distances, e.target)))),
  );
  const neighborhood = focus
    ? new Set([
        focus,
        ...possible
          .filter((e) => e.source === focus || e.target === focus)
          .flatMap((e) => [e.source, e.target]),
      ])
    : null;
  const candidates = all.names.filter(
    (n) =>
      (!distances || n === focusPath || Object.hasOwn(distances, n)) &&
      (!neighborhood || neighborhood.has(n)) &&
      (!query || n.toLowerCase().includes(query.toLowerCase())) &&
      (kind === "all" ||
        possible.some((e) => e.source === n || e.target === n)) &&
      (!all.owner.has(n) || !!focus || kind !== "all" || !!query),
  );
  const shown = new Set(candidates.slice(0, limit));
  if (focus && candidates.includes(focus)) shown.add(focus);
  const nodes = [...shown].map((id, i) => ({
    id,
    data: { label: id.split("/").at(-1) },
    position: { x: (i % 3) * 230, y: Math.floor(i / 3) * 100 + (i % 3) * 20 },
    style: {
      background:
        id === selected || id === focusPath
          ? "#473681"
          : distances
            ? "#30264b"
            : "#212128",
      color: "#efeef7",
      border: "1px solid #625781",
      width: 190,
      fontSize: 12,
      overflowWrap: "anywhere" as const,
    },
  }));
  const edges: FlowEdge[] = possible
    .filter((e) => shown.has(e.source) && shown.has(e.target))
    .map((e, i) => ({
      id: String(i),
      source: e.source,
      target: e.target,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke:
          e.source === selected
            ? "#b89aff"
            : e.target === selected
              ? "#63cbb2"
              : "#646075",
      },
      label:
        selected && (e.source === selected || e.target === selected)
          ? e.kind
          : undefined,
    }));
  const path = all.files.has(selected) ? selected : all.owner.get(selected);
  return (
    <section>
      <div className="graph-tools">
        <input
          aria-label="Search graph nodes"
          placeholder="Find a node…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          aria-label="Relationship type"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="all">All relationships</option>
          {kinds.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        {focus && (
          <Button variant="secondary" onClick={() => setFocus("")}>
            Show overview
          </Button>
        )}
      </div>
      <div className="graph">
        <ReactFlow
          key={[focus, kind, query, limit, focusPath].join("|")}
          nodes={nodes}
          edges={edges}
          onNodeClick={(_, n) => setSelected(n.id)}
          fitView
          colorMode="dark"
          nodesDraggable={false}
          nodesConnectable={false}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p className="muted">
        {shown.size} of {candidates.length} nodes · {edges.length} detected
        relationships
      </p>
      {shown.size < candidates.length && (
        <Button variant="secondary" onClick={() => setLimit((n) => n + 50)}>
          Show 50 more
        </Button>
      )}
      {selected && (
        <div className="inline-actions">
          <code>{selected}</code>
          <Button
            variant="secondary"
            onClick={() => {
              setFocus(selected);
              setQuery("");
            }}
          >
            Focus node
          </Button>
          {path && <Button onClick={() => open(path)}>Open source</Button>}
        </div>
      )}
    </section>
  );
}
