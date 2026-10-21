/* ===========================================================
   SEASONALITY TAB — Weekly Seasonality + Agri Crop Analysis
   Loaded dynamically by tab-switching.js
   =========================================================== */

function initSeasonalityTab() {
  /* Show the weekly seasonality straight away from cached static data —
     no need to click Generate in the COT tab first. */
  document.getElementById('chart5').style.display = 'block';
  buildSeaCommSel();
  if (!document.querySelector('#seaYrSel .yr-chip')) popYears();
  drawSea();
  doAgriCrop();
}

/* ===========================================================
   SEASONALITY (All BCOM)
   =========================================================== */
function buildSeaCommSel(){
  var ct=document.getElementById('seaCommSel');
  while(ct.children.length>1)ct.removeChild(ct.lastChild);
  if(!allBCOM.length)return;
  var allApis=allBCOM.map(function(c){return c.api;});
  var ba=document.createElement('button');ba.type='button';ba.className='chip-all comm-chip';ba.textContent='ALL';ba.style.cssText='margin-top:0;min-width:auto;';
  ba.onclick=function(){seaComms=new Set(allApis);refreshSeaChips();drawSea();};ct.appendChild(ba);
  var bn=document.createElement('button');bn.type='button';bn.className='chip-none comm-chip';bn.textContent='NONE';bn.style.cssText='margin-top:0;min-width:auto;';
  bn.onclick=function(){seaComms=new Set([allApis[0]]);refreshSeaChips();drawSea();};ct.appendChild(bn);
  /* Default: always start with just the currently-selected commodity */
  var dflt=CD&&allApis.indexOf(CD.comm)!==-1?CD.comm:(allBCOM.filter(function(b){return b.ticker==='CT';})[0]||allBCOM[0]).api;
  seaComms=new Set([dflt]);
  var cs='';
  allBCOM.forEach(function(bc){
    if(bc.sector!==cs){cs=bc.sector;var lb=document.createElement('span');lb.textContent='—'+bc.sector.split('(')[0].trim()+'—';lb.style.cssText='font-size:0.7em;color:#666;white-space:nowrap;';ct.appendChild(lb);}
    var ch=document.createElement('span');ch.className='comm-chip';ch.setAttribute('data-api',bc.api);ch.textContent=bc.name;
    ch.onclick=(function(api){return function(){if(seaComms.has(api)){if(seaComms.size>1)seaComms.delete(api);}else seaComms.add(api);refreshSeaChips();drawSea();};})(bc.api);
    ct.appendChild(ch);
  });refreshSeaChips();
}
function refreshSeaChips(){
  document.querySelectorAll('#seaCommSel [data-api]').forEach(function(el){el.classList.toggle('active',seaComms.has(el.getAttribute('data-api')));});
  var el=document.getElementById('seaCount');if(el)el.textContent='('+seaComms.size+'/'+allBCOM.length+')';
}
function popYears(){
  var ys={};
  if(CD&&CD.dates.length){CD.dates.forEach(function(d){ys[+d.slice(0,4)]=true;});}
  else{var y1=COTStore.man?+COTStore.man.report_date.slice(0,4):new Date().getFullYear();for(var y=2006;y<=y1;y++)ys[y]=true;}
  var yrs=Object.keys(ys).map(Number).sort(),ct=document.getElementById('seaYrSel');if(!ct)return;ct.innerHTML='<strong style="font-size:0.85em;">Years:</strong>';
  seaYrs=new Set(yrs.slice(-3));
  yrs.forEach(function(y){var c=document.createElement('div');c.className='yr-chip'+(seaYrs.has(y)?' active':'');c.textContent=y;c.onclick=function(){if(seaYrs.has(y)&&seaYrs.size>1){seaYrs.delete(y);c.classList.remove('active');}else if(!seaYrs.has(y)){seaYrs.add(y);c.classList.add('active');}drawSea();};ct.appendChild(c);});
}
var seaRaw={};  /* api -> raw source (static series wrapper or live records); category applied per draw */
function seaLoad(api,ep){
  if(seaRaw[api])return Promise.resolve(seaRaw[api]);
  return COTStore.seriesForApi(api).then(function(ser){return seaRaw[api]=staticRaw(ser,api);})
  .catch(function(){
    return fetchT(ep+"?$where="+liveWhere(api)+" AND report_date_as_yyyy_mm_dd >= '2006-01-01'&$order=report_date_as_yyyy_mm_dd ASC&$limit=10000",25000)
      .then(function(r){return r.json();}).then(function(d){if(d.length)seaRaw[api]=d;return seaRaw[api];});
  });
}
function drawSea(){
  if(!document.getElementById('seaChart'))return;
  var metric=document.getElementById('seaMet').value,agg=document.getElementById('seaAgg').value;
  var comms=Array.from(seaComms);if(!comms.length)return;
  var tc=document.getElementById('traderCategory')?document.getElementById('traderCategory').value:'managed_money';
  var ep=EP[document.getElementById('reportType')?document.getElementById('reportType').value:'combined']||EP.combined;
  var note=document.getElementById('seaNote');if(note&&comms.some(function(c){return!seaRaw[c];}))note.textContent='Loading…';
  Promise.all(comms.map(function(c){return seaLoad(c,ep).catch(function(){return null;});})).then(function(){
    var map={};comms.forEach(function(c){if(seaRaw[c]){var p=procData(seaRaw[c],tc,'all');if(p)map[c]=p;}});
    var band=document.getElementById('seaBand');
    renderSea(metric,agg,comms,'seaChart','sea','seaNote',seaYrs,map,band&&band.checked);
  });
}

function renderSea(metric,agg,comms,canvasId,chartKey,noteId,yearsSet,dataMap,showBand){
  var src=dataMap||seaCache,yd={},maxYr=0;
  comms.forEach(function(comm){var p=src[comm];if(p&&p.dates.length)maxYr=Math.max(maxYr,+p.dates[p.dates.length-1].slice(0,4));});
  var bandYrs={};if(showBand)for(var by=maxYr-5;by<maxYr;by++)bandYrs[by]=true;
  var cw={}; /* comm|yr|week -> {s,c}: average within a week per market first (two reports can share an ISO week after holidays/shutdowns) */
  comms.forEach(function(comm){var p=src[comm];if(!p)return;
    p.dates.forEach(function(date,di){var yr=+date.slice(0,4);if(!yearsSet.has(yr)&&!bandYrs[yr])return;var w=wk(new Date(date));var key=comm+'|'+yr+'|'+w;if(!cw[key])cw[key]={yr:yr,w:w,s:0,c:0};
      var v=0;switch(metric){case'net':v=p.net[di];break;case'long':v=p.long[di];break;case'short':v=p.short[di];break;case'net_pct':v=p.nPct[di];break;case'traders_total':v=p.tT[di];break;case'per_trader_long':v=p.plL[di];break;case'per_trader_short':v=p.plS[di];break;}
      cw[key].s+=v;cw[key].c+=1;
    });
  });
  Object.keys(cw).forEach(function(k2){var e=cw[k2];if(!yd[e.yr])yd[e.yr]={};if(!yd[e.yr][e.w])yd[e.yr][e.w]={s:0,c:0};yd[e.yr][e.w].s+=e.s/e.c;yd[e.yr][e.w].c+=1;});
  var yc=['#c0392b','#d4880f','#f39c12','#1a8c4e','#2980b9','#8e44ad','#16a085','#d35400','#2c3e50','#1abc9c'];
  var sy=Array.from(yearsSet).sort(),ds=[];
  if(showBand){
    var lo=new Array(53).fill(null),hi=new Array(53).fill(null),av=new Array(53).fill(null),nb=0;
    for(var w2=1;w2<=53;w2++){var vals=[];Object.keys(bandYrs).forEach(function(y){var e=yd[y]&&yd[y][w2];if(e&&e.c)vals.push(agg==='sum'?e.s:e.s/e.c);});
      if(vals.length>=3){lo[w2-1]=Math.min.apply(null,vals);hi[w2-1]=Math.max.apply(null,vals);av[w2-1]=vals.reduce(function(a,b){return a+b;},0)/vals.length;nb=Math.max(nb,vals.length);}}
    if(nb){var bl=(maxYr-5)+'–'+(maxYr-1);
      ds.push({label:bl+' range',data:hi,borderWidth:0,pointRadius:0,backgroundColor:'rgba(42,82,152,0.10)',fill:'+1',spanGaps:true,order:10});
      ds.push({label:'_lo',data:lo,borderWidth:0,pointRadius:0,fill:false,spanGaps:true,order:10});
      ds.push({label:bl+' avg',data:av,borderColor:'rgba(42,82,152,0.55)',borderDash:[5,4],borderWidth:1.5,pointRadius:0,fill:false,spanGaps:true,order:9,tension:0.3});}
  }
  sy.forEach(function(yr,yi){if(!yd[yr]||!yearsSet.has(yr))return;var wd=new Array(53).fill(null);for(var w=1;w<=53;w++){var e=yd[yr][w];if(!e||e.c===0)continue;wd[w-1]=agg==='sum'?e.s:(e.s/e.c);}ds.push({label:String(yr),data:wd,borderColor:yc[yi%yc.length],borderWidth:2.5,pointRadius:2,pointHoverRadius:5,spanGaps:true,fill:false,tension:0.3});});
  var ml={net:'Net',long:'Long',short:'Short',net_pct:'Net%OI',traders_total:'Traders',per_trader_long:'L/Trader',per_trader_short:'S/Trader'};
  var nm=function(c){var it=COTStore.itemByApi(c);return it?it.name:c.split(' - ')[0];};var cl=comms.length<=3?comms.map(nm).join(', '):comms.length+' commodities';
  var ne=document.getElementById(noteId);if(ne)ne.innerHTML='<strong>Showing:</strong> '+cl+' | <strong>Metric:</strong> '+ml[metric]+' | <strong>Agg:</strong> '+(agg==='sum'?'Sum':'Avg');
  var wl=[];for(var i=1;i<=53;i++)wl.push('W'+i);
  var ip=metric.indexOf('pct')!==-1;
  var ctx=document.getElementById(canvasId).getContext('2d');
  if(charts[chartKey])charts[chartKey].destroy();
  charts[chartKey]=new Chart(ctx,{type:'line',data:{labels:wl,datasets:ds},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{title:{display:true,text:cl+' — '+ml[metric]+' ('+(agg==='sum'?'Sum':'Avg')+')',font:{size:11,weight:'bold'},color:'#1a1a1a'},legend:{position:'top',labels:{boxWidth:11,font:{size:9},color:'#333',filter:function(i){return i.text.charAt(0)!=='_';}}},tooltip:{filter:function(i){return i.dataset.label.charAt(0)!=='_'&&i.raw!=null;},callbacks:{title:function(it){return 'Week '+parseInt(it[0].label.replace('W',''));},label:function(it){return it.dataset.label+': '+Number(it.raw).toLocaleString(undefined,{maximumFractionDigits:ip?2:0});}}}},scales:{x:{title:{display:true,text:'Week',font:{size:9},color:'#333'},ticks:{callback:function(v,i){return i%4===0?'W'+(i+1):'';},font:{size:8},color:'#333'}},y:{title:{display:true,text:ml[metric],font:{weight:'bold',size:9},color:'#333'},ticks:{callback:function(v){return ip?v.toFixed(0)+'%':(Math.abs(v)>=1000?(v/1000).toFixed(0)+'k':v);},font:{size:9},color:'#333'}}}}});
}



/* ===========================================================
   AGRI CROP — Fetch all crop-year BCOM commodities
   =========================================================== */
function getCropBCOM(){return allBCOM.filter(function(c){return CROP_COMM[c.name];});}

function doAgriCrop(){
  var cropComms=getCropBCOM();
  if(!cropComms.length){showE('No crop commodities loaded. Try loading commodity list first.');return;}
  var ep=EP.combined,tot=cropComms.length,done=0;
  cropComms.forEach(function(it){
    if(agriRaw[it.api]){done++;if(done>=tot)onAllAgriDone();return;}
    COTStore.seriesForApi(it.api).then(function(ser){agriRaw[it.api]=staticRaw(ser,it.api);})
    .catch(function(){
      return fetchT(ep+"?$where="+liveWhere(it.api)+" AND report_date_as_yyyy_mm_dd >= '2006-01-01'&$order=report_date_as_yyyy_mm_dd ASC&$limit=10000",25000)
        .then(function(r){return r.json();}).then(function(data){if(data.length>0)agriRaw[it.api]=data;});
    })
    .catch(function(e){console.warn('Crop data fail:',it.name,e);})
    .finally(function(){done++;if(done>=tot)onAllAgriDone();});
  });
}

function onAllAgriDone(){
  if(!document.getElementById('agriExecSec'))return;
  buildAgriExec();
  buildAgriSum();
  buildAgriSeaSel();
  document.getElementById('agriExecSec').style.display='block';
  document.getElementById('agriSumSec').style.display='block';
  document.getElementById('agriSeaSec').style.display='block';
  drawAllAgriSea();
  showL(false);
}

/* ===========================================================
   AGRI EXEC SUMMARY
   =========================================================== */
var agriExecData={old:[],other:[],all:[]};

function buildAgriExec(){
  var cropComms=getCropBCOM();
  ['old','other','all'].forEach(function(ct){
    agriExecData[ct]=[];
    cropComms.forEach(function(it,idx){
      var raw=agriRaw[it.api];if(!raw||!raw.length)return;
      var mm=procData(raw,'managed_money',ct);if(!mm||!mm.net.length)return;
      var l=mm.net.length-1;
      agriExecData[ct].push({comm:it.name,idx:idx,mSP:pct(mm.short,mm.short[l]),mLP:pct(mm.long,mm.long[l]),mNP:pct(mm.net,mm.net[l]),mSPoi:pct(mm.sPct,mm.sPct[l]),mLPoi:pct(mm.lPct,mm.lPct[l]),mNPoi:pct(mm.nPct,mm.nPct[l])});
    });
    renderAgriExecPanel(ct);
  });
}

function renderAgriExecPanel(ct){
  var data=agriExecData[ct];
  if(!data||!data.length){document.getElementById('agriTxt_'+ct).textContent='No data for this crop type.';return;}
  var gs=data.slice().sort(function(a,b){return b.mSP-a.mSP;});
  var ns=data.slice().sort(function(a,b){return a.mNP-b.mNP;});
  var gl=data.slice().sort(function(a,b){return a.mLP-b.mLP;});
  var gso=data.slice().sort(function(a,b){return b.mSPoi-a.mSPoi;});
  var nso=data.slice().sort(function(a,b){return a.mNPoi-b.mNPoi;});
  var glo=data.slice().sort(function(a,b){return a.mLPoi-b.mLPoi;});
  function pColor(p,r,g,b){var a=0.08+0.52*(p/100);return 'rgba('+r+','+g+','+b+','+a.toFixed(2)+')';}
  function fill(id,arr,field,r,g,b,inv){var tb=document.getElementById(id);if(!tb)return;tb.innerHTML='';arr.forEach(function(it){var v=inv?100-it[field]:it[field];v=Math.max(0,Math.min(100,v));var tr=document.createElement('tr');tr.innerHTML='<td>'+it.comm+'</td><td style="background:'+pColor(v,r,g,b)+';color:#1a1a1a;">'+v.toFixed(1)+'%</td>';tb.appendChild(tr);});}
  fill('ag_gs_'+ct,gs,'mSP',231,76,60,false);fill('ag_ns_'+ct,ns,'mNP',243,156,18,true);fill('ag_gl_'+ct,gl,'mLP',39,174,96,false);fill('ag_gso_'+ct,gso,'mSPoi',169,50,38,false);fill('ag_nso_'+ct,nso,'mNPoi',183,149,11,true);fill('ag_glo_'+ct,glo,'mLPoi',30,132,73,false);
  var eS=[],eL=[],cS=[],cL=[],longC=[],shortC=[];
  data.forEach(function(d){if(d.mSP>=80)eS.push(d.comm);if(d.mLP>=80)eL.push(d.comm);if(d.mNP<=15)cS.push(d.comm);if(d.mNP>=85)cL.push(d.comm);if(d.mSP>=75&&d.mNP<=25)longC.push(d.comm);if(d.mLP>=75&&d.mNP>=75)shortC.push(d.comm);});
  var ctLbl={'old':'Old Crop','other':'Other Crop','all':'All Crop Years'}[ct];
  var txt='<strong>BCOM Managed Money Positioning Analysis — '+ctLbl+' (Historical Percentile Since 2006):</strong><br>';
  txt+='Crop-year breakdowns reveal how speculative positioning differs between near-term delivery contracts (Old Crop) and forward supply/demand expectations (Other Crop).<br><br>';
  if(eS.length)txt+='<strong>&#x1F534; Extreme Gross Short (&gt;80th %ile):</strong> '+eS.join(', ')+' — Limited room to add shorts; contrarian LONG bias favored.<br>';
  if(cS.length)txt+='<strong>&#x1F7E0; Extreme Net Short (&lt;15th %ile):</strong> '+cS.join(', ')+' — Max bearish; short-covering risk elevated.<br>';
  if(eL.length)txt+='<strong>&#x1F7E2; Extreme Gross Long (&gt;80th %ile):</strong> '+eL.join(', ')+' — Crowded longs; liquidation risk.<br>';
  if(cL.length)txt+='<strong>&#x1F535; Extreme Net Long (&gt;85th %ile):</strong> '+cL.join(', ')+' — Contrarian SHORT bias.<br>';
  if(!eS.length&&!eL.length&&!cS.length&&!cL.length)txt+='No extremes in '+ctLbl+' currently.<br>';
  txt+='<br>';
  if(longC.length)txt+='<strong>&#x2705; Long Candidates:</strong> '+longC.join(', ')+'<br>';
  if(shortC.length)txt+='<strong>&#x274C; Short Candidates:</strong> '+shortC.join(', ')+'<br>';
  document.getElementById('agriTxt_'+ct).innerHTML=txt;
}

function switchAgriExec(ct){
  ['old','other','all'].forEach(function(t){
    document.getElementById('aep_'+t).classList.toggle('active',t===ct);
    var tab=document.getElementById('aet_'+t);if(!tab)return;
    tab.classList.remove('active-old','active-other','active-all');
    if(t===ct)tab.classList.add('active-'+ct);
  });
}

/* ===========================================================
   AGRI MARKET SUMMARY
   =========================================================== */
var agriSumData={old:[],other:[],all:[]};

function buildAgriSum(){
  var cropComms=getCropBCOM();
  ['old','other','all'].forEach(function(ct){
    agriSumData[ct]=[];
    cropComms.forEach(function(it){
      var raw=agriRaw[it.api];if(!raw||!raw.length)return;
      CATS.forEach(function(cat){
        var p=procData(raw,cat,ct);if(!p||!p.net.length)return;
        var l=p.net.length-1;
        agriSumData[ct].push({comm:it.name,cat:CAT_LBL[cat],catKey:cat,sec:it.sector,net:p.net[l],netMn:Math.min.apply(null,p.net),netMx:Math.max.apply(null,p.net),nPct:p.nPct[l],nPctMn:Math.min.apply(null,p.nPct),nPctMx:Math.max.apply(null,p.nPct),lon:p.long[l],lonMn:Math.min.apply(null,p.long),lonMx:Math.max.apply(null,p.long),lPct:p.lPct[l],lPctMn:Math.min.apply(null,p.lPct),lPctMx:Math.max.apply(null,p.lPct),sho:p.short[l],shoMn:Math.min.apply(null,p.short),shoMx:Math.max.apply(null,p.short),sPct:p.sPct[l],sPctMn:Math.min.apply(null,p.sPct),sPctMx:Math.max.apply(null,p.sPct)});
      });
    });
    renderSum('asb_'+ct,agriSumData[ct]);
  });
}

function switchAgriSum(ct){
  ['old','other','all'].forEach(function(t){
    document.getElementById('amp_'+t).classList.toggle('active',t===ct);
    var tab=document.getElementById('amt_'+t);if(!tab)return;
    tab.classList.remove('active-old','active-other','active-all');
    if(t===ct)tab.classList.add('active-'+ct);
  });
}

/* ===========================================================
   AGRI SEASONALITY
   =========================================================== */
function buildAgriSeaSel(){
  var cropComms=getCropBCOM();
  var ct=document.getElementById('aSeaCommSel');
  while(ct.children.length>1)ct.removeChild(ct.lastChild);
  if(agriSeaComms.size===0&&cropComms.length>0){
    /* Default: the currently selected commodity if it's a crop comm, else first crop comm */
    var selApi=CD?CD.comm:null;
    var selIsCrop=selApi&&cropComms.some(function(c){return c.api===selApi;});
    agriSeaComms=new Set([selIsCrop?selApi:cropComms[0].api]);
  }
  cropComms.forEach(function(bc){
    if(!agriRaw[bc.api])return;
    var ch=document.createElement('span');ch.className='comm-chip';ch.setAttribute('data-aapi',bc.api);ch.textContent=bc.name;
    ch.onclick=(function(api){return function(){if(agriSeaComms.has(api)){if(agriSeaComms.size>1)agriSeaComms.delete(api);}else agriSeaComms.add(api);refreshAgriSeaChips();drawAllAgriSea();};})(bc.api);
    ct.appendChild(ch);
  });
  refreshAgriSeaChips();
  /* Collect ALL years from agriRaw — full history since 2006 */
  var yrSet={};
  Object.keys(agriRaw).forEach(function(api){
    var arr=agriRaw[api];if(!arr)return;
    if(arr.__series){arr.__series.dates.forEach(function(d){var y=+d.slice(0,4);if(y>=2006)yrSet[y]=true;});return;}
    arr.forEach(function(d){var y=new Date(d.report_date_as_yyyy_mm_dd).getFullYear();if(y>=2006)yrSet[y]=true;});
  });
  var yrs=Object.keys(yrSet).map(Number).sort();
  if(!yrs.length){var now=new Date().getFullYear();for(var y2=2006;y2<=now;y2++)yrs.push(y2);}
  if(agriSeaYrs.size===0)agriSeaYrs=new Set(yrs.slice(-3));
  var ySel=document.getElementById('aSeaYrSel');ySel.innerHTML='<strong style="font-size:0.85em;">Years ('+yrs[0]+'–'+yrs[yrs.length-1]+'):</strong>';
  yrs.forEach(function(y){
    var c=document.createElement('div');c.className='yr-chip'+(agriSeaYrs.has(y)?' active':'');c.textContent=y;
    c.onclick=function(){if(agriSeaYrs.has(y)&&agriSeaYrs.size>1){agriSeaYrs.delete(y);c.classList.remove('active');}else if(!agriSeaYrs.has(y)){agriSeaYrs.add(y);c.classList.add('active');}drawAllAgriSea();};
    ySel.appendChild(c);
  });
}
function refreshAgriSeaChips(){
  document.querySelectorAll('#aSeaCommSel [data-aapi]').forEach(function(el){el.classList.toggle('active',agriSeaComms.has(el.getAttribute('data-aapi')));});
  var el=document.getElementById('aSeaCount');if(el)el.textContent='('+agriSeaComms.size+')';
}
/* Draw one agri sea chart for a given crop type into a specific canvas */
function drawOneAgriSea(ct, canvasId, noteId){
  var metric=document.getElementById('aSMet').value,agg=document.getElementById('aSAgg').value;
  var tc=document.getElementById('traderCategory')?document.getElementById('traderCategory').value||'managed_money':'managed_money';
  var comms=Array.from(agriSeaComms);if(!comms.length)return;
  var map={};
  comms.forEach(function(api){var raw=agriRaw[api];if(!raw)return;var p=procData(raw,tc,ct);if(p)map[api]=p;});
  var band=document.getElementById('aSeaBand');
  renderSea(metric,agg,comms,canvasId,'agriSea_'+ct,noteId,agriSeaYrs,map,band&&band.checked);
}
function drawAllAgriSea(){
  drawOneAgriSea('old',  'aSeaChartOld',   'aSeaNoteOld');
  drawOneAgriSea('other','aSeaChartOther','aSeaNoteOther');
  drawOneAgriSea('all',  'aSeaChartAll',   'aSeaNoteAll');
}

