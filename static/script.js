        // --- 状态变量 ---
        let currentFilePath = "";
        let currentAnalysisAnswer = "";
        let currentChartData = null;
        let currentRefImagePath = "";

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

        // ================= 步骤 1: 上传数据 =================
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

                    // [修改]：自动填充后端生成的描述，如果后端没有返回则使用默认值
                    const descBox = document.getElementById('tableDesc');
                    if(data.description) {
                        descBox.value = data.description;
                        // 增加一个简单的视觉反馈（可选）
                        descBox.style.backgroundColor = "#f0fdf4";
                        setTimeout(() => descBox.style.backgroundColor = "#fbfbfb", 1000);
                    }

                    alert("Data Loaded & Description Generated");
                } else { alert(data.error); }
            } catch(e) { alert("Error: " + e); }
            finally {
                toggleLoading('loading-upload', false);
                document.getElementById('btnUpload').disabled = false;
            }
        });

// 替换原有的 renderSchema 函数
        function renderSchema(meta) {
            const container = document.getElementById('tab-schema');
            // 显示总行数
            let html = `<div style="font-size:10px; color:#999; margin-bottom:15px;">${meta.rows} ROWS FOUND</div>`;

            // 遍历列名并生成带标签的列表项
            meta.columns.forEach(col => {
                html += `<div style="margin-bottom:8px; border-bottom:1px solid #eee; padding-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-family:'JetBrains Mono'; font-size:11px; font-weight:600;">${col}</span>
                            <span class="schema-type">STR/NUM</span>
                         </div>`;
            });
            container.innerHTML = html;
        }

        // ================= 步骤 3: 分析与图表 =================
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
                    // 更新 Insight 选项卡
                    currentAnalysisAnswer = data.answer;
                    document.getElementById('tab-insight').innerHTML = `<div style="font-size:12px; line-height:1.5">${data.answer.replace(/\n/g, '<br>')}</div>`;
                    switchTab(1); // 切换到 Insight

                    // 更新图表
                    if(data.chart) {
                        currentChartData = data.chart; // 保存原始数据供后续使用

                        // 1. 深拷贝一份配置，以免修改影响 currentChartData
                        const spec = JSON.parse(JSON.stringify(data.chart));

                        // 2. 强制覆盖宽高为 "container"，让 Vega 自动适应 CSS 的宽高
                        spec.width = "container";
                        spec.height = "container";

                        // 3. 设置 autosize 策略：fit (缩放以适应) 并包含 padding
                        spec.autosize = {
                            type: "fit",
                            contains: "padding",
                            resize: true // 允许随浏览器窗口调整大小重绘
                        };

                        // 4. 渲染图表
                        // 注意：我们先清空内容，防止重复渲染或残留文字
                        document.getElementById('vis').innerHTML = "";
                        vegaEmbed('#vis', spec, {
                            actions: false,    // 隐藏右上角三个点菜单
                            renderer: 'canvas' // 推荐使用 canvas，性能更好且不易溢出
                        }).catch(console.warn);

                        document.getElementById('btnGenInfo').style.display = 'block';
                    }
                } else { alert(data.error); }
            } catch(e) { alert("Analysis Error: " + e); }
            finally {
                toggleLoading('loading-analyze', false);
                document.getElementById('btnAnalyze').disabled = false;
            }
        });

        // ================= 步骤 3.5: 生成信息图 =================
        document.getElementById('btnGenInfo').addEventListener('click', async () => {
            toggleLoading('loading-info', true);
            try {
                const res = await fetch('/generate_infographic', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        description: document.getElementById('tableDesc').value,
                        query: document.getElementById('queryInput').value,
                        analysis_result: currentAnalysisAnswer,
                        chart_source: currentChartData
                    })
                });
                const data = await res.json();
                if(data.status === 'success') {
                    document.getElementById('infoPlaceholder').style.display = 'none';
                    const img = document.getElementById('generatedImg');
                    img.src = data.image_url;
                    img.style.display = 'block';
                } else { alert(data.error); }
            } catch(e) { alert("Info Gen Error: " + e); }
            finally { toggleLoading('loading-info', false); }
        });

        // ================= 步骤 4: 参考图像处理 =================
        async function handleRefResponse(res) {
            const data = await res.json();
            if(data.status === 'success') {
                currentRefImagePath = data.image_path;
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

        // ================= 步骤 5 & 6: 调色板流水线 =================
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
                    renderMasks(data.results);
                    switchTab(2); // 自动切换到 Palette 选项卡
                } else { alert('No objects found'); }
            } catch(e) { alert("Pipeline Error: " + e); }
            finally { toggleLoading('loading-palette', false); }
        });

        function renderMasks(items) {
            const svgLayer = document.getElementById('interactionLayer');
            svgLayer.innerHTML = '';

            items.forEach((item, index) => {
                if(!item.polygons) return;
                const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
                g.setAttribute('class', 'mask-group');

                item.polygons.forEach(poly => {
                    const pointsStr = poly.map(p => p.join(',')).join(' ');
                    const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
                    polygon.setAttribute('points', pointsStr);
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
                <div class="data-row">
                    <div class="data-label">Selected Object</div>
                    <div class="data-value" style="color:var(--primary)">${item.label.toUpperCase()}</div>
                </div>
                <div class="data-row">
                    <div class="data-label">Extracted Palette</div>
                    <div class="palette-grid">${paletteHtml}</div>
                </div>
                <div class="data-row">
                    <div class="data-label">Harmony Score</div>
                    <div class="data-value">${item.harmony_score ? item.harmony_score.toFixed(3) : 'N/A'}</div>
                </div>
            `;
            switchTab(2);
        }
