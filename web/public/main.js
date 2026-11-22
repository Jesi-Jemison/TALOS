const $ = id => document.getElementById(id);
const ui = {csv_base64: null, filename: null, history: [], pending: null, snapshot: null};
const MAX_CSV_BYTES = 2_000_000;

function notice(message, error = false) {
  const box = $('notice');
  box.textContent = message;
  box.classList.toggle('error', error);
  box.hidden = !message;
}

function busy(value) {
  document.querySelectorAll('button').forEach(button => button.disabled = value);
}

function stateBody(extra = {}) {
  return {csv_base64: ui.csv_base64, filename: ui.filename, history: ui.history, ...extra};
}

async function api(path, extra = {}) {
  busy(true);
  notice('TALOS is checking the working copy…');
  try {
    const response = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(stateBody(extra)),
    });
    const type = response.headers.get('content-type') || '';
    if (!response.ok) {
      const body = type.includes('json') ? await response.json() : {};
      throw new Error(body.error || `The request failed (${response.status}).`);
    }
    notice('');
    return response;
  } catch (error) {
    notice(error.message || 'TALOS could not complete that request.', true);
    throw error;
  } finally {
    busy(false);
  }
}

function base64(bytes) {
  const parts = [];
  // A multiple of three keeps every chunk independently valid in base64.
  for (let start = 0; start < bytes.length; start += 48_000) {
    parts.push(btoa(String.fromCharCode(...bytes.slice(start, start + 48_000))));
  }
  return parts.join('');
}

async function loadFile(bytes, name) {
  if (!bytes.length) return notice('The CSV is empty.', true);
  if (bytes.length > MAX_CSV_BYTES) return notice('This Vercel version accepts CSV files up to 2 MB. Use the Streamlit app for larger files.', true);
  ui.csv_base64 = base64(bytes);
  ui.filename = name;
  ui.history = [];
  ui.pending = null;
  try {
    ui.snapshot = await (await api('/api/inspect')).json();
    render();
    $('workspace').scrollIntoView({behavior:'smooth'});
  } catch (_) {
    ui.csv_base64 = null;
  }
}

function metric(value, label) {
  const item = document.createElement('div');
  item.className = 'metric';
  const strong = document.createElement('strong');
  strong.textContent = value == null ? '-' : String(value);
  const span = document.createElement('span');
  span.textContent = label;
  item.append(strong, span);
  return item;
}

function renderTable(target, rows) {
  target.replaceChildren();
  if (!rows?.length) { target.textContent = 'No rows to show.'; return; }
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const table = target.tagName === 'TABLE' ? target : document.createElement('table');
  const head = document.createElement('thead');
  const hr = document.createElement('tr');
  columns.forEach(column => {const th=document.createElement('th');th.textContent=column;hr.append(th);});
  head.append(hr);
  const body = document.createElement('tbody');
  rows.forEach(row => {const tr=document.createElement('tr');columns.forEach(column => {const td=document.createElement('td');const value=row[column];td.textContent=value == null ? '-' : typeof value === 'object' ? JSON.stringify(value) : String(value);tr.append(td);});body.append(tr);});
  table.append(head, body);
  if (target !== table) target.append(table);
}

function signalGroup(title, lines) {
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = `${title} · ${lines.length}`;
  details.append(summary);
  const body = document.createElement('div');
  if (!lines.length) body.textContent = 'No signals in this group.';
  else {
    const list = document.createElement('ul');
    lines.slice(0, 35).forEach(line => {const li=document.createElement('li');li.textContent=line;list.append(li);});
    body.append(list);
  }
  details.append(body);
  return details;
}

function renderSignals(snapshot) {
  const signals = snapshot.signals;
  const container = $('signals');
  container.replaceChildren();
  container.append(
    signalGroup('Missing values', signals.missing.filter(item => item.missing_count).map(item => `${item.column}: ${item.missing_count} missing (${Number(item.missing_percentage).toFixed(1)}%)`)),
    signalGroup('Category variants', signals.category_variants.map(item => `${item.column}: ${(item.variants || []).map(v => v.value).join(' · ')}`)),
    signalGroup('Numeric outliers', signals.outliers.filter(item => item.outlier_count).map(item => `${item.column}: ${item.outlier_count} flagged by the IQR rule`)),
    signalGroup('Structure', [
      ...(signals.structure.empty_columns || []).map(name => `${name}: empty column`),
      ...(signals.structure.constant_columns || []).map(item => `${item.column}: one observed value`),
      ...(signals.structure.identifier_columns || []).map(item => `${item.column}: possible identifier; ${item.duplicate_value_count} repeated values`),
    ]),
  );
}

function renderSuggestions(snapshot) {
  const container = $('suggestions');
  container.replaceChildren();
  if (!snapshot.suggestions.length) {
    const p=document.createElement('p');p.className='muted';p.textContent='No conservative repairs suggested. You can still choose an action below.';container.append(p);return;
  }
  snapshot.suggestions.forEach(item => {
    const button=document.createElement('button');
    button.className='suggestion';
    const title=document.createElement('strong');title.textContent=item.title;
    const description=document.createElement('small');description.textContent=item.description;
    button.append(title,description);
    button.onclick=()=>showPreview({kind:'actions',actions:[item.action]});
    container.append(button);
  });
}

function render() {
  const snapshot = ui.snapshot;
  for (const id of ['workspace','forge','evidence']) $(id).hidden = false;
  $('fileMeta').textContent = `${ui.filename} · ${snapshot.summary.row_count.toLocaleString()} rows · ${snapshot.summary.column_count} columns`;
  $('score').textContent = snapshot.summary.score ?? '-';
  const metrics = $('metrics');metrics.replaceChildren();
  [
    [snapshot.summary.missing_cells,'Missing cells'],
    [snapshot.summary.duplicate_rows,'Exact duplicate rows'],
    [snapshot.summary.category_variant_groups,'Category variant groups'],
    [snapshot.summary.outlier_values,'IQR outlier values'],
    [snapshot.summary.structural_signals,'Structure signals'],
    [snapshot.source_summary.score,'Original score'],
  ].forEach(([value,label])=>metrics.append(metric(value,label)));
  renderTable($('sampleTable'),snapshot.sample);
  renderSignals(snapshot);
  renderSuggestions(snapshot);
  $('changeCount').textContent = `${ui.history.length} approved change${ui.history.length===1?'':'s'}`;
  const ledger=$('ledger');ledger.replaceChildren();
  snapshot.ledger.forEach(item=>{const li=document.createElement('li');li.textContent=`${item.transformation_type || item.description || 'Approved repair'} · ${item.affected_rows ?? 0} rows affected`;ledger.append(li);});
  if (!snapshot.ledger.length) {const li=document.createElement('li');li.textContent='No repairs approved yet.';ledger.append(li);}
  const select=$('columnSelect');select.replaceChildren();
  snapshot.columns.forEach(column=>{const option=document.createElement('option');option.value=column;option.textContent=column;select.append(option);});
  $('preview').hidden=true;
  updateManualControls();
}

function updateManualControls() {
  const type=$('actionType').value;
  $('columnWrap').hidden=type==='remove_exact_duplicates';
  $('methodWrap').hidden=!['fill_numeric_missing','fill_text_missing','outlier'].includes(type);
  $('textRuleWrap').hidden=type!=='text';
  $('trimWrap').hidden=type!=='text';
  const methods=$('methodSelect');methods.replaceChildren();
  const options=type==='fill_numeric_missing' ? [['median','Median'],['mean','Mean'],['custom','Custom number']]
    :type==='fill_text_missing' ? [['mode','Most common value'],['custom','Custom text']]
    :type==='outlier' ? [['blank','Blank flagged values'],['mean','Non-outlier mean'],['median','Non-outlier median'],['custom','Custom number'],['cap','Cap at IQR boundary'],['remove_rows','Remove affected rows'],['remove_negative_integers','Remove negative whole-number rows'],['remove_negative_integer_outliers','Remove negative whole-number outlier rows']]
    :[];
  options.forEach(([value,label])=>{const option=document.createElement('option');option.value=value;option.textContent=label;methods.append(option);});
  updateCustomValue();
}

function updateCustomValue(){ $('valueWrap').hidden=$('methodSelect').value!=='custom'; }

function manualAction() {
  const type=$('actionType').value,column=$('columnSelect').value,method=$('methodSelect').value,value=$('customValue').value;
  if (type==='text') return {kind:'text',columns:[column],rule:$('textRule').value,trim_whitespace:$('trimText').checked,collapse_spaces:$('trimText').checked};
  if (type==='outlier') return {kind:'outlier',column,strategy:method,value};
  let action={type};
  if (type!=='remove_exact_duplicates') action.column=column;
  if (type==='remove_columns') {delete action.column;action.columns=[column];}
  if (type==='fill_numeric_missing'||type==='fill_text_missing') {action.method=method;if(method==='custom')action.value=value;}
  return {kind:'actions',actions:[action]};
}

async function showPreview(action) {
  if (!ui.csv_base64) return;
  try {
    const result=await (await api('/api/preview',{next:action})).json();
    ui.pending=action;
    $('previewTitle').textContent=`${result.operation.replaceAll('_',' ')} · ${result.targets.join(', ') || 'all columns'}`;
    const stats=$('previewStats');stats.replaceChildren();
    [[result.affected_rows,'Rows affected'],[result.affected_values,'Values affected'],[result.rows_removed,'Rows removed'],[result.columns_removed,'Columns removed']].forEach(([v,l])=>stats.append(metric(v,l)));
    const warnings=$('previewWarnings');warnings.replaceChildren();
    result.warnings.forEach(w=>{const li=document.createElement('li');li.textContent=w;warnings.append(li);});
    const examples=$('previewExamples');renderTable(examples,result.examples);
    $('preview').hidden=false;
    $('preview').scrollIntoView({behavior:'smooth',block:'center'});
  } catch (_) {}
}

$('fileInput').addEventListener('change',async event=>{const file=event.target.files?.[0];if(file)await loadFile(new Uint8Array(await file.arrayBuffer()),file.name);});
$('demoButton').onclick=async()=>{try{const response=await fetch('/talos_demo.csv');if(!response.ok)throw new Error('The demo file could not be loaded.');await loadFile(new Uint8Array(await response.arrayBuffer()),'talos_demo.csv');}catch(error){notice(error.message,true);}};
$('resetButton').onclick=()=>{ui.csv_base64=null;ui.filename=null;ui.history=[];ui.pending=null;ui.snapshot=null;$('fileInput').value='';for(const id of ['workspace','forge','evidence'])$(id).hidden=true;notice('This dataset has been cleared from the tab.');window.scrollTo({top:0,behavior:'smooth'});};
$('actionType').onchange=updateManualControls;
$('methodSelect').onchange=updateCustomValue;
$('manualPreview').onclick=()=>showPreview(manualAction());
$('cancelPreview').onclick=()=>{ui.pending=null;$('preview').hidden=true;};
$('applyButton').onclick=async()=>{if(!ui.pending)return;try{const snapshot=await(await api('/api/apply',{next:ui.pending})).json();ui.history.push(ui.pending);ui.pending=null;ui.snapshot=snapshot;render();notice('Repair approved and applied to the working copy. The original is intact.');$('workspace').scrollIntoView({behavior:'smooth'});}catch(_){}};
document.querySelectorAll('[data-export]').forEach(button=>button.onclick=async()=>{try{const response=await api(`/api/export/${button.dataset.export}`);const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=({csv:'talos_cleaned.csv',log:'talos_transformation_log.csv',html:'talos_report.html',pdf:'talos_report.pdf',evidence:'talos_evidence.zip'})[button.dataset.export];link.click();setTimeout(()=>URL.revokeObjectURL(url),60_000);}catch(_){}});
