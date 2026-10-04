'use strict';
const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
  scan:'<path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3"/><circle cx="12" cy="12" r="5"/><path d="M7 12h10m-5-5v10"/>',
  plus:'<path d="M12 5v14M5 12h14"/>', minus:'<path d="M5 12h14"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1.5 1-1.5 1-1.5 2"/><path d="M12 16h.01"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  contrast:'<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18Z" fill="currentColor" stroke="none"/>',
  expand:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  external:'<path d="M14 3h7v7m0-7L11 13M10 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>', check:'<path d="m5 12 4 4L19 6"/>',
  'chevron-left':'<path d="m15 6-6 6 6 6"/>', 'chevron-right':'<path d="m9 6 6 6-6 6"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.scan}</svg>`;
const $ = id => document.getElementById(id);
document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon));
const presets = {lung: {name:'Poumon', c:-600, w:1500}, soft: {name:'Tissus mous', c:40, w:400}, bone: {name:'Os', c:400, w:1800}};
const query = new URLSearchParams(location.search);
const detached = query.has('view');
function stored(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Private browsing may disable persistence. */ } }
const savedFavorites = stored('lumina-favorites', []);
const state = {series:[], active:null, selected:0, mode:'overview', favoritesOnly:false,
  favorites:new Set(Array.isArray(savedFavorites) ? savedFavorites.filter(x => typeof x === 'string') : []),
  preset:'lung', search:'', gridZoom:Math.min(160, Math.max(70, Number(stored('lumina-grid-zoom',100)) || 100))};
let viewerState = null, toastTimer, selectRequest = 0, contrastTimer, dragDepth = 0;
const fmt = (n, digits=2) => n == null ? '—' : new Intl.NumberFormat('fr-FR', {maximumFractionDigits:digits}).format(n);
const sliceName = n => `Coupe ${String(n + 1).padStart(3, '0')}`;
const favoriteKey = (sid, index) => `${sid}:${index}`;
function notify(message, error=false, persistent=false) {
  clearTimeout(toastTimer); $('toast').textContent = message; $('toast').classList.toggle('error', error); $('toast').hidden = false;
  if (!persistent) toastTimer = setTimeout(() => $('toast').hidden = true, 5000);
}
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'La requête a échoué.');
  return data;
}
function imageUrl(sid, index, c, w, invert=false) {
  return `/api/image?${new URLSearchParams({series:sid, index, center:c, width:w, invert:invert ? 1 : 0})}`;
}
function getSeries(sid) { return state.series.find(s => s.id === sid); }
function updateFavoriteCounts() {
  const available = state.series.reduce((sum, s) => sum + [...state.favorites].filter(k => k.startsWith(`${s.id}:`) && Number(k.split(':')[1]) < s.count).length, 0);
  $('favorite-count').textContent = available;
}
function renderSeriesList() {
  $('series-count').textContent = state.series.length;
  updateFavoriteCounts(); $('series-list').replaceChildren();
  state.series.forEach(s => {
    const button = document.createElement('button'); button.className = `series-item${s.id === state.active ? ' selected' : ''}`;
    button.innerHTML = `<span class="series-icon">${icon('scan')}</span><span><strong></strong><small></small></span>${s.id === state.active ? '<span class="local-dot"></span>' : ''}`;
    button.querySelector('strong').textContent = s.name;
    button.querySelector('small').textContent = `${s.count} coupes · ${s.plane}`;
    button.setAttribute('aria-pressed', s.id === state.active); button.addEventListener('click', () => activateSeries(s.id));
    $('series-list').append(button);
  });
}
function activateSeries(sid) {
  const s = getSeries(sid); if (!s) return;
  state.active = sid; state.selected = Math.floor(s.count / 2); state.search = ''; $('search').value = '';
  renderSeriesList(); $('series-title').textContent = s.name;
  $('series-source').textContent = `${s.source} · ${s.calibrated ? 'Intensités calibrées en HU' : 'Calibration à vérifier'}`;
  $('series-plane').textContent = `ACQUISITION ${s.plane.toUpperCase()}`;
  $('stat-count').textContent = s.count; $('stat-matrix').textContent = `${s.columns} × ${s.rows}`;
  $('stat-spacing').textContent = s.slice_spacing == null ? '—' : `${fmt(s.slice_spacing)} mm`;
  $('detail-plane').textContent = s.plane.charAt(0).toUpperCase() + s.plane.slice(1);
  $('detail-matrix').textContent = `${s.columns} × ${s.rows} px`;
  $('detail-pixel').textContent = s.pixel_spacing.map(v => fmt(v,3)).join(' × ');
  $('geometry-warning').hidden = !s.warnings.length; $('geometry-warning').textContent = s.warnings.join(' ');
  renderGallery(); selectSlice(state.selected);
  document.querySelectorAll('.inspector button').forEach(el => el.disabled = false);
}
function setMode(mode) {
  state.mode = mode; $('overview-button').classList.toggle('selected',mode === 'overview'); $('all-button').classList.toggle('selected',mode === 'all'); renderGallery();
}
function setFavoritesOnly(value) {
  state.favoritesOnly = value; $('library-nav').classList.toggle('active',!value); $('favorites-nav').classList.toggle('active',value);
  document.querySelector('.breadcrumb strong').textContent = value ? 'Favoris' : 'Bibliothèque'; renderGallery();
}
function currentIndices() {
  const s = getSeries(state.active); if (!s) return [];
  let indices;
  if (state.mode === 'all' || state.search || state.favoritesOnly) indices = Array.from({length:s.count}, (_,i) => i);
  else indices = Array.from(new Set(Array.from({length:Math.min(24,s.count)}, (_,i) => s.count === 1 ? 0 : Math.round(i * (s.count-1)/(Math.min(24,s.count)-1)))));
  if (state.search) indices = indices.filter(i => String(i+1).padStart(3,'0').includes(state.search.trim()));
  if (state.favoritesOnly) indices = indices.filter(i => state.favorites.has(favoriteKey(s.id,i)));
  return indices;
}
function renderGallery() {
  const s = getSeries(state.active), indices = currentIndices(); $('gallery').replaceChildren();
  $('image-count').textContent = s ? `${indices.length} aperçu${indices.length === 1 ? '' : 's'} · ${s.count} coupe${s.count === 1 ? '' : 's'}` : 'Aucune série';
  if (!indices.length) {
    const empty = document.createElement('div'); empty.className = 'empty-state';
    empty.innerHTML = `${icon(s ? (state.favoritesOnly ? 'heart' : 'search') : 'upload')}<h3></h3><p></p><button class="secondary-button"></button>`;
    empty.querySelector('h3').textContent = !s ? 'Votre bibliothèque commence ici' : state.favoritesOnly ? 'Aucun favori dans cette série' : 'Aucune coupe trouvée';
    empty.querySelector('p').textContent = !s ? 'Importez une série DICOM pour explorer ses images.' : state.favoritesOnly ? 'Cliquez sur le cœur d’une image pour la retrouver ici.' : 'Recherchez un numéro de coupe, par exemple « 42 ».';
    const button = empty.querySelector('button'); button.textContent = !s ? 'Importer des DICOM' : state.favoritesOnly ? 'Voir toutes les images' : 'Effacer la recherche';
    button.addEventListener('click', () => { if (!s) $('file-input').click(); else { state.search=''; $('search').value=''; setFavoritesOnly(false); } });
    $('gallery').append(empty); return;
  }
  const p = presets[state.preset];
  const fragment = document.createDocumentFragment();
  indices.forEach(index => {
    const favorite = state.favorites.has(favoriteKey(s.id,index));
    const card = document.createElement('article'); card.className = `image-card${index === state.selected ? ' selected' : ''}`; card.dataset.index = index;
    card.innerHTML = `<button class="image-button" aria-label="${sliceName(index)}, sélectionner" aria-pressed="${index === state.selected}"><img loading="lazy" decoding="async" alt="${sliceName(index)} — CT ${s.plane}"><span class="image-corner">CT</span><span class="card-check">${icon('check')}</span><span class="image-error">Image illisible</span></button><div class="card-footer"><div><strong>${sliceName(index)}</strong><small>DICOM · ${s.plane}</small></div><div class="card-actions"><button class="icon-button card-favorite${favorite ? ' favorite-on' : ''}" aria-label="${favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'} : ${sliceName(index)}" aria-pressed="${favorite}">${icon('heart')}</button><button class="icon-button card-open" aria-label="${sliceName(index)}, nouvelle fenêtre">${icon('external')}</button></div></div>`;
    const img = card.querySelector('img'); img.src = imageUrl(s.id,index,p.c,p.w); img.addEventListener('error', () => card.classList.add('failed'));
    fragment.append(card);
  }); $('gallery').append(fragment);
}
async function selectSlice(index) {
  const s = getSeries(state.active); if (!s || index < 0 || index >= s.count) return;
  state.selected = index; const p = presets[state.preset];
  $('selected-image').src = imageUrl(s.id,index,p.c,p.w); $('selected-image').alt = `${sliceName(index)} — CT ${s.plane}`;
  $('selected-title').textContent = sliceName(index); $('selected-tag').textContent = sliceName(index).toUpperCase();
  $('selected-subtitle').textContent = `${s.name} · DICOM · CT`; $('detail-window').textContent = p.name;
  const favorite = state.favorites.has(favoriteKey(s.id,index)); $('selected-favorite').classList.toggle('favorite-on',favorite);
  $('selected-favorite').setAttribute('aria-pressed',favorite); $('selected-favorite').setAttribute('aria-label',favorite ? 'Retirer des favoris' : 'Ajouter aux favoris');
  $('gallery').querySelectorAll('.image-card').forEach(el => { const selected = Number(el.dataset.index) === index; el.classList.toggle('selected', selected); el.querySelector('.image-button').setAttribute('aria-pressed',selected); });
  const token = ++selectRequest; $('detail-position').textContent = '…';
  try { const data = await request(`/api/slice?series=${s.id}&index=${index}`); if (token === selectRequest) $('detail-position').textContent = fmt(data.position); }
  catch { if (token === selectRequest) $('detail-position').textContent = 'Indisponible'; }
}
function toggleFavorite(index) {
  if (!state.active) return;
  const key = favoriteKey(state.active,index); state.favorites.has(key) ? state.favorites.delete(key) : state.favorites.add(key);
  save('lumina-favorites',[...state.favorites]); updateFavoriteCounts();
  if (state.favoritesOnly) renderGallery();
  else {
    const button = $('gallery').querySelector(`[data-index="${index}"] .card-favorite`);
    if (button) { const on=state.favorites.has(key); button.classList.toggle('favorite-on',on); button.setAttribute('aria-pressed',on); button.setAttribute('aria-label',`${on ? 'Retirer des favoris' : 'Ajouter aux favoris'} : ${sliceName(index)}`); }
  }
  if (state.selected === index) { const on=state.favorites.has(key); $('selected-favorite').classList.toggle('favorite-on',on); $('selected-favorite').setAttribute('aria-pressed',on); $('selected-favorite').setAttribute('aria-label',on ? 'Retirer des favoris' : 'Ajouter aux favoris'); }
}
function setGridZoom(value) {
  state.gridZoom = Math.min(160,Math.max(70,Number(value))); $('grid-zoom').value = state.gridZoom;
  $('zoom-value').textContent = `${state.gridZoom} %`;
  document.documentElement.style.setProperty('--tile-width',`${Math.round(180 * state.gridZoom/100)}px`);
  save('lumina-grid-zoom',state.gridZoom);
}
function detachViewer(index=state.selected, useViewer=false) {
  const p = presets[state.preset]; const v = useViewer && viewerState ? viewerState : {sid:state.active,index,c:p.c,w:p.w,invert:false};
  if (!v.sid) return;
  const url = `/?${new URLSearchParams({view:v.sid,index:v.index,center:v.c,width:v.w,invert:v.invert ? 1 : 0})}`;
  const win = window.open(url,'_blank','popup=yes,width=1180,height=880');
  if (!win) notify('Le navigateur a bloqué la fenêtre. Autorisez les fenêtres contextuelles pour ce site.',true);
  else win.opener = null;
}
function openViewer(index=state.selected) {
  if (!state.active) return;
  const p=presets[state.preset]; viewerState={sid:state.active,index,c:p.c,w:p.w,invert:false,zoom:1,panX:0,panY:0};
  $('viewer-preset').value=state.preset; $('viewer-dialog').showModal(); updateViewer();
}
function updateViewer() {
  if (!viewerState) return;
  const v=viewerState, s=getSeries(v.sid); if (!s) return;
  $('viewer-name').textContent=`${s.name} · ${sliceName(v.index)}`;
  $('viewer-description').textContent=`CT · Acquisition ${s.plane} · ${s.columns} × ${s.rows} pixels`;
  $('viewer-info').textContent=`${s.name}\n${sliceName(v.index)} / ${s.count}`;
  $('viewer-window').textContent=`C ${fmt(v.c)} / L ${fmt(v.w)} ${s.calibrated ? 'HU' : 'intensité'}\n${s.pixel_spacing.map(n=>fmt(n,3)).join(' × ')} mm/px`;
  $('viewer-image').src=imageUrl(v.sid,v.index,v.c,v.w,v.invert); $('viewer-image').alt=`${sliceName(v.index)} — CT ${s.plane}`;
  $('viewer-error').hidden=true; $('viewer-image').style.opacity='1';
  $('viewer-slice-count').textContent=`${v.index+1} / ${s.count}`; $('slice-slider').max=s.count-1; $('slice-slider').value=v.index;
  $('window-center').value=v.c; $('window-width').value=v.w; $('viewer-invert').setAttribute('aria-pressed',v.invert);
  $('previous-slice').disabled=v.index===0; $('next-slice').disabled=v.index===s.count-1;
  ['top','left','right','bottom'].forEach(side=>$(`orientation-${side}`).textContent=s.labels[side] || '');
  updateViewerZoom();
  if (detached) {
    document.title=`${sliceName(v.index)} — Lumina`;
    history.replaceState(null,'',`/?${new URLSearchParams({view:v.sid,index:v.index,center:v.c,width:v.w,invert:v.invert ? 1 : 0})}`);
  } else selectSlice(v.index);
}
function moveSlice(delta) { if (!viewerState) return; const s=getSeries(viewerState.sid); viewerState.index=Math.max(0,Math.min(s.count-1,viewerState.index+delta)); updateViewer(); }
function updateViewerZoom() {
  const v=viewerState; if (!v) return;
  $('viewer-stage').style.setProperty('--image-zoom',v.zoom); $('viewer-stage').style.setProperty('--pan-x',`${v.panX || 0}px`); $('viewer-stage').style.setProperty('--pan-y',`${v.panY || 0}px`);
  $('viewer-zoom-value').textContent=`${Math.round(v.zoom*100)} %`;
}
function viewerZoom(delta) { if (!viewerState) return; viewerState.zoom=Math.min(4,Math.max(.5,Math.round((viewerState.zoom+delta)*10)/10)); if(viewerState.zoom<=1){viewerState.panX=0;viewerState.panY=0;} updateViewerZoom(); }
function closeViewer() { if (detached) { window.close(); } else { $('viewer-dialog').close(); viewerState=null; } }
$('gallery').addEventListener('click', e => {
  const card=e.target.closest('.image-card'); if(!card) return; const index=Number(card.dataset.index);
  if(e.target.closest('.card-favorite')) toggleFavorite(index);
  else if(e.target.closest('.card-open')) {selectSlice(index);detachViewer(index);}
  else if(e.target.closest('.image-button')) selectSlice(index);
});
$('gallery').addEventListener('dblclick',e=>{const button=e.target.closest('.image-button');if(button)openViewer(Number(button.closest('.image-card').dataset.index));});
$('overview-button').addEventListener('click',()=>setMode('overview')); $('all-button').addEventListener('click',()=>setMode('all'));
$('library-nav').addEventListener('click',()=>setFavoritesOnly(false)); $('favorites-nav').addEventListener('click',()=>setFavoritesOnly(true));
$('search').addEventListener('input',e=>{state.search=e.target.value;renderGallery();});
$('preset').addEventListener('change',e=>{state.preset=e.target.value;renderGallery();selectSlice(state.selected);});
$('grid-zoom').addEventListener('input',e=>setGridZoom(e.target.value));
$('zoom-minus').addEventListener('click',()=>setGridZoom(state.gridZoom-10)); $('zoom-plus').addEventListener('click',()=>setGridZoom(state.gridZoom+10)); $('zoom-reset').addEventListener('click',()=>setGridZoom(100));
$('selected-favorite').addEventListener('click',()=>toggleFavorite(state.selected));
['preview-button','quick-preview'].forEach(id=>$(id).addEventListener('click',()=>openViewer()));
$('window-button').addEventListener('click',()=>detachViewer()); $('viewer-detach').addEventListener('click',()=>detachViewer(undefined,true));
$('viewer-close').addEventListener('click',closeViewer); $('viewer-dialog').addEventListener('cancel',()=>viewerState=null);
$('previous-slice').addEventListener('click',()=>moveSlice(-1)); $('next-slice').addEventListener('click',()=>moveSlice(1));
$('slice-slider').addEventListener('input',e=>{viewerState.index=Number(e.target.value);updateViewer();});
$('viewer-preset').addEventListener('change',e=>{const p=presets[e.target.value];if(p){viewerState.c=p.c;viewerState.w=p.w;updateViewer();}});
['window-center','window-width'].forEach(id=>$(id).addEventListener('input',()=>{clearTimeout(contrastTimer);contrastTimer=setTimeout(()=>{if(!viewerState)return;const c=Number($('window-center').value),w=Number($('window-width').value);if($('window-center').value===''||$('window-width').value===''||!Number.isFinite(c)||!Number.isFinite(w)||c< -10000||c>10000||w<1||w>20000)return;viewerState.c=c;viewerState.w=w;$('viewer-preset').value='custom';updateViewer();},160);}));
$('viewer-invert').addEventListener('click',()=>{viewerState.invert=!viewerState.invert;updateViewer();});
$('viewer-download').addEventListener('click',()=>{const v=viewerState;if(!v)return;const a=document.createElement('a');a.href=imageUrl(v.sid,v.index,v.c,v.w,v.invert)+'&download=1';a.download=`lumina-coupe-${v.index+1}.png`;a.click();});
$('viewer-zoom-minus').addEventListener('click',()=>viewerZoom(-.1)); $('viewer-zoom-plus').addEventListener('click',()=>viewerZoom(.1));
$('viewer-fit').addEventListener('click',()=>{viewerState.zoom=1;viewerState.panX=0;viewerState.panY=0;updateViewerZoom();});
$('viewer-image').addEventListener('error',()=>{if(viewerState){$('viewer-error').hidden=false;$('viewer-image').style.opacity='0';}});
let pan=null;
$('viewer-image').addEventListener('pointerdown',e=>{if(!viewerState||viewerState.zoom<=1)return;pan={x:e.clientX,y:e.clientY,oldX:viewerState.panX,oldY:viewerState.panY};e.target.setPointerCapture(e.pointerId);e.preventDefault();});
$('viewer-image').addEventListener('pointermove',e=>{if(!pan||!viewerState)return;viewerState.panX=pan.oldX+e.clientX-pan.x;viewerState.panY=pan.oldY+e.clientY-pan.y;updateViewerZoom();});
['pointerup','pointercancel'].forEach(type=>$('viewer-image').addEventListener(type,()=>pan=null));
$('help-button').addEventListener('click',()=>$('help-dialog').showModal()); $('help-close').addEventListener('click',()=>$('help-dialog').close());
document.addEventListener('keydown',e=>{
  if (e.target.closest('input,select,textarea')) return;
  if(viewerState) {
    if(e.key==='ArrowLeft'){e.preventDefault();moveSlice(-1);} else if(e.key==='ArrowRight'){e.preventDefault();moveSlice(1);}
    else if(e.key==='+'||e.key==='='){e.preventDefault();viewerZoom(.1);} else if(e.key==='-'){e.preventDefault();viewerZoom(-.1);}
    else if(e.key==='Escape'&&detached)closeViewer();
  } else if(e.code==='Space'&&!$('help-dialog').open&&(e.target===document.body||e.target.closest('.image-button'))) {e.preventDefault();openViewer();}
});
async function importFiles(files) {
  if(!files.length)return; if(files.reduce((n,f)=>n+f.size,0)>250*1024*1024){notify('Sélection trop volumineuse. Importez jusqu’à 250 Mo de fichiers par lot.',true);return;}
  if(files.length>2000){notify('Import limité à 2 000 fichiers par lot.',true);return;}
  const buttons=[...document.querySelectorAll('[data-import]')]; buttons.forEach(b=>b.disabled=true);
  notify(`Import de ${files.length} fichier${files.length>1?'s':''}…`,false,true);
  try {
    const form=new FormData(); files.forEach(f=>form.append('files',f));
    const result=await request('/api/import',{method:'POST',body:form}); state.series=await request('/api/series');
    setFavoritesOnly(false); activateSeries(result.ids[0]);
    notify(`${result.ids.length} série(s) importée(s)${result.rejected?` · ${result.rejected} fichier(s) incompatible(s) écarté(s)`:''}.`);
  } catch(error){notify(error.message,true);} finally{buttons.forEach(b=>b.disabled=false);$('file-input').value='';}
}
document.querySelectorAll('[data-import]').forEach(button=>button.addEventListener('click',()=>$('file-input').click()));
$('file-input').addEventListener('change',e=>importFiles([...e.target.files]));
document.addEventListener('dragenter',e=>{if(detached||!e.dataTransfer.types.includes('Files'))return;e.preventDefault();dragDepth++;document.body.classList.add('dragover');});
document.addEventListener('dragover',e=>{if(!detached&&e.dataTransfer.types.includes('Files'))e.preventDefault();});
document.addEventListener('dragleave',e=>{if(detached)return;if(--dragDepth<=0){dragDepth=0;document.body.classList.remove('dragover');}});
document.addEventListener('drop',e=>{if(detached)return;e.preventDefault();dragDepth=0;document.body.classList.remove('dragover');importFiles([...e.dataTransfer.files]);});
async function initialize() {
  setGridZoom(state.gridZoom);
  document.querySelectorAll('.inspector button').forEach(el=>el.disabled=true);
  try {
    state.series=await request('/api/series');
    if(detached){
      const s=getSeries(query.get('view')); if(!s)throw new Error('Cette série est introuvable. Revenez à la bibliothèque.');
      const number=(key,fallback)=>{const n=Number(query.get(key));return query.has(key)&&Number.isFinite(n)?n:fallback;};
      const c=Math.max(-10000,Math.min(10000,number('center',-600))),w=Math.max(1,Math.min(20000,number('width',1500)));
      viewerState={sid:s.id,index:Math.max(0,Math.min(s.count-1,Math.trunc(number('index',0)))),c,w,invert:query.get('invert')==='1',zoom:1,panX:0,panY:0};
      const matched=Object.entries(presets).find(([,p])=>p.c===c&&p.w===w);$('viewer-preset').value=matched?matched[0]:'custom';
      document.body.classList.add('windowed'); document.body.prepend($('viewer')); $('library').remove(); $('viewer-dialog').remove();
      $('viewer-detach').hidden=true; $('viewer-close').setAttribute('aria-label','Fermer la fenêtre');updateViewer();
    } else if(state.series.length){activateSeries(state.series[0].id);} else {
      $('series-title').textContent='Aucune série importée';$('series-source').textContent='Ajoutez vos fichiers DICOM pour commencer';$('series-list').replaceChildren();renderSeriesList();renderGallery();
    }
  }catch(error){
    notify(error.message,true,true);
    if(detached){document.body.classList.add('windowed');const box=document.createElement('div');box.className='empty-state';const title=document.createElement('h3');title.textContent=error.message;const link=document.createElement('a');link.href='/';link.textContent='Ouvrir la bibliothèque';box.append(title,link);$('library').remove();document.body.prepend(box);}
    else{$('series-title').textContent='Chargement indisponible';$('series-source').textContent='Vérifiez que le serveur local est démarré';$('series-list').replaceChildren();renderGallery();}
  }
}
initialize();
