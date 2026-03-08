let currentFilePath = "";
let currentAnalysisAnswer = "";
let currentChartData = null;
let currentSchemaMeta = null;

// Frontend-only graph mode switch:
// - showForceLayoutOption = false: hide FORCE option and use SOM only.
// - showForceLayoutOption = true: allow FORCE/SOM toggle in UI.
const GRAPH_LAYOUT_UI_SETTINGS = {
    showForceLayoutOption: false,
    defaultLayoutMode: "som",
};

function normalizeGraphMode(mode) {
    return String(mode || "").trim().toLowerCase() === "som" ? "som" : "force";
}

function isForceLayoutEnabled() {
    return Boolean(GRAPH_LAYOUT_UI_SETTINGS.showForceLayoutOption);
}

function getAllowedGraphMode(mode) {
    const normalized = normalizeGraphMode(mode);
    if (!isForceLayoutEnabled() && normalized === "force") {
        return "som";
    }
    return normalized;
}

let graphLayoutMode = getAllowedGraphMode(GRAPH_LAYOUT_UI_SETTINGS.defaultLayoutMode);
let graphBundle = null;
let fullGraphData = null;
let forceGraphData = null;
let somGraphData = null;
let somSelectionData = null;
let graphNodeMap = {};
let groupDefaults = {};
let forceNodeTooltipEl = null;

const layerOrder = ["bottom_layer", "middle_layer", "top_layer"];
const somLayerPriority = {
    bottom_layer: 1,
    middle_layer: 2,
    top_layer: 3,
    title_layer: 4,
    title_scheme: 4,
};
const somHexSize = 14;
const somHexWidth = Math.sqrt(3) * somHexSize;
const somHexHeight = 2 * somHexSize;
const somEmptyColor = "#f4f6f9";
const somColorPalettes = [
    { scale: d3.interpolateGreens, hex: "#27ae60" },
    { scale: d3.interpolateTeals, hex: "#16a085" },
    { scale: d3.interpolateBlues, hex: "#2980b9" },
    { scale: d3.interpolatePurples, hex: "#8e44ad" },
    { scale: d3.interpolateReds, hex: "#c0392b" },
    { scale: d3.interpolateOranges, hex: "#d35400" },
    { scale: d3.interpolateYlOrBr, hex: "#b8860b" },
    { scale: d3.interpolateCool, hex: "#00b894" },
    { scale: d3.interpolateWarm, hex: "#d63031" },
    { scale: d3.interpolateCividis, hex: "#2c3e50" },
];

// let forceStep = 0; // [FORCE-DISABLED] Force layout step counter — not used when force is off
let selectedNodes = [];
let somStep = 0;
let somPhases = [];
let somRequirements = {};
let somSelections = {};
let somCategoryColorScales = {};
let somBadgeColors = {};
let somLayerColors = {};
let somCurrentActiveDegree = {};
let somLinkLookup = {};
let somNodeByElementId = {};
let somLinkThicknessScale = null;

let selectedColorNodeId = "";
let selectedPaletteMeta = null;
let extractedPaletteResults = [];
let currentRefImagePath = "";

let galleryData = [];
let activeGalleryIndex = 0;
let galleryViewMode = "single";
let sankeyFloatingPanelCleanup = null;
let forceGraphJobId = null;
let forceGraphProgressTimer = null;
let forceGraphPollingInFlight = false;
let forceGraphLastProgress = -1;
let forceGraphPollDelayMs = 3500;
const RECOMMENDED_FORCE_SAMPLE_COUNT = 100;
const FORCE_SAMPLE_COUNT_FALLBACK_MIN = 1;
const FORCE_SAMPLE_COUNT_FALLBACK_MAX = 150;

let colorScale = null;
let graphLinkWeightCache = null;
let graphLinkWeightCacheRef = null;

const SANKEY_COLUMN_COUNT = 6;
const SANKEY_MAX_FLOW_WIDTH = 5;
const SANKEY_COLUMN_TITLES = [
    "洞察(Insight)",
    "底层(Bottom)",
    "中层(Middle)",
    "顶层(Top)",
    "配色(Palette)",
    "输出(Output)",
];
const SANKEY_COLUMN_COLORS = {
    0: "#7EA6F0",   // Insight  — soft blue
    1: "#F2B07B",   // Bottom   — soft peach/orange
    2: "#E89AC0",   // Middle   — soft pink
    3: "#8CCB90",   // Top      — soft green
    4: "#C0A2E8",   // Palette  — soft lavender
    5: "#7ECFCF",   // Output   — soft teal
};

function getColorScale() {
    if (typeof d3 === "undefined") return null;
    if (!colorScale) {
        const fallbackScheme = ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#f97316"];
        const scheme = Array.isArray(d3.schemeSet3) && d3.schemeSet3.length ? d3.schemeSet3 : fallbackScheme;
        colorScale = d3.scaleOrdinal(scheme);
    }
    return colorScale;
}

function colorForGroup(key) {
    const scale = getColorScale();
    if (scale) return scale(String(key || "unknown"));

    const fallback = ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#f97316"];
    const text = String(key || "unknown");
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) {
        hash = ((hash << 5) - hash) + text.charCodeAt(i);
        hash |= 0;
    }
    return fallback[Math.abs(hash) % fallback.length];
}

function getGraphModeLabel(mode) {
    return mode === "som" ? "SOM Graph" : "Force Graph";
}

function getForceSampleCountLimits() {
    const input = document.getElementById("forceSampleCountInput");
    const minValue = Number.parseInt(input?.min, 10);
    const maxValue = Number.parseInt(input?.max, 10);
    return {
        min: Number.isInteger(minValue) ? minValue : FORCE_SAMPLE_COUNT_FALLBACK_MIN,
        max: Number.isInteger(maxValue) ? maxValue : FORCE_SAMPLE_COUNT_FALLBACK_MAX,
    };
}

function getRequestedSampleCount() {
    const input = document.getElementById("forceSampleCountInput");
    const limits = getForceSampleCountLimits();

    if (!input) {
        return Math.max(limits.min, Math.min(limits.max, RECOMMENDED_FORCE_SAMPLE_COUNT));
    }

    const parsed = Number.parseInt(String(input.value || "").trim(), 10);
    const fallback = Math.max(limits.min, Math.min(limits.max, RECOMMENDED_FORCE_SAMPLE_COUNT));
    const normalized = Number.isInteger(parsed) ? parsed : fallback;
    const clamped = Math.max(limits.min, Math.min(limits.max, normalized));

    if (String(clamped) !== String(input.value)) {
        input.value = String(clamped);
    }
    return clamped;
}

function updateGraphActionLabels() {
    const sampleCount = getRequestedSampleCount();
    const buildBtn = document.getElementById("btnGenInfo");
    if (buildBtn) {
        buildBtn.textContent = graphLayoutMode === "som"
            ? `Build SOM Graph (${sampleCount} JSON)`
            : `Build Force Graph (${sampleCount} JSON)`;
    }

    const uploadBuildBtn = document.getElementById("btnGenInfoFromJson");
    if (uploadBuildBtn) {
        uploadBuildBtn.textContent = graphLayoutMode === "som"
            ? "Build SOM Graph From Uploaded JSON"
            : "Build Force Graph From Uploaded JSON";
    }
}

function getSomTooltipElement() {
    const container = document.getElementById("forceGraphContainer");
    if (!container) return null;
    return container.querySelector(".som-tooltip");
}

function hideSomTooltip() {
    const tooltip = getSomTooltipElement();
    if (tooltip) tooltip.style.visibility = "hidden";
}

function setGraphContainerModeClass() {
    const container = document.getElementById("forceGraphContainer");
    if (!container) return;
    container.classList.toggle("som-graph-container", graphLayoutMode === "som");
}

function renderGraphPlaceholder() {
    const container = document.getElementById("forceGraphContainer");
    if (!container) return;
    hideForceNodeTooltip();
    hideSomTooltip();
    setGraphContainerModeClass();
    const sampleCount = getRequestedSampleCount();
    if (graphLayoutMode === "som") {
        container.innerHTML = `<div class="center-msg">Click "Build SOM Graph (${sampleCount} JSON)" to start</div>`;
    } else {
        container.innerHTML = `<div class="center-msg">Click "Build Force Graph (${sampleCount} JSON)" to start</div>`;
    }
}

function updateGraphModeUI() {
    const title = document.getElementById("graphExplorerTitle");
    if (title) {
        title.textContent = graphLayoutMode === "som"
            ? "SOM-GUIDED SCHEME EXPLORER"
            : "FORCE-GUIDED SCHEME EXPLORER";
    }

    const forceEnabled = isForceLayoutEnabled();
    const toggleWrap = document.getElementById("graphLayoutToggle");
    if (toggleWrap) {
        toggleWrap.style.display = forceEnabled ? "inline-flex" : "none";
    }

    const forceBtn = document.getElementById("btnLayoutForce");
    const somBtn = document.getElementById("btnLayoutSom");
    if (forceBtn) {
        forceBtn.style.display = forceEnabled ? "inline-block" : "none";
    }
    if (somBtn) {
        somBtn.style.display = "inline-block";
    }
    if (forceBtn) forceBtn.classList.toggle("active", graphLayoutMode === "force");
    if (somBtn) somBtn.classList.toggle("active", graphLayoutMode === "som");

    const stepIndicator = document.getElementById("forceStepIndicator");
    if (stepIndicator) {
        stepIndicator.style.display = graphLayoutMode === "som" ? "none" : "flex";
    }

    const btnNext = document.getElementById("btnForceNext");
    const btnGenerate = document.getElementById("btnForceGenerate");
    if (graphLayoutMode === "som") {
        if (btnNext) btnNext.style.display = "none";
        if (btnGenerate) btnGenerate.style.display = "none";
    } else {
        if (btnGenerate) btnGenerate.style.display = "none";
        if (btnNext && !forceGraphData) btnNext.style.display = "none";
    }

    updateGraphActionLabels();
    setGraphContainerModeClass();
}

// [FORCE-DISABLED] useForceGraphAsActiveData — sets forceGraphData as the active graph data
// function useForceGraphAsActiveData() {
//     fullGraphData = forceGraphData;
//     graphLinkWeightCache = null;
//     graphLinkWeightCacheRef = null;
//     graphNodeMap = {};
//     (fullGraphData?.nodes || []).forEach((node) => {
//         graphNodeMap[node.id] = node;
//     });
// }

function normalizeSomElement(rawElement) {
    if (!rawElement || typeof rawElement !== "object") return null;
    const elementId = String(rawElement.id || "").trim();
    if (!elementId) return null;

    const layer = String(rawElement.layer || "top_layer").trim() || "top_layer";
    const groupId = String(rawElement.group_id || rawElement.category || "unknown_group").trim() || "unknown_group";
    const groupName = String(rawElement.group || rawElement.category || groupId).trim() || groupId;
    const nodeName = String(rawElement.name || rawElement.label || elementId).trim() || elementId;

    return {
        id: elementId,
        name: nodeName,
        label: nodeName,
        group: groupName,
        group_id: groupId,
        category: String(rawElement.category || groupName).trim() || groupName,
        layer,
        desc: String(rawElement.desc || "").trim(),
        val: Number(rawElement.val ?? rawElement.count ?? 1) || 1,
        count: Number(rawElement.count ?? rawElement.val ?? 1) || 1,
        option_payload: rawElement.option_payload && typeof rawElement.option_payload === "object"
            ? rawElement.option_payload
            : {},
        is_palette_node: Boolean(rawElement.is_palette_node || groupId === "color_scheme"),
    };
}

function prepareSomSelectionData() {
    const cells = (somGraphData?.nodes || []).map((cell) => ({
        x: Number(cell.x || 0),
        y: Number(cell.y || 0),
        u_value: Number(cell.u_value || 0),
        elements: Array.isArray(cell.elements) ? cell.elements : [],
    }));
    const links = Array.isArray(somGraphData?.links) ? somGraphData.links : [];

    const normalizedCells = [];
    const elementNodes = [];
    somNodeByElementId = {};
    somLinkLookup = {};
    somCategoryColorScales = {};
    somBadgeColors = {};
    somLayerColors = {};
    somCurrentActiveDegree = {};
    somRequirements = {};

    const categorySeen = new Set();
    let categoryCount = 0;
    const layerSet = new Set();
    let maxCount = 1;
    let maxLift = 1;

    cells.forEach((cell) => {
        const normalizedElements = cell.elements
            .map((elem) => normalizeSomElement(elem))
            .filter(Boolean);
        const normalizedCell = {
            x: cell.x,
            y: cell.y,
            u_value: cell.u_value,
            elements: normalizedElements,
            cx: (cell.x + (cell.y % 2 === 0 ? 0 : 0.5)) * somHexWidth,
            cy: cell.y * (somHexHeight * 0.75),
        };
        normalizedCells.push(normalizedCell);

        if (normalizedElements.length > 0) {
            const elem = normalizedElements[0];
            elementNodes.push(elem);
            somNodeByElementId[elem.id] = normalizedCell;

            layerSet.add(elem.layer);
            if (!somRequirements[elem.layer]) somRequirements[elem.layer] = new Set();
            somRequirements[elem.layer].add(elem.category);

            if (!categorySeen.has(elem.category)) {
                const cp = somColorPalettes[categoryCount % somColorPalettes.length];
                somCategoryColorScales[elem.category] = cp.scale;
                somBadgeColors[elem.category] = cp.hex;
                categorySeen.add(elem.category);
                categoryCount += 1;
            }

            maxCount = Math.max(maxCount, Number(elem.count || 1));
        }
    });

    somPhases = Array.from(layerSet).sort(
        (a, b) => (somLayerPriority[a] || 99) - (somLayerPriority[b] || 99)
    );

    somPhases.forEach((layer, idx) => {
        somLayerColors[layer] = somColorPalettes[idx % somColorPalettes.length].hex;
        somRequirements[layer] = Array.from(somRequirements[layer] || []);
    });

    links.forEach((link) => {
        const sId = String(link.source || "");
        const tId = String(link.target || "");
        if (!sId || !tId) return;
        const key = [sId, tId].sort().join("||");
        somLinkLookup[key] = {
            source: sId,
            target: tId,
            lift: Number(link.lift || 0),
            co_occur: Number(link.co_occur || 0),
        };
        maxLift = Math.max(maxLift, Number(link.lift || 0));
    });

    somLinkThicknessScale = d3
        .scaleLinear()
        .domain([0, maxLift || 1])
        .range([1.5, 4.5])
        .clamp(true);

    somSelectionData = {
        cells: normalizedCells,
        links,
        maxCount,
    };

    fullGraphData = {
        nodes: elementNodes,
        links: links.map((link) => ({
            source: link.source,
            target: link.target,
            lift: Number(link.lift || 0),
            co_occur: Number(link.co_occur || 0),
            is_intra: false,
        })),
    };
    graphLinkWeightCache = null;
    graphLinkWeightCacheRef = null;
    graphNodeMap = {};
    elementNodes.forEach((node) => {
        graphNodeMap[node.id] = node;
    });
}

function syncSelectedNodesFromSomSelections() {
    const nodes = [];
    somPhases.forEach((layer) => {
        const byCat = somSelections[layer] || {};
        Object.values(byCat).forEach((node) => {
            if (!node) return;
            nodes.push(node);
        });
    });
    selectedNodes = nodes;
}

function initializeSomSelections() {
    somSelections = {};
    somPhases.forEach((layer) => {
        somSelections[layer] = {};
    });
    somStep = 0;
    syncSelectedNodesFromSomSelections();
}

function setGraphLayoutMode(mode, opts = {}) {
    const normalizedMode = getAllowedGraphMode(mode);
    const preserveSelection = Boolean(opts.preserveSelection);
    const preservePalette = Boolean(opts.preservePalette);

    graphLayoutMode = normalizedMode;
    updateGraphModeUI();

    if (!preserveSelection) {
        selectedNodes = [];
        if (!preservePalette) {
            clearPaletteSelectionState();
        }
    }

    if (graphLayoutMode === "som") {
        hideForceNodeTooltip();
        if (somGraphData && Array.isArray(somGraphData.nodes) && somGraphData.nodes.length > 0) {
            prepareSomSelectionData();
            initializeSomSelections();
            renderSomStep();
        } else {
            fullGraphData = null;
            graphLinkWeightCache = null;
            graphLinkWeightCacheRef = null;
            graphNodeMap = {};
            renderDesignSummary();
            renderGraphPlaceholder();
        }
        return;
    }

    // [FORCE-DISABLED] Force layout branch — unreachable when showForceLayoutOption=false
    // hideSomTooltip();
    // if (forceGraphData && Array.isArray(forceGraphData.nodes) && forceGraphData.nodes.length > 0) {
    //     useForceGraphAsActiveData();
    //     initForceExplorer();
    // } else {
    //     fullGraphData = null;
    //     graphLinkWeightCache = null;
    //     graphLinkWeightCacheRef = null;
    //     graphNodeMap = {};
    //     renderDesignSummary();
    //     renderGraphPlaceholder();
    // }
}

function toggleLoading(id, show) {
    const el = document.getElementById(id);
    if (el) el.style.display = show ? "block" : "none";
}

function escapeHtml(text) {
    return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function getForceNodeTooltip() {
    if (forceNodeTooltipEl) return forceNodeTooltipEl;
    const el = document.createElement("div");
    el.className = "force-node-tooltip";
    el.style.display = "none";
    document.body.appendChild(el);
    forceNodeTooltipEl = el;
    return forceNodeTooltipEl;
}

function getLayerLabel(layerKey) {
    if (layerKey === "bottom_layer") return "Bottom Layer";
    if (layerKey === "middle_layer") return "Middle Layer";
    if (layerKey === "top_layer") return "Top Layer";
    return layerKey || "Unknown";
}

function getNodeDescription(node) {
    const directDesc = String(node?.desc || "").trim();
    if (directDesc) return directDesc;
    const payload = node?.option_payload;
    if (payload && typeof payload === "object") {
        const fallback = payload.desc || payload.description || payload.text || payload.content || payload.suggestion;
        return String(fallback || "").trim();
    }
    return "";
}

// [FORCE-DISABLED] moveForceNodeTooltip — repositions the force node hover tooltip
// function moveForceNodeTooltip(event) {
//     const tooltip = getForceNodeTooltip();
//     if (tooltip.style.display === "none") return;
//     const gap = 12;
//     const maxX = window.innerWidth - tooltip.offsetWidth - 8;
//     const maxY = window.innerHeight - tooltip.offsetHeight - 8;
//     const x = Math.max(8, Math.min(maxX, event.clientX + gap));
//     const y = Math.max(8, Math.min(maxY, event.clientY + gap));
//     tooltip.style.left = `${x}px`;
//     tooltip.style.top = `${y}px`;
// }

// [FORCE-DISABLED] showForceNodeTooltip — displays tooltip for a force graph node on hover
// function showForceNodeTooltip(event, node) {
//     const tooltip = getForceNodeTooltip();
//     const desc = getNodeDescription(node);
//     tooltip.innerHTML = `
//         <div class="tt-title">${escapeHtml(node?.name || "Node")}</div>
//         <div class="tt-row"><span>Category</span><b>${escapeHtml(node?.group || node?.group_id || "Unknown")}</b></div>
//         <div class="tt-row"><span>Layer</span><b>${escapeHtml(getLayerLabel(node?.layer))}</b></div>
//         <div class="tt-row"><span>Frequency</span><b>${escapeHtml(node?.val ?? "N/A")}</b></div>
//         <div class="tt-row"><span>Group ID</span><b>${escapeHtml(node?.group_id || "N/A")}</b></div>
//         ${desc ? `<div class="tt-desc">${escapeHtml(desc)}</div>` : ""}
//     `;
//     tooltip.style.display = "block";
//     moveForceNodeTooltip(event);
// }

function hideForceNodeTooltip() {
    const tooltip = getForceNodeTooltip();
    tooltip.style.display = "none";
}

function setForceProgress(percent, text, visible = true) {
    const panel = document.getElementById("forceProgressPanel");
    const bar = document.getElementById("forceProgressBar");
    const msg = document.getElementById("forceProgressText");
    if (!panel || !bar || !msg) return;

    panel.style.display = visible ? "block" : "none";
    const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
    bar.style.width = `${safePercent}%`;
    msg.textContent = text || `${safePercent}%`;
}

function stopForceGraphPolling() {
    if (forceGraphProgressTimer) {
        clearTimeout(forceGraphProgressTimer);
        forceGraphProgressTimer = null;
    }
    forceGraphPollingInFlight = false;
}

function scheduleForceGraphPolling(delayMs) {
    stopForceGraphPolling();
    const safeDelay = Math.max(1200, Number(delayMs) || forceGraphPollDelayMs || 3500);
    forceGraphProgressTimer = setTimeout(pollForceGraphProgressOnce, safeDelay);
}

async function pollForceGraphProgressOnce() {
    if (!forceGraphJobId || forceGraphPollingInFlight) return;
    forceGraphPollingInFlight = true;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 20000);
        const progressRes = await fetch(`/infographic/force_graph_plan/progress/${forceGraphJobId}`, {
            signal: controller.signal,
        });
        clearTimeout(timeoutId);

        const progressData = await progressRes.json();

        if (progressData.status !== "success") {
            setForceProgress(100, progressData.error || "Progress fetch failed", true);
            stopForceGraphPolling();
            toggleLoading("loading-info", false);
            document.getElementById("btnGenInfo").disabled = false;
            forceGraphJobId = null;
            return;
        }

        const pct = Number(progressData.progress || 0);
        const modeLabel = getGraphModeLabel(String(progressData.layout_mode || graphLayoutMode || "force").toLowerCase() === "som" ? "som" : "force");
        const statusText = `${modeLabel}: ${progressData.message || "Running"} | success ${progressData.success_count || 0}/${progressData.target_count || 50}, failed ${progressData.failed_count || 0}`;
        setForceProgress(pct, statusText, true);

        if (progressData.job_status === "completed") {
            stopForceGraphPolling();
            const mode = String(progressData.layout_mode || graphLayoutMode || "force").toLowerCase() === "som" ? "som" : "force";
            const ok = applyGraphBundleByMode(progressData.result || {}, mode);
            setForceProgress(100, ok ? `${getGraphModeLabel(mode)} completed.` : "Completed with empty graph.", true);
            toggleLoading("loading-info", false);
            document.getElementById("btnGenInfo").disabled = false;
            forceGraphJobId = null;
            if (ok) saveSession();
            return;
        }

        if (progressData.job_status === "failed") {
            stopForceGraphPolling();
            const mode = String(progressData.layout_mode || graphLayoutMode || "force").toLowerCase() === "som" ? "som" : "force";
            const err = progressData.error || `${getGraphModeLabel(mode)} generation failed`;
            setForceProgress(100, err, true);
            alert(err);
            toggleLoading("loading-info", false);
            document.getElementById("btnGenInfo").disabled = false;
            forceGraphJobId = null;
            return;
        }

        if (pct > forceGraphLastProgress) {
            forceGraphPollDelayMs = 2500;
        } else {
            forceGraphPollDelayMs = Math.min(9000, forceGraphPollDelayMs + 1000);
        }
        forceGraphLastProgress = pct;
    } catch (pollErr) {
        const timeoutLike =
            pollErr?.name === "AbortError" ||
            String(pollErr).toLowerCase().includes("timeout") ||
            String(pollErr).toLowerCase().includes("network");

        if (timeoutLike && forceGraphJobId) {
            forceGraphPollDelayMs = Math.min(10000, forceGraphPollDelayMs + 1500);
            setForceProgress(
                Math.max(1, forceGraphLastProgress > 0 ? forceGraphLastProgress : 1),
                `Waiting for backend response... next poll in ${Math.round(forceGraphPollDelayMs / 1000)}s`,
                true
            );
        } else {
            stopForceGraphPolling();
            setForceProgress(100, `Progress polling error: ${pollErr}`, true);
            toggleLoading("loading-info", false);
            document.getElementById("btnGenInfo").disabled = false;
            forceGraphJobId = null;
            return;
        }
    } finally {
        forceGraphPollingInFlight = false;
    }

    if (forceGraphJobId) {
        scheduleForceGraphPolling(forceGraphPollDelayMs);
    }
}

function applyGraphBundleByMode(data, modeHint = "force") {
    const mode = normalizeGraphMode(data?.layout_mode || modeHint || "force");

    graphBundle = data;
    groupDefaults = data.group_defaults || {};

    if (mode === "som") {
        somGraphData = data.graph_data || { nodes: [], links: [] };
        if (!Array.isArray(somGraphData.nodes) || somGraphData.nodes.length === 0) {
            alert("No nodes returned from SOM planning.");
            return false;
        }

        if (Number(data.success_count || 0) < Number(data.target_count || 50)) {
            alert(`Generated ${data.success_count} valid JSON plans (target ${data.target_count || 50}).`);
        }

        setGraphLayoutMode("som");
        switchTab(3);
        return true;
    }

    // [FORCE-DISABLED] Force layout branch — disabled via showForceLayoutOption=false
    // if (!isForceLayoutEnabled()) {
    //     alert("Force layout is disabled in frontend settings. Set showForceLayoutOption = true to enable it.");
    //     return false;
    // }
    // forceGraphData = data.graph_data || { nodes: [], links: [] };
    // if (!Array.isArray(forceGraphData.nodes) || forceGraphData.nodes.length === 0) {
    //     alert("No nodes returned from force-graph planning.");
    //     return false;
    // }
    // if (Number(data.success_count || 0) < Number(data.target_count || 50)) {
    //     alert(`Generated ${data.success_count} valid JSON plans (target ${data.target_count || 50}).`);
    // }
    // setGraphLayoutMode("force");
    // switchTab(3);
    // return true;
    return false;
}

// [FORCE-DISABLED] applyForceGraphBundle — applies a force-graph bundle to the UI
// function applyForceGraphBundle(data) {
//     return applyGraphBundleByMode(data, "force");
// }

function switchTab(index) {
    document.querySelectorAll(".tab-btn").forEach((b, i) => b.classList.toggle("active", i === index));
    document.querySelectorAll(".tab-content").forEach((c, i) => c.classList.toggle("active", i === index));
    if (Number(index) === 3) {
        renderDesignSummary();
    }
}
window.switchTab = switchTab;

function toHexColor(rgb) {
    if (!Array.isArray(rgb) || rgb.length < 3) return null;
    const clamp = (n) => Math.max(0, Math.min(255, Number(n) || 0));
    return "#" + [clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2])]
        .map((v) => v.toString(16).padStart(2, "0"))
        .join("")
        .toUpperCase();
}

function softenHexColor(hex, whiteMix = 0.56) {
    const rgb = rgbTripletFromHex(hex);
    if (!rgb) return String(hex || "#9CA3AF");
    const mix = Math.max(0, Math.min(0.9, Number(whiteMix) || 0));
    const eased = [
        Math.round(rgb[0] + ((255 - rgb[0]) * mix)),
        Math.round(rgb[1] + ((255 - rgb[1]) * mix)),
        Math.round(rgb[2] + ((255 - rgb[2]) * mix)),
    ];
    return toHexColor(eased) || String(hex || "#9CA3AF");
}

function renderSchema(meta) {
    currentSchemaMeta = meta || null;
    const container = document.getElementById("tab-schema");
    if (!meta || !Array.isArray(meta.columns)) {
        container.innerHTML = '<div class="center-msg">No Data</div>';
        return;
    }

    let html = `<div style="font-size:10px; color:#999; margin-bottom:15px;">${meta.rows} ROWS FOUND</div>`;
    meta.columns.forEach((col) => {
        html += `
        <div style="margin-bottom:8px; border-bottom:1px solid #eee; padding-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
            <span style="font-family:'JetBrains Mono'; font-size:11px; font-weight:600;">${col}</span>
            <span class="schema-type">STR/NUM</span>
        </div>`;
    });

    container.innerHTML = html;
}

function getNodeById(nodeId) {
    return graphNodeMap[nodeId] || null;
}

function hexPoints(size) {
    const points = [];
    for (let i = 0; i < 6; i += 1) {
        const angleRad = (Math.PI / 180) * (60 * i - 30);
        points.push(`${size * Math.cos(angleRad)},${size * Math.sin(angleRad)}`);
    }
    return points.join(" ");
}

function getSomCurrentLayer() {
    if (!somPhases.length) return null;
    const safeIndex = Math.min(somStep, somPhases.length - 1);
    return somPhases[safeIndex];
}

function getSomLinkBetween(aId, bId) {
    const key = [String(aId || ""), String(bId || "")].sort().join("||");
    return somLinkLookup[key] || null;
}

function getSomNodeColor(elements) {
    if (!Array.isArray(elements) || elements.length === 0) return somEmptyColor;
    const elem = elements[0];
    const interpolator = somCategoryColorScales[elem.category] || d3.interpolateGreys;
    const maxCount = Number(somSelectionData?.maxCount || 1);
    const count = Number(elem.count || elem.val || 1);
    const normalized = 0.3 + 0.7 * (count / maxCount);
    return interpolator(normalized);
}

function updateSomActionButtons() {
    const btnNext = document.getElementById("btnForceNext");
    const btnGenerate = document.getElementById("btnForceGenerate");
    if (btnNext) btnNext.style.display = "none";
    if (btnGenerate) btnGenerate.style.display = somStep >= somPhases.length ? "inline-block" : "none";
}

function renderSomStep() {
    updateSomActionButtons();
    renderSomGraph();
    renderDesignSummary();
}

function renderSomGraph() {
    const container = document.getElementById("forceGraphContainer");
    if (!container) return;

    container.innerHTML = "";
    if (typeof d3 === "undefined") {
        container.innerHTML = '<div class="center-msg">D3 failed to load. Upload/analysis still works.</div>';
        return;
    }

    if (!somSelectionData || !Array.isArray(somSelectionData.cells) || somSelectionData.cells.length === 0) {
        container.innerHTML = '<div class="center-msg">No SOM nodes available</div>';
        return;
    }

    const tooltip = document.createElement("div");
    tooltip.className = "som-tooltip";
    tooltip.style.visibility = "hidden";
    container.appendChild(tooltip);

    const svgRoot = d3.select(container).append("svg")
        .attr("width", "100%")
        .attr("height", "100%");

    const zoomRoot = svgRoot.append("g");
    const zoomBehavior = d3.zoom()
        .scaleExtent([0.3, 6])
        .on("zoom", (event) => {
            zoomRoot.attr("transform", event.transform);
        });
    svgRoot.call(zoomBehavior);

    const linkLayer = zoomRoot.append("g").attr("class", "links-layer").style("pointer-events", "none");
    const hexLayer = zoomRoot.append("g").attr("class", "hex-layer");
    const cells = somSelectionData.cells;

    const hexGroups = hexLayer.selectAll(".hex-group")
        .data(cells)
        .enter()
        .append("g")
        .attr("class", "hex-group")
        .attr("transform", (d) => `translate(${d.cx}, ${d.cy})`)
        .on("mouseover", (event, d) => {
            if (!Array.isArray(d.elements) || d.elements.length === 0) return;
            const elem = d.elements[0];
            const currentLayer = getSomCurrentLayer();
            const degree = somCurrentActiveDegree[elem.id] || 0;
            const isCurrent = elem.layer === currentLayer;

            tooltip.innerHTML = `
                <div style="${!isCurrent ? "opacity:0.5;" : ""}">
                    <b style="color:${somBadgeColors[elem.category] || "#2c3e50"};">[${escapeHtml(elem.category)}]</b>
                    ${escapeHtml(elem.name)}
                    <span style="font-size:11px; color:#c0392b; font-weight:bold; float:right;">频次: ${escapeHtml(elem.count)}</span>
                    ${elem.desc ? `<br><span style="font-size:11px; color:#666; display:block; margin-top:6px;">${escapeHtml(elem.desc)}</span>` : ""}
                    ${degree > 0 ? `<span style="font-size:11px; color:#2980b9; display:block; margin-top:6px; font-weight:bold;">当前跨层连线数: ${degree}</span>` : ""}
                </div>
            `;
            tooltip.style.visibility = "visible";

            const rect = container.getBoundingClientRect();
            tooltip.style.left = `${event.clientX - rect.left + 15}px`;
            tooltip.style.top = `${event.clientY - rect.top + 15}px`;

            if (degree > 0) {
                linkLayer.raise();
                linkLayer.selectAll(".active-link")
                    .transition()
                    .duration(200)
                    .attr("stroke-opacity", (linkData) => {
                        const sourceId = linkData?.source?.elements?.[0]?.id;
                        const targetId = linkData?.target?.elements?.[0]?.id;
                        if (sourceId === elem.id || targetId === elem.id) return 1;
                        return 0.05;
                    })
                    .attr("stroke-width", (linkData) => {
                        const baseWidth = somLinkThicknessScale ? somLinkThicknessScale(Number(linkData.lift || 0)) : 1.5;
                        const sourceId = linkData?.source?.elements?.[0]?.id;
                        const targetId = linkData?.target?.elements?.[0]?.id;
                        return (sourceId === elem.id || targetId === elem.id) ? (baseWidth * 1.8) : baseWidth;
                    });
            }
        })
        .on("mousemove", (event) => {
            if (tooltip.style.visibility !== "visible") return;
            const rect = container.getBoundingClientRect();
            tooltip.style.left = `${event.clientX - rect.left + 15}px`;
            tooltip.style.top = `${event.clientY - rect.top + 15}px`;
        })
        .on("mouseout", () => {
            tooltip.style.visibility = "hidden";
            hexLayer.raise();
            linkLayer.selectAll(".active-link")
                .transition()
                .duration(200)
                .attr("stroke-opacity", 0.5)
                .attr("stroke-width", (d) => (somLinkThicknessScale ? somLinkThicknessScale(Number(d.lift || 0)) : 1.5));
        })
        .on("click", (_, d) => {
            if (!Array.isArray(d.elements) || d.elements.length === 0) return;
            const elem = d.elements[0];
            const currentLayer = getSomCurrentLayer();
            if (!currentLayer || elem.layer !== currentLayer) return;

            if (!somSelections[currentLayer]) somSelections[currentLayer] = {};
            somSelections[currentLayer][elem.category] = elem;
            syncSelectedNodesFromSomSelections();

            if (elem.group_id === "color_scheme") {
                selectedColorNodeId = elem.id;
                selectedPaletteMeta = null;
                const generateBtn = document.getElementById("btnGeneratePaletteFromNode");
                if (generateBtn) generateBtn.disabled = false;
                const hint = document.getElementById("paletteNodeHint");
                if (hint) {
                    const desc = elem.desc ? ` | ${elem.desc}` : "";
                    hint.textContent = `${elem.name}${desc}`;
                }
                generatePaletteFromSelectedColorNode({ reuseImage: false });
            }

            const requiredCategories = somRequirements[currentLayer] || [];
            const selectedCategories = Object.keys(somSelections[currentLayer] || {});
            if (requiredCategories.length > 0 && requiredCategories.every((cat) => selectedCategories.includes(cat))) {
                if (somStep < somPhases.length - 1) {
                    somStep += 1;
                } else {
                    somStep = somPhases.length;
                    setTimeout(() => {
                        alert("信息图装配完成！全层级结构已就绪。");
                    }, 300);
                }
            }

            renderSomStep();
        });

    hexGroups.append("polygon")
        .attr("class", "hex")
        .attr("points", hexPoints(somHexSize))
        .attr("fill", (d) => getSomNodeColor(d.elements))
        .attr("opacity", (d) => (d.elements.length === 0 ? 0.6 : 1));

    hexGroups.append("circle")
        .attr("class", "contact-dot")
        .attr("cx", 0)
        .attr("cy", 0)
        .attr("r", 0)
        .attr("fill", "#fff")
        .attr("stroke", "#2c3e50")
        .attr("stroke-width", 1.5)
        .attr("opacity", 0)
        .style("pointer-events", "none");

    const currentLayer = getSomCurrentLayer();
    const activeLinks = [];
    somCurrentActiveDegree = {};

    if (somStep > 0 && somStep <= somPhases.length) {
        let prevSelected = [];
        for (let i = 0; i < somStep; i += 1) {
            const layer = somPhases[i];
            if (!layer) continue;
            prevSelected = prevSelected.concat(Object.values(somSelections[layer] || {}));
        }

        cells.forEach((cell) => {
            if (!Array.isArray(cell.elements) || cell.elements.length === 0) return;
            const elem = cell.elements[0];
            if (elem.layer !== currentLayer) return;

            prevSelected.forEach((sourceElem) => {
                const link = getSomLinkBetween(sourceElem.id, elem.id);
                if (!link) return;
                const sourceCell = somNodeByElementId[sourceElem.id];
                if (!sourceCell) return;

                activeLinks.push({
                    id: `${sourceElem.id}-${elem.id}`,
                    source: sourceCell,
                    target: cell,
                    lift: Number(link.lift || 0),
                    category: elem.category,
                });
                somCurrentActiveDegree[sourceElem.id] = (somCurrentActiveDegree[sourceElem.id] || 0) + 1;
                somCurrentActiveDegree[elem.id] = (somCurrentActiveDegree[elem.id] || 0) + 1;
            });
        });
    }

    const paths = linkLayer.selectAll(".active-link").data(activeLinks, (d) => d.id);
    paths.exit().remove();
    paths.enter()
        .append("path")
        .attr("class", "active-link link")
        .merge(paths)
        .attr("stroke", (d) => somBadgeColors[d.category] || "#64748b")
        .attr("stroke-width", (d) => (somLinkThicknessScale ? somLinkThicknessScale(Number(d.lift || 0)) : 1.5))
        .attr("stroke-opacity", 0.5)
        .attr(
            "d",
            (d) => `M ${d.source.cx} ${d.source.cy} Q ${(d.source.cx + d.target.cx) / 2} ${((d.source.cy + d.target.cy) / 2) - 50} ${d.target.cx} ${d.target.cy}`
        );

    hexGroups.attr("class", (d) => {
        const classes = ["hex-group"];
        if (!Array.isArray(d.elements) || d.elements.length === 0) {
            classes.push("dimmed");
            return classes.join(" ");
        }

        const elem = d.elements[0];
        const selectedInLayer = somSelections[elem.layer] || {};
        const selectedNode = selectedInLayer[elem.category];
        const isSelected = Boolean(selectedNode && selectedNode.id === elem.id);
        if (isSelected) classes.push("selected-node");

        if (elem.layer !== currentLayer && !isSelected) classes.push("dimmed");
        if ((somCurrentActiveDegree[elem.id] || 0) > 0 && !isSelected && elem.layer === currentLayer) classes.push("highlight");
        return classes.join(" ");
    });

    hexGroups.select(".contact-dot")
        .transition()
        .duration(300)
        .attr("r", (d) => {
            if (!Array.isArray(d.elements) || d.elements.length === 0) return 0;
            const elem = d.elements[0];
            if (elem.layer !== currentLayer) return 0;
            const degree = somCurrentActiveDegree[elem.id] || 0;
            return degree > 0 ? 2 + degree * 2 : 0;
        })
        .attr("opacity", (d) => {
            if (!Array.isArray(d.elements) || d.elements.length === 0) return 0;
            const elem = d.elements[0];
            if (elem.layer !== currentLayer) return 0;
            return (somCurrentActiveDegree[elem.id] || 0) > 0 ? 1 : 0;
        });

    // Auto-fit SOM cells into the current viewport instead of using a fixed transform.
    const rect = container.getBoundingClientRect();
    const viewWidth = Math.max(1, Number(rect.width) || 1);
    const viewHeight = Math.max(1, Number(rect.height) || 1);
    const fitPadding = 24;

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    cells.forEach((cell) => {
        const cx = Number(cell.cx || 0);
        const cy = Number(cell.cy || 0);
        minX = Math.min(minX, cx - somHexSize);
        maxX = Math.max(maxX, cx + somHexSize);
        minY = Math.min(minY, cy - somHexSize);
        maxY = Math.max(maxY, cy + somHexSize);
    });

    const contentWidth = Math.max(1, maxX - minX);
    const contentHeight = Math.max(1, maxY - minY);
    const availableWidth = Math.max(1, viewWidth - (fitPadding * 2));
    const availableHeight = Math.max(1, viewHeight - (fitPadding * 2));
    const rawScale = Math.min(availableWidth / contentWidth, availableHeight / contentHeight);
    const fitScale = Math.max(0.3, Math.min(6, rawScale));

    const fitTranslateX = ((viewWidth - (contentWidth * fitScale)) / 2) - (minX * fitScale);
    const fitTranslateY = ((viewHeight - (contentHeight * fitScale)) / 2) - (minY * fitScale);

    svgRoot.call(
        zoomBehavior.transform,
        d3.zoomIdentity.translate(fitTranslateX, fitTranslateY).scale(fitScale)
    );
}

function resetSomFlow() {
    if (!somGraphData) return;
    prepareSomSelectionData();
    initializeSomSelections();
    clearPaletteSelectionState();
    renderSomStep();
}

function isNodeSelected(nodeId) {
    return selectedNodes.some((n) => n.id === nodeId);
}

function clearPaletteSelectionState() {
    selectedColorNodeId = "";
    selectedPaletteMeta = null;
    extractedPaletteResults = [];
    currentRefImagePath = "";

    const hint = document.getElementById("paletteNodeHint");
    if (hint) hint.textContent = "No color scheme node selected";

    const promptPreview = document.getElementById("palettePromptPreview");
    if (promptPreview) promptPreview.value = "";

    const refPlaceholder = document.getElementById("refPlaceholder");
    if (refPlaceholder) {
        refPlaceholder.style.display = "flex";
        refPlaceholder.textContent = "No palette reference image";
    }

    const canvasContainer = document.getElementById("canvasContainer");
    if (canvasContainer) canvasContainer.style.display = "none";

    const interactionLayer = document.getElementById("interactionLayer");
    if (interactionLayer) interactionLayer.innerHTML = "";

    const generateBtn = document.getElementById("btnGeneratePaletteFromNode");
    if (generateBtn) generateBtn.disabled = true;

    renderPaletteOptions([]);
}

function removeSelectedNodeById(nodeId) {
    const index = selectedNodes.findIndex((n) => n.id === nodeId);
    if (index >= 0) {
        const removed = selectedNodes[index];
        selectedNodes.splice(index, 1);
        if (removed.group_id === "color_scheme" && selectedColorNodeId === removed.id) {
            clearPaletteSelectionState();
        }
    }
}

// [FORCE-DISABLED] toggleForceNodeSelection — handles node click selection in force graph
// function toggleForceNodeSelection(node) {
//     if (graphLayoutMode !== "force") return;
//     if (!node || layerOrder[forceStep] !== node.layer) return;
//     const existed = isNodeSelected(node.id);
//     if (existed) {
//         removeSelectedNodeById(node.id);
//         renderForceStep();
//         renderDesignSummary();
//         return;
//     }
//     const sameGroupNode = selectedNodes.find((n) => n.layer === node.layer && n.group_id === node.group_id);
//     if (sameGroupNode) {
//         removeSelectedNodeById(sameGroupNode.id);
//     }
//     selectedNodes.push(node);
//     if (node.group_id === "color_scheme") {
//         selectedColorNodeId = node.id;
//         selectedPaletteMeta = null;
//         const generateBtn = document.getElementById("btnGeneratePaletteFromNode");
//         if (generateBtn) generateBtn.disabled = false;
//         const hint = document.getElementById("paletteNodeHint");
//         if (hint) {
//             const desc = node.desc ? ` | ${node.desc}` : "";
//             hint.textContent = `${node.name}${desc}`;
//         }
//         generatePaletteFromSelectedColorNode({ reuseImage: false });
//     }
//     renderForceStep();
//     renderDesignSummary();
// }

function getSourceId(link) {
    return typeof link.source === "object" ? link.source.id : link.source;
}

function getTargetId(link) {
    return typeof link.target === "object" ? link.target.id : link.target;
}

// [FORCE-DISABLED] computeActiveGraphData — computes visible nodes/links for the current force step
// function computeActiveGraphData() {
//     if (!fullGraphData) return { nodes: [], links: [] };
//     let activeNodes = [...selectedNodes];
//     let candidateNodes = [];
//     if (forceStep < layerOrder.length) {
//         const currentLayer = layerOrder[forceStep];
//         candidateNodes = fullGraphData.nodes.filter((n) => n.layer === currentLayer);
//         if (forceStep > 0) {
//             const pastSelectedIds = new Set(
//                 selectedNodes
//                     .filter((n) => layerOrder.indexOf(n.layer) < forceStep)
//                     .map((n) => n.id)
//             );
//             const validIds = new Set();
//             fullGraphData.links.forEach((link) => {
//                 if (link.is_intra) return;
//                 const sId = getSourceId(link);
//                 const tId = getTargetId(link);
//                 if (pastSelectedIds.has(sId)) validIds.add(tId);
//                 if (pastSelectedIds.has(tId)) validIds.add(sId);
//             });
//             const filtered = candidateNodes.filter((n) => validIds.has(n.id));
//             if (filtered.length > 0) candidateNodes = filtered;
//         }
//         candidateNodes.forEach((n) => {
//             if (!activeNodes.some((s) => s.id === n.id)) activeNodes.push(n);
//         });
//     }
//     const activeNodeIds = new Set(activeNodes.map((n) => n.id));
//     const activeLinks = fullGraphData.links.filter((link) => {
//         const sId = getSourceId(link);
//         const tId = getTargetId(link);
//         if (!activeNodeIds.has(sId) || !activeNodeIds.has(tId)) return false;
//         if (link.is_intra) return true;
//         const sourceSelected = selectedNodes.some((n) => n.id === sId);
//         const targetSelected = selectedNodes.some((n) => n.id === tId);
//         return sourceSelected || targetSelected;
//     });
//     return { nodes: activeNodes, links: activeLinks };
// }

// [FORCE-DISABLED] renderForceGraph — core D3 force-simulation rendering function
// Draws nodes/links with d3.forceSimulation (charge, link, collide, x/y forces) and drag interaction.
// function renderForceGraph(nodes, links) {
//     if (graphLayoutMode !== "force") return;
//     const container = document.getElementById("forceGraphContainer");
//     if (!container) return;
//     setGraphContainerModeClass();
//     hideSomTooltip();
//     container.innerHTML = "";
//     if (typeof d3 === "undefined") {
//         container.innerHTML = '<div class="center-msg">D3 failed to load. Upload/analysis still works.</div>';
//         return;
//     }
//     if (!nodes.length) {
//         container.innerHTML = '<div class="center-msg">No nodes available for current step</div>';
//         return;
//     }
//     const rect = container.getBoundingClientRect();
//     const width = Math.max(600, Math.floor(rect.width));
//     const height = Math.max(240, Math.floor(rect.height));
//     const svg = d3.select(container).append("svg").attr("width", width).attr("height", height);
//     const root = svg.append("g");
//     svg.call(d3.zoom().on("zoom", (event) => root.attr("transform", event.transform)));
//     const linkSel = root.append("g")
//         .selectAll("line")
//         .data(links, (d) => `${getSourceId(d)}-${getTargetId(d)}`)
//         .join("line")
//         .attr("stroke", (d) => (d.is_intra ? "transparent" : "#b9c1cc"))
//         .attr("stroke-opacity", (d) => (d.is_intra ? 0 : 0.65))
//         .attr("stroke-width", (d) => (d.is_intra ? 0 : Math.max(1, Number(d.jaccard || 0) * 10)));
//     const nodeSel = root.append("g")
//         .selectAll("g")
//         .data(nodes, (d) => d.id)
//         .join((enter) => {
//             const g = enter.append("g").style("cursor", "pointer");
//             g.append("circle");
//             g.append("text");
//             return g;
//         })
//         .on("click", (event, d) => {
//             event.stopPropagation();
//             hideForceNodeTooltip();
//             toggleForceNodeSelection(d);
//         })
//         .on("mouseover", (event, d) => { showForceNodeTooltip(event, d); })
//         .on("mousemove", (event) => { moveForceNodeTooltip(event); })
//         .on("mouseout", () => { hideForceNodeTooltip(); });
//     nodeSel.select("circle")
//         .attr("r", (d) => Math.sqrt(Number(d.val || 1)) * 2.4 + 11)
//         .attr("fill", (d) => colorForGroup(d.group_id || d.group || "unknown"))
//         .attr("stroke", (d) => (isNodeSelected(d.id) ? "#ef4444" : "#ffffff"))
//         .attr("stroke-width", (d) => (isNodeSelected(d.id) ? 4 : 2.5))
//         .attr("opacity", (d) => {
//             if (forceStep >= layerOrder.length) return isNodeSelected(d.id) ? 1 : 0.75;
//             if (d.layer !== layerOrder[forceStep]) return 0.95;
//             return isNodeSelected(d.id) ? 1 : 0.68;
//         });
//     nodeSel.select("text")
//         .text((d) => d.name)
//         .attr("y", (d) => Math.sqrt(Number(d.val || 1)) * 2.4 + 24)
//         .attr("text-anchor", "middle")
//         .style("font-size", "11px")
//         .style("font-weight", 600)
//         .style("fill", "#1f2937")
//         .style("pointer-events", "none");
//     const simulation = d3.forceSimulation(nodes)
//         .force("link", d3.forceLink(links)
//             .id((d) => d.id)
//             .distance((d) => (d.is_intra ? Math.max(35, 55 - Number(d.jaccard || 0) * 35) : 190))
//             .strength((d) => (d.is_intra ? Math.max(0.1, Number(d.jaccard || 0) * 1.8) : Math.max(0.03, Number(d.jaccard || 0) * 0.7))))
//         .force("charge", d3.forceManyBody().strength(-420))
//         .force("x", d3.forceX((d) => {
//             const idx = layerOrder.indexOf(d.layer);
//             return (idx + 1) * (width / 4);
//         }).strength(0.8))
//         .force("y", d3.forceY(height / 2).strength(0.1))
//         .force("collide", d3.forceCollide().radius((d) => Math.sqrt(Number(d.val || 1)) * 2.4 + 22));
//     nodeSel.call(
//         d3.drag()
//             .on("start", (event, d) => {
//                 if (!event.active) simulation.alphaTarget(0.3).restart();
//                 d.fx = d.x; d.fy = d.y;
//             })
//             .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
//             .on("end", (event, d) => {
//                 if (!event.active) simulation.alphaTarget(0);
//                 d.fx = null; d.fy = null;
//             })
//     );
//     simulation.on("tick", () => {
//         linkSel.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
//                .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
//         nodeSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
//     });
// }

// [FORCE-DISABLED] updateForceStepUI — updates step chips and Next/Generate buttons for force flow
// function updateForceStepUI() {
//     if (graphLayoutMode !== "force") return;
//     const chips = document.querySelectorAll(".force-step-chip");
//     chips.forEach((chip, index) => {
//         chip.classList.remove("active", "done");
//         if (index < forceStep) chip.classList.add("done");
//         else if (index === forceStep) chip.classList.add("active");
//     });
//     const btnNext = document.getElementById("btnForceNext");
//     const btnGenerate = document.getElementById("btnForceGenerate");
//     if (forceStep >= layerOrder.length) {
//         if (btnNext) btnNext.style.display = "none";
//         if (btnGenerate) btnGenerate.style.display = "inline-block";
//     } else {
//         if (btnNext) btnNext.style.display = "inline-block";
//         if (btnGenerate) btnGenerate.style.display = "none";
//     }
// }

// [FORCE-DISABLED] renderForceStep — re-renders the force graph for the current layer step
// function renderForceStep() {
//     if (graphLayoutMode !== "force") return;
//     updateForceStepUI();
//     const data = computeActiveGraphData();
//     renderForceGraph(data.nodes, data.links);
// }

// [FORCE-DISABLED] initForceExplorer — initialises the force graph explorer from forceGraphData
// function initForceExplorer() {
//     if (!forceGraphData || !Array.isArray(forceGraphData.nodes) || !forceGraphData.nodes.length) {
//         renderGraphPlaceholder();
//         return;
//     }
//     useForceGraphAsActiveData();
//     forceStep = 0;
//     selectedNodes = [];
//     clearPaletteSelectionState();
//     renderForceStep();
//     renderDesignSummary();
// }

// [FORCE-DISABLED] nextForceStep — advances the force layer step and re-renders
// function nextForceStep() {
//     if (graphLayoutMode === "som") return;
//     if (forceStep >= layerOrder.length) return;
//     const currentLayer = layerOrder[forceStep];
//     const count = selectedNodes.filter((n) => n.layer === currentLayer).length;
//     if (count === 0) {
//         alert("Please select at least one node in the current layer.");
//         return;
//     }
//     forceStep += 1;
//     renderForceStep();
//     renderDesignSummary();
// }

function resetForceFlow() {
    if (graphLayoutMode === "som") {
        resetSomFlow();
        return;
    }
    // [FORCE-DISABLED] Force reset branch — initForceExplorer disabled
    // if (!forceGraphData) return;
    // initForceExplorer();
}

function buildSelectionMaps() {
    const selectedByLayerGroup = {
        bottom_layer: {},
        middle_layer: {},
        top_layer: {},
    };

    selectedNodes.forEach((node) => {
        if (!selectedByLayerGroup[node.layer]) return;
        selectedByLayerGroup[node.layer][node.group_id] = node;
    });

    Object.entries(groupDefaults || {}).forEach(([layer, groupMap]) => {
        if (!selectedByLayerGroup[layer] || !groupMap || typeof groupMap !== "object") return;
        Object.entries(groupMap).forEach(([groupId, nodeId]) => {
            if (selectedByLayerGroup[layer][groupId]) return;
            const fallbackNode = getNodeById(nodeId);
            if (fallbackNode) selectedByLayerGroup[layer][groupId] = fallbackNode;
        });
    });

    return selectedByLayerGroup;
}

function buildFinalSelectionsFromGraph() {
    const selectedByLayerGroup = buildSelectionMaps();
    const finalSelections = {
        bottom_layer: {},
        middle_layer: {},
        top_layer: {},
    };

    layerOrder.forEach((layer) => {
        Object.entries(selectedByLayerGroup[layer] || {}).forEach(([groupId, node]) => {
            if (!node) return;

            if (groupId === "visual_assets") {
                if (node.option_payload && typeof node.option_payload === "object") {
                    finalSelections[layer][groupId] = JSON.parse(JSON.stringify(node.option_payload));
                } else {
                    finalSelections[layer][groupId] = {
                        category: node.group || "Visual Asset",
                        suggestion: node.name,
                        keywords: node.name,
                    };
                }
                return;
            }

            if (groupId === "color_scheme" && selectedPaletteMeta) {
                finalSelections[layer][groupId] = {
                    type: selectedPaletteMeta.type,
                    label: selectedPaletteMeta.label,
                    source_label: selectedPaletteMeta.source_label,
                    palette: selectedPaletteMeta.palette,
                    harmony_score: selectedPaletteMeta.harmony_score,
                };
                return;
            }

            finalSelections[layer][groupId] = node.name;
        });
    });

    return finalSelections;
}

function renderDesignSummary() {
    const container = document.getElementById("designSelectionSummary");
    if (!container) return;

    if (!fullGraphData) {
        container.innerHTML = graphLayoutMode === "som"
            ? '<div class="center-msg">Build SOM graph and select nodes first</div>'
            : '<div class="center-msg">Build force graph and select nodes first</div>';
        if (isDesignTabActive()) {
            requestAnimationFrame(() => {
                renderDesignSankey();
            });
        }
        return;
    }

    const selectionMap = buildSelectionMaps();

    const layerLabel = {
        bottom_layer: "Bottom Layer",
        middle_layer: "Middle Layer",
        top_layer: "Top Layer",
    };

    let html = "";
    layerOrder.forEach((layer) => {
        const groups = selectionMap[layer] || {};
        html += `<div class="data-row"><div class="data-label">${layerLabel[layer]}</div>`;

        if (Object.keys(groups).length === 0) {
            html += `<div class="data-value">No selection</div></div>`;
            return;
        }

        Object.values(groups).forEach((node) => {
            html += `<div class="data-value" style="margin-bottom:4px;">${node.group}: <b>${node.name}</b></div>`;
        });
        html += `</div>`;
    });

    if (selectedPaletteMeta && Array.isArray(selectedPaletteMeta.palette)) {
        const hexText = selectedPaletteMeta.palette
            .slice(0, 5)
            .map(toHexColor)
            .filter(Boolean)
            .join(" / ");
        html += `
        <div class="data-row">
            <div class="data-label">Selected Extracted Palette</div>
            <div class="data-value">${selectedPaletteMeta.label || "Palette"}</div>
            <div class="data-value" style="color:#059669;">${hexText || "N/A"}</div>
        </div>`;
    }

    container.innerHTML = html;
    if (isDesignTabActive()) {
        requestAnimationFrame(() => {
            renderDesignSankey();
        });
    }
}

function isDesignTabActive() {
    const tab = document.getElementById("tab-design");
    return Boolean(tab && tab.classList.contains("active"));
}

function renderDesignSankey() {
    const sankeyContainer = document.getElementById("designSankeyContainer");
    const schemeLabel = document.getElementById("designSankeySchemeLabel");
    if (!sankeyContainer) return;

    if (!galleryData.length) {
        if (schemeLabel) schemeLabel.textContent = "No Scheme";
        sankeyContainer.innerHTML = '<div class="center-msg">Generate and select a scheme first</div>';
        return;
    }

    if (activeGalleryIndex >= galleryData.length) activeGalleryIndex = galleryData.length - 1;
    if (activeGalleryIndex < 0) activeGalleryIndex = 0;
    galleryViewMode = "single";

    const activeItem = galleryData[activeGalleryIndex];
    if (!activeItem) {
        if (schemeLabel) schemeLabel.textContent = "No Scheme";
        sankeyContainer.innerHTML = '<div class="center-msg">No active scheme</div>';
        return;
    }

    const schemeNumber = galleryData.length - activeGalleryIndex;
    if (schemeLabel) schemeLabel.textContent = `Scheme ${schemeNumber}`;
    const context = getAnalysisContextForGalleryItem(activeItem);
    renderSankeyDiagram(sankeyContainer, activeItem, context, { aggregate: false });
}

async function generateFinalPosterFromForceGraph() {
    if (!fullGraphData) {
        alert(`Build ${getGraphModeLabel(graphLayoutMode)} first.`);
        return;
    }

    const btn = document.getElementById("btnForceGenerate");
    const originalText = btn ? btn.innerText : "Generate Infographic";
    if (btn) {
        btn.innerText = "Generating...";
        btn.disabled = true;
    }

    try {
        const finalSelections = buildFinalSelectionsFromGraph();

        const res = await fetch("/infographic/generate_final", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                selections: finalSelections,
                chart_source: currentChartData,
                description: document.getElementById("tableDesc").value,
                query: document.getElementById("queryInput").value,
                analysis_result: currentAnalysisAnswer,
            }),
        });
        const data = await res.json();

        if (data.status === "success") {
            addToGallery(data.image_url, finalSelections);
            switchTab(3);
            if (btn) btn.innerText = "Done";
        } else {
            alert(data.error || "Final generation failed");
            if (btn) btn.innerText = "Retry";
        }
    } catch (e) {
        alert("Final generation error: " + e);
        if (btn) btn.innerText = "Error";
    } finally {
        if (btn) {
            setTimeout(() => {
                btn.innerText = originalText;
                btn.disabled = false;
            }, 1200);
        }
    }
}

// Gallery UI/addToGallery/switch handlers are overridden in the Sankey section below.

async function renderRefImage(url) {
    const mainImage = document.getElementById("mainImage");
    const svgLayer = document.getElementById("interactionLayer");
    const canvasContainer = document.getElementById("canvasContainer");
    const refPlaceholder = document.getElementById("refPlaceholder");

    if (!mainImage || !svgLayer || !canvasContainer || !refPlaceholder) return;

    canvasContainer.style.display = "inline-block";
    refPlaceholder.style.display = "none";
    svgLayer.innerHTML = "";

    return new Promise((resolve) => {
        mainImage.onload = () => {
            svgLayer.setAttribute("viewBox", `0 0 ${mainImage.naturalWidth} ${mainImage.naturalHeight}`);
            resolve();
        };
        mainImage.src = `${url}?t=${Date.now()}`;
    });
}

function renderMasks(items) {
    const svgLayer = document.getElementById("interactionLayer");
    if (!svgLayer) return;

    svgLayer.innerHTML = "";
    (items || []).forEach((item, idx) => {
        if (!Array.isArray(item.polygons) || !item.polygons.length) return;

        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        item.polygons.forEach((poly) => {
            const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            polygon.setAttribute("points", poly.map((p) => p.join(",")).join(" "));
            polygon.setAttribute("class", "mask-poly");
            group.appendChild(polygon);
        });

        group.addEventListener("click", (event) => {
            event.stopPropagation();
            document.querySelectorAll(".mask-poly").forEach((el) => el.classList.remove("active"));
            group.querySelectorAll(".mask-poly").forEach((el) => el.classList.add("active"));
            window.selectExtractedPalette(idx);
        });

        svgLayer.appendChild(group);
    });
}

function renderPaletteOptions(items) {
    const panel = document.getElementById("paletteOptionsPanel");
    if (!panel) return;

    if (!Array.isArray(items) || items.length === 0) {
        panel.innerHTML = '<div class="center-msg">No extracted palettes</div>';
        return;
    }

    const cards = items.map((item, idx) => {
        const swatches = (item.palette || [])
            .map((c) => `<div class="color-swatch" style="background:${toHexColor(c) || '#ddd'}" title="${toHexColor(c) || ''}"></div>`)
            .join("");

        const selected = selectedPaletteMeta && selectedPaletteMeta._index === idx;
        const harmony = typeof item.harmony_score === "number" ? item.harmony_score.toFixed(3) : "N/A";
        return `
        <div class="palette-option-card ${selected ? "selected" : ""}" onclick="selectExtractedPalette(${idx})">
            <div class="palette-option-title">${item.label || `Object ${idx + 1}`} | Harmony ${harmony}</div>
            <div class="palette-grid">${swatches || '<div class="center-msg">No colors</div>'}</div>
        </div>`;
    }).join("");

    panel.innerHTML = cards;
}

window.selectExtractedPalette = function(index) {
    const item = extractedPaletteResults[index];
    if (!item || !Array.isArray(item.palette) || !item.palette.length) return;

    const colorNode = getNodeById(selectedColorNodeId);
    const nodeName = colorNode ? colorNode.name : "Node Palette";

    selectedPaletteMeta = {
        type: "palette",
        label: `Palette-${nodeName}-${index + 1}`,
        source_label: item.label || `object_${index + 1}`,
        palette: item.palette,
        harmony_score: item.harmony_score ?? null,
        _index: index,
    };

    renderPaletteOptions(extractedPaletteResults);
    renderDesignSummary();
};

async function generatePaletteFromSelectedColorNode(options = {}) {
    const colorNode = getNodeById(selectedColorNodeId);
    if (!colorNode) return;
    const regionPromptInput = document.getElementById("regionPromptInput");
    const userRegionPrompt = regionPromptInput ? regionPromptInput.value.trim() : "";
    const shouldReuseImage = Boolean(options.reuseImage) && Boolean(currentRefImagePath);

    toggleLoading("loading-palette-node", true);

    try {
        const res = await fetch("/palette/from_color_node", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                description: document.getElementById("tableDesc").value,
                query: document.getElementById("queryInput").value,
                analysis_result: currentAnalysisAnswer,
                chart_source: currentChartData,
                node_label: colorNode.name,
                node_desc: colorNode.desc || "",
                user_region_prompt: userRegionPrompt,
                reuse_image: shouldReuseImage,
                current_image_path: currentRefImagePath,
                aspect_ratio: "1:1",
            }),
        });
        const data = await res.json();

        if (data.status !== "success") {
            alert(data.error || "Palette generation failed");
            return;
        }

        currentRefImagePath = data.image_path || "";
        extractedPaletteResults = (data.results || []).filter((r) => Array.isArray(r.palette) && r.palette.length > 0);

        const promptPreview = document.getElementById("palettePromptPreview");
        if (promptPreview) promptPreview.value = data.composed_prompt || "";

        if (currentRefImagePath && !data.used_existing_image) {
            await renderRefImage(currentRefImagePath);
            if (data.full_image_mode) {
                const interactionLayer = document.getElementById("interactionLayer");
                if (interactionLayer) interactionLayer.innerHTML = "";
            } else {
                renderMasks(data.results || []);
            }
        } else if (data.used_existing_image) {
            if (data.full_image_mode) {
                const interactionLayer = document.getElementById("interactionLayer");
                if (interactionLayer) interactionLayer.innerHTML = "";
            } else {
                renderMasks(data.results || []);
            }
        }

        selectedPaletteMeta = null;
        renderPaletteOptions(extractedPaletteResults);
        renderDesignSummary();
        switchTab(2);
        saveSession();
    } catch (e) {
        alert("Palette from node error: " + e);
    } finally {
        toggleLoading("loading-palette-node", false);
    }
}

async function uploadCsv() {
    const fileInput = document.getElementById("fileInput");
    if (!fileInput.files.length) {
        alert("Select CSV first");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    toggleLoading("loading-upload", true);
    document.getElementById("btnUpload").disabled = true;

    try {
        const res = await fetch("/upload_csv", { method: "POST", body: formData });
        const data = await res.json();

        if (data.status !== "success") {
            alert(data.error || "Upload failed");
            return;
        }

        currentFilePath = data.filepath;
        document.getElementById("btnAnalyze").disabled = false;
        renderSchema(data.meta);

        if (data.description) {
            document.getElementById("tableDesc").value = data.description;
        }

        saveSession();
        alert("Data Loaded");
    } catch (e) {
        alert("Upload Error: " + e);
    } finally {
        toggleLoading("loading-upload", false);
        document.getElementById("btnUpload").disabled = false;
    }
}

async function runAnalysis() {
    const desc = document.getElementById("tableDesc").value;
    const query = document.getElementById("queryInput").value;
    if (!currentFilePath || !query) {
        alert("Missing data or query");
        return;
    }

    toggleLoading("loading-analyze", true);
    document.getElementById("btnAnalyze").disabled = true;

    try {
        const res = await fetch("/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                filepath: currentFilePath,
                description: desc,
                query: query,
            }),
        });
        const data = await res.json();

        if (data.status !== "success") {
            alert(data.error || "Analysis failed");
            return;
        }

        currentAnalysisAnswer = data.answer || "";
        document.getElementById("tab-insight").innerHTML = `<div style="font-size:12px; line-height:1.5">${(data.answer || "").replace(/\n/g, "<br>")}</div>`;

        if (data.chart) {
            currentChartData = data.chart;
            const spec = JSON.parse(JSON.stringify(data.chart));
            spec.width = "container";
            spec.height = "container";
            spec.autosize = { type: "fit", contains: "padding", resize: true };
            document.getElementById("vis").innerHTML = "";
            vegaEmbed("#vis", spec, { actions: false, renderer: "canvas" }).catch(console.warn);

            document.getElementById("btnGenInfo").style.display = "block";
            updateGraphActionLabels();
            switchTab(1);
        }
        saveSession();
    } catch (e) {
        alert("Analysis Error: " + e);
    } finally {
        toggleLoading("loading-analyze", false);
        document.getElementById("btnAnalyze").disabled = false;
    }
}

async function buildForceGraphPlan() {
    if (!currentChartData) {
        alert("Please run analysis first.");
        return;
    }

    const mode = graphLayoutMode === "som" ? "som" : "force";
    const sampleCount = getRequestedSampleCount();
    stopForceGraphPolling();
    toggleLoading("loading-info", true);
    document.getElementById("btnGenInfo").disabled = true;
    const loadingInfo = document.getElementById("loading-info");
    if (loadingInfo) loadingInfo.textContent = `GENERATING ${sampleCount} PLANS`;
    setForceProgress(1, `Starting ${getGraphModeLabel(mode)} job (${sampleCount} runs)...`, true);

    try {
        const res = await fetch("/infographic/force_graph_plan/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                description: document.getElementById("tableDesc").value,
                query: document.getElementById("queryInput").value,
                analysis_result: currentAnalysisAnswer,
                chart_source: currentChartData,
                sample_count: sampleCount,
                layout_mode: mode,
            }),
        });
        const data = await res.json();

        if (data.status !== "success") {
            alert(data.error || `${getGraphModeLabel(mode)} generation failed`);
            toggleLoading("loading-info", false);
            document.getElementById("btnGenInfo").disabled = false;
            return;
        }
        forceGraphJobId = data.job_id;
        forceGraphLastProgress = -1;
        forceGraphPollDelayMs = 2500;
        scheduleForceGraphPolling(300);
    } catch (e) {
        alert(`${getGraphModeLabel(mode)} Error: ${e}`);
        setForceProgress(100, `Failed: ${e}`, true);
        toggleLoading("loading-info", false);
        document.getElementById("btnGenInfo").disabled = false;
    } finally {
        // Keep loading state until async polling completes.
    }
}

function syncForceJsonUploadState() {
    const fileInput = document.getElementById("forceJsonInput");
    const uploadBtn = document.getElementById("btnGenInfoFromJson");
    if (!fileInput || !uploadBtn) return;
    uploadBtn.disabled = !(fileInput.files && fileInput.files.length > 0);
}

async function buildForceGraphFromUploadedJson() {
    const fileInput = document.getElementById("forceJsonInput");
    if (!fileInput || !fileInput.files || !fileInput.files.length) {
        alert("Please choose a JSON file first.");
        return;
    }

    const mode = graphLayoutMode === "som" ? "som" : "force";
    stopForceGraphPolling();
    forceGraphJobId = null;
    toggleLoading("loading-info-json", true);
    setForceProgress(8, `Uploading JSON for ${getGraphModeLabel(mode)}: ${fileInput.files[0].name}`, true);

    const uploadBtn = document.getElementById("btnGenInfoFromJson");
    const buildBtn = document.getElementById("btnGenInfo");
    if (uploadBtn) uploadBtn.disabled = true;
    if (buildBtn) buildBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        formData.append("layout_mode", mode);

        const res = await fetch("/infographic/force_graph_plan/upload_json", {
            method: "POST",
            body: formData,
        });
        const data = await res.json();

        if (data.status !== "success") {
            const errMsg = data.error || "Uploaded JSON processing failed";
            alert(errMsg);
            setForceProgress(100, errMsg, true);
            return;
        }

        const ok = applyGraphBundleByMode(data, mode);
        const runCount = Number(data.target_count || 0);
        if (ok) {
            const doneMsg = runCount > 0
                ? `${getGraphModeLabel(mode)} built from uploaded JSON (${runCount} runs).`
                : `${getGraphModeLabel(mode)} built from uploaded JSON.`;
            setForceProgress(100, doneMsg, true);
            saveSession();
        } else {
            setForceProgress(100, "Uploaded JSON parsed, but no graph nodes.", true);
        }
    } catch (e) {
        alert("Upload JSON Error: " + e);
        setForceProgress(100, `Upload JSON failed: ${e}`, true);
    } finally {
        toggleLoading("loading-info-json", false);
        if (buildBtn) buildBtn.disabled = false;
        syncForceJsonUploadState();
    }
}

function deepClone(value) {
    if (value === undefined) return undefined;
    if (typeof structuredClone === "function") {
        try {
            return structuredClone(value);
        } catch (_) {
            // Fall through to JSON clone.
        }
    }
    return JSON.parse(JSON.stringify(value));
}

function normalizeMatchText(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "")
        .replace(/[^\w\u4e00-\u9fa5]/g, "");
}

function shortSankeyLabel(text, maxLen = 8) {
    const raw = String(text || "").trim();
    if (!raw) return "N/A";
    if (raw.length <= maxLen) return raw;
    return `${raw.slice(0, maxLen)}...`;
}

function clampToByte(num) {
    return Math.max(0, Math.min(255, Number(num) || 0));
}

function normalizeRgbTriplet(color) {
    if (!Array.isArray(color) || color.length < 3) return null;
    return [
        Math.round(clampToByte(color[0])),
        Math.round(clampToByte(color[1])),
        Math.round(clampToByte(color[2])),
    ];
}

function rgbTripletFromHex(hex) {
    const clean = String(hex || "").trim().replace("#", "");
    if (!/^[0-9a-fA-F]{6}$/.test(clean)) return null;
    return [
        Number.parseInt(clean.slice(0, 2), 16),
        Number.parseInt(clean.slice(2, 4), 16),
        Number.parseInt(clean.slice(4, 6), 16),
    ];
}

function normalizePalettePayload(meta, fallbackLabel = "Palette") {
    if (!meta || typeof meta !== "object") return null;
    const palette = (Array.isArray(meta.palette) ? meta.palette : [])
        .map((color) => {
            if (Array.isArray(color)) return normalizeRgbTriplet(color);
            if (typeof color === "string") return rgbTripletFromHex(color);
            return null;
        })
        .filter(Boolean);

    if (!palette.length) return null;

    return {
        type: String(meta.type || "palette"),
        label: String(meta.label || fallbackLabel || "Palette"),
        source_label: String(meta.source_label || meta.label || fallbackLabel || "palette_source"),
        palette,
        harmony_score: Number.isFinite(Number(meta.harmony_score)) ? Number(meta.harmony_score) : null,
    };
}

function paletteHexListFromPayload(payload) {
    const normalized = normalizePalettePayload(payload);
    if (!normalized) return [];
    return normalized.palette
        .map((triplet) => toHexColor(triplet))
        .filter(Boolean);
}

function getSankeyColumnColor(column, payload = null) {
    if (Number(column) === 4) {
        const paletteHex = paletteHexListFromPayload(payload);
        return paletteHex[0] || SANKEY_COLUMN_COLORS[4];
    }
    return SANKEY_COLUMN_COLORS[column] || "#B0B8C4";
}

function getSankeySafeId(parts) {
    return parts
        .map((part) => String(part || "unknown").trim().replace(/[^\w\u4e00-\u9fa5-]+/g, "_"))
        .join("::");
}

function getSankeyLinkKey(sourceId, targetId) {
    return `${sourceId}=>${targetId}`;
}

function getGalleryWorkingSelections(galleryItem) {
    return deepClone(galleryItem?.pendingSelections || galleryItem?.selections || {
        bottom_layer: {},
        middle_layer: {},
        top_layer: {},
    });
}

function getAnalysisContextForGalleryItem(galleryItem) {
    const snap = galleryItem?.analysisSnapshot || {};
    return {
        query: snap.query ?? (document.getElementById("queryInput")?.value || ""),
        description: snap.description ?? (document.getElementById("tableDesc")?.value || ""),
        analysisAnswer: snap.analysisAnswer ?? currentAnalysisAnswer,
        chartData: snap.chartData ?? currentChartData,
        paletteMeta: snap.paletteMeta ?? selectedPaletteMeta,
    };
}

function getSelectionDisplayName(groupId, value) {
    if (value === null || value === undefined) return "N/A";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        return String(value);
    }
    if (typeof value !== "object") return String(value);

    if (groupId === "color_scheme") {
        return value.label || value.name || value.source_label || "Palette";
    }
    if (groupId === "visual_assets") {
        return value.suggestion || value.keywords || value.label || value.name || "Asset";
    }

    return value.label || value.name || value.value || value.text || value.content || JSON.stringify(value);
}

function getGraphLinkWeightLookup() {
    if (!fullGraphData || !Array.isArray(fullGraphData.links)) return new Map();
    if (graphLinkWeightCache && graphLinkWeightCacheRef === fullGraphData) {
        return graphLinkWeightCache;
    }

    const map = new Map();
    fullGraphData.links.forEach((link) => {
        const sourceId = getSourceId(link);
        const targetId = getTargetId(link);
        if (!sourceId || !targetId) return;
        const key = [sourceId, targetId].sort().join("||");

        let strength = Number(link.jaccard);
        if (!Number.isFinite(strength)) {
            const lift = Number(link.lift);
            if (Number.isFinite(lift)) {
                strength = Math.min(1, Math.max(0, lift / 5));
            } else {
                const coOccur = Number(link.co_occur);
                strength = Number.isFinite(coOccur) ? Math.min(1, Math.max(0, coOccur / 10)) : 0;
            }
        }

        const existing = map.get(key);
        if (!Number.isFinite(existing) || strength > existing) {
            map.set(key, strength);
        }
    });

    graphLinkWeightCache = map;
    graphLinkWeightCacheRef = fullGraphData;
    return map;
}

function getStrengthFromIds(sourceIds, targetIds) {
    const lookup = getGraphLinkWeightLookup();
    let best = null;

    sourceIds.forEach((sourceId) => {
        targetIds.forEach((targetId) => {
            if (!sourceId || !targetId || sourceId === targetId) return;
            const key = [sourceId, targetId].sort().join("||");
            const strength = lookup.get(key);
            if (Number.isFinite(strength)) {
                best = best === null ? strength : Math.max(best, strength);
            }
        });
    });

    return best;
}

function getGraphCandidates(layer, groupId) {
    if (!fullGraphData || !Array.isArray(fullGraphData.nodes)) return [];
    return fullGraphData.nodes.filter((node) => node.layer === layer && node.group_id === groupId);
}

function makeAlternativeFromGraphNode(node, layerHint, groupHint) {
    const payload = node?.option_payload && typeof node.option_payload === "object"
        ? deepClone(node.option_payload)
        : null;

    const alt = {
        id: String(node?.id || ""),
        name: String(node?.name || node?.label || node?.id || "Option"),
        layer: layerHint || node?.layer || "middle_layer",
        groupId: groupHint || node?.group_id || "unknown_group",
        nodeType: "design_element",
        payload,
        graphRefId: String(node?.id || ""),
        val: Number(node?.val || node?.count || 1) || 1,
    };

    if (alt.groupId === "color_scheme") {
        const palettePayload = normalizePalettePayload(payload || {}, alt.name);
        alt.nodeType = "palette";
        if (palettePayload) alt.payload = palettePayload;
    }

    return alt;
}

function getAlternativesForNode(layer, groupId, excludeId) {
    return getGraphCandidates(layer, groupId)
        .filter((node) => String(node.id) !== String(excludeId))
        .sort((a, b) => (Number(b.val || b.count || 0) - Number(a.val || a.count || 0)))
        .slice(0, 6)
        .map((node) => makeAlternativeFromGraphNode(node, layer, groupId));
}

function getPaletteAlternatives(excludeId) {
    const alternatives = [];

    (fullGraphData?.nodes || [])
        .filter((node) => node.is_palette_node || node.group_id === "color_scheme")
        .forEach((node) => {
            if (String(node.id) === String(excludeId)) return;
            alternatives.push({
                ...makeAlternativeFromGraphNode(node, "middle_layer", "color_scheme"),
                nodeType: "palette",
            });
        });

    extractedPaletteResults.forEach((item, idx) => {
        const payload = normalizePalettePayload({
            type: "palette",
            label: item?.label || `Extracted-${idx + 1}`,
            source_label: item?.label || `object_${idx + 1}`,
            palette: item?.palette || [],
            harmony_score: item?.harmony_score,
        }, `Extracted-${idx + 1}`);
        if (!payload) return;

        alternatives.push({
            id: `palette_preset::${idx}`,
            name: payload.label || `Preset ${idx + 1}`,
            layer: "middle_layer",
            groupId: "color_scheme",
            nodeType: "palette",
            payload,
            graphRefId: "",
            val: 1,
        });
    });

    const unique = new Map();
    alternatives.forEach((alt) => {
        if (!alt || !alt.id) return;
        if (!unique.has(alt.id)) unique.set(alt.id, alt);
    });

    return Array.from(unique.values()).slice(0, 8);
}

function findGraphNodeMatch(layer, groupId, selectedValue, displayName) {
    const candidates = getGraphCandidates(layer, groupId);
    if (!candidates.length) return null;

    const targets = new Set([
        normalizeMatchText(displayName),
        normalizeMatchText(selectedValue?.label),
        normalizeMatchText(selectedValue?.name),
        normalizeMatchText(selectedValue?.value),
        normalizeMatchText(selectedValue?.suggestion),
        normalizeMatchText(selectedValue?.keywords),
    ]);

    let direct = candidates.find((node) => targets.has(normalizeMatchText(node.name)));
    if (direct) return direct;

    direct = candidates.find((node) => targets.has(normalizeMatchText(node.id)));
    if (direct) return direct;

    return candidates[0];
}

function inferDataDomain(query, analysisAnswer) {
    const text = `${query || ""} ${analysisAnswer || ""}`;
    const rules = [
        { tag: "历史文物", keys: ["文物", "瓷器", "考古", "博物馆", "朝代"] },
        { tag: "金融", keys: ["金融", "股票", "收益", "基金", "市值"] },
        { tag: "医疗", keys: ["医疗", "患者", "诊断", "药物", "医院"] },
        { tag: "教育", keys: ["教育", "学校", "学生", "成绩", "课程"] },
        { tag: "电商", keys: ["电商", "销售", "订单", "用户", "GMV"] },
    ];

    for (const rule of rules) {
        if (rule.keys.some((key) => text.includes(key))) return rule.tag;
    }
    return "通用数据";
}

function extractInsightNodes(query, analysisAnswer) {
    const nodes = [];
    const intentText = String(query || "用户问题").trim();
    nodes.push({
        id: getSankeySafeId(["insight", "query_intent", intentText.slice(0, 20)]),
        name: intentText.slice(0, 20) || "Query Intent",
        groupId: "query_intent",
        payload: { raw: intentText },
    });

    const metricMatch = String(analysisAnswer || "").match(/[-+]?\d+(?:\.\d+)?%?/g);
    if (metricMatch && metricMatch.length) {
        const metric = metricMatch.slice(0, 3).join(" / ");
        nodes.push({
            id: getSankeySafeId(["insight", "key_metric", metric]),
            name: `指标 ${metric}`.slice(0, 20),
            groupId: "key_metric",
            payload: { metric },
        });
    }

    const domain = inferDataDomain(query, analysisAnswer);
    nodes.push({
        id: getSankeySafeId(["insight", "data_domain", domain]),
        name: domain,
        groupId: "data_domain",
        payload: { domain },
    });

    return nodes;
}

function normalizeSankeyLinksBySource(links, maxFlowWidth = SANKEY_MAX_FLOW_WIDTH) {
    const grouped = {};
    links.forEach((link) => {
        const sourceId = String(link.source || "");
        if (!grouped[sourceId]) grouped[sourceId] = [];
        grouped[sourceId].push(link);
    });

    Object.values(grouped).forEach((groupLinks) => {
        const exps = groupLinks.map((link) => Math.exp(Number(link.strength || 0)));
        const total = exps.reduce((sum, num) => sum + num, 0) || 1;
        groupLinks.forEach((link, idx) => {
            const normalized = exps[idx] / total;
            link.value = Math.max(1, Math.round(normalized * maxFlowWidth));
            link.normalized_weight = normalized;
        });
    });
}

function ensureSankeyColumns(nodes) {
    const byCol = {};
    nodes.forEach((node) => {
        const col = Number(node.column || 0);
        if (!byCol[col]) byCol[col] = [];
        byCol[col].push(node);
    });

    for (let col = 0; col < SANKEY_COLUMN_COUNT; col += 1) {
        if (!byCol[col] || !byCol[col].length) {
            const placeholder = {
                id: `placeholder::${col}`,
                name: "N/A",
                column: col,
                layer: "placeholder",
                groupId: "placeholder",
                nodeType: "design_element",
                value: 1,
                color: getSankeyColumnColor(col),
                isEditable: false,
                isActive: false,
                payload: {},
                alternatives: [],
                graphRefId: "",
            };
            nodes.push(placeholder);
            byCol[col] = [placeholder];
        }
    }
    return byCol;
}

function repairIsolatedSankeyNodes(nodes, links) {
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const inDegree = {};
    const outDegree = {};

    links.forEach((link) => {
        const sourceId = String(link.source);
        const targetId = String(link.target);
        inDegree[targetId] = (inDegree[targetId] || 0) + 1;
        outDegree[sourceId] = (outDegree[sourceId] || 0) + 1;
    });

    const columns = ensureSankeyColumns(nodes);

    nodes.forEach((node) => {
        const hasIn = (inDegree[node.id] || 0) > 0;
        const hasOut = (outDegree[node.id] || 0) > 0;
        if (hasIn || hasOut) return;

        // Preserve relationship fidelity: only auto-bridge synthetic placeholders.
        if (node.layer !== "placeholder") return;

        const col = Number(node.column || 0);
        if (col === SANKEY_COLUMN_COUNT - 1) {
            const prev = columns[col - 1]?.[0];
            if (prev) {
                links.push({ source: prev.id, target: node.id, value: 1, strength: 0.25, isHighlighted: false });
            }
        } else {
            const next = columns[col + 1]?.[0];
            if (next) {
                links.push({ source: node.id, target: next.id, value: 1, strength: 0.25, isHighlighted: false });
            }
        }
    });

    for (let idx = links.length - 1; idx >= 0; idx -= 1) {
        const link = links[idx];
        const source = nodeMap.get(String(link.source));
        const target = nodeMap.get(String(link.target));
        if (!source || !target || source.column >= target.column || source.id === target.id) {
            links.splice(idx, 1);
        }
    }
}

function buildSankeyData(galleryItem, analysisContext = {}) {
    const selections = getGalleryWorkingSelections(galleryItem) || {};
    const nodes = [];
    const links = [];
    const nodeMap = new Map();
    const linkMap = new Map();
    const columns = Array.from({ length: SANKEY_COLUMN_COUNT }, () => []);

    const addNode = (rawNode) => {
        if (!rawNode || !rawNode.id) return null;
        const id = String(rawNode.id);

        if (nodeMap.has(id)) {
            const existing = nodeMap.get(id);
            existing.value += Number(rawNode.value || 1);
            return existing;
        }

        const node = {
            id,
            name: rawNode.name || id,
            column: Number(rawNode.column || 0),
            layer: rawNode.layer || "middle_layer",
            groupId: rawNode.groupId || "unknown_group",
            nodeType: rawNode.nodeType || "design_element",
            value: Math.max(1, Number(rawNode.value || 1)),
            color: rawNode.color || getSankeyColumnColor(Number(rawNode.column || 0), rawNode.payload),
            isEditable: Boolean(rawNode.isEditable),
            isActive: rawNode.isActive !== false,
            payload: rawNode.payload && typeof rawNode.payload === "object" ? rawNode.payload : {},
            alternatives: Array.isArray(rawNode.alternatives) ? rawNode.alternatives : [],
            graphRefId: String(rawNode.graphRefId || ""),
        };

        nodes.push(node);
        nodeMap.set(id, node);
        if (columns[node.column]) columns[node.column].push(node);
        return node;
    };

    const addLink = (sourceId, targetId, value = 1, strength = 1) => {
        const source = nodeMap.get(String(sourceId));
        const target = nodeMap.get(String(targetId));
        if (!source || !target) return;
        if (source.id === target.id || source.column >= target.column) return;

        const key = getSankeyLinkKey(source.id, target.id);
        if (linkMap.has(key)) {
            const existing = linkMap.get(key);
            existing.value += Number(value || 1);
            existing.strength = (Number(existing.strength || 0) + Number(strength || 0)) / 2;
            return;
        }

        const link = {
            source: source.id,
            target: target.id,
            value: Math.max(1, Number(value || 1)),
            strength: Math.max(0, Math.min(1, Number(strength || 0))),
            isHighlighted: false,
        };
        links.push(link);
        linkMap.set(key, link);
    };

    const insightNodes = extractInsightNodes(analysisContext.query, analysisContext.analysisAnswer).map((insight) => addNode({
        id: insight.id,
        name: insight.name,
        column: 0,
        layer: "data_insight",
        groupId: insight.groupId,
        nodeType: "data_insight",
        value: 1,
        color: getSankeyColumnColor(0),
        isEditable: false,
        isActive: true,
        payload: insight.payload || {},
        alternatives: [],
        graphRefId: "",
    })).filter(Boolean);

    const buildLayerNodes = (layer, columnIdx) => {
        const layerData = selections[layer] && typeof selections[layer] === "object" ? selections[layer] : {};
        const built = [];
        Object.entries(layerData).forEach(([groupId, selectedValue]) => {
            const displayName = getSelectionDisplayName(groupId, selectedValue);
            const matchedGraph = findGraphNodeMatch(layer, groupId, selectedValue, displayName);
            const payload = (selectedValue && typeof selectedValue === "object")
                ? deepClone(selectedValue)
                : (matchedGraph?.option_payload && typeof matchedGraph.option_payload === "object"
                    ? deepClone(matchedGraph.option_payload)
                    : {});
            const nodeId = matchedGraph?.id || getSankeySafeId([layer, groupId, displayName]);
            const alternatives = getAlternativesForNode(layer, groupId, nodeId);

            const node = addNode({
                id: nodeId,
                name: displayName,
                column: columnIdx,
                layer,
                groupId,
                nodeType: "design_element",
                value: 1,
                color: getSankeyColumnColor(columnIdx),
                isEditable: true,
                isActive: true,
                payload,
                alternatives,
                graphRefId: matchedGraph?.id || "",
            });
            if (node) built.push(node);
        });
        return built;
    };

    const bottomNodes = buildLayerNodes("bottom_layer", 1);
    const middleNodes = buildLayerNodes("middle_layer", 2);
    const topNodes = buildLayerNodes("top_layer", 3);
    const colorSchemeNode = middleNodes.find((node) => node.groupId === "color_scheme") || null;

    let palettePayload = normalizePalettePayload(analysisContext.paletteMeta, "Palette");
    if (!palettePayload) {
        palettePayload = normalizePalettePayload(selections?.middle_layer?.color_scheme, colorSchemeNode?.name || "Palette");
    }
    if (!palettePayload && colorSchemeNode?.payload) {
        palettePayload = normalizePalettePayload(colorSchemeNode.payload, colorSchemeNode.name || "Palette");
    }

    let paletteNode = null;
    if (palettePayload || colorSchemeNode) {
        const paletteLabel = palettePayload?.label || colorSchemeNode?.name || "Palette";
        const paletteId = palettePayload
            ? getSankeySafeId(["palette", paletteLabel, galleryItem?.id || "active"])
            : getSankeySafeId(["palette", colorSchemeNode?.id || "color_scheme"]);

        paletteNode = addNode({
            id: paletteId,
            name: paletteLabel,
            column: 4,
            layer: "palette",
            groupId: "palette",
            nodeType: "palette",
            value: 1,
            color: getSankeyColumnColor(4, palettePayload),
            isEditable: true,
            isActive: true,
            payload: palettePayload || {},
            alternatives: getPaletteAlternatives(paletteId),
            graphRefId: colorSchemeNode?.graphRefId || colorSchemeNode?.id || "",
        });
    }

    const outputNode = addNode({
        id: getSankeySafeId(["output", galleryItem?.id || "active"]),
        name: `Infographic #${String(galleryItem?.id || "N").slice(-4)}`,
        column: 5,
        layer: "output",
        groupId: "output",
        nodeType: "output",
        value: 1,
        color: getSankeyColumnColor(5),
        isEditable: false,
        isActive: true,
        payload: { imgUrl: galleryItem?.imgUrl || "" },
        alternatives: [],
        graphRefId: "",
    });

    insightNodes.forEach((insightNode) => {
        bottomNodes.forEach((bottomNode) => {
            addLink(insightNode.id, bottomNode.id, 1, 1);
        });
    });

    const getNodeGraphIds = (node) => {
        const ids = [];
        if (node.graphRefId) ids.push(node.graphRefId);
        ids.push(node.id);
        return Array.from(new Set(ids));
    };

    bottomNodes.forEach((bottomNode) => {
        middleNodes.forEach((middleNode) => {
            const strength = getStrengthFromIds(getNodeGraphIds(bottomNode), getNodeGraphIds(middleNode));
            if (!Number.isFinite(strength) || strength <= 0) return;
            const s = Math.max(0, Math.min(1, Number(strength)));
            const flowValue = Math.max(1, Math.round(1 + (s * 10)));
            addLink(bottomNode.id, middleNode.id, flowValue, s);
        });
    });

    middleNodes.forEach((middleNode) => {
        topNodes.forEach((topNode) => {
            const strength = getStrengthFromIds(getNodeGraphIds(middleNode), getNodeGraphIds(topNode));
            if (!Number.isFinite(strength) || strength <= 0) return;
            const s = Math.max(0, Math.min(1, Number(strength)));
            const flowValue = Math.max(1, Math.round(1 + (s * 10)));
            addLink(middleNode.id, topNode.id, flowValue, s);
        });
    });

    if (colorSchemeNode && paletteNode) {
        addLink(colorSchemeNode.id, paletteNode.id, 1, 1);
    }

    topNodes.forEach((topNode) => {
        addLink(topNode.id, outputNode.id, 1, 1);
    });
    if (paletteNode) {
        addLink(paletteNode.id, outputNode.id, 1, 1);
    }

    ensureSankeyColumns(nodes);
    repairIsolatedSankeyNodes(nodes, links);

    return {
        nodes,
        links,
        selections,
        isAggregate: false,
    };
}

function aggregateSankeyData(allGalleryItems, analysisContext = {}) {
    const nodeMap = new Map();
    const linkMap = new Map();

    allGalleryItems.forEach((item) => {
        const itemContext = getAnalysisContextForGalleryItem(item) || analysisContext;
        const data = buildSankeyData(item, itemContext);

        data.nodes.forEach((node) => {
            if (!nodeMap.has(node.id)) {
                nodeMap.set(node.id, {
                    ...deepClone(node),
                    alternatives: Array.isArray(node.alternatives) ? [...node.alternatives] : [],
                });
            } else {
                const existing = nodeMap.get(node.id);
                existing.value += Number(node.value || 1);
            }
        });

        data.links.forEach((link) => {
            const key = getSankeyLinkKey(link.source, link.target);
            if (!linkMap.has(key)) {
                linkMap.set(key, {
                    source: link.source,
                    target: link.target,
                    value: Number(link.value || 1),
                    _weight: Number(link.value || 1),
                    _strengthWeighted: Number(link.strength || 0) * Number(link.value || 1),
                    strength: Number(link.strength || 0),
                    isHighlighted: false,
                });
                return;
            }

            const existing = linkMap.get(key);
            existing.value += Number(link.value || 1);
            existing._weight += Number(link.value || 1);
            existing._strengthWeighted += Number(link.strength || 0) * Number(link.value || 1);
        });
    });

    const nodes = Array.from(nodeMap.values());
    const links = Array.from(linkMap.values()).map((link) => {
        const weight = Math.max(1, Number(link._weight || 1));
        const strength = Number(link._strengthWeighted || 0) / weight;
        return {
            source: link.source,
            target: link.target,
            value: Number(link.value || 1),
            strength: Math.max(0, Math.min(1, strength)),
            isHighlighted: false,
        };
    });

    const values = links.map((link) => Number(link.value || 0));
    const minValue = values.length ? Math.min(...values) : 1;
    const maxValue = values.length ? Math.max(...values) : 1;
    links.forEach((link) => {
        if (maxValue === minValue) {
            link.value = 6;
            return;
        }
        const normalized = (Number(link.value || 0) - minValue) / (maxValue - minValue);
        link.value = Math.round(2 + normalized * 10);
    });

    ensureSankeyColumns(nodes);
    repairIsolatedSankeyNodes(nodes, links);

    return {
        nodes,
        links,
        selections: {},
        isAggregate: true,
    };
}

function traceFullPath(hoveredNodeId, sankeyData) {
    const upstreamIds = new Set();
    const downstreamIds = new Set();

    const getSourceIdLocal = (link) => (typeof link.source === "object" ? link.source.id : link.source);
    const getTargetIdLocal = (link) => (typeof link.target === "object" ? link.target.id : link.target);

    const upstreamQueue = [hoveredNodeId];
    while (upstreamQueue.length) {
        const current = upstreamQueue.shift();
        sankeyData.links.forEach((link) => {
            const sourceId = getSourceIdLocal(link);
            const targetId = getTargetIdLocal(link);
            if (targetId === current && !upstreamIds.has(sourceId) && sourceId !== hoveredNodeId) {
                upstreamIds.add(sourceId);
                upstreamQueue.push(sourceId);
            }
        });
    }

    const downstreamQueue = [hoveredNodeId];
    while (downstreamQueue.length) {
        const current = downstreamQueue.shift();
        sankeyData.links.forEach((link) => {
            const sourceId = getSourceIdLocal(link);
            const targetId = getTargetIdLocal(link);
            if (sourceId === current && !downstreamIds.has(targetId) && targetId !== hoveredNodeId) {
                downstreamIds.add(targetId);
                downstreamQueue.push(targetId);
            }
        });
    }

    const pathNodeIds = new Set([...upstreamIds, hoveredNodeId, ...downstreamIds]);
    const pathLinkIds = new Set();
    sankeyData.links.forEach((link) => {
        const sourceId = getSourceIdLocal(link);
        const targetId = getTargetIdLocal(link);
        if (pathNodeIds.has(sourceId) && pathNodeIds.has(targetId)) {
            pathLinkIds.add(getSankeyLinkKey(sourceId, targetId));
        }
    });

    return { pathNodeIds, pathLinkIds };
}

function forceColumnPositions(sankeyLayout, width, margins, nodeWidth) {
    if (!nodeWidth) nodeWidth = 20;
    const colWidth =
        (width - margins.left - margins.right) /
        Math.max(1, SANKEY_COLUMN_COUNT - 1);
    sankeyLayout.nodes.forEach((node) => {
        const col = Math.max(
            0,
            Math.min(SANKEY_COLUMN_COUNT - 1, Number(node.column || 0))
        );
        node.x0 = margins.left + col * colWidth;
        node.x1 = node.x0 + nodeWidth;
    });
}

function projectSankeyBottomUp(sankeyLayout, chartHeight) {
    sankeyLayout.nodes.forEach((node) => {
        node.plotX0 = Number(node.y0 || 0);
        node.plotX1 = Number(node.y1 || 0);
        node.plotY0 = chartHeight - Number(node.x1 || 0);
        node.plotY1 = chartHeight - Number(node.x0 || 0);
    });

    sankeyLayout.links.forEach((link) => {
        link.plotX0 = Number(link.y0 || 0);
        link.plotX1 = Number(link.y1 || 0);
        link.plotY0 = chartHeight - Number(link.source?.x1 || 0);
        link.plotY1 = chartHeight - Number(link.target?.x0 || 0);
    });
}

function sankeyLinkVerticalPath(link) {
    const x0 = Number(link.plotX0 || 0);
    const y0 = Number(link.plotY0 || 0);
    const x1 = Number(link.plotX1 || 0);
    const y1 = Number(link.plotY1 || 0);
    const yMid = y0 + ((y1 - y0) * 0.5);
    return `M${x0},${y0}C${x0},${yMid} ${x1},${yMid} ${x1},${y1}`;
}
function verticalSankeyLinkPath(link) {
    const sx = Number(link._vx0 || 0);
    const sy = Number(link._vy0 || 0);
    const tx = Number(link._vx1 || 0);
    const ty = Number(link._vy1 || 0);
    const midY = sy + (ty - sy) * 0.5;
    return `M${sx},${sy} C${sx},${midY} ${tx},${midY} ${tx},${ty}`;
}
function fitSankeySceneToViewport(sceneSel, chartWidth, chartHeight, padding) {
    if (!padding && padding !== 0) padding = 12;
    const sceneNode = sceneSel?.node?.();
    if (!sceneNode || typeof sceneNode.getBBox !== "function") return;

    const bbox = sceneNode.getBBox();
    if (
        !Number.isFinite(bbox.width) ||
        !Number.isFinite(bbox.height) ||
        bbox.width <= 0 ||
        bbox.height <= 0
    )
        return;

    const innerW = Math.max(1, chartWidth - padding * 2);
    const innerH = Math.max(1, chartHeight - padding * 2);
    const scale = Math.min(innerW / bbox.width, innerH / bbox.height);
    if (!Number.isFinite(scale) || scale <= 0) return;

    const tx =
        padding + (innerW - bbox.width * scale) / 2 - bbox.x * scale;
    const ty =
        padding + (innerH - bbox.height * scale) / 2 - bbox.y * scale;
    sceneSel.attr("transform", `translate(${tx},${ty}) scale(${scale})`);
}

function closeSankeyFloatingPanel() {
    if (typeof sankeyFloatingPanelCleanup === "function") {
        sankeyFloatingPanelCleanup();
    }
    sankeyFloatingPanelCleanup = null;
}

function mountSankeyFloatingPanel(containerElement, panelEl, event) {
    closeSankeyFloatingPanel();

    panelEl.classList.add("sankey-floating-panel");
    containerElement.appendChild(panelEl);
    const rect = containerElement.getBoundingClientRect();
    const maxLeft = Math.max(8, containerElement.clientWidth - panelEl.offsetWidth - 8);
    const maxTop = Math.max(8, containerElement.clientHeight - panelEl.offsetHeight - 8);
    const left = Math.min(maxLeft, Math.max(8, event.clientX - rect.left + 10));
    const top = Math.min(maxTop, Math.max(8, event.clientY - rect.top - 20));

    panelEl.style.left = `${left}px`;
    panelEl.style.top = `${top}px`;

    const handleDocClick = (evt) => {
        if (!panelEl.contains(evt.target)) {
            closeSankeyFloatingPanel();
        }
    };
    const handleKeydown = (evt) => {
        if (evt.key === "Escape") {
            closeSankeyFloatingPanel();
        }
    };

    setTimeout(() => {
        document.addEventListener("mousedown", handleDocClick, true);
        document.addEventListener("keydown", handleKeydown, true);
    }, 0);

    sankeyFloatingPanelCleanup = () => {
        document.removeEventListener("mousedown", handleDocClick, true);
        document.removeEventListener("keydown", handleKeydown, true);
        panelEl.remove();
    };
}

function computeAlternativeCompatibility(altNode, otherSelectedNodes) {
    const sourceIds = [altNode.graphRefId, altNode.id].filter(Boolean);
    let score = 0;

    otherSelectedNodes.forEach((otherNode) => {
        const targetIds = [otherNode.graphRefId, otherNode.id].filter(Boolean);
        const strength = getStrengthFromIds(sourceIds, targetIds);
        if (Number.isFinite(strength)) score += strength;
    });

    return score;
}

function compatibilityBarColor(ratio) {
    if (ratio >= 0.66) return "#10B981";
    if (ratio >= 0.33) return "#F59E0B";
    return "#EF4444";
}

function applySelectionReplacement(currentSelections, oldNode, newNode) {
    const updated = deepClone(currentSelections || {});
    if (!updated.bottom_layer) updated.bottom_layer = {};
    if (!updated.middle_layer) updated.middle_layer = {};
    if (!updated.top_layer) updated.top_layer = {};

    if (oldNode.nodeType === "design_element") {
        const layer = oldNode.layer;
        const groupId = oldNode.groupId;
        if (!updated[layer]) updated[layer] = {};

        if (groupId === "visual_assets") {
            const payload = (newNode.payload && typeof newNode.payload === "object")
                ? deepClone(newNode.payload)
                : null;
            updated[layer][groupId] = payload || {
                category: newNode.groupId || "Visual Asset",
                suggestion: newNode.name,
                keywords: newNode.name,
            };
            return updated;
        }

        if (groupId === "color_scheme") {
            const palettePayload = normalizePalettePayload(newNode.payload || {}, newNode.name);
            updated[layer][groupId] = palettePayload || newNode.name;
            return updated;
        }

        updated[layer][groupId] = newNode.name;
        return updated;
    }

    if (oldNode.nodeType === "palette") {
        const palettePayload = normalizePalettePayload(newNode.payload || {}, newNode.name);
        updated.middle_layer.color_scheme = palettePayload || newNode.name;
        return updated;
    }

    return updated;
}

function replaceNodeAndRegenerate(oldNode, newNode, galleryItem, context = {}) {
    if (!galleryItem) return;
    const baseSelections = getGalleryWorkingSelections(galleryItem);
    const newSelections = applySelectionReplacement(baseSelections, oldNode, newNode);
    galleryItem.pendingSelections = newSelections;
    galleryItem.isPendingRegenerate = true;
    galleryItem.regenerateError = "";

    if (!galleryItem.analysisSnapshot) {
        galleryItem.analysisSnapshot = getAnalysisContextForGalleryItem(galleryItem);
    }
    if (oldNode.nodeType === "palette") {
        const palettePayload = normalizePalettePayload(newNode.payload || {}, newNode.name);
        galleryItem.analysisSnapshot.paletteMeta = palettePayload || galleryItem.analysisSnapshot.paletteMeta || null;
    }

    if (context.containerElement) {
        const nodeEl = Array.from(context.containerElement.querySelectorAll("[data-node-id]"))
            .find((el) => el.getAttribute("data-node-id") === oldNode.id);
        if (nodeEl) nodeEl.classList.add("sankey-node-removing");
        context.containerElement.querySelectorAll(".sankey-link").forEach((linkEl) => {
            linkEl.classList.add("sankey-link-morphing");
        });
    }

    closeSankeyFloatingPanel();
    setTimeout(() => {
        renderGalleryUI();
    }, 220);
}

function hexToHsl(hex) {
    const rgb = rgbTripletFromHex(hex);
    if (!rgb) return null;
    const [rRaw, gRaw, bRaw] = rgb;
    const r = rRaw / 255;
    const g = gRaw / 255;
    const b = bRaw / 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const delta = max - min;

    let h = 0;
    if (delta !== 0) {
        if (max === r) h = ((g - b) / delta) % 6;
        else if (max === g) h = ((b - r) / delta) + 2;
        else h = ((r - g) / delta) + 4;
        h = Math.round(h * 60);
        if (h < 0) h += 360;
    }

    const l = (max + min) / 2;
    const s = delta === 0 ? 0 : delta / (1 - Math.abs(2 * l - 1));
    return { h, s, l };
}

function computePaletteHarmonyScore(hexPalette) {
    const colors = (hexPalette || []).map(hexToHsl).filter(Boolean);
    if (colors.length < 2) return 1;

    let matched = 0;
    let total = 0;
    for (let i = 0; i < colors.length; i += 1) {
        for (let j = i + 1; j < colors.length; j += 1) {
            total += 1;
            const diffRaw = Math.abs(colors[i].h - colors[j].h);
            const diff = Math.min(diffRaw, 360 - diffRaw);
            const isComplementary = Math.abs(diff - 180) < 15;
            const isTriadic = Math.abs(diff - 120) < 15;
            const isAnalogous = diff < 30;
            const isSplitComplementary = Math.abs(diff - 150) < 15;
            if (isComplementary || isTriadic || isAnalogous || isSplitComplementary) {
                matched += 1;
            }
        }
    }

    return total === 0 ? 1 : matched / total;
}

function editPaletteNode(paletteNode, event, context) {
    const containerElement = context.containerElement;
    if (!containerElement) return;

    const initialHexPalette = paletteHexListFromPayload(paletteNode.payload).slice(0, 5);
    const currentHexPalette = (initialHexPalette.length ? initialHexPalette : ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"])
        .map((hex) => (hex && /^#[0-9A-Fa-f]{6}$/.test(hex) ? hex.toUpperCase() : "#3B82F6"));

    const panel = document.createElement("div");
    panel.className = "sankey-palette-panel";

    const title = document.createElement("div");
    title.className = "sankey-panel-title";
    title.textContent = "编辑配色";
    panel.appendChild(title);

    const swatchWrap = document.createElement("div");
    swatchWrap.className = "sankey-palette-editor";
    panel.appendChild(swatchWrap);

    const harmonyText = document.createElement("div");
    harmonyText.className = "sankey-harmony-text";
    panel.appendChild(harmonyText);

    const divider = document.createElement("div");
    divider.className = "sankey-panel-divider";
    divider.textContent = "— 或选择预设 —";
    panel.appendChild(divider);

    const presetWrap = document.createElement("div");
    presetWrap.className = "sankey-palette-presets";
    panel.appendChild(presetWrap);

    const actionRow = document.createElement("div");
    actionRow.className = "sankey-panel-actions";
    panel.appendChild(actionRow);

    const confirmBtn = document.createElement("button");
    confirmBtn.className = "sankey-panel-btn primary";
    confirmBtn.textContent = "应用";
    actionRow.appendChild(confirmBtn);

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "sankey-panel-btn";
    cancelBtn.textContent = "取消";
    actionRow.appendChild(cancelBtn);

    const refreshHarmony = () => {
        const score = computePaletteHarmonyScore(currentHexPalette);
        harmonyText.textContent = `Harmony: ${score.toFixed(3)}`;
    };

    const renderSwatches = () => {
        swatchWrap.innerHTML = "";
        currentHexPalette.forEach((hex, index) => {
            const slot = document.createElement("label");
            slot.className = "sankey-palette-slot";

            const box = document.createElement("span");
            box.className = "sankey-palette-slot-color";
            box.style.background = hex;
            slot.appendChild(box);

            const picker = document.createElement("input");
            picker.type = "color";
            picker.value = hex;
            picker.addEventListener("input", () => {
                currentHexPalette[index] = picker.value.toUpperCase();
                box.style.background = currentHexPalette[index];
                refreshHarmony();
            });
            slot.appendChild(picker);
            swatchWrap.appendChild(slot);
        });
        refreshHarmony();
    };

    const presets = getPaletteAlternatives(paletteNode.id);
    if (!presets.length) {
        const empty = document.createElement("div");
        empty.className = "sankey-empty-text";
        empty.textContent = "没有可用预设";
        presetWrap.appendChild(empty);
    } else {
        presets.forEach((preset) => {
            const presetPayload = normalizePalettePayload(preset.payload || {}, preset.name);
            if (!presetPayload) return;
            const hexes = paletteHexListFromPayload(presetPayload).slice(0, 5);
            if (!hexes.length) return;

            const row = document.createElement("button");
            row.type = "button";
            row.className = "sankey-preset-row";
            row.innerHTML = `
                <span class="sankey-preset-name">${escapeHtml(shortSankeyLabel(preset.name, 14))}</span>
                <span class="sankey-preset-swatches">${hexes.map((hex) => `<i style="background:${hex}"></i>`).join("")}</span>
            `;
            row.addEventListener("click", () => {
                for (let i = 0; i < Math.min(5, hexes.length); i += 1) {
                    currentHexPalette[i] = hexes[i].toUpperCase();
                }
                renderSwatches();
            });
            presetWrap.appendChild(row);
        });
    }

    confirmBtn.addEventListener("click", () => {
        const paletteTriplets = currentHexPalette
            .map((hex) => rgbTripletFromHex(hex))
            .filter(Boolean);
        const harmonyScore = computePaletteHarmonyScore(currentHexPalette);
        replaceNodeAndRegenerate(paletteNode, {
            id: getSankeySafeId(["palette_custom", Date.now()]),
            name: "Custom Palette",
            nodeType: "palette",
            payload: {
                type: "palette",
                label: "Custom Palette",
                source_label: "sankey_editor",
                palette: paletteTriplets,
                harmony_score: harmonyScore,
            },
            graphRefId: "",
        }, context.galleryItem, context);
    });

    cancelBtn.addEventListener("click", () => {
        closeSankeyFloatingPanel();
    });

    renderSwatches();
    mountSankeyFloatingPanel(containerElement, panel, event);
}

function showAlternativesPanel(clickedNode, event, context) {
    const containerElement = context.containerElement;
    if (!containerElement) return;

    let alternatives = Array.isArray(clickedNode.alternatives) ? [...clickedNode.alternatives] : [];
    if (!alternatives.length) {
        alternatives = getAlternativesForNode(clickedNode.layer, clickedNode.groupId, clickedNode.id);
    }
    if (!alternatives.length) {
        const panel = document.createElement("div");
        panel.className = "sankey-alternatives-panel";
        panel.innerHTML = `
            <div class="sankey-panel-title">替换: ${escapeHtml(clickedNode.groupId)}</div>
            <div class="sankey-empty-text">暂无可替换候选</div>
        `;
        mountSankeyFloatingPanel(containerElement, panel, event);
        return;
    }

    const otherSelectedNodes = (context.sankeyData?.nodes || []).filter((node) => node.id !== clickedNode.id);
    alternatives.forEach((alt) => {
        alt.compatibilityScore = computeAlternativeCompatibility(alt, otherSelectedNodes);
    });
    alternatives.sort((a, b) => Number(b.compatibilityScore || 0) - Number(a.compatibilityScore || 0));

    const maxScore = Math.max(0.0001, ...alternatives.map((alt) => Number(alt.compatibilityScore || 0)));
    const panel = document.createElement("div");
    panel.className = "sankey-alternatives-panel";

    const title = document.createElement("div");
    title.className = "sankey-panel-title";
    title.textContent = `替换: ${clickedNode.groupId}`;
    panel.appendChild(title);

    const list = document.createElement("div");
    list.className = "sankey-alt-list";
    panel.appendChild(list);

    alternatives.slice(0, 6).forEach((alt) => {
        const score = Number(alt.compatibilityScore || 0);
        const ratio = Math.max(0, Math.min(1, score / maxScore));
        const row = document.createElement("div");
        row.className = "sankey-alt-row";
        row.innerHTML = `
            <div class="sankey-alt-score"><span style="width:${Math.round(ratio * 100)}%; background:${compatibilityBarColor(ratio)};"></span></div>
            <div class="sankey-alt-name">${escapeHtml(shortSankeyLabel(alt.name, 10))}</div>
            <button type="button" class="sankey-alt-pick" aria-label="pick">→</button>
        `;
        row.querySelector(".sankey-alt-pick")?.addEventListener("click", () => {
            replaceNodeAndRegenerate(clickedNode, alt, context.galleryItem, context);
        });
        list.appendChild(row);
    });

    mountSankeyFloatingPanel(containerElement, panel, event);
}

function renderSankeyDiagram(
    containerElement,
    galleryItem,
    analysisContext,
    options = {}
) {
    if (!containerElement) return;
    closeSankeyFloatingPanel();
    containerElement.innerHTML = "";

    if (typeof d3 === "undefined" || typeof d3.sankey !== "function") {
        containerElement.innerHTML =
            '<div class="center-msg">d3-sankey not loaded</div>';
        return;
    }

    const isAggregate = Boolean(options.aggregate);
    const sankeySource = isAggregate
        ? aggregateSankeyData(galleryData, analysisContext)
        : buildSankeyData(galleryItem, analysisContext);

    if (!sankeySource.nodes.length || !sankeySource.links.length) {
        containerElement.innerHTML =
            '<div class="center-msg">No Sankey data</div>';
        return;
    }

    // ── Measure container ──
    const measuredWidth = Math.floor(
        containerElement.clientWidth ||
            containerElement.getBoundingClientRect().width ||
            0
    );
    const measuredHeight = Math.floor(
        containerElement.clientHeight ||
            containerElement.getBoundingClientRect().height ||
            0
    );

    if (measuredWidth < 40 || measuredHeight < 40) {
        containerElement.innerHTML =
            '<div class="center-msg">Sankey preparing layout…</div>';
        requestAnimationFrame(() => {
            const nw = Math.floor(containerElement.clientWidth || 0);
            const nh = Math.floor(containerElement.clientHeight || 0);
            if (nw >= 40 && nh >= 40)
                renderSankeyDiagram(
                    containerElement,
                    galleryItem,
                    analysisContext,
                    options
                );
        });
        return;
    }

    const viewW = Math.max(320, measuredWidth);
    const viewH = Math.max(240, measuredHeight);

    // ── Internal layout canvas (horizontal d3-sankey, then rotated to bottom-to-top)
    //
    //  d3-sankey computes in horizontal orientation:
    //    x-axis = column direction  → becomes VERTICAL after flip
    //    y-axis = node spread       → becomes HORIZONTAL after flip
    //
    //  So for the rotated diagram to fill viewW × viewH:
    //    pre-rotation width  (x, columns)    → viewH (vertical extent)
    //    pre-rotation height (y, node spread) → viewW (horizontal extent)
    const layoutW = viewH;   // column spacing axis → becomes vertical
    const layoutH = viewW;   // node spread axis    → becomes horizontal

    const nodesPerCol = Array.from(
        { length: SANKEY_COLUMN_COUNT },
        () => 0
    );
    sankeySource.nodes.forEach((n) => {
        const c = Math.max(
            0,
            Math.min(SANKEY_COLUMN_COUNT - 1, Number(n.column || 0))
        );
        nodesPerCol[c] += 1;
    });
    const maxNodesInCol = Math.max(1, ...nodesPerCol);

    // nodeWidth = thickness of each column band in flow direction
    //   → after rotation this becomes the vertical height of each layer band
    const nodeWidth = Math.max(
        16,
        Math.min(36, Math.floor(viewH / 24))
    );

    // Margins (in pre-rotation coords):
    //   left/right  → bottom/top of rotated view (column direction)
    //   top/bottom  → left/right of rotated view (node spread)
    const titleGutter = 42;   // room for column title text on the left
    const margins = {
        left: 10,              // bottom margin in rotated view
        right: 10,             // top margin in rotated view
        bottom: 6,             // right margin in rotated view
        top: titleGutter,      // left margin in rotated view (for column titles)
    };

    const innerW = Math.max(100, layoutH - margins.top - margins.bottom);
    const nodePad = Math.max(
        8,
        Math.min(28, Math.floor(innerW / (maxNodesInCol + 1)))
    );

    // ── SVG ──
    const svg = d3
        .select(containerElement)
        .append("svg")
        .attr("class", "sankey-svg sankey-vertical")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", `0 0 ${viewW} ${viewH}`)
        .attr("preserveAspectRatio", "xMidYMid meet");

    const defs = svg.append("defs");

    // Clean white background
    svg.append("rect")
        .attr("width", viewW)
        .attr("height", viewH)
        .attr("fill", "#FCFCFD")
        .attr("rx", 4);

    const root = svg.append("g").attr("class", "sankey-scene");

    // ── d3-sankey layout (horizontal) ──
    const sankeyGenerator = d3
        .sankey()
        .nodeId((d) => d.id)
        .nodeWidth(nodeWidth)
        .nodePadding(nodePad)
        .nodeAlign((node) =>
            Math.max(
                0,
                Math.min(
                    SANKEY_COLUMN_COUNT - 1,
                    Number(node.column || 0)
                )
            )
        )
        .nodeSort((a, b) => {
            if (a.column !== b.column) return a.column - b.column;
            return Number(b.value || 0) - Number(a.value || 0);
        })
        .extent([
            [margins.left, margins.top],
            [layoutW - margins.right, layoutH - margins.bottom],
        ]);

    const sankeyInput = {
        nodes: sankeySource.nodes.map((n) => ({ ...deepClone(n) })),
        links: sankeySource.links.map((l) => ({ ...deepClone(l) })),
    };

    const sankeyLayout = sankeyGenerator(sankeyInput);

    // Force evenly-spaced columns (horizontal positions)
    forceColumnPositions(sankeyLayout, layoutW, margins, nodeWidth);
    if (typeof sankeyGenerator.update === "function") {
        sankeyGenerator.update(sankeyLayout);
    }

    // ─────────────────────────────────────────────────────────
    //  TRANSFORM: Horizontal → Bottom-to-Top (Vertical)
    //
    //  Original (horizontal d3-sankey):
    //    x0,x1 → column position (left–right)
    //    y0,y1 → node spread within column (top–bottom)
    //
    //  After transform:
    //    vx0,vx1 → horizontal spread (was y0,y1)
    //    vy0,vy1 → vertical position, flipped (column 0 at BOTTOM)
    // ─────────────────────────────────────────────────────────
    const transformH = layoutW; // flip across the column axis (pre-rotation x = layoutW)

    sankeyLayout.nodes.forEach((node) => {
        node.vx0 = node.y0;
        node.vx1 = node.y1;
        node.vy0 = transformH - node.x1; // top edge (in screen coords)
        node.vy1 = transformH - node.x0; // bottom edge
    });

    // For links: compute vertical exit/entry points
    sankeyLayout.links.forEach((link) => {
        // link.y0 = y-pos where link exits source (horiz layout)
        // link.y1 = y-pos where link enters target
        // After transform, these become x positions
        link._vx0 = link.y0; // exit x
        link._vy0 = transformH - link.source.x1; // exit y (bottom of source in horiz = top after flip)
        link._vx1 = link.y1; // entry x
        link._vy1 = transformH - link.target.x0; // entry y (top of target in horiz = bottom after flip)
    });

    // ── Adaptive flow widths ──
    const rawWidths = sankeyLayout.links
        .map((l) => Number(l.width || l.value || 1))
        .filter((w) => Number.isFinite(w) && w > 0);
    const wMin = rawWidths.length ? Math.min(...rawWidths) : 1;
    const wMax = rawWidths.length ? Math.max(...rawWidths) : 1;
    const vScale = Math.max(
        0.85,
        Math.min(1.6, Math.min(viewW, viewH) / 400)
    );
    const flowMin = 2.5 * vScale;
    const flowMax = 20 * vScale;

    function adaptiveFlowWidth(link) {
        const raw = Number(link.width || link.value || 1);
        const s = Math.max(
            0,
            Math.min(1, Number(link.strength || 0.5))
        );
        if (!Number.isFinite(raw)) return flowMin;
        if (wMax <= wMin) {
            return Math.max(
                flowMin,
                Math.min(flowMax, raw * vScale * (0.9 + s * 0.3))
            );
        }
        const ratio = Math.pow((raw - wMin) / (wMax - wMin), 0.78);
        const wByVal = flowMin + (flowMax - flowMin) * ratio;
        return Math.max(
            flowMin,
            Math.min(flowMax * 1.25, wByVal * (0.9 + s * 0.35))
        );
    }

    // ── Gradients (vertical) ──
    sankeyLayout.links.forEach((link, idx) => {
        const srcCol = Number(link.source?.column || 0);
        const tgtCol = Number(link.target?.column || 0);
        const srcColor =
            link.source?.color || getSankeyColumnColor(srcCol, link.source?.payload);
        const tgtColor =
            link.target?.color || getSankeyColumnColor(tgtCol, link.target?.payload);
        const srcSoft = softenHexColor(srcColor, 0.32);
        const tgtSoft = softenHexColor(tgtColor, 0.32);

        const gid = `sankey-vgrad-${galleryItem?.id || "agg"}-${idx}`;
        link._gradientId = gid;
        link._linkKey = getSankeyLinkKey(link.source.id, link.target.id);

        // Vertical gradient (top → bottom corresponds to source → target)
        const grad = defs
            .append("linearGradient")
            .attr("id", gid)
            .attr("gradientUnits", "userSpaceOnUse")
            .attr("x1", link._vx0)
            .attr("y1", link._vy0)
            .attr("x2", link._vx1)
            .attr("y2", link._vy1);

        grad.append("stop")
            .attr("offset", "0%")
            .attr("stop-color", srcSoft)
            .attr("stop-opacity", 0.72);
        grad.append("stop")
            .attr("offset", "100%")
            .attr("stop-color", tgtSoft)
            .attr("stop-opacity", 0.72);
    });

    // ── Column background bands & titles ──
    const colInfo = {};
    const globalMinVx = Math.min(...sankeyLayout.nodes.map((n) => n.vx0));
    const globalMaxVx = Math.max(...sankeyLayout.nodes.map((n) => n.vx1));

    for (let col = 0; col < SANKEY_COLUMN_COUNT; col++) {
        const colNodes = sankeyLayout.nodes.filter(
            (n) => Number(n.column || 0) === col
        );
        if (!colNodes.length) continue;
        const minVy = Math.min(...colNodes.map((n) => n.vy0));
        const maxVy = Math.max(...colNodes.map((n) => n.vy1));
        colInfo[col] = { centerY: (minVy + maxVy) / 2, minVy, maxVy };
    }

    // Subtle colored background bands for each layer
    const bandLayer = root.append("g").attr("class", "sankey-column-bands");
    Object.entries(colInfo).forEach(([colStr, info]) => {
        const col = Number(colStr);
        const bandColor = SANKEY_COLUMN_COLORS[col] || "#ccc";
        const bandPad = 5;
        bandLayer
            .append("rect")
            .attr("x", globalMinVx - 10)
            .attr("y", info.minVy - bandPad)
            .attr("width", globalMaxVx - globalMinVx + 20)
            .attr("height", info.maxVy - info.minVy + bandPad * 2)
            .attr("fill", bandColor)
            .attr("fill-opacity", 0.06)
            .attr("rx", 4)
            .attr("ry", 4);
    });

    // Column title text (left side of the diagram)
    const titleLayer = root
        .append("g")
        .attr("class", "sankey-column-titles-v");

    Object.entries(colInfo).forEach(([colStr, info]) => {
        const col = Number(colStr);
        const fullTitle = SANKEY_COLUMN_TITLES[col] || `Col ${col}`;
        const title = fullTitle.split("(")[0].trim();
        const labelColor = SANKEY_COLUMN_COLORS[col] || "#8a8f99";
        titleLayer
            .append("text")
            .attr("x", globalMinVx - 14)
            .attr("y", info.centerY)
            .attr("text-anchor", "end")
            .attr("dominant-baseline", "middle")
            .attr("fill", labelColor)
            .attr("font-size", "10px")
            .attr("font-weight", "700")
            .attr("letter-spacing", "0.5px")
            .attr("opacity", 0.85)
            .text(title);
    });

    // ── Draw links (vertical bezier) ──
    const linkSel = root
        .append("g")
        .attr("fill", "none")
        .selectAll("path")
        .data(sankeyLayout.links)
        .join("path")
        .attr("class", "sankey-link")
        .attr("d", verticalSankeyLinkPath)
        .attr("stroke", (d) => `url(#${d._gradientId})`)
        .attr("stroke-opacity", 0.55)
        .attr("stroke-width", (d) => adaptiveFlowWidth(d))
        .attr("stroke-linecap", "round");

    // ── Draw nodes ──
    const nodeSel = root
        .append("g")
        .selectAll("g")
        .data(sankeyLayout.nodes, (d) => d.id)
        .join("g")
        .attr(
            "class",
            (d) =>
                `sankey-node ${
                    d.isEditable && !isAggregate
                        ? "is-editable"
                        : "is-readonly"
                }`
        )
        .attr("data-node-id", (d) => d.id)
        .on("mouseenter", (_, hovered) => {
            const traced = traceFullPath(hovered.id, sankeyLayout);
            nodeSel.classed(
                "is-path",
                (n) => traced.pathNodeIds.has(n.id)
            );
            nodeSel.classed(
                "is-dim",
                (n) => !traced.pathNodeIds.has(n.id)
            );
            linkSel.classed(
                "is-path",
                (l) => traced.pathLinkIds.has(l._linkKey)
            );
            linkSel.classed(
                "is-dim",
                (l) => !traced.pathLinkIds.has(l._linkKey)
            );
        })
        .on("mouseleave", () => {
            nodeSel
                .classed("is-path", false)
                .classed("is-dim", false);
            linkSel
                .classed("is-path", false)
                .classed("is-dim", false);
        })
        .on("click", (event, node) => {
            event.stopPropagation();
            if (isAggregate || !node.isEditable) return;
            const ctx = {
                galleryItem,
                analysisContext,
                sankeyData: sankeyLayout,
                containerElement,
            };
            if (node.nodeType === "palette") {
                editPaletteNode(node, event, ctx);
            } else {
                showAlternativesPanel(node, event, ctx);
            }
        });

    // Node rectangles (using transformed coords)
    nodeSel
        .append("rect")
        .attr("class", "sankey-node-shape")
        .attr("x", (d) => d.vx0)
        .attr("y", (d) => d.vy0)
        .attr("width", (d) => Math.max(8, d.vx1 - d.vx0))
        .attr("height", (d) => Math.max(4, d.vy1 - d.vy0))
        .attr("rx", 3)
        .attr("ry", 3)
        .attr(
            "fill",
            (d) =>
                d.color ||
                getSankeyColumnColor(
                    Number(d.column || 0),
                    d.payload
                )
        )
        .attr("fill-opacity", 0.88)
        .attr("stroke", "rgba(255,255,255,0.5)")
        .attr("stroke-width", 0.6)
        .classed(
            "sankey-output-pending",
            (d) =>
                Boolean(
                    !isAggregate &&
                        d.nodeType === "output" &&
                        galleryItem?.isPendingRegenerate
                )
        );

    // Pencil icon for editable nodes
    nodeSel
        .filter((d) => d.isEditable && !isAggregate)
        .append("path")
        .attr("class", "sankey-pencil")
        .attr("d", (d) => {
            const cx = (d.vx0 + d.vx1) / 2;
            const cy = (d.vy0 + d.vy1) / 2;
            return `M${cx - 3},${cy - 5} l4,-2 l2,2 l-4,2 z`;
        });

    // ── Auto-fit scene into viewport ──
    fitSankeySceneToViewport(root, viewW, viewH, 8);

    // ── Hover tooltip (HTML overlay, no static labels on nodes) ──
    const tooltipEl = document.createElement("div");
    tooltipEl.className = "sankey-node-tooltip";
    tooltipEl.style.display = "none";
    containerElement.appendChild(tooltipEl);

    const typeLabels = {
        data_insight: "洞察",
        design_element: "设计元素",
        palette: "配色",
        output: "输出",
    };

    nodeSel
        .on("mousemove.tooltip", (event) => {
            const rect = containerElement.getBoundingClientRect();
            let tx = event.clientX - rect.left + 14;
            let ty = event.clientY - rect.top - 40;
            // Keep within container bounds
            if (tx + 180 > containerElement.clientWidth) tx -= 180;
            if (ty < 4) ty = event.clientY - rect.top + 14;
            tooltipEl.style.left = `${tx}px`;
            tooltipEl.style.top = `${ty}px`;
        });

    // Augment existing mouseenter/mouseleave to also drive tooltip
    nodeSel.each(function (d) {
        const el = d3.select(this);
        const origEnter = el.on("mouseenter");
        const origLeave = el.on("mouseleave");

        el.on("mouseenter.tooltip", (event, datum) => {
            const typeLabel = typeLabels[datum.nodeType] || datum.nodeType || "";
            tooltipEl.innerHTML =
                `<div>${datum.name}</div>` +
                (typeLabel ? `<div class="tooltip-type">${typeLabel}</div>` : "");
            tooltipEl.style.display = "block";
        });
        el.on("mouseleave.tooltip", () => {
            tooltipEl.style.display = "none";
        });
    });

    // ── Click to close floating panels ──
    if (!isAggregate) {
        d3.select(containerElement).on("click", () => {
            closeSankeyFloatingPanel();
        });
    }
}


function renderGalleryUI() {
    const tabsContainer = document.getElementById("galleryTabs");
    const viewContainer = document.getElementById("galleryView");
    if (!tabsContainer || !viewContainer) return;

    closeSankeyFloatingPanel();

    if (!galleryData.length) {
        galleryViewMode = "single";
        activeGalleryIndex = 0;
        tabsContainer.innerHTML = "";
        viewContainer.innerHTML = '<div class="center-msg">Generated infographics will appear here</div>';
        const designActionsEl = document.getElementById("designGalleryActions");
        if (designActionsEl) designActionsEl.innerHTML = "";
        if (isDesignTabActive()) {
            requestAnimationFrame(() => {
                renderDesignSankey();
            });
        }
        return;
    }

    if (activeGalleryIndex >= galleryData.length) {
        activeGalleryIndex = galleryData.length - 1;
    }
    if (activeGalleryIndex < 0) activeGalleryIndex = 0;

    const itemTabs = galleryData
        .map((item, idx) => {
            const active = idx === activeGalleryIndex;
            return `<div class="gallery-tab ${active ? "active" : ""}" onclick="switchGalleryTab(${idx})">Scheme ${galleryData.length - idx}</div>`;
        })
        .join("");
    tabsContainer.innerHTML = itemTabs;

    galleryViewMode = "single";
    const activeItem = galleryData[activeGalleryIndex];
    const canRegenerate = Boolean(activeItem?.pendingSelections && activeItem?.isPendingRegenerate);
    const regenerateText = activeItem?.isRegenerating
        ? "Regenerating..."
        : (activeItem?.regenerateError ? "Retry Regenerate" : "Regenerate");

    // Image only in gallery view
    viewContainer.innerHTML = `
        <div class="gallery-item">
            <div class="gallery-img-container">
                <img src="${activeItem.imgUrl}" class="gallery-img" alt="poster">
            </div>
        </div>
    `;

    // Action buttons live in the Design tab's top bar
    const designActionsEl = document.getElementById("designGalleryActions");
    if (designActionsEl) {
        designActionsEl.innerHTML =
            `<a href="${activeItem.imgUrl}" download="infographic_${activeItem.id}.png" class="gallery-action-link">Download</a>` +
            `<button class="gallery-action-btn ${canRegenerate ? "primary" : ""}" ${(!canRegenerate || activeItem?.isRegenerating) ? "disabled" : ""} onclick="regenerateGalleryItem(${activeGalleryIndex})">${regenerateText}</button>` +
            (canRegenerate ? `<button class="gallery-action-btn" onclick="revertGalleryPending(${activeGalleryIndex})">Undo</button>` : "");
    }

    if (isDesignTabActive()) {
        requestAnimationFrame(() => {
            renderDesignSankey();
        });
    }
}

function addToGallery(imgUrl, usedSelections) {
    galleryData.unshift({
        id: Date.now(),
        imgUrl,
        selections: deepClone(usedSelections || {}),
        pendingSelections: null,
        isPendingRegenerate: false,
        isRegenerating: false,
        regenerateError: "",
        analysisSnapshot: {
            query: document.getElementById("queryInput")?.value || "",
            description: document.getElementById("tableDesc")?.value || "",
            analysisAnswer: currentAnalysisAnswer || "",
            chartData: currentChartData ? deepClone(currentChartData) : null,
            paletteMeta: selectedPaletteMeta ? deepClone(selectedPaletteMeta) : null,
        },
    });

    galleryViewMode = "single";
    activeGalleryIndex = 0;
    renderGalleryUI();
    saveSession();
}

window.switchGalleryTab = function(index) {
    galleryViewMode = "single";
    activeGalleryIndex = Math.max(0, Math.min(galleryData.length - 1, Number(index) || 0));
    renderGalleryUI();
};

window.switchGalleryAggregate = function() {
    if (!galleryData.length) return;
    galleryViewMode = "single";
    activeGalleryIndex = 0;
    renderGalleryUI();
};

async function regenerateGalleryItem(index) {
    const item = galleryData[index];
    if (!item) return;

    const pendingSelections = item.pendingSelections ? deepClone(item.pendingSelections) : null;
    if (!pendingSelections) {
        alert("No pending changes to regenerate.");
        return;
    }

    const context = getAnalysisContextForGalleryItem(item);
    item.isRegenerating = true;
    item.regenerateError = "";
    renderGalleryUI();

    try {
        const res = await fetch("/infographic/generate_final", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                selections: pendingSelections,
                chart_source: context.chartData,
                description: context.description || "",
                query: context.query || "",
                analysis_result: context.analysisAnswer || "",
            }),
        });

        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.error || "Regenerate failed");
        }

        item.imgUrl = data.image_url;
        item.selections = deepClone(pendingSelections);
        item.pendingSelections = null;
        item.isPendingRegenerate = false;
        item.regenerateError = "";
    } catch (err) {
        item.regenerateError = String(err);
        alert(`Regenerate error: ${err}`);
    } finally {
        item.isRegenerating = false;
        renderGalleryUI();
    }
}

window.regenerateGalleryItem = regenerateGalleryItem;

window.revertGalleryPending = function(index) {
    const item = galleryData[index];
    if (!item) return;
    item.pendingSelections = null;
    item.isPendingRegenerate = false;
    item.regenerateError = "";
    renderGalleryUI();
};

// ── Session persistence ──────────────────────────────────────────────────────

async function saveSession() {
    try {
        const session = {
            saved_at: new Date().toISOString(),
            filepath: currentFilePath,
            schema_meta: currentSchemaMeta ? deepClone(currentSchemaMeta) : null,
            table_description: document.getElementById("tableDesc")?.value || "",
            query: document.getElementById("queryInput")?.value || "",
            analysis_answer: currentAnalysisAnswer,
            chart_data: currentChartData ? deepClone(currentChartData) : null,
            graph_bundle: graphBundle ? deepClone(graphBundle) : null,
            som_step: somStep,
            som_selections: deepClone(somSelections),
            selected_nodes: deepClone(selectedNodes),
            selected_color_node_id: selectedColorNodeId,
            selected_palette_meta: selectedPaletteMeta ? deepClone(selectedPaletteMeta) : null,
            extracted_palette_results: deepClone(extractedPaletteResults),
            current_ref_image_path: currentRefImagePath,
            gallery_data: deepClone(galleryData),
        };
        await fetch("/session/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(session),
        });
    } catch (e) {
        console.warn("Session save failed:", e);
    }
}

async function restoreSession() {
    try {
        const res = await fetch("/session/load");
        const data = await res.json();
        if (data.status !== "success" || !data.session) return;

        const s = data.session;

        // Restore file path
        if (s.filepath) {
            currentFilePath = s.filepath;
            document.getElementById("btnAnalyze").disabled = false;
        }

        // Restore form inputs
        if (s.table_description) {
            const descEl = document.getElementById("tableDesc");
            if (descEl) descEl.value = s.table_description;
        }
        if (s.query) {
            const queryEl = document.getElementById("queryInput");
            if (queryEl) queryEl.value = s.query;
        }

        // Restore schema table
        if (s.schema_meta) {
            renderSchema(s.schema_meta);
            switchTab(0);
        }

        // Restore analysis answer
        if (s.analysis_answer) {
            currentAnalysisAnswer = s.analysis_answer;
            const insightEl = document.getElementById("tab-insight");
            if (insightEl) {
                insightEl.innerHTML = `<div style="font-size:12px; line-height:1.5">${s.analysis_answer.replace(/\n/g, "<br>")}</div>`;
            }
        }

        // Restore chart
        if (s.chart_data) {
            currentChartData = s.chart_data;
            const spec = JSON.parse(JSON.stringify(s.chart_data));
            spec.width = "container";
            spec.height = "container";
            spec.autosize = { type: "fit", contains: "padding", resize: true };
            const visEl = document.getElementById("vis");
            if (visEl) visEl.innerHTML = "";
            vegaEmbed("#vis", spec, { actions: false, renderer: "canvas" }).catch(console.warn);
            const btnGenInfo = document.getElementById("btnGenInfo");
            if (btnGenInfo) btnGenInfo.style.display = "block";
            updateGraphActionLabels();
            switchTab(1);
        }

        // Restore graph bundle (SOM or force)
        if (s.graph_bundle && s.graph_bundle.graph_data) {
            const mode = normalizeGraphMode(s.graph_bundle.layout_mode || "som");
            applyGraphBundleByMode(s.graph_bundle, mode);

            // After applyGraphBundleByMode resets SOM state, restore saved step and selections
            if (mode === "som") {
                if (typeof s.som_step === "number" && s.som_step > 0) {
                    somStep = Math.min(s.som_step, somPhases.length - 1);
                }
                if (s.som_selections && typeof s.som_selections === "object") {
                    somSelections = s.som_selections;
                    syncSelectedNodesFromSomSelections();
                }
                renderSomStep();
            }

            if (s.selected_nodes && s.selected_nodes.length) {
                selectedNodes = s.selected_nodes;
            }
        }

        // Restore palette state
        if (s.selected_color_node_id) {
            selectedColorNodeId = s.selected_color_node_id;
            const hint = document.getElementById("paletteNodeHint");
            const colorNode = getNodeById(selectedColorNodeId);
            if (hint && colorNode) hint.textContent = colorNode.name || selectedColorNodeId;
            const generateBtn = document.getElementById("btnGeneratePaletteFromNode");
            if (generateBtn) generateBtn.disabled = false;
        }
        if (s.selected_palette_meta) {
            selectedPaletteMeta = s.selected_palette_meta;
        }
        if (Array.isArray(s.extracted_palette_results) && s.extracted_palette_results.length) {
            extractedPaletteResults = s.extracted_palette_results;
            renderPaletteOptions(extractedPaletteResults);
        }
        if (s.current_ref_image_path) {
            currentRefImagePath = s.current_ref_image_path;
            renderRefImage(currentRefImagePath).catch(console.warn);
        }

        // Restore gallery
        if (Array.isArray(s.gallery_data) && s.gallery_data.length) {
            galleryData = s.gallery_data;
            activeGalleryIndex = 0;
            renderGalleryUI();
        }

        renderDesignSummary();
        console.log(`[Session] Restored from ${s.saved_at}`);
    } catch (e) {
        console.warn("[Session] Restore failed:", e);
    }
}

// ────────────────────────────────────────────────────────────────────────────

function bindEvents() {
    // [FORCE-DISABLED] Force layout toggle button listener
    // const btnLayoutForce = document.getElementById("btnLayoutForce");
    const btnLayoutSom = document.getElementById("btnLayoutSom");
    // if (btnLayoutForce) {
    //     btnLayoutForce.addEventListener("click", () => {
    //         setGraphLayoutMode("force");
    //     });
    // }
    if (btnLayoutSom) {
        btnLayoutSom.addEventListener("click", () => {
            setGraphLayoutMode("som");
        });
    }

    document.getElementById("btnUpload").addEventListener("click", uploadCsv);
    document.getElementById("btnAnalyze").addEventListener("click", runAnalysis);
    document.getElementById("btnGenInfo").addEventListener("click", buildForceGraphPlan);
    document.getElementById("btnGenInfoFromJson").addEventListener("click", buildForceGraphFromUploadedJson);
    document.getElementById("forceJsonInput").addEventListener("change", syncForceJsonUploadState);
    const sampleInput = document.getElementById("forceSampleCountInput");
    if (sampleInput) {
        sampleInput.addEventListener("input", () => {
            getRequestedSampleCount();
            updateGraphActionLabels();
        });
        sampleInput.addEventListener("change", () => {
            getRequestedSampleCount();
            updateGraphActionLabels();
        });
    }
    const recommendedBtn = document.getElementById("btnUseRecommendedCount");
    if (recommendedBtn) {
        recommendedBtn.addEventListener("click", () => {
            const input = document.getElementById("forceSampleCountInput");
            if (!input) return;
            const limits = getForceSampleCountLimits();
            const recommended = Math.max(limits.min, Math.min(limits.max, RECOMMENDED_FORCE_SAMPLE_COUNT));
            input.value = String(recommended);
            updateGraphActionLabels();
        });
    }

    document.getElementById("btnForceReset").addEventListener("click", resetForceFlow);
    // [FORCE-DISABLED] btnForceNext — only used in force layer step navigation
    // document.getElementById("btnForceNext").addEventListener("click", nextForceStep);
    document.getElementById("btnForceGenerate").addEventListener("click", generateFinalPosterFromForceGraph);

    document.getElementById("btnGeneratePaletteFromNode").addEventListener("click", () => {
        if (!selectedColorNodeId) {
            alert(`Select a color scheme node in ${getGraphModeLabel(graphLayoutMode)} first.`);
            return;
        }
        generatePaletteFromSelectedColorNode({ reuseImage: true });
    });

    window.addEventListener("resize", () => {
        if (graphLayoutMode === "som") {
            if (somGraphData) renderSomStep();
            if (isDesignTabActive()) {
                requestAnimationFrame(() => {
                    renderDesignSankey();
                });
            }
            return;
        }
        // [FORCE-DISABLED] if (forceGraphData) renderForceStep();
        if (isDesignTabActive()) {
            requestAnimationFrame(() => {
                renderDesignSankey();
            });
        }
    });

    syncForceJsonUploadState();
    updateGraphActionLabels();
}

bindEvents();
setGraphLayoutMode(getAllowedGraphMode(GRAPH_LAYOUT_UI_SETTINGS.defaultLayoutMode), { preserveSelection: true, preservePalette: true });
renderGalleryUI();
restoreSession();
