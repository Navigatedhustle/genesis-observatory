/* Readable presentation of existing records. No extra inference or world actions. */
window.Understanding = (() => {
  let held = false, lastFeed = '', probeHits = [];
  const roleText = {
    mira: 'Studies food: how much is nearby and how quickly it returns.',
    oren: 'Studies movement: how much energy a probe needs to travel.',
    vale: 'Checks uncertainty: what other explanations might fit the evidence.'
  };
  function describeRole(a) {
    if (!a) return 'Investigates the world through local measurements.';
    const defaults = {mira:'resource dynamics and repeated measurements',oren:'travel energetics and controlled comparisons',vale:'alternative explanations, uncertainty, and falsification'};
    if (defaults[a.id] === a.priority) return roleText[a.id];
    if (a.priority === 'Quantitative investigation of travel energy, uncertainty, controls, and falsification.') return 'Investigates movement energy with local instruments, controls, and separate memories.';
    return a.priority ? 'Configured focus: ' + a.priority : 'Investigates the world through local measurements.';
  }
  const names = () => view === 'operator' ? state?.agent_registry?.[world] || {} : {[actor]: {name: state?.identity || actor}};
  const name = id => id === 'operator' ? 'You' : names()[id]?.name || 'An investigator';
  const short = (text, max = 180) => String(text || '').length > max ? String(text).slice(0, max).trim() + '…' : String(text || '');
  const location = p => Array.isArray(p) ? `(${p.join(', ')})` : 'its local area';
  const tickOf = r => r.data?.recorded_tick ?? r.data?.result?.start_tick ?? r.data?.result?.tick ?? r.data?.start_tick ?? r.data?.at_tick ?? r.data?.tick;
  function source(r) {
    return `<details class="log-source" data-source="${r.id}"><summary>Source record #${r.id}</summary><pre>${esc(JSON.stringify(r.data, null, 2))}</pre></details>`;
  }
  function measurement(result) {
    if (!result) return 'No measurement has been recorded.';
    if (result.error) return `The instrument could not run: ${result.error}.`;
    const at = location(result.position);
    switch (result.instrument) {
      case 'local_sample': return `Sampled ${at}: ${fmt(result.resource)} food energy available; one probe step costs ${fmt(result.travel_energy_one_step)} energy.`;
      case 'probe_position': return `Moved the measuring probe to ${at}.`;
      case 'arrival_position': return `Arrived at ${at}, with separate records.`;
      case 'organism_observation': return `Counted ${fmt(result.count)} organisms near ${at}.`;
      case 'movement': return `Tested ${result.steps ?? '?'} probe steps near ${at}: used ${fmt(result.value)} energy. Predicted ${fmt(result.prediction)} before the test.`;
      case 'growth': return `Tested food regrowth near ${at}: ${fmt(result.value)} energy returned after ${fmt(result.ticks)} steps. Predicted ${fmt(result.prediction)} before the test.`;
      default: return 'Recorded an instrument observation; see its original record.';
    }
  }
  function describeRecord(r) {
    const d = r.data || {}, who = name(r.actor), result = d.result;
    const row = {key: 'r-' + r.id, id: r.id, time: r.time, tick: tickOf(r), group: 'investigators', tag: 'Measured', title: '', body: '', record: r};
    switch (r.kind) {
      case 'god_prediction':
        row.group='god';row.tag='God’s prediction';row.title='God predicted an outcome before changing the world';
        row.body=`After 100 steps, compared with an unchanged copy: ${d.population_delta>=0?'+':''}${fmt(d.population_delta)} organisms, ${d.energy_delta>=0?'+':''}${fmt(d.energy_delta)} mean energy, and ${fmt(d.food_coverage_delta*100)} percentage points of food-rich ground. ${d.hypothesis || ''}`;break;
      case 'god_change':
        row.group='god';row.tag='Actual change';row.title=d.kind==='food_pulse'?'God changed the food available in a patch':`God changed ${d.kind==='growth'?'food regrowth':'movement cost'} in a patch`;
        row.body=d.kind==='food_pulse'?`Delivered ${fmt(d.energy_delivered)} net food energy in region ${d.region.join(', ')}.`:`Multiplier ${fmt(d.factor)} in region ${d.region.join(', ')} until step ${fmt(d.end)}. Investigators must measure the effects themselves.`;break;
      case 'god_outcome':
        row.group='god';row.tag='Independent comparison';row.title=d.confounded?'God’s test finished with another change mixed in':'The world was compared with an unchanged copy';
        row.body=`After 100 steps, compared with an unchanged copy: population difference ${fmt(d.difference_vs_control.population_delta)} organisms; mean-energy difference ${fmt(d.difference_vs_control.energy_delta)}; food-rich ground difference ${fmt(d.difference_vs_control.food_coverage_delta*100)} percentage points. Predictions within tolerance: ${Object.values(d.grade).filter(x=>x.within_tolerance).length}/3. ${d.replay_match?'Recorded actions replay exactly.':'Replay check failed.'}`;break;
      case 'god_reply':
        row.group='god';row.tag='God’s interpretation · may be wrong';row.title='God answered from recorded observations';row.body=d.reply;row.quote=true;break;
      case 'god_failure':
        row.group='god';row.tag='Request status';row.title='God’s request encountered a failure';row.body=d.error || 'A local model output did not pass validation. No successful outcome is assumed.';break;
      case 'god_control':
        row.group='god';row.tag='Your control';row.title=d.enabled?'God’s automatic experiments enabled':'God’s automatic experiments stopped';row.body=`Target: ${d.world}. Decision interval: ${d.interval} seconds. Existing temporary rules expire at their recorded step.`;break;
      case 'tool':
        if (['movement','growth'].includes(result?.instrument)) return null; // The paired measurement record contains this outcome.
        row.title = `${who} ${result?.instrument === 'probe_position' ? 'moved a probe' : result?.instrument === 'organism_observation' ? 'observed organisms' : 'took a measurement'}`;
        row.body = measurement(result); break;
      case 'measurement':
        row.title = `${who} finished a ${d.instrument === 'growth' ? 'food-regrowth' : 'movement'} test`;
        row.body = measurement(d); row.tag = 'Test result'; break;
      case 'prediction':
        row.title = `${who} made a prediction before testing`;
        row.body = `Expected ${fmt(d.prediction)} ${d.instrument === 'growth' ? 'food energy to return' : 'probe energy to be used'}${d.position ? ' near ' + location(d.position) : ''}. The result comes afterward.`;
        row.tag = 'Prediction'; break;
      case 'note':
        row.title = `${who} recorded a belief`; row.body = d.hypothesis || d.reply || 'No belief text was saved.'; row.tag = 'Belief · may be wrong';
        row.quote = true; break;
      case 'message_sent':
        row.title = `${name(d.sender)} sent a message to ${name(d.recipient)}`;
        row.body = d.text || ''; row.quote = true; row.tag = d.evidence?.length ? 'Message + evidence' : 'Message · testimony';
        row.extra = `${d.evidence?.length || 0} actual instrument record(s) attached.${d.origin?.startsWith('operator') ? ' You composed this message.' : ''}`; break;
      case 'message': return null; // Same delivery is already represented by message_sent.
      case 'first_contact':
        row.title = `${name(d.actor)} arrived in this world`; row.body = `Started at ${location(d.position)} with its own records. ${d.origin === 'ngi' ? 'This newcomer uses a different local model family.' : 'This is a same-family newcomer.'}`;
        row.tag = 'Arrival'; row.group = 'changes'; break;
      case 'arrival_scheduled':
        row.title = `You scheduled ${d.name || 'a newcomer'} to arrive`; row.body = `Arrival is set for step ${fmt(d.arrival_tick)} at ${location(d.position)}.`; row.tag = 'Your control'; row.group = 'changes'; break;
      case 'intervention':
        row.title = `You changed ${d.kind === 'growth' ? 'food regrowth' : 'movement cost'}`;
        row.body = `Multiplier ${fmt(d.factor)} in region ${d.region?.join(', ')}${d.start !== undefined ? ', starting at step ' + fmt(d.start) : ''}. This rule information is visible to you, not the investigators.`;
        row.group = 'changes'; row.tag = 'Your control'; break;
      case 'checkpoint':
        row.title = 'You saved a moment'; row.body = `The world and investigator records can be restored from ${d.id || d.checkpoint || 'this save'}.`; row.tag = 'Your control'; row.group = 'changes'; break;
      case 'branch':
        row.title = 'You made independent copies of a saved world'; row.body = 'The copies can now develop under different rules. Their investigator memories stay separate.'; row.tag = 'Your control'; row.group = 'changes'; break;
      case 'restore':
        row.title = 'You rewound a world'; row.body = 'The saved physical state and investigator records were restored.'; row.tag = 'Your control'; row.group = 'changes'; break;
      case 'control':
        row.title = 'You changed the observation controls'; row.body = [d.paused !== undefined ? (d.paused ? 'World stepping paused.' : 'World stepping resumed.') : '', d.speed !== undefined ? `World speed set to ${d.speed * 2} steps per second.` : '', d.live_autonomy !== undefined ? (d.live_autonomy ? 'Automatic investigations enabled.' : 'Automatic investigations stopped; chat is still available.') : ''].filter(Boolean).join(' '); row.tag = 'Your control'; row.group = 'changes'; break;
      case 'job':
        if (!['failed','cancelled','interrupted'].includes(d.status)) return null;
        row.title = `${name(d.actor)}’s request ${d.status === 'failed' ? 'failed' : 'stopped'}`; row.body = d.error || 'The request did not finish. No successful outcome is assumed.'; row.tag = 'Request status'; break;
      case 'failure': case 'tool_error':
        row.title = `${who}’s request could not finish`; row.body = d.error || d.detail || d.message || 'An error was recorded. See the original record.'; row.tag = 'Request status'; break;
      default: return null;
    }
    return row;
  }
  function ecologyRows(w) {
    const h = w?.history || [], rows = [];
    for (let i = Math.max(1,h.length-10); i < h.length; i++) {
      const a = h[i-1], b = h[i];
      if (b.tick <= a.tick || b.births < a.births || b.deaths < a.deaths) continue;
      rows.push({key:'eco-'+world+'-'+b.tick, tick:b.tick, from:a.tick, group:'ecology', tag:'World counters', title:'Organisms lived, ate, and reproduced',
        body:`From step ${fmt(a.tick)} to ${fmt(b.tick)}: ${fmt(b.births-a.births)} born, ${fmt(b.deaths-a.deaths)} died. Organisms ate ${fmt(b.food_consumed-a.food_consumed)} food energy; ${fmt(b.resource_generated-a.resource_generated)} grew back. ${fmt(b.population)} organisms were alive at the end.`, source:{from:a,to:b}});
    }
    return rows;
  }
  function allRecords() {
    const records = [...(state.records || []), ...Object.values(state.investigator_records || {}).flat(), ...(state.channel_records || []), ...(state.god?.records || [])];
    return [...new Map(records.filter(r=>r.scope === world || r.scope === 'god:'+world || (r.scope === 'operator' && r.kind === 'control' && r.data?.world_ticks?.[world] !== undefined)).map(r=>[r.id,r])).values()];
  }
  function resetJournal() {
    held=false;lastFeed='';$('feed').innerHTML='';$('ecology-summary').textContent='';
    $('hold-log').textContent='Hold log still';$('hold-log').setAttribute('aria-pressed','false');
  }
  function renderFeed() {
    if (view !== 'operator' || !state?.worlds) return;
    const records = allRecords();
    $('log-status').textContent = held ? 'Log held still · world continues' : 'Live · saved events';
    if (held) return;
    const filter = $('log-filter').value, beliefs = $('show-beliefs').checked;
    const events = records.map(describeRecord).filter(Boolean).filter(r=>beliefs || (!r.tag.startsWith('Belief') && !r.tag.includes('interpretation')));
    const ecology = ecologyRows(selectedWorld());
    let rows = [...events, ...(filter==='ecology'?ecology:ecology.slice(-1))].filter(r => filter === 'all' || r.group === filter || (filter === 'selected' && (r.record?.actor === actor || r.record?.data?.sender === actor || r.record?.data?.recipient === actor)));
    // Time-of-world is authoritative; older records without a tick sort by record order below dated world events.
    rows.sort((a,b)=>(b.tick ?? -1)-(a.tick ?? -1) || (b.id || 0)-(a.id || 0));
    rows = rows.slice(0,45);
    const html = rows.map(r => `<article class="journal-entry group-${r.group}" data-event="${esc(r.key)}"><div class="journal-meta"><span class="event-tag ${r.quote?'claim':''}">${esc(r.tag)}</span><span>${r.tick !== undefined ? 'step ' + fmt(r.tick) : r.time ? new Date(r.time*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''}</span></div><h3>${esc(r.title)}</h3><p>${r.quote?'“':''}${esc(short(r.body,310))}${r.quote?'”':''}</p>${r.extra?'<p class="hint">'+esc(r.extra)+'</p>':''}${String(r.body).length>310?`<details class="full-statement" data-source="full-${esc(r.key)}"><summary>Read the complete statement</summary><p>${esc(r.body)}</p></details>`:''}${r.record ? source(r.record) : `<details class="log-source" data-source="${esc(r.key)}"><summary>Source: measured world counters</summary><pre>${esc(JSON.stringify(r.source,null,2))}</pre></details>`}</article>`).join('') || '<div class="empty-log">No matching records yet. Choose an investigator and ask for a measurement, or choose another log filter.</div>';
    if (html !== lastFeed) {
      const feed = $('feed'), scroll = feed.scrollTop;
      const open = [...feed.querySelectorAll('details[open][data-source]')].map(el=>el.dataset.source);
      feed.innerHTML = html; feed.scrollTop = scroll;
      feed.querySelectorAll('details[data-source]').forEach(el=>el.open=open.includes(el.dataset.source));
      lastFeed = html;
    }
    const w = selectedWorld(), rowsEco = ecologyRows(w), last = rowsEco.at(-1);
    $('ecology-summary').textContent = last ? `Latest recorded window: ${fmt(last.source.to.births-last.source.from.births)} born · ${fmt(last.source.to.deaths-last.source.from.deaths)} died · ${fmt(w.metrics.population)} alive now` : `${fmt(w.metrics.population)} organisms alive. Population changes come from the actual world.`;
    $('ecology-summary').hidden = !['all','ecology'].includes(filter);
  }
  function jobsFor(id) { return (state.jobs || []).filter(j=>j.actor===id && (!j.world || j.world===world)); }
  function latestRecords(id) { return (state.investigator_records?.[id] || []).slice().sort((a,b)=>(b.id || 0)-(a.id || 0)); }
  function doing(id) {
    const jobs = jobsFor(id), active = jobs.find(j=>j.status==='running'), waiting = jobs.find(j=>j.status==='queued');
    if (active) return {label:'Working', text: active.kind==='chat' ? 'Preparing an answer from its own observations and records.' : 'Investigating with bounded instruments. A request may contain several measurements.'};
    if (waiting) return {label:'Queued', text:'Waiting for its local model. The world can keep moving while it waits.'};
    const latest = jobs.at(-1);
    if (latest && ['failed','cancelled','interrupted'].includes(latest.status)) return {label:'Request stopped',text:latest.error || 'Its last request did not finish. You can ask again.'};
    return {label:'Between requests',text:state.settings?.live_autonomy ? (world==='origin' ? 'Between investigations. Automatic requests start about once a minute; your chat can start one now.' : 'Automatic investigations run in the original world. In this copy, ask a question or request a measurement.') : 'Waiting for a question or a measurement request. Automatic investigation is off.'};
  }
  function choose(id) { actor=id;lastChat='';selected=null;held=false;$('hold-log').textContent='Hold log still';$('hold-log').setAttribute('aria-pressed','false');$('message').placeholder='Ask '+name(id)+' a question…';if(view==='operator'&&state?.worlds)render();refresh(); }
  function renderAgents() {
    const agents = view==='operator' ? Object.values(names()) : [{id:actor,name:state.identity,active:true}];
    agents.forEach(a=>{if(a.color) colors[a.id]=a.color});
    const container=document.querySelector('.investigators');
    const html=agents.map(a=>{const status=view==='operator'?doing(a.id).label:'Selected observer';return `<button data-actor="${esc(a.id)}" class="investigator ${a.id===actor?'active':''}" ${a.active?'':'disabled'}><span class="initial" style="color:${esc(a.color || '#70ded7')}">${esc(a.name[0])}</span><div><b>${esc(a.name)}</b><small>${esc(a.id==='mira'?'Food researcher':a.id==='oren'?'Movement researcher':a.id==='vale'?'Checks alternative explanations':view==='operator' && a.origin==='ngi'?'Newcomer · different model family':'Investigator')}</small></div><span class="agent-state">${a.active?esc(status):'Arrives at step '+fmt(a.arrival_tick)}</span></button>`}).join('');
    if(container.innerHTML!==html){const focus=container.querySelector(':focus')?.dataset.actor;container.innerHTML=html;container.querySelectorAll('[data-actor]').forEach(b=>b.onclick=()=>choose(b.dataset.actor));if(focus)container.querySelector(`[data-actor="${CSS.escape(focus)}"]`)?.focus()}
    if(view==='operator')fillSelect('recipient',agents.filter(a=>{if(!a.active||a.id===actor)return false;const p=state.probes[world]?.[actor]||[0,0],q=state.probes[world]?.[a.id]||a.position;return q && Math.max(Math.min(Math.abs(p[0]-q[0]),48-Math.abs(p[0]-q[0])),Math.min(Math.abs(p[1]-q[1]),48-Math.abs(p[1]-q[1])))<=12}).map(a=>({value:a.id,label:a.name})));
  }
  function renderInvestigator(records) {
    const who=name(actor), ordered=records.some(r=>r.id) ? records.slice().sort((a,b)=>(b.id || 0)-(a.id || 0)) : records.slice().reverse();
    const tool=ordered.find(r=>r.kind==='tool' && r.data?.result && !r.data.result.error), note=ordered.find(r=>r.kind==='note');
    $('observer-name').textContent=who;
    $('chat-title').textContent='Talk to '+who;
    $('belief-heading').textContent='What '+who+' believes';
    $('message').placeholder='Ask '+who+' a question…';
    $('observer-role').textContent=view==='operator' ? describeRole(names()[actor]) : 'You are seeing only this investigator’s permitted observations and records.';
    const status=view==='operator' ? doing(actor) : {label:state.jobs.some(j=>j.status==='running')?'Working':'Scoped records',text:'No global state or hidden rule information is shown here.'};
    $('observer-status').textContent=status.label;
    $('observer-now').innerHTML=`<small>Doing now</small><p>${esc(status.text)}</p>`;
    $('observer-last').innerHTML=`<small>Last actual action</small><p>${esc(tool?measurement(tool.data.result):'No instrument action is in the available records yet.')}</p>`;
    const tick=tool?.data.result?.tick ?? tool?.data.result?.start_tick, current=view==='operator'?selectedWorld()?.tick:state.tick;
    $('observer-age').textContent=tick !== undefined ? `Measured at step ${fmt(tick)} · ${fmt(Math.max(0,current-tick))} world steps ago. This reading is not a live feed.` : '';
    $('next-plan').textContent=note?.data.next_experiment ? 'Proposed next: '+note.data.next_experiment+' (a proposal, not a completed action).' : '';
    if(note){$('confidence').textContent='Self-reported confidence: '+Math.round(note.data.confidence*100)+'%';$('falsifier').textContent='What would change this belief: '+note.data.falsifier+(note.data.recorded_tick!==undefined?' · Note from step '+fmt(note.data.recorded_tick):'')}
    if(view==='operator') {
      let button=$('inspect-observer');
      if(!button){button=document.createElement('button');button.id='inspect-observer';button.className='text-link';$('observer-card').append(button)}
      button.hidden=false;button.textContent='About '+who+' & its saved records';button.onclick=()=>inspect(actor);
    }else if($('inspect-observer'))$('inspect-observer').hidden=true;
  }
  function render() {
    const operator=view==='operator';
    $('world-guide').hidden=!operator || $('guide-toggle').getAttribute('aria-expanded')==='false';
    $('watch-controls').hidden=!operator;$('science-details').hidden=!operator;
    $('guide-toggle').disabled=!operator;
    if(!operator){$('inspector-summary').innerHTML='';return;}
    const w=selectedWorld();
    $('world-title').innerHTML=(world==='origin'?'The living world':esc(world))+' <span>• '+fmt(w.tick)+' world steps</span>';
    $('pause').textContent=state.settings.paused?'Resume world':'Pause world';
    $('autonomy').textContent='Auto investigation: '+(state.settings.live_autonomy?'on':'off');
    $('clock').textContent='step '+fmt(w.tick);
    const m=w.metrics;
    $('stats').innerHTML=[['Organisms alive',fmt(m.population),'Tiny dots that eat and reproduce'],['Food-rich ground',Math.round(m.resource_coverage*100)+'%','Cells with more than 0.4 food energy'],['Investigators present',Object.values(names()).filter(a=>a.active).length,'Named probes that measure and talk']].map(([label,value,hint])=>`<div class="stat"><small>${label}</small><b>${value}</b><em>${hint}</em></div>`).join('');
    const activeLaws=w.laws.filter(l=>l.end===undefined||w.tick<l.end);
    $('world-law').textContent=activeLaws.length?activeLaws.map(l=>`${l.kind==='growth'?'Food regrowth':'Movement cost'} ×${fmt(l.factor)}${l.start>w.tick?' at step '+fmt(l.start):''}${l.god_id?' · God, expires '+fmt(l.end):''}`).join(' · '):'Original rules · no changes here';
    $('generation').textContent='Latest organism generation: '+fmt(m.max_generation)+' (reproduction depth, not an intelligence score).';
    // Existing server fetch status is separate from all physical counters.
  }
  function roundRect(ctx,x,y,w,h,r=6){ctx.beginPath();ctx.roundRect(x,y,w,h,r);}
  function drawWorld(canvas,w,isMain=false) {
    if(!w)return;
    const [ctx,cw,ch]=canvasContext(canvas),z=isMain?zoom:1,s=Math.min(cw,ch)/48*z,ox=(cw-48*s)/2+(isMain?pan[0]:0),oy=(ch-48*s)/2+(isMain?pan[1]:0);
    ctx.fillStyle=matrix?'#040d08':'#091b23';ctx.fillRect(0,0,cw,ch);ctx.save();ctx.translate(ox,oy);
    for(let y=0;y<48;y++)for(let x=0;x<48;x++){const f=w.food[y][x];ctx.fillStyle=matrix?`rgb(4,${Math.round(16+f*23)},${Math.round(10+f*8)})`:`rgb(${Math.round(12+f*7)},${Math.round(32+f*36)},${Math.round(35+f*23)})`;ctx.fillRect(x*s,y*s,s+.4,s+.4)}
    if(isMain&&selected!==null){const t=trail.get(world+':'+selected)||[];ctx.strokeStyle='#ffe0a28a';ctx.lineWidth=2;ctx.beginPath();t.forEach((p,i)=>{if(!i||Math.abs(p[0]-t[i-1][0])+Math.abs(p[1]-t[i-1][1])>4)ctx.moveTo((p[0]+.5)*s,(p[1]+.5)*s);else ctx.lineTo((p[0]+.5)*s,(p[1]+.5)*s)});ctx.stroke()}
    let alive=false;
    for(const o of w.organisms){const energy=Math.min(1,Math.max(0,o.energy/16)),x=(o.x+.5)*s,y=(o.y+.5)*s,r=Math.max(2,s*.21);
      ctx.fillStyle=matrix?`hsl(128 75% ${38+energy*38}%)`:`hsl(174 65% ${40+energy*35}%)`;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
      if(s>13){ctx.strokeStyle='#d8fff75c';ctx.lineWidth=.65;ctx.stroke()}
      if(o.id===selected&&isMain){alive=true;ctx.strokeStyle='#ffe0a2';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,r+5,0,Math.PI*2);ctx.stroke();const key=world+':'+selected,t=trail.get(key)||[];if(!t.length||t.at(-1)[2]!==w.tick)t.push([o.x,o.y,w.tick]);trail.set(key,t.slice(-100));$('selection').textContent=`Following organism #${o.id} · age ${o.age} steps · ${fmt(o.energy)} energy · generation ${o.generation}. Its line shows observed travel.`}
    }
    if(isMain&&selected!==null&&!alive)$('selection').textContent=`Organism #${selected} is no longer alive. It is absent from the current population; click another dot.`;
    for(const l of w.laws.filter(l=>l.end===undefined||w.tick<l.end)){const [x0,y0,x1,y1]=l.region;ctx.fillStyle='#e8b76b12';ctx.fillRect(x0*s,y0*s,(x1-x0)*s,(y1-y0)*s);ctx.strokeStyle=l.start>w.tick?'#e8b76b55':'#e8b76bcc';ctx.lineWidth=1.5;ctx.setLineDash([6,5]);ctx.strokeRect(x0*s,y0*s,(x1-x0)*s,(y1-y0)*s);ctx.setLineDash([])}
    const habitatKey=Object.keys(state.worlds).find(k=>state.worlds[k]===w),probes=state.probes?.[habitatKey]||{},agents=state.agent_registry?.[habitatKey]||{},labels=[];
    if(isMain)probeHits=[];
    // Labels can move for readability; a connector always points to the actual probe cell.
    for(const [id,p] of Object.entries(probes)){
      const a=agents[id];if(!a?.active)continue;const x=(p[0]+.5)*s,y=(p[1]+.5)*s,color=colors[id]||'#a2ff99';
      ctx.strokeStyle=color;ctx.fillStyle='#0b1b22';ctx.lineWidth=id===actor?2.5:1.5;ctx.beginPath();ctx.arc(x,y,Math.max(6,s*.5),0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.font='600 11px system-ui';ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(a.name[0],x,y+4);ctx.textAlign='left';
      const text=a.name,width=ctx.measureText(text).width+20,height=25;let lx=Math.min(48*s-width-2,Math.max(2,x+12)),ly=Math.max(2,y-31);
      for(let attempt=0;attempt<15 && labels.some(b=>lx<b.x+b.w+5&&lx+width>b.x-5&&ly<b.y+b.h+4&&ly+height>b.y-4);attempt++)ly+=29;
      if(ly+height>48*s)ly=Math.max(2,y-31-29*labels.length);
      labels.push({x:lx,y:ly,w:width,h:height});ctx.strokeStyle=color+'90';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(lx+5,ly+height/2);ctx.stroke();
      roundRect(ctx,lx,ly,width,height);ctx.fillStyle=id===actor?'#193d42':'#102831';ctx.fill();ctx.strokeStyle=color+'99';ctx.stroke();ctx.fillStyle=color;ctx.fillText(text,lx+10,ly+17);
      if(isMain){probeHits.push({id,x:lx+ox,y:ly+oy,w:width,h:height});probeHits.push({id,x:x+ox-9,y:y+oy-9,w:18,h:18})}
    }
    ctx.restore();if(matrix&&isMain){drawRain(ctx,cw,ch);ctx.font='10px monospace';ctx.fillStyle='#9dfc91';ctx.fillText('DECORATIVE RAIN · VALUES AND ENTITIES ARE REAL',12,20)}
    return {s,ox,oy};
  }
  async function inspectEntity(entity) {
    if(view!=='operator')return;
    const requestedWorld=world;
    try{
      const data=await api('/api/entity/'+encodeURIComponent(world)+'/'+encodeURIComponent(entity));
      if(view!=='operator'||requestedWorld!==world)return;
      $('inspector-data').textContent=JSON.stringify(data,null,2);
      if(data.category==='evolved organism'){
        const o=selectedWorld().organisms.find(o=>o.id===data.id),action=data.last_controller_activation?.action;
        const actions=['Stayed in place','Moved east','Moved west','Moved south','Moved north','Tried to eat nearby food'];
        $('inspector-title').textContent='Organism #'+data.id;
        $('inspector-summary').innerHTML=`<p class="entity-lead">One of the little dots. It has an inherited neural controller, not a language model.</p><div class="entity-stats"><div><small>Energy remaining</small><b>${o?fmt(o.energy):'No longer present'}</b></div><div><small>Age in world steps</small><b>${o?fmt(o.age):'—'}</b></div><div><small>Generation</small><b>${fmt(data.generation)}</b></div></div><p><b>Last recorded controller choice:</b> ${esc(actions[action] || 'No controller trace available yet')}.</p><p>Movement uses energy. Eating nearby food restores energy. An organism with enough energy can reproduce; its child inherits a slightly mutated controller. It dies if its energy runs out or its age reaches 600 steps.</p><p class="hint">Parent: ${data.parent<0?'original founding organism':'organism #'+data.parent}. Generation counts reproduction, not intelligence. The choice is a recorded action, not a thought.</p>`;
      }else{
        const a=data.provenance,rs=data.records.filter(r=>r.kind==='tool'),note=data.records.find(r=>r.kind==='note');
        $('inspector-title').textContent='Meet '+a.name;
        $('inspector-summary').innerHTML=`<p class="entity-lead">${esc(describeRole(a))}</p><p>${esc(data.category)} · ${esc(data.model.family)} family. It cannot see your hidden rule controls, source code, or other investigators’ private records.</p><h3>Last actual instrument action</h3><p>${esc(rs[0]?measurement(rs[0].data.result):'No action is in the available records yet.')}</p><h3>Current recorded belief · may be wrong</h3><blockquote>${esc(note?.data.hypothesis || 'No belief recorded.')}</blockquote><p>Its records and beliefs can change. Its model weights are not being trained here. It observes the organisms rather than controlling their behaviour.</p><button id="inspect-follow" class="accent">Follow ${esc(a.name)}’s measurements</button>`;
        $('inspect-follow').onclick=()=>{$('inspector').close();choose(a.id)};
      }
      $('inspector').querySelector('.raw-details').open=false;
      if(!$('inspector').open)$('inspector').showModal();
    }catch(e){toast(e.message==='Organism is no longer alive'?'This organism died before its record could open. Pause the world to inspect a dot, or choose another.':e.message)}
  }
  $('advanced-toggle').onclick=()=>{const open=$('advanced-panel').hidden;$('advanced-panel').hidden=!open;$('advanced-toggle').setAttribute('aria-expanded',String(open));document.body.classList.toggle('advanced-mode',open)};
  $('close-advanced').onclick=()=>{$('advanced-panel').hidden=true;$('advanced-toggle').setAttribute('aria-expanded','false');document.body.classList.remove('advanced-mode');$('advanced-toggle').focus()};
  $('guide-toggle').onclick=()=>{const open=$('guide-toggle').getAttribute('aria-expanded')!=='true';$('guide-toggle').setAttribute('aria-expanded',String(open));$('world-guide').hidden=!open};
  $('hold-log').onclick=()=>{held=!held;$('hold-log').textContent=held?'Resume live log':'Hold log still';$('hold-log').setAttribute('aria-pressed',String(held));if(!held)lastFeed='';renderFeed()};
  $('log-filter').onchange=()=>{held=false;$('hold-log').textContent='Hold log still';$('hold-log').setAttribute('aria-pressed','false');lastFeed='';renderFeed()};
  $('show-beliefs').onchange=()=>{held=false;$('hold-log').textContent='Hold log still';$('hold-log').setAttribute('aria-pressed','false');lastFeed='';renderFeed()};
  document.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>{$('message').value=b.dataset.question;$('message').focus()});
  return {resetJournal,renderFeed,renderAgents,renderInvestigator,render,drawWorld,inspect:inspectEntity,choose,measurement,describeRecord,ecologyRows,get probeHits(){return probeHits}};
})();
