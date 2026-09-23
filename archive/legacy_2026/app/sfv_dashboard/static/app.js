/* ────────────────── helpers ────────────────── */
const fmtInt = v => v == null ? '—' : Math.round(v).toLocaleString('ru-RU');
const fmtRub = v => v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽';
const fmtPct = (v, d=1) => v == null || isNaN(v) ? '—' : (v * 100).toFixed(d) + '%';
const fmtPctRaw = (v, d=1) => v == null || isNaN(v) ? '—' : Number(v).toFixed(d) + '%';
const fmtNum = (v, d=1) => v == null || isNaN(v) ? '—' : Number(v).toLocaleString('ru-RU', {maximumFractionDigits: d});

const PLOTLY_LAYOUT_BASE = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: {family:'IBM Plex Sans', size: 11, color:'#e6edf3'},
  margin: {l: 60, r: 30, t: 30, b: 50},
  xaxis: {gridcolor: '#30363d', zerolinecolor: '#30363d', tickfont: {color:'#8b949e'}},
  yaxis: {gridcolor: '#30363d', zerolinecolor: '#30363d', tickfont: {color:'#8b949e'}},
  legend: {orientation: 'h', y: -0.18, x: 0.5, xanchor: 'center',
           font: {color: '#e6edf3', size: 11}, bgcolor: 'rgba(0,0,0,0)'},
  hoverlabel: {bgcolor:'#1c2333', bordercolor:'#58a6ff', font:{color:'#e6edf3', family:'IBM Plex Sans'}},
};
const PLOTLY_CONFIG = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ['lasso2d','select2d','autoScale2d','toggleSpikelines'],
  locale: 'ru',
};

const CAT_COLORS = {
  'Газировка':'#58a6ff','Сэндвич':'#f85149','Прочее':'#8b949e',
  'Горячее блюдо':'#f0883e','Чай':'#bc8cff','Снэк':'#d29922',
  'Кофе':'#39d2c0','Пиво':'#ffa657','Сок':'#a371f7','Десерт':'#ff8c8c',
  'Вода негаз':'#3fb950','Сливки/доп':'#7d8590'
};
const catColor = c => CAT_COLORS[c] || '#8b949e';

/* ────────────────── state ────────────────── */
const state = {
  filters: { date_from: '', date_to: '', flight_out: '', item_category: '', item_sku: '' },
  lookups: null,
};

function buildQS(extra = {}) {
  const all = { ...state.filters, ...extra };
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(all)) {
    if (v !== '' && v != null) usp.append(k, v);
  }
  return usp.toString();
}

async function api(path, extra = {}) {
  const qs = buildQS(extra);
  const url = '/api' + path + (qs ? '?' + qs : '');
  const r = await fetch(url);
  if (!r.ok) throw new Error(`API ${path} → HTTP ${r.status}`);
  return r.json();
}

/* ────────────────── overlay ────────────────── */
let _loadingCounter = 0;
function loadingOn(label = 'обновление...') {
  _loadingCounter++;
  const o = document.getElementById('overlay');
  document.getElementById('overlay-text').textContent = label;
  o.classList.add('on');
}
function loadingOff() {
  _loadingCounter = Math.max(0, _loadingCounter - 1);
  if (_loadingCounter === 0) document.getElementById('overlay').classList.remove('on');
}

/* ────────────────── tabs ────────────────── */
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
  document.querySelectorAll('.view').forEach(x => x.classList.remove('on'));
  t.classList.add('on');
  document.getElementById('view-' + t.dataset.view).classList.add('on');
  window.dispatchEvent(new Event('resize'));
}));

/* ────────────────── filter UI ────────────────── */
function readFilters() {
  state.filters = {
    date_from: document.getElementById('f-date-from').value,
    date_to:   document.getElementById('f-date-to').value,
    flight_out:document.getElementById('f-flight').value,
    item_category: document.getElementById('f-cat').value,
    item_sku:  document.getElementById('f-sku').value,
  };
  const parts = [];
  if (state.filters.date_from || state.filters.date_to)
    parts.push(`${state.filters.date_from || '...'} → ${state.filters.date_to || '...'}`);
  if (state.filters.flight_out) parts.push(`рейс ${state.filters.flight_out}`);
  if (state.filters.item_category) parts.push(state.filters.item_category);
  if (state.filters.item_sku) parts.push(state.filters.item_sku);
  document.getElementById('applied-info').textContent = parts.length ? 'фильтры: ' + parts.join(' · ') : 'фильтры не заданы';
}
function resetFilters() {
  ['f-date-from','f-date-to'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('f-flight').value = '';
  document.getElementById('f-cat').value = '';
  document.getElementById('f-sku').value = '';
}
document.getElementById('btn-apply').addEventListener('click', () => {
  readFilters();
  refreshAll();
});
document.getElementById('btn-reset').addEventListener('click', () => {
  resetFilters();
  readFilters();
  refreshAll();
});

/* ────────────────── lookups + bootstrap ────────────────── */
async function loadLookups() {
  state.lookups = await api('/lookups');
  const fl = document.getElementById('f-flight');
  state.lookups.flights.forEach(r => {
    const o = document.createElement('option');
    o.value = r.flight_out; o.textContent = `${r.flight_out} (${r.n})`;
    fl.appendChild(o);
  });
  const cat = document.getElementById('f-cat');
  state.lookups.categories.forEach(r => {
    const o = document.createElement('option');
    o.value = r.item_category; o.textContent = `${r.item_category} (${r.n})`;
    cat.appendChild(o);
  });
  const sku = document.getElementById('f-sku');
  state.lookups.skus.forEach(r => {
    const o = document.createElement('option');
    o.value = r.item_sku;
    o.textContent = `${r.item_sku} · ${r.item_name || ''}`.slice(0, 60);
    sku.appendChild(o);
  });
  const rng = state.lookups.date_range;
  if (rng) {
    document.getElementById('f-date-from').min = rng.dmin;
    document.getElementById('f-date-from').max = rng.dmax;
    document.getElementById('f-date-to').min = rng.dmin;
    document.getElementById('f-date-to').max = rng.dmax;
  }
}

async function checkHealth() {
  try {
    const h = await api('/health');
    document.getElementById('live-badge').textContent = `CH ${h.ch_version} · ${h.rows.toLocaleString('ru-RU')} строк`;
  } catch (e) {
    const b = document.getElementById('live-badge');
    b.textContent = 'CH offline'; b.classList.add('err');
  }
}

/* ────────────────── KPI ────────────────── */
async function renderKpi() {
  const k = await api('/kpi');
  const sub = `Период <b>${k.dmin || '—'}</b> → <b>${k.dmax || '—'}</b> · ` +
              `${(+k.shipments || 0).toLocaleString('ru-RU')} накладных, ${k.uniq_sku} SKU, ${k.uniq_flights} рейсов`;
  document.getElementById('sub-line').innerHTML = sub;

  const st_pct = k.sell_through != null ? +k.sell_through * 100 : null;
  const ret_pct = k.return_rate != null ? +k.return_rate * 100 : null;
  const days_total = k.dmin && k.dmax ? Math.round((new Date(k.dmax) - new Date(k.dmin)) / 86400000) + 1 : 0;
  const days_present = +k.days_present || 0;
  const cov = days_total ? days_present / days_total * 100 : 0;
  const missing_days = days_total - days_present;

  const cards = [
    {l:'Выручка',          v:fmtRub(k.revenue), d:`за ${days_present} дн.`},
    {l:'Загружено',        v:fmtInt(k.loaded),  d:'единиц на борт'},
    {l:'Продано',          v:fmtInt(k.sold),    d:'покупок пассажиров'},
    {l:'Sell-through',     v:st_pct == null ? '—' : st_pct.toFixed(1)+'%',
      d:'продано / загружено',
      cls: st_pct < 30 ? 'warn' : 'ok'},
    {l:'Возврат',          v:ret_pct == null ? '—' : ret_pct.toFixed(1)+'%',
      d:'не куплено, возвращено',
      cls: ret_pct > 60 ? 'bad' : (ret_pct > 40 ? 'warn' : 'ok')},
    {l:'Покрытие дней',    v:cov.toFixed(1)+'%',
      d:`${days_present}/${days_total}, дыр: ${missing_days}`,
      cls: missing_days > 0 ? 'warn' : 'ok'},
    {l:'Σ Средн. чек/ед.', v:k.avg_check_per_unit ? Math.round(k.avg_check_per_unit) + ' ₽' : '—',
      d:'выручка / проданная единица'},
    {l:'Σ Средн. накл.',   v:k.avg_rev_per_ship ? fmtRub(k.avg_rev_per_ship) : '—',
      d:'выручка / накладную'},
    {l:'Возвращено, ед.',  v:fmtInt(k.returned), d:'товаров на склад'},
  ];
  document.getElementById('kpi-grid').innerHTML = cards.map(c =>
    `<div class="metric ${c.cls||''}"><div class="ml">${c.l}</div>` +
    `<div class="mv">${c.v}</div><div class="md">${c.d}</div></div>`
  ).join('');
}

/* ────────────────── weekly ────────────────── */
async function renderWeekly() {
  const w = await api('/weekly');
  const x = w.map(r => r.week_start);
  Plotly.newPlot('chart-weekly', [
    {
      type: 'bar', name: 'Выручка, ₽',
      x, y: w.map(r => +r.revenue || 0),
      marker: {color: '#58a6ff'},
      yaxis: 'y',
      hovertemplate: '%{x}<br>Выручка: %{y:,.0f} ₽<extra></extra>'
    },
    {
      type: 'scatter', mode: 'lines+markers', name: 'Sell-through, %',
      x, y: w.map(r => r.sell_through == null ? null : +r.sell_through * 100),
      line: {color: '#f0883e', width: 2}, marker: {size: 5},
      yaxis: 'y2',
      hovertemplate: '%{x}<br>Sell-through: %{y:.1f}%<extra></extra>'
    },
    {
      type: 'scatter', mode: 'lines+markers', name: 'Возврат, %',
      x, y: w.map(r => r.return_rate == null ? null : +r.return_rate * 100),
      line: {color: '#f85149', width: 2, dash: 'dot'}, marker: {size: 4},
      yaxis: 'y2',
      hovertemplate: '%{x}<br>Возврат: %{y:.1f}%<extra></extra>'
    },
  ], {
    ...PLOTLY_LAYOUT_BASE,
    showlegend: true,
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis, title: {text:'Выручка, ₽', font:{color:'#58a6ff'}}, tickformat: ',.0s'},
    yaxis2: {title:{text:'%', font:{color:'#f0883e'}}, overlaying:'y', side:'right',
             tickfont:{color:'#f0883e'}, gridcolor:'rgba(0,0,0,0)', range: [0, 100]},
    margin: {l:70, r:60, t:30, b:60},
  }, PLOTLY_CONFIG);
}

/* ────────────────── month×dow heatmap ────────────────── */
async function renderHeatmapMonthDow() {
  const h = await api('/heatmap/month-dow');
  const z = h.z_avg_revenue;
  const n = h.z_shipments;
  const txt = z.map((row, i) => row.map((v, j) =>
    v == null ? '—' : `${(v/1000).toFixed(1)}k\n(${n[i][j]})`));
  const flat = z.flat().filter(v => v != null);
  const vmax = flat.length ? Math.max(...flat) : 1;
  Plotly.newPlot('chart-heatmap-md', [{
    type:'heatmap', x: h.x, y: h.y, z,
    colorscale: [[0,'#0e3b66'],[0.25,'#1a5fa3'],[0.5,'#2f86d3'],[0.75,'#7cb8f0'],[1,'#d6ecff']],
    hoverongaps: false,
    hovertemplate: '%{y} %{x}<br>Средн ₽/накл: %{z:,.0f}<extra></extra>',
    colorbar: {title: {text:'₽/накл', font:{color:'#e6edf3', size:10}}, tickfont: {color:'#8b949e'}, tickformat:',.0s'}
  }], {
    ...PLOTLY_LAYOUT_BASE,
    xaxis: {...PLOTLY_LAYOUT_BASE.xaxis, side:'top', tickfont:{color:'#e6edf3', size:12}},
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis, autorange:'reversed', tickfont:{color:'#e6edf3', size:11}},
    margin: {l:80, r:30, t:50, b:30},
    annotations: h.y.flatMap((m, i) => h.x.map((d, j) => ({
      x: d, y: m, text: txt[i][j], showarrow: false, align: 'center',
      font: {size: 9, color: txt[i][j] === '—' ? '#8b949e'
                       : ((z[i][j] || 0) > vmax * 0.55 ? '#0d1117' : '#e6edf3')}
    }))),
  }, PLOTLY_CONFIG);
}

/* ────────────────── category × month heatmap ────────────────── */
async function renderCategoryMonth() {
  const h = await api('/heatmap/category-month');
  const flat = h.z.flat().filter(v => v != null && v > 0);
  const vmax = flat.length ? Math.max(...flat) : 1;
  const txt = h.z.map(row => row.map(v => v == null || v === 0 ? '' : (v/1000).toFixed(0) + 'k'));
  Plotly.newPlot('chart-cat-month', [{
    type:'heatmap', x: h.x, y: h.y, z: h.z,
    colorscale: [[0,'#0d1117'],[0.05,'#1a3a5c'],[0.3,'#2f86d3'],[0.7,'#f0883e'],[1,'#f85149']],
    hoverongaps: false,
    hovertemplate: '%{y} · %{x}<br>Выручка: %{z:,.0f} ₽<extra></extra>',
    colorbar: {title: {text:'₽', font:{color:'#e6edf3'}}, tickformat:',.0s', tickfont:{color:'#8b949e'}}
  }], {
    ...PLOTLY_LAYOUT_BASE,
    xaxis: {...PLOTLY_LAYOUT_BASE.xaxis, tickfont:{color:'#e6edf3', size:11}},
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis, automargin:true, tickfont:{color:'#e6edf3', size:11}},
    margin: {l:120, r:30, t:20, b:50},
    annotations: h.y.flatMap((c, i) => h.x.map((m, j) => ({
      x: m, y: c, text: txt[i][j], showarrow: false,
      font: {size: 8, color: (h.z[i][j] || 0) > vmax * 0.5 ? '#0d1117' : '#e6edf3'}
    }))),
  }, PLOTLY_CONFIG);
}

/* ────────────────── Pareto ────────────────── */
async function renderPareto() {
  const p = await api('/sku/pareto', {top: 30});
  const labels = p.map(r => `${r.item_sku} · ${(r.item_name || '').slice(0, 22)}`);
  Plotly.newPlot('chart-pareto', [
    {type:'bar', name:'Выручка SKU, ₽',
     x: labels, y: p.map(r => +r.revenue || 0),
     marker:{color: p.map(r => catColor(r.item_category)), line:{color:'#0d1117', width:0.5}},
     text: p.map(r => fmtRub(r.revenue)), textposition:'outside',
     textfont:{size:9, color:'#e6edf3'}, cliponaxis:false,
     hovertemplate:'<b>%{x}</b><br>Выручка: %{y:,.0f} ₽<br>Доля периода: %{customdata:.1%}<extra></extra>',
     customdata: p.map(r => +r.share || 0)},
    {type:'scatter', mode:'lines+markers', name:'Накопленная доля выручки, %',
     x: labels, y: p.map(r => +r.cum_share * 100),
     yaxis:'y2', line:{color:'#39d2c0', width:2.5, shape:'spline'}, marker:{size:6, color:'#39d2c0'},
     hovertemplate:'<b>%{x}</b><br>Накоплено: %{y:.1f}%<extra></extra>'},
  ], {
    ...PLOTLY_LAYOUT_BASE,
    showlegend: true,
    xaxis: {...PLOTLY_LAYOUT_BASE.xaxis, type:'category', tickangle: -40,
            automargin:true, tickfont:{size:10, color:'#e6edf3'}, fixedrange:false},
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis, title:{text:'Выручка, ₽', font:{color:'#58a6ff'}},
            tickformat:',.0s', rangemode:'tozero'},
    yaxis2: {title:{text:'Накопленная доля, %', font:{color:'#39d2c0'}}, overlaying:'y', side:'right',
             range:[0, 105], tickfont:{color:'#39d2c0'}, gridcolor:'rgba(0,0,0,0)', ticksuffix:'%'},
    margin: {l:70, r:70, t:30, b:160},
    shapes: [
      {type:'line', xref:'paper', yref:'y2', x0:0, x1:1, y0:80, y1:80,
       line:{color:'#39d2c0', dash:'dot', width:1}},
    ],
    annotations: [
      {xref:'paper', yref:'y2', x:0.99, y:82, xanchor:'right', text:'правило 80/20',
       showarrow:false, font:{color:'#39d2c0', size:10}}
    ]
  }, PLOTLY_CONFIG);
}

/* ────────────────── categories ────────────────── */
async function renderCategories() {
  const c = await api('/categories');
  const sorted = c.slice().sort((a, b) => +b.revenue - +a.revenue);
  Plotly.newPlot('chart-cat-rev', [{
    type:'bar', orientation:'h',
    x: sorted.map(r => +r.revenue),
    y: sorted.map(r => r.item_category),
    marker: {color: sorted.map(r => catColor(r.item_category))},
    text: sorted.map(r => fmtRub(r.revenue)), textposition: 'outside',
    textfont: {color:'#e6edf3', size:10},
    hovertemplate: '%{y}<br>Выручка: %{x:,.0f} ₽<extra></extra>'
  }], {
    ...PLOTLY_LAYOUT_BASE,
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis, automargin: true, tickfont:{size:11, color:'#e6edf3'}},
    xaxis: {...PLOTLY_LAYOUT_BASE.xaxis, tickformat: ',.0s'},
    margin:{l:120, r:80, t:10, b:40},
    showlegend: false,
  }, PLOTLY_CONFIG);

  Plotly.newPlot('chart-cat-st', [
    {type:'bar', name:'Sell-through, %', orientation:'h',
     x: sorted.map(r => (+r.sell_through || 0) * 100), y: sorted.map(r => r.item_category),
     marker:{color:'#3fb950'},
     text: sorted.map(r => fmtPct(r.sell_through, 1)), textposition: 'outside', textfont:{size:9, color:'#3fb950'},
     hovertemplate:'%{y}<br>Sell-through: %{x:.1f}%<extra></extra>'},
    {type:'bar', name:'Возврат, %', orientation:'h',
     x: sorted.map(r => +r.return_pct || 0), y: sorted.map(r => r.item_category),
     marker:{color:'#f85149'},
     text: sorted.map(r => fmtPctRaw(r.return_pct, 1)), textposition: 'outside', textfont:{size:9, color:'#f85149'},
     hovertemplate:'%{y}<br>Возврат: %{x:.1f}%<extra></extra>'},
  ], {
    ...PLOTLY_LAYOUT_BASE,
    barmode:'group',
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis, automargin: true, tickfont:{size:11, color:'#e6edf3'}},
    xaxis: {...PLOTLY_LAYOUT_BASE.xaxis, ticksuffix:'%', range:[0, 110]},
    margin:{l:120, r:30, t:10, b:60},
    showlegend: true,
  }, PLOTLY_CONFIG);
}

/* ────────────────── SKU scatter & table ────────────────── */
let SKU_SORT = {key:'revenue', asc:false};
let SKU_ROWS = [];
async function renderSku() {
  SKU_ROWS = await api('/sku/table');
  // Точки строим только для валидных SKU (avg_loaded > 0).
  const valid = SKU_ROWS.filter(r => +r.avg_loaded > 0);
  // Нормировка размера: max диаметр 60 px.
  const maxRev = Math.max(1, ...valid.map(r => +r.revenue || 0));
  const sizeRef = 2 * maxRev / (60 * 60);
  const xMax = Math.max(1, ...valid.map(r => +r.avg_loaded));
  const xMin = Math.min(...valid.map(r => +r.avg_loaded || 1));

  const byCat = {};
  valid.forEach(r => { (byCat[r.item_category] = byCat[r.item_category] || []).push(r); });
  const traces = Object.entries(byCat).map(([cat, arr]) => ({
    type:'scatter', mode:'markers+text', name: cat,
    x: arr.map(r => +r.avg_loaded),
    y: arr.map(r => (+r.sell_through || 0) * 100),
    text: arr.map(r => r.item_sku),
    textposition: 'top center',
    textfont:{size:9, color:'#c9d1d9'},
    marker:{
      size: arr.map(r => +r.revenue || 0),
      sizemode:'area', sizeref: sizeRef, sizemin: 6,
      color: catColor(cat),
      line:{color:'#0d1117', width:1},
      opacity: 0.85,
    },
    customdata: arr.map(r => [r.item_name || '', +r.revenue || 0, +r.loadings || 0,
                              +r.med_return_pct || 0, +r.soldout_share || 0]),
    hovertemplate:
      '<b>%{text}</b> · '+cat+'<br>'+
      '%{customdata[0]}<br>'+
      'Средн загрузка: %{x:.1f} шт/накл<br>'+
      'Sell-through: %{y:.1f}%<br>'+
      'Медиан возврат: %{customdata[3]:.1f}%<br>'+
      'Доля распродаж: %{customdata[4]:.1%}<br>'+
      'Загрузок: %{customdata[2]:,d}<br>'+
      'Выручка: %{customdata[1]:,.0f} ₽<extra></extra>',
  }));
  Plotly.newPlot('chart-sku-scatter', traces, {
    ...PLOTLY_LAYOUT_BASE,
    xaxis: {...PLOTLY_LAYOUT_BASE.xaxis,
            title:{text:'Средняя загрузка на накладную, шт. (лог-шкала)', font:{color:'#e6edf3'}},
            type:'log',
            range:[Math.log10(Math.max(0.5, xMin * 0.7)), Math.log10(xMax * 1.4)]},
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis,
            title:{text:'Sell-through (продано / загружено), %', font:{color:'#e6edf3'}},
            range:[-2, 102], ticksuffix:'%'},
    showlegend: true,
    legend: {...PLOTLY_LAYOUT_BASE.legend, y: -0.18, title:{text:'Категория · размер ∝ выручке'}},
    shapes: [
      // Полупрозрачные зоны квадрантов
      {type:'rect', xref:'paper', yref:'y', x0:0, x1:1, y0:70, y1:102,
       fillcolor:'rgba(63,185,80,0.05)', line:{width:0}},
      {type:'rect', xref:'paper', yref:'y', x0:0, x1:1, y0:-2, y1:25,
       fillcolor:'rgba(248,81,73,0.06)', line:{width:0}},
      {type:'line', xref:'paper', yref:'y', x0:0, x1:1, y0:70, y1:70,
       line:{color:'#3fb950', dash:'dot', width:1}},
      {type:'line', xref:'paper', yref:'y', x0:0, x1:1, y0:25, y1:25,
       line:{color:'#f85149', dash:'dot', width:1}},
    ],
    annotations: [
      {xref:'paper', x:0.99, y:97, yref:'y', text:'хорошо: высокий sell-through (≥70%) — кандидаты на доп. загрузку',
       showarrow:false, font:{color:'#3fb950', size:10}, xanchor:'right'},
      {xref:'paper', x:0.99, y:5, yref:'y', text:'плохо: sell-through ≤25% — перетарка, риск списаний',
       showarrow:false, font:{color:'#f85149', size:10}, xanchor:'right'},
    ],
    margin:{l:70, r:30, t:30, b:90},
  }, PLOTLY_CONFIG);

  renderSkuTable();
}

function renderSkuTable() {
  const sorted = SKU_ROWS.slice().sort((a, b) => {
    const k = SKU_SORT.key, dir = SKU_SORT.asc ? 1 : -1;
    let av = a[k], bv = b[k];
    if (av == null) return 1; if (bv == null) return -1;
    if (typeof av === 'string') return dir * av.localeCompare(bv);
    return dir * (Number(av) - Number(bv));
  });
  const tb = document.querySelector('#tbl-sku tbody');
  tb.innerHTML = sorted.map(r => {
    const st = +r.sell_through;
    const stCls = st > 0.7 ? 'cell-good' : (st < 0.2 ? 'cell-bad' : '');
    const rt = +r.med_return_pct;
    const rtCls = rt > 80 ? 'cell-bad' : (rt > 50 ? 'cell-warn' : 'cell-good');
    const ss = +r.soldout_share;
    const soCls = ss > 0.5 ? 'cell-bad' : '';
    return `<tr>
      <td>${r.item_sku || ''}</td>
      <td class="txt">${r.item_name || ''}</td>
      <td class="txt"><span class="tag" style="background:${catColor(r.item_category)}22;color:${catColor(r.item_category)}">${r.item_category || ''}</span></td>
      <td>${fmtInt(r.loadings)}</td>
      <td>${fmtNum(r.avg_loaded, 1)}</td>
      <td>${fmtNum(r.avg_sold, 1)}</td>
      <td class="${stCls}">${fmtPct(r.sell_through, 1)}</td>
      <td class="${rtCls}">${fmtPctRaw(r.med_return_pct, 1)}</td>
      <td class="${soCls}">${fmtPct(r.soldout_share, 1)}</td>
      <td>${fmtRub(r.revenue)}</td>
    </tr>`;
  }).join('');
  document.querySelectorAll('#tbl-sku th').forEach(th => {
    th.classList.toggle('sorted', th.dataset.key === SKU_SORT.key);
    th.classList.toggle('asc', th.dataset.key === SKU_SORT.key && SKU_SORT.asc);
  });
}
document.querySelectorAll('#tbl-sku th').forEach(th => th.addEventListener('click', () => {
  if (SKU_SORT.key === th.dataset.key) SKU_SORT.asc = !SKU_SORT.asc;
  else { SKU_SORT.key = th.dataset.key; SKU_SORT.asc = false; }
  renderSkuTable();
}));

/* ────────────────── flights ────────────────── */
let FLT_SORT = {key:'total_revenue', asc:false};
let FLT_ROWS = [];
async function renderFlights() {
  FLT_ROWS = await api('/flights/summary');
  // Топ-25 рейсов по совокупной выручке — иначе бары превращаются в гребень.
  const f = FLT_ROWS.slice()
    .filter(r => r.flight_out != null)
    .sort((a, b) => +b.total_revenue - +a.total_revenue)
    .slice(0, 25);
  const x = f.map(r => '№ ' + r.flight_out);
  Plotly.newPlot('chart-flights-bar', [
    {type:'bar', name:'Средн загрузка, ед/накл', x, y: f.map(r => +r.avg_loaded || 0),
     marker:{color:'#58a6ff'},
     hovertemplate:'Рейс %{x}<br>Загрузка: %{y:.1f} ед/накл<extra></extra>'},
    {type:'bar', name:'Средн продажа, ед/накл', x, y: f.map(r => +r.avg_sold || 0),
     marker:{color:'#3fb950'},
     hovertemplate:'Рейс %{x}<br>Продажа: %{y:.1f} ед/накл<extra></extra>'},
    {type:'scatter', mode:'markers', name:'Средн выручка/накл, ₽',
     x, y: f.map(r => +r.avg_revenue || 0),
     yaxis:'y2',
     marker:{size:10, color:'#f0883e', symbol:'diamond', line:{color:'#0d1117', width:1}},
     hovertemplate:'Рейс %{x}<br>Средн выручка: %{y:,.0f} ₽/накл<extra></extra>'},
  ], {
    ...PLOTLY_LAYOUT_BASE,
    barmode:'group',
    showlegend: true,
    xaxis:{...PLOTLY_LAYOUT_BASE.xaxis, type:'category',
           title:{text:'Топ-25 рейсов по совокупной выручке (out)', font:{color:'#e6edf3'}},
           tickangle:-40, tickfont:{color:'#e6edf3', size:10}, automargin:true},
    yaxis:{...PLOTLY_LAYOUT_BASE.yaxis,
           title:{text:'Среднее на накладную, ед', font:{color:'#58a6ff'}},
           rangemode:'tozero'},
    yaxis2:{title:{text:'Средн выручка/накл, ₽', font:{color:'#f0883e'}},
            overlaying:'y', side:'right', tickformat:',.0s',
            tickfont:{color:'#f0883e'}, gridcolor:'rgba(0,0,0,0)', rangemode:'tozero'},
    margin:{l:70, r:70, t:30, b:120},
  }, PLOTLY_CONFIG);

  renderFlightsTable();
}

function renderFlightsTable() {
  const rows = FLT_ROWS.slice().sort((a,b) => {
    const k = FLT_SORT.key, dir = FLT_SORT.asc ? 1 : -1;
    let av = a[k], bv = b[k];
    if (av == null) return 1; if (bv == null) return -1;
    return dir * (Number(av) - Number(bv));
  });
  document.querySelector('#tbl-flights tbody').innerHTML = rows.map(r => {
    const st = +r.sell_through;
    const stCls = st > 0.4 ? 'cell-good' : (st < 0.15 ? 'cell-bad' : '');
    const z = +r.z_st;
    const zCls = z < -1 ? 'cell-bad' : (z > 1 ? 'cell-good' : '');
    return `<tr>
      <td>${r.flight_out}</td>
      <td>${fmtInt(r.n)}</td>
      <td>${fmtNum(r.avg_loaded, 1)}</td>
      <td>${fmtNum(r.avg_sold, 1)}</td>
      <td class="${stCls}">${fmtPct(r.sell_through, 1)}</td>
      <td>${fmtPctRaw(r.avg_return, 1)}</td>
      <td>${fmtRub(r.avg_revenue)}</td>
      <td>${fmtRub(r.total_revenue)}</td>
      <td class="${zCls}">${fmtNum(r.z_st, 2)}</td>
    </tr>`;
  }).join('');
  document.querySelectorAll('#tbl-flights th').forEach(th => {
    th.classList.toggle('sorted', th.dataset.key === FLT_SORT.key);
    th.classList.toggle('asc', th.dataset.key === FLT_SORT.key && FLT_SORT.asc);
  });
}
document.querySelectorAll('#tbl-flights th').forEach(th => th.addEventListener('click', () => {
  if (FLT_SORT.key === th.dataset.key) FLT_SORT.asc = !FLT_SORT.asc;
  else { FLT_SORT.key = th.dataset.key; FLT_SORT.asc = false; }
  renderFlightsTable();
}));

async function renderFlightSkuHeat() {
  const h = await api('/flights/heatmap', {top_flights: 15, top_skus: 15, min_n: 10});
  const z = h.z_revenue;
  const n = h.z_n;
  const flat = z.flat().filter(v => v != null);
  const vmax = flat.length ? Math.max(...flat) : 1;
  const txt = z.map((row, i) => row.map((v, j) => v == null ? '—' : `${(v/1000).toFixed(0)}k\n(${n[i][j]})`));
  Plotly.newPlot('chart-flight-sku-heat', [{
    type:'heatmap',
    x: h.x, y: h.y.map(v => '№ ' + v), z,
    xtype:'array', ytype:'array',
    colorscale: [[0,'#0d1117'],[0.05,'#1a3a5c'],[0.3,'#2f86d3'],[0.7,'#f0883e'],[1,'#f85149']],
    hoverongaps: false,
    hovertemplate: 'Рейс %{y} · SKU %{x}<br>Выручка: %{z:,.0f} ₽<br>Пар наблюдений: %{customdata}<extra></extra>',
    customdata: n,
    colorbar: {title:{text:'Выручка, ₽', font:{color:'#e6edf3', size:10}},
               tickformat:',.0s', tickfont:{color:'#8b949e'}}
  }], {
    ...PLOTLY_LAYOUT_BASE,
    xaxis: {...PLOTLY_LAYOUT_BASE.xaxis, type:'category',
            title:{text:'SKU (топ по выручке)', font:{color:'#e6edf3'}},
            tickangle: -40, automargin:true, tickfont:{color:'#e6edf3', size:11}},
    yaxis: {...PLOTLY_LAYOUT_BASE.yaxis, type:'category',
            title:{text:'Рейс (out)', font:{color:'#e6edf3'}},
            automargin:true, tickfont:{color:'#e6edf3', size:11}},
    margin: {l:90, r:30, t:30, b:140},
    annotations: h.y.flatMap((fl, i) => h.x.map((s, j) => ({
      x: s, y: '№ ' + fl, text: txt[i][j], showarrow: false, align:'center',
      font: {size: 9, color: txt[i][j] === '—' ? '#3a3f47'
                       : ((z[i][j] || 0) > vmax * 0.55 ? '#0d1117' : '#e6edf3')}
    }))),
  }, PLOTLY_CONFIG);
}

/* ────────────────── patterns ────────────────── */
async function renderGaps() {
  const gaps = await api('/gaps');
  const wrap = document.getElementById('gaps');
  if (!gaps.length) {
    wrap.innerHTML = `<div class="metric ok"><div class="mv">Пробелов нет</div><div class="md">Все дни в выбранном периоде имеют накладные</div></div>`;
    return;
  }
  wrap.innerHTML = gaps.map(g =>
    `<div class="gap-card"><div class="gn">${g.start} → ${g.end} · ${g.days} дн.</div>
     <div class="gd">Период без единой накладной. Проверить источник (1С / Drive).</div></div>`
  ).join('');
}

async function renderDow() {
  const dow = (await api('/dow')).slice().sort((a, b) => +a.dow - +b.dow);
  const order = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
  const x = dow.map(r => r.dow_name);
  Plotly.newPlot('chart-dow', [
    {type:'bar', name:'Средн загрузка, ед/накл', x, y: dow.map(r => +r.avg_loaded),
     marker:{color:'#58a6ff'},
     text: dow.map(r => fmtNum(r.avg_loaded, 0)), textposition:'outside',
     textfont:{color:'#58a6ff', size:10}, cliponaxis:false,
     hovertemplate:'%{x}<br>Загрузка: %{y:.1f} ед/накл<extra></extra>'},
    {type:'bar', name:'Средн продажа, ед/накл', x, y: dow.map(r => +r.avg_sold),
     marker:{color:'#3fb950'},
     text: dow.map(r => fmtNum(r.avg_sold, 0)), textposition:'outside',
     textfont:{color:'#3fb950', size:10}, cliponaxis:false,
     hovertemplate:'%{x}<br>Продажа: %{y:.1f} ед/накл<extra></extra>'},
    {type:'scatter', mode:'lines+markers', name:'Средн выручка/накл, ₽', yaxis:'y2',
     x, y: dow.map(r => +r.avg_revenue),
     line:{color:'#f0883e', width:2.5, shape:'spline'}, marker:{size:8},
     hovertemplate:'%{x}<br>Выручка: %{y:,.0f} ₽/накл<extra></extra>'},
  ], {
    ...PLOTLY_LAYOUT_BASE, barmode:'group', showlegend: true,
    xaxis:{...PLOTLY_LAYOUT_BASE.xaxis, type:'category',
           categoryorder:'array', categoryarray: order,
           tickfont:{color:'#e6edf3', size:12}},
    yaxis:{...PLOTLY_LAYOUT_BASE.yaxis,
           title:{text:'Среднее на накладную, ед', font:{color:'#58a6ff'}},
           rangemode:'tozero'},
    yaxis2:{title:{text:'Средн выручка/накл, ₽', font:{color:'#f0883e'}},
            overlaying:'y', side:'right', tickformat:',.0s',
            tickfont:{color:'#f0883e'}, gridcolor:'rgba(0,0,0,0)', rangemode:'tozero'},
    margin: {l:70, r:70, t:30, b:80},
  }, PLOTLY_CONFIG);
}

async function renderMonthly() {
  const mon = await api('/monthly');
  Plotly.newPlot('chart-month', [
    {type:'bar', name:'Накладных', x: mon.map(r => r.month), y: mon.map(r => +r.n),
     marker:{color:'#264f78'}, hovertemplate:'%{x}<br>Накладных: %{y}<extra></extra>'},
    {type:'scatter', mode:'lines+markers', name:'Средн выручка/накл, ₽',
     x: mon.map(r => r.month), y: mon.map(r => +r.avg_revenue),
     yaxis:'y2', line:{color:'#f0883e', width:2}, marker:{size:6},
     hovertemplate:'%{x}<br>Выручка: %{y:,.0f} ₽<extra></extra>'},
    {type:'scatter', mode:'lines+markers', name:'Средн % возврата',
     x: mon.map(r => r.month), y: mon.map(r => +r.avg_return),
     yaxis:'y3', line:{color:'#f85149', width:2, dash:'dot'}, marker:{size:5},
     hovertemplate:'%{x}<br>Возврат: %{y:.1f}%<extra></extra>'},
  ], {
    ...PLOTLY_LAYOUT_BASE, showlegend: true,
    yaxis:{...PLOTLY_LAYOUT_BASE.yaxis, title:{text:'Накладных', font:{color:'#58a6ff'}}},
    yaxis2:{title:{text:'Выручка, ₽', font:{color:'#f0883e'}}, overlaying:'y', side:'right',
            tickformat:',.0s', tickfont:{color:'#f0883e'}, gridcolor:'rgba(0,0,0,0)'},
    yaxis3:{overlaying:'y', side:'right', position:0.93, showgrid:false,
            range:[0,100], tickfont:{color:'#f85149'}, ticksuffix:'%'},
    margin: {l:60, r:80, t:30, b:60},
  }, PLOTLY_CONFIG);
}

async function renderLifecycle() {
  // Сортируем так, чтобы свежие/долгоживущие SKU были вверху списка.
  const lc = (await api('/sku/lifecycle')).slice().sort((a, b) =>
    a.first_seen.localeCompare(b.first_seen));
  const labels = lc.map(r => `${r.item_sku} · ${(r.item_name || '').slice(0, 30)}`);
  // По одной линии на SKU: scatter с двумя точками (start, end) и mode='lines+markers'.
  // Группируем по категории чтобы вышла единая легенда.
  const seen = new Set();
  const traces = lc.map(r => {
    const lbl = `${r.item_sku} · ${(r.item_name || '').slice(0, 30)}`;
    const cat = r.item_category || 'Прочее';
    const showLegend = !seen.has(cat);
    seen.add(cat);
    const days = Math.max(1, (new Date(r.last_seen) - new Date(r.first_seen)) / 86400000 + 1);
    return {
      type:'scatter', mode:'lines+markers', name: cat,
      legendgroup: cat, showlegend: showLegend,
      x: [r.first_seen, r.last_seen],
      y: [lbl, lbl],
      line:{color: catColor(cat), width: 6},
      marker:{color: catColor(cat), size: 8, line:{color:'#0d1117', width:1}},
      hovertemplate:
        `<b>${r.item_sku}</b> · ${r.item_name || ''}<br>` +
        `Категория: ${cat}<br>` +
        `Период: ${r.first_seen} → ${r.last_seen} (${Math.round(days)} дн)<br>` +
        `Загрузок: ${(+r.loadings).toLocaleString('ru-RU')}<br>` +
        `Выручка: ${Math.round(+r.revenue || 0).toLocaleString('ru-RU')} ₽<extra></extra>`,
    };
  });
  Plotly.newPlot('chart-lifecycle', traces, {
    ...PLOTLY_LAYOUT_BASE,
    showlegend: true,
    legend: {...PLOTLY_LAYOUT_BASE.legend, y: -0.05, x: 0.5, xanchor:'center'},
    xaxis:{...PLOTLY_LAYOUT_BASE.xaxis, type:'date',
           title:{text:'Период присутствия SKU в накладных', font:{color:'#e6edf3'}}},
    yaxis:{...PLOTLY_LAYOUT_BASE.yaxis, type:'category',
           categoryorder:'array', categoryarray: labels,
           automargin:true, tickfont:{size:10, color:'#c9d1d9'}, autorange:'reversed'},
    margin:{l:280, r:30, t:20, b:80},
  }, PLOTLY_CONFIG);
}

async function renderOutlierWeeks() {
  const w = await api('/return-outliers', {threshold_z: 1.5});
  if (!w.length) {
    Plotly.newPlot('chart-outlier-weeks', [], {
      ...PLOTLY_LAYOUT_BASE,
      annotations: [{xref:'paper', yref:'paper', x:0.5, y:0.5,
                     text:'Аномальных недель не найдено (|Z| < 1.5)',
                     showarrow:false, font:{color:'#8b949e', size:13}}]
    }, PLOTLY_CONFIG);
    return;
  }
  // Делим на 2 группы — это даёт «настоящую» легенду.
  const high = w.filter(r => +r.z > 0);
  const low  = w.filter(r => +r.z <= 0);
  // Средний возврат за период (для пунктира): через высчитывание из z.
  // mean = return - z*std. Берём первый элемент и обратно вычисляем mean (приблизительно).
  // Проще — медиана return_rate всех известных недель не доступна; считаем как
  // взвешенный по элементам средний return, исключая outliers, через linear inverse:
  // mean ≈ avg(return - z*std). std неизвестен — пропустим, берём min(return) высоких vs max(return) низких.
  Plotly.newPlot('chart-outlier-weeks', [
    {type:'bar', name:'Z > 0 · аномально высокий возврат',
     x: high.map(r => r.week), y: high.map(r => (+r.return_rate || 0) * 100),
     marker:{color:'#f85149'},
     text: high.map(r => `Z=${(+r.z).toFixed(1)}`), textposition:'outside',
     textfont:{size:9, color:'#f85149'}, cliponaxis:false,
     hovertemplate:'Неделя %{x}<br>Возврат: %{y:.1f}% (выше нормы)<br>Накладных: %{customdata}<extra></extra>',
     customdata: high.map(r => +r.n)},
    {type:'bar', name:'Z < 0 · аномально низкий возврат (хорошо)',
     x: low.map(r => r.week), y: low.map(r => (+r.return_rate || 0) * 100),
     marker:{color:'#3fb950'},
     text: low.map(r => `Z=${(+r.z).toFixed(1)}`), textposition:'outside',
     textfont:{size:9, color:'#3fb950'}, cliponaxis:false,
     hovertemplate:'Неделя %{x}<br>Возврат: %{y:.1f}% (ниже нормы)<br>Накладных: %{customdata}<extra></extra>',
     customdata: low.map(r => +r.n)},
  ], {
    ...PLOTLY_LAYOUT_BASE,
    showlegend: true,
    xaxis:{...PLOTLY_LAYOUT_BASE.xaxis, type:'date',
           title:{text:'Неделя (понедельник)', font:{color:'#e6edf3'}}},
    yaxis:{...PLOTLY_LAYOUT_BASE.yaxis,
           title:{text:'Доля возврата, %', font:{color:'#e6edf3'}}, ticksuffix:'%',
           range:[0, 100]},
    margin:{l:70, r:20, t:30, b:80},
  }, PLOTLY_CONFIG);
}

/* ────────────────── refresh orchestrator ────────────────── */
async function refreshAll() {
  loadingOn('обновление виджетов...');
  try {
    await Promise.all([
      renderKpi(),
      renderWeekly(),
      renderHeatmapMonthDow(),
      renderCategoryMonth(),
      renderPareto(),
      renderCategories(),
      renderSku(),
      renderFlights(),
      renderFlightSkuHeat(),
      renderGaps(),
      renderDow(),
      renderMonthly(),
      renderLifecycle(),
      renderOutlierWeeks(),
    ]);
  } catch (e) {
    console.error(e);
    alert('Ошибка обновления: ' + e.message);
  } finally {
    loadingOff();
    document.getElementById('gen-stamp').textContent =
      ` · обновлено ${new Date().toLocaleString('ru-RU')}`;
  }
}

/* ────────────────── init ────────────────── */
(async () => {
  loadingOn('подключение к ClickHouse...');
  try {
    await checkHealth();
    await loadLookups();
    readFilters();
  } finally {
    loadingOff();
  }
  refreshAll();
})();
