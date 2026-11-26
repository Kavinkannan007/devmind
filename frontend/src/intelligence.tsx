import { useEffect, useState, type FormEvent } from "react";
import Markdown from "react-markdown";
import {
  BookMarked,
  Download,
  FileCode2,
  MessageSquareText,
  Send,
} from "lucide-react";
import { api, errorText, type Answer, type Citation } from "./api";
import { Button, Loading, Notice } from "./ui";
export type OpenCitation = (c: Citation) => void;
function References({
  items,
  open,
}: {
  items: Citation[];
  open: OpenCitation;
}) {
  return (
    <div className="refs">
      {items.map((c, i) => (
        <button key={i} onClick={() => open(c)} title={c.sha}>
          <FileCode2 size={13} /> {c.label && <strong>{c.label}</strong>}{" "}
          {c.path} · L{c.start_line}–{c.end_line}
        </button>
      ))}
    </div>
  );
}
function AnswerView({ answer, open }: { answer: Answer; open: OpenCitation }) {
  return (
    <article className="answer">
      <Markdown
        skipHtml
        components={{
          img: () => null,
          a: ({ children }) => <span>{children}</span>,
        }}
      >
        {answer.answer}
      </Markdown>
      <References items={answer.citations} open={open} />
    </article>
  );
}
export function Assistant({
  id,
  path,
  clear,
  open,
}: {
  id: string;
  path?: string;
  clear: () => void;
  open: OpenCitation;
}) {
  const [history, setHistory] = useState<Answer[]>([]),
    [question, setQuestion] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    api<Answer[]>("/repos/" + id + "/history")
      .then((v) => active && setHistory(v))
      .catch((e) => active && setError(errorText(e)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [id]);
  async function send(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError("");
    try {
      const q = question.trim();
      const reply = await api<Answer>("/repos/" + id + "/ask", {
        question: q,
        ...(path ? { path } : {}),
      });
      setHistory((a) => [...a, { ...reply, question: q }]);
      setQuestion("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="assistant">
      <h2>
        <MessageSquareText size={18} /> Ask DevMind
      </h2>
      {loading ? (
        <Loading label="Loading conversation" />
      ) : (
        <div className="messages">
          {history.length === 0 && (
            <p className="muted">
              Ask about the architecture, an endpoint or a file. Answers include
              source references where evidence is available.
            </p>
          )}
          {history.map((a, i) => (
            <div key={i}>
              <div className="question">{a.question}</div>
              <AnswerView answer={a} open={open} />
            </div>
          ))}
        </div>
      )}
      {error && <Notice>{error}</Notice>}
      <form onSubmit={send}>
        {path && (
          <button
            type="button"
            className="scope"
            onClick={clear}
            title="Clear file context"
          >
            {path} ×
          </button>
        )}
        <textarea
          aria-label="Your question"
          maxLength={1800}
          required
          placeholder="Ask about this codebase…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button disabled={busy || loading || !question.trim()}>
          <Send size={14} />
          {busy ? "Retrieving evidence…" : "Ask question"}
        </Button>
      </form>
    </section>
  );
}
export function SearchPanel({ id, open }: { id: string; open: OpenCitation }) {
  const [text, setText] = useState(""),
    [results, setResults] = useState<Citation[] | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setResults(null);
    try {
      setResults(
        await api<Citation[]>("/repos/" + id + "/search", {
          question: text.trim(),
        }),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <form className="inline-actions" onSubmit={submit}>
        <input
          required
          maxLength={1800}
          aria-label="Code search"
          placeholder="Search symbols, paths or a question"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button disabled={busy || !text.trim()}>Search</Button>
      </form>
      {busy && <Loading label="Searching indexed source" />}
      {error && <Notice>{error}</Notice>}
      {results?.length === 0 && <p>No matching code chunks.</p>}
      {results?.map((r, i) => (
        <article className="result" key={i}>
          <References items={[r]} open={open} />
          {r.symbol && <small>{r.symbol}</small>}
          <pre>{r.text}</pre>
        </article>
      ))}
    </>
  );
}
const topics = [
  "Project overview",
  "Technology stack",
  "Folder structure",
  "Architecture summary",
  "API endpoints",
  "Installation guidance",
  "Developer onboarding guide",
  "Important modules",
  "Dependency overview",
];
export function Documents({ id, open }: { id: string; open: OpenCitation }) {
  const [topic, setTopic] = useState(topics[0]),
    [docs, setDocs] = useState<Answer[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    api<Answer[]>("/repos/" + id + "/documents")
      .then((v) => active && setDocs(v))
      .catch((e) => active && setError(errorText(e)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [id]);
  async function generate() {
    setBusy(true);
    setError("");
    try {
      const answer = await api<Answer>("/repos/" + id + "/documents", {
        question: topic,
      });
      setDocs((d) => [{ ...answer, question: topic }, ...d]);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  function download(d: Answer) {
    const references = d.citations
      .map(
        (c) =>
          "- " +
          (c.label || "") +
          " [" +
          c.path +
          " L" +
          c.start_line +
          "–" +
          c.end_line +
          "](" +
          c.url +
          ")",
      )
      .join("\n");
    const url = URL.createObjectURL(
      new Blob([d.answer + "\n\n## Sources\n\n" + references], {
        type: "text/markdown",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "devmind-documentation.md";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <div className="inline-actions">
        <select
          aria-label="Document topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        >
          {topics.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <Button disabled={busy || loading} onClick={generate}>
          <BookMarked size={16} />
          {busy ? "Generating…" : "Generate document"}
        </Button>
      </div>
      {error && <Notice>{error}</Notice>}
      {loading ? (
        <Loading label="Loading documents" />
      ) : (
        docs.map((d, i) => (
          <section className="document" key={i}>
            <div className="inline-actions">
              <h3>{d.question || "Saved document"}</h3>
              <Button variant="quiet" onClick={() => download(d)}>
                <Download size={15} />
                Markdown
              </Button>
            </div>
            <AnswerView answer={d} open={open} />
          </section>
        ))
      )}
      {!loading && !docs.length && (
        <p className="muted">
          Generated documents and their source references appear here.
        </p>
      )}
    </>
  );
}
