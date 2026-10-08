// Run with: node tests/frontend_smoke.cjs
// Exercises the browser application's API contracts without a browser, model,
// external network, or additional npm dependencies. This is not visual QA.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag = "div", text = "") {
    this.tagName = tag;
    this._text = text;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.events = {};
    this.value = "";
    this.className = "";
    this.hidden = false;
    this.disabled = false;
    this.classList = { toggle() {} };
  }
  set innerHTML(_) { throw new Error("Unsafe HTML insertion"); }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((node) => node.textContent).join(""); }
  append(...children) { assert.ok(children.every(Boolean)); this.children.push(...children); }
  replaceChildren(...children) {
    this._text = "";
    this.children = children;
    if (this.tagName === "select") this.value = children[0]?.value || "";
  }
  addEventListener(type, handler) { this.events[type] = handler; }
  setAttribute(name, value) { this.attributes[name] = value; }
  cloneNode() { return new Element(this.tagName, this.textContent); }
  get firstElementChild() { return this.children[0] || new Element(); }
  focus() {}
  scrollIntoView() {}
  remove() {}
  click() {}
}

const staticDirectory = path.join(__dirname, "../src/claimlens/static");
const html = fs.readFileSync(path.join(staticDirectory, "index.html"), "utf8");
const nodes = new Map();
for (const match of html.matchAll(/<([a-z][a-z0-9-]*)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
  assert.ok(!nodes.has(match[2]), `Duplicate ID: ${match[2]}`);
  const node = new Element(match[1]);
  const value = match[0].match(/\bvalue="([^"]*)"/);
  node.value = value?.[1] || "";
  node.checked = /\bchecked\b/.test(match[0]);
  nodes.set(match[2], node);
}
const get = (id) => { assert.ok(nodes.has(id), `Missing HTML element ${id}`); return nodes.get(id); };
get("booklet-language").value = "de";
get("claim-language").value = "auto";
get("import-form").elements = ["booklet-url", "booklet-file", "booklet-language", "booklet-title", "booklet-vote", "import-button"].map(get);
const visit = (node) => [node, ...node.children.flatMap(visit)];
const allNodes = () => [...nodes.values()].flatMap(visit);
const document = {
  getElementById: get,
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => new Element("#text", text),
  querySelector: () => get("live-mode").checked ? get("live-mode") : get("demo-mode"),
  querySelectorAll: (selector) => selector.includes('input[name="mode"]') ? [get("demo-mode"), get("live-mode")]
    : allNodes().filter((node) => selector === "[data-check-index]" ? node.dataset.checkIndex !== undefined : node.className === "example-button"),
  body: new Element("body"),
};

const claim = "😀 Der Beitrag beträgt CHF 200 ab 2027.";
const characters = Array.from(claim);
const amountStart = characters.findIndex((character, index) => characters.slice(index, index + 3).join("") === "CHF");
const result = {
  claim, model: "swiss-ai/Apertus-v1.5-8B", mode: "demo", overall: "contradiction", classification: 2,
  summary: "<img src=x onerror=alert(1)>", warnings: [],
  checks: [
    { text: claim, start: 0, end: characters.length, dimension: "general", label: "contradiction", explanation: "The date differs.", evidence: [{ passage_id: "p1", quote: "Ab 2028: CHF 200." }] },
    { text: "CHF 200", start: amountStart, end: amountStart + 7, dimension: "amount", label: "entailment", explanation: "The amount agrees.", evidence: [{ passage_id: "p1", quote: "CHF 200" }] },
  ],
  passages: [{ id: "p1", text: "Ab 2028: CHF 200.", title: "Source", page: 2, attribution: "Government", url: "https://www.bk.admin.ch/source.pdf" }],
  metrics: { input_tokens: 321, output_tokens: 123, context_tokens: null, context_characters: 1234, inference_seconds: 3.5, token_usage_source: "provider" },
};
const booklet = {
  id: "booklet-test", title: "Voting booklet · 2026", language: "fr", source_url: "https://www.bk.admin.ch/source.pdf",
  page_count: 20, character_count: 20000, votes: ["Fee proposal"], warnings: ["One page contains no extractable text."], imported_at: "2026-10-08T10:00:00Z",
};
const configuration = {
  models: [{ id: result.model, label: "Apertus 1.5 · 8B · local" }], default_model: result.model,
  live_ready: true, local_model_configured: true, request_timeout_seconds: 7200, documents: [],
  proposals: [{ id: "demo-fr", title: "Walkthrough", language: "fr", is_fixture: false, examples: [{ id: "one", title: "Compare the numbers", claim, claim_language: "de" }] }],
};
let library = [];
let status = { configured: true, reachable: true, local: true, context_tokens: 8192, message: "Runtime reachable; no inference was run." };
let lastCheck;
let importCalls = 0;
let importFailure = false;
let lastImport;
let timerId = 0;
const timers = [];
const fetch = async (url, options = {}) => {
  let body;
  let ok = true;
  if (url === "/api/config") body = configuration;
  else if (url === "/api/model/status") body = status;
  else if (url === "/api/library") body = { documents: library };
  else if (url.startsWith("/api/booklets/")) {
    importCalls++;
    lastImport = { url, ...options };
    if (importFailure) { ok = false; body = { error: "PDF has no extractable text." }; }
    else { library = [booklet]; body = { document: booklet }; }
  } else if (url === "/api/check") {
    lastCheck = JSON.parse(options.body);
    if (lastCheck.claim === "custom demo claim" && lastCheck.mode === "demo") { ok = false; body = { error: "Choose a bundled example." }; }
    else body = {
      ...result, mode: lastCheck.mode,
      served_model: lastCheck.mode === "live" ? "claimlens-apertus-v1.5-8b-q4" : null,
      processing: { strategy: lastCheck.document_id ? "hierarchical" : "demo", source_pages: 19, segments: 4, model_calls: 5, context_limit_tokens: 8192, coverage: "All extractable source segments were processed." },
    };
  } else throw new Error(`Unexpected request: ${url}`);
  return { ok, json: async () => body };
};
const context = vm.createContext({
  document, Option: function(text, value) { const option = new Element("option", text); option.value = value; return option; },
  URL, URLSearchParams, Blob, AbortController, Date, console, fetch, matchMedia: () => ({ matches: false }),
  setTimeout: (_, delay) => { timers.push(delay); return ++timerId; }, clearTimeout() {},
  setInterval: () => ++timerId, clearInterval() {},
});
vm.runInContext(fs.readFileSync(path.join(staticDirectory, "app.js"), "utf8"), context);
const flush = () => new Promise((resolve) => setImmediate(resolve));
const submit = (id) => get(id).events.submit({ preventDefault() {} });

(async () => {
  await flush();
  assert.equal(get("claim").value, claim);
  assert.equal(get("claim-language").value, "de");
  assert.match(get("runtime-title").textContent, /Local Apertus is reachable/);
  assert.match(get("runtime-context").textContent, /8,192/);
  await submit("claim-form");
  assert.equal(lastCheck.proposal_id, "demo-fr");
  assert.equal(lastCheck.mode, "demo");
  assert.equal(get("highlighted-claim").textContent, claim);
  assert.equal(get("highlighted-claim").children.filter((node) => node.tagName === "button").length, 1);
  assert.equal(get("result-summary").textContent, result.summary);
  assert.match(get("result-metrics").textContent, /not measured/);
  assert.ok(timers.includes(7200000), "Long document timeout honors server budget");

  for (const url of ["https://www.bk.admin.ch.evil.example/file.pdf", "https://sub.bk.admin.ch/file.pdf", "https://www.bk.admin.ch:8443/file.pdf"]) {
    get("booklet-url").value = url;
    await submit("import-form");
    assert.equal(importCalls, 0, "Lookalike domains, other subdomains and custom ports fail before fetching");
    assert.equal(get("import-error").hidden, false);
  }
  get("booklet-url").value = "https://www.bk.admin.ch/source.pdf#page=2";
  get("booklet-title").value = "A source title";
  await submit("import-form");
  assert.equal(importCalls, 1);
  assert.equal(JSON.parse(lastImport.body).url, "https://www.bk.admin.ch/source.pdf");
  assert.equal(get("document-select").value, booklet.id);
  assert.equal(get("live-mode").checked, true);
  assert.equal(get("demo-mode").disabled, true);
  assert.equal(get("vote").value, "Fee proposal");
  assert.match(get("document-details").textContent, /20 pages/);
  assert.match(get("document-details").textContent, /no extractable text/);
  assert.equal(get("results").hidden, true);
  assert.ok(timers.includes(310000), "Imports have their own timeout");

  get("claim").value = claim;
  get("vote").value = "";
  await submit("claim-form");
  assert.equal(get("form-error").hidden, false);
  get("vote").value = "Edited proposal name";
  await submit("claim-form");
  assert.equal(lastCheck.document_id, booklet.id);
  assert.equal(lastCheck.vote, "Edited proposal name");
  assert.equal(lastCheck.mode, "live");
  assert.equal(lastCheck.proposal_id, undefined);
  assert.match(get("result-processing").textContent, /Whole-document review in stages/);
  assert.match(get("result-processing").textContent, /19 source pages/);
  assert.match(get("result-processing").textContent, /5 model calls/);
  assert.match(get("result-metrics").textContent, /claimlens-apertus-v1.5-8b-q4/);
  assert.match(get("result-metrics").textContent, /Not reported/);
  assert.ok(visit(get("evidence-content")).some((node) => node.href === "/api/booklets/booklet-test/pdf#page=2"));

  await get("refresh-library").events.click();
  assert.equal(get("claim").value, claim, "Refreshing unchanged library preserves drafted claim");
  get("upload-method").events.click();
  assert.equal(get("booklet-url").disabled, true, "Hidden invalid URL cannot block PDF upload validation");
  assert.equal(get("booklet-file").disabled, false);
  const file = { name: "booklet.pdf", size: 100, type: "application/pdf" };
  get("booklet-file").files = [file];
  get("booklet-language").value = "it";
  await submit("import-form");
  assert.match(lastImport.url, /^\/api\/booklets\/upload\?language=it/);
  assert.equal(lastImport.headers["Content-Type"], "application/pdf");
  assert.equal(lastImport.body, file, "PDF body is raw binary input");
  importFailure = true;
  await submit("import-form");
  assert.equal(get("import-error").textContent, "PDF has no extractable text.");
  assert.equal(get("import-button").disabled, false);

  status = { configured: true, reachable: false, local: true, message: "Start the local runtime." };
  await get("refresh-runtime").events.click();
  assert.match(get("runtime-title").textContent, /unavailable/);
  assert.equal(get("check-button").disabled, true);
  get("demo-source").events.click();
  assert.equal(get("check-button").disabled, false, "Offline demo remains available");
  get("claim").value = "custom demo claim";
  await submit("claim-form");
  assert.equal(get("form-error").textContent, "Choose a bundled example.");
  assert.equal(get("check-button").disabled, false);
  assert.equal(vm.runInContext("safeSourceUrl('javascript:alert(1)')", context), null);
  console.log("PASS: demo, source library, URL/PDF imports, editable vote contract, page links, staged coverage, runtime health, model metrics, long timeouts, safe rendering, and error recovery.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
