/* =====================================================================
   app.js — TTS Video Generation Tool Frontend
   ===================================================================== */

// ── State ─────────────────────────────────────────────────────────────
const state = {
  config: null,          // current AppConfig dict
  previewDebounce: null,
  currentJob: null,
  eventSource: null,
  previewRow: 0,         // which row index to preview
};

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadConfig();
  bindEvents();
  populateUI();
  requestPreview();
});

// ── Config Load/Save ──────────────────────────────────────────────────
async function loadConfig() {
  const res = await fetch('/api/config');
  state.config = await res.json();

  // Load available fonts into selects
  const fontsRes = await fetch('/api/list-fonts');
  const { fonts } = await fontsRes.json();
  document.querySelectorAll('.font-select').forEach(sel => {
    sel.innerHTML = '<option value="">-- auto --</option>';
    fonts.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f; opt.textContent = f;
      sel.appendChild(opt);
    });
  });
}

async function saveConfig() {
  const cfg = collectConfigFromUI();
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg)
  });
  showToast('配置已保存 ✓');
}

// ── Populate UI from config ───────────────────────────────────────────
function populateUI() {
  if (!state.config) return;
  const c = state.config;

  setVal('ffmpeg-path', c.ffmpeg_path);
  setVal('watermark-text', c.watermark_text);
  setVal('watermark-pos-x', c.watermark_pos_x);
  setVal('watermark-pos-y', c.watermark_pos_y);
  setVal('watermark-font-size', c.watermark_font_size);
  setColor('watermark-color', c.watermark_color);
  setVal('output-filename', c.behavior.output_filename);

  // TTS
  setVal('tts-backend', c.tts.backend);
  setVal('tts-api-url', c.tts.api_url);
  setVal('tts-api-key', c.tts.api_key);
  setVal('tts-voice', c.tts.voice);
  setVal('tts-source-list', c.tts.tts_source_list);

  // Behavior
  setVal('repeat-count', c.behavior.repeat_count);
  setVal('silent-multiplier', c.behavior.silent_multiplier);
  setVal('tts-delay', c.behavior.tts_request_delay);
  setVal('show-t3-from', c.behavior.show_text3_from_repeat ?? 1);

  // Sync slider displays manually after setting programmatic values
  document.getElementById('repeat-count').dispatchEvent(new Event('input', { bubbles: true }));
  document.getElementById('silent-multiplier').dispatchEvent(new Event('input', { bubbles: true }));
  document.getElementById('tts-delay').dispatchEvent(new Event('input', { bubbles: true }));

  // Text layers
  for (const n of [1, 2, 3, 4]) {
    const layer = c[`text${n}`];
    setVal(`t${n}-pos-x`, layer.pos_x);
    setVal(`t${n}-pos-y`, layer.pos_y);
    setVal(`t${n}-font-size`, layer.font_size);
    setColor(`t${n}-color`, layer.color);
    setVal(`t${n}-font-file`, layer.font_file);
  }

  updateTTSBackendVisibility();
  updatePosBadges();
}

// ── Collect config from UI ────────────────────────────────────────────
function collectConfigFromUI() {
  const cfg = {
    ffmpeg_path: getVal('ffmpeg-path'),
    watermark_text: getVal('watermark-text'),
    watermark_pos_x: parseInt(getVal('watermark-pos-x')) || 1820,
    watermark_pos_y: parseInt(getVal('watermark-pos-y')) || 1000,
    watermark_font_size: parseInt(getVal('watermark-font-size')) || 30,
    watermark_color: getVal('watermark-color'),
    tts: {
      backend: getVal('tts-backend'),
      api_url: getVal('tts-api-url'),
      api_key: getVal('tts-api-key'),
      voice: getVal('tts-voice'),
      tts_source_list: parseInt(getVal('tts-source-list')) || 0,
    },
    behavior: {
      repeat_count: parseInt(getVal('repeat-count')) || 1,
      silent_multiplier: parseFloat(getVal('silent-multiplier')) || 2.5,
      tts_request_delay: parseFloat(getVal('tts-delay')) || 0.5,
      output_filename: getVal('output-filename'),
      show_text3_from_repeat: (() => { const v = parseInt(getVal('show-t3-from')); return isNaN(v) ? 1 : v; })(),
    },
  };
  for (const n of [1, 2, 3, 4]) {
    cfg[`text${n}`] = {
      pos_x: parseInt(getVal(`t${n}-pos-x`)) || 100,
      pos_y: parseInt(getVal(`t${n}-pos-y`)) || 200,
      font_size: parseInt(getVal(`t${n}-font-size`)) || 60,
      color: getVal(`t${n}-color`),
      font_file: getVal(`t${n}-font-file`) || '',
    };
  }
  return cfg;
}

// ── Event Bindings ────────────────────────────────────────────────────
function bindEvents() {
  // Delegated capture-phase listener: catches ALL inputs inside .preview-trigger
  // elements (number, color, text, range, select) reliably and immediately.
  document.addEventListener('input', (e) => {
    if (e.target.matches('.preview-trigger') || e.target.closest('.preview-trigger')) {
      debouncedPreview();
    }
    // Also trigger if the element itself is a preview-trigger
    if (e.target.classList && e.target.classList.contains('preview-trigger')) {
      debouncedPreview();
    }
  }, true); // useCapture = true ensures we catch number spinners too

  document.addEventListener('change', (e) => {
    if (e.target.classList && e.target.classList.contains('preview-trigger')) {
      debouncedPreview();
    }
  }, true);

  // Sync slider displays
  document.getElementById('repeat-count').addEventListener('input', e => {
    setVal('repeat-count-disp', e.target.value);
  });
  document.getElementById('silent-multiplier').addEventListener('input', e => {
    setVal('silent-multiplier-disp', e.target.value);
  });
  document.getElementById('tts-delay').addEventListener('input', e => {
    setVal('tts-delay-disp', e.target.value);
  });

  // TTS backend visibility
  document.getElementById('tts-backend').addEventListener('change', () => {
    updateTTSBackendVisibility();
    debouncedPreview();
  });

  // Text-list textareas — preview first row, update count badge
  for (const n of [1, 2, 3, 4]) {
    document.getElementById(`texts-${n}`).addEventListener('input', () => {
      updateTextCount(n);
      debouncedPreview();
    });
  }

  // Preview image: click to place selected layer
  document.getElementById('preview-img').addEventListener('click', onPreviewClick);

  // Layer collapsibles
  document.querySelectorAll('.layer-header').forEach(h => {
    h.addEventListener('click', () => {
      const c = h.nextElementSibling;
      const ch = h.querySelector('.chevron');
      c.classList.toggle('open');
      ch.classList.toggle('open');
    });
  });

  // Tab strips
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.dataset.group;
      document.querySelectorAll(`[data-group="${group}"].tab-btn`).forEach(b => b.classList.remove('active'));
      document.querySelectorAll(`[data-tab-group="${group}"]`).forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.dataset.tab;
      document.getElementById(targetId).classList.add('active');
    });
  });

  // Save config button
  document.getElementById('btn-save-config').addEventListener('click', saveConfig);

  // Generate button
  document.getElementById('btn-generate').addEventListener('click', startGenerate);

  // Resume button
  const btnResume = document.getElementById('btn-resume');
  if (btnResume) btnResume.addEventListener('click', startResume);

  // Upload background
  document.getElementById('bg-file-input').addEventListener('change', onBgUpload);

  // Preview row selector
  document.getElementById('preview-row').addEventListener('input', e => {
    state.previewRow = parseInt(e.target.value) - 1;
    debouncedPreview();
  });
}

function updateTTSBackendVisibility() {
  const backend = getVal('tts-backend');
  document.getElementById('http-api-fields').style.display =
    backend === 'http_api' ? 'block' : 'none';
}

function updateTextCount(n) {
  const lines = getLines(n);
  const badge = document.getElementById(`count-badge-${n}`);
  if (badge) badge.textContent = `${lines.length} 行`;
}

function updatePosBadges() {
  for (const n of [1, 2, 3, 4]) {
    const x = getVal(`t${n}-pos-x`);
    const y = getVal(`t${n}-pos-y`);
    const badge = document.getElementById(`pos-badge-${n}`);
    if (badge) badge.textContent = `${x}, ${y}`;
  }
}

// ── Preview ───────────────────────────────────────────────────────────
function debouncedPreview() {
  clearTimeout(state.previewDebounce);
  state.previewDebounce = setTimeout(requestPreview, 350);
}

async function requestPreview() {
  const img = document.getElementById('preview-img');
  const placeholder = document.getElementById('preview-placeholder');
  img.classList.add('loading');

  const cfg = collectConfigFromUI();
  const rowIdx = state.previewRow;
  const sample = [1, 2, 3, 4].map(n => {
    const lines = getLines(n);
    return lines[rowIdx] || lines[0] || '';
  });

  // Which repeat to simulate (from the preview toolbar)
  const previewRepeat = parseInt(getVal('preview-repeat-num')) || 1;

  try {
    const res = await fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: cfg, sample_texts: sample, preview_repeat: previewRepeat }),
    });
    const data = await res.json();
    if (data.ok) {
      img.src = `data:${data.mime};base64,${data.image}`;
      img.style.display = 'block';
      if (placeholder) placeholder.style.display = 'none';
    }
  } catch (e) {
    console.error('Preview error:', e);
  } finally {
    img.classList.remove('loading');
    updatePosBadges();
  }
}

// Click on preview image -> set layer position
function onPreviewClick(e) {
  const img = e.currentTarget;
  const rect = img.getBoundingClientRect();
  // Natural image dimensions
  const natW = img.naturalWidth || 960;
  const natH = img.naturalHeight || 540;
  const dispW = rect.width;
  const dispH = rect.height;

  const relX = (e.clientX - rect.left) / dispW;
  const relY = (e.clientY - rect.top) / dispH;

  const absX = Math.round(relX * natW);
  const absY = Math.round(relY * natH);

  const target = getVal('click-target-select');
  if (target === 'watermark') {
    setVal('watermark-pos-x', absX);
    setVal('watermark-pos-y', absY);
  } else {
    const n = parseInt(target);
    setVal(`t${n}-pos-x`, absX);
    setVal(`t${n}-pos-y`, absY);
  }
  debouncedPreview();
}

// ── Background upload ─────────────────────────────────────────────────
async function onBgUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/upload-background', { method: 'POST', body: form });
  const data = await res.json();
  if (data.ok) {
    setVal('bg-path-display', data.path);
    showToast('背景图已更新');
    debouncedPreview();
  } else {
    showToast('上传失败: ' + data.error, 'error');
  }
}

// ── Generate Pipeline ─────────────────────────────────────────────────
async function startGenerate() {
  _runPipeline('/api/generate', '开始生成视频');
}

async function startResume() {
  _runPipeline('/api/resume', '继续生成（跳过TTS/图片）');
}

async function _runPipeline(endpoint, label) {
  const btn = document.getElementById('btn-generate');
  const btnR = document.getElementById('btn-resume');
  if (btn) btn.disabled = true;
  if (btnR) btnR.disabled = true;
  clearLog();
  appendLog(`▶ ${label}`);
  setProgress('tts', 0);
  setProgress('images', 0);
  setProgress('video', 0);
  setStatusDot('running');

  const cfg = collectConfigFromUI();
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  });

  const textLists = [1, 2, 3, 4].map(n => getLines(n));

  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config: cfg, text_lists: textLists }),
  });
  const data = await res.json();
  if (!data.ok) {
    appendLog('启动失败: ' + (data.error || '未知错误'), 'error');
    if (btn) btn.disabled = false;
    if (btnR) btnR.disabled = false;
    setStatusDot('error');
    return;
  }

  state.currentJob = data.job_id;
  listenProgress(data.job_id, btn, btnR);
}

function listenProgress(jobId, btn, btnR) {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = new EventSource(`/api/progress/${jobId}`);

  const _enable = () => {
    if (btn) btn.disabled = false;
    if (btnR) btnR.disabled = false;
  };

  state.eventSource.onmessage = (e) => {
    const payload = JSON.parse(e.data);
    const { event, data } = payload;

    if (event === 'log') {
      const levelMap = { info: 'info', warning: 'warn', error: 'error' };
      appendLog(data.msg, levelMap[data.level] || 'info');
    } else if (event === 'progress') {
      setProgress(data.stage, data.pct, data.detail);
    } else if (event === 'done') {
      state.eventSource.close();
      state.eventSource = null;
      _enable();
      if (data.output) {
        appendLog(`✅ 完成！输出: ${data.output}`, 'ok');
        showToast('视频生成完成 🎉');
        setStatusDot('done');
      } else {
        appendLog('❌ 生成失败，请查看日志', 'error');
        setStatusDot('error');
      }
    } else if (event === 'end') {
      state.eventSource.close();
      state.eventSource = null;
    }
  };

  state.eventSource.onerror = () => {
    appendLog('SSE 连接断开', 'warn');
    state.eventSource.close();
    state.eventSource = null;
    _enable();
    setStatusDot('error');
  };
}

// ── UI Helpers ────────────────────────────────────────────────────────
function getVal(id) {
  const el = document.getElementById(id);
  if (!el) return '';
  if (el.type === 'color') return el.value;
  return el.value;
}
function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val !== undefined && val !== null ? val : '';
}
function setColor(id, val) {
  const el = document.getElementById(id);
  if (!el) return;
  // Ensure hex format
  try {
    if (val && val.startsWith('#') && val.length === 7) {
      el.value = val;
    } else {
      el.value = '#ffffff';
    }
  } catch (e) { el.value = '#ffffff'; }
}
function getLines(n) {
  const ta = document.getElementById(`texts-${n}`);
  if (!ta) return [];
  return ta.value.split('\n').map(l => l.trim()).filter(l => l.length > 0);
}

function appendLog(msg, cls = 'info') {
  const panel = document.getElementById('log-panel');
  const line = document.createElement('div');
  line.className = `log-${cls}`;
  const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  line.textContent = `[${ts}] ${msg}`;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
}
function clearLog() {
  document.getElementById('log-panel').innerHTML = '';
}

const progressBars = { tts: 0, images: 0, video: 0 };
function setProgress(stage, pct, detail = '') {
  progressBars[stage] = pct;
  // Overall = average
  const total = (progressBars.tts + progressBars.images + progressBars.video) / 3;
  const bar = document.getElementById('overall-progress');
  const label = document.getElementById('progress-label');
  if (bar) bar.style.width = `${Math.round(total)}%`;
  if (label) label.textContent = detail || `${Math.round(total)}%`;

  // Stage-specific bars
  const stageBar = document.getElementById(`progress-${stage}`);
  if (stageBar) stageBar.style.width = `${pct}%`;
}

function setStatusDot(state) {
  const dot = document.getElementById('status-dot');
  if (!dot) return;
  dot.className = 'status-dot';
  if (state === 'running') dot.classList.add('running');
  else if (state === 'error') dot.classList.add('error');
  else if (state === 'done') dot.classList.add('');   // green = default
  else dot.classList.add('idle');
}

let _toastTimer;
function showToast(msg, type = 'ok') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderColor = type === 'error' ? 'var(--red)' : 'var(--accent)';
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), 3000);
}
