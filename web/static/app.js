/* ==========================================================
   Images → ePub / PDF  –  Frontend Logic
   ========================================================== */

const IMAGE_EXTS = new Set(['jpg','jpeg','png','webp','bmp','tiff','tif','gif']);
const ARCHIVE_EXTS = new Set(['zip','cbz']);

const state = {
  images: [],      // [{id, file, url, name}]
  format: 'epub',
  sortable: null,
};

/* ── Các hàm tiện ích nhỏ ─────────────────────────────────────────── */
function uid() { return Math.random().toString(36).slice(2,10); }

function ext(filename) {
  return (filename || '').split('.').pop().toLowerCase();
}

/* ── Khởi động ─────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  setupDrop();
  setupInputs();
  setupFormat();
  setupQuality();
  setupClear();
  setupSortAZ();
  setupConvert();
  setupTheme();
});

/* ── Kéo thả file ──────────────────────────────────────────── */
function setupDrop() {
  const zone = document.getElementById('dropZone');

  ['dragenter','dragover'].forEach(ev => {
    zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('drag-over'); });
  });
  ['dragleave','drop'].forEach(ev => {
    zone.addEventListener(ev, e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      if (ev === 'drop') {
        if (e.dataTransfer.items) {
          getFilesFromDataTransfer(e.dataTransfer.items).then(addFiles);
        } else {
          addFiles([...e.dataTransfer.files]);
        }
      }
    });
  });

  // Bấm vào vùng kéo thả (ngoại trừ nút bấm) cũng mở cửa sổ chọn file
  zone.addEventListener('click', e => {
    if (!e.target.closest('.btn')) document.getElementById('inputImages').click();
  });
}

/* ── Nút chọn file ──────────────────────────────────────────── */
function setupInputs() {
  const imgPicker  = document.getElementById('inputImages');
  const folderPicker = document.getElementById('inputFolder');

  document.getElementById('btnAddImages') .addEventListener('click', e => { e.stopPropagation(); imgPicker.click(); });
  document.getElementById('btnAddFolder') .addEventListener('click', e => { e.stopPropagation(); folderPicker.click(); });

  imgPicker .addEventListener('change', e => { addFiles([...e.target.files]); e.target.value = ''; });
  folderPicker.addEventListener('change', e => { addFiles([...e.target.files]); e.target.value = ''; });
}

/* ── Xử lý file đầu vào ─────────────────────────────────────────── */
async function getFilesFromDataTransfer(items) {
  const files = [];
  const promises = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind === 'file') {
      if (typeof item.webkitGetAsEntry === 'function') {
        const entry = item.webkitGetAsEntry();
        if (entry) {
          promises.push(traverseFileTree(entry, '', files));
        }
      } else {
        files.push(item.getAsFile());
      }
    }
  }
  await Promise.all(promises);
  return files;
}

function traverseFileTree(item, path, files) {
  return new Promise((resolve) => {
    path = path || '';
    if (item.isFile) {
      item.file(file => {
        file.customPath = path + file.name;
        files.push(file);
        resolve();
      });
    } else if (item.isDirectory) {
      const dirReader = item.createReader();
      dirReader.readEntries(async entries => {
        const promises = [];
        for (let i = 0; i < entries.length; i++) {
          promises.push(traverseFileTree(entries[i], path + item.name + "/", files));
        }
        await Promise.all(promises);
        resolve();
      });
    } else {
      resolve();
    }
  });
}

/* ── Add files ────────────────────────────────────────────── */
async function addFiles(files) {
  let added = 0;
  for (const file of files) {
    const e = ext(file.name);
    if (IMAGE_EXTS.has(e)) {
      addImage(file);
      added++;
    } else if (ARCHIVE_EXTS.has(e)) {
      const n = await extractArchive(file);
      added += n;
    }
  }
  if (added) renderUI();
}

function addImage(file) {
  const url = URL.createObjectURL(file);
  const path = file.customPath || file.webkitRelativePath || file.name;
  state.images.push({ id: uid(), file, url, name: file.name, path: path });
}

async function extractArchive(file) {
  addLog(`📦 Đang giải nén ${file.name}…`);
  try {
    if (typeof JSZip === 'undefined') {
      addLog('⚠️ Thư viện JSZip chưa tải – cần kết nối internet khi mở lần đầu.', 'warn');
      return 0;
    }
    const zip      = new JSZip();
    const contents = await zip.loadAsync(file);
    const entries  = Object.keys(contents.files)
      .filter(n => IMAGE_EXTS.has(ext(n)) && !contents.files[n].dir)
      .sort();

    for (const name of entries) {
      const blob   = await contents.files[name].async('blob');
      const mime   = `image/${ext(name) === 'jpg' ? 'jpeg' : ext(name)}`;
      const typed  = new File([blob], name.split('/').pop(), { type: mime });
      addImage(typed);
    }
    addLog(`✅ Giải nén xong – ${entries.length} ảnh từ ${file.name}`, 'success');
    return entries.length;
  } catch (err) {
    addLog(`❌ Không thể giải nén: ${err.message}`, 'error');
    return 0;
  }
}

/* ── Render UI ────────────────────────────────────────────── */
function renderUI() {
  const section    = document.getElementById('previewSection');
  const grid       = document.getElementById('previewGrid');
  const countEl    = document.getElementById('imageCount');
  const convertBtn = document.getElementById('btnConvert');

  if (state.images.length === 0) {
    section.style.display = 'none';
    convertBtn.disabled   = true;
    return;
  }

  section.style.display = 'flex';
  countEl.textContent   = `${state.images.length} ảnh`;
  convertBtn.disabled   = false;

  // Rebuild grid
  grid.innerHTML = '';
  state.images.forEach((img, i) => {
    const card = document.createElement('div');
    card.className  = 'thumb-card';
    card.dataset.id = img.id;
    card.innerHTML  = `
      <div class="thumb-order">${i + 1}</div>
      <img class="thumb-img" src="${img.url}" alt="${img.name}" loading="lazy"/>
      <div class="thumb-name" title="${img.path}">${img.path}</div>
      <button class="thumb-remove" data-id="${img.id}" title="Xóa ảnh này">✕</button>
    `;
    grid.appendChild(card);
  });

  // Remove handlers
  grid.querySelectorAll('.thumb-remove').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const id  = btn.dataset.id;
      const idx = state.images.findIndex(i => i.id === id);
      if (idx !== -1) { URL.revokeObjectURL(state.images[idx].url); state.images.splice(idx, 1); }
      renderUI();
    });
  });

  // Sortable
  if (state.sortable) state.sortable.destroy();
  state.sortable = new Sortable(grid, {
    animation: 200,
    ghostClass: 'sortable-ghost',
    dragClass:  'sortable-drag',
    onEnd() {
      const ids = [...grid.querySelectorAll('.thumb-card')].map(c => c.dataset.id);
      state.images.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      refreshNumbers();
    },
  });
}

function refreshNumbers() {
  document.querySelectorAll('.thumb-order').forEach((el, i) => {
    el.textContent = i + 1;
  });
}

/* ── Format toggle ────────────────────────────────────────── */
function setupFormat() {
  const epubBtn = document.getElementById('fmtEpub');
  const pdfBtn  = document.getElementById('fmtPdf');
  const cbzBtn  = document.getElementById('fmtCbz');
  const pdfSettings = document.getElementById('pdfSettings');
  
  [epubBtn, pdfBtn, cbzBtn].forEach(btn => {
    btn.addEventListener('click', () => {
      [epubBtn, pdfBtn, cbzBtn].forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.format = btn.dataset.format;
      document.getElementById('convertLabel').textContent = `Tạo ${state.format.toUpperCase()}`;
      
      pdfSettings.style.display = state.format === 'pdf' ? 'block' : 'none';

      // Checkbox visibilities
      const mangaRow = document.getElementById('mangaRow');
      const webpRow  = document.getElementById('webpRow');
      const ocrRow   = document.getElementById('ocrRow');

      if (mangaRow) mangaRow.style.display = '';
      if (webpRow)  webpRow.style.display  = state.format === 'epub' ? '' : 'none';
      if (ocrRow)   ocrRow.style.display   = state.format === 'pdf' ? '' : 'none';
    });
  });
}

/* ── Quality slider ───────────────────────────────────────── */
function setupQuality() {
  const slider = document.getElementById('quality');
  const badge  = document.getElementById('qualityBadge');
  slider.addEventListener('input', () => { badge.textContent = slider.value + '%'; });
}

/* ── Clear all ────────────────────────────────────────────── */
function setupClear() {
  document.getElementById('btnClear').addEventListener('click', () => {
    state.images.forEach(img => URL.revokeObjectURL(img.url));
    state.images = [];
    renderUI();
    clearLog();
  });
}

/* ── Sort A-Z ─────────────────────────────────────────────── */
function setupSortAZ() {
  const btn = document.getElementById('btnSortAZ');
  if (btn) {
    btn.addEventListener('click', () => {
      if (state.images.length === 0) return;
      state.images.sort((a, b) => a.path.localeCompare(b.path));
      renderUI();
      addLog('✨ Đã sắp xếp lại ảnh theo thứ tự A-Z', 'info');
    });
  }
}

/* ── Convert ──────────────────────────────────────────────── */
function setupConvert() {
  document.getElementById('btnConvert').addEventListener('click', doConvert);

  // Ctrl+Enter or Cmd+Enter shortcut
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      const convertBtn = document.getElementById('btnConvert');
      if (!convertBtn.disabled) {
        e.preventDefault();
        doConvert();
      }
    }
  });
}

async function doConvert() {
  // Validate
  if (state.images.length === 0) {
    addLog('⚠️ Chưa có ảnh nào!', 'warn');
    return;
  }

  // Auto-Title logic
  let autoTitle = 'output';
  if (state.images.length > 0) {
    const firstPath = state.images[0].path;
    const parts = firstPath.split(/[\/\\]/);
    if (parts.length > 1) {
      autoTitle = parts[0];
    } else {
      autoTitle = firstPath.replace(/\.[^/.]+$/, "");
    }
  }

  // Build FormData
  const fd = new FormData();
  state.images.forEach((img, i) => {
    // Rename to ensure server sorts by arrival order
    const e    = ext(img.name);
    const name = `${String(i).padStart(6,'0')}.${e}`;
    fd.append('files[]', img.file, name);
  });
  state.images.forEach((img) => {
    fd.append('paths[]', img.path);
  });
  fd.append('title',      autoTitle);
  fd.append('author',     '');
  fd.append('format',     state.format);
  fd.append('quality',    document.getElementById('quality').value);
  fd.append('rtl',        document.getElementById('rtl').checked ? 'true' : 'false');
  fd.append('grayscale',  document.getElementById('grayscale').checked ? 'true' : 'false');
  fd.append('auto_crop',  document.getElementById('autoCrop').checked ? 'true' : 'false');
  fd.append('split_spreads', document.getElementById('splitSpreads').checked ? 'true' : 'false');
  fd.append('binarize',   document.getElementById('binarize').checked ? 'true' : 'false');
  fd.append('use_webp',   document.getElementById('useWebp').checked ? 'true' : 'false');
  fd.append('use_ocr',    document.getElementById('useOcr').checked ? 'true' : 'false');
  fd.append('ai_upscale', document.getElementById('aiUpscale').checked ? 'true' : 'false');
  fd.append('deskew_crop',document.getElementById('deskewCrop').checked ? 'true' : 'false');
  fd.append('guided_view',document.getElementById('guidedView').checked ? 'true' : 'false');
  fd.append('page_size',  document.getElementById('pageSize').value);
  fd.append('margin',     document.getElementById('pdfMargin').value);
  fd.append('max_width',  document.getElementById('maxWidth').value  || '');
  fd.append('max_height', document.getElementById('maxHeight').value || '');

  setWorking(true);
  showProgress(true, 0, 'Đang chuẩn bị upload…');
  addLog(`🚀 Bắt đầu tạo ${state.format.toUpperCase()} (${state.images.length} ảnh)`);

  try {
    const blob = await uploadWithProgress(fd, state.format);
    const url  = URL.createObjectURL(blob);
    
    if (state.format === 'pdf') {
      window.open(url, '_blank');
      addLog(`👀 Đang mở Preview PDF ở tab mới...`, 'info');
    }
    
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `${autoTitle}.${state.format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);

    setProgress(100, '✅ Hoàn tất!');
    addLog(`✅ File "${autoTitle}.${state.format}" đã tải về máy!`, 'success');
    setTimeout(() => showProgress(false), 3000);
  } catch (err) {
    setProgress(0, '');
    addLog(`❌ Lỗi: ${err.message}`, 'error');
    showProgress(false);
  } finally {
    setWorking(false);
  }
}

function uploadWithProgress(formData, fmt) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/convert');
    xhr.responseType = 'arraybuffer';

    // Upload phase (0–40%)
    xhr.upload.addEventListener('progress', e => {
      if (e.lengthComputable) {
        const pct = (e.loaded / e.total) * 40;
        setProgress(pct, `Đang upload… ${Math.round(pct / 0.4)}%`);
      }
    });

    // Simulate server-side progress (40–95%)
    let fake = 40;
    const iv = setInterval(() => {
      if (fake < 92) {
        fake += (92 - fake) * 0.07;
        setProgress(fake, `Đang xử lý ảnh… ${Math.round(fake)}%`);
      }
    }, 350);

    xhr.onload = () => {
      clearInterval(iv);
      if (xhr.status === 200) {
        const mime = fmt === 'epub' ? 'application/epub+zip' : 'application/pdf';
        resolve(new Blob([xhr.response], { type: mime }));
      } else {
        // Try to parse JSON error
        try {
          const text = new TextDecoder().decode(xhr.response);
          const json = JSON.parse(text);
          reject(new Error(json.error || `Server error ${xhr.status}`));
        } catch {
          reject(new Error(`Server error ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => { clearInterval(iv); reject(new Error('Không thể kết nối đến server')); };
    xhr.send(formData);
  });
}

/* ── Progress helpers ─────────────────────────────────────── */
function showProgress(show, pct = 0, text = '') {
  const wrap = document.getElementById('progressWrap');
  wrap.style.display = show ? 'flex' : 'none';
  if (show) setProgress(pct, text);
}

function setProgress(pct, text) {
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressText').textContent  = text;
}

/* ── Working state ────────────────────────────────────────── */
function setWorking(on) {
  const btn   = document.getElementById('btnConvert');
  const label = document.getElementById('convertLabel');

  btn.disabled = on;

  if (on) {
    label.innerHTML = '<span class="spinner"></span> Đang xử lý…';
  } else {
    label.innerHTML = 'Tạo file';
  }

  // Disable pickers while working
  ['btnAddImages','btnAddArchive','btnClear'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = on;
  });
}

/* ── Log ──────────────────────────────────────────────────── */
function addLog(msg, type = 'info') {
  const box  = document.getElementById('logBox');
  const line = document.createElement('div');
  const ts   = new Date().toLocaleTimeString('vi-VN', { hour12: false });
  line.className   = `log-line log-${type}`;
  line.textContent = `[${ts}] ${msg}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function clearLog() { document.getElementById('logBox').innerHTML = ''; }

/* ── Theme toggle ─────────────────────────────────────────── */
function setupTheme() {
  const btn      = document.getElementById('themeToggle');
  const iconMoon = document.getElementById('iconMoon');
  const iconSun  = document.getElementById('iconSun');

  btn.addEventListener('click', () => {
    const isLight = document.documentElement.getAttribute('data-theme') !== 'light';
    if (isLight) {
        document.documentElement.setAttribute('data-theme', 'light');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    iconMoon.style.display = isLight ? 'none' : '';
    iconSun.style.display  = isLight ? '' : 'none';
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
  });

  // Restore saved theme
  if (localStorage.getItem('theme') === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    iconMoon.style.display = 'none';
    iconSun.style.display  = '';
  }
}
