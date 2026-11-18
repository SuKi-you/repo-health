const $ = (id) => document.getElementById(id);

const GREEN = "#3ddc84";
const RED = "#ff5a5f";

const form = $("form");
const input = $("url");
const startBtn = $("start");
const errorBox = $("error");
const search = $("search");
const result = $("result");
const metricsBox = $("metrics");
const toggleBtn = $("toggle");

let current = null;

function human(n) {
  if (n === null || n === undefined) return "缺";
  if (n >= 1e8) return (n / 1e8).toFixed(1) + " 亿";
  if (n >= 1e4) return Math.round(n / 1e4) + " 万";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + " 千";
  return String(Math.round(n));
}

function days(v) { return v === null || v === undefined ? "缺" : v + " 天"; }
function pct(v) { return v === null || v === undefined ? "缺" : (v * 100).toFixed(0) + "%"; }
function signed(v) { return v === null || v === undefined ? "缺" : (v >= 0 ? "+" : "") + (v * 100).toFixed(0) + "%"; }

function mix(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const out = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return "rgb(" + out.join(",") + ")";
}

function drawActivity(el, weeks, color) {
  if (!weeks || !weeks.length) {
    el.innerHTML = '<div class="empty">GitHub 仍在计算 commit 数据，稍后重试</div>';
    return { active: 0, total: 0 };
  }

  const totals = weeks.map((w) => w.total || 0);
  const peak = Math.max(...totals, 1);
  const active = totals.filter((t) => t > 0).length;
  const total = totals.reduce((a, b) => a + b, 0);

  const W = 560, H = 58;
  const n = totals.length;
  const gap = 0.32;
  const cell = W / (n * (1 + gap));

  const rects = totals.map((v, i) => {
    const fill = v === 0 ? "#1a231e" : mix("#16211b", color, 0.28 + 0.72 * (v / peak));
    const x = i * cell * (1 + gap);
    return `<rect x="${x.toFixed(2)}" y="0" width="${cell.toFixed(2)}" height="${H}" fill="${fill}"><title>${v} 次提交</title></rect>`;
  }).join("");

  el.innerHTML = `
    <div class="big-num">${active} / ${n}</div>
    <div class="big-sub">周有提交　·　合计 ${total} 次</div>
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:58px;margin-top:20px">${rects}</svg>
    <div class="hint">一格 = 一周　·　灰色表示该周没有任何提交</div>
  `;
  return { active, total };
}

function drawDownloads(el, downloads, color) {
  if (!downloads || !downloads.length) {
    el.innerHTML = '<div class="empty">该项目不在 PyPI 上，无下载数据</div>';
    return 0;
  }

  const values = downloads.map((d) => d[1]);
  const dates = downloads.map((d) => d[0]);
  const total = values.reduce((a, b) => a + b, 0);
  const W = 660, H = 230, pad = 8;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = (W - 2 * pad) / (values.length - 1);

  const pts = values.map((v, i) => {
    const x = pad + i * step;
    const y = H - pad - ((v - min) / span) * (H - 2 * pad);
    return [x, y];
  });

  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)} ${H - pad} L${pts[0][0].toFixed(1)} ${H - pad} Z`;
  const gid = "g" + Math.random().toString(36).slice(2, 8);

  el.innerHTML = `
    <div class="card-head">
      <span class="chart-total">181 天合计 ${human(total)} 次</span>
    </div>
    <div class="chart-wrap">
      <svg viewBox="0 0 ${W} ${H}" style="height:230px">
        <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.22"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient></defs>
        <path d="${area}" fill="url(#${gid})"/>
        <path d="${line}" fill="none" stroke="${color}" stroke-width="2.2"
              stroke-linejoin="round" stroke-linecap="round"/>
        <g class="cursor" style="opacity:0">
          <line class="cursor-line" x1="0" y1="0" x2="0" y2="${H}"
                stroke="${color}" stroke-opacity="0.5" stroke-dasharray="3 4" stroke-width="1"/>
          <circle class="cursor-dot" r="4.5" fill="${color}" stroke="#0f1512" stroke-width="2"/>
        </g>
      </svg>
      <div class="tip" hidden></div>
    </div>
  `;

  const svg = el.querySelector("svg");
  const cursor = el.querySelector(".cursor");
  const cursorLine = el.querySelector(".cursor-line");
  const cursorDot = el.querySelector(".cursor-dot");
  const tip = el.querySelector(".tip");

  function move(event) {
    const box = svg.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * W;
    let index = Math.round((x - pad) / step);
    index = Math.max(0, Math.min(values.length - 1, index));

    const [px, py] = pts[index];
    cursor.style.opacity = 1;
    cursorLine.setAttribute("x1", px);
    cursorLine.setAttribute("x2", px);
    cursorDot.setAttribute("cx", px);
    cursorDot.setAttribute("cy", py);

    tip.hidden = false;
    tip.innerHTML = `<span class="tip-date">${dates[index]}</span><span class="tip-val">${human(values[index])} 次</span>`;

    const left = (px / W) * box.width;
    const top = (py / H) * box.height;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }

  svg.addEventListener("mousemove", move);
  svg.addEventListener("touchmove", (e) => {
    if (e.touches[0]) move(e.touches[0]);
  }, { passive: true });
  svg.addEventListener("mouseleave", () => {
    cursor.style.opacity = 0;
    tip.hidden = true;
  });

  return total;
}

function metricCards(m) {
  const items = [
    ["发版距今", days(m.release_age)],
    ["4 周周均 commit", m.commits_4w === null ? "缺" : m.commits_4w.toFixed(1)],
    ["周下载量", m.dl_week === null ? "缺" : human(m.dl_week)],
    ["下载 4 周趋势", signed(m.dl_trend)],
    ["issue 中位关闭", days(m.median_close)],
    ["未关闭占比", pct(m.unclosed_ratio)],
    ["老 issue 滞留", days(m.stuck_days)],
    ["top1 贡献者", pct(m.top1_share)],
    ["归档状态", m.archived ? "是" : "否"],
    ["issue 样本跨度", days(m.sample_span)],
    ["周环比噪声", m.dl_noise === null || m.dl_noise === undefined ? "缺" : "±" + (m.dl_noise * 100).toFixed(1) + "%"],
    ["主语言", m.language || "缺"],
  ];

  metricsBox.innerHTML = items.map(([k, v]) => `
    <div class="metric">
      <div class="k">${k}</div>
      <div class="v${v === "缺" ? " na" : ""}">${v}</div>
    </div>
  `).join("");
}

function render(data) {
  current = data;
  const color = data.verdict === "健康" ? GREEN : RED;
  document.documentElement.style.setProperty("--accent", color);

  $("repo").textContent = data.repo;
  $("verdict").textContent = data.verdict;

  drawActivity($("activity"), data.series.weeks, color);
  drawDownloads($("downloads"), data.series.downloads, color);
  metricCards(data.metrics);

  metricsBox.hidden = true;
  toggleBtn.classList.remove("on");
  toggleBtn.textContent = "指标数据";
  result.classList.remove("compact");

  const stamp = new Date().toLocaleDateString("zh-CN");
  $("stamp").textContent = `数据生成于 ${stamp}　·　${data.cached ? "本周缓存" : "实时分析"}`;

  search.hidden = true;
  result.hidden = false;
}

async function analyze(url) {
  errorBox.hidden = true;
  startBtn.disabled = true;
  startBtn.textContent = "分析中…";

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || "分析失败");
    render(data);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.hidden = false;
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = "START";
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const url = input.value.trim();
  if (!url) {
    errorBox.textContent = "请输入仓库链接";
    errorBox.hidden = false;
    return;
  }
  analyze(url);
});

toggleBtn.addEventListener("click", () => {
  const open = metricsBox.hidden;
  metricsBox.hidden = !open;
  toggleBtn.classList.toggle("on", open);
  toggleBtn.textContent = open ? "收起指标" : "指标数据";
  result.classList.toggle("compact", open);
});

$("again").addEventListener("click", () => {
  result.hidden = true;
  search.hidden = false;
  input.value = "";
  input.focus();
});
