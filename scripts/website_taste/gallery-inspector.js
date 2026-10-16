/* Exact per-result inputs and a transparent view of the invalidated classifier. */
const originalRender = render;
const originalCard = card;
const originalSetView = setView;
let initialBrief = false;
let initialView = false;
let investigation = null;
let inspected = null;
let inspectorTab = 'skill';

const fixed = document.createElement('div');
fixed.className = 'fixed-brief';
fixed.id = 'fixedBrief';
document.querySelector('.overview').before(fixed);
const notice = document.createElement('div');
notice.className = 'run-notice';
notice.id = 'runNotice';
document.querySelector('.overview').before(notice);
const judgeTab = document.createElement('button');
judgeTab.id = 'judgeTab';
judgeTab.className = 'tab';
judgeTab.setAttribute('role', 'tab');
judgeTab.setAttribute('aria-selected', 'false');
judgeTab.textContent = 'The judge';
document.querySelector('.tabs').append(judgeTab);
const judgeView = document.createElement('section');
judgeView.id = 'judgeView';
judgeView.className = 'judge-view';
document.querySelector('main').append(judgeView);
const modalBody = document.createElement('div');
modalBody.className = 'modal-body';
const preview = document.querySelector('.modal-img');
preview.before(modalBody);
modalBody.append(preview);
const panel = document.createElement('aside');
panel.className = 'skill-panel';
panel.innerHTML = '<div class="skill-panel-header"><strong id="skillHeading">Exact skill used</strong><button class="skill-copy" id="copySkill">Copy skill</button></div><div class="skill-tabs"><button data-skill-tab="skill" class="active">Full skill</button><button data-skill-tab="changes">Changes</button><button data-skill-tab="input">Input</button><button data-skill-tab="judge">Trace + judge</button></div><pre class="skill-source" id="skillSource">Loading exact instructions…</pre>';
modalBody.append(panel);

card = function(row, comparing = false) {
  const rendered = originalCard(row, comparing);
  return rendered.replace('</article>', `<button class="skill-button" data-skill="${row.id}">View skill used ↗</button>${row.humanLabel === 'disliked' ? '<span class="human-rejected"> · Rejected by you</span>' : ''}</article>`);
};

function fixedPrompt() {
  const task = $('taskFilter').value;
  const row = data.trials.find(r => r.task === task);
  $('fixedBrief').innerHTML = task === 'all'
    ? '<strong>Mixed briefs</strong><p>Choose one brief to compare the same website prompt across skill revisions.</p>'
    : `<strong>Fixed website prompt</strong><p>${esc(row?.brief || '')}<small>Same brief · ${esc(data.model)} · seed ${row?.seed ?? '—'}. The skill used for each result is saved separately.</small></p>`;
  const shown = filtered();
  renderCompare();
  $('count').textContent = shown.filter(r => r.image).length;
  $('total').textContent = shown.length;
  const scores = shown.filter(r => r.score != null);
  $('best').innerHTML = scores.length ? (100 * Math.max(...scores.map(r => r.score))).toFixed(1) + '<span> / 100</span>' : '—';
}

render = function() {
  originalRender();
  if (!initialBrief) {
    const preferred = new URLSearchParams(location.search).get('brief') || data.defaultTask;
    if (preferred && [...$('taskFilter').options].some(o => o.value === preferred)) $('taskFilter').value = preferred;
    initialBrief = true;
    renderCards();
    renderChart();
  }
  document.querySelector('h1').textContent = 'One brief. Every skill revision.';
  document.querySelector('.sub').textContent = 'Compare the same website prompt across attempts. Open any result to see the exact skill it used and what GEPA changed.';
  $('runNotice').hidden = !data.invalidated;
  $('runNotice').innerHTML = 'Run stopped: you rejected a design scored 92.5 by this judge. Its old scores are preserved for inspection. <a href="?view=judge" id="inspectJudge">Inspect the judge →</a>';
  if (data.invalidated) {
    $('statusText').textContent = 'Stopped · judge invalidated';
    $('status').className = 'status stopped';
    document.querySelector('.chart-title').innerHTML = 'Old judge scores <span>invalidated model</span>';
    document.querySelectorAll('.stat-label')[1].textContent = 'Highest old judge score';
  }
  $('stages').className = 'parallel-stage';
  $('stages').innerHTML = '<div class="shared-start"><b>Shared starting point</b><br>Trace data · judge · baseline skill</div><div class="branches">' + data.branches.map(b => `<div class="branch"><strong>${esc(b.label)}</strong><span>${b.done ? 'Complete' : data.invalidated ? 'Stopped' : 'Independent experiment'}</span><p><i>Changes:</i> ${esc(b.changes)}<br>Fixed: ${esc(b.fixed)}</p></div>`).join('') + '</div>';
  fixedPrompt();
  updateContext();
  if (view === 'judge') loadJudge();
  $('judgeView').classList.toggle('visible', view === 'judge');
  document.querySelector('.bottom details p').textContent = 'Your past feedback supplies shared preference evidence. GEPA changes the skill while keeping Qwen weights fixed. Weight refinement changes Qwen weights using the original skill. These are independent experiments; neither consumes the other’s result.';
  if (!initialView && new URLSearchParams(location.search).get('view') === 'judge') setView('judge');
  initialView = true;
};

setView = function(next) {
  originalSetView(next);
  $('judgeView').classList.toggle('visible', next === 'judge');
  $('judgeTab').classList.toggle('active', next === 'judge');
  $('judgeTab').setAttribute('aria-selected', String(next === 'judge'));
  updateContext();
  if (next === 'judge') loadJudge();
};

function updateContext() {
  const judging = view === 'judge';
  document.querySelector('h1').textContent = judging ? 'Inside the taste judge.' : 'One brief. Every skill revision.';
  document.querySelector('.sub').textContent = judging ? 'What the judge saw, what it checked, and the evidence behind its verdict. Original classifier results are kept below for diagnosis.' : 'Compare the same website prompt across attempts. Open any result to see the exact skill it used and what GEPA changed.';
  for (const element of [document.querySelector('.overview'), $('fixedBrief'), $('stages')]) element.style.display = judging ? 'none' : '';
  if (data.invalidated) $('learned').textContent = `Historical model fitted on ${data.labelCount} automatic labels. Invalidated; no validated personal-taste model yet.`;
}

async function loadJudge() {
  try {
    const r = await fetch('/api/judge', {cache:'no-store'});
    if (!r.ok) throw Error('Judge report unavailable');
    const judge = await r.json();
    const generic = judge.drivers.find(d => d.kind === 'verdict');
    const cases = judge.examples.map(e => `<div class="judge-case"><div><img src="${e.image}" alt="Website you rejected despite a high judge score"></div><div><h3>A confirmed false positive</h3><p class="judge-description">Old judge score: <b>${(100*e.score).toFixed(1)} / 100</b> · Your label: <b>${esc(e.humanLabel)}</b></p><blockquote>${esc(e.feedback)}</blockquote><table class="judge-table"><thead><tr><th>Feature on this design</th><th>Answer</th></tr></thead><tbody>${Object.entries(e.rubric).map(([key, probabilities]) => `<tr><td>${esc(key.replaceAll('_',' '))}</td><td>${Object.entries(probabilities).map(([name,p]) => `${esc(name)} ${(100*p).toFixed(0)}%`).join('<br>')}</td></tr>`).join('')}</tbody></table></div></div>`).join('');
    const investigations = (judge.agentReports || []).map(report => `<div class="judge-box"><h2>${esc(title(report.task))} · ${esc(report.verdict?.label || 'abstained')}</h2><p>${esc(report.verdict?.summary || 'The inspection did not finish.')}</p><p>${esc(report.model)} · Full recorded trace + HTML source + actual screenshot. Exploratory verdict; no calibrated probability.</p><button class="skill-button" data-investigation="${report.id}">Inspect inputs and evidence →</button></div>`).join('');
    $('judgeView').innerHTML = `<h2 class="judge-heading">Agent judge · trace and finished website</h2><p class="judge-description">The new prototype reads the recorded messages and generated source, then directly inspects the rendered screenshot. It compares those observations with training-only preference quotes. Existing Qwen runs have one generation response; they do not contain a multi-step coding trace. No hidden reasoning is included.</p><div class="judge-intro">${investigations || '<p>No agent investigations recorded yet.</p>'}</div><p class="judge-description">This is an unvalidated evaluator prototype. It has not replaced the reward for GEPA or weight refinement. The historical classifier below remains invalidated.</p><h2 class="judge-heading">What the classifier actually evaluated</h2><div class="judge-intro"><div class="judge-box"><h2>Current version · ${judge.invalidated?'invalidated':'prototype'}</h2><p class="judge-target">${esc(judge.target)}</p><p>${esc(judge.traceRole)}</p><div class="judge-flow">${judge.inputPipeline.map(esc).join(' → ')}</div><p><b>New inspection prototype:</b> full recorded agent trace + rendered website, shown above. It has not been independently validated or enabled as an optimization reward.</p></div><div class="judge-box"><h2>Why this version was stopped</h2><div class="judge-branch"><b>${generic?(100*generic.share).toFixed(1)+'%':'—'}</b><span>of reported feature influence came from the generic verdict; the taste criteria barely affected the result.</span></div><div class="judge-branch"><b>${judge.development.n?Math.round(judge.development.accuracy*judge.development.n)+' / '+judge.development.n:'—'}</b><span>development labels matched. This weak result should have blocked the pilot.</span></div><div class="judge-branch"><b>${judge.automaticTest.n?Math.round(judge.automaticTest.accuracy*judge.automaticTest.n)+' / '+judge.automaticTest.n:'—'}</b><span>held-out automatic labels matched. This was not human validation.</span></div></div></div>${cases}<h4>Criteria and reported influence</h4><table class="judge-table"><thead><tr><th>Question</th><th>Influence</th></tr></thead><tbody>${judge.drivers.map(d=>`<tr><td>${esc(d.prompt)}<small>${esc(d.kind)}</small></td><td>${(100*d.share).toFixed(2)}%</td></tr>`).join('')}</tbody></table>`;
  } catch (error) {
    $('judgeView').textContent = 'The judge report could not be loaded. Try refreshing.';
  }
}

function renderSkill() {
  if (!inspected) return;
  for (const button of panel.querySelectorAll('[data-skill-tab]')) button.classList.toggle('active', button.dataset.skillTab === inspectorTab);
  if (inspectorTab === 'judge') {
    if (!investigation) { $('skillSource').textContent = 'No investigation has been recorded for this attempt. The old classifier only graded a screenshot description.'; return; }
    const v = investigation.verdict;
    $('skillSource').textContent = [
      'AGENT JUDGE · EXPLORATORY, UNCALIBRATED',
      investigation.note,
      v ? `VERDICT: ${v.label}\n${v.summary}\n\nTask fulfillment: ${v.task_fulfillment}\nCorrections: ${v.correction_handling}` : 'No completed verdict.',
      ...(v?.findings || []).map(f => `FINDING: ${f.observation}\nEvidence: ${f.evidence}\nTrace: ${f.trace_step_ids.join(', ')}\nPreference references: ${f.preference_ids.join(', ')}`),
      'LIMITATIONS\n' + (v?.limitations || []).join('\n'),
      'ACTUAL INPUTS\n' + investigation.inputs.trace_kind + '\n' + investigation.inputs.artifact_provenance,
      ...investigation.inputs.trace.map(step => `${step.id} · ${step.role}\n${step.content}`),
      'TRAINING-ONLY PREFERENCE EVIDENCE\n' + JSON.stringify(investigation.inputs.evidence, null, 2),
      'INSPECTION RECEIPT\n' + JSON.stringify(investigation.inspection.map(item => ({tool:item.tool, input:item.input, result:item.tool === 'inspect_render' ? item.result : item.tool === 'finish' ? {accepted:true} : {offset:item.result.offset, next_offset:item.result.next_offset, total_chars:item.result.total_chars}})), null, 2)
    ].join('\n\n');
  } else if (inspectorTab === 'changes') {
    $('skillSource').innerHTML = inspected.changes ? inspected.changes.split('\n').map(line => `<span class="${line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@') ? 'diff-meta' : line.startsWith('+') ? 'diff-add' : line.startsWith('-') ? 'diff-remove' : ''}">${esc(line) || ' '}</span>`).join('') : 'This result used the starting skill unchanged.';
  } else {
    $('skillSource').textContent = inspectorTab === 'input' ? `WEBSITE PROMPT\n${inspected.brief}\n\nMODEL\n${inspected.model?.id || 'Qwen'}\nSeed: ${inspected.seed}\n\nFIXED SYSTEM INSTRUCTIONS\n${inspected.system}` : inspected.skill || 'No additional skill was used.';
  }
}

async function loadSkill(id) {
  inspected = null;
  investigation = null;
  const judgeRequest = fetch(`/api/design/${id}/judge`, {cache:'no-store'}).then(r => r.ok ? r.json() : null).catch(() => null);
  $('skillSource').textContent = 'Loading the exact instructions for this result…';
  try {
    const response = await fetch(`/api/design/${id}/instructions`, {cache:'no-store'});
    if (!response.ok) throw Error('Unavailable');
    const result = await response.json();
    if (modalId !== id) return;
    const report = await judgeRequest;
    if (modalId !== id) return;
    investigation = report;
    inspected = result;
    $('skillHeading').textContent = result.isBaseline ? 'Starting skill · unchanged' : 'Exact skill used';
    renderSkill();
  } catch (error) {
    if (modalId === id) $('skillSource').textContent = 'The recorded skill could not be loaded.';
  }
}

const oldUpdateModal = updateModal;
updateModal = function() {
  const previous = modalId;
  const row = data.trials.find(r => r.id === modalId);
  if (!row) return;
  if (row.image) {
    $('modalImage').hidden = false;
    document.querySelector('.missing-design')?.remove();
    oldUpdateModal();
  } else {
    $('modalImage').hidden = true;
    $('modalHeading').innerHTML = `<h2>${esc(title(row.task))} #${row.number}</h2>${methodTag(row)}`;
    $('modalBrief').textContent = row.brief;
    $('modalScore').textContent = row.status === 'invalid' ? 'Incomplete HTML · not an aesthetic judgment' : 'No finished output';
    if (!document.querySelector('.missing-design')) preview.insertAdjacentHTML('beforeend','<div class="missing-design">This attempt did not produce a complete rendered website.<br>You can still inspect the exact skill that was used.</div>');
  }
  const rows = filtered(), index = rows.findIndex(r => r.id === modalId);
  $('previous').disabled = index <= 0;
  $('next').disabled = index < 0 || index === rows.length - 1;
  if (data.invalidated && row.score != null) $('modalScore').textContent = score(row) + ' / 100 · historical score · invalidated';
  if (inspected?.id !== previous) loadSkill(previous);
};

openModal = function(id) {
  if (!data.trials.some(r => r.id === id)) return;
  focusBefore = document.activeElement;
  modalId = id;
  inspectorTab = 'skill';
  updateModal();
  $('modal').classList.add('visible');
  document.body.classList.add('modal-open');
  $('close').focus();
};

$('judgeTab').onclick = () => setView('judge');
$('taskFilter').onchange = () => {renderCards();renderChart();fixedPrompt();};
document.addEventListener('click', event => {
  const report = event.target.closest('[data-investigation]');
  if (report) {openModal(report.dataset.investigation); inspectorTab='judge'; if (inspected) renderSkill();}
  const skill = event.target.closest('[data-skill]');
  if (skill) openModal(skill.dataset.skill);
  const tab = event.target.closest('[data-skill-tab]');
  if (tab) {inspectorTab=tab.dataset.skillTab;renderSkill();}
  if (event.target.closest('#inspectJudge')) {event.preventDefault();setView('judge');}
});
$('copySkill').onclick = async () => {
  if (!inspected) return;
  try {await navigator.clipboard.writeText(inspected.skill);$('copySkill').textContent='Copied';setTimeout(()=>{$('copySkill').textContent='Copy skill';},1500);} catch(error) {$('copySkill').textContent='Select text to copy';}
};

// Compare only attempts for the selected brief. Include incomplete attempts so
// an unsuccessful GEPA revision cannot quietly disappear from the comparison.
renderCompare = function() {
  const brief = $('taskFilter').value;
  const rows = data.trials.filter(r => brief === 'all' || r.task === brief);
  if (rows.length < 2) {
    $('comparison').innerHTML = '<div class="empty"><strong>One attempt for this brief so far.</strong>The next revision will appear beside it when it is available.</div>';
    $('compareNote').textContent = ''; $('compareLeft').innerHTML=''; $('compareRight').innerHTML=''; return;
  }
  const old = [$('compareLeft').value, $('compareRight').value];
  if (selected.length === 2) {old[0]=selected[0];old[1]=selected[1];}
  if (!rows.some(r=>r.id===old[0])) old[0]=rows[0].id;
  if (!rows.some(r=>r.id===old[1]) || old[0]===old[1]) old[1]=rows.find(r=>r.id!==old[0]).id;
  for (const [i,id] of ['compareLeft','compareRight'].entries()) {
    $(id).innerHTML=rows.map(r=>`<option value="${r.id}">${esc(label(r))}</option>`).join('');$(id).value=old[i];
  }
  const a=rows.find(r=>r.id===old[0]), b=rows.find(r=>r.id===old[1]);
  $('comparison').innerHTML=[a,b].map(r=>card(r,true)).join('');
  $('compareNote').textContent=a.task===b.task?'Same brief · '+a.brief:'Mixed briefs. Select a single brief in Timeline to compare identical prompts.';
};

moveModal = function(step) {
  const rows=filtered(), i=rows.findIndex(r=>r.id===modalId);
  if (i>=0 && rows[i+step]) {modalId=rows[i+step].id;updateModal();preview.scrollTop=0;}
};
