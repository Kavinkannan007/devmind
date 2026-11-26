import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Repo } from "./api";
export default function Overview({ repo }: { repo: Repo }) {
  const languages = new Map<string, number>();
  for (const f of repo.files)
    languages.set(f.language, (languages.get(f.language) || 0) + 1);
  const data = [...languages.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([name, files]) => ({ name, files }));
  const metrics = [
    [
      repo.metadata.truncated
        ? "Discovered files (partial tree)"
        : "Discovered files",
      repo.metadata.discovered ?? "Unavailable",
    ],
    ["Indexed files", repo.files.length],
    ["Indexed source lines", repo.files.reduce((sum, f) => sum + f.lines, 0)],
    [
      "Detected functions & methods",
      repo.symbols.filter((s) => ["function", "method"].includes(s.kind))
        .length,
    ],
    ["Detected classes", repo.symbols.filter((s) => s.kind === "class").length],
    ["Dependency edges", repo.edges.length],
  ];
  return (
    <>
      <p>
        {repo.metadata.description || "No repository description available."}
      </p>
      <div className="metric-grid">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <small>{label}</small>
            <strong>{value.toLocaleString()}</strong>
          </div>
        ))}
      </div>
      {data.length > 0 && (
        <section className="panel">
          <h3>Indexed files by language</h3>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid stroke="#32323d" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: "#b5b4c2", fontSize: 11 }}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fill: "#b5b4c2", fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{
                    background: "#22212a",
                    borderColor: "#494753",
                  }}
                />
                <Bar dataKey="files" fill="#a48ae9" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}
      <section className="panel">
        <h3>Index coverage</h3>
        <dl>
          {Object.entries(repo.metadata.skipped || {}).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replaceAll("_", " ")}</dt>
              <dd>{value} skipped</dd>
            </div>
          ))}
          <div>
            <dt>GitHub stars</dt>
            <dd>{repo.metadata.stars?.toLocaleString() ?? "Unavailable"}</dd>
          </div>
          <div>
            <dt>GitHub forks</dt>
            <dd>{repo.metadata.forks?.toLocaleString() ?? "Unavailable"}</dd>
          </div>
          <div>
            <dt>Repository updated</dt>
            <dd>
              {repo.metadata.updated_at
                ? new Date(repo.metadata.updated_at).toLocaleString()
                : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt>Default branch</dt>
            <dd>{repo.metadata.default_branch || "Unavailable"}</dd>
          </div>
          <div>
            <dt>GitHub languages</dt>
            <dd>
              {Object.keys(repo.metadata.languages || {}).join(", ") ||
                "Unavailable"}
            </dd>
          </div>
          <div>
            <dt>Detected frameworks</dt>
            <dd>{repo.metadata.frameworks?.join(", ") || "None detected"}</dd>
          </div>
          <div>
            <dt>Indexed commit</dt>
            <dd>
              <code>{repo.sha || "Pending"}</code>
            </dd>
          </div>
        </dl>
        {!!repo.metadata.skipped_files?.length && (
          <details>
            <summary>
              Inspect skipped paths ({repo.metadata.skipped_files.length}{" "}
              listed)
            </summary>
            <ul>
              {repo.metadata.skipped_files.map((s) => (
                <li key={s.path}>
                  <code>{s.path}</code> · {s.reason}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
    </>
  );
}
