/* ==========================================================================
 * 一卡通账单 一键抓取脚本（账单助手 · 校园卡导入）
 *
 * 为什么需要它：
 *   一卡通列表接口带 Sign 签名，程序无法直接调用；页面也没有导出按钮。
 *   但「已经登录的页面」可以合法地调自己的接口。
 *   所以把抓取放在浏览器里跑：钩住页面自己的请求 → 自动滚动 → 导出 CSV。
 *   全程不构造请求，不碰签名，不上传任何数据。
 *
 * 用法：
 *   1. 登录 http://etcard.hzcu.edu.cn:8088/easytong_webapp/index.html#/bill
 *   2. F12 → Console，首次需手打 allow pasting，然后粘贴本文件，回车
 *      （或 Sources → Snippets → 粘贴 → Ctrl+Enter）
 *   3. 等它跑完，自动下载「校园卡流水_日期.csv」
 *
 * ⚠️ 时序限制：
 *   脚本的钩子永远比页面首屏请求晚一步，首屏那 20 笔抓不到。
 *   脚本会先自动尝试逼页面重发；若失败，会给出提示，
 *   此时请手动点一下顶部的「钱包」筛选再点回「全部」，
 *   然后执行 __campusGrabAgain()，会补上并重新导出。
 * ========================================================================== */
(() => {
  const STATE_KEY = '__campusGrab';
  const S = window[STATE_KEY] || (window[STATE_KEY] = {
    captured: new Map(),          // payRecNum -> 记录
    declaredTotal: null,
    installed: false,
    running: false,
  });

  const log = (m) => console.log('%c[一卡通抓取] ' + m, 'color:#0a0;font-weight:bold');
  const warn = (m) => console.warn('%c[一卡通抓取] ' + m, 'color:#f80;font-weight:bold');
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------ 收集响应
  function absorb(json) {
    if (!json || !Array.isArray(json.list)) return;
    if (S.declaredTotal == null && typeof json.count === 'number') S.declaredTotal = json.count;
    for (const group of json.list) {
      const month = String(group.month || '');
      for (const r of (group.dealDetail || [])) {
        const key = r.payRecNum;
        if (key == null || S.captured.has(key)) continue;
        S.captured.set(key, { ...r, _month: month });
      }
    }
  }

  function installHooks() {
    if (S.installed) return;
    S.installed = true;

    const origFetch = window.fetch;
    window.fetch = function (...args) {
      const p = origFetch.apply(this, args);
      p.then((res) => res.clone().json().then(absorb).catch(() => {})).catch(() => {});
      return p;
    };

    const XO = XMLHttpRequest.prototype.open;
    const XS = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u) {
      this.__grabUrl = u;
      return XO.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
      this.addEventListener('load', () => {
        try {
          if (String(this.__grabUrl || '').indexOf('GetDealRec') >= 0) {
            absorb(JSON.parse(this.responseText));
          }
        } catch (_) {}
      });
      return XS.apply(this, arguments);
    };
  }

  // ------------------------------------------------------------ 模拟点击
  function tap(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const opt = {
      bubbles: true, cancelable: true, view: window,
      clientX: r.x + Math.max(r.width / 2, 1), clientY: r.y + Math.max(r.height / 2, 1),
    };
    for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      const Ev = (t.startsWith('pointer') && window.PointerEvent) ? window.PointerEvent : MouseEvent;
      try { el.dispatchEvent(new Ev(t, opt)); } catch (_) {}
    }
    return true;
  }

  function candidates(text, limit = 3) {
    const out = [];
    for (const el of document.querySelectorAll('*')) {
      if (el.children.length > 2) continue;
      if (el.textContent.trim() !== text) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) continue;
      out.push(el);
      if (out.length >= limit) break;
    }
    return out;
  }

  async function retrigger() {
    const base = S.captured.size;

    // 策略一：切筛选 tab（全部 / 钱包），这是最可能重载列表的入口
    for (const t of ['钱包', '全部', '钱包', '全部']) {
      for (const el of candidates(t)) { tap(el); await sleep(350); }
      await sleep(1200);
      if (S.captured.size > base) return true;
    }

    // 策略二：打开时间范围下拉，换成别的选项再换回来
    const titles = [...document.querySelectorAll(
      '.van-dropdown-menu__title, [class*="dropdown"] [class*="title"], [class*="select"] [class*="title"]')];
    for (const t of titles) {
      tap(t);
      await sleep(900);
      const opts = [...document.querySelectorAll(
        '.van-dropdown-item .van-cell, .van-popup .van-cell, [class*="dropdown"] li, [class*="option"] li')];
      const other = opts.find((o) => o.textContent.trim() && o.textContent.trim() !== '本月');
      if (other) { tap(other); await sleep(1500); if (S.captured.size > base) return true; }
      const cur = opts.find((o) => /本月/.test(o.textContent) && o.textContent.trim().length < 12);
      if (cur) { tap(cur); await sleep(1500); if (S.captured.size > base) return true; }
      tap(t);
      await sleep(400);
    }
    return S.captured.size > base;
  }

  // ------------------------------------------------------------ 滚动收集
  async function collect() {
    let lastSize = -1, idle = 0;
    for (let i = 0; i < 60; i++) {
      window.scrollTo(0, document.body.scrollHeight);
      const sc = document.scrollingElement || document.documentElement;
      sc.scrollTop = sc.scrollHeight;
      const target = document.querySelector('.van-list, .scroll-view, main, #app') || document.body;
      target.dispatchEvent(new WheelEvent('wheel', {
        deltaY: 2000, bubbles: true, cancelable: true, view: window,
      }));
      await sleep(1300);

      if (S.captured.size === lastSize) {
        idle += 1;
        if (idle >= 3) break;
      } else {
        idle = 0;
        lastSize = S.captured.size;
        log(`已收集 ${S.captured.size} 笔`);
      }
    }
  }

  // ------------------------------------------------------------ 导出 CSV
  // 「第三方支付平台转账」= 微信/支付宝充值进校园卡，必须标成「充值」，
  // 否则会和微信/支付宝那边的付款重复计一次支出。
  const KIND_MAP = { '消费': '消费', '第三方支付平台转账': '充值' };
  const pad = (n) => String(n).padStart(2, '0');

  function exportCsv() {
    if (!S.captured.size) {
      warn('一笔都没抓到。请确认：已登录、停在账单页、列表已经显示出流水。');
      return null;
    }
    const rows = [];
    const now = new Date();
    for (const r of S.captured.values()) {
      let year = now.getFullYear(), month = now.getMonth() + 1;
      const m = /(\d{4})\D*(\d{1,2})/.exec(String(r._month || ''));
      if (m) { year = +m[1]; month = +m[2]; }
      const dm = /(\d{1,2})/.exec(String(r.dealDate || '1'));
      const day = dm ? +dm[1] : 1;
      const kind = KIND_MAP[r.feeNumStr] || r.feeNumStr || '消费';
      rows.push({
        t: `${year}-${pad(month)}-${pad(day)} ${String(r.dealTime || '00:00:00')}`,
        kind,
        shop: (r.businessName || (kind === '充值' ? '微信/支付宝充值' : ''))
          .replace(/[",\n]/g, ' '),
        amount: Math.abs(Number(r.money || 0)).toFixed(2),
      });
    }
    rows.sort((a, b) => (a.t < b.t ? 1 : -1));

    const csv = '\ufeff' + '交易时间,交易类型,商户名称,交易金额,余额\r\n'
      + rows.map((r) => `${r.t},${r.kind},${r.shop},${r.amount},`).join('\r\n');

    const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
    const name = `校园卡流水_${stamp}.csv`;
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 3000);

    const consume = rows.filter((r) => r.kind === '消费').length;
    log(`已下载 ${name}：共 ${rows.length} 笔（消费 ${consume} / 充值 ${rows.length - consume}）`);
    console.log(`%c最新一笔：${rows[0].t}　最早一笔：${rows[rows.length - 1].t}`,
      'color:#333;font-size:13px');
    return { name, count: rows.length, newest: rows[0].t };
  }

  // ------------------------------------------------------------ 主流程
  async function run(isRerun) {
    if (S.running) { warn('正在运行中，请稍候'); return; }
    S.running = true;
    installHooks();

    if (!isRerun) {
      log('正在尝试自动补齐首屏（首屏请求早于本脚本安装）…');
      const ok = await retrigger();

      if (ok) {
        log(`首屏已补齐，当前 ${S.captured.size} 笔`);
      } else {
        // 实测：手动点一次筛选是确定性有效的（切换会让列表重新从第 1 页请求）。
        // 所以脚本在这里等用户操作，而不是让他再敲一条命令。
        warn('需要你手动配合一步：请在 30 秒内，点顶部「钱包」筛选，再点回「全部」。');
        console.log('%c（这一步会让列表重新从第 1 页加载，钩子已装好，能抓到首屏）',
          'color:#333;font-size:12px');
        const before = S.captured.size;
        for (let i = 0; i < 60; i++) {
          await sleep(500);
          if (S.captured.size > before) {
            log('检测到列表已重新加载，继续收集');
            break;
          }
          if (i === 59) {
            warn('30 秒内没检测到新数据，将按已收集的内容导出。'
              + '仍想补全的话：手动切一次筛选后执行 __campusGrabAgain()');
          }
        }
      }
    }

    log('开始自动滚动加载…（期间请不要操作页面）');
    await collect();

    const result = exportCsv();
    S.running = false;

    if (result) {
      console.log('%c%s',
        'color:#0a0;font-weight:bold;font-size:13px',
        '核对方法：看页面上最新一笔的日期时间，是否等于上面「最新一笔」。');
      console.warn('%c如果页面上最新一笔比它更新，说明首屏没抓到。补救两步：\n'
        + '  ① 手动点顶部「钱包」筛选，再点回「全部」（列表会重新从第 1 页加载）\n'
        + '  ② 在控制台执行  __campusGrabAgain()\n'
        + '  它会带着已有数据继续收集，并重新导出一份完整的 CSV。',
      'color:#f80;font-size:12px');
    }
  }

  // 补齐首屏后重新收集 + 重新导出（用户手动切换筛选之后调用）
  window.__campusGrabAgain = () => run(true);

  if (S.captured.size > 0) {
    log(`检测到已收集 ${S.captured.size} 笔，继续累积（不会重复）`);
  }
  run(false);
})();
