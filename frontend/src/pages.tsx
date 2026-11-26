import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import {
  Braces,
  BookOpenText,
  Check,
  CircleDot,
  CodeXml,
  Database,
  FileCode2,
  FolderGit2,
  GitBranch,
  Github,
  GitPullRequest,
  Layers3,
  LogOut,
  Network,
  ScanLine,
  Search,
  Workflow,
} from "lucide-react";
import { useSession } from "./main";
import { api, errorText, setupHint, supabase, type RepoRow } from "./api";
import { Brand, Button, Footer, Loading, Notice } from "./ui";

function ImportForm() {
  const session = useSession(),
    navigate = useNavigate();
  const [url, setUrl] = useState(
      () => sessionStorage.getItem("pending-repo") || "",
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const clean = url.trim();
    if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/i.test(clean)) {
      setError(
        "Enter a public repository URL such as https://github.com/owner/repository.",
      );
      return;
    }
    if (!session) {
      sessionStorage.setItem("pending-repo", clean);
      navigate("/auth");
      return;
    }
    setBusy(true);
    try {
      const repo = await api<{ id: string }>("/repos", { url: clean });
      sessionStorage.removeItem("pending-repo");
      navigate("/repositories/" + repo.id);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <form className="import" onSubmit={submit}>
        <Github size={20} />
        <input
          aria-label="Public GitHub repository URL"
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/owner/repository"
        />
        <Button disabled={busy}>
          {busy ? "Importing…" : "Import repository"}
        </Button>
      </form>
      {error && <Notice>{error}</Notice>}
    </div>
  );
}
const features = [
  {
    Icon: BookOpenText,
    title: "Source-grounded answers",
    description:
      "Ask a question and follow the references straight to the lines behind each answer.",
  },
  {
    Icon: Network,
    title: "Architecture explorer",
    description:
      "Trace internal imports, explore modules and inspect the connections between files.",
  },
  {
    Icon: GitPullRequest,
    title: "Change impact",
    description:
      "See which files depend on a module and where to focus your review before editing.",
  },
];
const stages = [
  { Icon: FolderGit2, name: "Repository", detail: "Public GitHub source" },
  { Icon: Braces, name: "Parse & chunk", detail: "Syntax-aware indexing" },
  { Icon: Database, name: "Embed & retrieve", detail: "Hybrid code search" },
  {
    Icon: BookOpenText,
    name: "Cited answer",
    detail: "Commit-pinned evidence",
  },
];
function Pipeline() {
  return (
    <figure className="pipeline" aria-label="Repository indexing workflow">
      <div className="figure-head">
        <GitBranch size={15} /> Ingestion pipeline{" "}
        <span className="diagram-tag">SCHEMATIC</span>
      </div>
      <div className="pipeline-body">
        <div className="stack" aria-hidden="true">
          {[3, 2, 1, 0].map((i) => (
            <div className={"plate p" + i} key={i}>
              <span />
              <i />
              <b />
              {i === 0 && <Layers3 size={42} />}
            </div>
          ))}
        </div>
        <ol className="pipeline-legend">
          {stages.map(({ Icon, name, detail }) => (
            <li key={name}>
              <i>
                <Icon size={17} />
              </i>
              <div>
                <strong>{name}</strong>
                <small>{detail}</small>
              </div>
            </li>
          ))}
        </ol>
      </div>
      <figcaption>
        <span className="dot" />
        Read-only analysis{" "}
        <span className="fig-right">
          <CodeXml size={13} /> Source → context
        </span>
      </figcaption>
    </figure>
  );
}
export function Landing() {
  const session = useSession(),
    reduce = useReducedMotion();
  return (
    <div className="landing" id="top">
      <header className="site-head">
        <div className="container nav-row">
          <Brand />
          <nav>
            <a href="#capabilities">Capabilities</a>
            <a href="#workflow">Workflow</a>
          </nav>
          <Button asChild variant="secondary">
            <Link to={session ? "/repositories" : "/auth"}>
              {session ? "My repositories" : "Sign in"}
            </Link>
          </Button>
        </div>
      </header>
      <main className="container">
        <section className="hero">
          <motion.div
            className="hero-copy"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            <div className="eyebrow">
              <span />
              Codebase intelligence
            </div>
            <h1>
              Understand any codebase{" "}
              <em>before touching a single line of code.</em>
            </h1>
            <p>
              Explore architecture, trace dependencies and get answers grounded
              in the source. Start with a public GitHub repository.
            </p>
            <ImportForm />
            <div className="form-note">
              <CircleDot size={13} /> Public repositories <span>·</span>{" "}
              Read-only access
            </div>
          </motion.div>
          <Pipeline />
        </section>
        <section id="capabilities" className="capabilities">
          <div className="section-kicker">
            <ScanLine size={16} /> Capabilities
          </div>
          <h2>Understand before you change.</h2>
          <div className="feature-grid">
            {features.map(({ Icon, title, description }) => (
              <article key={title}>
                <div className="icon-frame">
                  <Icon size={23} />
                </div>
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </section>
        <section id="workflow" className="workflow-section">
          <div>
            <div className="section-kicker">
              <Workflow size={15} /> Workflow
            </div>
            <h2>From repository to evidence.</h2>
          </div>
          <ol>
            <li>
              <GitBranch />
              <div>
                <h3>Import a commit</h3>
                <p>
                  DevMind reads eligible source files at a specific GitHub
                  commit and records indexing coverage.
                </p>
              </div>
            </li>
            <li>
              <Search />
              <div>
                <h3>Retrieve relevant code</h3>
                <p>
                  Gemini embeddings and keyword search find source passages
                  related to your question.
                </p>
              </div>
            </li>
            <li>
              <Check />
              <div>
                <h3>Inspect the references</h3>
                <p>
                  Open the retrieved file and line range alongside the answer to
                  verify it for yourself.
                </p>
              </div>
            </li>
          </ol>
        </section>
      </main>
      <div className="container">
        <Footer />
      </div>
    </div>
  );
}
export function Auth() {
  const session = useSession();
  const [params] = useSearchParams();
  const [signup, setSignup] = useState(params.get("mode") === "signup"),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  if (session) return <Navigate replace to="/repositories" />;
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");
    if (!supabase) {
      setError(setupHint);
      return;
    }
    setBusy(true);
    try {
      const result = signup
        ? await supabase.auth.signUp({
            email,
            password,
            options: { emailRedirectTo: location.origin + "/repositories" },
          })
        : await supabase.auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      if (signup && !result.data.session)
        setMessage("Check your email to confirm your account, then sign in.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-screen">
      <Brand />
      <section className="auth-box">
        <div className="icon-frame">
          <FolderGit2 />
        </div>
        <h1>{signup ? "Create an account" : "Sign in to DevMind"}</h1>
        <p>
          {signup
            ? "Create your personal codebase workspace."
            : "Access your saved repositories and source conversations."}
        </p>
        <form onSubmit={submit}>
          <label>
            Email
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              minLength={signup ? 8 : 1}
              required
              autoComplete={signup ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button disabled={busy}>
            {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
          </Button>
        </form>
        {!supabase && <Notice>{setupHint}</Notice>}
        {error && <Notice>{error}</Notice>}
        {message && <p role="status">{message}</p>}
        <button
          className="text-btn"
          onClick={() => {
            setSignup(!signup);
            setError("");
            setMessage("");
          }}
        >
          {signup
            ? "Already have an account? Sign in"
            : "New here? Create an account"}
        </button>
      </section>
    </main>
  );
}
export function Repositories() {
  const session = useSession();
  const [rows, setRows] = useState<RepoRow[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<RepoRow[]>("/repos")
      .then((v) => active && setRows(v))
      .catch((e) => active && setError(errorText(e)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);
  return (
    <div className="container">
      <header className="nav-row">
        <Brand />
        <div className="account">
          <Link to="/profile" aria-label="Your profile">
            {session?.user.user_metadata.display_name || session?.user.email}
          </Link>
          <Button
            variant="quiet"
            onClick={() =>
              supabase?.auth.signOut().then(({ error }) => {
                if (error) setError(error.message);
              })
            }
          >
            <LogOut size={15} /> Sign out
          </Button>
        </div>
      </header>
      <main className="library">
        <div className="section-kicker">
          <FolderGit2 size={16} /> Workspace
        </div>
        <h1>Your repositories</h1>
        <p>Import a public GitHub repository to index its source.</p>
        <ImportForm />
        <div className="list">
          {error && <Notice>{error}</Notice>}
          {loading ? (
            <Loading />
          ) : rows.length ? (
            rows.map((r) => (
              <Link
                className="repo-row"
                key={r.id}
                to={"/repositories/" + r.id}
              >
                <FileCode2 size={20} />
                <strong>{r.name || r.url}</strong>
                <code>{r.sha?.slice(0, 8) || r.status || "Index pending"}</code>
              </Link>
            ))
          ) : (
            !error && <p>No repositories imported yet.</p>
          )}
        </div>
      </main>
    </div>
  );
}

export function Profile() {
  const session = useSession();
  const [name, setName] = useState<string>(
    session?.user.user_metadata.display_name || "",
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const { error } = await supabase.auth.updateUser({
        data: { display_name: name.trim() },
      });
      if (error) throw error;
      setMessage("Profile saved.");
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-screen">
      <Brand />
      <section className="auth-box">
        <h1>Your profile</h1>
        <p>{session?.user.email}</p>
        <form onSubmit={save}>
          <label>
            Display name
            <input
              maxLength={80}
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <Button disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button>
        </form>
        {message && <p role="status">{message}</p>}
        {error && <Notice>{error}</Notice>}
        <Link to="/repositories" className="text-btn">
          Back to repositories
        </Link>
      </section>
    </main>
  );
}
