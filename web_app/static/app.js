/**
 * Contract Explorer & Contract Navigator — Frontend Controller
 * Focused 2-Column Architecture:
 * - Left Sidebar: Navigable Contract Structure (Parts, Conditions & Annexes)
 * - Main Canvas: High-Fidelity Raw PDF Viewer (PDF.js) with Responsive Zoom & Search
 */

// Configure PDF.js Worker
if (window.pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
}

const state = {
  isSearching: false,
  activeView: "search",
  contracts: [],
  filteredScheme: "ALL",
};

const navState = {
  docKey: null,
  docTitle: "",
  pdfDoc: null,
  pageNum: 1,
  requestedPageNum: 1,
  totalPages: 0,
  scale: 1.2,
  isRendering: false,
  pendingPageNum: null,
  renderPromise: null,
  renderTask: null,
  renderVersion: 0,
  navigationRequestId: 0,
  hierarchy: null,
  activeConditionId: null,
  loadRequestId: 0,
  initializing: false,
};

// DOM Elements
const searchView = document.getElementById("searchView");
const contractsView = document.getElementById("contractsView");
const navigatorView = document.getElementById("navigatorView");

const tabSearch = document.getElementById("tabSearch");
const tabContracts = document.getElementById("tabContracts");
const tabNavigator = document.getElementById("tabNavigator");

const headerNavContext = document.getElementById("headerNavContext");
const navDocMetaTitle = document.getElementById("navDocMetaTitle");
const navScopedSearchInput = document.getElementById("navScopedSearchInput");
const scopedSearchSpinner = document.getElementById("scopedSearchSpinner");
const scopedSearchResultsDropdown = document.getElementById("scopedSearchResultsDropdown");

const messagesStream = document.getElementById("messagesStream");
const welcomeScreen = document.getElementById("welcomeScreen");
const queryInput = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
const contractsGrid = document.getElementById("contractsGrid");

// Navigator Elements
const navigatorSidebar = document.getElementById("navigatorSidebar");
const navigatorContractSelector = document.getElementById("navigatorContractSelector");
const sidebarTreeContainer = document.getElementById("sidebarTreeContainer");
const sidebarConditionCount = document.getElementById("sidebarConditionCount");
const hierarchyFilterInput = document.getElementById("hierarchyFilterInput");

const pdfCanvas = document.getElementById("pdfCanvas");
const pdfLoadingOverlay = document.getElementById("pdfLoadingOverlay");
const pdfLoadingText = document.getElementById("pdfLoadingText");
const pdfPageInput = document.getElementById("pdfPageInput");
const pdfTotalPages = document.getElementById("pdfTotalPages");
const pdfPrintedPageLabel = document.getElementById("pdfPrintedPageLabel");
const pdfZoomLabel = document.getElementById("pdfZoomLabel");
const navigatorInsightsBody = document.getElementById("navigatorInsightsBody");
const insightsReferenceCount = document.getElementById("insightsReferenceCount");

const crossReferenceState = {
  cache: new Map(),
  requestId: 0,
};

// Keyboard shortcut: Ctrl+K or Cmd+K to focus search input
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    if (state.activeView === "navigator") {
      if (navScopedSearchInput) {
        navScopedSearchInput.focus();
        navScopedSearchInput.select();
      }
    } else {
      if (state.activeView !== "search") {
        switchView("search");
      }
      focusMainInput();
    }
  } else if (state.activeView === "navigator") {
    if (e.key === "ArrowLeft" && !e.target.matches("input, select, textarea")) {
      e.preventDefault();
      prevPdfPage();
    } else if (e.key === "ArrowRight" && !e.target.matches("input, select, textarea")) {
      e.preventDefault();
      nextPdfPage();
    }
  }
});

// Close scoped search dropdown on outside click
document.addEventListener("click", (e) => {
  if (scopedSearchResultsDropdown && !e.target.closest(".nav-scoped-search-container")) {
    scopedSearchResultsDropdown.style.display = "none";
  }
});

function focusMainInput() {
  if (queryInput) {
    queryInput.focus();
    queryInput.select();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// VIEW SWITCHING
// ─────────────────────────────────────────────────────────────────────────────

function switchView(viewName) {
  state.activeView = viewName;

  tabSearch.classList.toggle("active", viewName === "search");
  tabContracts.classList.toggle("active", viewName === "contracts");
  tabNavigator.classList.toggle("active", viewName === "navigator");

  searchView.classList.toggle("active", viewName === "search");
  contractsView.classList.toggle("active", viewName === "contracts");
  navigatorView.classList.toggle("active", viewName === "navigator");

  if (headerNavContext) {
    headerNavContext.style.display = viewName === "navigator" ? "flex" : "none";
  }

  if (viewName === "search") {
    setTimeout(focusMainInput, 50);
  } else if (viewName === "contracts") {
    loadContracts();
  } else if (viewName === "navigator") {
    initDefaultNavigator();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTRACT LIBRARY VIEW
// ─────────────────────────────────────────────────────────────────────────────

async function loadContracts() {
  if (state.contracts && state.contracts.length > 0) {
    renderContractCards(state.contracts);
    populateNavigatorContractSelector(state.contracts);
    return;
  }

  try {
    const res = await fetch("/api/contracts");
    if (!res.ok) throw new Error("Failed to load contract library");
    const data = await res.json();
    state.contracts = data.contracts || [];
    renderContractCards(state.contracts);
    populateNavigatorContractSelector(state.contracts);
    updateSchemeFilterCounts(state.contracts);
  } catch (e) {
    if (contractsGrid) {
      contractsGrid.innerHTML = `
        <div class="loading-card" style="margin: 40px auto; color: #fca5a5; border-color: #5c1d24;">
          <span>Error loading contract corpus: ${escapeHtml(e.message)}</span>
        </div>
      `;
    }
  }
}

function updateSchemeFilterCounts(contracts) {
  const counts = { ALL: contracts.length, CFD: 0, CCUS: 0, LCHA: 0 };
  contracts.forEach(c => {
    const s = (c.scheme || "").toUpperCase();
    if (counts[s] !== undefined) counts[s]++;
  });
  const pills = document.querySelectorAll(".contracts-filter-pills .filter-pill");
  pills.forEach(pill => {
    const txt = pill.textContent.trim();
    if (txt.startsWith("All")) pill.textContent = `All (${counts.ALL})`;
    else if (txt.startsWith("CfD")) pill.textContent = `CfD · Power (${counts.CFD})`;
    else if (txt.startsWith("CCUS")) pill.textContent = `CCUS · Carbon Capture (${counts.CCUS})`;
    else if (txt.startsWith("LCHA")) pill.textContent = `LCHA · Hydrogen (${counts.LCHA})`;
  });
  const tabLabel = document.querySelector("#tabContracts span");
  if (tabLabel) tabLabel.textContent = `Contract Library (${counts.ALL})`;
}

function renderContractCards(contracts) {
  if (!contractsGrid) return;

  const filtered = state.filteredScheme === "ALL" 
    ? contracts 
    : contracts.filter(c => (c.scheme || "").toUpperCase() === state.filteredScheme.toUpperCase());

  if (filtered.length === 0) {
    contractsGrid.innerHTML = `
      <div class="loading-card" style="margin: 40px auto;">
        <span>No contracts found for selected scheme.</span>
      </div>
    `;
    return;
  }

  contractsGrid.innerHTML = filtered.map(c => `
    <div class="contract-card">
      <div class="contract-card-top">
        <div class="card-header-tags">
          <span class="card-scheme-badge">${escapeHtml(c.scheme || "Contract")}</span>
          <span class="card-round-chip">${escapeHtml(c.round || "Standard")}</span>
        </div>
        <div class="contract-card-title">${escapeHtml(c.title)}</div>
        <div class="contract-card-desc">
          ${getContractDescription(c)}
        </div>
      </div>

      <div>
        <div class="contract-metrics-row">
          <span class="metric-chip">📄 <strong>${c.total_pages || 0}</strong> pages</span>
          <span class="metric-chip">⚖️ <strong>${c.condition_count || 0}</strong> conditions</span>
        </div>

        <div class="contract-card-actions" style="margin-top: 14px;">
          <button 
            class="card-pdf-btn" 
            style="width: 100%;"
            onclick="openContractInNavigator('${c.document_key}', 1)"
            title="View contract structure"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 6h16M4 12h16M4 18h7"></path>
            </svg>
          <span>View Structure</span>
          </button>
        </div>
      </div>
    </div>
  `).join("");
}

function filterContractsByScheme(scheme, buttonEl) {
  state.filteredScheme = scheme;
  document.querySelectorAll(".filter-pill").forEach(el => el.classList.remove("active"));
  if (buttonEl) buttonEl.classList.add("active");
  renderContractCards(state.contracts);
}

function getContractDescription(c) {
  const s = (c.scheme || "").toUpperCase();
  const t = (c.title || "").toLowerCase();
  if (s === "LCHA") {
    return "Standard terms and conditions governing the UK Low Carbon Hydrogen Agreement subsidy mechanism.";
  } else if (s === "CCUS") {
    if (t.includes("dpa")) {
      return "Standard terms and conditions for Dispatchable Power Agreement carbon capture facilities.";
    }
    return "Standard terms and conditions for Industrial Carbon Capture (ICC) projects under CCUS business models.";
  } else {
    return `UK Contracts for Difference standard legal terms and conditions for low-carbon electricity generation (${c.round || "CfD"}).`;
  }
}

function populateNavigatorContractSelector(contracts) {
  if (!navigatorContractSelector) return;
  const selectedDocKey = String(navState.docKey || navigatorContractSelector.value || "");
  navigatorContractSelector.innerHTML = contracts.map(c => `
    <option value="${c.document_key}">${escapeHtml(c.title)}</option>
  `).join("");
  if (selectedDocKey && contracts.some(c => String(c.document_key) === selectedDocKey)) {
    navigatorContractSelector.value = selectedDocKey;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// GLOBAL CLAUSE SEARCH
// ─────────────────────────────────────────────────────────────────────────────

async function handleChatSubmit(event) {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query || state.isSearching) return;

  queryInput.value = "";
  await executeSearch(query);
}

async function submitSampleQuery(queryText) {
  if (state.isSearching) return;
  queryInput.value = queryText;
  await executeSearch(queryText);
}

async function executeSearch(query) {
  state.isSearching = true;
  sendBtn.disabled = true;

  if (welcomeScreen) {
    welcomeScreen.style.display = "none";
  }

  renderUserMessage(query);
  const loadingElement = renderLoadingMessage();
  scrollToBottom();

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        top_k: 5,
        use_reranker: true
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: "Network error" }));
      throw new Error(errorData.detail || "Failed to retrieve search results");
    }

    const data = await response.json();
    loadingElement.remove();
    renderBotResponse(data, query);

  } catch (err) {
    loadingElement.remove();
    renderErrorMessage(err.message);
  } finally {
    state.isSearching = false;
    sendBtn.disabled = false;
    queryInput.focus();
    scrollToBottom();
  }
}

function renderUserMessage(query) {
  const row = document.createElement("div");
  row.className = "message-row user";

  const bubble = document.createElement("div");
  bubble.className = "user-bubble";
  bubble.textContent = query;

  row.appendChild(bubble);
  messagesStream.appendChild(row);
}

function renderLoadingMessage() {
  const row = document.createElement("div");
  row.className = "message-row bot";

  const loadingCard = document.createElement("div");
  loadingCard.className = "loading-card";
  loadingCard.innerHTML = `
    <div class="spinner-gold"></div>
    <span>Searching contract clauses & ranking matches...</span>
  `;

  row.appendChild(loadingCard);
  messagesStream.appendChild(row);
  return row;
}

function renderBotResponse(data, query) {
  const row = document.createElement("div");
  row.className = "message-row bot";

  const container = document.createElement("div");
  container.className = "bot-container";

  container.appendChild(renderSearchInterpretation(data, query));

  const tableCard = document.createElement("div");
  tableCard.className = "results-table-card";

  const metaBar = document.createElement("div");
  metaBar.className = "table-meta-bar";
  metaBar.innerHTML = `
    <div class="meta-stats-group">
      <span>Matches ranked in order of relevance</span>
      ${data.detected_filter ? `<span class="detected-scope-chip">Scope: <strong>${escapeHtml(data.detected_filter.replace(/_/g, " "))}</strong></span>` : ""}
    </div>
    <div><strong>${data.results.length}</strong> Results</div>
  `;
  tableCard.appendChild(metaBar);

  const table = document.createElement("table");
  table.className = "results-table";
  table.innerHTML = `
    <thead>
      <tr>
        <th class="col-rank">Rank</th>
        <th class="col-doc">Document</th>
        <th class="col-breadcrumb">Breadcrumb</th>
        <th class="col-topic">Topic</th>
        <th class="col-pdf-action">Action</th>
      </tr>
    </thead>
    <tbody>
      ${data.results.map((r, index) => buildTableRow(r, index)).join("")}
    </tbody>
  `;

  tableCard.appendChild(table);
  container.appendChild(tableCard);
  row.appendChild(container);
  messagesStream.appendChild(row);
}

function renderSearchInterpretation(data, query) {
  const card = document.createElement("div");
  card.className = "search-interpretation-card";

  const strongestMatch = data.results && data.results[0];
  const scope = data.detected_filter
    ? data.detected_filter.replace(/_/g, " ")
    : "the contract collection";

  const interp = data.interpretation || {};
  const userIntent = interp.user_intent;
  const matchDesc = interp.match_description;

  let matchHtml = `
    <div class="search-interpretation-no-match">
      No strong match was returned. Try adding a contract name, condition number, or a more specific phrase.
    </div>
  `;

  if (strongestMatch) {
    const page = strongestMatch.page_start || strongestMatch.pdf_page_start || "—";
    const targetPdfPage = strongestMatch.pdf_page_start || strongestMatch.page_start || 1;
    const conditionTitle = strongestMatch.topic && strongestMatch.topic !== strongestMatch.breadcrumb
      ? ` — ${escapeHtml(strongestMatch.topic)}`
      : "";

    matchHtml = `
      <div class="search-interpretation-match" onclick="openContractInNavigator('${strongestMatch.document_key}', ${targetPdfPage}, '${escapeHtml(strongestMatch.breadcrumb || "")}', { openLeftCrossRef: true })" style="cursor: pointer;" title="Jump to this provision in Contract Navigator">
        <div class="search-interpretation-match-top">
          <span class="search-interpretation-match-label">Most likely match</span>
          <span class="search-interpretation-match-doc">${escapeHtml(strongestMatch.document || scope)} · contract p.${escapeHtml(page)}</span>
        </div>
        <strong class="search-interpretation-match-title">${escapeHtml(strongestMatch.breadcrumb || "Contract provision")}${conditionTitle}</strong>
        ${matchDesc ? `
          <div class="search-interpretation-term-desc">
            <span class="term-desc-tag">What this term is:</span>
            <span class="term-desc-text">${escapeHtml(matchDesc)}</span>
          </div>
        ` : ""}
      </div>
    `;
  }

  const intentHtml = userIntent
    ? `
      <div class="search-interpretation-text">
        <div class="search-interpretation-intent-badge">Understood meaning</div>
        <div class="search-interpretation-intent-body">${escapeHtml(userIntent)}</div>
      </div>
    `
    : `
      <div class="search-interpretation-text">
        I understood “<strong>${escapeHtml(query)}</strong>” as a request to find the most relevant provision in <strong>${escapeHtml(scope)}</strong>.
      </div>
    `;

  const tagLabel = interp.status === "generated"
    ? "✦ AI Interpretation"
    : "Retrieval only";

  card.innerHTML = `
    <div class="search-interpretation-header">
      <div class="search-interpretation-header-title">
        <span>Search interpretation</span>
      </div>
      <span class="search-interpretation-tag">${escapeHtml(tagLabel)}</span>
    </div>
    ${intentHtml}
    ${matchHtml}
    <div class="search-interpretation-confirmation">
      Does this look like the area you meant? The references below are ranked results from the contract database.
      <button type="button" class="search-refine-btn" onclick="focusMainInput()">Refine search</button>
    </div>
  `;
  return card;
}

function buildTableRow(result, index) {
  const partTag = result.total_parts > 1 ? `<span class="part-indicator">Part ${result.sequence_index}/${result.total_parts}</span>` : "";
  const pageLabel = (result.page_start && result.page_end) 
    ? (result.page_start === result.page_end ? `p. ${result.page_start}` : `pp. ${result.page_start}–${result.page_end}`)
    : "View PDF";

  const clauseBadge = result.clause_range ? `<span class="clause-tag">${escapeHtml(result.clause_range)}</span>` : "";

  return `
    <tr>
      <td class="col-rank">
        <span class="rank-badge">#${index + 1}</span>
      </td>
      <td class="col-doc">
        <div class="doc-block">
          <span class="scheme-tag">${escapeHtml(result.scheme || "Contract")}</span>
          <span class="doc-name-text">${escapeHtml(result.document)}</span>
        </div>
      </td>
      <td class="col-breadcrumb">
        <div class="breadcrumb-content" onclick="openContractInNavigator('${result.document_key}', ${result.pdf_page_start || result.page_start || 1}, '${escapeHtml(result.breadcrumb || "")}', { openLeftCrossRef: true })" style="cursor: pointer;" title="Open in Contract Structure with Cross References">
          <span class="breadcrumb-title">${escapeHtml(result.breadcrumb)} ${partTag}</span>
          ${clauseBadge}
        </div>
      </td>
      <td class="col-topic">
        <div class="topic-text" onclick="openContractInNavigator('${result.document_key}', ${result.pdf_page_start || result.page_start || 1}, '${escapeHtml(result.breadcrumb || "")}', { openLeftCrossRef: true })" style="cursor: pointer;" title="Open in Contract Structure with Cross References">${escapeHtml(result.topic || "Contract Clause")}</div>
        ${result.summary ? `<div class="clause-summary-text">${escapeHtml(result.summary)}</div>` : ""}
      </td>
      <td class="col-pdf-action">
        <button 
          class="pdf-jump-btn" 
          onclick="event.stopPropagation(); openContractInNavigator('${result.document_key}', ${result.pdf_page_start || result.page_start || 1}, '${escapeHtml(result.breadcrumb || "")}', { openLeftCrossRef: true })"
          title="Open in Contract Navigator at page ${result.page_start || 1}"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          <span>${pageLabel}</span>
        </button>
      </td>
    </tr>
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTRACT NAVIGATOR (2-COLUMN HIERARCHY + PDF VIEWER)
// ─────────────────────────────────────────────────────────────────────────────

async function initDefaultNavigator() {
  if (navState.docKey || navState.initializing) {
    return;
  }

  navState.initializing = true;
  try {
    if (state.contracts.length === 0) {
      await loadContracts();
    }
    const defaultDoc = state.contracts.find(c => (c.scheme || "").toUpperCase() === "LCHA") || state.contracts[0];
    if (defaultDoc) {
      await openContractInNavigator(defaultDoc.document_key, 1);
    }
  } finally {
    navState.initializing = false;
  }
}

/**
 * Main Entry Point: Opens a contract in the Navigator at the given page
 */
// ─────────────────────────────────────────────────────────────────────────────
// AR1 STRUCTURAL HIERARCHY CONTROLLER
// ─────────────────────────────────────────────────────────────────────────────

let ar1Data = null;

async function loadAr1Hierarchy() {
  const container = document.getElementById("ar1HierarchyBody");
  if (!container) return;

  if (ar1Data) {
    renderAr1Hierarchy(ar1Data);
    return;
  }

  container.innerHTML = `
    <div class="loading-card" style="margin: 40px auto;">
      <div class="spinner-gold"></div>
      <span>Loading AR1 structural hierarchy...</span>
    </div>
  `;

  try {
    const res = await fetch("/api/ar1/hierarchy");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    ar1Data = await res.json();
    
    // Update stats in header card
    const partsEl = document.getElementById("ar1TotalParts");
    const condsEl = document.getElementById("ar1TotalConditions");
    const clausesEl = document.getElementById("ar1TotalClauses");
    const schedEl = document.getElementById("ar1TotalSchedules");
    if (partsEl) partsEl.textContent = ar1Data.total_parts;
    if (condsEl) condsEl.textContent = ar1Data.total_conditions;
    if (clausesEl) clausesEl.textContent = Number(ar1Data.total_clauses).toLocaleString();
    if (schedEl) schedEl.textContent = (ar1Data.schedules_and_annexes || []).length;

    renderAr1Hierarchy(ar1Data);
  } catch (err) {
    console.error("[AR1 Hierarchy Error]", err);
    container.innerHTML = `
      <div class="loading-card" style="margin: 40px auto; color: #fca5a5; border-color: #5c1d24;">
        <span>Error loading AR1 hierarchy: ${escapeHtml(err.message)}</span>
      </div>
    `;
  }
}

function renderAr1Hierarchy(data) {
  const container = document.getElementById("ar1HierarchyBody");
  if (!container) return;

  const parts = data.parts || [];
  const partsHtml = parts.map((part, pIdx) => {
    const conds = part.conditions || [];
    const minPage = conds.length > 0 ? conds[0].page_start : "--";
    const maxPage = conds.length > 0 ? conds[conds.length - 1].page_start : "--";
    const pageSpanText = minPage === maxPage ? `p. ${minPage}` : `pp. ${minPage}–${maxPage}`;

    return `
      <div class="ar1-part-item ${pIdx === 0 ? "expanded" : ""}" id="ar1Part-${escapeHtml(part.part_number)}">
        <div class="ar1-part-header" onclick="toggleAr1Part('${escapeHtml(part.part_number)}')">
          <div class="ar1-part-left">
            <span class="ar1-part-badge">PART ${escapeHtml(part.part_number)}</span>
            <span class="ar1-part-title" title="${escapeHtml(part.title)}">${escapeHtml(part.title)}</span>
          </div>
          <div class="ar1-part-right">
            <span class="ar1-part-count">${conds.length} ${conds.length === 1 ? "condition" : "conditions"} · ${pageSpanText}</span>
            <svg class="ar1-part-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </div>
        </div>

        <div class="ar1-conditions-list">
          ${conds.map(cond => `
            <div class="ar1-cond-row" id="ar1Cond-${escapeHtml(cond.number)}" data-cond-num="${escapeHtml(cond.number)}" data-cond-title="${escapeHtml(cond.title.toLowerCase())}">
              <div class="ar1-cond-header" onclick="toggleAr1Condition('${escapeHtml(cond.number)}')">
                <div class="ar1-cond-left">
                  <span class="ar1-cond-num">Condition ${escapeHtml(cond.number)}</span>
                  <span class="ar1-cond-title" title="${escapeHtml(cond.title)}">${escapeHtml(cond.title)}</span>
                </div>
                <div class="ar1-cond-right">
                  <span class="ar1-page-badge">p. ${cond.page_start || "--"}</span>
                  <span class="ar1-item-count">${cond.item_count || 0} ${cond.item_count === 1 ? "clause" : "clauses/defs"}</span>
                  <svg class="ar1-cond-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                </div>
              </div>

              <div class="ar1-clauses-wrapper">
                ${(cond.clauses || []).map(cl => `
                  <div class="ar1-clause-item">
                    <div class="ar1-clause-left">
                      <span class="ar1-clause-tag">${escapeHtml(cl.number ? `Clause ${cl.number}` : cl.kind)}</span>
                      <span class="ar1-clause-text">${escapeHtml(cl.title)}</span>
                    </div>
                    <span class="ar1-page-badge" style="background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.1); color: var(--text-muted); font-size: 0.68rem;">p. ${cl.page || cond.page_start || "--"}</span>
                  </div>
                `).join("")}
              </div>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }).join("");

  // Schedules & Annexes section
  const schedules = data.schedules_and_annexes || [];
  const schedulesHtml = schedules.length > 0 ? `
    <div class="ar1-schedules-card">
      <div class="ar1-schedules-header">
        <span>Schedules & Annexes (${schedules.length})</span>
        <span style="font-size: 0.76rem; color: var(--text-muted); font-family: var(--font-mono);">pp. 235 – 517</span>
      </div>
      <div class="ar1-schedules-body">
        ${schedules.map(sch => `
          <div class="ar1-schedule-row">
            <span class="ar1-schedule-title">${escapeHtml(sch.title)}</span>
            <span class="ar1-page-badge">p. ${sch.page || "--"}</span>
          </div>
        `).join("")}
      </div>
    </div>
  ` : "";

  container.innerHTML = partsHtml + schedulesHtml;
  updateAr1VisibleCount();
}

function toggleAr1Part(partNumber) {
  const el = document.getElementById(`ar1Part-${partNumber}`);
  if (el) el.classList.toggle("expanded");
}

function toggleAr1Condition(condNumber) {
  const el = document.getElementById(`ar1Cond-${condNumber}`);
  if (el) el.classList.toggle("expanded");
}

function expandAllParts() {
  document.querySelectorAll(".ar1-part-item").forEach(el => el.classList.add("expanded"));
  document.querySelectorAll(".ar1-cond-row").forEach(el => el.classList.add("expanded"));
}

function collapseAllParts() {
  document.querySelectorAll(".ar1-part-item").forEach(el => el.classList.remove("expanded"));
  document.querySelectorAll(".ar1-cond-row").forEach(el => el.classList.remove("expanded"));
}

function handleAr1Filter(query) {
  const q = (query || "").trim().toLowerCase();
  const clearBtn = document.getElementById("ar1FilterClearBtn");
  if (clearBtn) clearBtn.style.display = q ? "block" : "none";

  const partItems = document.querySelectorAll(".ar1-part-item");
  let totalVisibleConds = 0;

  partItems.forEach(partEl => {
    let partMatches = false;
    const condRows = partEl.querySelectorAll(".ar1-cond-row");

    condRows.forEach(condRow => {
      const num = condRow.getAttribute("data-cond-num") || "";
      const title = condRow.getAttribute("data-cond-title") || "";
      const text = condRow.textContent.toLowerCase();
      const match = !q || num.includes(q) || title.includes(q) || text.includes(q);

      condRow.style.display = match ? "block" : "none";
      if (match) {
        partMatches = true;
        totalVisibleConds++;
      }
    });

    if (q) {
      partEl.style.display = partMatches ? "block" : "none";
      if (partMatches) partEl.classList.add("expanded");
    } else {
      partEl.style.display = "block";
    }
  });

  const countEl = document.getElementById("ar1VisibleCount");
  if (countEl) {
    if (q) {
      countEl.textContent = `Showing ${totalVisibleConds} matching conditions`;
    } else {
      countEl.textContent = `Showing 18 parts · 88 conditions`;
    }
  }
}

function clearAr1Filter() {
  const input = document.getElementById("ar1FilterInput");
  if (input) {
    input.value = "";
    handleAr1Filter("");
  }
}

function updateAr1VisibleCount() {
  const countEl = document.getElementById("ar1VisibleCount");
  if (countEl && ar1Data) {
    countEl.textContent = `Showing ${ar1Data.total_parts} parts · ${ar1Data.total_conditions} conditions`;
  }
}

function toggleNavigatorSidebar() {
  if (navigatorSidebar) {
    navigatorSidebar.classList.toggle("collapsed");
  }
}

function findConditionInHierarchy(hierarchy, pageNum, identifier = "") {
  if (!hierarchy || !hierarchy.parts) return null;

  if (identifier) {
    const clean = String(identifier).trim().toLowerCase();
    const match = clean.match(/\bcondition\s+(\d+[a-z]?)\b/i) || clean.match(/\b(\d+[a-z]?)\b/);
    const condNum = match ? match[1].toLowerCase() : null;

    for (const part of hierarchy.parts) {
      for (const cond of part.conditions || []) {
        if (cond.id && String(cond.id).toLowerCase() === clean) return cond;
        if (condNum && cond.number && String(cond.number).trim().toLowerCase() === condNum) return cond;
        if (cond.title && clean.includes(cond.title.toLowerCase())) return cond;
      }
    }
  }

  return findConditionForPage(pageNum);
}

async function openContractInNavigator(docKey, pageNumber = 1, nodeId = "") {
  if (state.contracts.length === 0) {
    await loadContracts();
  }

  state.activeView = "navigator";
  tabSearch.classList.remove("active");
  tabContracts.classList.remove("active");
  tabNavigator.classList.add("active");
  searchView.classList.remove("active");
  contractsView.classList.remove("active");
  navigatorView.classList.add("active");
  if (navigatorSidebar) navigatorSidebar.classList.remove("collapsed");
  if (headerNavContext) headerNavContext.style.display = "flex";

  const requestId = ++navState.loadRequestId;
  navState.navigationRequestId++;
  await resetPdfRenderState();
  resetCrossReferencePanel();
  navState.docKey = String(docKey);
  navState.pageNum = Number(pageNumber) || 1;
  navState.requestedPageNum = navState.pageNum;

  if (navigatorContractSelector) {
    navigatorContractSelector.value = String(docKey);
  }
  if (sidebarTreeContainer) {
    sidebarTreeContainer.innerHTML = '<div class="loading-tree">Loading contract structure...</div>';
  }
  showPdfLoading(true, "Loading contract PDF...");

  try {
    const response = await fetch(`/api/contracts/${encodeURIComponent(docKey)}/hierarchy`);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Hierarchy request failed (${response.status})`);
    }

    const hierarchy = await response.json();
    if (requestId !== navState.loadRequestId) return;

    navState.hierarchy = hierarchy;
    if (navDocMetaTitle) {
      navDocMetaTitle.textContent = `${navState.hierarchy.title || "Contract"} · ${navState.hierarchy.page_count || "—"} pages`;
    }
    renderNavigatorHierarchy(navState.hierarchy);

    // Resolve matching condition from page or identifier
    const matchedCond = findConditionInHierarchy(navState.hierarchy, navState.pageNum, nodeId);
    if (matchedCond) {
      navState.activeConditionId = matchedCond.id;
      highlightTreeCondition(matchedCond.id, { scroll: true });
      updatePrintedPageIndicator(navState.pageNum, matchedCond.id);
      showConditionInsights(matchedCond.id);
    }

    await loadPdfDocument(docKey, navState.pageNum, requestId);
  } catch (error) {
    if (requestId !== navState.loadRequestId) return;
    console.error("[Navigator Error]", error);
    if (sidebarTreeContainer) {
      sidebarTreeContainer.innerHTML = `<div class="loading-tree" style="color: #fca5a5;">${escapeHtml(error.message)}</div>`;
    }
    showPdfLoading(true, `Unable to open contract: ${error.message}`);
  }
}

/**
 * Load PDF.js Document
 */
async function loadPdfDocument(docKey, initialPage = 1, requestId = navState.loadRequestId) {
  showPdfLoading(true, "Rendering PDF pages...");

  try {
    const pdfUrl = `/api/pdf/${encodeURIComponent(docKey)}?request=${requestId}`;
    const loadingTask = pdfjsLib.getDocument({
      url: pdfUrl,
      cMapUrl: "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/cmaps/",
      cMapPacked: true,
    });

    const pdfDoc = await loadingTask.promise;
    if (requestId !== navState.loadRequestId) {
      await pdfDoc.destroy();
      return;
    }

    navState.pdfDoc = pdfDoc;
    navState.totalPages = navState.pdfDoc.numPages;
    navState.pageNum = Math.max(1, Math.min(Number(initialPage) || 1, navState.totalPages));
    navState.requestedPageNum = navState.pageNum;

    if (pdfTotalPages) {
      pdfTotalPages.textContent = navState.totalPages;
    }
    updatePdfPageInputWidth();
    if (pdfPrintedPageLabel) pdfPrintedPageLabel.textContent = "contract p.—";

    fitPdfPage(false);
    await renderPdfPage(navState.pageNum);
    if (requestId === navState.loadRequestId) {
      showPdfLoading(false);
    }

  } catch (e) {
    if (requestId !== navState.loadRequestId) return;
    console.error("[PDF.js Error]", e);
    showPdfLoading(true, `Failed to render PDF: ${e.message}`);
  }
}

/**
 * Render specific PDF page on Canvas with High-DPI support
 */
async function renderPdfPage(num) {
  if (!navState.pdfDoc) return;
  num = Math.max(1, Math.min(num, navState.totalPages || 9999));
  navState.requestedPageNum = num;
  navState.pendingPageNum = num;

  if (navState.renderPromise) return navState.renderPromise;

  const pdfDoc = navState.pdfDoc;
  const renderVersion = navState.renderVersion;
  const renderJob = { promise: null };
  navState.isRendering = true;
  renderJob.promise = (async () => {
    try {
      while (
        navState.pendingPageNum !== null &&
        renderVersion === navState.renderVersion &&
        pdfDoc === navState.pdfDoc
      ) {
        const targetPage = navState.pendingPageNum;
        navState.pendingPageNum = null;

        const page = await pdfDoc.getPage(targetPage);
        const dpr = window.devicePixelRatio || 1;
        const viewport = page.getViewport({ scale: navState.scale * dpr });

        pdfCanvas.height = viewport.height;
        pdfCanvas.width = viewport.width;
        pdfCanvas.style.width = `${viewport.width / dpr}px`;
        pdfCanvas.style.height = `${viewport.height / dpr}px`;

        navState.renderTask = page.render({
          canvasContext: pdfCanvas.getContext("2d"),
          viewport,
        });
        await navState.renderTask.promise;

        if (renderVersion !== navState.renderVersion || pdfDoc !== navState.pdfDoc) {
          return;
        }

        navState.pageNum = targetPage;
        if (pdfPageInput) pdfPageInput.value = targetPage;
      }
    } catch (err) {
      if (err?.name !== "RenderingCancelledException") {
        console.error("[Page Render Error]", err);
      }
    } finally {
      navState.renderTask = null;
      if (navState.renderPromise === renderJob.promise) {
        navState.isRendering = false;
        navState.renderPromise = null;
      }
    }
  })();

  navState.renderPromise = renderJob.promise;
  return renderJob.promise;
}

async function resetPdfRenderState() {
  const previousRender = navState.renderPromise;
  navState.renderVersion++;
  navState.pendingPageNum = null;

  if (navState.renderTask) {
    try {
      navState.renderTask.cancel();
    } catch (err) {
      console.debug("[PDF render cancel]", err);
    }
  }

  if (previousRender) {
    try {
      await previousRender;
    } catch (err) {
      console.debug("[PDF render cleanup]", err);
    }
  }

  const previousPdf = navState.pdfDoc;
  navState.pdfDoc = null;
  navState.renderPromise = null;
  navState.renderTask = null;
  navState.isRendering = false;

  if (previousPdf) {
    try {
      await previousPdf.destroy();
    } catch (err) {
      console.debug("[PDF document cleanup]", err);
    }
  }
}

function prevPdfPage() {
  const currentPage = navState.requestedPageNum || navState.pageNum;
  if (currentPage <= 1) return;
  goToPdfPage(currentPage - 1);
}

function nextPdfPage() {
  if (!navState.pdfDoc) return;
  const currentPage = navState.requestedPageNum || navState.pageNum;
  if (currentPage >= navState.totalPages) return;
  goToPdfPage(currentPage + 1);
}

async function goToPdfPage(num, selection = { mode: "page" }) {
  num = Math.max(1, Math.min(num, navState.totalPages || 9999));
  navState.requestedPageNum = num;
  const requestId = ++navState.navigationRequestId;
  await renderPdfPage(num);
  if (requestId !== navState.navigationRequestId) return;

  if (selection.mode === "part" && selection.partId) {
    updatePrintedPageIndicator(num, null);
    highlightTreePart(selection.partId, { scroll: false });
  } else if (selection.mode === "condition" && selection.nodeUid) {
    updatePrintedPageIndicator(num, selection.nodeUid);
    highlightTreeCondition(selection.nodeUid, { scroll: false });
  } else {
    selectConditionForPage(num, { scroll: true });
  }
}

function handlePageInputChange(event) {
  const rawValue = String(event.target.value || "").trim();
  const val = Number(rawValue);
  if (!Number.isInteger(val) || val < 1 || !navState.pdfDoc) {
    event.target.value = navState.pageNum || 1;
    return;
  }

  const targetPage = Math.max(1, Math.min(val, navState.totalPages));
  event.target.value = targetPage;
  goToPdfPage(targetPage);
}

function handlePageInputKeydown(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    handlePageInputChange(event);
    event.target.blur();
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.target.value = navState.pageNum || 1;
    event.target.blur();
  }
}

function zoomPdf(delta) {
  navState.scale = Math.max(0.6, Math.min(2.5, navState.scale + delta));
  if (pdfZoomLabel) {
    pdfZoomLabel.textContent = `${Math.round(navState.scale * 100)}%`;
  }
  renderPdfPage(navState.pageNum);
}

function fitPdfPage(render = true) {
  const viewportWidth = document.getElementById("pdfViewport")?.clientWidth || 900;
  const desiredScale = Math.max(0.8, Math.min(2.0, (viewportWidth - 80) / 600));
  navState.scale = desiredScale;
  if (pdfZoomLabel) {
    pdfZoomLabel.textContent = `${Math.round(navState.scale * 100)}%`;
  }
  if (render) renderPdfPage(navState.requestedPageNum || navState.pageNum);
}

function showPdfLoading(show, text = "Loading...") {
  if (pdfLoadingOverlay) {
    pdfLoadingOverlay.style.display = show ? "flex" : "none";
  }
  if (pdfLoadingText) {
    pdfLoadingText.textContent = text;
  }
}

function updatePdfPageInputWidth() {
  if (!pdfPageInput) return;
  const digits = String(Math.max(1, navState.totalPages || 1)).length;
  const width = Math.max(60, digits * 12 + 24);
  pdfPageInput.style.width = `${width}px`;
}

function handleNavigatorContractSwitch() {
  if (!navigatorContractSelector) return;
  const docKey = navigatorContractSelector.value;
  if (docKey) {
    openContractInNavigator(docKey, 1);
  }
}

function resetCrossReferencePanel() {
  crossReferenceState.requestId++;
  if (insightsReferenceCount) insightsReferenceCount.textContent = "—";

  if (navigatorInsightsBody) {
    navigatorInsightsBody.innerHTML = `
      <div class="insights-empty">
        <span class="insights-empty-icon">↗</span>
        <span>Select a condition to view resolved cross references.</span>
      </div>
    `;
  }
}

async function getCrossReferenceData(docKey) {
  const cacheKey = String(docKey);
  if (crossReferenceState.cache.has(cacheKey)) {
    return crossReferenceState.cache.get(cacheKey);
  }

  const response = await fetch(`/api/contracts/${encodeURIComponent(docKey)}/enricher`);
  if (!response.ok) {
    throw new Error(`Cross-reference request failed (${response.status})`);
  }
  const data = await response.json();
  crossReferenceState.cache.set(cacheKey, data);
  return data;
}

async function showConditionInsights(nodeUid) {
  if (!navigatorInsightsBody || !navState.docKey || !nodeUid) return;

  const requestId = ++crossReferenceState.requestId;
  navigatorInsightsBody.innerHTML = `
    <div class="insights-loading">
      <div class="spinner-gold-sm"></div>
      <span>Loading cross references...</span>
    </div>
  `;

  try {
    const data = await getCrossReferenceData(navState.docKey);
    if (requestId !== crossReferenceState.requestId) return;

    const condition = Object.values(data.conditions || {}).find(
      item => item.node_uid === nodeUid,
    );
    if (!condition) {
      renderConditionInsights(null);
      return;
    }
    renderConditionInsights(condition);
  } catch (error) {
    if (requestId !== crossReferenceState.requestId) return;
    navigatorInsightsBody.innerHTML = `
      <div class="insights-error">${escapeHtml(error.message)}</div>
    `;
    if (insightsReferenceCount) insightsReferenceCount.textContent = "—";
  }
}

function renderConditionInsights(condition) {
  if (!navigatorInsightsBody) return;
  if (!condition) {
    navigatorInsightsBody.innerHTML = `
      <div class="insights-empty">
        <span class="insights-empty-icon">↗</span>
        <span>No cross-reference data is available for this condition.</span>
      </div>
    `;
    if (insightsReferenceCount) insightsReferenceCount.textContent = "0";
    return;
  }

  const impact = condition.impact || [];
  const referencedBy = condition.referenced_by || [];
  const totalLinks = impact.length + referencedBy.length;
  if (insightsReferenceCount) insightsReferenceCount.textContent = String(totalLinks);

  const renderLink = (item, direction) => {
    const nodeUid = direction === "outbound" ? item.target_node_uid : item.source_node_uid;
    const page = item.navigation_pdf_page || item.pdf_page_start;
    return `
      <button
        type="button"
        class="cross-reference-item"
        data-node-uid="${escapeHtml(nodeUid || "")}"
        data-pdf-page="${Number(page) || 1}"
      >
        <span class="cross-reference-item-main">
          <span class="cross-reference-item-title">${escapeHtml(item.title || "Condition")}</span>
          <span class="cross-reference-item-subtitle">${escapeHtml(item.subtitle || "")}</span>
        </span>
        <span class="cross-reference-item-meta">
          <span class="cross-reference-count">${escapeHtml(item.count_badge || "")}</span>
          <span class="cross-reference-arrow">→</span>
        </span>
      </button>
    `;
  };

  const section = (title, items, direction, emptyText) => `
    <section class="cross-reference-section">
      <div class="cross-reference-section-header">
        <span>${title}</span>
        <span>${items.length}</span>
      </div>
      ${items.length ? items.map(item => renderLink(item, direction)).join("") : `<div class="cross-reference-empty">${emptyText}</div>`}
    </section>
  `;

  navigatorInsightsBody.innerHTML = `
    <div class="insights-condition-header">
      <div class="insights-condition-title">${escapeHtml(condition.header_title || `C${condition.condition_number}`)}</div>
      <div class="insights-condition-subtitle">${escapeHtml(condition.header_subtitle || "")}</div>
    </div>
    ${section("This condition references", impact, "outbound", "No outbound references.")}
    ${section("Referenced by", referencedBy, "inbound", "No resolved inbound links.")}
  `;
}

if (navigatorInsightsBody) {
  navigatorInsightsBody.addEventListener("click", event => {
    const link = event.target.closest(".cross-reference-item");
    if (!link || !navigatorInsightsBody.contains(link)) return;
    handleConditionClick(
      link.dataset.nodeUid,
      Number(link.dataset.pdfPage) || 1,
    );
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// HIERARCHY TREE SIDEBAR & QUICK FILTER
// ─────────────────────────────────────────────────────────────────────────────

function renderNavigatorHierarchy(hierarchy) {
  if (!sidebarTreeContainer) return;
  if (sidebarConditionCount) {
    sidebarConditionCount.textContent = `${hierarchy.total_conditions || 0} sections`;
  }

  const parts = hierarchy.parts || [];
  if (parts.length === 0) {
    sidebarTreeContainer.innerHTML = `
      <div class="loading-tree">
        <span>No structure available for this contract.</span>
      </div>
    `;
    return;
  }

  sidebarTreeContainer.innerHTML = parts.map((part, pIdx) => `
      <div class="tree-part-item ${pIdx === 0 ? "expanded" : ""}" id="partGroup-${escapeHtml(part.id)}">
      <button
        type="button"
        class="tree-part-header"
        data-part-id="${escapeHtml(part.id)}"
        data-pdf-page="${part.pdf_page_start || 1}"
        aria-expanded="${pIdx === 0 ? "true" : "false"}"
        aria-controls="partConditions-${escapeHtml(part.id)}"
      >
        <span class="tree-part-title-row">
          <span class="tree-part-dot" style="background: ${part.color || "#f59e0b"};"></span>
          <span class="tree-part-label" title="${escapeHtml(part.title)}">${escapeHtml(part.title)}</span>
        </span>
        <svg class="tree-chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
      </button>

      <div class="tree-conditions-list" id="partConditions-${escapeHtml(part.id)}">
        ${(part.conditions || []).map(cond => `
          <button
            type="button"
            class="tree-condition-item" 
            id="treeCond-${escapeHtml(cond.id)}" 
            data-condition-id="${escapeHtml(cond.id)}"
            data-pdf-page="${cond.pdf_page_start || 1}"
            data-cond-num="${escapeHtml(cond.number || "")}" 
            data-title="${escapeHtml((cond.title || '').toLowerCase())}"
          >
            <span class="tree-condition-left">
              <span class="tree-condition-num">${escapeHtml(cond.number || "")}</span>
              <span class="tree-condition-title" title="${escapeHtml(cond.title)}">${escapeHtml(cond.title)}</span>
            </span>
            <span class="tree-page-badge">p${cond.page_start || 1}</span>
          </button>
        `).join("")}
      </div>
    </div>
  `).join("");
}

if (sidebarTreeContainer) {
  sidebarTreeContainer.addEventListener("click", (event) => {
    const conditionEl = event.target.closest(".tree-condition-item");
    if (conditionEl && sidebarTreeContainer.contains(conditionEl)) {
      handleConditionClick(
        conditionEl.dataset.conditionId,
        Number(conditionEl.dataset.pdfPage) || 1,
      );
      return;
    }

    const partHeader = event.target.closest(".tree-part-header");
    if (partHeader && sidebarTreeContainer.contains(partHeader)) {
      handlePartClick(
        partHeader.dataset.partId,
        Number(partHeader.dataset.pdfPage) || 1,
      );
    }
  });
}

function setPartExpanded(partEl, expanded) {
  if (!partEl) return;
  partEl.classList.toggle("expanded", expanded);
  const header = partEl.querySelector(".tree-part-header");
  if (header) header.setAttribute("aria-expanded", String(expanded));
}

function togglePartAccordion(partId) {
  const partEl = document.getElementById(`partGroup-${partId}`);
  if (!partEl) return false;
  const expanded = !partEl.classList.contains("expanded");
  setPartExpanded(partEl, expanded);
  return expanded;
}

function handlePartClick(partId, pageStart) {
  togglePartAccordion(partId);
  highlightTreePart(partId);
  goToPdfPage(pageStart || 1, { mode: "part", partId });
}

function handleConditionClick(nodeUid, pageStart) {
  navState.activeConditionId = nodeUid || null;
  highlightTreeCondition(nodeUid);
  showConditionInsights(nodeUid);
  goToPdfPage(pageStart || 1, { mode: "condition", nodeUid });
}

function highlightTreeCondition(nodeUid, { scroll = true } = {}) {
  document.querySelectorAll(".tree-condition-item, .tree-part-item").forEach(el => el.classList.remove("active"));
  const condEl = document.getElementById(`treeCond-${nodeUid}`);
  if (condEl) {
    condEl.classList.add("active");
    const parentPart = condEl.closest(".tree-part-item");
    if (parentPart) setPartExpanded(parentPart, true);
    // Smooth scroll inside sidebar tree
    if (scroll) condEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function highlightTreePart(nodeUid, { scroll = true } = {}) {
  document.querySelectorAll(".tree-condition-item, .tree-part-item").forEach(el => el.classList.remove("active"));
  const partEl = document.getElementById(`partGroup-${nodeUid}`);
  if (partEl) {
    partEl.classList.add("active");
    if (scroll) partEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function findConditionForPage(pageNum) {
  if (!navState.hierarchy || !navState.hierarchy.parts) return;

  let matchedCond = null;
  for (const part of navState.hierarchy.parts) {
    for (const cond of part.conditions || []) {
      if (pageNum >= cond.pdf_page_start && pageNum <= cond.pdf_page_end) {
        matchedCond = cond;
        break;
      }
    }
    if (matchedCond) break;
  }

  if (!matchedCond) {
    let closestDiff = 99999;
    for (const part of navState.hierarchy.parts) {
      for (const cond of part.conditions || []) {
        if (cond.pdf_page_start <= pageNum && (pageNum - cond.pdf_page_start) < closestDiff) {
          closestDiff = pageNum - cond.pdf_page_start;
          matchedCond = cond;
        }
      }
    }
  }

  return matchedCond;
}

function updatePrintedPageIndicator(pdfPageNum, nodeUid = null) {
  if (!pdfPrintedPageLabel) return;

  let matchedCond = null;
  if (nodeUid && navState.hierarchy?.parts) {
    for (const part of navState.hierarchy.parts) {
      matchedCond = (part.conditions || []).find(cond => cond.id === nodeUid) || matchedCond;
    }
  }
  matchedCond = matchedCond || findConditionForPage(pdfPageNum);

  if (!matchedCond) {
    pdfPrintedPageLabel.textContent = "contract p.—";
    return;
  }

  const pageDelta = Math.max(0, pdfPageNum - matchedCond.pdf_page_start);
  const printedPage = Math.max(1, matchedCond.page_start + pageDelta);
  pdfPrintedPageLabel.textContent = `contract p.${printedPage}`;
}

function selectConditionForPage(pageNum, { scroll = true } = {}) {
  const matchedCond = findConditionForPage(pageNum);
  updatePrintedPageIndicator(pageNum, matchedCond?.id || null);
  if (matchedCond) {
    highlightTreeCondition(matchedCond.id, { scroll });
    showConditionInsights(matchedCond.id);
  }
}

/**
 * Quick Filter Tree items in sidebar
 */
function filterHierarchyTree(query) {
  const q = (query || "").trim().toLowerCase();
  const partItems = document.querySelectorAll(".tree-part-item");

  partItems.forEach(partEl => {
    let hasVisibleChild = false;
    const condItems = partEl.querySelectorAll(".tree-condition-item");

    condItems.forEach(condEl => {
      const num = condEl.getAttribute("data-cond-num") || "";
      const title = condEl.getAttribute("data-title") || "";
      const matches = !q || num.includes(q) || title.includes(q);

      condEl.style.display = matches ? "flex" : "none";
      if (matches) hasVisibleChild = true;
    });

    if (q) {
      partEl.style.display = hasVisibleChild ? "block" : "none";
      if (hasVisibleChild) partEl.classList.add("expanded");
    } else {
      partEl.style.display = "block";
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTRACT-SCOPED HYBRID SEARCH
// ─────────────────────────────────────────────────────────────────────────────

let scopedSearchTimeout = null;

function handleScopedSearchInput(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    const query = navScopedSearchInput.value.trim();
    if (query) {
      executeScopedSearch(query);
    }
    return;
  }

  clearTimeout(scopedSearchTimeout);
  scopedSearchTimeout = setTimeout(() => {
    const query = navScopedSearchInput.value.trim();
    if (query.length >= 2) {
      executeScopedSearch(query);
    } else if (scopedSearchResultsDropdown) {
      scopedSearchResultsDropdown.style.display = "none";
    }
  }, 350);
}

async function executeScopedSearch(query) {
  if (!navState.docKey) return;

  if (scopedSearchSpinner) scopedSearchSpinner.style.display = "block";
  if (scopedSearchResultsDropdown) {
    scopedSearchResultsDropdown.style.display = "block";
    scopedSearchResultsDropdown.innerHTML = `
      <div style="padding: 12px 14px; font-size: 0.76rem; color: var(--text-muted); display: flex; align-items: center; gap: 8px;">
        <div class="spinner-gold-sm"></div>
        <span>Searching this contract with Isaacus cross-encoder...</span>
      </div>
    `;
  }

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        document_key: navState.docKey,
        top_k: 5,
        use_reranker: true
      }),
    });

    if (!response.ok) throw new Error("Search failed");
    const data = await response.json();

    if (data.results.length === 0) {
      scopedSearchResultsDropdown.innerHTML = `
        <div style="padding: 12px 14px; font-size: 0.76rem; color: var(--text-muted);">
          No matching clauses found in this contract.
        </div>
      `;
      return;
    }

    scopedSearchResultsDropdown.innerHTML = data.results.map((r, idx) => `
      <div 
        class="scoped-result-row" 
        onclick="handleScopedResultSelect(${r.pdf_page_start || r.page_start || 1})"
      >
        <div class="scoped-row-header">
          <span class="scoped-rank-tag">#${idx + 1}</span>
          <span class="scoped-page-tag">p.${r.page_start || 1}</span>
        </div>
        <div class="scoped-row-title">${escapeHtml(r.breadcrumb || r.topic)}</div>
        ${r.summary ? `<div class="scoped-row-summary">${escapeHtml(r.summary)}</div>` : ""}
      </div>
    `).join("");

  } catch (err) {
    scopedSearchResultsDropdown.innerHTML = `
      <div style="padding: 12px 14px; font-size: 0.76rem; color: #fca5a5;">
        Error: ${escapeHtml(err.message)}
      </div>
    `;
  } finally {
    if (scopedSearchSpinner) scopedSearchSpinner.style.display = "none";
  }
}

function handleScopedResultSelect(pageStart) {
  if (scopedSearchResultsDropdown) {
    scopedSearchResultsDropdown.style.display = "none";
  }
  goToPdfPage(pageStart);
}

// ─────────────────────────────────────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────────────────────────────────────

function renderErrorMessage(errorText) {
  const row = document.createElement("div");
  row.className = "message-row bot";
  row.innerHTML = `
    <div class="bot-container">
      <div class="bot-speech-bubble" style="background: #2a1215; border-color: #5c1d24; color: #fca5a5;">
        Error retrieving results: ${escapeHtml(errorText)}
      </div>
    </div>
  `;
  messagesStream.appendChild(row);
}

function scrollToBottom() {
  if (messagesStream) {
    messagesStream.scrollTop = messagesStream.scrollHeight;
  }
}

function escapeHtml(text) {
  if (!text) return "";
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return String(text).replace(/[&<>"']/g, (m) => map[m]);
}

// Global PDF event listener
window.addEventListener("open-pdf-viewer", (e) => {
  const { documentKey, page } = e.detail || {};
  if (documentKey) {
    openContractInNavigator(documentKey, page || 1);
  }
});
