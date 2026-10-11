/* Operator-only steward console. Inhabitants never receive this state. */
window.GodUI = (() => {
  let chatKey='', recordKey='', policyKey='';
  const signed=n=>(n>0?'+':'')+fmt(n);
  function open() {
    if(view!=='operator')return;
    const next=!document.body.classList.contains('god-chat-mode');
    document.body.classList.toggle('god-chat-mode',next);
    $('god-panel').hidden=!next;$('god-toggle').setAttribute('aria-expanded',String(next));
    if(next){if(document.body.classList.contains('presentation-mode'))$('presentation').click();render();$('god-panel').scrollIntoView({behavior:'smooth',block:'start'});}
  }
  function hideAndClear() {
    document.body.classList.remove('god-chat-mode');$('god-panel').hidden=true;$('god-toggle').setAttribute('aria-expanded','false');
    ['god-chat','god-results','god-reactions','god-records','god-runtime','god-status','god-work','god-auto-info'].forEach(id=>$(id).textContent='');
    $('god-policy').value='';$('god-message').value='';$('god-export').removeAttribute('href');chatKey=recordKey=policyKey='';
  }
  function changeText(c,tick) {
    if(!c)return 'No God change has run in this world yet.';
    const at='patch ('+c.region.join(', ')+')';
    if(c.kind==='food_pulse')return `At step ${fmt(c.tick)}: ${signed(c.energy_delivered)} food energy delivered to ${at}. This was a one-time resource change.`;
    return `At step ${fmt(c.tick)}: ${c.kind==='growth'?'food regrowth':'movement cost'} ×${fmt(c.factor)} in ${at}. ${tick>=c.end?'Expired':'Expires'} at step ${fmt(c.end)}.`;
  }
  async function submit(path,data,notice) {
    try {const r=await api(path,data);toast(notice);refresh();return r;}catch(e){toast(e.message);return null;}
  }
  function render() {
    $('god-toggle').hidden=view!=='operator';
    if(view!=='operator'){hideAndClear();return;}
    const s=state?.god;if(!s)return;
    const cfg=s.config,rt=s.runtime,w=selectedWorld(),busy=s.jobs.filter(j=>['queued','running'].includes(j.status));
    const current=busy.find(j=>j.status==='running'),last=s.jobs.at(-1);
    $('god-status').textContent=current?'God is reading and responding':rt.resident?'God is ready · local 70B model':rt.runtime_available?'Local model will load on request':'Local runtime unavailable';
    $('god-runtime').textContent=`Llama 3.1 70B · Ollama · ${rt.resident?'loaded, '+fmt(rt.resident_gib)+' GiB':'not loaded'}${rt.available_gib!==undefined?' · '+fmt(rt.available_gib)+' GiB memory available':''}${rt.latency_s?' · last reply '+fmt(rt.latency_s)+' s':''}`;
    $('god-work').textContent=current?`Request ${current.id}: ${Math.round(Date.now()/1000-current.created)} seconds elapsed. ${s.queue} waiting. This large model may take several minutes, including one retry; world steps continue.`:last?.status==='failed'?`Last request failed: ${last.error}`:last?.status==='interrupted'?'Last request was interrupted by restart. Repeat it as a new request.':last?.status==='cancelled'?'Last request cancelled.':`${s.queue} requests waiting. A reply describes measurements taken when the request began.`;
    if(current||busy.length){const cancel=document.createElement('button');cancel.textContent='Cancel '+(current?'current request':'queued request');cancel.onclick=()=>submit('/api/god/jobs/'+(current||busy[0]).id+'/cancel',{},'Cancellation requested');$('god-work').append(document.createElement('br'),cancel);}
    $('god-auto').textContent=cfg.enabled?(cfg.world===world?'Automatic: on':'Use in this world'):'Automatic: off';
    $('god-auto').setAttribute('aria-pressed',String(cfg.enabled&&cfg.world===world));
    $('god-auto').classList.toggle('active',cfg.enabled&&cfg.world===world);
    $('god-auto-info').textContent=cfg.enabled?`God chooses a bounded experiment in ${cfg.world==='origin'?'the original world':cfg.world} about every ${Math.round(cfg.interval/60)} minute(s), when no test or previous rule is active. Pausing holds automatic decisions. Use a slower world speed to watch changes longer.`:'Turn on to let God choose bounded changes without your messages. Chat still works while this is off.';
    if(document.activeElement!==$('god-interval'))$('god-interval').value=cfg.interval;
    if(policyKey!==cfg.policy && document.activeElement!==$('god-policy')){$('god-policy').value=cfg.policy;policyKey=cfg.policy;}
    const outcome=s.records.find(r=>r.kind==='god_outcome'),p=s.pending;
    let facts=`<p>${esc(changeText(s.last_change,w.tick))}</p>`;
    if(p)facts+=`<p class="god-pending">Measuring the current change: the paired result is due at step ${fmt(p.target_tick)}${state.settings.paused?' · world paused':''}.</p>`;
    if(outcome){const d=outcome.data,latest=s.last_change?.id===d.id,labels={'population_delta':['Organisms alive',' organisms'],'energy_delta':['Energy per organism',' energy'],'food_coverage_delta':['Food-rich ground',' percentage points']};
      facts+=`<p class="hint">${latest?'Last change':'Earlier change'} · measured after exactly 100 steps. Difference from an unchanged copy:</p><div class="god-comparison">`+Object.entries(labels).map(([k,[label,unit]])=>`<div><small>${label}</small><b>${signed(d.difference_vs_control[k]*(k==='food_coverage_delta'?100:1))}</b><span>${unit}</span></div>`).join('')+'</div>';
      const correct=Object.values(d.grade).filter(x=>x.within_tolerance).length;
      facts+=`<p class="hint">${correct}/3 numerical predictions within the predefined tolerances. ${d.replay_match?'Recorded actions replay exactly.':'Replay verification failed.'}${d.confounded?' Another operator change occurred during this comparison; the effect cannot be attributed to God alone.':''} This is a short-term comparison.</p>`;
    }else if(!p)facts+='<p class="hint">After a change, actual survival, energy, and food are compared with a matching unchanged world. The result can show no benefit.</p>';
    $('god-results').innerHTML=facts;
    $('god-reactions').innerHTML=s.last_change?'<h4>Have investigators measured since then?</h4>'+s.reactions.map(r=>`<p><b>${esc(r.name)}</b>: ${r.new_measurements} measurement(s) in its latest 50 records since that step.${r.new_measurements===0?' No observed investigation yet.':''}</p>`).join('')+'<p class="hint">New measurements are evidence of investigation. They do not by themselves mean the change was discovered.</p>':'';
    const chats=s.records.filter(r=>['god_request','god_reply'].includes(r.kind)).slice().reverse(),key=world+JSON.stringify(chats);
    if(chatKey!==key){chatKey=key;const box=$('god-chat'),nearBottom=box.scrollHeight-box.scrollTop-box.clientHeight<50;
      box.innerHTML=chats.length?chats.map(r=>`<div class="bubble ${r.kind==='god_request'?'visitor':''}"><small>${r.kind==='god_request'?(r.data.autonomous?'Automatic experiment goal':'Your request'):'God’s interpretation · may be wrong'}${r.data.observation_tick!==undefined?' · observed step '+fmt(r.data.observation_tick):r.data.tick!==undefined?' · step '+fmt(r.data.tick):''}</small><p>${esc(r.kind==='god_request'?(r.data.autonomous?'Automatic decision using your saved goal. '+(s.jobs.find(j=>j.id===r.data.job)?.status==='cancelled'?'This request was cancelled.':''):r.data.text):r.data.reply)}</p>${r.kind==='god_reply'?`<p class="god-execution">${r.data.applied?'✓ A real change was applied. Prediction saved as #'+r.data.prediction_id:'No change applied. '+(r.data.reason || '')}</p><small>Uncertainty: ${esc(r.data.uncertainty || 'No uncertainty text provided.')}</small><small>Evidence: ${esc((r.data.evidence_ids || []).map(id=>'#'+id).join(', ') || 'No source cited')}</small>`:''}</div>`).join(''):'<p class="chat-empty">Ask why the population changes, whether a recent intervention helped, or suggest a small experiment.</p>';
      if(nearBottom||box.scrollTop===0)box.scrollTop=box.scrollHeight;
    }
    const rk=world+JSON.stringify(s.records.map(r=>r.id));
    if(recordKey!==rk){recordKey=rk;const existing=[...$('god-records').querySelectorAll('details[open]')].map(d=>d.dataset.id);
      $('god-records').innerHTML=s.records.filter(r=>['god_prediction','god_change','god_outcome','god_failure'].includes(r.kind)).map(r=>`<details data-id="${r.id}"><summary>#${r.id} · ${esc(r.kind.replace('god_',''))}</summary><pre>${esc(JSON.stringify(r.data,null,2))}</pre></details>`).join('');
      $('god-records').querySelectorAll('details').forEach(d=>d.open=existing.includes(d.dataset.id));
    }
    $('god-export').href='/api/god/export/'+encodeURIComponent(world);
  }
  $('god-toggle').onclick=open;$('god-back').onclick=open;
  $('god-auto').onclick=()=>submit('/api/god/control',{enabled:!(state.god.config.enabled&&state.god.config.world===world),world},'God’s automatic experiment setting saved');
  $('god-interval').onchange=()=>submit('/api/god/control',{interval:Number($('god-interval').value)},'Decision interval saved');
  $('god-save-policy').onclick=()=>submit('/api/god/control',{policy:$('god-policy').value},'God’s goal saved');
  $('god-act').onclick=()=>submit('/api/god/act',{world},'God is choosing a small experiment');
  $('god-chat-form').onsubmit=async e=>{e.preventDefault();const input=$('god-message'),text=input.value.trim();if(!text)return;
    const result=await submit('/api/god/chat',{world,message:text,allow_changes:$('god-allow').checked},'Question queued for the local 70B model');
    if(result){input.value='';$('god-allow').checked=false;}
  };
  document.querySelectorAll('[data-god-question]').forEach(b=>b.onclick=()=>{$('god-message').value=b.dataset.godQuestion;$('god-allow').checked=b.dataset.change==='true';$('god-message').focus()});
  window.addEventListener('DOMContentLoaded',()=>{if(new URLSearchParams(location.search).get('god')==='1')open()});
  return {render,hideAndClear,open};
})();
