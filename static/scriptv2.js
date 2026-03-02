let currentFilePath = "";
let currentAnalysisAnswer = "";
let currentChartData = null;

let graphBundle = null;
let fullGraphData = null;
let graphNodeMap = {};
let groupDefaults = {};
let forceNodeTooltipEl = null;

const layerOrder = ["bottom_layer", "middle_layer", "top_layer"];
let forceStep = 0;
let selectedNodes = [];

let selectedColorNodeId = "";
let selectedPaletteMeta = null;
let extractedPaletteResults = [];
let currentRefImagePath = "";

let galleryData = [];
let activeGalleryIndex = 0;
let forceGraphJobId = null;
let forceGraphProgressTimer = null;
let forceGraphPollingInFlight = false;
let forceGraphLastProgress = -1;
let forceGraphPollDelayMs = 3500;

let colorScale = null;

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

function moveForceNodeTooltip(event) {
    const tooltip = getForceNodeTooltip();
    if (tooltip.style.display === "none") return;

    const gap = 12;
    const maxX = window.innerWidth - tooltip.offsetWidth - 8;
    const maxY = window.innerHeight - tooltip.offsetHeight - 8;
    const x = Math.max(8, Math.min(maxX, event.clientX + gap));
    const y = Math.max(8, Math.min(maxY, event.clientY + gap));

    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
}

function showForceNodeTooltip(event, node) {
    const tooltip = getForceNodeTooltip();
    const desc = getNodeDescription(node);
    tooltip.innerHTML = `
        <div class="tt-title">${escapeHtml(node?.name || "Node")}</div>
        <div class="tt-row"><span>Category</span><b>${escapeHtml(node?.group || node?.group_id || "Unknown")}</b></div>
        <div class="tt-row"><span>Layer</span><b>${escapeHtml(getLayerLabel(node?.layer))}</b></div>
        <div class="tt-row"><span>Frequency</span><b>${escapeHtml(node?.val ?? "N/A")}</b></div>
        <div class="tt-row"><span>Group ID</span><b>${escapeHtml(node?.group_id || "N/A")}</b></div>
        ${desc ? `<div class="tt-desc">${escapeHtml(desc)}</div>` : ""}
    `;
    tooltip.style.display = "block";
    moveForceNodeTooltip(event);
}

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
        const statusText = `${progressData.message || "Running"} | success ${progressData.success_count || 0}/${progressData.target_count || 50}, failed ${progressData.failed_count || 0}`;
        setForceProgress(pct, statusText, true);

        if (progressData.job_status === "completed") {
            stopForceGraphPolling();
            const ok = applyForceGraphBundle(progressData.result || {});
            setForceProgress(100, ok ? "Force graph completed." : "Completed with empty graph.", true);
            toggleLoading("loading-info", false);
            document.getElementById("btnGenInfo").disabled = false;
            forceGraphJobId = null;
            return;
        }

        if (progressData.job_status === "failed") {
            stopForceGraphPolling();
            const err = progressData.error || "Force graph generation failed";
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

function applyForceGraphBundle(data) {
    graphBundle = data;
    fullGraphData = data.graph_data || { nodes: [], links: [] };
    groupDefaults = data.group_defaults || {};

    graphNodeMap = {};
    (fullGraphData.nodes || []).forEach((node) => {
        graphNodeMap[node.id] = node;
    });

    if (!fullGraphData.nodes || fullGraphData.nodes.length === 0) {
        alert("No nodes returned from force-graph planning.");
        return false;
    }

    if (Number(data.success_count || 0) < Number(data.target_count || 50)) {
        alert(`Generated ${data.success_count} valid JSON plans (target ${data.target_count || 50}).`);
    }

    initForceExplorer();
    switchTab(3);
    return true;
}

function switchTab(index) {
    document.querySelectorAll(".tab-btn").forEach((b, i) => b.classList.toggle("active", i === index));
    document.querySelectorAll(".tab-content").forEach((c, i) => c.classList.toggle("active", i === index));
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

function renderSchema(meta) {
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

function toggleForceNodeSelection(node) {
    if (!node || layerOrder[forceStep] !== node.layer) return;

    const existed = isNodeSelected(node.id);
    if (existed) {
        removeSelectedNodeById(node.id);
        renderForceStep();
        renderDesignSummary();
        return;
    }

    const sameGroupNode = selectedNodes.find((n) => n.layer === node.layer && n.group_id === node.group_id);
    if (sameGroupNode) {
        removeSelectedNodeById(sameGroupNode.id);
    }

    selectedNodes.push(node);

    if (node.group_id === "color_scheme") {
        selectedColorNodeId = node.id;
        selectedPaletteMeta = null;
        const generateBtn = document.getElementById("btnGeneratePaletteFromNode");
        if (generateBtn) generateBtn.disabled = false;
        const hint = document.getElementById("paletteNodeHint");
        if (hint) {
            const desc = node.desc ? ` | ${node.desc}` : "";
            hint.textContent = `${node.name}${desc}`;
        }
        generatePaletteFromSelectedColorNode({ reuseImage: false });
    }

    renderForceStep();
    renderDesignSummary();
}

function getSourceId(link) {
    return typeof link.source === "object" ? link.source.id : link.source;
}

function getTargetId(link) {
    return typeof link.target === "object" ? link.target.id : link.target;
}

function computeActiveGraphData() {
    if (!fullGraphData) return { nodes: [], links: [] };

    let activeNodes = [...selectedNodes];
    let candidateNodes = [];

    if (forceStep < layerOrder.length) {
        const currentLayer = layerOrder[forceStep];
        candidateNodes = fullGraphData.nodes.filter((n) => n.layer === currentLayer);

        if (forceStep > 0) {
            const pastSelectedIds = new Set(
                selectedNodes
                    .filter((n) => layerOrder.indexOf(n.layer) < forceStep)
                    .map((n) => n.id)
            );

            const validIds = new Set();
            fullGraphData.links.forEach((link) => {
                if (link.is_intra) return;
                const sId = getSourceId(link);
                const tId = getTargetId(link);
                if (pastSelectedIds.has(sId)) validIds.add(tId);
                if (pastSelectedIds.has(tId)) validIds.add(sId);
            });

            const filtered = candidateNodes.filter((n) => validIds.has(n.id));
            if (filtered.length > 0) candidateNodes = filtered;
        }

        candidateNodes.forEach((n) => {
            if (!activeNodes.some((s) => s.id === n.id)) activeNodes.push(n);
        });
    }

    const activeNodeIds = new Set(activeNodes.map((n) => n.id));

    const activeLinks = fullGraphData.links.filter((link) => {
        const sId = getSourceId(link);
        const tId = getTargetId(link);
        if (!activeNodeIds.has(sId) || !activeNodeIds.has(tId)) return false;
        if (link.is_intra) return true;

        const sourceSelected = selectedNodes.some((n) => n.id === sId);
        const targetSelected = selectedNodes.some((n) => n.id === tId);
        return sourceSelected || targetSelected;
    });

    return { nodes: activeNodes, links: activeLinks };
}

function renderForceGraph(nodes, links) {
    const container = document.getElementById("forceGraphContainer");
    if (!container) return;

    container.innerHTML = "";

    if (typeof d3 === "undefined") {
        container.innerHTML = '<div class="center-msg">D3 failed to load. Upload/analysis still works.</div>';
        return;
    }

    if (!nodes.length) {
        container.innerHTML = '<div class="center-msg">No nodes available for current step</div>';
        return;
    }

    const rect = container.getBoundingClientRect();
    const width = Math.max(600, Math.floor(rect.width));
    const height = Math.max(240, Math.floor(rect.height));

    const svg = d3.select(container)
        .append("svg")
        .attr("width", width)
        .attr("height", height);

    const root = svg.append("g");
    svg.call(d3.zoom().on("zoom", (event) => root.attr("transform", event.transform)));

    const linkSel = root.append("g")
        .selectAll("line")
        .data(links, (d) => `${getSourceId(d)}-${getTargetId(d)}`)
        .join("line")
        .attr("stroke", (d) => (d.is_intra ? "transparent" : "#b9c1cc"))
        .attr("stroke-opacity", (d) => (d.is_intra ? 0 : 0.65))
        .attr("stroke-width", (d) => (d.is_intra ? 0 : Math.max(1, Number(d.jaccard || 0) * 10)));

    const nodeSel = root.append("g")
        .selectAll("g")
        .data(nodes, (d) => d.id)
        .join((enter) => {
            const g = enter.append("g").style("cursor", "pointer");
            g.append("circle");
            g.append("text");
            return g;
        })
        .on("click", (event, d) => {
            event.stopPropagation();
            hideForceNodeTooltip();
            toggleForceNodeSelection(d);
        })
        .on("mouseover", (event, d) => {
            showForceNodeTooltip(event, d);
        })
        .on("mousemove", (event) => {
            moveForceNodeTooltip(event);
        })
        .on("mouseout", () => {
            hideForceNodeTooltip();
        });

    nodeSel.select("circle")
        .attr("r", (d) => Math.sqrt(Number(d.val || 1)) * 2.4 + 11)
        .attr("fill", (d) => colorForGroup(d.group_id || d.group || "unknown"))
        .attr("stroke", (d) => (isNodeSelected(d.id) ? "#ef4444" : "#ffffff"))
        .attr("stroke-width", (d) => (isNodeSelected(d.id) ? 4 : 2.5))
        .attr("opacity", (d) => {
            if (forceStep >= layerOrder.length) return isNodeSelected(d.id) ? 1 : 0.75;
            if (d.layer !== layerOrder[forceStep]) return 0.95;
            return isNodeSelected(d.id) ? 1 : 0.68;
        });

    nodeSel.select("text")
        .text((d) => d.name)
        .attr("y", (d) => Math.sqrt(Number(d.val || 1)) * 2.4 + 24)
        .attr("text-anchor", "middle")
        .style("font-size", "11px")
        .style("font-weight", 600)
        .style("fill", "#1f2937")
        .style("pointer-events", "none");

    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links)
            .id((d) => d.id)
            .distance((d) => (d.is_intra ? Math.max(35, 55 - Number(d.jaccard || 0) * 35) : 190))
            .strength((d) => (d.is_intra ? Math.max(0.1, Number(d.jaccard || 0) * 1.8) : Math.max(0.03, Number(d.jaccard || 0) * 0.7))))
        .force("charge", d3.forceManyBody().strength(-420))
        .force("x", d3.forceX((d) => {
            const idx = layerOrder.indexOf(d.layer);
            return (idx + 1) * (width / 4);
        }).strength(0.8))
        .force("y", d3.forceY(height / 2).strength(0.1))
        .force("collide", d3.forceCollide().radius((d) => Math.sqrt(Number(d.val || 1)) * 2.4 + 22));

    nodeSel.call(
        d3.drag()
            .on("start", (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on("drag", (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on("end", (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            })
    );

    simulation.on("tick", () => {
        linkSel
            .attr("x1", (d) => d.source.x)
            .attr("y1", (d) => d.source.y)
            .attr("x2", (d) => d.target.x)
            .attr("y2", (d) => d.target.y);

        nodeSel.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });
}

function updateForceStepUI() {
    const chips = document.querySelectorAll(".force-step-chip");
    chips.forEach((chip, index) => {
        chip.classList.remove("active", "done");
        if (index < forceStep) chip.classList.add("done");
        else if (index === forceStep) chip.classList.add("active");
    });

    const btnNext = document.getElementById("btnForceNext");
    const btnGenerate = document.getElementById("btnForceGenerate");

    if (forceStep >= layerOrder.length) {
        if (btnNext) btnNext.style.display = "none";
        if (btnGenerate) btnGenerate.style.display = "inline-block";
    } else {
        if (btnNext) btnNext.style.display = "inline-block";
        if (btnGenerate) btnGenerate.style.display = "none";
    }
}

function renderForceStep() {
    updateForceStepUI();
    const data = computeActiveGraphData();
    renderForceGraph(data.nodes, data.links);
}

function initForceExplorer() {
    forceStep = 0;
    selectedNodes = [];
    clearPaletteSelectionState();
    renderForceStep();
    renderDesignSummary();
}

function nextForceStep() {
    if (forceStep >= layerOrder.length) return;

    const currentLayer = layerOrder[forceStep];
    const count = selectedNodes.filter((n) => n.layer === currentLayer).length;
    if (count === 0) {
        alert("Please select at least one node in the current layer.");
        return;
    }

    forceStep += 1;
    renderForceStep();
    renderDesignSummary();
}

function resetForceFlow() {
    if (!fullGraphData) return;
    initForceExplorer();
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
        container.innerHTML = "Build force graph and select nodes first";
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
}

async function generateFinalPosterFromForceGraph() {
    if (!fullGraphData) {
        alert("Build force graph first.");
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

function renderGalleryUI() {
    const tabsContainer = document.getElementById("galleryTabs");
    const viewContainer = document.getElementById("galleryView");

    if (!tabsContainer || !viewContainer) return;

    if (galleryData.length === 0) {
        tabsContainer.innerHTML = "";
        viewContainer.innerHTML = '<div class="center-msg">Generated infographics will appear here</div>';
        return;
    }

    tabsContainer.innerHTML = galleryData
        .map((item, index) => `<div class="gallery-tab ${index === activeGalleryIndex ? "active" : ""}" onclick="switchGalleryTab(${index})">Scheme ${galleryData.length - index}</div>`)
        .join("");

    const activeItem = galleryData[activeGalleryIndex];
    const selections = activeItem.selections || {};

    const layerTitleMap = {
        bottom_layer: "Bottom Layer",
        middle_layer: "Middle Layer",
        top_layer: "Top Layer",
    };

    let selectionHtml = "";
    layerOrder.forEach((layer) => {
        const layerData = selections[layer] || {};
        if (!Object.keys(layerData).length) return;

        selectionHtml += `<div style="margin-bottom:10px;"><div style="font-size:11px; color:var(--primary); font-weight:700; margin-bottom:4px;">${layerTitleMap[layer]}</div>`;
        Object.entries(layerData).forEach(([key, value]) => {
            let displayValue = value;
            if (typeof value === "object" && value !== null) {
                displayValue = value.label || value.keywords || value.name || JSON.stringify(value);
            }
            selectionHtml += `<div class="info-row"><div class="info-label">${key}</div><div class="info-val">${displayValue}</div></div>`;
        });
        selectionHtml += `</div>`;
    });

    viewContainer.innerHTML = `
        <div class="gallery-item">
            <div class="gallery-img-container"><img src="${activeItem.imgUrl}" class="gallery-img" alt="poster"></div>
            <div class="gallery-info">
                <h4>Design Selections</h4>
                ${selectionHtml || '<div class="center-msg">No selection details</div>'}
                <div style="margin-top:12px;">
                    <a href="${activeItem.imgUrl}" download="infographic_${activeItem.id}.png" class="primary-btn" style="display:block; text-align:center; text-decoration:none; padding:8px;">Download</a>
                </div>
            </div>
        </div>
    `;
}

function addToGallery(imgUrl, usedSelections) {
    galleryData.unshift({
        id: Date.now(),
        imgUrl,
        selections: JSON.parse(JSON.stringify(usedSelections || {})),
    });
    activeGalleryIndex = 0;
    renderGalleryUI();
}

window.switchGalleryTab = function(index) {
    activeGalleryIndex = index;
    renderGalleryUI();
};

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
            switchTab(1);
        }
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

    stopForceGraphPolling();
    toggleLoading("loading-info", true);
    document.getElementById("btnGenInfo").disabled = true;
    setForceProgress(1, "Starting force-graph job...", true);

    try {
        const res = await fetch("/infographic/force_graph_plan/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                description: document.getElementById("tableDesc").value,
                query: document.getElementById("queryInput").value,
                analysis_result: currentAnalysisAnswer,
                chart_source: currentChartData,
                sample_count: 50,
            }),
        });
        const data = await res.json();

        if (data.status !== "success") {
            alert(data.error || "Force graph generation failed");
            toggleLoading("loading-info", false);
            document.getElementById("btnGenInfo").disabled = false;
            return;
        }
        forceGraphJobId = data.job_id;
        forceGraphLastProgress = -1;
        forceGraphPollDelayMs = 2500;
        scheduleForceGraphPolling(300);
    } catch (e) {
        alert("Force Graph Error: " + e);
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

    stopForceGraphPolling();
    forceGraphJobId = null;
    toggleLoading("loading-info-json", true);
    setForceProgress(8, `Uploading JSON: ${fileInput.files[0].name}`, true);

    const uploadBtn = document.getElementById("btnGenInfoFromJson");
    const buildBtn = document.getElementById("btnGenInfo");
    if (uploadBtn) uploadBtn.disabled = true;
    if (buildBtn) buildBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);

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

        const ok = applyForceGraphBundle(data);
        const runCount = Number(data.target_count || 0);
        if (ok) {
            const doneMsg = runCount > 0
                ? `Force graph built from uploaded JSON (${runCount} runs).`
                : "Force graph built from uploaded JSON.";
            setForceProgress(100, doneMsg, true);
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

function bindEvents() {
    document.getElementById("btnUpload").addEventListener("click", uploadCsv);
    document.getElementById("btnAnalyze").addEventListener("click", runAnalysis);
    document.getElementById("btnGenInfo").addEventListener("click", buildForceGraphPlan);
    document.getElementById("btnGenInfoFromJson").addEventListener("click", buildForceGraphFromUploadedJson);
    document.getElementById("forceJsonInput").addEventListener("change", syncForceJsonUploadState);

    document.getElementById("btnForceReset").addEventListener("click", resetForceFlow);
    document.getElementById("btnForceNext").addEventListener("click", nextForceStep);
    document.getElementById("btnForceGenerate").addEventListener("click", generateFinalPosterFromForceGraph);

    document.getElementById("btnGeneratePaletteFromNode").addEventListener("click", () => {
        if (!selectedColorNodeId) {
            alert("Select a color scheme node in force graph first.");
            return;
        }
        generatePaletteFromSelectedColorNode({ reuseImage: true });
    });

    window.addEventListener("resize", () => {
        if (fullGraphData) renderForceStep();
    });

    syncForceJsonUploadState();
}

bindEvents();
renderGalleryUI();
