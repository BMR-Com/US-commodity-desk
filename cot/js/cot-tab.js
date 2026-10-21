/* ===========================================================
   COT TAB — Main Charts (Position, Comparison, Traders, Size)
   Loaded dynamically by tab-switching.js
   =========================================================== */

function initCotTab() {
    // Charts are drawn by fetchData() after commodity selection
    // Zoom sliders are already set up in HTML
    console.log('[COT Tab] Initialized');
}

/* ===========================================================
   MAIN CHARTS
   =========================================================== */
function updateAll(){drawPos();drawCmp();drawTrd();drawSz();if(typeof drawSea==='function')drawSea();}

function getCommShort(){return CD?(CD.comm||'').split(' - ')[0]:'';}
function getCatLabel(){return CAT_LBL[document.getElementById('traderCategory').value]||'Managed Money';}
function setSubtitle(chartId,text){var el=document.getElementById(chartId+'_sub');if(!el){el=document.createElement('div');el.id=chartId+'_sub';el.className='chart-subtitle';var hdr=document.getElementById(chartId).querySelector('.chart-title');if(hdr&&hdr.parentNode)hdr.parentNode.insertBefore(el,hdr.nextSibling);}el.textContent=text;}

function drawPos(){
  if(!CD)return;var m=document.getElementById('posMet').value,ctx=document.getElementById('posChart').getContext('2d');
  if(charts.pos)charts.pos.destroy();
  var v,l,c,ip=m.indexOf('pct')!==-1,sz=m==='net'||m==='net_pct';
  var mLabels={net:'Net Position',long:'Long',short:'Short',spread:'Spread',net_pct:'Net%OI',long_pct:'Long%OI',short_pct:'Short%OI'};
  switch(m){case'net':v=CD.net;l='Net';c='#2a5298';break;case'long':v=CD.long;l='Long';c='#1a8c4e';break;case'short':v=CD.short;l='Short';c='#c0392b';break;case'spread':v=CD.spread;l='Spread';c='#d4880f';break;case'net_pct':v=CD.nPct;l='Net%OI';c='#2a5298';break;case'long_pct':v=CD.lPct;l='Long%OI';c='#1a8c4e';break;case'short_pct':v=CD.sPct;l='Short%OI';c='#c0392b';break;}
  setSubtitle('chart1',getCommShort()+' — '+getCatLabel()+' — '+mLabels[m]);
  var ds=[{label:l,data:pts(CD.dates,v),borderColor:c,backgroundColor:c+'18',borderWidth:2,pointRadius:0,fill:true,tension:0.4}];
  if(sz)ds.push({label:'Zero',data:CD.dates.map(function(d){return{x:d,y:0};}),borderColor:'rgba(192,57,43,0.35)',borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false});
  charts.pos=mkLine(ctx,ds,true,ip?'% OI':'Contracts',ip,false);
  applyZoom(charts.pos,'pos');addPx('pos');
}
function drawCmp(){
  if(!ATD)return;var m=document.getElementById('cmpMet').value,ctx=document.getElementById('cmpChart').getContext('2d');
  if(charts.cmp)charts.cmp.destroy();var ip=m==='net_pct';
  var ds=[];CATS.forEach(function(c){var d=ATD[c];if(!d)return;var v;switch(m){case'net':v=d.net;break;case'long':v=d.long;break;case'short':v=d.short;break;default:v=d.nPct;}ds.push({label:CAT_LBL[c],data:pts(d.dates,v),borderColor:CAT_COL[c],borderWidth:2,fill:false,pointRadius:0,tension:0.4});});
  charts.cmp=mkLine(ctx,ds,true,ip?'% OI':'',ip,true);applyZoom(charts.cmp,'cmp');addPx('cmp');
}
function drawTrd(){
  if(!CD)return;var m=document.getElementById('trdMet').value,ctx=document.getElementById('trdChart').getContext('2d');
  if(charts.trd)charts.trd.destroy();var ds=[];
  var mLabels={total:'Total Traders',long:'Long Traders',short:'Short Traders',both:'Long & Short Traders'};
  setSubtitle('chart3',getCommShort()+' — '+getCatLabel()+' — '+mLabels[m]);
  if(m==='total')ds=[{label:'Total',data:pts(CD.dates,CD.tT),borderColor:'#2a5298',borderWidth:2,pointRadius:0,fill:true,tension:0.4}];
  else if(m==='long')ds=[{label:'Long',data:pts(CD.dates,CD.tL),borderColor:'#1a8c4e',borderWidth:2,pointRadius:0,fill:true,tension:0.4}];
  else if(m==='short')ds=[{label:'Short',data:pts(CD.dates,CD.tS),borderColor:'#c0392b',borderWidth:2,pointRadius:0,fill:true,tension:0.4}];
  else ds=[{label:'Long',data:pts(CD.dates,CD.tL),borderColor:'#1a8c4e',borderWidth:2,pointRadius:0,fill:false,tension:0.4},{label:'Short',data:pts(CD.dates,CD.tS),borderColor:'#c0392b',borderWidth:2,pointRadius:0,fill:false,tension:0.4}];
  charts.trd=mkLine(ctx,ds,true,'Traders',false,m==='both');applyZoom(charts.trd,'trd');
}
function drawSz(){
  if(!CD)return;var m=document.getElementById('szMet').value,ctx=document.getElementById('szChart').getContext('2d');
  if(charts.sz)charts.sz.destroy();var ds=[];
  var mLabels={per_trader_long:'Contracts per Trader (Long)',per_trader_short:'Contracts per Trader (Short)',long_vs_short:'Long & Short per Trader'};
  setSubtitle('chart4',getCommShort()+' — '+getCatLabel()+' — '+mLabels[m]);
  if(m==='per_trader_long')ds=[{label:'Long/Trader',data:pts(CD.dates,CD.plL),borderColor:'#1a8c4e',borderWidth:2,pointRadius:0,fill:true,tension:0.4}];
  else if(m==='per_trader_short')ds=[{label:'Short/Trader',data:pts(CD.dates,CD.plS),borderColor:'#c0392b',borderWidth:2,pointRadius:0,fill:true,tension:0.4}];
  else ds=[{label:'Long/T',data:pts(CD.dates,CD.plL),borderColor:'#1a8c4e',borderWidth:2,pointRadius:0,fill:false,tension:0.4},{label:'Short/T',data:pts(CD.dates,CD.plS),borderColor:'#c0392b',borderWidth:2,pointRadius:0,fill:false,tension:0.4}];
  charts.sz=mkLine(ctx,ds,true,'Contracts/Trader',false,m==='long_vs_short');applyZoom(charts.sz,'sz');
}

/* ===========================================================
   WEEKLY DETAIL — reads raw records directly, exact CFTC field names
   =========================================================== */
function chgCell(v){return '<td class="'+(v>0?'val-pos':v<0?'val-neg':'')+'">'+(v>0?'+':'')+v.toLocaleString()+'</td>';}

/* Exact Socrata field names per crop variant — confirmed from API foundry */
var WD={
  all:{
    oi:  'open_interest_all',
    pmL: 'prod_merc_positions_long',        pmS: 'prod_merc_positions_short',
    sdL: 'swap_positions_long_all',         sdS: 'swap__positions_short_all',      sdSp:'swap__positions_spread_all',
    mmL: 'm_money_positions_long_all',      mmS: 'm_money_positions_short_all',    mmSp:'m_money_positions_spread',
    orL: 'other_rept_positions_long',       orS: 'other_rept_positions_short',     orSp:'other_rept_positions_spread'
  },
  old:{
    oi:  'open_interest_old',
    pmL: 'prod_merc_positions_long_1',      pmS: 'prod_merc_positions_short_1',
    sdL: 'swap_positions_long_old',         sdS: 'swap__positions_short_old',      sdSp:'swap__positions_spread_old',
    mmL: 'm_money_positions_long_old',      mmS: 'm_money_positions_short_old',    mmSp:'m_money_positions_spread_1',
    orL: 'other_rept_positions_long_1',     orS: 'other_rept_positions_short_1',   orSp:'other_rept_positions_spread_1'
  },
  other:{
    oi:  'open_interest_other',
    pmL: 'prod_merc_positions_long_2',      pmS: 'prod_merc_positions_short_2',
    sdL: 'swap_positions_long_other',       sdS: 'swap__positions_short_other',    sdSp:'swap__positions_spread_other',
    mmL: 'm_money_positions_long_other',    mmS: 'm_money_positions_short_other',  mmSp:'m_money_positions_spread_2',
    orL: 'other_rept_positions_long_2',     orS: 'other_rept_positions_short_2',   orSp:'other_rept_positions_spread_2'
  }
};

function ri(rec,k){ if(!k||rec[k]==null||rec[k]==='')return 0; return parseInt(rec[k])||0; }

/* Build one section table from raw records for a given variant: 'all'|'old'|'other' */
function buildWDSection(raw, variant, weeks){
  if(!raw||!raw.length)return '<p style="color:#999;padding:16px;">No data.</p>';
  var recs=raw.slice().sort(function(a,b){
    return new Date(b.report_date_as_yyyy_mm_dd)-new Date(a.report_date_as_yyyy_mm_dd);
  }).slice(0, weeks+1);

  var f=WD[variant];
  var sample=recs[0];
  if(!sample.hasOwnProperty(f.mmL)||sample[f.mmL]==null||sample[f.mmL]===''){
    return '<div style="padding:14px;color:#8B6914;background:#fff8e1;border-radius:4px;">'+
      '⚠ No '+variant+' crop-year fields found for this commodity.</div>';
  }

  /* thead — PM: 3 cols (no Spread), SD/MM/OR: 4 cols */
  var h='<div style="overflow-x:auto;"><table class="weekly-detail-tbl"><thead><tr>';
  h+='<th rowspan="2" style="background:#34495e;color:white;">Date</th>';
  h+='<th colspan="3" class="cat-hdr-pm">Prod/Merchant</th>';
  h+='<th colspan="4" class="cat-hdr-sd">Swap Dealers</th>';
  h+='<th colspan="4" class="cat-hdr-mm">Managed Money</th>';
  h+='<th colspan="4" class="cat-hdr-or">Other Rept</th>';
  h+='<th rowspan="2" style="background:#1a1a1a;color:white;">Open Interest</th>';
  h+='</tr><tr>';
  h+='<th class="sub-pm">Long</th><th class="sub-pm">Short</th><th class="sub-pm">Net</th>';
  h+='<th class="sub-sd">Long</th><th class="sub-sd">Short</th><th class="sub-sd">Spread</th><th class="sub-sd">Net</th>';
  h+='<th class="sub-mm">Long</th><th class="sub-mm">Short</th><th class="sub-mm">Spread</th><th class="sub-mm">Net</th>';
  h+='<th class="sub-or">Long</th><th class="sub-or">Short</th><th class="sub-or">Spread</th><th class="sub-or">Net</th>';
  h+='</tr></thead><tbody>';

  function nc(n){return '<td class="'+(n>=0?'val-pos':'val-neg')+'">'+n.toLocaleString()+'</td>';}

  for(var w=0;w<Math.min(weeks,recs.length);w++){
    var rec=recs[w], isLatest=(w===0);
    var pmL=ri(rec,f.pmL), pmS=ri(rec,f.pmS);
    var sdL=ri(rec,f.sdL), sdS=ri(rec,f.sdS), sdSp=ri(rec,f.sdSp);
    var mmL=ri(rec,f.mmL), mmS=ri(rec,f.mmS), mmSp=ri(rec,f.mmSp);
    var orL=ri(rec,f.orL), orS=ri(rec,f.orS), orSp=ri(rec,f.orSp);
    var oi=ri(rec,f.oi);
    h+='<tr'+(isLatest?' style="background:#f0f7ff;font-weight:600;"':'')+'>'; 
    h+='<td>'+rec.report_date_as_yyyy_mm_dd.substring(0,10)+'</td>';
    h+='<td>'+pmL.toLocaleString()+'</td><td>'+pmS.toLocaleString()+'</td>'+nc(pmL-pmS);
    h+='<td>'+sdL.toLocaleString()+'</td><td>'+sdS.toLocaleString()+'</td><td>'+sdSp.toLocaleString()+'</td>'+nc(sdL-sdS);
    h+='<td>'+mmL.toLocaleString()+'</td><td>'+mmS.toLocaleString()+'</td><td>'+mmSp.toLocaleString()+'</td>'+nc(mmL-mmS);
    h+='<td>'+orL.toLocaleString()+'</td><td>'+orS.toLocaleString()+'</td><td>'+orSp.toLocaleString()+'</td>'+nc(orL-orS);
    h+='<td>'+oi.toLocaleString()+'</td></tr>';

    if(isLatest&&recs.length>1){
      var prev=recs[1];
      var ppmL=ri(prev,f.pmL),ppmS=ri(prev,f.pmS);
      var psdL=ri(prev,f.sdL),psdS=ri(prev,f.sdS),psdSp=ri(prev,f.sdSp);
      var pmmL=ri(prev,f.mmL),pmmS=ri(prev,f.mmS),pmmSp=ri(prev,f.mmSp);
      var porL=ri(prev,f.orL),porS=ri(prev,f.orS),porSp=ri(prev,f.orSp);
      var poi=ri(prev,f.oi);
      h+='<tr class="chg-row"><td style="font-style:italic;color:#666;">Chg vs '+prev.report_date_as_yyyy_mm_dd.substring(0,10)+'</td>';
      h+=chgCell(pmL-ppmL)+chgCell(pmS-ppmS)+chgCell((pmL-pmS)-(ppmL-ppmS));
      h+=chgCell(sdL-psdL)+chgCell(sdS-psdS)+chgCell(sdSp-psdSp)+chgCell((sdL-sdS)-(psdL-psdS));
      h+=chgCell(mmL-pmmL)+chgCell(mmS-pmmS)+chgCell(mmSp-pmmSp)+chgCell((mmL-mmS)-(pmmL-pmmS));
      h+=chgCell(orL-porL)+chgCell(orS-porS)+chgCell(orSp-porSp)+chgCell((orL-orS)-(porL-porS));
      h+=chgCell(oi-poi)+'</tr>';
    }
  }
  h+='</tbody></table></div>';
  return h;
}

function buildWeeklyDetail(){
  if(!rawCache||!rawCache.length||!CD)return;
  var comm=CD.comm||'';
  document.getElementById('wdTitle').textContent='📋 '+comm.split(' - ')[0]+' — 4-Week Positioning Detail (All Trader Categories)';

  /* Summary line from procData (all-crop, MM) */
  var mm=procData(rawCache,'managed_money','all');
  if(mm&&mm.net.length){
    var l=mm.net.length-1,p2=Math.max(0,l-1);
    var mmN=mm.net[l],mmC=mmN-(mm.net[p2]||0),mmL=mm.long[l],mmS=mm.short[l];
    var note=cropInfo?' <em style="color:#8B6914;">⚠ Cross-crop-year spreading only visible in All Crop row.</em>':'';
    document.getElementById('wdSummary').innerHTML=
      '<strong>Latest week ('+mm.dates[l].substring(0,10)+'):</strong> Managed Money net <strong style="color:'+(mmN>=0?'#1a8c4e':'#c0392b')+'">'+mmN.toLocaleString()+'</strong>'+
      ' ('+(mmC>=0?'+':'')+mmC.toLocaleString()+' w/w, '+pct(mm.net,mmN).toFixed(0)+'th %ile since '+mm.dates[0].substring(0,4)+').'+
      ' Gross long '+mmL.toLocaleString()+' ('+pct(mm.long,mmL).toFixed(0)+'th %ile),'+
      ' gross short '+mmS.toLocaleString()+' ('+pct(mm.short,mmS).toFixed(0)+'th %ile).'+
      ' OI: '+(mm.oi[l]||0).toLocaleString()+'.'+note;
  }

  var cont=document.getElementById('wdTables');cont.innerHTML='';
  var weeks=4;

  if(cropInfo){
    var secs=[
      {lbl:'🌾 Old Crop — expiring/current crop year',  cls:'hdr-old',   sfx:'old'},
      {lbl:'🌱 Other Crop — subsequent crop year',       cls:'hdr-other', sfx:'other'},
      {lbl:'📊 All Crop Years — aggregate (cross-year spreading here)', cls:'hdr-all', sfx:'all'}
    ];
    secs.forEach(function(sec){
      var wrap=document.createElement('div');wrap.className='weekly-crop-section';
      var hdr=document.createElement('div');hdr.className='weekly-crop-hdr '+sec.cls;hdr.textContent=sec.lbl;
      wrap.appendChild(hdr);
      var inner=document.createElement('div');inner.innerHTML=buildWDSection(rawCache,sec.sfx,weeks);
      wrap.appendChild(inner);cont.appendChild(wrap);
    });
    /* Crop notes at bottom of this section */
    var notesDiv=document.createElement('div');
    notesDiv.style.cssText='margin-top:16px;background:rgba(139,105,20,0.08);border-left:4px solid #8B6914;border-radius:6px;padding:12px 16px;font-size:0.82em;color:#1a1a1a;';
    notesDiv.innerHTML='<strong style="color:#8B6914;">&#x1F4C5; Crop Year Breakdown — '+comm.split(' - ')[0]+'</strong> '+
      (cropInfo?'(Crop year: '+cropInfo.first+' &rarr; '+cropInfo.last+')':'')+
      '<br><strong>Old Crop:</strong> Futures for the current/expiring crop year. '+
      '<strong>Other Crop:</strong> All subsequent futures months. '+
      '<strong>All:</strong> Aggregate — cross-crop-year spreading only appears in the All Crop view. '+
      'Old + Other spread positions will NOT sum to All spread due to cross-year spreading.';
    cont.appendChild(notesDiv);
  } else {
    var wrap=document.createElement('div');wrap.className='weekly-crop-section';
    var hdr=document.createElement('div');hdr.className='weekly-crop-hdr hdr-all';hdr.textContent='📊 All Positions';
    wrap.appendChild(hdr);
    var inner=document.createElement('div');inner.innerHTML=buildWDSection(rawCache,'all',weeks);
    wrap.appendChild(inner);cont.appendChild(wrap);
  }
}


/* ===========================================================
   PRICE OVERLAY — roll-adjusted weekly price on a right-hand axis.
   Only drawn when the pre-computed series has a current price feed;
   if Yahoo is missing or stale the series carries no price and the
   charts simply show positions alone.
   =========================================================== */
var PXC={};
function curTicker(){var s=document.getElementById('commoditySelect');var o=s&&s.options[s.selectedIndex];return o?o.getAttribute('data-tk'):null;}
function addPx(key){
  var t=curTicker(),chart=charts[key];if(!t||!CD||!chart)return;
  var go=function(map){
    if(!map||charts[key]!==chart)return;
    var data=CD.dates.map(function(d){return{x:d,y:map[d]==null?null:map[d]};});
    if(data.filter(function(p){return p.y!=null;}).length<CD.dates.length*0.5)return;
    chart.data.datasets.push({label:'Price (roll-adjusted)',data:data,borderColor:'rgba(70,70,70,.75)',borderWidth:1.3,borderDash:[4,3],pointRadius:0,fill:false,yAxisID:'y1',tension:0.2,spanGaps:false});
    chart.options.scales.y1={position:'right',grid:{drawOnChartArea:false},ticks:{font:{size:9},color:'#555'},title:{display:true,text:'Price',font:{size:10,weight:'bold'},color:'#555'}};
    chart.options.plugins.legend.display=true;chart.update('none');
  };
  if(t in PXC)return go(PXC[t]);
  COTStore.series(t).then(function(s){
    var m=null,n=0;
    if(s&&s.px){m={};s.dates.forEach(function(d,i){if(s.px[i]!=null){m[d]=s.px[i];n++;}});if(n<20)m=null;}
    PXC[t]=m;go(m);
  }).catch(function(){PXC[t]=null;});
}
