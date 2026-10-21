function initAiTab(){
  if(_aiInited) return;
  _aiInited = true;
  // Restore saved key
  var saved = localStorage.getItem('groqApiKey');
  if(saved){
    document.getElementById('aiKeyStatus').textContent = '✅ Key ready';
  }
  loadAiData();
}

function aiSaveKey(){
  var k = document.getElementById('aiKeyInput').value.trim();
  if(!k){ alert('Paste your Groq API key first (starts with gsk_).'); return; }
  localStorage.setItem('groqApiKey', k);
  document.getElementById('aiKeyInput').value = '';
  document.getElementById('aiKeyStatus').textContent = '✅ Key saved for this session';
}

function getAiKey(){
  var k = localStorage.getItem('groqApiKey') || document.getElementById('aiKeyInput').value.trim();
  if(!k){
    alert('Paste your Groq API key first.\n\nGet a free key at console.groq.com/keys (30-second signup).');
    return null;
  }
  return k;
}

function aiFillPreset(){
  var q = document.getElementById('aiPresetSel').value;
  if(q){ document.getElementById('aiCustomQ').value = q; }
}

/* Build context string from pre-computed JSON (or live chart data fallback) */
function buildAiContext(){
  var ctx='';
  var data=window._cotData;
  if(data&&data.commodities){
    ctx+='BCOM COT DATA — Report: '+data.report_date+' | History from: '+data.data_from+'\n\n';
    ctx+='MANAGED MONEY POSITIONING (net, wk change, percentile vs full history & 10yr, extremes):\n';
    data.commodities.forEach(function(comm){
      comm.variants.forEach(function(v){
        var mm=v.categories&&v.categories.managed_money;if(!mm)return;
        var p=mm.pctiles||{},h=mm.historical||{},hn=h.net||{};
        var crop=comm.is_crop?'['+v.crop_type.toUpperCase()+']':'';
        ctx+=comm.name+'('+comm.ticker+')'+crop+': ';
        ctx+='Net='+(mm.net||0).toLocaleString();
        ctx+=' Chg='+((mm.wk_chg_net||0)>=0?'+':'')+(mm.wk_chg_net||0).toLocaleString();
        ctx+=' Net%ile=Full:'+(p.net_full||'?')+'% 10yr:'+(p.net_10yr||'?')+'%';
        ctx+=' Long%ile:'+(p.long_full||'?')+'% Short%ile:'+(p.short_full||'?')+'%';
        ctx+=' Net%OI='+(mm.net_pct_oi||0).toFixed(1)+'%\n';
        if(hn['10yr_min']!==undefined)ctx+='  10yr: min='+hn['10yr_min']+'('+hn['10yr_min_date']+') max='+hn['10yr_max']+'('+hn['10yr_max_date']+')\n';
        if(hn.full_min!==undefined)ctx+='  AllTime: min='+hn.full_min+'('+hn.full_min_date+') max='+hn.full_max+'('+hn.full_max_date+')\n';
      });
    });
    ctx+='\nPROD/MERCHANT NET (full %ile):\n';
    data.commodities.forEach(function(comm){
      var v0=comm.variants&&comm.variants[0];if(!v0)return;
      var pm=v0.categories&&v0.categories.prod_merc;if(!pm)return;
      ctx+=comm.name+'('+comm.ticker+'): Net='+(pm.net||0).toLocaleString()+' %ile='+(pm.pctiles&&pm.pctiles.net_full||'?')+'%\n';
    });
  } else {
    ctx+='Pre-computed data not loaded. Using live chart data.\n';
    if(CD){
      var l=CD.net.length-1,tc=document.getElementById('traderCategory').value||'managed_money';
      ctx+='Selected: '+(CD.comm||'').split(' - ')[0]+' | '+(CAT_LBL[tc]||tc)+'\n';
      ctx+='Date: '+CD.dates[l].substring(0,10)+'\n';
      ctx+='Net: '+CD.net[l].toLocaleString()+' ('+pct(CD.net,CD.net[l]).toFixed(0)+'th %ile)\n';
      ctx+='Long: '+CD.long[l].toLocaleString()+' ('+pct(CD.long,CD.long[l]).toFixed(0)+'th %ile)\n';
      ctx+='Short: '+CD.short[l].toLocaleString()+' ('+pct(CD.short,CD.short[l]).toFixed(0)+'th %ile)\n';
    }
    if(scData&&scData.length){
      ctx+='\nALL BCOM MM (%ile):\n';
      scData.forEach(function(d){ctx+=d.comm+': Net='+d.mNP.toFixed(0)+'% Short='+d.mSP.toFixed(0)+'% Long='+d.mLP.toFixed(0)+'%\n';});
    }
  }
  return ctx;
}

async function aiQ(question){
  var key = getAiKey(); if(!key) return;
  var spin = document.getElementById('aiPane_spinner');
  var resp = document.getElementById('aiPane_response');
  var text = document.getElementById('aiPane_text');
  spin.style.display = 'block';
  resp.style.display = 'none';
  document.getElementById('aiChartArea').style.display = 'none';
  spin.scrollIntoView({behavior:'smooth', block:'start'});

  var context = buildAiContext();

  /* System prompt includes chart detection instructions */
  var SYS =
    'You are an expert commodity futures analyst specializing in CFTC COT reports and the Bloomberg Commodity Index (BCOM).\n\n' +
    'CHART DETECTION: When the user asks to plot, chart, graph, draw, or visualize data, you MUST:\n' +
    '1. Respond with your analysis text as normal.\n' +
    '2. At the END of your response, include a chart spec tag in this exact format (no spaces inside braces):\n' +
    '   [CHART:{"commodity":"<exact name>","metric":"<metric>","years":<number>,"crop_type":"<all|old|other>"}]\n\n' +
    'Valid commodity names: Brent Crude Oil, Natural Gas, WTI Crude Oil, Low Sulphur Gas Oil, ULS Diesel, RBOB Gasoline, Corn, Soybeans, Soybean Meal, Soybean Oil, Wheat SRW, HRW Wheat, Copper, Aluminum, Zinc, Nickel, Lead, Gold, Silver, Sugar, Coffee, Cocoa, Cotton, Live Cattle, Lean Hogs\n\n' +
    'Valid metrics:\n' +
    '  mm_net (Managed Money Net = Long minus Short)\n' +
    '  mm_long (MM Gross Long positions)\n' +
    '  mm_short (MM Gross Short positions)\n' +
    '  mm_net_pct_oi (MM Net as % of Open Interest)\n' +
    '  pm_net (Prod/Merchant Net)\n' +
    '  pm_long (Prod/Merchant Gross Long)\n' +
    '  pm_short (Prod/Merchant Gross Short)\n' +
    '  sd_net (Swap Dealers Net)\n' +
    '  or_net (Other Reportables Net)\n' +
    '  open_interest (Total Open Interest)\n\n' +
    'Examples:\n' +
    '  "plot 10 year MM net chart for cotton" → [CHART:{"commodity":"Cotton","metric":"mm_net","years":10,"crop_type":"all"}]\n' +
    '  "show me gold managed money longs since 2020" → [CHART:{"commodity":"Gold","metric":"mm_long","years":4,"crop_type":"all"}]\n' +
    '  "chart corn old crop MM net for 5 years" → [CHART:{"commodity":"Corn","metric":"mm_net","years":5,"crop_type":"old"}]\n' +
    '  "graph WTI crude open interest over 3 years" → [CHART:{"commodity":"WTI Crude Oil","metric":"open_interest","years":3,"crop_type":"all"}]\n\n' +
    'For questions without chart requests: answer concisely with bullet points. Use exact numbers from the data context. Max 450 words.';

  try{
    var res = await fetch('https://api.groq.com/openai/v1/chat/completions',{
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+key},
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        messages: [
          {role:'system', content: SYS},
          {role:'user', content: question + '\n\nDATA CONTEXT:\n' + context}
        ],
        max_tokens: 1400,
        temperature: 0.3
      })
    });
    if(!res.ok){
      var err = await res.json();
      throw new Error((err.error && err.error.message) || 'HTTP '+res.status);
    }
    var data = await res.json();
    var raw_answer = (data.choices&&data.choices[0]&&data.choices[0].message&&data.choices[0].message.content)||'No response.';

    // Parse for chart tags
    var parsed = parseAiResponse(raw_answer);
    text.textContent = parsed.clean;
    resp.style.display = 'block';

    // Render each chart found
    if(parsed.specs.length > 0){
      parsed.specs.forEach(function(spec){ renderAiChart(spec); });
    }

  } catch(e){
    text.textContent = 'Error: '+e.message+'\n\nCheck your Groq API key at console.groq.com/keys';
    resp.style.display = 'block';
  }
  spin.style.display = 'none';
  resp.scrollIntoView({behavior:'smooth', block:'start'});
}

function aiAskCustom(){
  var q = document.getElementById('aiCustomQ').value.trim();
  if(!q){ alert('Type or select a question first.'); return; }
  aiQ(q);
}

/* Populate the snapshot table from pre-computed data */
function loadAiData(){
  var status=document.getElementById('aiDataStatus');
  status.innerHTML='⏳ Loading data/latest_summary.json...';
  fetch('data/latest_summary.json',{cache:'no-cache'})
    .then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
    .then(function(data){
      window._cotData=data;
      status.innerHTML='✅ Data loaded · Report: <strong>'+data.report_date+'</strong> · History from: '+data.data_from;
      status.style.color='#c8f7c5';status.style.background='rgba(39,174,96,0.15)';
      var sd=document.getElementById('aiSnapDate');if(sd)sd.textContent='Report: '+data.report_date;
      var df=document.getElementById('aiDataFrom');if(df)df.textContent='History from '+data.data_from;
      renderSnapTable(data,document.getElementById('aiSnapBody'));
    })
    .catch(function(err){
      window._cotData=null;
      status.innerHTML='ℹ️ '+err.message+' — Run the <strong>Weekly COT Data Update</strong> GitHub Action once to generate data/latest_summary.json. Until then AI uses live chart data — load a commodity in the COT tab first.';
      status.style.background='rgba(231,76,60,0.15)';status.style.color='#ffcdd2';
    });
}
function renderSnapTable(data,tbody){
  if(!tbody)return;
  tbody.innerHTML='';
  var SO=['Energy','Grains','Industrial Metals','Precious Metals','Softs','Livestock'];
  var sorted=data.commodities.slice().sort(function(a,b){
    return SO.indexOf(a.sector)-SO.indexOf(b.sector)||a.name.localeCompare(b.name);
  });
  var lastSec='';
  sorted.forEach(function(comm){
    if(comm.sector!==lastSec){
      lastSec=comm.sector;
      var hr=document.createElement('tr');
      hr.innerHTML='<td colspan="12" style="background:#34495e;color:white;font-weight:700;padding:5px 8px;font-size:0.82em;">'+comm.sector+'</td>';
      tbody.appendChild(hr);
    }
    comm.variants.forEach(function(v,vi){
      var mm=v.categories&&v.categories.managed_money;if(!mm)return;
      var p=mm.pctiles||{},hn=(mm.historical&&mm.historical.net)||{};
      function pc(val){
        if(val<0)return'#999';if(val<=15)return'#c0392b';if(val<=30)return'#e67e22';
        if(val>=85)return'#1a8c4e';if(val>=70)return'#2980b9';return'#555';
      }
      function fmt(n){return(n!==undefined&&n!==null)?Number(n).toLocaleString():'—';}
      function fp(v){return v>=0?('<span style="color:'+pc(v)+';font-weight:700;">'+Number(v).toFixed(0)+'%</span>'):'—';}
      var row=document.createElement('tr');
      row.style.borderBottom='1px solid #eee';
      if(vi%2===1)row.style.background='#fafafa';
      row.innerHTML=
        '<td style="padding:4px 8px;font-weight:'+(vi===0?'600':'400')+';color:#1a1a1a;">'+(vi===0?comm.name+' ('+comm.ticker+')':'')+'</td>'+
        '<td style="padding:4px 6px;text-align:center;font-size:0.8em;color:#777;">'+(comm.is_crop?v.crop_type.toUpperCase():'—')+'</td>'+
        '<td style="padding:4px 6px;text-align:right;font-family:monospace;color:'+(mm.net>=0?'#1a8c4e':'#c0392b')+';font-weight:600;">'+(mm.net>=0?'+':'')+fmt(mm.net)+'</td>'+
        '<td style="padding:4px 6px;text-align:right;font-family:monospace;color:'+((mm.wk_chg_net||0)>=0?'#1a8c4e':'#c0392b')+';">'+(((mm.wk_chg_net||0)>=0)?'+':'')+fmt(mm.wk_chg_net)+'</td>'+
        '<td style="padding:4px 6px;text-align:center;">'+fp(p.net_full)+'</td>'+
        '<td style="padding:4px 6px;text-align:center;">'+fp(p.net_10yr)+'</td>'+
        '<td style="padding:4px 6px;text-align:center;">'+fp(p.long_full)+'</td>'+
        '<td style="padding:4px 6px;text-align:center;">'+fp(p.short_full)+'</td>'+
        '<td style="padding:4px 6px;text-align:right;font-family:monospace;font-size:0.8em;color:#c0392b;">'+fmt(hn['10yr_min'])+'<br><small style="color:#aaa;">'+(hn['10yr_min_date']||'')+'</small></td>'+
        '<td style="padding:4px 6px;text-align:right;font-family:monospace;font-size:0.8em;color:#1a8c4e;">'+fmt(hn['10yr_max'])+'<br><small style="color:#aaa;">'+(hn['10yr_max_date']||'')+'</small></td>'+
        '<td style="padding:4px 6px;text-align:right;font-family:monospace;font-size:0.8em;color:#c0392b;">'+fmt(hn.full_min)+'<br><small style="color:#aaa;">'+(hn.full_min_date||'')+'</small></td>'+
        '<td style="padding:4px 6px;text-align:right;font-family:monospace;font-size:0.8em;color:#1a8c4e;">'+fmt(hn.full_max)+'<br><small style="color:#aaa;">'+(hn.full_max_date||'')+'</small></td>';
      tbody.appendChild(row);
    });
  });
}


/* ===========================================================
   AI RESPONSE PARSING & CHART RENDERING
   =========================================================== */

/* Parse AI response for [CHART:{...}] tags and extract clean text */
function parseAiResponse(rawText){
  var clean = rawText;
  var specs = [];

  // Find all [CHART:{...}] tags
  var regex = /\[CHART:(\{[^\}]+\})\]/g;
  var match;

  while((match = regex.exec(rawText)) !== null){
    try{
      var spec = JSON.parse(match[1]);
      if(spec.commodity && spec.metric){
        specs.push(spec);
      }
    }catch(e){
      console.warn('Failed to parse chart spec:', match[1]);
    }
  }

  // Remove chart tags from clean text
  clean = clean.replace(/\[CHART:[^\]]+\]/g, '').trim();

  return {clean: clean, specs: specs};
}

/* Render a chart based on AI-requested spec */
function renderAiChart(spec){
  var area = document.getElementById('aiChartArea');
  var title = document.getElementById('aiChartTitle');
  var sub = document.getElementById('aiChartSub');
  var note = document.getElementById('aiChartNote');
  var spinner = document.getElementById('aiChartSpinner');

  area.style.display = 'block';
  spinner.style.display = 'block';

  // Map commodity name to API name
  var commApi = null;
  for(var i=0; i<allBCOM.length; i++){
    if(allBCOM[i].name.toLowerCase() === spec.commodity.toLowerCase()){
      commApi = allBCOM[i].api;
      break;
    }
  }

  if(!commApi){
    title.textContent = 'Error: Commodity not found';
    sub.textContent = spec.commodity;
    spinner.style.display = 'none';
    return;
  }

  // Determine metric mapping
  var metricMap = {
    'mm_net': {field: 'net', cat: 'managed_money', label: 'Managed Money Net'},
    'mm_long': {field: 'long', cat: 'managed_money', label: 'MM Gross Long'},
    'mm_short': {field: 'short', cat: 'managed_money', label: 'MM Gross Short'},
    'mm_net_pct_oi': {field: 'nPct', cat: 'managed_money', label: 'MM Net %OI'},
    'pm_net': {field: 'net', cat: 'prod_merc', label: 'Prod/Merchant Net'},
    'pm_long': {field: 'long', cat: 'prod_merc', label: 'PM Gross Long'},
    'pm_short': {field: 'short', cat: 'prod_merc', label: 'PM Gross Short'},
    'sd_net': {field: 'net', cat: 'swap_dealers', label: 'Swap Dealers Net'},
    'or_net': {field: 'net', cat: 'other_rept', label: 'Other Reportables Net'},
    'open_interest': {field: 'oi', cat: 'managed_money', label: 'Open Interest'}
  };

  var m = metricMap[spec.metric] || metricMap['mm_net'];

  title.textContent = m.label + ' — ' + spec.commodity;
  sub.textContent = (spec.years || 10) + ' year history' + (spec.crop_type && spec.crop_type !== 'all' ? ' (' + spec.crop_type + ' crop)' : '');

  // Calculate date range
  var endDate = new Date();
  var startDate = new Date();
  startDate.setFullYear(endDate.getFullYear() - (spec.years || 10));

  var ep = EP.combined;
  var url = ep + "?$where=" + liveWhere(commApi) + " AND report_date_as_yyyy_mm_dd >= '" + startDate.toISOString().split('T')[0] + "' AND report_date_as_yyyy_mm_dd <= '" + endDate.toISOString().split('T')[0] + "'&$order=report_date_as_yyyy_mm_dd ASC&$limit=10000";

  fetchT(url, 20000)
    .then(function(r){ return r.json(); })
    .then(function(data){
      if(!data || !data.length){
        throw new Error('No data returned from CFTC');
      }

      var p = procData(data, m.cat, spec.crop_type || 'all');
      if(!p){
        throw new Error('Failed to process data for ' + spec.crop_type + ' crop type');
      }

      // Get values
      var values, label, color;
      switch(m.field){
        case 'net': values = p.net; color = '#2a5298'; label = 'Net Position'; break;
        case 'long': values = p.long; color = '#1a8c4e'; label = 'Long'; break;
        case 'short': values = p.short; color = '#c0392b'; label = 'Short'; break;
        case 'nPct': values = p.nPct; color = '#2a5298'; label = 'Net %OI'; break;
        case 'lPct': values = p.lPct; color = '#1a8c4e'; label = 'Long %OI'; break;
        case 'sPct': values = p.sPct; color = '#c0392b'; label = 'Short %OI'; break;
        case 'oi': values = p.oi; color = '#8e44ad'; label = 'Open Interest'; break;
        default: values = p.net; color = '#2a5298'; label = 'Net';
      }

      var isPct = m.field.indexOf('Pct') !== -1 || m.field === 'nPct' || m.field === 'lPct' || m.field === 'sPct';

      // Create chart
      var ctx = document.getElementById('aiChartCanvas').getContext('2d');
      if(charts.aiChart) charts.aiChart.destroy();

      charts.aiChart = new Chart(ctx, {
        type: 'line',
        data: {
          datasets: [{
            label: label,
            data: pts(p.dates, values),
            borderColor: color,
            backgroundColor: color + '20',
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
            legend: { display: true, position: 'top' },
            tooltip: {
              callbacks: {
                label: function(ctx) {
                  var v = ctx.raw.y;
                  return label + ': ' + (isPct ? v.toFixed(1) + '%' : v.toLocaleString());
                }
              }
            }
          },
          scales: {
            x: {
              type: 'time',
              time: { unit: 'month', displayFormats: { month: 'MMM yy' } },
              grid: { display: false },
              ticks: { maxTicksLimit: 12, font: { size: 9 } }
            },
            y: {
              grid: { color: 'rgba(0,0,0,0.05)' },
              ticks: {
                callback: function(v) {
                  return isPct ? v.toFixed(0) + '%' : (Math.abs(v) >= 1000 ? (v/1000).toFixed(0) + 'k' : v);
                },
                font: { size: 9 }
              }
            }
          }
        }
      });

      // Add note
      var latest = values[values.length - 1];
      var pctile = pct(values, latest);
      note.innerHTML = '<strong>Latest:</strong> ' + (isPct ? latest.toFixed(1) + '%' : latest.toLocaleString()) + 
                       ' | <strong>Historical %ile:</strong> ' + pctile.toFixed(0) + 'th percentile vs ' + spec.years + '-year range';

      spinner.style.display = 'none';
    })
    .catch(function(e){
      title.textContent = 'Error loading chart';
      sub.textContent = e.message;
      spinner.style.display = 'none';
      console.error('Chart error:', e);
    });
}

/* Restore saved Groq key on load */
(function(){
  var k=localStorage.getItem('groqApiKey');
  if(k){
    var el=document.getElementById('aiKeyStatus');
    if(el)el.textContent='✅ Key ready';
  }
})();

