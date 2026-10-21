/* ===========================================================
   TAB SWITCHING
   =========================================================== */
function switchTab(tab, keepHash){
  if(!keepHash && tab!=='cot'){ try{ history.replaceState(null,'','#'+tab); }catch(e){} }
  var allTabs = ['cot','summary','scatter','index','levels','seasonality','formula','ai'];
  allTabs.forEach(function(t){
    var pane = document.getElementById('pane_'+t);
    var btn = document.getElementById('tb_'+t);
    if(pane) pane.style.display = t===tab ? 'block' : 'none';
    if(btn) btn.classList.toggle('active', t===tab);
  });

  // Load tab content on demand
  if(tab==='cot' && !_tabLoaded['cot']){
    loadTab('cot', 'tabs/cot-tab.html', 'js/cot-tab.js').then(function(){ initCotTab(); });
  }
  if(tab==='summary' && !_tabLoaded['summary']){
    loadTab('summary', 'tabs/summary-tab.html', 'js/summary-tab.js').then(function(){ initSummaryTab(); });
  }
  if(tab==='scatter' && !_tabLoaded['scatter']){
    loadTab('scatter', 'tabs/scatter-tab.html', 'js/scatter-tab.js').then(function(){ initScatterTab(); });
  }
  if(tab==='index' && !_tabLoaded['index']){
    loadTab('index', 'tabs/index-tab.html', 'js/index-tab.js').then(function(){ initIndexTab(); });
  }
  if(tab==='levels' && !_tabLoaded['levels']){
    loadTab('levels', 'tabs/levels-tab.html', 'js/levels-tab.js').then(function(){ initLevelsTab(); });
  }
  if(tab==='seasonality' && !_tabLoaded['seasonality']){
    loadTab('seasonality', 'tabs/seasonality-tab.html', 'js/seasonality-tab.js').then(function(){ initSeasonalityTab(); });
  }
  if(tab==='formula' && !_tabLoaded['formula']){
    loadTab('formula', 'tabs/formula-tab.html', 'js/formula-tab.js').then(function(){ initFormulaTab(); });
  }
  if(tab==='ai' && !_tabLoaded['ai']){
    loadTab('ai', 'tabs/ai-tab.html', 'js/ai-tab.js').then(function(){ initAiTab(); });
  }

  // Call init functions for already-loaded tabs
  if(tab==='ai' && _tabLoaded['ai']) initAiTab();
  if(tab==='formula' && _tabLoaded['formula']) initFormulaTab();
  // First visit to the COT Analyzer: show Cotton straight away instead of an empty page
  if(tab==='cot' && _tabLoaded['cot']) autoLoadDefaultMarket();
  if(tab==='cot' && !_tabLoaded['cot']) setTimeout(function wait(){ if(_tabLoaded['cot']) autoLoadDefaultMarket(); else setTimeout(wait,150); },150);
}

/* ===========================================================
   AI TAB — Groq integration + pre-computed data
   =========================================================== */
var _aiInited = false;


var _autoLoaded=false;
function autoLoadDefaultMarket(){
  if(_autoLoaded||typeof CD==='undefined'||CD)return;
  var sel=document.getElementById('commoditySelect');if(!sel||sel.value)return;
  var o=sel.querySelector('option[data-tk="CT"]');if(!o)return;
  _autoLoaded=true;sel.value=o.value;
  if(typeof onCommChange==='function')onCommChange();
  if(typeof fetchData==='function')fetchData();
}


/* ===========================================================
   DIRECT LINKS & MARKET SEARCH
   #CT, #KC ... open that market in the COT Analyzer;
   #summary, #index, #levels ... open a tab.
   =========================================================== */
var TAB_IDS=['summary','cot','scatter','index','levels','seasonality','formula','ai'];
function openMarket(tk){
  if(!tk)return;tk=String(tk).toUpperCase();
  _autoLoaded=true;
  switchTab('cot',true);
  try{ history.replaceState(null,'','#'+tk); }catch(e){}
  (function wait(n){
    var sel=document.getElementById('commoditySelect');
    var o=sel&&sel.querySelector('option[data-tk="'+tk+'"]');
    if(!o){ if(n<60) setTimeout(function(){wait(n+1);},150); return; }
    sel.value=o.value;
    if(typeof onCommChange==='function')onCommChange();
    if(typeof fetchData==='function')fetchData();
    window.scrollTo(0,0);
  })(0);
}
function routeHash(){
  var h=(location.hash||'').replace('#','');
  if(!h){switchTab('summary');return;}
  if(TAB_IDS.indexOf(h.toLowerCase())>=0){switchTab(h.toLowerCase(),true);return;}
  openMarket(h);
}
function initMarketSearch(){
  var dl=document.getElementById('mktList'),inp=document.getElementById('mktSearch');if(!dl||!inp)return;
  COTStore.manifest().then(function(m){
    dl.innerHTML=(m.commodities||[]).map(function(c){return '<option value="'+c.name+' ('+c.ticker+')">';}).join('');
  }).catch(function(){});
  var go=function(){
    var v=(inp.value||'').trim();if(!v)return;
    var mt=v.match(/\(([A-Z]{1,3})\)$/), tk=mt?mt[1]:null;
    if(!tk){ var o=document.querySelector('#mktList option[value^="'+v.replace(/"/g,'')+'" i]')||Array.prototype.find.call(document.querySelectorAll('#mktList option'),function(x){return x.value.toLowerCase().indexOf(v.toLowerCase())>=0;}); if(o){var m2=o.value.match(/\(([A-Z]{1,3})\)$/);tk=m2?m2[1]:null;} else tk=v.toUpperCase(); }
    inp.value='';inp.blur();openMarket(tk);
  };
  inp.addEventListener('change',go);
  inp.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();go();}});
}
