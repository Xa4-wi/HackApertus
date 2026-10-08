"use strict";

// The browser only talks to the local application. Provider credentials stay on the server.
const ui = Object.fromEntries([
  "claim-form", "input-title", "proposal", "model", "claim", "claim-language", "examples", "character-count",
  "proposal-description", "live-mode", "demo-mode", "live-mode-status", "mode-description",
  "check-button", "check-button-label", "form-error", "connection-error", "results",
  "results-title", "overall-label", "result-run", "result-summary", "result-metrics", "result-warnings", "result-processing",
  "highlighted-claim", "checks", "check-count", "evidence-content", "evidence-count",
  "evidence-subtitle", "corpus-note", "download-button", "runtime-indicator", "runtime-title",
  "runtime-message", "runtime-context", "refresh-runtime", "library-source", "demo-source",
  "library-count", "library-source-panel", "demo-source-panel", "document-select", "document-details",
  "refresh-library", "library-error", "vote", "vote-options", "vote-field", "vote-help",
  "import-panel", "import-form", "url-method", "upload-method", "url-import-field", "pdf-import-field",
  "booklet-url", "booklet-file", "booklet-language", "booklet-title", "booklet-vote", "import-button",
  "import-status", "import-error", "check-progress", "check-progress-title", "check-progress-detail", "check-elapsed",
].map((id) => [id, document.getElementById(id)]));

const labels = {
  entailment: { friendly: "Supported", name: "entailment", classification: 0 },
  contradiction: { friendly: "Contradicted", name: "contradiction", classification: 2 },
  neutral: { friendly: "Unresolved", name: "neutral", classification: 1 },
};
const languageNames = { de: "German", fr: "French", it: "Italian", en: "English" };
let configuration = null;
let currentResult = null;
let busy = false;
let importing = false;
let refreshingLibrary = false;
let runtimeStatus = null;
let checkingRuntime = false;
let documents = [];
let sourceKind = "demo";
let importMethod = "url";
let resultDocument = null;
let progressTimer = null;
const emptyEvidence = ui["evidence-content"].firstElementChild.cloneNode(true);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function safeSourceUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function sourceLink(value, text) {
  const href = safeSourceUrl(value);
  if (!href) return null;
  const link = element("a", "source-link", text);
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function verdict(label) {
  const definition = labels[label] || labels.neutral;
  const badge = element("span", "verdict", `${definition.classification} · ${definition.friendly} · ${definition.name}`);
  badge.dataset.label = definition.name;
  return badge;
}

function selectedProposal() {
  return configuration?.proposals?.find((proposal) => proposal.id === ui.proposal.value);
}

function selectedDocument() {
  return documents.find((booklet) => booklet.id === ui["document-select"].value);
}

function pdfLink(booklet, text, page) {
  if (!booklet?.id) return null;
  const link = element("a", "source-link", text);
  link.href = `/api/booklets/${encodeURIComponent(booklet.id)}/pdf${Number.isInteger(page) && page > 0 ? `#page=${page}` : ""}`;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function readableDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function documentVotes(booklet) {
  return (booklet?.votes || []).map((vote) => typeof vote === "string" ? vote : (vote?.title || vote?.name || vote?.vote || "")).filter(Boolean);
}

function resetResult() {
  currentResult = null;
  resultDocument = null;
  ui.results.hidden = true;
  ui["form-error"].hidden = true;
  ui["evidence-content"].replaceChildren(emptyEvidence.cloneNode(true));
  ui["evidence-count"].textContent = "SOURCE TRAIL";
  ui["evidence-subtitle"].textContent = "The original words, kept close to the finding.";
}

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function updateCharacterCount() {
  ui["character-count"].textContent = `${ui.claim.value.length.toLocaleString()} / 2,000`;
}

function updateMode() {
  const destination = configuration?.local_model_configured ? "local Apertus runtime" : "Apertus provider";
  ui["mode-description"].textContent = selectedMode() === "live"
    ? `Sends the claim and ${sourceKind === "library" ? "booklet text" : "selected passages"} to the configured ${destination}. ${sourceKind === "library" ? "Long booklets may be processed in several stages; coverage is reported with the result." : "The result is generated by the selected model."}`
    : "The demo is a fixed walkthrough of the example claims. It does not run a model. Custom claims require Live Apertus.";
  updateControls();
}

function updateProposal() {
  const proposal = selectedProposal();
  if (!proposal) return;
  resetResult();
  const language = languageNames[proposal.language] || proposal.language;
  ui["proposal-description"].textContent = [language ? `Booklet language: ${language}` : "", proposal.description].filter(Boolean).join(" · ");
  ui.examples.replaceChildren();
  if (proposal.examples?.length) {
    ui.examples.append(element("span", "examples-label", "TRY AN EXAMPLE"));
    for (const example of proposal.examples) {
      const button = element("button", "example-button", example.title);
      button.type = "button";
      button.addEventListener("click", () => {
        ui.claim.value = example.claim;
        ui["claim-language"].value = ["de", "fr", "it"].includes(example.claim_language) ? example.claim_language : "auto";
        updateCharacterCount();
        ui["form-error"].hidden = true;
        ui.claim.focus();
      });
      ui.examples.append(button);
    }
    ui.claim.value = proposal.examples[0].claim;
    ui["claim-language"].value = ["de", "fr", "it"].includes(proposal.examples[0].claim_language) ? proposal.examples[0].claim_language : "auto";
  } else {
    ui.claim.value = "";
    ui["claim-language"].value = "auto";
  }
  updateCharacterCount();
  ui.vote.value = proposal.vote || proposal.title || "";
  ui.vote.required = false;
  ui["vote-help"].textContent = "This walkthrough uses a fixed evidence set. Import a booklet to examine a different proposal.";
  ui["corpus-note"].replaceChildren();
  ui["corpus-note"].append(
    element("strong", "", proposal.is_fixture ? "Illustrative evidence set" : "Selected evidence set"),
    element("p", "", proposal.is_fixture
      ? "This proposal and its passages are fictional fixtures for testing the workflow. They are not official voting material."
      : "Findings are limited to the bundled passages for this proposal. Review the original source for its full context."),
  );
  const link = sourceLink(proposal.source_url, "View source ↗");
  if (link) ui["corpus-note"].append(link);
  ui["corpus-note"].hidden = false;
}

function setBusy(value) {
  busy = value;
  document.body.classList.toggle("is-loading", value);
  ui["claim-form"].setAttribute("aria-busy", String(value));
  ui["check-button-label"].textContent = value ? "Reading the evidence…" : "Examine claim";
  ui["check-progress"].hidden = !value;
  updateControls();
}

function updateControls() {
  const locked = busy || importing || !configuration;
  const missingSource = sourceKind === "library" ? !selectedDocument() : !selectedProposal();
  const liveUnavailable = selectedMode() === "live" && (!configuration?.live_ready || runtimeStatus?.reachable === false);
  ui["check-button"].disabled = locked || missingSource || liveUnavailable;
  for (const id of ["proposal", "model", "claim", "claim-language", "library-source", "demo-source", "document-select"]) ui[id].disabled = locked;
  ui["demo-source"].disabled = locked || !configuration?.proposals?.length;
  ui["document-select"].disabled = locked || !documents.length;
  ui.vote.disabled = locked || sourceKind !== "library";
  ui["refresh-library"].disabled = locked || refreshingLibrary;
  ui["refresh-runtime"].disabled = busy || checkingRuntime;
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.disabled = locked || (input.value === "live" && !configuration?.live_ready)
      || (input.value === "demo" && sourceKind === "library");
  });
  document.querySelectorAll(".example-button").forEach((button) => { button.disabled = locked; });
  for (const control of ui["import-form"].elements) control.disabled = busy || importing || !configuration;
  ui["booklet-url"].disabled = busy || importing || !configuration || importMethod !== "url";
  ui["booklet-file"].disabled = busy || importing || !configuration || importMethod !== "upload";
  ui["url-method"].disabled = busy || importing;
  ui["upload-method"].disabled = busy || importing;
}

function setSourceKind(kind) {
  sourceKind = kind;
  ui["library-source"].setAttribute("aria-pressed", String(kind === "library"));
  ui["demo-source"].setAttribute("aria-pressed", String(kind === "demo"));
  ui["library-source-panel"].hidden = kind !== "library";
  ui["demo-source-panel"].hidden = kind !== "demo";
  ui["demo-mode"].checked = kind === "demo";
  ui["live-mode"].checked = kind === "library";
  if (kind === "library") updateDocument();
  else updateProposal();
  updateMode();
}

function renderLibrary(preferredId) {
  const selectedId = ui["document-select"].value;
  const previousId = preferredId || selectedId;
  ui["library-count"].textContent = String(documents.length);
  const options = documents.map((booklet) => new Option(
    `${booklet.title || "Untitled booklet"} · ${languageNames[booklet.language] || booklet.language || ""}`, booklet.id,
  ));
  ui["document-select"].replaceChildren(...(options.length ? options : [new Option("No booklets imported yet", "")]));
  if (documents.some((booklet) => booklet.id === previousId)) ui["document-select"].value = previousId;
  if (sourceKind === "library" && (preferredId || selectedId !== ui["document-select"].value)) updateDocument();
  updateControls();
}

function updateDocument() {
  resetResult();
  ui.examples.replaceChildren();
  ui.claim.value = "";
  ui["claim-language"].value = "auto";
  updateCharacterCount();
  ui.vote.required = true;
  ui["vote-help"].textContent = "A booklet can cover several proposals. Name the one your claim concerns; suggestions remain editable.";
  const booklet = selectedDocument();
  const votes = documentVotes(booklet);
  ui["vote-options"].replaceChildren(...votes.map((vote) => new Option(vote, vote)));
  ui.vote.value = votes[0] || "";
  ui["document-details"].replaceChildren();
  ui["corpus-note"].replaceChildren();
  ui["corpus-note"].hidden = !booklet;
  if (!booklet) {
    ui["document-details"].append(element("p", "library-empty", "Your next source starts here. Add an official voting booklet using its PDF link, or upload a copy below."));
    updateControls();
    return;
  }
  const metadata = element("div", "document-metadata");
  const language = languageNames[booklet.language] || booklet.language || "Language not specified";
  metadata.append(element("span", "metadata-chip", language));
  if (Number.isFinite(booklet.page_count)) metadata.append(element("span", "metadata-chip", `${booklet.page_count} pages`));
  if (Number.isFinite(booklet.character_count)) metadata.append(element("span", "metadata-chip", `${booklet.character_count.toLocaleString()} characters`));
  const origin = safeSourceUrl(booklet.source_url);
  const links = element("div", "document-links");
  links.append(pdfLink(booklet, "Read the PDF ↗"));
  const original = sourceLink(booklet.source_url, "Original source ↗");
  if (original) links.append(original);
  ui["document-details"].append(element("h3", "document-title", booklet.title || "Voting booklet"), metadata);
  const sourceDescription = origin ? `Source: ${new URL(origin).hostname}` : "Source: uploaded PDF";
  const imported = readableDate(booklet.imported_at);
  ui["document-details"].append(element("p", "document-origin", `${sourceDescription}${imported ? ` · Added ${imported}` : ""}`), links);
  for (const warning of booklet.warnings || []) ui["document-details"].append(element("p", "document-warning", warning));
  ui["corpus-note"].append(element("strong", "", "Selected voting booklet"), element("p", "", booklet.title || "Voting booklet"),
    element("p", "", `${language}${Number.isFinite(booklet.page_count) ? ` · ${booklet.page_count} original PDF pages` : ""}. Quotations remain linked to the source page.`), pdfLink(booklet, "Open source PDF ↗"));
  updateControls();
}

async function refreshLibrary(preferredId) {
  if (refreshingLibrary) return;
  refreshingLibrary = true;
  ui["library-error"].hidden = true;
  updateControls();
  try {
    const response = await fetch("/api/library");
    const data = await response.json();
    if (!response.ok || !Array.isArray(data.documents)) throw new Error(data.error || "Could not refresh the booklet library.");
    documents = data.documents;
    renderLibrary(preferredId);
  } catch (error) {
    ui["library-error"].textContent = error instanceof TypeError ? "Could not reach the local library. Check the server and refresh again." : error.message;
    ui["library-error"].hidden = false;
  } finally {
    refreshingLibrary = false;
    updateControls();
  }
}

async function refreshRuntime() {
  if (checkingRuntime) return;
  checkingRuntime = true;
  updateControls();
  ui["runtime-indicator"].dataset.state = "checking";
  ui["runtime-message"].textContent = "Checking the model endpoint without running inference…";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch("/api/model/status", { signal: controller.signal });
    const status = await response.json();
    if (!response.ok || typeof status.reachable !== "boolean") throw new Error("Status unavailable");
    runtimeStatus = status;
    const place = status.local ? "Local Apertus" : "Apertus endpoint";
    ui["runtime-title"].textContent = status.reachable ? `${place} is reachable` : (status.configured ? `${place} is unavailable` : "Model endpoint not configured");
    ui["runtime-indicator"].dataset.state = status.reachable ? "ready" : "unavailable";
    ui["runtime-message"].textContent = status.message || (status.reachable ? "Connection checked. Model outputs still require source review." : "Configure or start the runtime, then refresh its status.");
    ui["runtime-context"].textContent = Number.isFinite(status.context_tokens) ? `${status.context_tokens.toLocaleString()} token context` : "";
    ui["live-mode-status"].textContent = status.reachable ? (status.local ? "Local runtime reachable" : "Endpoint reachable") : (status.configured ? "Runtime unavailable" : "Set up .env to enable");
  } catch {
    runtimeStatus = null;
    ui["runtime-title"].textContent = configuration?.local_model_configured ? "Local model configured" : (configuration?.live_ready ? "Model endpoint configured" : "Model endpoint not configured");
    ui["runtime-indicator"].dataset.state = "unknown";
    ui["runtime-message"].textContent = "Could not verify runtime health. Refresh to try again; configuration alone does not confirm availability.";
    ui["runtime-context"].textContent = "";
    ui["live-mode-status"].textContent = configuration?.live_ready ? "Health not verified" : "Set up .env to enable";
  } finally {
    clearTimeout(timeout);
    checkingRuntime = false;
    updateControls();
  }
}

function setImportMethod(method) {
  importMethod = method;
  ui["url-method"].setAttribute("aria-pressed", String(method === "url"));
  ui["upload-method"].setAttribute("aria-pressed", String(method === "upload"));
  ui["url-import-field"].hidden = method !== "url";
  ui["pdf-import-field"].hidden = method !== "upload";
  ui["booklet-url"].required = method === "url";
  ui["booklet-file"].required = method === "upload";
  ui["import-error"].hidden = true;
  updateControls();
}

function renderHighlights(result) {
  // API offsets are Python/Unicode code-point offsets, not JavaScript UTF-16 offsets.
  const characters = Array.from(result.claim);
  let ranges = result.checks.map((check, index) => ({ ...check, index })).filter((check) => (
    Number.isInteger(check.start) && Number.isInteger(check.end) &&
    check.start >= 0 && check.end > check.start && check.end <= characters.length &&
    characters.slice(check.start, check.end).join("") === check.text
  )).sort((a, b) => a.start - b.start || a.end - b.end);
  // The official whole-claim classification is shown above the text. Highlight its
  // narrower explanatory checks when available so the exact differing words stay visible.
  if (ranges.some((check) => check.start > 0 || check.end < characters.length)) {
    ranges = ranges.filter((check) => check.start > 0 || check.end < characters.length);
  }
  ui["highlighted-claim"].replaceChildren();
  let position = 0;
  for (const check of ranges) {
    // Overlapping checks remain available in the list, without duplicating claim words.
    if (check.start < position) continue;
    ui["highlighted-claim"].append(document.createTextNode(characters.slice(position, check.start).join("")));
    const highlight = element("button", "claim-highlight", check.text);
    highlight.type = "button";
    highlight.dataset.label = (labels[check.label] || labels.neutral).name;
    highlight.dataset.checkIndex = String(check.index);
    highlight.setAttribute("aria-label", `${check.text}: ${(labels[check.label] || labels.neutral).friendly}. Show evidence.`);
    highlight.addEventListener("click", () => selectCheck(check.index, true));
    ui["highlighted-claim"].append(highlight);
    position = check.end;
  }
  ui["highlighted-claim"].append(document.createTextNode(characters.slice(position).join("")));
}

function renderChecks(result) {
  ui.checks.replaceChildren();
  ui["check-count"].textContent = `${result.checks.length} ${result.checks.length === 1 ? "finding" : "findings"}`;
  result.checks.forEach((check, index) => {
    const card = element("button", "check-card");
    card.type = "button";
    card.dataset.checkIndex = String(index);
    const top = element("span", "check-topline");
    top.append(element("span", "check-dimension", check.text === result.claim ? "Whole claim" : (check.dimension || `Part ${index + 1}`)), verdict(check.label));
    const evidenceCount = (check.evidence || []).length;
    card.append(
      top,
      element("span", "check-text", `“${check.text}”`),
      element("span", "check-explanation", check.explanation),
      element("span", "check-evidence-hint", evidenceCount
        ? `${evidenceCount} evidence ${evidenceCount === 1 ? "passage" : "passages"} · Follow the source →`
        : "No conclusive evidence cited"),
    );
    card.addEventListener("click", () => selectCheck(index, true));
    ui.checks.append(card);
  });
}

function renderEvidence(check) {
  ui["evidence-content"].replaceChildren();
  const selected = element("p", "selected-phrase", `“${check.text}”`);
  const list = element("div", "evidence-items");
  const evidence = check.evidence || [];
  ui["evidence-count"].textContent = `${evidence.length} ${evidence.length === 1 ? "PASSAGE" : "PASSAGES"}`;
  ui["evidence-subtitle"].textContent = "Evidence for the selected part of your claim.";
  if (!evidence.length) {
    list.append(element("p", "evidence-empty", "No passage establishes this part of the claim. Missing evidence does not establish that it is false."));
  }
  for (const citation of evidence) {
    const passage = currentResult.passages.find((item) => item.id === citation.passage_id);
    const card = element("article", "evidence-item");
    const header = element("div", "evidence-item-header");
    header.append(element("span", "passage-id", citation.passage_id));
    if (passage?.page !== undefined && passage.page !== null) header.append(element("span", "page-number", `PAGE ${passage.page}`));
    card.append(header, element("h3", "passage-title", passage?.title || "Cited passage"));
    card.append(element("blockquote", "evidence-quote", citation.quote || passage?.text || "No excerpt provided."));
    if (passage?.attribution) card.append(element("p", "evidence-attribution", `Attribution: ${passage.attribution}`));
    if (!passage) card.append(element("p", "evidence-attribution", "Source metadata is missing for this citation."));
    const link = sourceLink(passage?.url, "Open original source ↗");
    if (link) card.append(link);
    const pageLink = pdfLink(resultDocument, Number.isInteger(passage?.page) ? `View PDF · page ${passage.page} ↗` : "Open source PDF ↗", passage?.page);
    if (pageLink) card.append(pageLink);
    if (passage?.text && passage.text !== citation.quote) {
      const details = element("details", "evidence-details");
      details.append(element("summary", "", "Read the full passage"), element("p", "full-passage", passage.text));
      card.append(details);
    }
    list.append(card);
  }
  ui["evidence-content"].append(selected, list);
}

function selectCheck(index, userInitiated = false) {
  const check = currentResult?.checks[index];
  if (!check) return;
  document.querySelectorAll("[data-check-index]").forEach((node) => {
    const active = node.dataset.checkIndex === String(index);
    node.classList.toggle("is-active", active);
    node.setAttribute("aria-pressed", String(active));
  });
  renderEvidence(check);
  if (userInitiated && matchMedia("(max-width: 820px)").matches) {
    document.getElementById("evidence-title").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  }
}

function renderResult(result) {
  currentResult = result;
  resultDocument = sourceKind === "library" ? selectedDocument() : null;
  ui.results.hidden = false;
  const overall = verdict(result.overall);
  ui["overall-label"].textContent = overall.textContent;
  ui["overall-label"].dataset.label = overall.dataset.label;
  const modelName = configuration.models.find((model) => model.id === result.model)?.label || result.model;
  ui["result-run"].textContent = result.mode === "demo" ? "DEMO · NO MODEL CALL" : `LIVE · ${modelName}`;
  ui["result-summary"].textContent = result.summary;
  renderMetrics(result);
  renderProcessing(result);
  ui["result-warnings"].replaceChildren();
  for (const warning of result.warnings || []) ui["result-warnings"].append(element("p", "result-warning", warning));
  renderHighlights(result);
  renderChecks(result);
  if (result.checks.length) selectCheck(0);
  else {
    ui["evidence-content"].replaceChildren(element("p", "evidence-empty", "No checkable parts were returned for this claim."));
    ui["evidence-count"].textContent = "0 PASSAGES";
  }
  ui["results-title"].focus({ preventScroll: true });
  ui.results.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
}

function renderProcessing(result) {
  const processing = result.processing;
  const container = ui["result-processing"];
  container.replaceChildren();
  container.hidden = !processing || result.mode === "demo";
  if (container.hidden) return;
  const hierarchical = processing.strategy === "hierarchical";
  const empty = processing.strategy === "empty";
  container.append(element("p", "small-label", "SOURCE COVERAGE"),
    element("h3", "processing-title", empty ? "No source text to assess" : (hierarchical ? "Whole-document review in stages" : "Full-document review")),
    element("p", "processing-description", empty ? "The source did not provide usable text; no model assessment was made."
      : (hierarchical
        ? "Each source segment was read, then selected exact excerpts were consolidated for the final assessment. Inspect the quotations and limitations below."
        : "The source text was supplied together for this assessment. The result remains limited to that source and the model’s interpretation.")));
  const details = [];
  const pageCount = Array.isArray(processing.source_pages) ? processing.source_pages.length : processing.source_pages;
  const segments = Array.isArray(processing.segments) ? processing.segments.length : processing.segments;
  if (Number.isFinite(pageCount)) details.push(`${pageCount} source pages`);
  if (Number.isFinite(segments)) details.push(`${segments} segments`);
  if (Number.isFinite(processing.model_calls)) details.push(`${processing.model_calls} model calls`);
  if (Number.isFinite(processing.context_limit_tokens)) details.push(`${processing.context_limit_tokens.toLocaleString()}-token context window`);
  if (details.length) container.append(element("p", "processing-detail", details.join(" · ")));
  if (typeof processing.coverage === "string" && processing.coverage) container.append(element("p", "processing-description", processing.coverage));
}

function renderMetrics(result) {
  const container = ui["result-metrics"];
  container.replaceChildren();
  container.hidden = false;
  if (result.mode === "demo") {
    container.append(element("p", "demo-metrics-note", "Fixed example walkthrough · token use and model inference time are not measured."));
    return;
  }
  const metrics = result.metrics || {};
  const count = (value) => typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : "Not reported";
  const values = [
    ["Input tokens", count(metrics.input_tokens)],
    ["Output tokens", count(metrics.output_tokens)],
    ["Context tokens", count(metrics.context_tokens)],
    ["Inference", typeof metrics.inference_seconds === "number" ? `${metrics.inference_seconds.toFixed(2)} s` : "Not reported"],
  ];
  const list = element("dl", "metric-list");
  for (const [title, value] of values) {
    const item = element("div", "metric");
    item.append(element("dt", "", title), element("dd", "", value));
    list.append(item);
  }
  container.append(list);
  const details = [];
  if (metrics.token_usage_source) details.push(`Token usage: ${String(metrics.token_usage_source).replaceAll("_", " ")}`);
  if (typeof metrics.context_characters === "number") details.push(`${metrics.context_characters.toLocaleString()} context characters`);
  if (details.length) container.append(element("p", "metrics-note", details.join(" · ")));
  if (result.served_model) container.append(element("p", "metrics-note served-model", `Served model: ${result.served_model}`));
}

ui["claim-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || importing || !configuration) return;
  const claim = ui.claim.value.trim();
  ui["form-error"].hidden = true;
  if (!claim) {
    ui["form-error"].textContent = "Enter a claim or choose an example first.";
    ui["form-error"].hidden = false;
    ui.claim.focus();
    return;
  }
  if (sourceKind === "library" && (!selectedDocument() || !ui.vote.value.trim())) {
    ui["form-error"].textContent = "Select a booklet and enter the proposal being checked.";
    ui["form-error"].hidden = false;
    ui.vote.focus();
    return;
  }
  const source = sourceKind === "library" ? { document_id: selectedDocument().id, vote: ui.vote.value.trim() } : { proposal_id: ui.proposal.value };
  const payload = { ...source, model: ui.model.value, claim, claim_language: ui["claim-language"].value, mode: selectedMode() };
  const controller = new AbortController();
  const configuredTimeout = configuration.request_timeout_seconds;
  // Leave the server's provider timeout a margin to return its own error. Older
  // servers or malformed config use the supported maximum rather than failing early.
  const timeoutSeconds = typeof configuredTimeout === "number" && Number.isFinite(configuredTimeout)
    && configuredTimeout >= 11 && configuredTimeout <= 86400 ? configuredTimeout : 610;
  const timeout = setTimeout(() => controller.abort(), timeoutSeconds * 1000);
  const started = Date.now();
  ui["check-progress-title"].textContent = selectedMode() === "demo" ? "Opening the walkthrough" : "Reading the source with Apertus";
  ui["check-progress-detail"].textContent = sourceKind === "library"
    ? "Long booklets may need several model passes. Evidence and coverage will appear together when complete."
    : "Comparing the claim against the selected passages…";
  ui["check-elapsed"].textContent = "0s";
  progressTimer = setInterval(() => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    ui["check-elapsed"].textContent = seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }, 1000);
  setBusy(true);
  try {
    const response = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : "The claim could not be checked. Please try again.");
    if (!Array.isArray(result.checks) || !Array.isArray(result.passages) || typeof result.claim !== "string") {
      throw new Error("The server returned an incomplete result. Please try again.");
    }
    renderResult(result);
  } catch (error) {
    ui["form-error"].textContent = error.name === "AbortError"
      ? "The check timed out. The provider may still be processing it; try again when it is available."
      : (error instanceof TypeError ? "Could not reach the local server. Check that it is running, then try again." : error.message);
    ui["form-error"].hidden = false;
  } finally {
    clearTimeout(timeout);
    clearInterval(progressTimer);
    progressTimer = null;
    setBusy(false);
  }
});

ui["import-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  if (importing || busy || !configuration) return;
  ui["import-error"].hidden = true;
  const metadata = { language: ui["booklet-language"].value };
  if (ui["booklet-title"].value.trim()) metadata.title = ui["booklet-title"].value.trim();
  if (ui["booklet-vote"].value.trim()) metadata.vote = ui["booklet-vote"].value.trim();
  let endpoint, options;
  try {
    if (importMethod === "url") {
      let url;
      try { url = new URL(ui["booklet-url"].value.trim()); } catch { throw new Error("Enter a valid HTTPS link to the official voting booklet PDF."); }
      if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")
          || !["bk.admin.ch", "www.bk.admin.ch"].includes(url.hostname)) {
        throw new Error("Official link import accepts HTTPS URLs on bk.admin.ch or www.bk.admin.ch without a custom port. Use Upload PDF for a saved document.");
      }
      url.hash = "";
      endpoint = "/api/booklets/import";
      options = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...metadata, url: url.href }) };
    } else {
      const file = ui["booklet-file"].files?.[0];
      if (!file || !file.size) throw new Error("Choose a nonempty PDF file to upload.");
      if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") throw new Error("Choose a PDF file.");
      endpoint = `/api/booklets/upload?${new URLSearchParams(metadata)}`;
      options = { method: "POST", headers: { "Content-Type": "application/pdf" }, body: file };
    }
  } catch (error) {
    ui["import-error"].textContent = error.message;
    ui["import-error"].hidden = false;
    return;
  }
  importing = true;
  updateControls();
  ui["import-form"].setAttribute("aria-busy", "true");
  ui["import-button"].textContent = "Adding booklet…";
  ui["import-status"].textContent = importMethod === "url" ? "Downloading the official PDF and extracting its pages…" : "Uploading the PDF and extracting its pages…";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 310000);
  try {
    const response = await fetch(endpoint, { ...options, signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The booklet could not be imported.");
    if (!data.document?.id) throw new Error("The import returned incomplete booklet metadata. Refresh the library to check its status.");
    documents = [...documents.filter((booklet) => booklet.id !== data.document.id), data.document];
    renderLibrary(data.document.id);
    setSourceKind("library");
    await refreshLibrary(data.document.id);
    ui["import-status"].textContent = "Booklet added. Name the proposal, enter a claim, and examine its evidence.";
    ui["import-panel"].open = false;
    ui["input-title"].focus?.({ preventScroll: true });
    document.getElementById("input-title").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  } catch (error) {
    ui["import-error"].textContent = error.name === "AbortError"
      ? "Import timed out. The server may still be extracting pages; refresh the library before retrying."
      : (error instanceof TypeError ? "Could not reach the local server. Check its connection and try again." : error.message);
    ui["import-error"].hidden = false;
    ui["import-status"].textContent = "No model was called during this import.";
  } finally {
    clearTimeout(timeout);
    importing = false;
    ui["import-form"].setAttribute("aria-busy", "false");
    ui["import-button"].textContent = "Add to library ↗";
    updateControls();
  }
});

ui["download-button"].addEventListener("click", () => {
  if (!currentResult) return;
  const blob = new Blob([JSON.stringify(currentResult, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = element("a");
  link.href = url;
  link.download = "claimlens-review.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

ui.claim.addEventListener("input", updateCharacterCount);
ui.proposal.addEventListener("change", updateProposal);
ui["document-select"].addEventListener("change", updateDocument);
ui["library-source"].addEventListener("click", () => setSourceKind("library"));
ui["demo-source"].addEventListener("click", () => setSourceKind("demo"));
ui["refresh-library"].addEventListener("click", () => refreshLibrary());
ui["refresh-runtime"].addEventListener("click", refreshRuntime);
ui["url-method"].addEventListener("click", () => setImportMethod("url"));
ui["upload-method"].addEventListener("click", () => setImportMethod("upload"));
document.querySelectorAll('input[name="mode"]').forEach((input) => input.addEventListener("change", updateMode));

async function initialize() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("Could not load the prototype configuration.");
    const config = await response.json();
    if (!config.models?.length) throw new Error("No models are configured. Check the local setup.");
    if (!Array.isArray(config.proposals)) config.proposals = [];
    configuration = config;
    documents = Array.isArray(config.documents) ? config.documents : [];
    ui.model.replaceChildren(...config.models.map((model) => new Option(model.label, model.id)));
    if (config.default_model) ui.model.value = config.default_model;
    ui.proposal.replaceChildren(...config.proposals.map((proposal) => new Option(proposal.title, proposal.id)));
    ui["live-mode-status"].textContent = config.live_ready
      ? (config.local_model_configured ? "Local model configured" : "Provider configured")
      : "Set up .env to enable";
    renderLibrary();
    setSourceKind(documents.length || !config.proposals.length ? "library" : "demo");
    setImportMethod("url");
    setBusy(false);
    refreshRuntime();
  } catch (error) {
    configuration = null;
    ui["connection-error"].textContent = `${error instanceof TypeError ? "Could not reach the local application." : error.message} Start the server and reload this page.`;
    ui["connection-error"].hidden = false;
    ui["live-mode-status"].textContent = "Server unavailable";
    setBusy(false);
  }
}

initialize();
