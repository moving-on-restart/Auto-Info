// --- 状态变量 ---
let currentFilePath = "";
let currentAnalysisAnswer = "";
let currentChartData = null;
let currentRefImagePath = "";
let currentPlan = null;         // 存储完整的设计方案 JSON
let wizardStep = 0;             // 当前向导步骤 (0-3)
let designSelections = {};      // 存储用户的选择 {groupId: value}
let designSelectionMeta = {};   // 存储结构化选项（如调色板数据）
let generatedAssets = {};       // 缓存已生成的素材 URL {keywords: url}
let galleryData = []; // 存储历史方案 { id, imgUrl, selections }
let activeGalleryIndex = 0; // 当前查看的方案索引
let extractedPaletteResults = []; // 提取到的 palette 结果
let paletteOptionMetaByLabel = {}; // { label: palette payload }

// --- UI 工具函数 ---
function toggleLoading(id, show) {
    const el = document.getElementById(id);
    if(el) el.style.display = show ? 'block' : 'none';
}

function switchTab(index) {
    document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === index));
    document.querySelectorAll('.tab-content').forEach((c, i) => c.classList.toggle('active', i === index));
}

function switchInputMode(mode) {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.mode-panel').forEach(p => p.classList.remove('active'));

    if(mode === 'gen') {
        document.querySelector('.mode-btn:nth-child(1)').classList.add('active');
        document.getElementById('panel-gen').classList.add('active');
    } else {
        document.querySelector('.mode-btn:nth-child(2)').classList.add('active');
        document.getElementById('panel-upload').classList.add('active');
    }
}

function toHexColor(rgb) {
    if (!Array.isArray(rgb) || rgb.length < 3) return null;
    const clamp = (n) => Math.max(0, Math.min(255, Number(n) || 0));
    return "#" + [clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2])]
        .map(v => v.toString(16).padStart(2, '0'))
        .join('')
        .toUpperCase();
}

function paletteToHexPreview(palette) {
    if (!Array.isArray(palette) || palette.length === 0) return "色值: N/A";
    const hexList = palette.slice(0, 5).map(toHexColor).filter(Boolean);
    return hexList.length ? `色值: ${hexList.join(' / ')}` : "色值: N/A";
}

function buildColorSchemeOptions(baseOptions) {
    const safeBase = Array.isArray(baseOptions) ? baseOptions : [];
    paletteOptionMetaByLabel = {};

    if (!Array.isArray(extractedPaletteResults) || extractedPaletteResults.length === 0) {
        return safeBase;
    }

    const paletteOptions = extractedPaletteResults
        .filter(item => Array.isArray(item.palette) && item.palette.length > 0)
        .map((item, idx) => {
            const sourceLabel = item.label || `对象${idx + 1}`;
            const harmonyText = typeof item.harmony_score === 'number' ? item.harmony_score.toFixed(3) : 'N/A';
            const optionLabel = `调色板配色-${sourceLabel}-${idx + 1}`;

            paletteOptionMetaByLabel[optionLabel] = {
                type: 'palette',
                label: optionLabel,
                source_label: sourceLabel,
                palette: item.palette,
                harmony_score: (item.harmony_score !== undefined ? item.harmony_score : null)
            };

            return {
                value: `palette_${idx}`,
                label: optionLabel,
                desc: `来源对象: ${sourceLabel}（#${idx + 1}） | ${paletteToHexPreview(item.palette)} | Harmony: ${harmonyText}`
            };
        });

    return safeBase.concat(paletteOptions);
}

// ================= 步骤 1: 上传数据 (不变) =================
document.getElementById('btnUpload').addEventListener('click', async () => {
    const fileInput = document.getElementById('fileInput');
    if(fileInput.files.length === 0) return alert("Select CSV first");

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    toggleLoading('loading-upload', true);
    document.getElementById('btnUpload').disabled = true;

    try {
        const res = await fetch('/upload_csv', { method: 'POST', body: formData });
        const data = await res.json();
        if(data.status === 'success') {
            currentFilePath = data.filepath;
            document.getElementById('btnAnalyze').disabled = false;
            renderSchema(data.meta);
            const descBox = document.getElementById('tableDesc');
            if(data.description) {
                descBox.value = data.description;
                descBox.style.backgroundColor = "#f0fdf4";
                setTimeout(() => descBox.style.backgroundColor = "#fbfbfb", 1000);
            }
            alert("Data Loaded");
        } else { alert(data.error); }
    } catch(e) { alert("Error: " + e); }
    finally {
        toggleLoading('loading-upload', false);
        document.getElementById('btnUpload').disabled = false;
    }
});

function renderSchema(meta) {
    const container = document.getElementById('tab-schema');
    let html = `<div style="font-size:10px; color:#999; margin-bottom:15px;">${meta.rows} ROWS FOUND</div>`;
    meta.columns.forEach(col => {
        html += `<div style="margin-bottom:8px; border-bottom:1px solid #eee; padding-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-family:'JetBrains Mono'; font-size:11px; font-weight:600;">${col}</span>
                    <span class="schema-type">STR/NUM</span>
                 </div>`;
    });
    container.innerHTML = html;
}

// ================= 步骤 3: 分析与图表 (不变) =================
document.getElementById('btnAnalyze').addEventListener('click', async () => {
    const desc = document.getElementById('tableDesc').value;
    const query = document.getElementById('queryInput').value;
    if(!currentFilePath || !query) return alert("Missing data or query");

    toggleLoading('loading-analyze', true);
    document.getElementById('btnAnalyze').disabled = true;

    try {
        const res = await fetch('/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filepath: currentFilePath, description: desc, query: query })
        });
        const data = await res.json();

        if(data.status === 'success') {
            currentAnalysisAnswer = data.answer;
            document.getElementById('tab-insight').innerHTML = `<div style="font-size:12px; line-height:1.5">${data.answer.replace(/\n/g, '<br>')}</div>`;
            switchTab(1); 

            if(data.chart) {
                currentChartData = data.chart;
                const spec = JSON.parse(JSON.stringify(data.chart));
                spec.width = "container";
                spec.height = "container";
                spec.autosize = { type: "fit", contains: "padding", resize: true };
                document.getElementById('vis').innerHTML = "";
                vegaEmbed('#vis', spec, { actions: false, renderer: 'canvas' }).catch(console.warn);

                // 显示设计按钮
                document.getElementById('btnGenInfo').style.display = 'block';
                // [新增] 显示随机生成控件
                document.getElementById('randomGenerateRow').style.display = 'flex';
            }
        } else { alert(data.error); }
    } catch(e) { alert("Analysis Error: " + e); }
    finally {
        toggleLoading('loading-analyze', false);
        document.getElementById('btnAnalyze').disabled = false;
    }
});

// ================= 步骤 3.5: 设计向导 (重写核心逻辑) =================

// 1. 开始设计：获取方案
document.getElementById('btnGenInfo').addEventListener('click', async () => {
    toggleLoading('loading-info', true);
    try {
        const res = await fetch('/infographic/plan', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                description: document.getElementById('tableDesc').value,
                query: document.getElementById('queryInput').value,
                analysis_result: currentAnalysisAnswer,
                chart_source: currentChartData
            })
        });
        const data = await res.json();
        if(data.status === 'success') {
            currentPlan = data.plan;
            wizardStep = 0;
            designSelections = {}; // 重置选择
            designSelectionMeta = {};
            switchTab(3); // 自动切换到 Design 标签页
            renderWizardStep();
        } else { alert(data.error); }
    } catch(e) { alert("Plan Error: " + e); }
    finally { toggleLoading('loading-info', false); }
});

// ================= [新增] 随机生成 N 个信息图 =================
function getRandomGenerationCount() {
    const input = document.getElementById('randomCountInput');
    const minVal = Number.parseInt(input.min || '1', 10);
    const maxVal = Number.parseInt(input.max || '12', 10);
    const count = Number.parseInt(input.value, 10);

    if (Number.isNaN(count) || count < minVal || count > maxVal) {
        alert(`Please input an integer between ${minVal} and ${maxVal}.`);
        input.focus();
        return null;
    }

    input.value = String(count);
    return count;
}

document.getElementById('btnGenRandom').addEventListener('click', async () => {
    const btn = document.getElementById('btnGenRandom');
    const count = getRandomGenerationCount();
    if (count === null) return;
    const originalText = btn.innerText;

    // 如果还没有 Plan，先静默请求一个 Plan
    if (!currentPlan) {
        btn.innerText = "🎲 Planning & Generating...";
        btn.disabled = true;
        try {
            const res = await fetch('/infographic/plan', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    description: document.getElementById('tableDesc').value,
                    query: document.getElementById('queryInput').value,
                    analysis_result: currentAnalysisAnswer,
                    chart_source: currentChartData
                })
            });
            const data = await res.json();
            if(data.status === 'success') {
                currentPlan = data.plan;
            } else {
                alert(data.error);
                btn.innerText = originalText;
                btn.disabled = false;
                return;
            }
        } catch(e) { alert("Plan Error: " + e); btn.innerText = originalText; btn.disabled = false; return; }
    }

    // 调用随机生成接口
    btn.innerText = `🎲 Generating ${count} Posters...`;
    btn.disabled = true;

    try {
        const res = await fetch('/infographic/generate_random', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                count: count,
                plan: currentPlan,
                chart_source: currentChartData,
                description: document.getElementById('tableDesc').value,
                query: document.getElementById('queryInput').value,
                analysis_result: currentAnalysisAnswer
            })
        });
        const data = await res.json();

        if(data.status === 'success') {
            galleryData = []; // 清空之前的画廊
            for (let i = data.results.length - 1; i >= 0; i--) {
                const item = data.results[i];
                // [修复]: 每次循环利用 i 作为偏移量，确保 Date.now() 不重复
                const uniqueId = Date.now() + i;

                const newEntry = {
                    id: uniqueId,
                    imgUrl: item.image_url,
                    selections: JSON.parse(JSON.stringify(item.selections)),
                    assetUrl: null
                };
                galleryData.unshift(newEntry);
            }
            activeGalleryIndex = 0;
            renderGalleryUI();

            switchTab(3);

            btn.innerText = "Done!";
            setTimeout(() => {
                btn.innerText = originalText;
                btn.disabled = false;
            }, 2000);
        } else {
            alert(data.error);
            btn.innerText = "Retry";
            btn.disabled = false;
        }
    } catch(e) {
        alert("Random Gen Error: " + e);
        btn.innerText = "Error";
        btn.disabled = false;
    }
});

// 2. 渲染右侧面板的向导步骤
function renderWizardStep() {
    const container = document.getElementById('tab-design');
    container.innerHTML = '';
    
    // 定义步骤
    const steps = [
        { id: 'bottom', title: '1. Background & Mood', data: currentPlan.element_pool.bottom_layer },
        { id: 'middle', title: '2. Chart Style', data: currentPlan.element_pool.middle_layer },
        { id: 'top', title: '3. Narrative Text', data: currentPlan.element_pool.top_layer.filter(i => i.id !== 'visual_assets') },
        { id: 'assets', title: '4. Visual Elements', data: currentPlan.element_pool.top_layer.find(i => i.id === 'visual_assets') }
    ];

    const currentStepConfig = steps[wizardStep];

    let html = `<div class="wizard-step-title">${currentStepConfig.title}</div>`;
    html += `<div class="wizard-options-grid">`;

    if (wizardStep === 3) {
        // 第4步：素材选择 (保持不变)
        html += renderAssetStep(currentStepConfig.data);
    } else {
        // 其他步骤
        currentStepConfig.data.forEach(group => {
            html += `<div style="font-size:10px; font-weight:bold; color:#888; margin-top:5px;">${group.name}</div>`;
            const options = group.id === 'color_scheme'
                ? buildColorSchemeOptions(group.options)
                : group.options;

            if (group.id === 'color_scheme' && hasSelection(group.id)) {
                const validValues = options.map(opt => opt.label || opt.name || opt);
                if (!validValues.includes(designSelections[group.id])) {
                    delete designSelections[group.id];
                    delete designSelectionMeta[group.id];
                }
            }

            options.forEach((opt, idx) => {
                // [核心修改]：提取展示用的中文文本作为最终保存的 Value
                const label = opt.label || opt.name || opt;
                // 如果需要向后端传特定的 key 但显示 label，这里我们统一使用 label
                const valToSave = label;

                const contentText = opt.content || opt.text || "";

                // 判断是否选中，直接用中文文本比较
                const isSelected = isOptionSelected(group.id, valToSave) || (idx === 0 && !hasSelection(group.id));
                if(isSelected && !hasSelection(group.id)) saveSelection(group.id, valToSave);
                const encodedVal = encodeURIComponent(String(valToSave));

                html += `
                <div class="wizard-card ${isSelected ? 'selected' : ''}" onclick="selectOption('${group.id}', '${encodedVal}')">
                    <strong>${label}</strong>
                    <span>${opt.desc || opt.description || ''}</span>
                    
                    ${contentText ? `<div class="wizard-content-preview">${contentText}</div>` : ''}
                </div>`;
            });
        });
    }
    html += `</div>`;

    html += `<div class="wizard-nav">`;
    if (wizardStep > 0) html += `<button onclick="prevStep()">Back</button>`;
    if (wizardStep < steps.length - 1) html += `<button class="primary-btn" onclick="nextStep()">Next</button>`;
    else html += `<button class="primary-btn" onclick="generateFinalPoster()">🚀 Generate</button>`;
    html += `</div>`;

    container.innerHTML = html;
    if (wizardStep === 3) loadVisualAssets(currentStepConfig.data);
}

// 辅助：选择逻辑
function hasSelection(groupId) { return designSelections[groupId] !== undefined; }
function isOptionSelected(groupId, val) { return designSelections[groupId] === val; }

function applySelection(groupId, val) {
    designSelections[groupId] = val;

    if (groupId === 'color_scheme') {
        if (paletteOptionMetaByLabel[val]) {
            designSelectionMeta[groupId] = JSON.parse(JSON.stringify(paletteOptionMetaByLabel[val]));
        } else {
            delete designSelectionMeta[groupId];
        }
    }
}

window.selectOption = function(groupId, encodedVal) {
    const val = decodeURIComponent(encodedVal || '');
    applySelection(groupId, val);
    renderWizardStep();
};

window.toggleAsset = function(keywords) {
    // 检查当前是否已经选中了这个素材
    if(designSelections['visual_assets'] && designSelections['visual_assets'].keywords === keywords) {
        delete designSelections['visual_assets'];
    } else {
        // 从 currentPlan 中找到该素材的完整对象数据
        const assetGroup = currentPlan.element_pool.top_layer.find(i => i.id === 'visual_assets');
        const fullObj = assetGroup.options.find(o => o.keywords === keywords);
        // 保存完整对象，而不仅是字符串
        designSelections['visual_assets'] = fullObj;
    }
    renderWizardStep();
}

// 导航函数
window.nextStep = function() { wizardStep++; renderWizardStep(); }
window.prevStep = function() { wizardStep--; renderWizardStep(); }
window.saveSelection = function(groupId, val) { applySelection(groupId, val); }

// 3. 素材步骤专用：渲染 + 异步生成
function renderAssetStep(assetGroup) {
    if(!assetGroup) return "<div>No visual assets suggested.</div>";

    let html = `<div class="asset-grid">`;

    assetGroup.options.forEach((opt, idx) => {
        const keywords = opt.keywords;
        // [修改]：对比时需要取 .keywords 属性
        const isSelected = designSelections['visual_assets'] && designSelections['visual_assets'].keywords === keywords;
        const imgUrl = generatedAssets[keywords];

        html += `
        <div class="asset-card ${isSelected ? 'selected' : ''}" onclick="toggleAsset('${keywords}')">
            ${imgUrl 
                ? `<img src="${imgUrl}">` 
                : `<div class="asset-loader" id="loader-${idx}">Generating...</div>`
            }
            <div class="asset-card-label">${opt.category}</div>
        </div>
        `;
    });
    html += `</div>`;
    return html;
}

// 异步生成素材并更新 DOM
async function loadVisualAssets(assetGroup) {
    if(!assetGroup) return;

    const styleDesc = "flat vector icon, minimal, clean white background, high quality";

    for (let i = 0; i < assetGroup.options.length; i++) {
        const opt = assetGroup.options[i];
        if (generatedAssets[opt.keywords]) continue;

        try {
            const res = await fetch('/infographic/generate_asset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ keywords: opt.keywords, style: styleDesc })
            });
            const data = await res.json();
            if(data.status === 'success') {
                generatedAssets[opt.keywords] = data.asset_url;
                const loader = document.getElementById(`loader-${i}`);
                if(loader) {
                    loader.parentNode.innerHTML = `
                        <img src="${data.asset_url}">
                        <div class="asset-card-label">${opt.category}</div>
                    `;
                }
            }
        } catch(e) { console.error("Asset gen error", e); }
    }
}

// 4. 生成最终海报并添加到画廊
window.generateFinalPoster = async function() {
    const btn = document.querySelector('.wizard-nav .primary-btn');
    btn.innerText = "Processing...";
    btn.disabled = true;

    const finalSelections = {
        bottom_layer: {},
        middle_layer: {},
        top_layer: {}
    };

    // 收集选项
    currentPlan.element_pool.bottom_layer.forEach(g => { if(designSelections[g.id]) finalSelections.bottom_layer[g.id] = designSelections[g.id]; });
    currentPlan.element_pool.middle_layer.forEach(g => {
        if(!designSelections[g.id]) return;

        if (g.id === 'color_scheme' && designSelectionMeta[g.id]) {
            finalSelections.middle_layer[g.id] = JSON.parse(JSON.stringify(designSelectionMeta[g.id]));
        } else {
            finalSelections.middle_layer[g.id] = designSelections[g.id];
        }
    });

    // [修改]：不再排除 'visual_assets'，直接将其文本存入 top_layer 发送给后端
    currentPlan.element_pool.top_layer.forEach(g => {
        if(designSelections[g.id]) finalSelections.top_layer[g.id] = designSelections[g.id];
    });

    // [修改]：保留本地的素材图片URL，用于在前端显示(不发给后端)
    const localAssetUrl = designSelections['visual_assets'] ? generatedAssets[designSelections['visual_assets'].keywords] : null;
    try {
        const res = await fetch('/infographic/generate_final', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                selections: finalSelections, // 现在这里面包含了 visual_assets 的文字名称
                chart_source: currentChartData,
                description: document.getElementById('tableDesc').value,
                query: document.getElementById('queryInput').value,
                analysis_result: currentAnalysisAnswer
                // [修改]：删除了 asset_urls 字段
            })
        });
        const data = await res.json();

        if(data.status === 'success') {
            addToGallery(data.image_url, finalSelections, localAssetUrl);
            btn.innerText = "Done!";
            setTimeout(() => {
                btn.innerText = "Generate Variant";
                btn.disabled = false;
            }, 2000);
        } else {
            alert(data.error);
            btn.innerText = "Retry";
            btn.disabled = false;
        }
    } catch(e) {
        alert(e);
        btn.innerText = "Error";
        btn.disabled = false;
    }
};

// 5. 将结果添加到画廊
// [修改]：增加 assetUrl 参数
function addToGallery(imgUrl, usedSelections, assetUrl) {
    const newEntry = {
        id: Date.now(),
        imgUrl: imgUrl,
        selections: JSON.parse(JSON.stringify(usedSelections)),
        assetUrl: assetUrl // 前端绑定的图片URL，仅作展示
    };

    galleryData.unshift(newEntry);
    activeGalleryIndex = 0;
    renderGalleryUI();
}

// -------------------------------------------------------------
// [修改] 渲染画廊 UI - 增加中英文对照字典与翻译逻辑
// -------------------------------------------------------------
function renderGalleryUI() {
    const tabsContainer = document.getElementById('galleryTabs');
    const viewContainer = document.getElementById('galleryView');

    if (galleryData.length === 0) {
        viewContainer.innerHTML = '<div class="center-msg">生成的图表海报将显示在这里</div>';
        tabsContainer.innerHTML = '';
        return;
    }

    // [核心修改]：极简字典，仅翻译系统固定字段 Key，不涉及 Value
    const keyDict = {
        'bottom_layer': '🎨 底层 (背景与氛围)',
        'middle_layer': '📊 中层 (数据与图表)',
        'top_layer': '✨ 顶层 (叙事与元素)',
        'bg_style': '背景风格',
        'grid_style': '网格风格',
        'axis_style': '坐标轴',
        'chart_type': '图表类型',
        'color_scheme': '配色方案',
        'highlight_insight': '核心洞察',
        'annotation_text': '文本注释',
        'visual_assets': '视觉元素'
    };
    const t = (key) => keyDict[key] || key;

    // 渲染 Tabs (代码不变)
    let tabsHtml = '';
    galleryData.forEach((item, index) => {
        tabsHtml += `<div class="gallery-tab ${index === activeGalleryIndex ? 'active' : ''}" onclick="switchGalleryTab(${index})">方案 ${galleryData.length - index}</div>`;
    });
    tabsContainer.innerHTML = tabsHtml;

    // 渲染内容区域
    const activeItem = galleryData[activeGalleryIndex];
    const selections = activeItem.selections;

    let layersHtml = '';
    const layerOrder = ['bottom_layer', 'middle_layer', 'top_layer'];

    layerOrder.forEach(layerKey => {
        const layerData = selections[layerKey] || {};
        if (Object.keys(layerData).length > 0) {
            layersHtml += `<div style="margin-bottom: 12px;">`;
            // 渲染层级标题 (如：🎨 底层)
            layersHtml += `<div style="font-size: 11px; font-weight: bold; color: var(--primary); margin-bottom: 5px; border-bottom: 1px solid #eee; padding-bottom: 3px;">${t(layerKey)}</div>`;

            // 渲染该层级下的所有选项
            for (const [key, val] of Object.entries(layerData)) {

                // [新增]：如果 val 是对象 (例如 visual_assets)，提取其 keywords 或 label 显示
                let displayVal = val;
                if (typeof val === 'object' && val !== null) {
                    displayVal = val.keywords || val.label || val.name || JSON.stringify(val);
                }

                if (key === 'visual_assets' && activeItem.assetUrl) {
                    layersHtml += `
                        <div class="info-row" style="display:flex; align-items:center; gap:8px;">
                            <img src="${activeItem.assetUrl}" style="width:24px; height:24px; border-radius:3px; border:1px solid #ddd; background:#f9f9f9;" alt="asset">
                            <div>
                                <div class="info-label">${t(key)}</div>
                                <div class="info-val" style="color: #10b981; font-weight:bold;">${displayVal}</div>
                            </div>
                        </div>`;
                } else {
                    layersHtml += `
                        <div class="info-row">
                            <div class="info-label">${t(key)}</div>
                            <div class="info-val">${displayVal}</div> 
                        </div>`;
                }
            }
            layersHtml += `</div>`;
        }
    });

    viewContainer.innerHTML = `
        <div class="gallery-item">
            <div class="gallery-img-container">
                <img src="${activeItem.imgUrl}" class="gallery-img">
            </div>
            <div class="gallery-info">
                <h4>🗂️ 设计结构解析</h4>
                ${layersHtml}
                <div style="margin-top:auto; padding-top:10px;">
                    <a href="${activeItem.imgUrl}" download="infographic_${activeItem.id}.png" class="primary-btn" style="display:block; text-align:center; text-decoration:none; padding:8px;">
                        ⬇ 下载海报
                    </a>
                </div>
            </div>
        </div>
    `;
}

// 切换标签的函数
window.switchGalleryTab = function(index) {
    activeGalleryIndex = index;
    renderGalleryUI();
}

// ================= 步骤 4 & 5 (Reference & Palette) 保持不变 =================
async function handleRefResponse(res) {
    const data = await res.json();
    if(data.status === 'success') {
        currentRefImagePath = data.image_path;
        extractedPaletteResults = [];
        delete designSelectionMeta['color_scheme'];
        delete designSelections['color_scheme'];
        await renderRefImage(currentRefImagePath);
        document.getElementById('btnExtract').disabled = false;
    } else { alert(data.error); }
}

document.getElementById('btnRefGen').addEventListener('click', async () => {
    const prompt = document.getElementById('refPrompt').value;
    if(!prompt) return;
    toggleLoading('loading-ref', true);
    try {
        const res = await fetch('/generate_ref_image', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ prompt, aspect_ratio: document.getElementById('aspectRatio').value })
        });
        await handleRefResponse(res);
    } catch(e) { alert(e); } finally { toggleLoading('loading-ref', false); }
});

document.getElementById('btnAutoPalettePrompt').addEventListener('click', async () => {
    const btn = document.getElementById('btnAutoPalettePrompt');
    const originalText = btn.innerText;
    const desc = document.getElementById('tableDesc').value || "";
    const query = document.getElementById('queryInput').value || "";

    if(!query) {
        alert("Please run analysis query first.");
        return;
    }

    btn.disabled = true;
    btn.innerText = "Synthesizing...";

    try {
        const res = await fetch('/generate_palette_prompt', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                description: desc,
                query: query,
                analysis_result: currentAnalysisAnswer,
                chart_source: currentChartData
            })
        });
        const data = await res.json();

        if(data.status === 'success') {
            const pkg = data.prompt_package || {};
            const stage4 = pkg.stage4 || {};

            if (stage4.reference_prompt) {
                document.getElementById('refPrompt').value = stage4.reference_prompt;
            } else {
                alert("No stage-4 prompt generated");
            }
        } else {
            alert(data.error || "Auto prompt generation failed");
        }
    } catch(e) {
        alert("Auto Prompt Error: " + e);
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
});

document.getElementById('btnRefUpload').addEventListener('click', async () => {
    const file = document.getElementById('refFileInput').files[0];
    if(!file) return;
    const formData = new FormData();
    formData.append('file', file);
    toggleLoading('loading-ref', true);
    try {
        const res = await fetch('/upload_ref_image', { method: 'POST', body: formData });
        await handleRefResponse(res);
    } catch(e) { alert(e); } finally { toggleLoading('loading-ref', false); }
});

async function renderRefImage(url) {
    const mainImage = document.getElementById('mainImage');
    const svgLayer = document.getElementById('interactionLayer');
    document.getElementById('canvasContainer').style.display = 'inline-block';
    document.getElementById('refPlaceholder').style.display = 'none';
    svgLayer.innerHTML = '';
    return new Promise((resolve) => {
        mainImage.onload = () => {
            svgLayer.setAttribute('viewBox', `0 0 ${mainImage.naturalWidth} ${mainImage.naturalHeight}`);
            resolve();
        };
        mainImage.src = url + "?t=" + new Date().getTime();
    });
}

document.getElementById('btnExtract').addEventListener('click', async () => {
    const text = document.getElementById('regionPrompt').value;
    if(!text) return;
    toggleLoading('loading-palette', true);
    document.getElementById('interactionLayer').innerHTML = '';
    try {
        const res = await fetch('/process_palette_pipeline', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ image_path: currentRefImagePath, text_prompt: text })
        });
        const data = await res.json();
        if(data.status === 'success') {
            extractedPaletteResults = (data.results || []).filter(item => Array.isArray(item.palette) && item.palette.length > 0);
            renderMasks(data.results);
            if (currentPlan) renderWizardStep();
            switchTab(2); 
        } else {
            extractedPaletteResults = [];
            alert('No objects found');
        }
    } catch(e) { alert("Pipeline Error: " + e); }
    finally { toggleLoading('loading-palette', false); }
});

function renderMasks(items) {
    const svgLayer = document.getElementById('interactionLayer');
    svgLayer.innerHTML = '';
    items.forEach((item) => {
        if(!item.polygons) return;
        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        item.polygons.forEach(poly => {
            const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            polygon.setAttribute('points', poly.map(p => p.join(',')).join(' '));
            polygon.setAttribute('class', 'mask-poly');
            g.appendChild(polygon);
        });
        g.addEventListener('click', (e) => {
            e.stopPropagation();
            document.querySelectorAll('.mask-poly').forEach(el => el.classList.remove('active'));
            g.querySelectorAll('.mask-poly').forEach(el => el.classList.add('active'));
            showPaletteDetails(item);
        });
        svgLayer.appendChild(g);
    });
}

function showPaletteDetails(item) {
    const rgbToHex = (r, g, b) => "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    const paletteHtml = item.palette ? item.palette.map(c =>
        `<div class="color-swatch" style="background:${rgbToHex(c[0],c[1],c[2])}" title="RGB: ${c}"></div>`
    ).join('') : 'No Palette';
    document.getElementById('tab-palette').innerHTML = `
        <div class="data-row"><div class="data-label">Selected Object</div><div class="data-value" style="color:var(--primary)">${item.label.toUpperCase()}</div></div>
        <div class="data-row"><div class="data-label">Extracted Palette</div><div class="palette-grid">${paletteHtml}</div></div>
        <div class="data-row"><div class="data-label">Harmony Score</div><div class="data-value">${item.harmony_score ? item.harmony_score.toFixed(3) : 'N/A'}</div></div>
    `;
    switchTab(2);
}
