"use strict";

// The browser sends source IDs and claims only to this local application.
const ui = Object.fromEntries(Array.from(document.querySelectorAll("[id]"), (node) => [node.id, node]));
const labels = {
  entailment: { friendly: "Supported", name: "entailment", classification: 0 },
  contradiction: { friendly: "Contradicted", name: "contradiction", classification: 2 },
  neutral: { friendly: "Unresolved", name: "neutral", classification: 1 },
};
const languageNames = { de: "German", fr: "French", it: "Italian" };
let configuration = null;
let documents = [];
let selectedId = null;
let runtimeStatus = null;
let currentResult = null;
let resultDocument = null;
let busy = false;
let importing = false;
let refreshingLibrary = false;
let checkingRuntime = false;
let importMethod = "url";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch { return null; }
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

function pdfLink(booklet, text, page) {
  if (!booklet?.id) return null;
  const link = element("a", "source-link", text);
  link.href = `/api/booklets/${encodeURIComponent(booklet.id)}/pdf${Number.isInteger(page) && page > 0 ? `#page=${page}` : ""}`;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function verdict(label) {
  const name = Object.hasOwn(labels, label) ? label : "neutral";
  const badge = element("span", "verdict", `${labels[name].classification} · ${labels[name].friendly}`);
  badge.dataset.label = name;
  return badge;
}

function selectedDocument() {
  return documents.find((booklet) => booklet.id === selectedId);
}

function pageLabel(count) {
  return `${count} ${count === 1 ? "page" : "pages"}`;
}

function bookletTitle(booklet) {
  const standard = /^Voting booklet (\d{4}-\d{2}-\d{2}) \([A-Z]{2}\)$/.exec(booklet.title || "");
  if (!standard) return booklet.title || "Untitled booklet";
  const date = new Date(standard[1] + "T12:00:00Z");
  return Number.isNaN(date.getTime()) ? booklet.title : date.toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
}

function isReady() {
  return configuration?.local_model_configured === true && runtimeStatus?.local === true && runtimeStatus?.reachable === true;
}

function resetResult() {
  currentResult = null;
  resultDocument = null;
  ui.results.hidden = true;
  ui["empty-result"].hidden = false;
  ui["form-error"].hidden = true;
}

function updateControls() {
  const locked = busy || importing || !configuration;
  const source = selectedDocument();
  for (const id of ["booklet-search", "source-language", "vote", "claim", "claim-language"]) ui[id].disabled = locked;
  for (const button of ui["document-list"].querySelectorAll("button")) button.disabled = locked;
  ui["refresh-library"].disabled = locked || refreshingLibrary;
  ui["refresh-runtime"].disabled = busy || checkingRuntime || !configuration;
  ui["check-button"].disabled = locked || !source || !isReady() || !ui.claim.value.trim() || !ui.vote.value.trim();
  ui["check-hint"].textContent = !isReady() ? "Start local Apertus to enable claim checking."
    : !source ? "Choose a booklet from the library."
      : "Processed by local Apertus. Full booklets can take a few minutes.";
  for (const control of ui["import-form"].elements) control.disabled = locked;
  ui["booklet-url"].disabled = locked || importMethod !== "url";
  ui["booklet-file"].disabled = locked || importMethod !== "upload";
  ui["url-method"].disabled = locked;
  ui["upload-method"].disabled = locked;
}

function updateClaim() {
  ui["character-count"].textContent = `${Array.from(ui.claim.value).length.toLocaleString()} / 2,000`;
  resetResult();
  updateControls();
}

function renderLibrary() {
  const query = ui["booklet-search"].value.trim().toLocaleLowerCase();
  const language = ui["source-language"].value;
  const filtered = documents.filter((booklet) => (language === "all" || booklet.language === language)
    && `${booklet.title} ${bookletTitle(booklet)} ${languageNames[booklet.language]}`.toLocaleLowerCase().includes(query))
    .sort((a, b) => (b.title || "").localeCompare(a.title || "") || a.language.localeCompare(b.language));
  ui["library-count"].textContent = query || language !== "all"
    ? `${filtered.length} of ${documents.length} booklets` : `${documents.length} booklets`;
  ui["document-list"].replaceChildren();
  if (!filtered.length) {
    ui["document-list"].append(element("p", "library-empty", documents.length
      ? "No matching booklets. Try another date, title or language."
      : "Your library is empty. Add an official PDF link or upload a booklet below."));
  }
  for (const booklet of filtered) {
    const button = element("button", "document-option");
    button.type = "button";
    button.dataset.documentId = booklet.id;
    button.setAttribute("aria-pressed", String(booklet.id === selectedId));
    const copy = element("span", "document-option-copy");
    copy.append(element("strong", "", bookletTitle(booklet)), element("small", "",
      `${languageNames[booklet.language] || booklet.language} · ${pageLabel(booklet.page_count)}`));
    const icon = element("span", "file-icon", "PDF");
    icon.setAttribute("aria-hidden", "true");
    const mark = element("span", "selected-mark", "✓");
    mark.setAttribute("aria-hidden", "true");
    button.append(icon, copy, mark);
    button.addEventListener("click", () => {
      if (busy || importing) return;
      selectedId = booklet.id;
      for (const item of ui["document-list"].querySelectorAll("button")) item.setAttribute("aria-pressed", String(item.dataset.documentId === selectedId));
      updateDocument();
    });
    ui["document-list"].append(button);
  }
  updateControls();
}

function updateDocument() {
  resetResult();
  const booklet = selectedDocument();
  ui["document-details"].replaceChildren();
  ui["document-details"].hidden = !booklet;
  ui["selected-source"].replaceChildren();
  const votes = (booklet?.votes || []).map((vote) => typeof vote === "string" ? vote : (vote.title || vote.name || vote.vote || "")).filter(Boolean);
  ui["vote-options"].replaceChildren(...votes.map((vote) => new Option(vote, vote)));
  // Multiple proposals need an explicit choice; one proposal can be prefilled.
  ui.vote.value = votes.length === 1 ? votes[0] : "";
  if (!booklet) {
    ui["selected-source"].textContent = "Select a booklet from the library to begin.";
    updateControls();
    return;
  }
  const icon = element("span", "file-icon", "PDF");
  icon.setAttribute("aria-hidden", "true");
  ui["selected-source"].append(icon, element("strong", "", bookletTitle(booklet)),
    element("span", "", `· ${languageNames[booklet.language]} · ${pageLabel(booklet.page_count)}`));
  const links = element("div", "document-links");
  links.append(pdfLink(booklet, "Open PDF ↗"));
  const original = sourceLink(booklet.source_url, "Official source ↗");
  if (original) links.append(original);
  ui["document-details"].append(links);
  if (booklet.warnings?.length) {
    const notes = element("details", "source-notes");
    notes.append(element("summary", "", `${booklet.warnings.length} extraction ${booklet.warnings.length === 1 ? "note" : "notes"}`));
    for (const warning of booklet.warnings) notes.append(element("p", "document-warning", warning));
    ui["document-details"].append(notes);
  }
  updateControls();
}

async function refreshLibrary() {
  if (refreshingLibrary || busy || importing) return;
  refreshingLibrary = true;
  ui["library-error"].hidden = true;
  updateControls();
  try {
    const response = await fetch("/api/library");
    const data = await response.json();
    if (!response.ok || !Array.isArray(data.documents)) throw new Error(data.error || "Could not refresh the booklet library.");
    documents = data.documents;
    if (selectedId && !selectedDocument()) { selectedId = null; updateDocument(); }
    renderLibrary();
  } catch (error) {
    ui["library-error"].textContent = error instanceof TypeError ? "Could not reach the local library. Start the app server and try again." : error.message;
    ui["library-error"].hidden = false;
  } finally { refreshingLibrary = false; updateControls(); }
}

async function refreshRuntime() {
  if (checkingRuntime) return;
  checkingRuntime = true;
  runtimeStatus = null;
  ui["runtime-indicator"].dataset.state = "checking";
  ui["runtime-title"].textContent = "Checking connection";
  updateControls();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch("/api/model/status", { signal: controller.signal });
    const status = await response.json();
    if (!response.ok || typeof status.reachable !== "boolean") throw new Error("Status unavailable");
    runtimeStatus = status;
    const ready = isReady();
    ui["runtime-title"].textContent = ready ? "Ready" : (configuration.local_model_configured ? "Offline" : "Local setup needed");
    ui["runtime-indicator"].dataset.state = ready ? "ready" : "unavailable";
    ui["runtime-message"].textContent = ready ? "Connected. Each check runs on local Apertus."
      : configuration.local_model_configured ? "The local model is not responding." : "The browser requires a local Apertus endpoint.";
    ui["runtime-context"].textContent = ready && Number.isFinite(status.context_tokens) ? `${status.context_tokens.toLocaleString()} context` : "";
  } catch {
    ui["runtime-title"].textContent = "Connection not verified";
    ui["runtime-indicator"].dataset.state = "unavailable";
    ui["runtime-message"].textContent = "Could not check model status. Make sure the app and model are running, then refresh.";
    ui["runtime-context"].textContent = "";
  } finally {
    clearTimeout(timeout);
    checkingRuntime = false;
    ui["runtime-setup"].hidden = isReady();
    ui["runtime-config-help"].hidden = configuration?.local_model_configured === true;
    updateControls();
  }
}

function setImportMethod(method) {
  importMethod = method;
  for (const value of ["url", "upload"]) ui[`${value}-method`].setAttribute("aria-pressed", String(value === method));
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

function renderResult(result, source) {
  currentResult = result;
  resultDocument = source;
  ui.results.hidden = false;
  ui["empty-result"].hidden = true;
  const badge = verdict(result.overall);
  ui["overall-label"].textContent = badge.textContent;
  ui["overall-label"].dataset.label = badge.dataset.label;
  ui["result-run"].textContent = `Local ${configuration.model.label}`;
  ui["result-source"].textContent = `${bookletTitle(source)} · ${languageNames[source.language]}`;
  ui["result-summary"].textContent = result.summary;
  ui["result-validation-warning"].hidden = !result.validation_degraded;
  const metrics = result.metrics || {};
  const processing = result.processing || {};
  const retrieval = processing.strategy === "retrieval";
  const selectedPages = Array.isArray(processing.selected_source_pages)
    ? processing.selected_source_pages.filter((page) => Number.isInteger(page) && page > 0) : [];
  ui["result-strategy"].hidden = !retrieval;
  ui["result-strategy"].textContent = retrieval ? "Selected passages" : "";
  ui["result-coverage"].hidden = !retrieval;
  ui["result-coverage"].textContent = retrieval
    ? processing.coverage || "Apertus assessed selected passages. Evidence elsewhere in the booklet may be missing." : "";
  const count = (value) => Number.isFinite(value) ? value.toLocaleString() : "Not reported";
  const values = [
    ["Analysis time", Number.isFinite(metrics.inference_seconds) ? `${metrics.inference_seconds.toFixed(1)} s` : "Not reported"],
    ["Input tokens", count(metrics.input_tokens)], ["Output tokens", count(metrics.output_tokens)],
    [retrieval ? "Pages selected / booklet" : "Source pages", retrieval
      ? `${selectedPages.length ? count(selectedPages.length) : "Not reported"} / ${count(processing.source_pages)}` : count(processing.source_pages)],
  ];
  const list = element("dl", "metric-list");
  for (const [label, value] of values) {
    const item = element("div", "metric");
    item.append(element("dt", "", label), element("dd", "", value));
    list.append(item);
  }
  ui["result-metrics"].replaceChildren(list);
  ui["result-processing"].replaceChildren(
    element("h3", "processing-title", retrieval ? "Selected passages assessed" : processing.strategy === "hierarchical" ? "Document reviewed in stages" : "Source reviewed in one pass"),
    element("p", "processing-detail", retrieval
      ? `${count(processing.selected_units)} of ${count(processing.source_units)} source passages selected · ${count(processing.model_calls)} model calls · ${count(processing.context_limit_tokens)} token context window`
      : `${count(processing.segments)} segments · ${count(processing.model_calls)} model calls · ${count(processing.context_limit_tokens)} token context window`),
    element("p", "processing-description", processing.coverage || "Review the cited passages against the original PDF."),
    element("p", "metrics-note", `Context-only tokens: ${count(metrics.context_tokens)} · ${count(metrics.context_characters)} source characters`),
    element("p", "metrics-note", `Served model: ${result.served_model || "Not reported"}`),
  );
  if (retrieval) {
    ui["result-processing"].append(
      element("p", "processing-detail", `Selected PDF pages: ${selectedPages.length ? selectedPages.join(", ") : "Not reported"}`),
      element("p", "processing-detail", `Local search index: ${processing.index_cache_hit === true ? "reused" : processing.index_cache_hit === false ? "built for this source" : "not reported"} · Cross-language search terms: ${processing.query_expansion === true ? "expanded" : processing.query_expansion === false ? "not expanded" : "not reported"}`),
    );
  }
  ui["result-warnings"].replaceChildren();
  for (const warning of result.warnings || []) ui["result-warnings"].append(element("p", "result-warning", warning));
  ui["technical-details"]?.removeAttribute("open");
  renderHighlights(result);
  renderChecks(result);
  if (result.checks.length) selectCheck(0);
  ui["results-title"].focus({ preventScroll: true });
  ui.results.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
}

ui["claim-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || importing || !configuration) return;
  const source = selectedDocument();
  const claim = ui.claim.value.trim();
  resetResult();
  if (!source || !ui.vote.value.trim() || !claim || !isReady()) {
    ui["form-error"].textContent = !isReady() ? "Start local Apertus and refresh its status before checking."
      : "Select a booklet, name its proposal and enter a claim.";
    ui["form-error"].hidden = false;
    return;
  }
  const payload = { document_id: source.id, vote: ui.vote.value.trim(), model: configuration.model.id,
    claim, claim_language: ui["claim-language"].value, mode: "live" };
  const controller = new AbortController();
  const configured = configuration.request_timeout_seconds;
  const seconds = Number.isFinite(configured) && configured >= 11 && configured <= 86400 ? configured : 1810;
  const timeout = setTimeout(() => controller.abort(), seconds * 1000);
  const started = Date.now();
  ui["check-elapsed"].textContent = "0s";
  const fast = configuration.document_strategy === "retrieval";
  ui["check-progress-title"].textContent = fast ? "Finding evidence and checking the claim" : "Checking the claim with Apertus";
  ui["check-progress-description"].textContent = fast
    ? "Long booklets are checked using selected passages. Keep this page open."
    : "Long documents may take several minutes. Keep this page open.";
  const timer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - started) / 1000);
    ui["check-elapsed"].textContent = elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`;
  }, 1000);
  busy = true;
  ui["claim-form"].setAttribute("aria-busy", "true");
  ui["check-progress"].hidden = false;
  ui["check-button-label"].textContent = "Checking…";
  updateControls();
  try {
    const response = await fetch("/api/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The model could not complete this check.");
    if (result.mode !== "live" || !result.served_model || !Array.isArray(result.checks)
        || !Array.isArray(result.passages) || result.claim !== claim || !Object.hasOwn(labels, result.overall)) {
      throw new Error("The server did not return a valid live model result.");
    }
    renderResult(result, source);
  } catch (error) {
    ui["form-error"].textContent = error.name === "AbortError"
      ? "The check timed out. Apertus may still be processing it; wait before retrying."
      : error instanceof TypeError ? "Could not reach the app server. Start it and try again." : error.message;
    ui["form-error"].hidden = false;
  } finally {
    clearTimeout(timeout);
    clearInterval(timer);
    busy = false;
    ui["claim-form"].setAttribute("aria-busy", "false");
    ui["check-progress"].hidden = true;
    ui["check-button-label"].textContent = "Check claim";
    updateControls();
  }
});

ui["import-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || importing || !configuration) return;
  ui["import-error"].hidden = true;
  const metadata = { language: ui["booklet-language"].value };
  if (ui["booklet-title"].value.trim()) metadata.title = ui["booklet-title"].value.trim();
  if (ui["booklet-vote"].value.trim()) metadata.vote = ui["booklet-vote"].value.trim();
  let endpoint, options;
  try {
    if (importMethod === "url") {
      let url;
      try { url = new URL(ui["booklet-url"].value.trim()); } catch { throw new Error("Enter a direct HTTPS link to an official booklet PDF."); }
      if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")
          || !["bk.admin.ch", "www.bk.admin.ch"].includes(url.hostname)) throw new Error("Use a PDF link from bk.admin.ch or www.bk.admin.ch, or upload a saved PDF.");
      url.hash = "";
      endpoint = "/api/booklets/import";
      options = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...metadata, url: url.href }) };
    } else {
      const file = ui["booklet-file"].files?.[0];
      if (!file || !file.size) throw new Error("Choose a nonempty PDF file.");
      if (file.size > 25000000) throw new Error("The PDF must be 25 MB or smaller.");
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
  ui["import-form"].setAttribute("aria-busy", "true");
  ui["import-button"].textContent = "Adding booklet…";
  ui["import-status"].textContent = "Saving the PDF and extracting its pages. Scans can take a few minutes.";
  updateControls();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 310000);
  try {
    const response = await fetch(endpoint, { ...options, signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The booklet could not be imported.");
    if (!data.document?.id) throw new Error("The import returned incomplete data. Refresh the library before retrying.");
    documents = [...documents.filter((booklet) => booklet.id !== data.document.id), data.document];
    selectedId = data.document.id;
    ui["booklet-search"].value = "";
    ui["source-language"].value = "all";
    renderLibrary();
    updateDocument();
    ui["import-status"].textContent = "Saved to your local library.";
    ui["import-panel"].open = false;
    ui["input-title"].focus({ preventScroll: true });
    ui["input-title"].scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  } catch (error) {
    ui["import-error"].textContent = error.name === "AbortError"
      ? "Import timed out. Extraction may still be running; refresh the library before retrying."
      : error instanceof TypeError ? "Could not reach the local app server." : error.message;
    ui["import-error"].hidden = false;
    ui["import-status"].textContent = "The model was not called during import.";
  } finally {
    clearTimeout(timeout);
    importing = false;
    ui["import-form"].setAttribute("aria-busy", "false");
    ui["import-button"].textContent = "Add to library";
    updateControls();
  }
});

ui["download-button"].addEventListener("click", () => {
  if (!currentResult) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(currentResult, null, 2)], { type: "application/json" }));
  const link = element("a");
  link.href = url;
  link.download = "claimlens-review.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
ui.claim.addEventListener("input", updateClaim);
ui.vote.addEventListener("input", () => { resetResult(); updateControls(); });
ui["claim-language"].addEventListener("change", resetResult);
ui["booklet-search"].addEventListener("input", renderLibrary);
ui["source-language"].addEventListener("change", renderLibrary);
ui["refresh-library"].addEventListener("click", refreshLibrary);
ui["refresh-runtime"].addEventListener("click", refreshRuntime);
ui["url-method"].addEventListener("click", () => setImportMethod("url"));
ui["upload-method"].addEventListener("click", () => setImportMethod("upload"));

async function initialize() {
  updateControls();
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    if (!response.ok || !config.model?.id || !Array.isArray(config.documents)) throw new Error("Could not load the application configuration.");
    configuration = config;
    documents = config.documents;
    ui["model-name"].textContent = config.model.label;
    renderLibrary();
    updateDocument();
    setImportMethod("url");
    await refreshRuntime();
  } catch (error) {
    configuration = null;
    ui["connection-error"].textContent = `${error instanceof TypeError ? "Could not reach the local app server." : error.message} Start it with make dev and reload this page.`;
    ui["connection-error"].hidden = false;
    ui["runtime-title"].textContent = "App unavailable";
    ui["runtime-message"].textContent = "Start the app server to load the library and check model status.";
    ui["runtime-indicator"].dataset.state = "unavailable";
    ui["library-count"].textContent = "Library unavailable";
    updateControls();
  }
}
initialize();
