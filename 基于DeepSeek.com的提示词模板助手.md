# DeepSeek.com 提示词模板助手

经过深思熟虑，我决定将这个“原本打算作为付费服务中的赠品”的东西开源了！

## 这是什么？

这是一个油猴脚本，它为`chat.deepseek.com`提供了“提示词模板”的功能，模板覆盖了公务员和办公室文员常用的提示词。（模板通过json文件存储，如果你会写json，可自己增加模板。）

## 如何使用？

它在浏览器上运行，以谷歌浏览器为例：
- 安装篡改猴
- 在扩展的详情页面，开启“允许运行用户脚本”
- 新建油猴脚本
- 粘贴本文中提供的代码
- 打开chat.deepseek.com尽情玩耍

## 增删提示词模板

提示词模板在代码中的导入：
```
  const CONFIG_URL = GM_getValue('CONFIG_URL') || 'https://gitee.com/deng_wenyi/ds-prompt-template/raw/main/prompts.json';
```

默认链接`https://gitee.com/deng_wenyi/ds-prompt-template/raw/main/prompts.json`，它在仓库：`https://gitee.com/deng_wenyi/ds-prompt-template`中。

这里需要一个可访问的链接，所以你可以将prompts.json的内容复制到你能控制的地方，然后将链接填到代码中，然后你就可以修改prompts.json了。

可以尝试gitee或者github，或者其他web文件服务器。

## 油猴脚本源码

```
// ==UserScript==
// @name         DeepSeek Prompt Helper (trigger menu + ribbon)
// @namespace    https://your.domain
// @version      0.1.5
// @description  在 chat.deepseek.com 输入框添加提示词列表与按钮栏：触发字符弹出列表、可搜索/上下键选择、点击或回车插入模板；数据来自远程 URL（JSON/TOML）
// @match        https://chat.deepseek.com/*
// @run-at       document-end
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @connect      gitee.com
// @connect      raw.githubusercontent.com
// ==/UserScript==

(function () {
  'use strict';

  // ========== 可自定义参数 ==========
  const CONFIG_URL = GM_getValue('CONFIG_URL') || 'https://gitee.com/deng_wenyi/ds-prompt-template/raw/main/prompts.json';
  const TRIGGER_STRING = GM_getValue('TRIGGER_STRING') || '/';
  const MAX_RIBBON = Number(GM_getValue('MAX_RIBBON') || 10);
  const CACHE_TTL_MS = 5 * 60 * 1000;
  const OPEN_KEY = GM_getValue('OPEN_KEY') || 'F2';
  const THEME = GM_getValue('THEME') || 'auto'; // 'auto' | 'dark' | 'light'

  // ========== 全局状态 ==========
  const state = {
    items: [],
    loadedAt: 0,
    textarea: null,
    ribbon: null,
    menu: null,
    searchInput: null,
    listEl: null,
    selectedIndex: -1,
    anchorOpenBy: null, // 'trigger' | 'button' | 'hotkey'
    triggerStart: null, // 触发字符串起始位置
    caretStart: null,   // 打开菜单时记录光标
    caretEnd: null,
  };

  // ========== 工具 ==========
  function gmFetch(url) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method: 'GET',
        url,
        headers: { 'Cache-Control': 'no-cache' },
        onload: (res) => {
          if (res.status >= 200 && res.status < 300) resolve(res.responseText);
          else reject(new Error(`HTTP ${res.status}`));
        },
        onerror: (e) => reject(e),
      });
    });
  }

  function parseConfig(text) {
    const t = text.trim();
    // 1) JSON（当前启用）
    if (t.startsWith('{') || t.startsWith('[')) {
      const data = JSON.parse(t);
      return normalizeConfig(data);
    }

    // 2) 简易 TOML（保留示例）
    /*
    const items = [];
    let current = null;
    for (const raw of t.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith('#')) continue;
      if (line.startsWith('[[') && line.endsWith(']]')) {
        if (current) items.push(current);
        current = {};
      } else if (current) {
        const m = line.match(/^([A-Za-z0-9_\-]+)\s*=\s*(.+)$/);
        if (m) {
          const key = m[1];
          let val = m[2].trim();
          if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
            val = val.slice(1, -1);
          } else if (/^\d+(\.\d+)?$/.test(val)) {
            val = Number(val);
          }
          current[key] = val;
        }
      }
    }
    if (current) items.push(current);
    return normalizeConfig({ items });
    */
  }

  function normalizeConfig(data) {
    const items = (Array.isArray(data) ? data : data.items) || [];
    const norm = items
      .map((x, i) => ({
        id: x.id || `item_${i}`,
        icon: x.icon || '🧩',
        title_zh: x.title_zh || x.zh || x.title || '',
        title_en: x.title_en || x.en || '',
        prompt: x.prompt || x.template || '',
        order: typeof x.order === 'number' ? x.order : 0,
        hint: x.hint || '',
      }))
      .filter((x) => x.title_zh || x.title_en || x.prompt);
    norm.sort((a, b) => b.order - a.order);
    return norm;
  }

  async function loadConfig(force = false) {
    const now = Date.now();
    if (!force && state.loadedAt && now - state.loadedAt < CACHE_TTL_MS && state.items.length) return state.items;
    try {
      const text = await gmFetch(CONFIG_URL);
      state.items = parseConfig(text);
      state.loadedAt = now;
      refreshRibbon();
    } catch (e) {
      console.error('[PromptHelper] 配置加载失败：', e);
    }
    return state.items;
  }

  function $(sel, root = document) { return root.querySelector(sel); }

  function ensureTextarea() {
    // 这里修复过一个bug，由于chat.deepseek.com变动，之前是textarea#chat-input现在是textarea
    const ta = $('textarea');
    if (ta && ta !== state.textarea) {
      state.textarea = ta;
      bindTextareaEvents(ta);
      injectRibbon(ta);
    }
    return state.textarea;
  }

  // 监听 DOM 变化，适配 SPA
  const mo = new MutationObserver(() => ensureTextarea());
  mo.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('load', ensureTextarea);
  setTimeout(ensureTextarea, 1000);

  // ========== 样式 ==========
  GM_addStyle(`
    .tmph-hidden { display: none !important; }

    /* Ribbon：grid 两列，左侧滚动，右侧固定；放在 textarea 包裹容器的上一层，不影响 ds-scroll-area 高度计算 */
    .tmph-ribbon {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 6px 8px 4px;
      margin: 0 8px 6px;      /* 与输入泡泡边距对齐 */
      box-sizing: border-box;
      overflow: hidden;
      width: auto;
    }
    .tmph-left {
      display: inline-flex;
      gap: 8px;
      min-width: 0;
      white-space: nowrap;
      overflow-x: auto;
      -ms-overflow-style: none;
      scrollbar-width: none;
    }
    .tmph-left::-webkit-scrollbar { display: none; }

    .tmph-btn {
      display: inline-flex; align-items: center; gap: 6px;
      border-radius: 8px; padding: 6px 10px; font-size: 12px;
      line-height: 1; cursor: pointer; user-select: none; border: 1px solid transparent;
      background: var(--tmph-btn-bg); color: var(--tmph-fg);
    }
    .tmph-btn:hover { background: var(--tmph-btn-hover); }
    .tmph-btn .ico { font-size: 14px; }

    .tmph-list-trigger {
      padding: 6px 8px; border-radius: 8px; border: 1px solid transparent;
      background: var(--tmph-btn-bg); cursor: pointer; color: var(--tmph-fg);
    }

    .tmph-menu {
      position: absolute; z-index: 99999; width: 420px; max-height: 56vh;
      border-radius: 12px; overflow: hidden; box-shadow: 0 6px 24px rgba(0,0,0,.25);
      background: var(--tmph-bg); color: var(--tmph-fg); border: 1px solid var(--tmph-border);
    }
    .tmph-menu .hdr { padding: 8px; border-bottom: 1px solid var(--tmph-border); }
    .tmph-menu .hdr input {
      width: 100%; padding: 8px 10px; font-size: 14px; border-radius: 8px;
      border: 1px solid var(--tmph-border); background: var(--tmph-input-bg); color: var(--tmph-fg);
      outline: none;
    }
    .tmph-menu .list {
      max-height: 48vh; overflow: auto;
      -ms-overflow-style: none; scrollbar-width: none;
    }
    .tmph-menu .list::-webkit-scrollbar { display: none; }

    .tmph-item {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 12px; cursor: pointer; border-bottom: 1px dashed var(--tmph-row-border);
    }
    .tmph-item:last-child { border-bottom: none; }
    .tmph-item .title { font-size: 14px; }
    .tmph-item .sub { opacity: .65; font-size: 12px; }
    .tmph-item.sel { background: var(--tmph-sel-bg); }
    .tmph-tip { padding: 6px 12px; opacity: .65; font-size: 12px; border-top: 1px solid var(--tmph-border); }

    /* 主题变量 */
    :root {
      --tmph-bg: #1f1f1f; --tmph-fg: #e7e7e7; --tmph-border: #2e2e2e;
      --tmph-row-border: #2b2b2b; --tmph-sel-bg: rgba(255,255,255,.06);
      --tmph-btn-bg: rgba(255,255,255,.06); --tmph-btn-hover: rgba(255,255,255,.12);
      --tmph-input-bg: rgba(255,255,255,.06);
    }
    .tmph-light {
      --tmph-bg: #fff; --tmph-fg: #222; --tmph-border: #dcdcdc;
      --tmph-row-border: #e9e9e9; --tmph-sel-bg: #f5f7ff;
      --tmph-btn-bg: #f2f3f5; --tmph-btn-hover: #e7e9ee;
      --tmph-input-bg: #fff;
    }
  `);

  // ========== 注入按钮栏 ==========
  function injectRibbon(textarea) {
    if (state.ribbon?.isConnected) state.ribbon.remove();

    // 目标：把 ribbon 插在“textarea 包裹容器”的上一层，并放在该容器之前
    // 结构一般是：container (我们要挂这里)
    //   ├─ taWrap (textarea 的直接父元素，包含 ds-scroll-area_gutters)
    //   ├─ 其他按钮栏/附件容器...
    const taWrap = textarea.parentElement;      // ds-scroll-area 容器
    const container = taWrap && taWrap.parentElement ? taWrap.parentElement : (textarea.parentElement || textarea.closest('div'));
    if (!container || !taWrap) return;

    const ribbon = document.createElement('div');
    ribbon.className = 'tmph-ribbon';
    applyTheme(ribbon);

    // 左侧：根据配置生成的按钮组（可横向滚动）
    const leftWrap = document.createElement('div');
    leftWrap.className = 'tmph-left';

    // 右端“全部模板”按钮（固定）
    const listBtn = document.createElement('button');
    listBtn.className = 'tmph-list-trigger';
    listBtn.title = '显示提示词列表';
    listBtn.innerHTML = '全部模板 📚';
    listBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openMenu('button');
    });

    ribbon.appendChild(leftWrap);
    ribbon.appendChild(listBtn);

    // 关键：插在 taWrap 前面（而不是插到 taWrap 里面）
    container.insertBefore(ribbon, taWrap);
    state.ribbon = ribbon;

    refreshRibbon();
  }

  function refreshRibbon() {
    if (!state.ribbon) return;
    const leftWrap = state.ribbon.querySelector('.tmph-left');
    if (!leftWrap) return;
    leftWrap.innerHTML = '';

    const items = state.items.slice(0, MAX_RIBBON);
    for (const it of items) {
      const btn = document.createElement('button');
      btn.className = 'tmph-btn';
      btn.title = it.hint || `${it.title_en || ''}`;
      btn.innerHTML = `<span class="ico">${escapeHTML(it.icon || '🧩')}</span><span>${escapeHTML(it.title_zh || it.title_en || '')}</span>`;
      btn.addEventListener('click', () => insertPrompt(it, 'button'));
      leftWrap.appendChild(btn);
    }
  }

  function applyTheme(el) {
    const mode = THEME === 'auto'
      ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
      : THEME;
    if (mode === 'light') el.classList.add('tmph-light');
    else el.classList.remove('tmph-light');
  }

  // ========== 菜单（弹出列表） ==========
  function ensureMenu() {
    if (state.menu?.isConnected) return state.menu;

    const menu = document.createElement('div');
    menu.className = 'tmph-menu tmph-hidden';
    applyTheme(menu);

    const hdr = document.createElement('div');
    hdr.className = 'hdr';
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = '搜索中文或英文标题（模糊匹配）…';
    hdr.appendChild(input);

    const list = document.createElement('div');
    list.className = 'list';

    const tip = document.createElement('div');
    tip.className = 'tmph-tip';
    tip.textContent = `↑/↓ 选择，Enter 插入，Esc 关闭`;

    menu.appendChild(hdr);
    menu.appendChild(list);
    menu.appendChild(tip);
    document.body.appendChild(menu);

    state.menu = menu;
    state.searchInput = input;
    state.listEl = list;

    // 事件
    input.addEventListener('input', () => renderList());
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { moveSel(1); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { moveSel(-1); e.preventDefault(); }
      else if (e.key === 'Enter') {
        const sel = getSelectedItem();
        if (sel) {
          e.preventDefault();
          chooseItem(sel);
        }
      } else if (e.key === 'Escape') {
        closeMenu();
      }
    });

    // 点击外部关闭（包括点击输入框）
    document.addEventListener('mousedown', (e) => {
      if (!menu || menu.classList.contains('tmph-hidden')) return;
      if (!menu.contains(e.target)) closeMenu();
    });

    return menu;
  }

  function openMenu(openBy) {
    ensureMenu();
    state.anchorOpenBy = openBy || 'button';
    const ta = ensureTextarea();
    if (!ta) return;

    // 记录打开时的光标位置
    state.caretStart = ta.selectionStart;
    state.caretEnd = ta.selectionEnd;

    loadConfig().then(() => {
      state.selectedIndex = 0;
      state.searchInput.value = '';
      renderList();

      const rect = ta.getBoundingClientRect();
      const menu = state.menu;
      menu.style.left = `${Math.max(12, rect.left)}px`;
      const preferredTop = rect.top - 12 - 320;
      const top = preferredTop > 10 ? rect.top - 330 : rect.bottom + 8;
      menu.style.top = `${Math.max(10, top)}px`;

      menu.classList.remove('tmph-hidden');
      state.searchInput.focus({ preventScroll: true });
      state.searchInput.select();
    });
  }

  function closeMenu() {
    if (state.menu) state.menu.classList.add('tmph-hidden');
    state.anchorOpenBy = null;
    state.triggerStart = null;
    state.selectedIndex = -1;
  }

  function renderList() {
    const list = state.listEl;
    if (!list) return;
    list.innerHTML = '';

    const q = (state.searchInput.value || '').trim();
    const items = filterItems(q, state.items);

    items.forEach((it, idx) => {
      const row = document.createElement('div');
      row.className = 'tmph-item' + (idx === state.selectedIndex ? ' sel' : '');
      row.innerHTML = `
        <span class="ico">${escapeHTML(it.icon || '🧩')}</span>
        <div>
          <div class="title">${hl(escapeHTML(it.title_zh || ''), q) || escapeHTML(it.title_zh || '')}</div>
          <div class="sub">${hl(escapeHTML(it.title_en || ''), q)}</div>
        </div>`;
      row.addEventListener('mouseenter', () => setSel(idx));
      row.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        chooseItem(it);
      });
      list.appendChild(row);
    });
  }

  function filterItems(q, items) {
    if (!q) return items;
    const key = normalize(q);
    const scored = [];
    for (const it of items) {
      const zh = normalize(it.title_zh || '');
      const en = normalize(it.title_en || '');
      const s1 = fuzzyScore(key, zh);
      const s2 = fuzzyScore(key, en);
      const score = Math.max(s1, s2);
      if (score > 0) scored.push({ it, score: score + (it.order || 0) / 1000 });
    }
    scored.sort((a, b) => b.score - a.score);
    return scored.map(x => x.it);
  }

  function fuzzyScore(q, s) {
    if (!q || !s) return 0;
    let qi = 0, si = 0, score = 0;
    while (qi < q.length && si < s.length) {
      if (q[qi] === s[si]) { score += 2; qi++; si++; }
      else si++;
    }
    if (qi === q.length) score += Math.min(q.length, 6);
    return score;
  }

  function hl(text, q) {
    if (!q) return text;
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx < 0) return text;
    return text.slice(0, idx) + '<b>' + text.slice(idx, idx + q.length) + '</b>' + text.slice(idx + q.length);
  }

  // 只切换选中样式
  function setSel(i) {
    const list = state.listEl;
    if (!list) return;
    const prev = state.selectedIndex;
    state.selectedIndex = i;
    if (prev >= 0 && list.children[prev]) list.children[prev].classList.remove('sel');
    if (i >= 0 && list.children[i]) list.children[i].classList.add('sel');
  }

  function moveSel(delta) {
    const q = (state.searchInput.value || '').trim();
    const items = filterItems(q, state.items);
    if (!items.length) return;
    state.selectedIndex = (state.selectedIndex + delta + items.length) % items.length;
    const list = state.listEl;
    Array.from(list.children).forEach((el, idx) => {
      el.classList.toggle('sel', idx === state.selectedIndex);
    });
    const child = list.children[state.selectedIndex];
    if (child) child.scrollIntoView({ block: 'nearest' });
  }

  function getSelectedItem() {
    const q = (state.searchInput.value || '').trim();
    const items = filterItems(q, state.items);
    if (!items.length) return null;
    const idx = Math.max(0, Math.min(items.length - 1, state.selectedIndex));
    return items[idx];
  }

  function chooseItem(it) {
    insertPrompt(it, 'menu');
    closeMenu();
  }

  // ========== 输入框事件 ==========
  function bindTextareaEvents(ta) {
    ta.addEventListener('keydown', (e) => {
      if (isTriggerKey(e)) {
        setTimeout(() => {
          const pos = ta.selectionStart;
          const val = ta.value;
          const triggerStart = pos - TRIGGER_STRING.length;
          if (triggerStart >= 0 && val.slice(triggerStart, pos) === TRIGGER_STRING) {
            state.triggerStart = triggerStart;
            openMenu('trigger');
          }
        }, 0);
        return;
      }
      if (e.key === OPEN_KEY) {
        e.preventDefault();
        openMenu('hotkey');
      }
      if (!isMenuHidden() && e.key === 'Enter') {
        e.stopPropagation();
      }
    });

    ta.addEventListener('focus', () => {
      if (!isMenuHidden()) closeMenu();
    });
  }

  function isTriggerKey(e) {
    if (!TRIGGER_STRING) return false;
    const lastChar = TRIGGER_STRING.slice(-1);
    return e.key === lastChar && !e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey;
  }

  function isMenuHidden() {
    return !state.menu || state.menu.classList.contains('tmph-hidden');
  }

  // ========== 插入与按钮状态 ==========
  function insertPrompt(item, source) {
    const ta = ensureTextarea();
    if (!ta) return;

    const prompt = item.prompt || '';
    let val = ta.value;

    // menu 插入时优先使用打开时光标位置
    let start = (source === 'menu' && typeof state.caretStart === 'number') ? state.caretStart : ta.selectionStart;
    let end = (source === 'menu' && typeof state.caretEnd === 'number') ? state.caretEnd : ta.selectionEnd;

    if (source === 'menu' && state.anchorOpenBy === 'trigger' && typeof state.triggerStart === 'number') {
      const slice = val.slice(state.triggerStart, state.triggerStart + TRIGGER_STRING.length);
      if (slice === TRIGGER_STRING) {
        const pre = val.slice(0, state.triggerStart);
        const post = val.slice(state.triggerStart + TRIGGER_STRING.length);
        val = pre + prompt + post;
        setTextareaValue(ta, val, 'insertText');
        const newPos = pre.length + prompt.length;
        ta.setSelectionRange(newPos, newPos);
        postInsertSync();
        return;
      }
    }

    // 普通插入
    const pre = val.slice(0, start);
    const post = val.slice(end);
    val = pre + prompt + post;
    setTextareaValue(ta, val, 'insertText');
    const newPos = pre.length + prompt.length;
    ta.setSelectionRange(newPos, newPos);
    postInsertSync();
  }

  function setTextareaValue(ta, value, inputType = 'insertText') {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    if (setter) setter.call(ta, value);
    else ta.value = value;

    try {
      const ev = new InputEvent('input', { bubbles: true, cancelable: false, data: value, inputType });
      ta.dispatchEvent(ev);
    } catch {
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
    ta.dispatchEvent(new Event('change', { bubbles: true }));
    ta.focus({ preventScroll: true });
  }

  function postInsertSync() {
    const ta = state.textarea;
    flashTextarea(ta);
    setTimeout(syncSendButton, 0);
    setTimeout(syncSendButton, 50);
  }

  function getSendButton() {
    const ta = state.textarea;
    if (!ta) return null;
    let root = ta;
    for (let i = 0; i < 4 && root; i++) {
      const container = root.parentElement;
      if (!container) break;
      const btns = container.querySelectorAll('div[role="button"][tabindex="-1"]');
      if (btns && btns.length >= 1) return btns[btns.length - 1];
      root = container;
    }
    return null;
  }

  function syncSendButton() {
    const ta = state.textarea;
    if (!ta) return;
    const btn = getSendButton();
    if (!btn) return;
    const hasText = (ta.value || '').trim().length > 0;
    btn.setAttribute('aria-disabled', hasText ? 'false' : 'true');
  }

  function flashTextarea(ta) {
    const orig = ta.style.outline;
    ta.style.outline = '2px solid #5b9cff';
    setTimeout(() => ta.style.outline = orig || 'none', 160);
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function normalize(s) {
    return (s || '').toString().toLowerCase().normalize('NFKC');
  }

  // 首次加载配置
  loadConfig();

  // 控制台辅助
  Object.assign(window, {
    TM_PH_setConfigUrl: (u) => { GM_setValue('CONFIG_URL', u); location.reload(); },
    TM_PH_reloadConfig: () => loadConfig(true),
  });

})();
```

## 感谢我？

![支付宝](https://github.com/Deng-Xian-Sheng/DeepinV25-desktop-wallpaper/blob/main/IMG_8270.jpeg)
![微信](https://github.com/Deng-Xian-Sheng/DeepinV25-desktop-wallpaper/blob/main/IMG_8271.jpeg)
