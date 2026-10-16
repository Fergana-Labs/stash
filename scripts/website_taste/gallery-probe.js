/* The probe owns the score. Investigator outputs remain separate audit evidence. */
const probeTab = document.createElement('button');
probeTab.id='probeTab'; probeTab.className='tab'; probeTab.setAttribute('role','tab'); probeTab.setAttribute('aria-selected','false'); probeTab.textContent='Grader';
document.querySelector('.tabs').insertBefore(probeTab, $('judgeTab'));
const probeView = document.createElement('section');
probeView.id='probeView'; probeView.className='probe-view'; document.querySelector('main').append(probeView);
$('judgeTab').textContent='Investigator';
const probeSkillTab=document.createElement('button');
probeSkillTab.dataset.skillTab='probe';probeSkillTab.textContent='Grader';document.querySelector('.skill-tabs').append(probeSkillTab);
let probeData=null, probeLoading=false, probeInitial=false;
const probeInspections=new Map();

const preProbeContext=updateContext;
updateContext=function(){
  preProbeContext();
  $('model').textContent=view==='probe'?'Qwen2.5-VL-3B':data.model.replace('Qwen/','');
  if(view==='probe'){
    document.querySelector('h1').textContent='Your learned taste grader.';
    document.querySelector('.sub').textContent='A frozen vision-language model reads the evidence. A personal linear probe assigns the score. The agent helps curate and audit.';
    for(const element of [document.querySelector('.overview'),$('fixedBrief'),$('stages')]) element.style.display='none';
    $('runNotice').hidden=true;
    $('statusText').textContent=probeData?.audit?.human_failures?.length?'Probe failed audit · optimization blocked':probeData?.status==='fitted'?'Probe fitted · validation pending':'Preparing activation probe';
  }
};
const preProbeView=setView;
setView=function(next){preProbeView(next);probeView.classList.toggle('visible',next==='probe');probeTab.classList.toggle('active',next==='probe');probeTab.setAttribute('aria-selected',String(next==='probe'));if(next==='probe')loadProbe();};
const preProbeRender=render;
render=function(){preProbeRender();if(!probeInitial&&new URLSearchParams(location.search).get('view')==='probe')setView('probe');probeInitial=true;};
probeTab.onclick=()=>setView('probe');

function probeMetric(metric){return metric?.n?`${Math.round(metric.accuracy*metric.n)} / ${metric.n}`:'—';}
function probeScoreCard(row){
  const p=row.prediction, a=row.audit;
  const disagreements=[a.human_label&&a.human_label!==p.label?'Disagrees with your recorded rating':null,a.agent_label&&a.agent_label!==p.label?'Disagrees with investigator audit':null].filter(Boolean);
  return `<article class="probe-score"><img src="/images/${row.trial_id}.png" alt="${esc(title(row.task))} website scored by the activation probe" loading="lazy"><div class="probe-score-body"><div class="probe-score-title"><span>${esc(title(row.task))} · ${esc(p.label)}</span><span class="probe-number">${p.score.toFixed(3)}</span></div><p>Uncalibrated readout · logit ${p.raw_logit.toFixed(3)} · no generated critique</p><p>${a.human_label?'Your rating: '+esc(a.human_label)+' · ':''}${a.agent_label?'Investigator audit: '+esc(a.agent_label):'No investigator audit recorded'}</p>${disagreements.length?`<p class="disagreement">${disagreements.map(esc).join(' · ')}</p>`:''}<button class="skill-button" data-probe-open="${row.trial_id}">Inspect grader input →</button></div></article>`;
}

async function loadProbe(){
  if(probeLoading)return;probeLoading=true;
  try{
    const response=await fetch('/api/probe',{cache:'no-store'});if(!response.ok)throw Error('Unavailable');
    probeData=await response.json();
    if(!['prepared','fitted'].includes(probeData.status)){probeView.innerHTML='<div class="empty"><strong>No activation probe connected.</strong>The original classifier and investigator are available in the other tabs.</div>';return;}
    const d=probeData, fitted=d.status==='fitted', gate=d.release_gate;
    const failedAudit=Boolean(d.audit?.human_failures?.length);
    const examples=(d.examples||[]).map(e=>`<article class="probe-example"><img src="${e.image}" alt="${esc(e.label)} preference evidence" loading="lazy"><div><b>${esc(e.label)} · ${esc(e.partition)}</b>${e.reference?' · reference image':''}<blockquote>${esc(e.quote||'Teacher-inferred label; no explicit human approval')}</blockquote><small>${esc(e.label_source)} · ${e.trace_steps} recorded trace steps<br>${e.human_reviewed?'Human reviewed':'Interpretation awaiting human review'}</small></div></article>`).join('');
    probeView.innerHTML=`<p class="probe-intro">The grader is the frozen model plus the learned linear head. The model receives selected public trace evidence, available source, and the actual screenshot. Personal preference labels fit the head; the target criticism and agent verdicts stay outside the input.</p><div class="probe-flow"><div class="probe-node"><small>01 · EVIDENCE</small><strong>Request + trace + website</strong><p>Source-bound spans and real pixels. Missing artifacts are explicit.</p></div><div class="probe-node"><small>02 · FROZEN MODEL</small><strong>Qwen2.5-VL · 3B</strong><p>One forward pass. Zero generated tokens. Backbone weights stay fixed.</p></div><div class="probe-node"><small>03 · REPRESENTATION</small><strong>${d.dimensions||'…'} activations</strong><p>Fixed layer and last-query-token readout. No agent opinion feature.</p></div><div class="probe-node"><small>04 · PERSONAL GRADER</small><strong>Learned linear probe</strong><p>Fits your label interpretations. Produces an uncalibrated score.</p></div></div><div class="probe-warning"><b>${failedAudit?'First probe failed the human-counterexample audit.':fitted?'Pipeline executed; validation pending.':'Evidence prepared; cloud extraction in progress.'}</b> ${gate?.passed?'The frozen release checks passed.':'Optimization is gated. The labels are automatic interpretations, and the old teacher checks are reused data. These results do not establish personal-taste accuracy.'}</div><div class="probe-metrics"><div class="probe-metric"><b>${d.trainable_parameters||'—'}</b><span>learned head parameters<br>0 trainable backbone parameters</span></div><div class="probe-metric"><b>${probeMetric(d.metrics?.dev)}</b><span>development label matches<br>${Object.entries(d.label_counts.dev).map(([label,n])=>`${n} ${esc(label)}`).join(' · ')}</span></div><div class="probe-metric"><b>${probeMetric(d.metrics?.test)}</b><span>reused teacher-check matches<br>not an untouched human test</span></div></div><h2 class="judge-heading">Scores on the saved designs</h2><p class="judge-description">The linear probe assigned these scores. Investigator and human ratings are shown separately for audit and were excluded from these inputs and from fitting.</p><div class="probe-score-grid">${(d.scores||[]).map(probeScoreCard).join('')||'<p class="judge-description">Saved-design scores will appear after extraction and fitting finish.</p>'}</div><details class="probe-details"><summary>Evidence and label provenance · ${d.evidence_coverage.examples} examples</summary><p>${d.evidence_coverage.with_trace} examples include selected public trace spans. ${d.evidence_coverage.references} are reference images. Target feedback and future messages are excluded; bounded selection does not imply complete long-session coverage.</p><div class="probe-evidence-list">${examples}</div></details><details class="probe-details"><summary>Validation checks and limitations</summary><ul>${Object.entries(gate?.checks||{}).map(([k,v])=>`<li>${v?'Pass':'Pending / failed'} · ${esc(k.replaceAll('_',' '))}</li>`).join('')}${(d.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details><p class="probe-version">Backbone ${esc(d.spec.model)}<br>Revision ${esc(d.spec.revision)}<br>Probe ${esc(d.version||'not fitted')}<br>${fitted?'<a href="/api/probe/head" target="_blank" rel="noopener">Inspect frozen weights and fit receipt ↗</a>':''}</p>`;
    if(view==='probe')updateContext();
  }catch(error){probeView.innerHTML='<p class="probe-warning">The probe report could not be loaded. Refresh to retry.</p>';}
  finally{probeLoading=false;}
}

const preProbeSkill=renderSkill;
renderSkill=function(){
  if(inspectorTab!=='probe'){preProbeSkill();return;}
  for(const button of document.querySelectorAll('[data-skill-tab]'))button.classList.toggle('active',button.dataset.skillTab==='probe');
  $('skillHeading').textContent='Activation-probe grader';
  const id=modalId, entry=probeInspections.get(id);
  if(entry){$('skillSource').textContent=JSON.stringify(entry,null,2);return;}
  $('skillSource').textContent='Loading the exact evidence packet and probe readout…';
  if(probeInspections.has(id))return;
  probeInspections.set(id,null);
  fetch(`/api/design/${id}/probe`,{cache:'no-store'}).then(r=>r.ok?r.json():{note:'No activation-probe score has been recorded for this attempt.'}).then(report=>{probeInspections.set(id,report);if(modalId===id&&inspectorTab==='probe')renderSkill();}).catch(()=>{probeInspections.set(id,{error:'Could not load probe input'});if(modalId===id&&inspectorTab==='probe')renderSkill();});
};
document.addEventListener('click',event=>{const button=event.target.closest('[data-probe-open]');if(button){openModal(button.dataset.probeOpen);inspectorTab='probe';renderSkill();}});
setInterval(()=>{if(view==='probe'&&!document.hidden)loadProbe();},10000);
if(data)render();
