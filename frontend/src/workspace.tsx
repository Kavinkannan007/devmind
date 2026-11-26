import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  BookMarked,
  ChevronLeft,
  CodeXml,
  FileSearch,
  FolderTree,
  GitBranch,
  GitFork,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Network,
  RefreshCw,
  Settings,
  Trash2,
} from "lucide-react";
import { api, errorText, type Citation, type Repo } from "./api";
import { Assistant, Documents, SearchPanel } from "./intelligence";
import type { Selection } from "./explorer";
import { Brand, Button, Loading, Notice } from "./ui";
const Graph = lazy(() => import("./graph")),
  Explorer = lazy(() => import("./explorer")),
  Overview = lazy(() => import("./overview"));
const views = [
  ["overview", "Overview", LayoutDashboard],
  ["ask", "Ask DevMind", MessageSquareText],
  ["files", "File explorer", FolderTree],
  ["architecture", "Architecture", Network],
  ["dependencies", "Dependencies", GitBranch],
  ["impact", "Change impact", GitFork],
  ["search", "Code search", FileSearch],
  ["docs", "Documentation", BookMarked],
  ["settings", "Settings", Settings],
] as const;
type Distances = {
  dependants: Record<string, number>;
  dependencies: Record<string, number>;
};
function Impact({ repo, open }: { repo: Repo; open: (p: string) => void }) {
  const [path, setPath] = useState(repo.files[0]?.path || ""),
    [result, setResult] = useState<Distances | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    setResult(null);
    setError("");
    if (!path) return;
    let active = true;
    api<Distances>(
      "/repos/" + repo.id + "/impact?path=" + encodeURIComponent(path),
    )
      .then((v) => active && setResult(v))
      .catch((e) => active && setError(errorText(e)));
    return () => {
      active = false;
    };
  }, [repo.id, path, repo.sha]);
  return (
    <>
      <p>
        Potential impact follows statically resolved imports. Review direct
        dependants first, then inspect more distant modules and their tests.
      </p>
      <select
        aria-label="Impact analysis source file"
        value={path}
        onChange={(e) => setPath(e.target.value)}
      >
        {repo.files.map((f) => (
          <option key={f.path}>{f.path}</option>
        ))}
      </select>
      {error && <Notice>{error}</Notice>}
      {result ? (
        <>
          <Graph
            key={path}
            repo={repo}
            focusPath={path}
            distances={{ ...result.dependants, ...result.dependencies }}
            open={open}
          />
          {(["dependants", "dependencies"] as const).map((k) => (
            <section className="panel" key={k}>
              <h3>
                {k === "dependants"
                  ? "Potentially affected files"
                  : "Upstream dependencies"}
              </h3>
              {Object.entries(result[k])
                .sort((a, b) => a[1] - b[1])
                .map(([f, d]) => (
                  <button className="repo-row" onClick={() => open(f)} key={f}>
                    <code>{f}</code>
                    <small>
                      {d === 1 ? "Direct" : "Indirect"} · distance {d}
                    </small>
                  </button>
                ))}
              {!Object.keys(result[k]).length && (
                <p className="muted">None detected in the indexed files.</p>
              )}
            </section>
          ))}
        </>
      ) : (
        path && !error && <Loading label="Following imports" />
      )}
    </>
  );
}
export function Workspace() {
  const { id = "", "*": route } = useParams(),
    navigate = useNavigate(),
    view = views.find((v) => v[0] === route) || views[0];
  const [repo, setRepo] = useState<Repo | null>(null),
    [error, setError] = useState(""),
    [selection, setSelection] = useState<Selection | null>(null),
    [scope, setScope] = useState(""),
    [menu, setMenu] = useState(false),
    [toast, setToast] = useState(""),
    [busy, setBusy] = useState(false),
    [confirm, setConfirm] = useState(false),
    [epoch, setEpoch] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const notify = useCallback((m: string) => {
    setToast(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(""), 3500);
  }, []);
  useEffect(() => {
    let active = true;
    let poll: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const v = await api<Repo>("/repos/" + id);
        if (!active) return;
        setRepo(v);
        setError("");
        if (
          v.job &&
          !["ready", "failed", "completed", "succeeded"].includes(
            v.job.status.toLowerCase(),
          )
        )
          poll = setTimeout(load, 1500);
      } catch (e) {
        if (active) setError(errorText(e));
      }
    }
    void load();
    return () => {
      active = false;
      clearTimeout(poll);
    };
  }, [id, epoch]);
  function go(v: string) {
    setMenu(false);
    navigate("/repositories/" + id + "/" + v);
  }
  function open(c: Citation) {
    if (c.sha && repo?.sha && c.sha !== repo.sha) {
      window.open(c.url, "_blank", "noopener,noreferrer");
      return;
    }
    setSelection({ path: c.path, start: c.start_line, end: c.end_line });
    go("files");
  }
  function file(path: string) {
    setSelection({ path });
    go("files");
  }
  async function action(remove = false) {
    setBusy(true);
    try {
      await api(
        "/repos/" + id + (remove ? "" : "/refresh"),
        undefined,
        remove ? "DELETE" : "POST",
      );
      if (remove) navigate("/repositories");
      else {
        notify("Refresh requested");
        setEpoch((n) => n + 1);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  }
  const ready = !!repo?.sha;
  return (
    <div className="workspace">
      <aside className={"sidebar " + (menu ? "mobile-open" : "")}>
        <Brand />
        <Link className="back" to="/repositories">
          <ChevronLeft size={16} /> Repositories
        </Link>
        <div className="sidebar-cap">Repository workspace</div>
        <nav>
          {views.map(([slug, title, Icon]) => (
            <Link
              aria-current={view[0] === slug ? "page" : undefined}
              className={view[0] === slug ? "active" : ""}
              key={slug}
              to={"/repositories/" + id + "/" + slug}
              onClick={() => setMenu(false)}
            >
              <Icon size={16} />
              {title}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="workspace-main">
        <div className="workspace-top">
          <Button
            variant="quiet"
            className="mobile-menu"
            aria-label="Toggle workspace navigation"
            onClick={() => setMenu(!menu)}
          >
            <Menu size={18} />
          </Button>
          <GitBranch size={16} />
          <span>{repo?.name || "Repository"}</span>
          <code>{repo?.sha?.slice(0, 8) || "Awaiting index"}</code>
        </div>
        <div className="workspace-inner">
          <div className="workspace-heading">
            <div>
              <div className="section-kicker">
                <CodeXml size={14} /> Repository intelligence
              </div>
              <h1>{view[1]}</h1>
            </div>
            {repo && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => action()}
              >
                <RefreshCw size={14} />
                Refresh repository
              </Button>
            )}
          </div>
          {error && (
            <>
              <Notice>{error}</Notice>
              <Button variant="quiet" onClick={() => setEpoch((n) => n + 1)}>
                Retry loading
              </Button>
            </>
          )}
          {!repo && !error ? (
            <Loading />
          ) : (
            repo && (
              <>
                {repo.job && (
                  <div className="job">
                    <strong>{repo.job.stage}</strong>
                    <span>{repo.job.status}</span>
                    {repo.job.total > 0 && (
                      <>
                        <progress value={repo.job.done} max={repo.job.total} />
                        <code>
                          {repo.job.done}/{repo.job.total}
                        </code>
                      </>
                    )}
                    {repo.job.error && <Notice>{repo.job.error}</Notice>}
                  </div>
                )}
                <div
                  className={
                    "workspace-panels " +
                    (ready && view[0] === "overview" ? "with-assistant" : "")
                  }
                >
                  <section className="main-panel">
                    <Suspense fallback={<Loading label="Opening view" />}>
                      {view[0] === "settings" ? (
                        <section className="panel">
                          <h3>Repository settings</h3>
                          <p>
                            <a href={repo.url} target="_blank" rel="noreferrer">
                              {repo.url}
                            </a>
                          </p>
                          <p>
                            Deleting this repository removes its index,
                            conversation and saved documents from this
                            workspace.
                          </p>
                          {confirm ? (
                            <div className="inline-actions">
                              <Button
                                disabled={busy}
                                onClick={() => action(true)}
                              >
                                Confirm deletion
                              </Button>
                              <Button
                                variant="secondary"
                                onClick={() => setConfirm(false)}
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <Button
                              variant="secondary"
                              onClick={() => setConfirm(true)}
                            >
                              <Trash2 size={15} />
                              Delete repository
                            </Button>
                          )}
                        </section>
                      ) : !ready ? (
                        <div className="empty">
                          Workspace tools become available after the first
                          successful index.
                        </div>
                      ) : (
                        <>
                          {view[0] === "overview" && <Overview repo={repo} />}
                          {view[0] === "files" && (
                            <Explorer
                              repo={repo}
                              selection={selection}
                              select={setSelection}
                              ask={(p) => {
                                setScope(p);
                                go("ask");
                              }}
                              notify={notify}
                            />
                          )}
                          {view[0] === "ask" && (
                            <Assistant
                              id={id}
                              path={scope}
                              clear={() => setScope("")}
                              open={open}
                            />
                          )}
                          {view[0] === "search" && (
                            <SearchPanel id={id} open={open} />
                          )}
                          {view[0] === "docs" && (
                            <Documents id={id} open={open} />
                          )}
                          {view[0] === "architecture" && (
                            <Graph repo={repo} open={file} />
                          )}
                          {view[0] === "impact" && (
                            <Impact repo={repo} open={file} />
                          )}
                          {view[0] === "dependencies" && (
                            <section className="panel">
                              <h3>Detected relationships</h3>
                              {repo.edges.map((edge, i) => (
                                <button
                                  key={i}
                                  className="edge-row"
                                  onClick={() =>
                                    open({
                                      path: edge.source,
                                      start_line: edge.line,
                                      end_line: edge.line,
                                      sha: repo.sha!,
                                      url: "",
                                    })
                                  }
                                >
                                  <strong>
                                    {edge.source}:{edge.line}
                                  </strong>
                                  <span>{edge.kind}</span>
                                  <code>{edge.target}</code>
                                </button>
                              ))}
                              {!repo.edges.length && (
                                <p>
                                  No relationships detected in the indexed
                                  files.
                                </p>
                              )}
                            </section>
                          )}
                        </>
                      )}
                    </Suspense>
                  </section>
                  {ready && view[0] === "overview" && (
                    <Assistant id={id} clear={() => setScope("")} open={open} />
                  )}
                </div>
              </>
            )
          )}
        </div>
      </main>
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
