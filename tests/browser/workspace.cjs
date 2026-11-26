/* Isolated authenticated UI regression. All service responses are intercepted in this browser context. */
const assert = require("node:assert/strict");
const { spawn, execFileSync } = require("node:child_process");
const { once } = require("node:events");
const { readFile, mkdtemp, rm } = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

const port = 4186;
const origin = "http://127.0.0.1:" + port;
const repoId = "c2be6102-e793-4316-b888-d63b4d12eae0";
const sha = "a".repeat(40);
const filePath = "src/count.py";
const source =
  "# Test fixture\n\ndef next_value(value):\n    return value + 1\n";
const lines = source.trimEnd().split("\n");
const repoUrl = "https://github.com/example/browser-test";
const citation = {
  path: filePath,
  sha,
  start_line: 3,
  end_line: 4,
  text: lines.slice(2).join("\n"),
  label: "S1",
  url: repoUrl + "/blob/" + sha + "/" + filePath + "#L3-L4",
};
const question = "What does next_value return?";
const answer = "It adds one to the argument. [S1]";
const doc = "The function increments its input. [S1]";

function testSession() {
  const now = Math.floor(Date.now() / 1000);
  const user = {
    id: "f8cb7495-76e7-4baf-a4f3-6b65ee71846d",
    email: "browser@example.invalid",
    aud: "authenticated",
    role: "authenticated",
    app_metadata: { provider: "email" },
    user_metadata: {},
  };
  const encode = (value) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  return {
    access_token:
      encode({ alg: "HS256", typ: "JWT" }) +
      "." +
      encode({
        sub: user.id,
        iat: now,
        exp: now + 3600,
        role: "authenticated",
      }) +
      ".testsignature",
    refresh_token: "local-test-refresh",
    token_type: "bearer",
    expires_in: 3600,
    expires_at: now + 3600,
    user,
  };
}

async function services(context) {
  const session = testSession();
  const state = {
    history: [],
    docs: [],
    refreshes: 0,
    polls: 0,
    fileReads: [],
    failures: [],
  };
  const repo = {
    id: repoId,
    name: "example/browser-test",
    url: repoUrl,
    sha,
    updated_at: "2026-01-01T01:00:00Z",
    metadata: {
      name: "browser-test",
      owner: "example",
      description: "UI regression fixture",
      default_branch: "main",
      languages: { Python: source.length },
      discovered: 1,
      skipped: {},
    },
    files: [
      { path: filePath, language: "Python", lines: lines.length, parsed: true },
    ],
    symbols: [
      {
        kind: "function",
        name: "next_value",
        path: filePath,
        start_line: 3,
        end_line: 4,
      },
    ],
    edges: [],
  };
  await context.route("**/*", async (route) => {
    const request = route.request();
    const target = new URL(request.url());
    const method = request.method(),
      pathname = target.pathname;
    const reply = (json, status = 200) => route.fulfill({ status, json });
    if (["blob:", "data:"].includes(target.protocol)) return route.continue();
    if (target.origin !== origin) {
      state.failures.push("Unexpected nonlocal request: " + target.origin);
      return route.abort();
    }
    if (pathname === "/auth-fixture/auth/v1/token" && method === "POST")
      return reply(session);
    if (!pathname.startsWith("/test-api/")) return route.continue();
    if (request.headers().authorization !== "Bearer " + session.access_token) {
      state.failures.push("Missing or incorrect test bearer credential");
      return reply({ detail: "Missing test authorization" }, 401);
    }
    const uri = pathname.slice("/test-api".length);
    if (method === "GET" && uri === "/repos") return reply([repo]);
    const base = "/repos/" + repoId;
    if (method === "GET" && uri === base) {
      const polling = state.refreshes && ++state.polls === 1;
      const job = polling
        ? {
            stage: "Retrieving file tree",
            status: "running",
            done: 0,
            total: 1,
          }
        : { stage: "Ready", status: "ready", done: 1, total: 1 };
      return reply({ ...repo, job });
    }
    if (
      method === "GET" &&
      uri === base + "/file" &&
      target.searchParams.get("path") === filePath
    ) {
      state.fileReads.push(filePath);
      return reply({ path: filePath, language: "Python", text: source });
    }
    if (uri === base + "/history" && method === "GET")
      return reply(state.history);
    if (uri === base + "/ask" && method === "POST") {
      const payload = request.postDataJSON();
      state.history.push({ ...payload, answer, citations: [citation] });
      return reply(state.history.at(-1));
    }
    if (uri === base + "/documents") {
      if (method === "GET") return reply(state.docs);
      if (method === "POST") {
        state.docs.push({
          ...request.postDataJSON(),
          answer: doc,
          citations: [citation],
        });
        return reply(state.docs.at(-1));
      }
    }
    if (uri === base + "/refresh" && method === "POST") {
      state.refreshes++;
      state.polls = 0;
      return reply({ id: repoId }, 202);
    }
    state.failures.push("Unexpected test request: " + method + " " + uri);
    return reply({ detail: "Unhandled test request" }, 404);
  });
  return state;
}

async function checkDesktop(page, state) {
  await page.goto(origin + "/repositories");
  await page.getByRole("heading", { name: "Sign in to DevMind" }).waitFor();
  await page
    .getByLabel("Email", { exact: true })
    .fill("browser@example.invalid");
  await page.getByLabel("Password", { exact: true }).fill("fixture-value");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: /example\/browser-test/ }).click();
  await page.getByRole("link", { name: "Ask DevMind" }).click();
  await page.getByRole("heading", { name: "Ask DevMind", level: 1 }).waitFor();
  await page.getByLabel("Your question").fill(question);
  await page.getByRole("button", { name: "Ask question" }).click();
  await page.getByText(answer, { exact: true }).waitFor();
  assert.equal(state.history[0].question, question);
  await page.reload();
  await page.getByText(question, { exact: true }).waitFor();
  await page.getByRole("button", { name: /src\/count.py.*L3–4/ }).click();
  await page.getByRole("heading", { name: "File explorer" }).waitFor();
  await page.locator(".view-line").filter({ hasText: "next_value" }).waitFor();
  await page.locator(".source-highlight").first().waitFor();
  assert.ok(state.fileReads.includes(filePath));
  const highlighted = await page.locator(".monaco-pane").evaluate((element) => {
    const offsets = [...element.querySelectorAll(".source-highlight")].map(
      (marker) => marker.getBoundingClientRect().top,
    );
    return [...element.querySelectorAll(".view-line")]
      .filter((line) =>
        offsets.some(
          (top) => Math.abs(top - line.getBoundingClientRect().top) < 1,
        ),
      )
      .map((line) => line.textContent.replace(/\u00a0/g, " ").trim());
  });
  assert.deepEqual(
    highlighted,
    lines.slice(2).map((line) => line.trim()),
    "Monaco should decorate only the cited lines",
  );
  await page.getByRole("button", { name: "Ask about file" }).click();
  await page.getByLabel("Your question").fill("Which file defines it?");
  await page.getByRole("button", { name: "Ask question" }).click();
  await page.getByText("Which file defines it?", { exact: true }).waitFor();
  assert.equal(state.history[1].path, filePath);
  await page.getByRole("link", { name: "Documentation" }).click();
  await page.getByLabel("Document topic").selectOption("Architecture summary");
  await page.getByRole("button", { name: "Generate document" }).click();
  await page.getByText(doc, { exact: true }).waitFor();
  assert.equal(state.docs[0].question, "Architecture summary");
  await page.reload();
  await page.getByText(doc, { exact: true }).waitFor();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Markdown" }).click();
  const download = await downloadEvent;
  assert.equal(download.suggestedFilename(), "devmind-documentation.md");
  const markdown = await readFile(await download.path(), "utf8");
  assert.ok(markdown.includes(doc) && markdown.includes(citation.url));
  await page.getByRole("button", { name: "Refresh repository" }).click();
  await page.getByText("Retrieving file tree", { exact: true }).waitFor();
  await page.getByText("Ready", { exact: true }).first().waitFor();
  assert.equal(state.refreshes, 1);
  assert.ok(state.polls >= 2);
}

async function checkMobile(page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Toggle workspace navigation" })
    .click();
  await page.getByRole("link", { name: "Ask DevMind" }).click();
  await page.getByText(question, { exact: true }).waitFor();
  await page
    .getByRole("button", { name: /src\/count.py.*L3–4/ })
    .first()
    .click();
  await page.locator(".source-highlight").first().waitFor();
  const width = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
  }));
  assert.ok(
    width.document <= width.viewport + 1,
    "Mobile file explorer overflows viewport: " + JSON.stringify(width),
  );
}

async function run() {
  const frontend = path.resolve(__dirname, "../../frontend");
  const output = await mkdtemp(
    path.join(require("node:os").tmpdir(), "devmind-ui-test-"),
  );
  const fixtureEnv = {
    ...process.env,
    VITE_SUPABASE_URL: origin + "/auth-fixture",
    VITE_SUPABASE_PUBLISHABLE_KEY: "ui-fixture-only",
    VITE_API_URL: origin + "/test-api",
  };
  const vite = "node_modules/vite/bin/vite.js";
  execFileSync(process.execPath, [vite, "build", "--outDir", output], {
    cwd: frontend,
    env: fixtureEnv,
  });
  const server = spawn(
    process.execPath,
    [
      vite,
      "preview",
      "--outDir",
      output,
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--strictPort",
    ],
    { cwd: frontend, env: fixtureEnv, stdio: ["ignore", "pipe", "pipe"] },
  );
  let logs = "";
  server.stdout.on("data", (data) => {
    logs = (logs + data).slice(-4000);
  });
  server.stderr.on("data", (data) => {
    logs = (logs + data).slice(-4000);
  });
  let browser;
  try {
    const deadline = Date.now() + 30000;
    while (!logs.includes("Local:")) {
      if (server.exitCode !== null || Date.now() > deadline)
        throw new Error("Test Vite unavailable: " + logs);
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({
      headless: true,
      ...(process.env.CHROME_BIN
        ? { executablePath: process.env.CHROME_BIN }
        : {}),
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 950 },
      reducedMotion: "reduce",
    });
    const state = await services(context);
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    page.on("pageerror", (error) => state.failures.push(error.message));
    await checkDesktop(page, state);
    await checkMobile(page);
    assert.deepEqual(state.failures, []);
    console.log(
      "Passed authenticated desktop and mobile UI regressions (isolated service fixtures).",
    );
  } finally {
    try {
      if (browser) await browser.close();
    } finally {
      if (server.exitCode === null) {
        const exited = once(server, "exit");
        server.kill("SIGTERM");
        await exited;
      }
      await rm(output, { recursive: true, force: true });
    }
  }
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
