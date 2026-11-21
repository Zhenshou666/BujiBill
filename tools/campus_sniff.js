/* ============================================================
 * 一卡通账单接口嗅探脚本
 *
 * 用法：
 *   1. 浏览器打开 https://etcard.hzcu.edu.cn:8088/... 并登录（停在账单页）
 *   2. 按 F12 → Console（控制台）
 *   3. 把本文件全部内容粘贴进去，回车
 *   4. 按提示操作页面：刷新 → 切换「本月」下拉 → 点开任意一笔详情
 *   5. 执行 __dumpSniff()，把打印出来的表格复制给开发同学
 *
 * 安全说明：
 *   - 只记录「请求路径」和「响应里有哪些字段名」，**不读取、不打印任何字段值**
 *   - 不会上传任何数据，不修改页面行为
 *   - 刷新页面即失效（不持久化）
 * ============================================================ */
(() => {
  if (window.__sniffInstalled) {
    console.log('%c嗅探已在运行，直接执行 __dumpSniff() 即可', 'color:#f80');
    return;
  }
  window.__sniffInstalled = true;

  const store = new Map();          // path -> { count, method, sample }

  /** 只取「结构」：对象给键名，数组给第一项的键名，原始值给类型 */
  function shape(v, depth = 0) {
    if (depth > 5) return '…';
    if (v === null) return 'null';
    if (Array.isArray(v)) {
      return v.length ? [`len=${v.length}`, shape(v[0], depth + 1)] : ['empty[]'];
    }
    if (typeof v === 'object') {
      const o = {};
      for (const k of Object.keys(v).slice(0, 40)) o[k] = shape(v[k], depth + 1);
      return o;
    }
    if (typeof v === 'string') {
      // 只报「大概是什么」，不回显内容：纯数字串 / 日期样式 / 其他
      if (/^\d{4}-\d{2}-\d{2}/.test(v)) return 'string(date)';
      if (/^-?\d+(\.\d+)?$/.test(v)) return 'string(number)';
      return `string(len=${v.length})`;
    }
    return typeof v;
  }

  function record(url, method, json) {
    try {
      const path = String(url).split('?')[0].split('#')[0];
      if (!/api|bill|jf|consume|trade|card|query|list|detail/i.test(path)) return;
      const e = store.get(path) || { count: 0, method, sample: null };
      e.count += 1;
      if (!e.sample) e.sample = shape(json);
      store.set(path, e);
    } catch (_) { /* 静默 */ }
  }

  // ---- hook fetch ----
  const origFetch = window.fetch;
  window.fetch = function (...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url);
    const method = (args[1] && args[1].method) || 'GET';
    const p = origFetch.apply(this, args);
    p.then((r) => {
      r.clone().json().then((j) => record(url, method, j)).catch(() => {});
    }).catch(() => {});
    return p;
  };

  // ---- hook XHR ----
  const XO = XMLHttpRequest.prototype.open;
  const XS = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    this.__sniffUrl = u;
    this.__sniffMethod = m;
    return XO.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('load', () => {
      try { record(this.__sniffUrl, this.__sniffMethod, JSON.parse(this.responseText)); }
      catch (_) { /* 不是 JSON 就算了 */ }
    });
    return XS.apply(this, arguments);
  };

  window.__dumpSniff = () => {
    const rows = [...store.entries()].map(([path, e]) => ({
      请求路径: path,
      方法: e.method,
      次数: e.count,
      响应结构: JSON.stringify(e.sample),
    }));
    if (!rows.length) {
      console.log('%c还没抓到接口。请在页面上做点操作：刷新 / 切换月份 / 点开一笔详情', 'color:#f80');
      return [];
    }
    console.table(rows);
    console.log('%c把上面这张表截图或复制给开发同学即可（不含任何金额与商户名）', 'color:#0a0;font-weight:bold');
    return rows;
  };

  console.log(
    '%c✅ 嗅探已启动\n%c现在请依次做：\n  1) 刷新页面\n  2) 点「本月」下拉，切一次时间范围\n  3) 点开任意一笔交易看详情\n  4) 回到控制台执行：__dumpSniff()',
    'color:#0a0;font-weight:bold;font-size:14px',
    'color:#333;font-size:12px'
  );
})();
