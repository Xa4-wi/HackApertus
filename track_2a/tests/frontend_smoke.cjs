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
  removeAttribute(name) { delete this.attributes[name]; }
  querySelectorAll(selector) { return visit(this).slice(1).filter((node) => node.tagName === selector); }
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
  node.id = match[2];
  nodes.set(match[2], node);
}
const get = (id) => { assert.ok(nodes.has(id), `Missing HTML element ${id}`); return nodes.get(id); };
get("booklet-language").value = "de";
get("claim-language").value = "de";
get("source-language").value = "all";
get("import-form").elements = ["booklet-url", "booklet-file", "booklet-language", "booklet-title", "booklet-vote", "import-button"].map(get);
const visit = (node) => [node, ...node.children.flatMap(visit)];
const allNodes = () => [...nodes.values()].flatMap(visit);
const document = {
  getElementById: get,
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => new Element("#text", text),
  querySelectorAll: (selector) => selector === "[id]" ? [...nodes.values()]
    : allNodes().filter((node) => selector === "[data-check-index]" && node.dataset.checkIndex !== undefined),
  body: new Element("body"),
};

const claim = "😀 Der Beitrag beträgt CHF 200 ab 2027.";
const characters = Array.from(claim);
const amountStart = characters.findIndex((_, i) => characters.slice(i, i + 3).join("") === "CHF");
const result = {
  claim, model: "swiss-ai/Apertus-v1.5-8B", mode: "live", served_model: "local-apertus", overall: "contradiction", classification: 2,
  summary: "<img src=x onerror=alert(1)>", warnings: ["Review the original PDF."],
  checks: [
    { text: claim, start: 0, end: characters.length, dimension: "general", label: "contradiction", explanation: "The date differs.", evidence: [{ passage_id: "p1", quote: "Ab 2028: CHF 200." }] },
    { text: "CHF 200", start: amountStart, end: amountStart + 7, dimension: "amount", label: "entailment", explanation: "The amount agrees.", evidence: [{ passage_id: "p1", quote: "CHF 200" }] },
  ],
  passages: [{ id: "p1", text: "Ab 2028: CHF 200.", title: "Source", page: 2, url: "javascript:alert(1)" }],
  metrics: { input_tokens: 321, output_tokens: 123, context_tokens: null, context_characters: 1234, inference_seconds: 3.5 },
  processing: { strategy: "hierarchical", source_pages: 20, segments: 4, model_calls: 5, context_limit_tokens: 16384, coverage: "All source segments examined; selection may miss evidence." },
};
const booklet = { id: "booklet-test", title: "Voting booklet 2026-09-27 (FR)", language: "fr", page_count: 20,
  votes: ["Fee proposal"], source_url: "https://www.bk.admin.ch/source.pdf", warnings: ["One unreadable page."] };
const configuration = { model: { id: result.model, label: "Apertus 1.5 8B" }, local_model_configured: true, request_timeout_seconds: 1810, documents: [] };
let library = [];
let status = { configured: true, reachable: true, local: true, context_tokens: 16384 };
let statusError = false;
let importFailure = false;
let lastImport, lastCheck;
let importCalls = 0, checkCalls = 0, timerId = 0;
let responseOverride = null, failCheck = false, releaseCheck;
const timers = [];
const fetch = async (url, options = {}) => {
  let body, ok = true;
  if (url === "/api/config") body = configuration;
  else if (url === "/api/model/status") {
    if (statusError) throw new Error("Unavailable");
    body = status;
  } else if (url === "/api/library") body = { documents: library };
  else if (url.startsWith("/api/booklets/")) {
    importCalls++; lastImport = { url, ...options };
    if (importFailure) { ok = false; body = { error: "Invalid PDF." }; }
    else { library = [booklet]; body = { document: booklet }; }
  } else if (url === "/api/check") {
    checkCalls++; lastCheck = JSON.parse(options.body);
    await new Promise(resolve => { releaseCheck = resolve; });
    ok = !failCheck;
    body = failCheck ? { error: "Local inference failed." } : (responseOverride || result);
  } else throw new Error(`Unexpected request: ${url}`);
  return { ok, json: async () => body };
};
const context = vm.createContext({
  document, Option: function(text, value) { const node = new Element("option", text); node.value = value; return node; },
  URL, URLSearchParams, Blob, AbortController, Date, console, fetch, matchMedia: () => ({ matches: false }),
  setTimeout: (_, delay) => { timers.push(delay); return ++timerId; }, clearTimeout() {}, setInterval: () => ++timerId, clearInterval() {},
});
vm.runInContext(fs.readFileSync(path.join(staticDirectory, "app.js"), "utf8"), context);
const flush = () => new Promise(resolve => setImmediate(resolve));
const submit = id => get(id).events.submit({ preventDefault() {} });
const fillClaim = () => { get("claim").value = claim; get("claim").events.input(); };
const finishCheck = async () => { const pending = submit("claim-form"); await flush(); releaseCheck(); await pending; };

(async () => {
  await flush();
  assert.equal(get("check-button").disabled, true, "An empty library cannot run inference");
  assert.match(get("document-list").textContent, /library is empty/);
  assert.equal(get("claim").value, "", "No stored claim is inserted");
  assert.equal(get("runtime-title").textContent, "Ready");
  for (const id of ["demo-mode", "demo-source", "examples"]) assert.equal(nodes.has(id), false);

  for (const url of ["https://bk.admin.ch.evil.example/test.pdf", "https://sub.bk.admin.ch/test.pdf", "https://bk.admin.ch:8443/test.pdf"]) {
    get("booklet-url").value = url; await submit("import-form");
    assert.equal(importCalls, 0); assert.equal(get("import-error").hidden, false);
  }
  get("booklet-url").value = booklet.source_url;
  get("booklet-language").value = "fr";
  await submit("import-form");
  assert.equal(importCalls, 1);
  assert.equal(get("vote").value, "Fee proposal");
  assert.match(get("selected-source").textContent, /27 September 2026/);
  assert.equal(get("check-button").disabled, true, "Empty claims remain disabled");
  fillClaim();
  assert.equal(get("check-button").disabled, false);
  const pending = submit("claim-form"); await flush();
  assert.equal(get("check-button").disabled, true);
  assert.equal(get("claim").disabled, true);
  assert.equal(get("check-progress").hidden, false);
  releaseCheck(); await pending;
  assert.equal(lastCheck.mode, "live");
  assert.equal(lastCheck.document_id, booklet.id);
  assert.equal(lastCheck.proposal_id, undefined);
  assert.equal(lastCheck.vote, "Fee proposal");
  assert.equal(get("highlighted-claim").textContent, claim, "Unicode offsets preserve the original claim");
  assert.equal(get("result-summary").textContent, result.summary, "Model text is never inserted as HTML");
  assert.equal(get("results").hidden, false);
  assert.match(get("result-metrics").textContent, /321/);
  assert.match(get("result-processing").textContent, /Not reported/);
  assert.equal(get("result-strategy").hidden, true);
  assert.equal(get("result-coverage").hidden, true);
  assert.ok(timers.includes(1810000), "Document analysis timeout honors backend budget");
  const evidenceLinks = visit(get("evidence-content")).filter(node => node.tagName === "a");
  assert.ok(evidenceLinks.some(link => link.href.endsWith("/pdf#page=2")));
  assert.ok(evidenceLinks.every(link => !link.href.startsWith("javascript:")));
  get("highlighted-claim").children.find(node => node.tagName === "button").events.click();
  assert.match(get("evidence-content").textContent, /CHF 200/);

  get("source-language").value = "it"; get("source-language").events.change();
  assert.match(get("document-list").textContent, /No matching/);
  assert.match(get("selected-source").textContent, /French/, "Filtering does not silently switch the selected source");
  get("source-language").value = "all"; get("source-language").events.change();
  get("booklet-search").value = "2026-09-27"; get("booklet-search").events.input();
  assert.equal(get("document-list").querySelectorAll("button").length, 1);

  fillClaim(); assert.equal(get("results").hidden, true, "Editing invalidates an earlier result");
  status.reachable = false; await get("refresh-runtime").events.click();
  assert.equal(get("check-button").disabled, true); assert.equal(get("runtime-setup").hidden, false);
  const before = checkCalls; await submit("claim-form"); assert.equal(checkCalls, before, "No fallback inference when offline");
  status.reachable = true; status.local = false; await get("refresh-runtime").events.click();
  assert.equal(get("check-button").disabled, true, "A responding remote model cannot enable this UI");
  status.local = true; statusError = true; await get("refresh-runtime").events.click();
  assert.equal(get("check-button").disabled, true, "Unknown health is not ready");
  statusError = false; await get("refresh-runtime").events.click();
  assert.equal(get("check-button").disabled, false);

  responseOverride = { ...result, validation_degraded: true };
  await finishCheck(); assert.equal(get("result-validation-warning").hidden, false);
  configuration.document_strategy = "retrieval";
  responseOverride = { ...result, processing: { strategy: "retrieval", source_pages: 20,
    selected_source_pages: [2, 7, 8], selected_units: 6, source_units: 84, model_calls: 2,
    context_limit_tokens: 16384, index_cache_hit: true, query_expansion: true,
    coverage: "Apertus reviewed selected passages; relevant facts elsewhere may be missing." } };
  const fastPending = submit("claim-form"); await flush();
  assert.match(get("check-progress-title").textContent, /Finding evidence/);
  assert.match(get("check-progress-description").textContent, /selected passages/);
  releaseCheck(); await fastPending;
  assert.equal(get("result-strategy").hidden, false);
  assert.equal(get("result-strategy").textContent, "Selected passages");
  assert.equal(get("result-coverage").hidden, false);
  assert.equal(get("result-coverage").textContent, responseOverride.processing.coverage);
  assert.match(get("result-metrics").textContent, /Pages selected \/ booklet3 \/ 20/);
  assert.match(get("result-processing").textContent, /6 of 84 source passages selected/);
  assert.match(get("result-processing").textContent, /Selected PDF pages: 2, 7, 8/);
  assert.match(get("result-processing").textContent, /index: reused/);
  assert.match(get("result-processing").textContent, /terms: expanded/);
  assert.doesNotMatch(get("result-processing").textContent, /Source reviewed in one pass|Document reviewed in stages/);
  responseOverride = { ...result, processing: { ...result.processing, strategy: "full" } };
  await finishCheck();
  assert.equal(get("result-strategy").hidden, true, "A later full-source result removes the retrieval badge");
  assert.equal(get("result-coverage").hidden, true, "A later full-source result removes the retrieval warning");
  assert.match(get("result-processing").textContent, /Source reviewed in one pass/);
  responseOverride = { ...result, mode: "demo", served_model: null };
  await finishCheck(); assert.equal(get("results").hidden, true); assert.match(get("form-error").textContent, /valid live model/);
  responseOverride = null; failCheck = true;
  await finishCheck(); assert.equal(get("results").hidden, true); assert.match(get("form-error").textContent, /Local inference failed/);
  failCheck = false;

  get("upload-method").events.click();
  get("booklet-file").files = [{ name: "test.pdf", type: "application/pdf", size: 25000001 }];
  const importsBefore = importCalls; await submit("import-form"); assert.equal(importCalls, importsBefore);
  get("booklet-file").files = [{ name: "test.pdf", type: "application/pdf", size: 1234 }];
  await submit("import-form"); assert.match(lastImport.url, /\/upload\?language=fr/);
  assert.equal(lastImport.headers["Content-Type"], "application/pdf");
  importFailure = true; await submit("import-form");
  assert.match(get("import-error").textContent, /Invalid PDF/); assert.equal(get("import-button").disabled, false);
  library = []; await get("refresh-library").events.click();
  assert.equal(get("check-button").disabled, true); assert.match(get("selected-source").textContent, /Select a booklet/);
  console.log("PASS: live-only requests, local-model health gating, empty library, search/filter, imports, Unicode highlights, safe evidence, PDF links, error recovery and long analysis budgets.");
})().catch(error => { console.error(error); process.exitCode = 1; });
