/* ===========================================================
   CUSTOM FORMULA BUILDER
   =========================================================== */

var FORMULA_CATS = ['managed_money','swap_dealers','prod_merc','other_rept'];
var FORMULA_METRICS = ['long','short','spread','net','net_pct_oi','long_pct_oi','short_pct_oi','traders_long','traders_short','per_trader_l','per_trader_s'];
var FORMULA_CROP_TYPES = ['all','old','other'];
var FORMULA_OPS = ['+','-'];

var formulaChart = null;
var formulaPctileChart = null;
var formulaSeaChart = null;
var formulaZoomPct = 100;
var formulaPctZoomPct = 100;
var formulaSeaYrs = new Set();

function initFormulaTab(){
    populateFormulaCommoditySelect();
    if(document.getElementById('formula-terms').children.length === 0){
        addFormulaTerm();
    }
    loadSavedFormulas();
}

function populateFormulaCommoditySelect(){
    var sel = document.getElementById('formulaCommodity');
    if(!sel) return;
    sel.innerHTML = '<option value="">-- Select Commodity --</option>';
    if(!allBCOM.length) return;
    var cs = '';
    allBCOM.forEach(function(bc){
        if(bc.sector !== cs){
            cs = bc.sector;
            var og = document.createElement('optgroup');
            og.label = cs;
            sel.appendChild(og);
        }
        var o = document.createElement('option');
        o.value = bc.api;
        o.textContent = bc.name + ' (' + bc.ticker + ')';
        sel.lastChild.appendChild(o);
    });
}

function addFormulaTerm(){
    var container = document.getElementById('formula-terms');
    if(!container) return;
    var idx = container.children.length;
    var div = document.createElement('div');
    div.className = 'formula-term-row';
    div.dataset.index = idx;

    var opHtml = idx === 0 
        ? '<span class="op-badge" style="color:#64748b;">START</span>' 
        : '<select class="op-select" style="width:50px;text-align:center;font-weight:bold;">' + 
          FORMULA_OPS.map(function(o){return '<option value="' + o + '">' + o + '</option>';}).join('') + 
          '</select>';

    div.innerHTML = 
        opHtml +
        '<select class="cat-select">' + FORMULA_CATS.map(function(c){return '<option value="' + c + '">' + c.replace(/_/g,' ') + '</option>';}).join('') + '</select>' +
        '<select class="metric-select">' + FORMULA_METRICS.map(function(m){return '<option value="' + m + '"' + (m==='net'?' selected':'') + '>' + m.replace(/_/g,' ') + '</option>';}).join('') + '</select>' +
        '<select class="crop-select">' + FORMULA_CROP_TYPES.map(function(c){return '<option value="' + c + '"' + (c==='all'?' selected':'') + '>' + c + '</option>';}).join('') + '</select>' +
        (idx > 0 ? '<span class="remove-btn" onclick="this.parentElement.remove();updateFormulaPreview();">×</span>' : '');

    div.querySelectorAll('select').forEach(function(s){ s.addEventListener('change', updateFormulaPreview); });
    container.appendChild(div);
    updateFormulaPreview();
}

function getFormulaTerms(){
    var terms = [];
    document.querySelectorAll('#formula-terms .formula-term-row').forEach(function(term){
        var opSel = term.querySelector('.op-select');
        var op = opSel ? opSel.value : '+';
        var cat = term.querySelector('.cat-select').value;
        var metric = term.querySelector('.metric-select').value;
        var crop = term.querySelector('.crop-select').value;
        terms.push({ op: op, cat: cat, metric: metric, crop: crop, col: cat + '_' + metric });
    });
    return terms;
}

function updateFormulaPreview(){
    var terms = getFormulaTerms();
    var text = terms.map(function(t, i){
        var label = t.cat.replace(/_/g,' ') + ' ' + t.metric.replace(/_/g,' ') + ' (' + t.crop + ')';
        return i === 0 ? label : t.op + ' ' + label;
    }).join(' ');
    var span = document.querySelector('#formula-preview span');
    if(span) span.textContent = text || '—';
}

function computeFormulaSeries(rawData, terms){
    if(!rawData || !rawData.length || !terms.length) return [];

    var termData = terms.map(function(term){
        var p = procData(rawData, term.cat, term.crop);
        if(!p) return null;
        return { proc: p, metric: term.metric };
    });

    if(termData.some(function(t){ return t === null; })){
        console.warn('[Formula] Some terms could not be processed');
        return [];
    }

    var n = termData[0].proc.dates.length;
    var result = [];

    for(var i = 0; i < n; i++){
        var value = 0;

        for(var t = 0; t < terms.length; t++){
            var p = termData[t].proc;
            var m = termData[t].metric;
            var val = 0;

            switch(m){
                case 'long': val = p.long[i]; break;
                case 'short': val = p.short[i]; break;
                case 'spread': val = p.spread[i]; break;
                case 'net': val = p.net[i]; break;
                case 'net_pct_oi': val = p.nPct[i]; break;
                case 'long_pct_oi': val = p.lPct[i]; break;
                case 'short_pct_oi': val = p.sPct[i]; break;
                case 'traders_long': val = p.tL[i]; break;
                case 'traders_short': val = p.tS[i]; break;
                case 'per_trader_l': val = p.plL[i]; break;
                case 'per_trader_s': val = p.plS[i]; break;
                default: val = p.net[i];
            }

            if(t === 0){ value = val; }
            else { value = terms[t].op === '+' ? value + val : value - val; }
        }

        result.push({ date: p.dates[i].substring(0,10), value: value });
    }

    return result;
}

function calculatePercentiles(series, windowSize){
    return series.map(function(pt, i){
        var start = 0;
        if(windowSize && windowSize > 0){
            start = Math.max(0, i + 1 - windowSize);
        }
        var hist = series.slice(start, i + 1).map(function(s){ return s.value; });
        var below = hist.filter(function(v){ return v < pt.value; }).length;
        var equal = hist.filter(function(v){ return v === pt.value; }).length;
        var pct = ((below + 0.5 * equal) / hist.length) * 100;
        return { date: pt.date, value: pt.value, pctile: Math.round(pct * 10) / 10 };
    });
}

function updateFormulaCharts(){
    var terms = getFormulaTerms();
    var commApi = document.getElementById('formulaCommodity').value;
    var cropType = document.getElementById('formulaCropType').value || 'all';

    if(!terms.length || !commApi){
        if(formulaChart){ formulaChart.destroy(); formulaChart = null; }
        if(formulaPctileChart){ formulaPctileChart.destroy(); formulaPctileChart = null; }
        if(formulaSeaChart){ formulaSeaChart.destroy(); formulaSeaChart = null; }
        return;
    }

    if(!window._formulaRawCache) window._formulaRawCache = {};

    if(window._formulaRawCache[commApi]){
        renderAllFormulaCharts(window._formulaRawCache[commApi], terms);
    } else {
        showL(true, 'Loading formula data...');
        /* Pre-computed weekly series (cached in the browser); live CFTC API as fallback */
        COTStore.seriesForApi(commApi).then(function(ser){
            window._formulaRawCache[commApi] = staticRaw(ser, commApi);
            renderAllFormulaCharts(window._formulaRawCache[commApi], terms);
            showL(false);
        }).catch(function(){
        var ep = EP.combined;  // Formula tab always uses combined reports
        fetchT(ep + "?$where=" + liveWhere(commApi) + " AND report_date_as_yyyy_mm_dd >= '2006-01-01'&$order=report_date_as_yyyy_mm_dd ASC&$limit=10000", 20000)
        .then(function(r){ return r.json(); })
        .then(function(data){
            if(data.length > 0){
                window._formulaRawCache[commApi] = data;
                renderAllFormulaCharts(data, terms);
            } else {
                showE('No data returned for this commodity');
            }
            showL(false);
        })
        .catch(function(e){
            showE('Error fetching data: ' + e.message);
            showL(false);
        });
        });
    }
}

function renderAllFormulaCharts(rawData, terms){
    if(!rawData || !rawData.length) return;

    var series = computeFormulaSeries(rawData, terms);
    if(!series.length){
        showE('Could not compute formula - check that selected crop type has data');
        return;
    }

    renderFormulaValueChart(series, terms);
    renderFormulaPctileChart(series);
    renderFormulaSeasonalityChart(series);
}

function renderFormulaValueChart(series, terms){
    var dates = series.map(function(s){ return s.date; });
    var values = series.map(function(s){ return s.value; });

    var ctx1 = document.getElementById('formulaChart').getContext('2d');
    if(formulaChart) formulaChart.destroy();

    var isPct = terms.some(function(t){ return t.metric.indexOf('pct') !== -1; });

    formulaChart = new Chart(ctx1, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Formula Value',
                data: values,
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37,99,235,0.08)',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 5,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                zoom: {
                    pan: { enabled: true, mode: 'x' },
                    zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx){
                            var v = ctx.raw;
                            return 'Value: ' + (isPct ? v.toFixed(2) + '%' : v.toLocaleString(undefined, {maximumFractionDigits: 0}));
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 12, font: { size: 9 }, color: '#333' }
                },
                y: {
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    ticks: {
                        callback: function(v){
                            return isPct ? v.toFixed(1) + '%' : (Math.abs(v) >= 1000 ? (v/1000).toFixed(1) + 'k' : v);
                        },
                        font: { size: 9 }, color: '#333'
                    },
                    title: { display: true, text: isPct ? '%' : 'Contracts', font: { size: 10, weight: 'bold' }, color: '#333' }
                }
            }
        }
    });

    applyFormulaZoom();
}

function renderFormulaPctileChart(series){
    var showPctile = document.getElementById('showPctileToggle').checked;
    document.getElementById('formulaPctileBox').style.display = showPctile ? 'block' : 'none';

    if(!showPctile) return;

    var windowSel = document.getElementById('formulaPctileWindow').value;
    var windowSize = null;
    switch(windowSel){
        case '1yr': windowSize = 52; break;
        case '3yr': windowSize = 156; break;
        case '5yr': windowSize = 260; break;
        case '10yr': windowSize = 520; break;
        default: windowSize = null;
    }

    var pctileSeries = calculatePercentiles(series, windowSize);
    var dates = pctileSeries.map(function(s){ return s.date; });
    var pctiles = pctileSeries.map(function(s){ return s.pctile; });

    var ctx2 = document.getElementById('formulaPctileChart').getContext('2d');
    if(formulaPctileChart) formulaPctileChart.destroy();

    var windowLabel = windowSel === 'full' ? 'Full History' : windowSel;

    formulaPctileChart = new Chart(ctx2, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Percentile (' + windowLabel + ')',
                data: pctiles,
                borderColor: '#059669',
                backgroundColor: 'rgba(5,150,105,0.1)',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 5,
                fill: 'origin',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: true, position: 'top', labels: { font: { size: 10 } } },
                zoom: {
                    pan: { enabled: true, mode: 'x' },
                    zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx){
                            return 'Percentile: ' + ctx.raw.toFixed(1) + '%';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 12, font: { size: 9 }, color: '#333' }
                },
                y: {
                    min: 0, max: 100,
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    ticks: {
                        callback: function(v){ return v + '%'; },
                        font: { size: 9 }, color: '#333'
                    },
                    title: { display: true, text: 'Percentile %', font: { size: 10, weight: 'bold' }, color: '#333' }
                }
            }
        }
    });

    applyFormulaPctZoom();
}

function renderFormulaSeasonalityChart(series){
    var ctx3 = document.getElementById('formulaSeaChart').getContext('2d');
    if(formulaSeaChart) formulaSeaChart.destroy();

    // Extract years from series
    var yrSet = {};
    series.forEach(function(s){ var y = parseInt(s.date.substring(0,4)); if(y >= 2006) yrSet[y] = true; });
    var allYrs = Object.keys(yrSet).map(Number).sort();

    // Default select last 3 years if not set
    if(formulaSeaYrs.size === 0 && allYrs.length > 0){
        formulaSeaYrs = new Set(allYrs.slice(-3));
    }

    // Build year selector chips
    var yrContainer = document.getElementById('formulaYearSelector');
    yrContainer.innerHTML = '<strong style="font-size:0.85em;">Years:</strong>';
    allYrs.forEach(function(y){
        var c = document.createElement('div');
        c.className = 'yr-chip' + (formulaSeaYrs.has(y) ? ' active' : '');
        c.textContent = y;
        c.onclick = function(){
            if(formulaSeaYrs.has(y) && formulaSeaYrs.size > 1){ formulaSeaYrs.delete(y); c.classList.remove('active'); }
            else if(!formulaSeaYrs.has(y)){ formulaSeaYrs.add(y); c.classList.add('active'); }
            renderFormulaSeasonalityChart(series);
        };
        yrContainer.appendChild(c);
    });

    // Build weekly seasonality data
    var yd = {};
    series.forEach(function(s){
        var yr = parseInt(s.date.substring(0,4));
        if(!formulaSeaYrs.has(yr)) return;
        var dt = new Date(s.date);
        var w = wk(dt);
        if(!yd[yr]) yd[yr] = {};
        if(!yd[yr][w]) yd[yr][w] = { sum: 0, count: 0 };
        yd[yr][w].sum += s.value;
        yd[yr][w].count += 1;
    });

    var yc = ['#c0392b','#d4880f','#f39c12','#1a8c4e','#2980b9','#8e44ad','#16a085','#d35400','#2c3e50','#1abc9c'];
    var sy = Array.from(formulaSeaYrs).sort();
    var ds = [];

    sy.forEach(function(yr, yi){
        if(!yd[yr]) return;
        var wd = new Array(53).fill(null);
        for(var w = 1; w <= 53; w++){
            var e = yd[yr][w];
            if(!e || e.count === 0) continue;
            wd[w-1] = e.sum / e.count;
        }
        ds.push({
            label: String(yr),
            data: wd,
            borderColor: yc[yi % yc.length],
            borderWidth: 2.5,
            pointRadius: 2,
            pointHoverRadius: 5,
            spanGaps: true,
            fill: false,
            tension: 0.3
        });
    });

    var wl = [];
    for(var i = 1; i <= 53; i++) wl.push('W' + i);

    var isPct = getFormulaTerms().some(function(t){ return t.metric.indexOf('pct') !== -1; });

    formulaSeaChart = new Chart(ctx3, {
        type: 'line',
        data: { labels: wl, datasets: ds },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                title: {
                    display: true,
                    text: 'Formula Seasonality — Weekly Average',
                    font: { size: 12, weight: 'bold' },
                    color: '#1a1a1a'
                },
                legend: {
                    position: 'top',
                    labels: { boxWidth: 11, font: { size: 10 }, color: '#333' }
                },
                zoom: {
                    pan: { enabled: true, mode: 'x' },
                    zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
                },
                tooltip: {
                    callbacks: {
                        title: function(it){ return 'Week ' + parseInt(it[0].label.replace('W','')); },
                        label: function(it){ return it.dataset.label + ': ' + Number(it.raw).toLocaleString(undefined, {maximumFractionDigits: isPct ? 2 : 0}) + (isPct ? '%' : ''); }
                    }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Week', font: { size: 10 }, color: '#333' },
                    ticks: { callback: function(v, i){ return i % 4 === 0 ? 'W' + (i+1) : ''; }, font: { size: 9 }, color: '#333' }
                },
                y: {
                    title: { display: true, text: isPct ? '%' : 'Value', font: { size: 10, weight: 'bold' }, color: '#333' },
                    ticks: {
                        callback: function(v){ return isPct ? v.toFixed(1) + '%' : (Math.abs(v) >= 1000 ? (v/1000).toFixed(0) + 'k' : v); },
                        font: { size: 9 }, color: '#333'
                    }
                }
            }
        }
    });

    var note = document.getElementById('formulaSeaNote');
    if(note){
        note.innerHTML = '<strong>Showing:</strong> ' + sy.length + ' years | <strong>Metric:</strong> Formula Value | <strong>Agg:</strong> Weekly Average';
    }
}

/* ── Zoom Controls for Formula Charts ── */
function onFormulaZoom(val){
    formulaZoomPct = parseInt(val);
    applyFormulaZoom();
    updateFormulaZoomLabel();
}

function applyFormulaZoom(){
    if(!formulaChart || !formulaChart.data || !formulaChart.data.labels) return;
    var dates = formulaChart.data.labels;
    var n = dates.length;
    var p = formulaZoomPct;

    if(p >= 100){
        formulaChart.options.scales.x.min = undefined;
        formulaChart.options.scales.x.max = undefined;
    } else {
        var show = Math.max(8, Math.round(n * p / 100));
        var si2 = Math.max(0, n - show);
        formulaChart.options.scales.x.min = dates[si2];
        formulaChart.options.scales.x.max = dates[n - 1];
    }
    formulaChart.update('none');
}

function resetFormulaZoom(){
    formulaZoomPct = 100;
    var s = document.getElementById('formulaZoomSlider');
    if(s) s.value = 100;
    applyFormulaZoom();
    updateFormulaZoomLabel();
}

function updateFormulaZoomLabel(){
    var el = document.getElementById('formulaZoomLabel');
    if(!el || !formulaChart || !formulaChart.data || !formulaChart.data.labels) return;
    var p = formulaZoomPct;
    if(p >= 100){ el.textContent = 'All data'; return; }
    el.textContent = 'Last ~' + Math.max(8, Math.round(formulaChart.data.labels.length * p / 100)) + ' wks';
}

function onFormulaPctZoom(val){
    formulaPctZoomPct = parseInt(val);
    applyFormulaPctZoom();
    updateFormulaPctZoomLabel();
}

function applyFormulaPctZoom(){
    if(!formulaPctileChart || !formulaPctileChart.data || !formulaPctileChart.data.labels) return;
    var dates = formulaPctileChart.data.labels;
    var n = dates.length;
    var p = formulaPctZoomPct;

    if(p >= 100){
        formulaPctileChart.options.scales.x.min = undefined;
        formulaPctileChart.options.scales.x.max = undefined;
    } else {
        var show = Math.max(8, Math.round(n * p / 100));
        var si2 = Math.max(0, n - show);
        formulaPctileChart.options.scales.x.min = dates[si2];
        formulaPctileChart.options.scales.x.max = dates[n - 1];
    }
    formulaPctileChart.update('none');
}

function resetFormulaPctZoom(){
    formulaPctZoomPct = 100;
    var s = document.getElementById('formulaPctZoomSlider');
    if(s) s.value = 100;
    applyFormulaPctZoom();
    updateFormulaPctZoomLabel();
}

function updateFormulaPctZoomLabel(){
    var el = document.getElementById('formulaPctZoomLabel');
    if(!el || !formulaPctileChart || !formulaPctileChart.data || !formulaPctileChart.data.labels) return;
    var p = formulaPctZoomPct;
    if(p >= 100){ el.textContent = 'All data'; return; }
    el.textContent = 'Last ~' + Math.max(8, Math.round(formulaPctileChart.data.labels.length * p / 100)) + ' wks';
}

function togglePctileChart(){
    var show = document.getElementById('showPctileToggle').checked;
    document.getElementById('formulaPctileBox').style.display = show ? 'block' : 'none';
    if(show) updateFormulaCharts();
}

/* ── Persistence ── */
function saveCurrentFormula(){
    var terms = getFormulaTerms();
    if(!terms.length){ alert('Build a formula first before saving.'); return; }
    var name = prompt('Name this formula:', document.querySelector('#formula-preview span').textContent.substring(0, 50));
    if(!name) return;

    var saved = JSON.parse(localStorage.getItem('cot_custom_formulas') || '[]');
    saved.push({ name: name, terms: terms, created: new Date().toISOString() });
    localStorage.setItem('cot_custom_formulas', JSON.stringify(saved));
    loadSavedFormulas();
}

function loadSavedFormulas(){
    var saved = JSON.parse(localStorage.getItem('cot_custom_formulas') || '[]');
    var list = document.getElementById('saved-formulas-list');
    var empty = document.getElementById('saved-formulas-empty');
    if(!list) return;

    if(!saved.length){
        list.innerHTML = '';
        if(empty) empty.style.display = 'block';
        return;
    }
    if(empty) empty.style.display = 'none';

    list.innerHTML = saved.map(function(f, i){
        return '<div class="saved-chip" onclick="loadFormula(' + i + ')">' +
               f.name +
               '<span class="delete-chip" onclick="event.stopPropagation();deleteFormula(' + i + ')">×</span>' +
               '</div>';
    }).join('');
}

function loadFormula(index){
    var saved = JSON.parse(localStorage.getItem('cot_custom_formulas') || '[]');
    var formula = saved[index];
    if(!formula) return;

    document.getElementById('formula-terms').innerHTML = '';
    formula.terms.forEach(function(t, i){
        addFormulaTerm();
        var termEl = document.querySelectorAll('#formula-terms .formula-term-row')[i];
        if(i > 0) termEl.querySelector('.op-select').value = t.op;
        termEl.querySelector('.cat-select').value = t.cat;
        termEl.querySelector('.metric-select').value = t.metric;
        termEl.querySelector('.crop-select').value = t.crop;
    });
    updateFormulaPreview();
    updateFormulaCharts();
}

function deleteFormula(index){
    var saved = JSON.parse(localStorage.getItem('cot_custom_formulas') || '[]');
    saved.splice(index, 1);
    localStorage.setItem('cot_custom_formulas', JSON.stringify(saved));
    loadSavedFormulas();
}

function clearFormula(){
    document.getElementById('formula-terms').innerHTML = '';
    addFormulaTerm();
    updateFormulaPreview();
    if(formulaChart){ formulaChart.destroy(); formulaChart = null; }
    if(formulaPctileChart){ formulaPctileChart.destroy(); formulaPctileChart = null; }
    if(formulaSeaChart){ formulaSeaChart.destroy(); formulaSeaChart = null; }
    window._formulaRawCache = {};
    formulaSeaYrs = new Set();
}

