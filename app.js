const titles = {
  overview: "Overview",
  samples: "Sample explorer",
  workbench: "Geochemical workbench",
  ree: "REE laboratory",
  basalts: "Basalt observatory",
  quality: "Data quality",
};
const root = document.querySelector("#view-root");
const state = {
  view: "overview",
  facets: null,
  species: null,
  samples: [],
  samplePage: 1,
  selectedAnalyses: new Set(
    JSON.parse(sessionStorage.getItem("selectedAnalyses") || "[]"),
  ),
  lastSampleQuery: {},
  lastObservations: [],
};
const api = async (path) => {
  const r = await fetch(`/api/v1/${path}`);
  const j = await r.json();
  if (!r.ok) throw Error(j.error?.message || `API ${r.status}`);
  return j;
};
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmt = (v) => Number(v || 0).toLocaleString();
function btn(label, attrs = "", cl = "secondary-button") {
  return `<button class="${cl}" ${attrs}>${label}</button>`;
}
function shellEmpty(title, body) {
  return `<div class="surface empty-panel"><div><h3>${esc(title)}</h3><p>${esc(body)}</p></div></div>`;
}
function chartPanel(
  title,
  canvasId,
  footer = "SOURCE ANALYSES REMAIN INDIVIDUAL · NO VISUAL DOWNSAMPLING",
) {
  return `<div class="surface"><div class="surface-head"><div class="surface-title">${title}</div><div class="surface-meta" id="${canvasId}-meta">LOADING</div></div><div class="scientific-chart" id="${canvasId}" role="img" aria-label="${title}"></div><div class="chart-footer">${footer}</div></div>`;
}
function overview() {
  return `<div class="hero"><div class="hero-copy"><div class="eyebrow">LUNAR MATERIALS · GEOCHEMISTRY</div><h1>Read the Moon<br>through its chemistry.</h1><p>A research workbench for exploring lunar compositions, analytical context, and the measurements behind each interpretation.</p></div><div class="hero-aside">DATA RELEASE<strong>2025.02 · v1.0</strong><span>ASTROMAT SYNTHESIS</span></div></div>
<div class="section-heading"><div><h2>Dataset at a glance</h2><p>Astromat lunar sample compilation · February 2025</p></div><button class="text-link" data-method>View provenance ↗</button></div>
<div class="metric-grid"><div class="metric"><div class="metric-label">Source sample labels</div><div class="metric-value" id="ov-samples">—</div><div class="metric-note">Conservative exact-label identity</div></div><div class="metric"><div class="metric-label">Analytical records</div><div class="metric-value" id="ov-analyses">—</div><div class="metric-note">Each source row remains distinct</div></div><div class="metric"><div class="metric-label">Measurements</div><div class="metric-value" id="ov-measurements">—</div><div class="metric-note">Reported values with source units</div></div><div class="metric"><div class="metric-label">Chemical variables</div><div class="metric-value" id="ov-species">—</div><div class="metric-note">Across units and measurement types</div></div></div>
<div class="overview-grid"><div>${chartPanel("Reported silica vs titania", "overview-chart", "ASTROMAT OBSERVATIONS · SAME SOURCE ANALYSIS · UP TO 5,000 RECORDS")}<p class="chart-context">This unfiltered view pairs reported SiO₂ and TiO₂ values from the same analysis; analyzed material varies. It shows up to the first 5,000 matching analyses without aggregation. Use the workbench to filter or inspect records.</p></div><div class="surface"><div class="surface-head"><div class="surface-title">Source coverage</div><div class="surface-meta">DATA RELEASE</div></div><div class="coverage"><div class="coverage-row"><span class="coverage-label">Major oxides</span><span class="coverage-status">AVAILABLE</span></div><div class="coverage-row"><span class="coverage-label">Trace elements</span><span class="coverage-status">AVAILABLE</span></div><div class="coverage-row"><span class="coverage-label">Rare-earth elements</span><span class="coverage-status">AVAILABLE</span></div><div class="coverage-row"><span class="coverage-label">Isotope measurements</span><span class="coverage-status">AVAILABLE</span></div><div class="coverage-row"><span class="coverage-label">Methods & publications</span><span class="coverage-status">AVAILABLE</span></div><div class="notice"><b>Coverage is not completeness.</b> Availability varies by species, sample, analyzed material, and publication. The source does not provide mission as a row-level field.</div></div></div></div>
<div class="lower-grid"><div class="surface source-card"><div class="eyebrow">PRIMARY DATASET · CC-BY-4.0</div><div class="surface-title">Astromat Synthesis Compilation: Lunar samples v.1</div><p>Curated lunar geochemical measurements. The local release is checksum-verified and its original archive is retained.</p><div class="doi">DOI 10.60520/IEDA/113696 · RELEASE 2025-02</div><p><a href="https://ecl.earthchem.org/view.php?id=3696" target="_blank" rel="noreferrer">Official release record ↗</a></p></div><div class="surface quick-card"><div class="eyebrow">ANALYTICAL SPACES</div><div class="surface-title">Continue with a research workspace</div><p>Charts query source measurements and preserve their analysis and publication context.</p><div class="quick-actions"><button class="action-chip" data-go="workbench">Geochemical workbench</button><button class="action-chip" data-go="ree">REE laboratory</button><button class="action-chip" data-go="basalts">Basalt observatory</button></div></div></div>`;
}
function samplesPage() {
  return `<h1 class="page-title">Sample explorer</h1><p class="page-intro">Browse exact source labels and follow each physical sample identifier through its analyses and individual measurements.</p><div class="toolbar"><input class="search" id="sample-search" value="${esc(state.lastSampleQuery.q || "")}" placeholder="Search source sample label" aria-label="Search sample identifier"><select class="select" id="sample-subtype"><option value="">All source classifications</option></select><select class="select" id="sample-material"><option value="">All analyzed materials</option></select><button class="secondary-button" id="sample-search-btn">Search</button></div><div class="surface"><div class="surface-head"><div class="surface-title">Lunar sample records</div><div class="surface-meta" id="sample-total">LOADING</div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Source identifier</th><th>Classification</th><th>Analyses</th><th>Measurements</th><th>Publications</th><th></th></tr></thead><tbody id="sample-rows"></tbody></table></div><div class="table-pagination" id="sample-pagination"></div></div>`;
}
function sampleDetailPage(id) {
  return `<div class="section-heading"><button class="text-link" data-go="samples">← Back to samples</button></div><div id="sample-detail">Loading sample record…</div>`;
}
function controlsSpecies(selectId) {
  return `<select id="${selectId}" class="select species-select"><option>Loading source species…</option></select>`;
}
function workbenchPage() {
  return `<h1 class="page-title">Geochemical workbench</h1><p class="page-intro">Plot two measurements only when they occur in the same source analysis. Values, units, material, publication, and sample labels remain attached to every point.</p><div class="workspace"><div class="surface control-panel"><h3 class="surface-title">Chart configuration</h3><label>X axis · source variable</label>${controlsSpecies("wb-x")}<label>Y axis · source variable</label>${controlsSpecies("wb-y")}<label>Classification filter</label><select class="select" id="wb-subtype"><option value="">All source classifications</option></select><label>Analyzed material</label><select class="select" id="wb-material"><option value="">All materials</option></select><label>Observation limit</label><select class="select" id="wb-limit"><option value="5000">5,000</option><option value="10000">10,000</option><option value="20000">20,000</option></select><div class="control-actions"><button class="primary-button" id="wb-plot">Plot observations</button><span>Scatter · linear axes</span></div></div><div class="surface">${chartPanel("Paired analytical observations", "workbench-chart")}<div class="chart-footer">Click a point to inspect its source sample and analysis.</div></div><div class="surface inspector"><h3>Measurement inspector</h3><p id="wb-inspector">Choose a point to inspect its analytical record.</p><div class="small-stat">Selected analyses <span id="wb-selected">0</span></div><div class="selected-list" id="wb-selected-list"></div></div></div><div class="section-heading"><div><h2>Source records</h2><p>The chart returns paired measurements from individual source analysis rows.</p></div></div><div class="surface"><div class="table-wrap"><table class="data-table"><thead><tr><th>Sample</th><th>Classification</th><th>Material</th><th>X value</th><th>Y value</th><th>Publication</th></tr></thead><tbody id="wb-table"></tbody></table></div></div>`;
}
function reePage() {
  return `<h1 class="page-title">REE laboratory</h1><p class="page-intro">Compare raw rare-earth element abundances from selected source analyses. Missing elements remain gaps. The source compilation does not include a vetted normalization reference, so this view shows raw abundances only.</p><div class="toolbar"><input id="ree-search" class="search" placeholder="Find a source sample label"><button id="ree-search-btn" class="secondary-button">Find samples</button><span class="release-chip"><i></i> RAW ABUNDANCE · ppm</span></div><div class="surface"><div class="table-wrap"><table class="data-table"><thead><tr><th>Sample</th><th>Classification</th><th>Analyses</th><th></th></tr></thead><tbody id="ree-samples"></tbody></table></div></div><div class="section-heading"><div><h2>Selected source analyses</h2><p>Select up to 20 analyses; patterns never combine different source rows.</p></div><button class="primary-button" id="ree-plot">Plot raw REE patterns</button></div><div class="workspace" style="grid-template-columns:minmax(0,1fr) 240px"><div>${chartPanel("Raw REE abundance patterns", "ree-chart", "LA → LU · LOGARITHMIC ABUNDANCE AXIS · MISSING ELEMENTS LEFT OPEN")}</div><div class="surface inspector"><h3>Normalization</h3><div class="small-stat">Mode <span>Raw ppm</span></div><p>The source compilation does not include a vetted chondrite reference. Normalized patterns are unavailable until a versioned, cited reference is selected.</p><div class="notice">No interpolation. A gap indicates the source analysis did not report that element.</div></div></div>`;
}
function basaltsPage() {
  return `<h1 class="page-title">Basalt observatory</h1><p class="page-intro">Compare whole-rock analyses whose source subtype is explicitly listed as ilmenite, olivine, or pigeonite basalt. The documented Ti tiers are applied to eligible source rows, with analysis and distinct-label counts shown separately.</p><div class="toolbar"><select class="select" id="basalt-scheme"><option value="published">Neal & Taylor (1992) published tiers</option><option value="exploratory">Exploratory basalt subtype cohort</option></select><select class="select" id="basalt-subtype"><option value="">All eligible source subtypes</option></select><button class="primary-button" id="basalt-load">Load cohort</button><span class="release-chip"><i></i> WHOLE ROCK ONLY</span></div><div class="metric-grid"><div class="metric"><div class="metric-label">Eligible analyses</div><div class="metric-value" id="basalt-analyses">—</div><div class="metric-note">Individual analysis rows</div></div><div class="metric"><div class="metric-label">Distinct source labels</div><div class="metric-value" id="basalt-samples">—</div><div class="metric-note">Exact source label identifiers</div></div><div class="metric"><div class="metric-label">TiO₂ records</div><div class="metric-value" id="basalt-tio2">—</div><div class="metric-note">With reported TiO₂ wt%</div></div><div class="metric"><div class="metric-label">Classification</div><div class="metric-value empty">Conditional</div><div class="metric-note">Only when source TiO₂ exists</div></div></div><div class="overview-grid" style="grid-template-columns:1fr 1fr;margin-top:14px">${chartPanel("TiO₂ vs FeO total · wt%", "basalt-feo")}${chartPanel("TiO₂ vs MgO · wt%", "basalt-mgo")}</div><div class="section-heading"><div><h2>Analysis-level cohort</h2><p id="basalt-note">Source analyses remain separate. No significance tests or geological interpretations are inferred.</p></div></div><div class="surface"><div class="table-wrap"><table class="data-table"><thead><tr><th>Sample</th><th>Source subtype</th><th>TiO₂</th><th>Tier</th><th>FeOT / FeO</th><th>MgO</th><th>Publication</th></tr></thead><tbody id="basalt-rows"></tbody></table></div></div>`;
}
function qualityPage() {
  return `<h1 class="page-title">Data quality observatory</h1><p class="page-intro">Review source coverage, unit reporting, method availability, and flagged records. Flags are investigative; they do not automatically remove measurements.</p><div class="metric-grid"><div class="metric"><div class="metric-label">Measurements</div><div class="metric-value" id="dq-measurements">—</div><div class="metric-note">Numeric observations parsed</div></div><div class="metric"><div class="metric-label">Measured zeros</div><div class="metric-value" id="dq-zeros">—</div><div class="metric-note">Retained separately from missing</div></div><div class="metric"><div class="metric-label">Source issues</div><div class="metric-value" id="dq-flags">—</div><div class="metric-note">Data-quality flags</div></div><div class="metric"><div class="metric-label">License</div><div class="metric-value">CC-BY 4.0</div><div class="metric-note">Cite DOI 10.60520/IEDA/113696</div></div></div><div class="overview-grid" style="margin-top:14px"><div class="surface"><div class="surface-head"><div class="surface-title">Measurement unit coverage</div><div class="surface-meta">REPORTED UNITS</div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Unit</th><th>Species</th><th>Measurements</th></tr></thead><tbody id="dq-units"></tbody></table></div></div><div class="surface"><div class="surface-head"><div class="surface-title">Source validation notes</div></div><div class="coverage" id="dq-warnings"></div></div></div><div class="section-heading"><div><h2>Flagged source records</h2><p>Negative concentration values are retained for review; duplicate source rows remain distinct.</p></div></div><div class="surface"><div class="table-wrap"><table class="data-table"><thead><tr><th>Flag</th><th>Severity</th><th>Count</th></tr></thead><tbody id="dq-flags-table"></tbody></table></div></div>`;
}
function titleBlock(view, intro) {
  return `<h1 class="page-title">${titles[view]}</h1><p class="page-intro">${intro}</p>`;
}
function render(view = state.view) {
  state.view = view;
  document.querySelector("#crumb-current").textContent =
    titles[view] || (view === "sampleDetail" ? "Sample detail" : view);
  document
    .querySelectorAll(".nav-item")
    .forEach((el) =>
      el.classList.toggle(
        "active",
        el.dataset.view === view ||
          (view === "sampleDetail" && el.dataset.view === "samples"),
      ),
    );
  history.replaceState(
    null,
    "",
    view === "sampleDetail"
      ? `#samples/${encodeURIComponent(state.currentSample || "")}`
      : `#${view}`,
  );
  root.innerHTML =
    view === "overview"
      ? overview()
      : view === "samples"
        ? samplesPage()
        : view === "sampleDetail"
          ? sampleDetailPage(state.currentSample)
          : view === "workbench"
            ? workbenchPage()
            : view === "ree"
              ? reePage()
              : view === "basalts"
                ? basaltsPage()
                : view === "quality"
                  ? qualityPage()
                  : `${titleBlock(view, "This analytical view is not enabled in the current release.")}${shellEmpty("Workspace not implemented yet", "The implemented workspaces provide source-linked analyses, sample records, raw REE patterns, and data quality.")}`;
  hydrate(view).catch((error) => {
    console.error(error);
    const target = document.querySelector("#view-root");
    if (target)
      target.insertAdjacentHTML(
        "afterbegin",
        `<div class="notice" role="alert">${esc(error.message || "Unable to load this view. Check that the local dataset is processed.")}</div>`,
      );
  });
}
async function getFacets() {
  if (!state.facets) state.facets = await api("facets");
  return state.facets;
}
async function getSpecies() {
  if (!state.species) state.species = (await api("species")).rows;
  return state.species;
}
async function fillOptions(id, values, placeholder) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML =
    `<option value="">${placeholder}</option>` +
    values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
}
async function fillSpecies(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const rows = await getSpecies();
  el.innerHTML = rows
    .map(
      (x) =>
        `<option value="${esc(x.species_id)}">${esc(x.variable)} · ${esc(x.unit || "unit not specified")} (${fmt(x.measurement_count)})</option>`,
    )
    .join("");
  if (id === "wb-x") {
    const preferred = rows.findIndex((x) => x.variable === "SiO2 (wt%)");
    el.selectedIndex = preferred >= 0 ? preferred : 0;
  } else if (id === "wb-y") {
    const preferred = rows.findIndex((x) => x.variable === "TiO2 (wt%)");
    el.selectedIndex =
      preferred >= 0 ? preferred : Math.min(1, rows.length - 1);
  }
}
async function hydrate(view) {
  if (view === "overview") return loadOverview();
  if (view === "samples") return loadSampleExplorer();
  if (view === "sampleDetail") return loadSampleDetail();
  if (view === "workbench") return loadWorkbench();
  if (view === "ree") return loadRee();
  if (view === "basalts") return loadBasalts();
  if (view === "quality") return loadQuality();
}
async function loadOverview() {
  const d = await api("overview");
  if (!d.dataset_loaded) {
    document
      .querySelectorAll("#view-root .metric-value")
      .forEach((e) => (e.textContent = "—"));
    return;
  }
  for (const [key, id] of Object.entries({
    samples: "ov-samples",
    analyses: "ov-analyses",
    measurements: "ov-measurements",
    species: "ov-species",
  }))
    document.getElementById(id).textContent = fmt(d.counts[key]);
  const species = await getSpecies();
  const x = species.find((s) => s.variable === "SiO2 (wt%)"),
    y = species.find((s) => s.variable === "TiO2 (wt%)");
  if (x && y) {
    const obs = await api(
      `query/observations?x=${encodeURIComponent(x.species_id)}&y=${encodeURIComponent(y.species_id)}&limit=5000`,
    );
    drawScatter("overview-chart", obs.rows, {
      xLabel: "SiO₂ (wt%)",
      yLabel: "TiO₂ (wt%)",
    });
    document.getElementById("overview-chart-meta").textContent =
      `${fmt(obs.rows.length)} PAIRED SOURCE ANALYSES`;
  }
}
async function loadSampleExplorer() {
  const f = await getFacets();
  await fillOptions("sample-subtype", f.subtypes, "All source classifications");
  await fillOptions("sample-material", f.materials, "All analyzed materials");
  document.getElementById("sample-subtype").value =
    state.lastSampleQuery.subtype || "";
  document.getElementById("sample-material").value =
    state.lastSampleQuery.material || "";
  document.getElementById("sample-search-btn").onclick = () => {
    state.samplePage = 1;
    querySamples();
  };
  document.getElementById("sample-search").onkeydown = (e) => {
    if (e.key === "Enter") {
      state.samplePage = 1;
      querySamples();
    }
  };
  document.getElementById("sample-subtype").onchange = () => {
    state.samplePage = 1;
    querySamples();
  };
  document.getElementById("sample-material").onchange = () => {
    state.samplePage = 1;
    querySamples();
  };
  document.getElementById("sample-pagination").onclick = (e) => {
    const page = e.target.closest("[data-page]");
    if (page) {
      state.samplePage = Number(page.dataset.page);
      querySamples();
    }
  };
  document.getElementById("sample-rows").onclick = (e) => {
    const b = e.target.closest("[data-sample]");
    if (b) {
      state.currentSample = b.dataset.sample;
      render("sampleDetail");
    }
  };
  await querySamples();
}
async function querySamples() {
  const q = document.getElementById("sample-search")?.value || "",
    subtype = document.getElementById("sample-subtype")?.value || "",
    material = document.getElementById("sample-material")?.value || "";
  state.lastSampleQuery = { q, subtype, material };
  const data = await api(
    `samples?page=${state.samplePage}&page_size=25&q=${encodeURIComponent(q)}&subtype=${encodeURIComponent(subtype)}&material=${encodeURIComponent(material)}`,
  );
  document.getElementById("sample-total").textContent =
    `${fmt(data.total)} SOURCE LABELS`;
  document.getElementById("sample-rows").innerHTML =
    data.rows
      .map(
        (s) =>
          `<tr><td><strong>${esc(s.original_sample_id)}</strong><small>${esc(s.sample_id)}</small></td><td>${esc(s.material_class || "Unclassified")}</td><td>${fmt(s.analysis_count)}</td><td>${fmt(s.measurement_count)}</td><td>${fmt(s.publication_count)}</td><td><button class="text-link" data-sample="${esc(s.sample_id)}">Inspect →</button></td></tr>`,
      )
      .join("") || `<tr><td colspan="6">No matching source labels.</td></tr>`;
  document.getElementById("sample-pagination").innerHTML =
    `<span>Page ${data.page} of ${Math.max(1, data.pages)}</span><div>${btn("Previous", 'data-page="' + Math.max(1, data.page - 1) + '"')}${btn("Next", 'data-page="' + Math.min(data.pages || 1, data.page + 1) + '"')}</div>`;
}
function renderSelected() {
  const el = document.getElementById("wb-selected");
  if (el) el.textContent = String(state.selectedAnalyses.size);
  const list = document.getElementById("wb-selected-list");
  if (list) {
    if (state.selectedAnalyses.size === 0) {
      list.innerHTML = "<span>No analyses selected</span>";
    } else {
      list.innerHTML =
        [...state.selectedAnalyses]
          .map(
            (id) =>
              `<div class="selected-pill">${esc(id)} <button class="pill-remove" data-remove-analysis="${esc(id)}" aria-label="Remove">×</button></div>`,
          )
          .join("") +
        '<button class="text-link" id="wb-clear-selected" style="margin-top:6px;font-size:11px;display:block">Clear all</button>';
      list.onclick = (e) => {
        const rm = e.target.closest("[data-remove-analysis]");
        if (rm) {
          state.selectedAnalyses.delete(rm.dataset.removeAnalysis);
          sessionStorage.setItem(
            "selectedAnalyses",
            JSON.stringify([...state.selectedAnalyses]),
          );
          renderSelected();
          return;
        }
        if (e.target.id === "wb-clear-selected") {
          state.selectedAnalyses.clear();
          sessionStorage.setItem("selectedAnalyses", "[]");
          renderSelected();
        }
      };
    }
  }
}
async function loadRee() {
  document.getElementById("ree-search-btn").onclick = searchReeSamples;
  document.getElementById("ree-search").onkeydown = (e) => {
    if (e.key === "Enter") searchReeSamples();
  };
  document.getElementById("ree-plot").onclick = plotRee;
  await searchReeSamples();
}
async function searchReeSamples() {
  const q = document.getElementById("ree-search").value || "";
  const d = await api(`samples?page=1&page_size=12&q=${encodeURIComponent(q)}`);
  const rows = document.getElementById("ree-samples");
  rows.innerHTML = d.rows
    .map(
      (s) =>
        `<tr><td>${esc(s.original_sample_id)}</td><td>${esc(s.material_class || "Unclassified")}</td><td>${fmt(s.analysis_count)}</td><td><button class="text-link" data-ree-sample="${esc(s.sample_id)}">Choose source analyses →</button></td></tr>`,
    )
    .join("");
  rows.onclick = async (e) => {
    const back = e.target.closest("#ree-back-samples");
    if (back) {
      searchReeSamples();
      return;
    }
    const b = e.target.closest("[data-ree-sample]");
    if (!b) return;
    const d = await api(`samples/${b.dataset.reeSample}/analyses?limit=50`);
    state.reeSample = b.dataset.reeSample;
    document.getElementById("ree-samples").innerHTML =
      `<tr><th colspan="4">Select analyses from ${esc(b.closest("tr").children[0].textContent)} · each curve remains tied to a source row <button class="text-link" id="ree-back-samples" style="margin-left:12px">← Back to samples</button></th></tr>` +
      d.rows
        .map(
          (a) =>
            `<tr><td><label><input type="checkbox" data-ree-analysis="${esc(a.analysis_id)}"> ${esc(a.analysis_id)}</label></td><td>${esc(a.analyzed_material)} · ${esc(a.mineral || "bulk")}</td><td>${fmt(a.measurement_count)} measurements</td><td>${a.citation_id ? esc(a.citation_id) : "—"}</td></tr>`,
        )
        .join("");
  };
}
async function plotRee() {
  const ids = [...document.querySelectorAll("[data-ree-analysis]:checked")].map(
    (x) => x.dataset.reeAnalysis,
  );
  if (!ids.length) {
    document.getElementById("ree-chart").innerHTML =
      '<div class="chart-empty"><strong>Choose one or more source analyses</strong><p>Patterns are never constructed across separate analytical records.</p></div>';
    return;
  }
  const d = await api(`analysis/ree?analysis_ids=${ids.join(",")}`);
  drawRee(d.rows, d.order);
  document.getElementById("ree-chart-meta").textContent =
    `${ids.length} SOURCE ANALYSES · RAW ppm`;
}
async function loadBasalts() {
  const f = await getFacets();
  const basaltTypes = f.subtypes.filter((x) =>
    ["ILMENITE BASALT", "OLIVINE BASALT", "PIGEONITE BASALT"].includes(x),
  );
  await fillOptions(
    "basalt-subtype",
    basaltTypes,
    "All eligible source subtypes",
  );
  document.getElementById("basalt-load").onclick = queryBasalts;
  await queryBasalts();
}
async function queryBasalts() {
  const group = document.getElementById("basalt-scheme").value,
    subtype = document.getElementById("basalt-subtype").value,
    d = await api(
      `analysis/basalts?group=${group}&subtype=${encodeURIComponent(subtype)}`,
    ),
    rows = d.observations;
  document.getElementById("basalt-analyses").textContent = fmt(
    d.analysis_count,
  );
  document.getElementById("basalt-samples").textContent = fmt(d.sample_count);
  document.getElementById("basalt-tio2").textContent = fmt(d.analysis_count);
  document.getElementById("basalt-note").textContent =
    `${d.classification_note} ${d.exclusions.missing_tio2} source analyses lack TiO₂.`;
  const xy = (x, y, fallbackY = null) =>
    rows
      .filter((r) => r[x] && (r[y] || (fallbackY && r[fallbackY])))
      .map((r) => {
        const yProp = r[y] || r[fallbackY];
        return {
          analysis_id: r.analysis_id,
          sample_id: r.sample_id,
          original_sample_id: r.original_sample_id,
          source_sample_subtype: r.source_sample_subtype,
          analyzed_material: r.analyzed_material,
          citation_id: r.citation_id,
          x_value: r[x].value,
          x_original_value: r[x].original_value,
          x_unit: r[x].unit,
          y_value: yProp.value,
          y_original_value: yProp.original_value,
          y_unit: yProp.unit,
        };
      });
  drawScatter("basalt-feo", xy("TiO2 (wt%)", "FeOT (wt%)", "FeO (wt%)"), {
    xLabel: "TiO₂ (wt%)",
    yLabel: "FeOT / FeO (wt%)",
  });
  drawScatter("basalt-mgo", xy("TiO2 (wt%)", "MgO (wt%)"), {
    xLabel: "TiO₂ (wt%)",
    yLabel: "MgO (wt%)",
  });
  document.getElementById("basalt-feo-meta").textContent =
    `${fmt(xy("TiO2 (wt%)", "FeOT (wt%)", "FeO (wt%)").length)} SOURCE ANALYSES`;
  document.getElementById("basalt-mgo-meta").textContent =
    `${fmt(xy("TiO2 (wt%)", "MgO (wt%)").length)} SOURCE ANALYSES`;
  document.getElementById("basalt-rows").innerHTML =
    rows
      .slice(0, 500)
      .map(
        (r) =>
          `<tr><td>${esc(r.original_sample_id)}</td><td>${esc(r.source_sample_subtype)}</td><td>${esc(r["TiO2 (wt%)"]?.original_value ?? "—")}</td><td>${esc(r.ti_class)}</td><td>${esc((r["FeOT (wt%)"] || r["FeO (wt%)"])?.original_value ?? "—")}</td><td>${esc(r["MgO (wt%)"]?.original_value ?? "—")}</td><td>${esc(r.citation_id || "—")}</td></tr>`,
      )
      .join("") ||
    '<tr><td colspan="7">No eligible source analyses with TiO₂ reported.</td></tr>';
  const existingBasaltFooter = document
    .getElementById("basalt-rows")
    .closest(".surface")
    .querySelector(".table-limit-footer");
  if (existingBasaltFooter) existingBasaltFooter.remove();
  if (rows.length > 500)
    document
      .getElementById("basalt-rows")
      .closest(".surface")
      .insertAdjacentHTML(
        "beforeend",
        `<div class="chart-footer table-limit-footer">First 500 rows shown; all ${fmt(rows.length)} eligible analyses included in figures.</div>`,
      );
}
async function loadWorkbench() {
  const f = await getFacets();
  await Promise.all([
    fillSpecies("wb-x"),
    fillSpecies("wb-y"),
    fillOptions("wb-subtype", f.subtypes, "All source classifications"),
    fillOptions("wb-material", f.materials, "All analyzed materials"),
  ]);
  document.getElementById("wb-plot").onclick = plotWorkbench;
  document.getElementById("workbench-chart").onclick = (e) => {
    const p = e.target.closest("[data-analysis]");
    if (p) showObservationInspector(p.dataset.analysis);
  };
  renderSelected();
  await plotWorkbench();
}
async function showObservationInspector(id) {
  const r = state.lastObservations.find((o) => o.analysis_id === id);
  if (!r) return;
  state.lastSampleId = r.sample_id;
  document.getElementById("wb-inspector").innerHTML =
    `<strong>${esc(r.original_sample_id)}</strong><br>${esc(r.source_sample_subtype || "Unclassified")} · ${esc(r.analyzed_material)}<div class="small-stat">${esc(r.x_variable)} <span>${esc(r.x_original_value)} ${esc(r.x_unit)}</span></div><div class="small-stat">${esc(r.y_variable)} <span>${esc(r.y_original_value)} ${esc(r.y_unit)}</span></div><p>${esc(r.citation_id || "Publication reference unavailable")}</p><button class="text-link" data-add-analysis="${esc(r.analysis_id)}">Add source analysis to selection</button>`;
  document.getElementById("wb-inspector").onclick = (e) => {
    const b = e.target.closest("[data-add-analysis]");
    if (b) {
      state.selectedAnalyses.add(b.dataset.addAnalysis);
      sessionStorage.setItem(
        "selectedAnalyses",
        JSON.stringify([...state.selectedAnalyses]),
      );
      renderSelected();
    }
  };
}
async function plotWorkbench() {
  const x = document.getElementById("wb-x").value,
    y = document.getElementById("wb-y").value,
    subtype = document.getElementById("wb-subtype").value,
    material = document.getElementById("wb-material").value,
    limit = document.getElementById("wb-limit").value;
  const data = await api(
    `query/observations?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}&subtype=${encodeURIComponent(subtype)}&material=${encodeURIComponent(material)}&limit=${limit}`,
  );
  const rows = (state.lastObservations = data.rows),
    xLabel =
      rows[0]?.x_variable ||
      document.querySelector("#wb-x option:checked")?.textContent ||
      "X",
    yLabel =
      rows[0]?.y_variable ||
      document.querySelector("#wb-y option:checked")?.textContent ||
      "Y";
  drawScatter("workbench-chart", rows, { xLabel, yLabel });
  document.getElementById("workbench-chart-meta").textContent =
    `${fmt(rows.length)} RAW ANALYSIS PAIRS`;
  document.getElementById("wb-table").innerHTML =
    rows
      .slice(0, 250)
      .map(
        (r) =>
          `<tr><td>${esc(r.original_sample_id)}</td><td>${esc(r.source_sample_subtype || "Unclassified")}</td><td>${esc(r.analyzed_material)}</td><td>${esc(r.x_original_value)} ${esc(r.x_unit)}</td><td>${esc(r.y_original_value)} ${esc(r.y_unit)}</td><td>${esc(r.citation_id || "—")} <button class="text-link" data-analysis="${esc(r.analysis_id)}">Inspect</button></td></tr>`,
      )
      .join("") ||
    `<tr><td colspan="6">No analyses contain both selected variables and filters.</td></tr>`;
  document.getElementById("wb-table").onclick = (e) => {
    const b = e.target.closest("[data-analysis]");
    if (b) showObservationInspector(b.dataset.analysis);
  };
  const existingWbFooter = document
    .getElementById("wb-table")
    .closest(".surface")
    .querySelector(".table-limit-footer");
  if (existingWbFooter) existingWbFooter.remove();
  if (rows.length > 250)
    document
      .getElementById("wb-table")
      .closest(".surface")
      .insertAdjacentHTML(
        "beforeend",
        `<div class="chart-footer table-limit-footer">Table shows first 250 of ${fmt(rows.length)} returned pairs. Chart includes all returned pairs; no observations were downsampled.</div>`,
      );
}
function drawScatter(id, rows, { xLabel, yLabel } = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = `<div class="chart-empty"><div class="orb">⌁</div><strong>No paired observations</strong><p>There are no source analyses with both measurements and filters.</p></div>`;
    return;
  }
  const width = Math.max(320, el.clientWidth || 640),
    height = Math.max(230, el.clientHeight || 285),
    m = { l: 58, r: 18, t: 16, b: 45 },
    values = rows.filter(
      (r) =>
        Number.isFinite(Number(r.x_value)) &&
        Number.isFinite(Number(r.y_value)),
    );
  if (!values.length) {
    el.innerHTML = "No numeric observations";
    return;
  }
  const xs = values.map((r) => Number(r.x_value)),
    ys = values.map((r) => Number(r.y_value)),
    x0 = Math.min(...xs),
    x1 = Math.max(...xs),
    y0 = Math.min(...ys),
    y1 = Math.max(...ys),
    pad = (a, b) =>
      a === b ? Math.max(Math.abs(a) * 0.08, 1) : (b - a) * 0.06,
    xmin = x0 - pad(x0, x1),
    xmax = x1 + pad(x0, x1),
    ymin = y0 - pad(y0, y1),
    ymax = y1 + pad(y0, y1),
    sx = (x) => m.l + ((x - xmin) / (xmax - xmin)) * (width - m.l - m.r),
    sy = (y) =>
      height - m.b - ((y - ymin) / (ymax - ymin)) * (height - m.t - m.b);
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(xLabel)} vs ${esc(yLabel)}" preserveAspectRatio="none">`;
  for (let i = 0; i < 5; i++) {
    const y = m.t + (i * (height - m.t - m.b)) / 4;
    svg += `<line class="gridline" x1="${m.l}" y1="${y}" x2="${width - m.r}" y2="${y}"/><text class="tick" x="${m.l - 8}" y="${y + 3}" text-anchor="end">${(ymax - ((ymax - ymin) * i) / 4).toPrecision(3)}</text>`;
    const x = m.l + (i * (width - m.l - m.r)) / 4;
    svg += `<line class="gridline" x1="${x}" y1="${m.t}" x2="${x}" y2="${height - m.b}"/><text class="tick" x="${x}" y="${height - m.b + 17}" text-anchor="middle">${(xmin + ((xmax - xmin) * i) / 4).toPrecision(3)}</text>`;
  }
  svg += `<line class="axisline" x1="${m.l}" y1="${height - m.b}" x2="${width - m.r}" y2="${height - m.b}"/><line class="axisline" x1="${m.l}" y1="${m.t}" x2="${m.l}" y2="${height - m.b}"/>`;
  for (const r of values) {
    const x = Number(r.x_value),
      y = Number(r.y_value);
    svg += `<circle class="point" tabindex="0" data-analysis="${esc(r.analysis_id)}" cx="${sx(x)}" cy="${sy(y)}" r="3.1"><title>${esc(r.original_sample_id)} · ${esc(xLabel)} ${esc(r.x_original_value)} ${esc(r.x_unit)} · ${esc(yLabel)} ${esc(r.y_original_value)} ${esc(r.y_unit)} · ${esc(r.analyzed_material)}</title></circle>`;
  }
  svg += `<text class="axis-caption" x="${(m.l + width - m.r) / 2}" y="${height - 6}" text-anchor="middle">${esc(xLabel)}</text><text class="axis-caption" transform="translate(14 ${(height + m.t - m.b) / 2}) rotate(-90)" text-anchor="middle">${esc(yLabel)}</text></svg>`;
  el.innerHTML = svg;
}
function drawRee(rows, order) {
  const el = document.getElementById("ree-chart");
  if (!rows.length) {
    el.innerHTML =
      '<div class="chart-empty"><strong>No raw ppm REE values in these analyses</strong><p>The source record may report elements in other units or omit them.</p></div>';
    return;
  }
  const width = Math.max(440, el.clientWidth || 760),
    height = Math.max(280, el.clientHeight || 360),
    m = { l: 58, r: 20, t: 20, b: 55 },
    groups = new Map();
  for (const r of rows) {
    const g = groups.get(r.analysis_id) || {
      label: `${r.original_sample_id} · ${r.analysis_id}`,
      values: new Map(),
    };
    g.values.set(
      order.indexOf(r.variable.replace(" (ppm)", "")),
      Number(r.standardized_value),
    );
    groups.set(r.analysis_id, g);
  }
  const positives = rows
      .map((r) => Number(r.standardized_value))
      .filter((v) => v > 0);
  if (!positives.length) {
    el.innerHTML =
      '<div class="chart-empty"><strong>No positive ppm REE values in these analyses</strong><p>Abundances on a log scale require positive concentrations.</p></div>';
    return;
  }
  const min = Math.min(...positives),
    max = Math.max(...positives),
    lo = Math.floor(Math.log10(min)),
    hi = Math.ceil(Math.log10(max || min * 10)),
    y = (v) =>
      height -
      m.b -
      ((Math.log10(v) - lo) / Math.max(hi - lo, 1)) * (height - m.t - m.b),
    x = (i) => m.l + (i * (width - m.l - m.r)) / (order.length - 1);
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Raw REE abundance in ppm on logarithmic axis">`;
  for (let n = lo; n <= hi; n++) {
    const yy = y(10 ** n);
    svg += `<line class="gridline" x1="${m.l}" y1="${yy}" x2="${width - m.r}" y2="${yy}"/><text class="tick" x="${m.l - 7}" y="${yy + 3}" text-anchor="end">10<tspan font-size="9" dy="-4">${n}</tspan><tspan dy="4">&#x200B;</tspan></text>`;
  }
  order.forEach(
    (el, i) =>
      (svg += `<text class="tick ree-tick" x="${x(i)}" y="${height - m.b + 19}" text-anchor="middle">${el}</text>`),
  );
  let palette = [
    "#c3dc9e",
    "#8ab6c1",
    "#d89967",
    "#b19fd8",
    "#d0bc83",
    "#84c0a1",
  ];
  let k = 0;
  for (const g of groups.values()) {
    let segment = [];
    const flush = () => {
      if (segment.length > 1)
        svg += `<polyline class="ree-line" stroke="${palette[k % palette.length]}" points="${segment.map((p) => `${p.x},${p.y}`).join(" ")}"/>`;
      segment.forEach(
        (p) =>
          (svg += `<circle cx="${p.x}" cy="${p.y}" r="3.4" fill="${palette[k % palette.length]}"><title>${esc(g.label)} · ${order[p.i]} ${p.v} ppm</title></circle>`),
      );
      segment = [];
    };
    for (let i = 0; i < order.length; i++) {
      const v = g.values.get(i);
      if (v != null && v > 0) segment.push({ i, v, x: x(i), y: y(v) });
      else flush();
    }
    flush();
    svg += `<text class="legend-label" x="${m.l + (k % 2) * 200}" y="${m.t + 14 + Math.floor(k / 2) * 15}" fill="${palette[k % palette.length]}">${esc(g.label.slice(0, 30))}</text>`;
    k++;
  }
  svg += `<text class="axis-caption" transform="translate(14 ${(height + m.t - m.b) / 2}) rotate(-90)" text-anchor="middle">Raw abundance (ppm · logarithmic)</text></svg>`;
  el.innerHTML = svg;
}
async function loadSampleDetail() {
  await renderSampleDetail();
}
async function renderSampleDetail() {
  const id = state.currentSample;
  if (!id) {
    render("samples");
    return;
  }
  const d = await api(`samples/${id}`),
    a = await api(`samples/${id}/analyses?limit=100`),
    s = d.sample;
  state.lastSampleId = id;
  document.getElementById("sample-detail").innerHTML =
    `<div class="hero specimen-hero"><div><div class="eyebrow">SOURCE SAMPLE PROFILE</div><h1>${esc(s.original_sample_id)}</h1><p>${esc(s.material_class || "No source classification supplied")} · exact source label preserved</p></div><div class="hero-aside">ANALYSES<strong>${fmt(d.counts.analysis_count)}</strong><span>${fmt(d.counts.publication_count)} PUBLICATIONS</span></div></div><div class="metric-grid" style="margin-top:14px"><div class="metric"><div class="metric-label">Distinct source analyses</div><div class="metric-value">${fmt(d.counts.analysis_count)}</div></div><div class="metric"><div class="metric-label">Measurements</div><div class="metric-value">${fmt(d.counts.measurement_count)}</div><div class="metric-note">Individual reported source values</div></div><div class="metric"><div class="metric-label">Mission</div><div class="metric-value empty">Unavailable</div><div class="metric-note">Not a field in this release</div></div><div class="metric"><div class="metric-label">Sample imagery</div><div class="metric-value empty">Unavailable</div><div class="metric-note">No verified mapping in this dataset</div></div></div><div class="section-heading"><div><h2>Source analysis history</h2><p>Each row is an individual source analysis; sample groups are never combined into one composition.</p></div></div><div class="surface"><div class="table-wrap"><table class="data-table"><thead><tr><th>Analysis ID</th><th>Material</th><th>Mineral</th><th>Measurements</th><th>Publication</th><th></th></tr></thead><tbody>${a.rows.map((r) => `<tr><td>${esc(r.analysis_id)}</td><td>${esc(r.analyzed_material)}</td><td>${esc(r.mineral || "—")}</td><td>${fmt(r.measurement_count)}</td><td>${esc(r.citation_id || "—")}</td><td><button class="text-link" data-add-analysis="${esc(r.analysis_id)}">${state.selectedAnalyses.has(r.analysis_id) ? "Added ✓" : "Add to workbench"}</button><button class="text-link" data-view-analysis="${esc(r.analysis_id)}"> Inspect values</button></td></tr>`).join("")}</tbody></table></div></div><div class="surface" style="margin-top:14px" id="sample-measurement-inspector"><div class="coverage"><h3 class="surface-title">Measurement inspector</h3><p class="chart-context">Select “Inspect values” to view reported values, methods, laboratories, uncertainty fields, material, and citation for one analysis.</p></div></div>`;
  document.getElementById("sample-detail").onclick = async (e) => {
    const add = e.target.closest("[data-add-analysis]");
    if (add) {
      const id = add.dataset.addAnalysis;
      state.selectedAnalyses.add(id);
      sessionStorage.setItem(
        "selectedAnalyses",
        JSON.stringify([...state.selectedAnalyses]),
      );
      add.textContent = "Added ✓";
      return;
    }
    const inspect = e.target.closest("[data-view-analysis]");
    if (inspect) {
      const m = await api(
        `samples/${id}/measurements?analysis_id=${inspect.dataset.viewAnalysis}&limit=1000`,
      );
      document.getElementById("sample-measurement-inspector").innerHTML =
        `<div class="surface-head"><div class="surface-title">${esc(inspect.dataset.viewAnalysis)} · source measurements</div><div class="surface-meta">${fmt(m.rows.length)} VALUES</div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Variable</th><th>Reported value</th><th>Unit</th><th>Method</th><th>Laboratory</th><th>Uncertainty fields</th></tr></thead><tbody>${m.rows.map((v) => `<tr><td>${esc(v.variable)}</td><td>${esc(v.original_value)}</td><td>${esc(v.unit || "—")}</td><td>${esc(v.method || "Not reported")}</td><td>${esc(v.laboratory || "Not reported")}</td><td>${esc(v.uncertainties_json || "{}")}</td></tr>`).join("")}</tbody></table></div>`;
    }
  };
}
async function loadQuality() {
  const d = await api("data-quality");
  document.getElementById("dq-measurements").textContent = fmt(
    d.counts.measurement_count,
  );
  document.getElementById("dq-zeros").textContent = fmt(
    d.counts.measured_zero_count,
  );
  document.getElementById("dq-flags").textContent = fmt(
    d.flags.reduce((s, x) => s + Number(x.count), 0),
  );
  document.getElementById("dq-units").innerHTML = d.units
    .map(
      (x) =>
        `<tr><td>${esc(x.unit || "No unit reported")}</td><td>${fmt(x.species_count)}</td><td>${fmt(x.measurement_count)}</td></tr>`,
    )
    .join("");
  document.getElementById("dq-warnings").innerHTML =
    d.warnings.map((x) => `<div class="notice">${esc(x)}</div>`).join("") ||
    '<div class="coverage-row">No validation warnings recorded.</div>';
  document.getElementById("dq-flags-table").innerHTML =
    d.flags
      .map(
        (x) =>
          `<tr><td>${esc(x.flag_type)}</td><td>${esc(x.severity)}</td><td>${fmt(x.count)}</td></tr>`,
      )
      .join("") || '<tr><td colspan="3">No record-level flags.</td></tr>';
}
document.querySelector("#nav").addEventListener("click", (e) => {
  const b = e.target.closest("[data-view]");
  if (b) render(b.dataset.view);
});
root.addEventListener("click", (e) => {
  const go = e.target.closest("[data-go]");
  if (go) {
    render(go.dataset.go);
    return;
  }
  if (e.target.closest("[data-method]"))
    document.querySelector("#method-dialog").showModal();
});
document
  .querySelector("#open-method")
  .addEventListener("click", () =>
    document.querySelector("#method-dialog").showModal(),
  );
document
  .querySelector("[data-close]")
  .addEventListener("click", () =>
    document.querySelector("#method-dialog").close(),
  );
document
  .querySelector("#theme-toggle")
  .addEventListener("click", () => document.body.classList.toggle("light"));
const initial = decodeURIComponent(location.hash.slice(1));
const detail = initial.match(/^samples\/(AST-LUNAR-[a-f0-9]{16})$/);
if (detail) {
  state.currentSample = detail[1];
  render("sampleDetail");
} else render(titles[initial] ? initial : "overview");

window.addEventListener("hashchange", () => {
  const current = decodeURIComponent(location.hash.slice(1));
  const d = current.match(/^samples\/(AST-LUNAR-[a-f0-9]{16})$/);
  if (d) {
    state.currentSample = d[1];
    render("sampleDetail");
  } else if (titles[current]) {
    render(current);
  } else if (!current || current === "overview") {
    render("overview");
  }
});
