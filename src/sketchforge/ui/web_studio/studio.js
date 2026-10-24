(() => {
  // ---------------------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------------------
  const $ = s => document.querySelector(s);
  const canvas = $('#canvas');
  const promptInput = $('#prompt');
  const log = $('#agent-log');

  let currentSlug = '', currentUrl = '', pollTimer = null, zoom = 75;
  let pendingSketchLayout = '';

  function addLog(text) { log.textContent = text + '\n' + log.textContent; }

  // ---------------------------------------------------------------------------
  // Preview state management
  // ---------------------------------------------------------------------------
  function showProject(project) {
    currentSlug = project.slug;
    currentUrl = project.preview_url ||
      `http://127.0.0.1:8000/preview/${encodeURIComponent(currentSlug)}/home.html`;
    $('#empty').hidden = true;
    $('#artboards').innerHTML = `<article class="artboard"><header class="artboard-header"><span>▣ ${project.name}</span><span>Live preview　•　<span id="frame-state">Connecting…</span></span></header><iframe id="preview" title="Actual generated project preview" sandbox="allow-scripts allow-forms allow-same-origin allow-modals allow-downloads" src="${currentUrl}"></iframe></article>`;
    const frame = $('#preview');
    frame.onload = () => {
      $('#frame-state').textContent = 'Ready';
      frame.contentWindow.postMessage({ type: 'sf-edit-mode', enabled: true }, '*');
      if (window.pendingPreviewState) {
        frame.contentWindow.postMessage({ type: 'sf-restore', state: window.pendingPreviewState }, '*');
        window.pendingPreviewState = null;
      }
    };
    $('#popout').onclick = () => window.open(frame.src, '_blank', 'noopener');
    $('#status').textContent = `${project.name} · Live preview`;
    $('#copy-link').disabled = false;
    $('#export-project').disabled = false;
    refreshProjects();
    // Push a snapshot into the undo history whenever we show a project.
    _historyPush(currentUrl);
  }

  // ---------------------------------------------------------------------------
  // Undo / Redo — preview URL history stack
  // ---------------------------------------------------------------------------
  const _history = [];
  let _historyIndex = -1;

  function _historyPush(url) {
    // Drop any forward history after the current position.
    _history.splice(_historyIndex + 1);
    _history.push(url);
    _historyIndex = _history.length - 1;
    _historyUpdateButtons();
  }

  function _historyUpdateButtons() {
    const undoBtn = $('#undo');
    const redoBtn = $('#redo');
    if (undoBtn) undoBtn.disabled = _historyIndex <= 0;
    if (redoBtn) redoBtn.disabled = _historyIndex >= _history.length - 1;
  }

  function _previewNavigate(url) {
    const frame = $('#preview');
    if (frame) {
      frame.src = url;
      currentUrl = url;
      $('#status').textContent = 'Preview state restored';
    }
  }

  $('#undo').onclick = () => {
    if (_historyIndex > 0) {
      _historyIndex--;
      _previewNavigate(_history[_historyIndex]);
      _historyUpdateButtons();
      addLog('Undo: preview state traversed back.');
    }
  };

  $('#redo').onclick = () => {
    if (_historyIndex < _history.length - 1) {
      _historyIndex++;
      _previewNavigate(_history[_historyIndex]);
      _historyUpdateButtons();
      addLog('Redo: preview state traversed forward.');
    }
  };

  $('#export-project').onclick = () => {
    if (currentSlug) window.location.href = '/api/export/' + encodeURIComponent(currentSlug);
  };

  // Initialise button states.
  _historyUpdateButtons();

  // ---------------------------------------------------------------------------
  // Canvas selection and direct editing
  // ---------------------------------------------------------------------------
  const toolButtons = document.querySelectorAll('.canvas-tools button');
  function setEditMode(enabled) {
    const frame = $('#preview');
    if (frame) frame.contentWindow.postMessage({ type: 'sf-edit-mode', enabled }, '*');
  }
  toolButtons.forEach((btn, i) => {
    if (i === 0) {
      btn.classList.add('tool-active');
      btn.setAttribute('aria-pressed', 'true');
      btn.onclick = () => {
        const enabled = !btn.classList.contains('tool-active');
        toolButtons.forEach(b => { b.classList.remove('tool-active'); b.setAttribute('aria-pressed', 'false'); });
        if (enabled) {
          btn.classList.add('tool-active');
          btn.setAttribute('aria-pressed', 'true');
        }
        setEditMode(enabled);
      };
    } else if (i === 4) {
      btn.onclick = () => $('#image-input').click();
    } else if (i === 6) {
      btn.onclick = () => $('#preview')?.contentWindow.postMessage({ type: 'sf-add-text' }, '*');
    } else {
      btn.classList.add('tool-coming-soon');
      btn.setAttribute('aria-disabled', 'true');
      btn.setAttribute('title', `${btn.getAttribute('title') || 'Tool'} — Coming Soon`);
      btn.onclick = e => {
        e.preventDefault();
        const label = btn.getAttribute('title') || 'This tool';
        addLog(`ℹ️  ${label} is not yet available.`);
      };
    }
  });

  // ---------------------------------------------------------------------------
  // Image upload
  // ---------------------------------------------------------------------------
  $('#attach').onclick = () => $('#image-input').click();
  async function uploadImage(file) {
    if (!file || !file.type.startsWith('image/')) return;
    if (!currentSlug) {
      try {
        const response = await fetch('/api/sketch-analysis', {
          method: 'POST', headers: { 'Content-Type': file.type }, body: file
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Sketch analysis failed.');
        pendingSketchLayout = payload.layout;
        addLog(`${payload.summary} The analysis will guide your next generation.`);
        $('#status').textContent = 'Sketch analyzed · ready to generate';
      } catch (error) { addLog('Sketch analysis failed: ' + error.message); }
      return;
    }
    try {
      const response = await fetch('/api/upload/' + encodeURIComponent(currentSlug), {
        method: 'POST', headers: { 'Content-Type': file.type }, body: file
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Image upload failed.');
      const frame = $('#preview');
      frame.contentWindow.postMessage({ type: 'sf-insert-image', url: new URL(payload.url, frame.src).href }, '*');
      addLog('Added image: ' + file.name);
    } catch (error) { addLog('Image upload failed: ' + error.message); }
  }
  $('#image-input').onchange = event => { uploadImage(event.target.files[0]); event.target.value = ''; };
  ['dragenter', 'dragover'].forEach(type => window.addEventListener(type, event => {
    if ([...event.dataTransfer.types].includes('Files')) { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }
  }));
  window.addEventListener('drop', event => {
    if ([...event.dataTransfer.types].includes('Files')) {
      event.preventDefault();
      [...event.dataTransfer.files].filter(file => file.type.startsWith('image/')).forEach(uploadImage);
    }
  });
  $('#mic').onclick   = () => addLog('ℹ️  Voice input — Coming Soon.');

  // ---------------------------------------------------------------------------
  // Mode selector — visual toggle only (no generation mode change yet)
  // ---------------------------------------------------------------------------
  document.querySelectorAll('.mode-toggle button').forEach(b => b.onclick = () => {
    document.querySelectorAll('.mode-toggle button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
  });

  // ---------------------------------------------------------------------------
  // Project list
  // ---------------------------------------------------------------------------
  async function refreshProjects() {
    try {
      const r = await fetch('/api/projects');
      const items = await r.json();
      $('#project-list').innerHTML = items.map(p =>
        `<button class="project-item" data-slug="${encodeURIComponent(p.slug)}">✳　${p.name}</button>`
      ).join('') || '<p class="muted">Your generated projects will appear here.</p>';
      document.querySelectorAll('.project-item').forEach(b => b.onclick = () =>
        showProject(items.find(p => p.slug === decodeURIComponent(b.dataset.slug))));
    } catch { /* network unavailable — silently ignore */ }
  }

  // ---------------------------------------------------------------------------
  // Generation
  // ---------------------------------------------------------------------------
  async function generate(text) {
    if (!text.trim()) return;
    if (!currentSlug && pendingSketchLayout) {
      text += `\n\nUse this OpenCV analysis of my uploaded sketch as the layout guide. Keep the detected regions and their relative positions:\n${pendingSketchLayout}`;
      pendingSketchLayout = '';
    }
    const revising = Boolean(currentSlug);
    const frame = $('#preview');
    let saved = window.pendingPreviewState || {};
    if (revising && frame) {
      saved = await new Promise(resolve => {
        const timer = setTimeout(() => resolve({}), 500);
        const receive = e => {
          if (e.data?.type === 'sf-state') {
            clearTimeout(timer);
            removeEventListener('message', receive);
            resolve(e.data.state);
          }
        };
        addEventListener('message', receive);
        frame.contentWindow.postMessage({ type: 'sf-snapshot' }, '*');
      });
    }
    $('#status').textContent = revising ? 'Revising your app…' : 'Generating your app…';
    $('#empty').hidden = false;
    $('#empty').innerHTML = '<span class="empty-spark">◌</span><h1>Bringing it to life</h1><p id="progress">Planning your frontend and backend…</p>';
    addLog((revising ? 'Revision: ' : 'Starting: ') + text);
    try {
      const start = await fetch(
        revising ? '/api/revise/' + encodeURIComponent(currentSlug) : '/api/generate',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: text }) }
      );
      const payload = await start.json();
      if (!start.ok) throw Error(payload.error);
      let lastLoggedMessage = null;
      pollTimer = setInterval(async () => {
        try {
          const res = await fetch('/api/jobs/' + payload.id);
          const job = await res.json();
          const p = $('#progress');
          if (p) p.textContent = job.progress || 'Generating…';
          if (job.progress && job.progress !== lastLoggedMessage) {
            addLog(job.progress);
            lastLoggedMessage = job.progress;
          }
          if (job.status === 'complete') {
            clearInterval(pollTimer);
            $('#empty').hidden = true;
            addLog('Updated ' + job.project.name);
            if (revising && frame) {
              window.pendingPreviewState = saved;
              const path = saved.url || frame.src;
              frame.src = path.split('?')[0] + '?revision=' + Date.now();
              $('#status').textContent = job.project.name + ' · Preview refreshed';
              _historyPush(frame.src);
            } else {
              showProject(job.project);
            }
          }
          if (job.status === 'failed') {
            clearInterval(pollTimer);
            throw Error(job.error || 'Generation failed');
          }
        } catch (err) {
          clearInterval(pollTimer);
          $('#status').textContent = 'Generation failed';
          $('#empty').innerHTML = `<span class="empty-spark">!</span><h1>Could not generate the app</h1><p class="error">${err.message}</p><button onclick="location.reload()">Try again</button>`;
        }
      }, 900);
    } catch (err) {
      $('#status').textContent = 'Generation failed';
      $('#empty').innerHTML = `<h1>Could not start generation</h1><p class="error">${err.message}</p>`;
    }
  }

  // ---------------------------------------------------------------------------
  // Form submit & example prompts
  // ---------------------------------------------------------------------------
  $('#prompt-form').onsubmit = e => { e.preventDefault(); const text = promptInput.value; promptInput.value = ''; generate(text); };
  document.querySelectorAll('[data-prompt]').forEach(b => b.onclick = () => { promptInput.value = b.dataset.prompt; generate(promptInput.value); });

  // ---------------------------------------------------------------------------
  // Device switch
  // ---------------------------------------------------------------------------
  document.querySelectorAll('[data-size]').forEach(b => b.onclick = () => {
    document.querySelectorAll('[data-size]').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    const artboard = $('.artboard');
    if (artboard) {
      artboard.classList.remove('mobile', 'tablet');
      if (b.dataset.size !== 'desktop') artboard.classList.add(b.dataset.size);
    }
  });

  // ---------------------------------------------------------------------------
  // Share dialog
  // ---------------------------------------------------------------------------
  $('#share').onclick = () => $('#share-dialog').showModal();
  $('#close-share').onclick = () => $('#share-dialog').close();
  $('#share-switch').onchange = e => {
    $('#share-state').textContent = e.target.checked
      ? 'Anyone with the local link can open this prototype'
      : 'Only you can access this project';
    $('#copy-link').disabled = !e.target.checked || !currentUrl;
  };
  $('#copy-link').onclick = async () => {
    await navigator.clipboard.writeText(currentUrl);
    $('#copy-link').textContent = 'Copied local prototype link';
  };

  // ---------------------------------------------------------------------------
  // Reload, zoom & agent log toggle
  // ---------------------------------------------------------------------------
  $('#reload').onclick = () => { const f = $('#preview'); if (f) f.src = f.src; };
  $('#zoom-in').onclick  = () => { $('#zoom-label').textContent = (zoom = Math.min(125, zoom + 5)) + '%'; $('#artboards').style.transform = `scale(${zoom / 75})`; };
  $('#zoom-out').onclick = () => { $('#zoom-label').textContent = (zoom = Math.max(40,  zoom - 5)) + '%'; $('#artboards').style.transform = `scale(${zoom / 75})`; };
  $('#agent-toggle').onclick = () => log.hidden = !log.hidden;

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------
  $('#search').oninput = e => document.querySelectorAll('.project-item').forEach(
    b => b.hidden = !b.textContent.toLowerCase().includes(e.target.value.toLowerCase())
  );

  // ---------------------------------------------------------------------------
  // iframe postMessage bridge
  // ---------------------------------------------------------------------------
  window.addEventListener('message', e => {
    if (e.source !== $('#preview')?.contentWindow) return;
    if (e.data?.type === 'sketchforge-error') {
      const badge = $('#error-badge');
      badge.hidden = false;
      $('#error-text').textContent = `${e.data.message} · line ${e.data.line || '?'}`;
    }
    if (e.data?.type === 'sf-state') window.pendingPreviewState = e.data.state;
    if (e.data?.type === 'sf-file-drop') uploadImage(e.data.file);
    if (e.data?.type === 'sf-edit-saved') addLog('Canvas change saved to the generated page.');
    if (e.data?.type === 'sf-edit-error') addLog('Could not save the canvas change.');
    if (e.data?.type === 'sf-element-selected') $('#status').textContent = 'Selected: ' + e.data.text;
  });

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------
  refreshProjects();
})();
