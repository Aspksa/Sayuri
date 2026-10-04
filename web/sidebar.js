/* Sayuri sidebar runtime: authenticated server telemetry, no simulated states. */
(()=>{
'use strict';
const el=id=>document.getElementById(id);
const labels={
 ready:'Готова помочь',reasoning:'Размышляет',researching:'Исследует',
 studying:'Изучает',memorizing:'Запоминает',linking:'Строит связи',
 verifying:'Проверяет',executing:'Выполняет задачу',idle:'Ожидает',
 disconnected:'Нет подключения',attention:'Требует внимания',completed:'Завершила'
};
const cloudLabels={
 connected:'Подключено',degraded:'Сервис отвечает с ошибками',
 rate_limited:'Превышен лимит',auth_error:'Ошибка авторизации',
 insufficient_balance:'Недостаточно средств',timeout:'Таймаут',
 unreachable:'Нет подключения',checking:'Проверка',unknown:'Не настроено / неизвестно'
};
const netLabels={online:'Интернет доступен',degraded:'Сеть работает нестабильно',
 offline:'Интернет недоступен',checking:'Проверка',unknown:'Нет свежих данных'};
const tones={
 ready:'good',completed:'good',idle:'',reasoning:'purple',linking:'purple',
 researching:'info',memorizing:'info',executing:'info',
 studying:'warning',verifying:'warning',attention:'error',disconnected:'error'
};
const validStates=new Set(Object.keys(labels));
let last=0,selected='account',currentToken='',failed=0,polling=null,
 aborter=null,reader=null,stopped=false,focusReturn=null,lastPayload=null,staleTimer=null,
 transportState='checking';
const narrow=()=>matchMedia('(max-width:767px)').matches;
const nodes=()=>{
 return [...el('sayuriSidebar').querySelectorAll('button,summary,a,input,select,textarea,[tabindex]:not([tabindex="-1"])')]
  .filter(n=>!n.disabled&&n.getClientRects().length>0);
};
function closeDrawer(){
 if(!document.body.classList.contains('open'))return;
 document.body.classList.remove('open');
 el('menu').setAttribute('aria-expanded','false');
 if(focusReturn&&narrow())focusReturn.focus();
}
function openDrawer(){
 focusReturn=document.activeElement;
 document.body.classList.add('open');
 el('menu').setAttribute('aria-expanded','true');
 const first=nodes()[0];if(first)first.focus();
}
const collapse=()=>{
 if(narrow())return;
 const compressed=document.body.classList.toggle('sidebar-collapsed');
 el('collapseSidebar').setAttribute('aria-expanded',String(!compressed));
 el('collapseSidebar').setAttribute('aria-label',compressed?'Развернуть боковое меню':'Свернуть боковое меню');
 try{localStorage.setItem('sayuri.sidebar.collapsed',String(compressed))}catch{}
};
try{
 if(localStorage.getItem('sayuri.sidebar.collapsed')==='true'&&!narrow())
  document.body.classList.add('sidebar-collapsed');
}catch{}
el('collapseSidebar').onclick=collapse;
el('menu').setAttribute('aria-expanded','false');
el('menu').setAttribute('aria-controls','sayuriSidebar');
el('menu').onclick=()=>document.body.classList.contains('open')?closeDrawer():openDrawer();
el('drawerBackdrop').addEventListener('click',closeDrawer);
window.addEventListener('keydown',e=>{
 if(e.key==='Escape'&&narrow()&&document.body.classList.contains('open')){
  e.preventDefault();closeDrawer();return;
 }
 if(e.key!=='Tab'||!narrow()||!document.body.classList.contains('open'))return;
 const controls=nodes();if(!controls.length)return;
 const first=controls[0],lastItem=controls[controls.length-1];
 if(e.shiftKey&&(document.activeElement===first||!el('sayuriSidebar').contains(document.activeElement))){
  e.preventDefault();lastItem.focus();
 }else if(!e.shiftKey&&document.activeElement===lastItem){
  e.preventDefault();first.focus();
 }
});
window.addEventListener('resize',()=>{
 if(!narrow())closeDrawer();
 else document.body.classList.remove('sidebar-collapsed');
});
const navIds={
 account:'showAccount',chat:'showChat',work:'showWork',files:'showFiles',
 home:'showHome',updates:'showUpdates'
};
function markNav(id){
 selected=id;
 for(const [view,buttonId] of Object.entries(navIds)){
  const btn=el(buttonId);
  btn.classList.toggle('current',view===id);
  if(view===id)btn.setAttribute('aria-current','page');
  else btn.removeAttribute('aria-current');
 }
 if(narrow())closeDrawer();
}
for(const [id,button] of Object.entries(navIds)){
 el(button).addEventListener('click',()=>markNav(id));
}
markNav('account');
el('sayuriSidebar').querySelectorAll('.diagnostic').forEach(details=>{
 details.addEventListener('toggle',()=>{
  details.querySelector('summary').setAttribute('aria-expanded',String(details.open));
  if(details.open&&document.body.classList.contains('sidebar-collapsed')&&!narrow()){
   document.body.classList.remove('sidebar-collapsed');
   el('collapseSidebar').setAttribute('aria-expanded','true');
   try{localStorage.setItem('sayuri.sidebar.collapsed','false')}catch{}
  }
 });
});
function stamp(date){
 if(!date)return 'Нет данных';
 const d=new Date(date);
 return isNaN(d.getTime())?'Нет данных':d.toLocaleString('ru-RU');
}
function fmt(ms){return Number.isFinite(ms)?ms+' мс':'Нет измерения'}
function addRow(target,label,val){
 const div=document.createElement('div');div.className='status-row';
 const key=document.createElement('span');key.className='status-key';key.textContent=label;
 const value=document.createElement('span');value.className='status-value';value.textContent=val??'Нет данных';
 div.append(key,value);target.append(div);
}
function statusDot(id,tone){
 el(id).dataset.tone=tone||'neutral';
}
function stale(){
 lastPayload=null;
 el('profileActivity').textContent='Нет свежих данных';
 el('sayuriStatusCompact').textContent='Нет свежих данных';
 el('networkCompact').textContent='Нет связи с backend';
 el('cloudCompact').textContent='Нет свежих данных';
 statusDot('sayuriStatusSymbol','error');
 statusDot('networkStatusSymbol','error');
 statusDot('cloudStatusSymbol','neutral');
 el('sayuriStatusDetail').textContent='Телеметрия недоступна или устарела';
}
function render(payload){
 if(!payload||payload.event!=='runtime_status')return;
 const eventTime=Date.parse(payload.ts);
 if(!Number.isFinite(eventTime)||Math.abs(Date.now()-eventTime)>65_000){stale();return}
 last=Date.now();lastPayload=payload;
 const s=payload.sayuri||{},n=payload.network||{},c=payload.cloud_ru||{};
 const state=validStates.has(s.state)?s.state:'disconnected';
 const label=labels[state];
 el('profileActivity').textContent=label;
 el('sayuriStatusCompact').textContent=label+(s.active_jobs?' · '+s.active_jobs+' задач':'');
 el('sayuriStatusDetail').textContent=s.description||'Подробности отсутствуют';
 statusDot('sayuriStatusSymbol',tones[state]);
 el('sayuriActiveJobs').textContent=(s.active_jobs||0)>0?
    String(s.active_jobs)+' выполняется · '+(s.description||'Без описания'):'Нет активных задач';
 const events=el('sayuriRecentEvents');events.replaceChildren();
 for(const item of payload.recent_events||[]){
  if(!validStates.has(item.state))continue;
  const row=document.createElement('div');row.className='status-event';
  row.textContent=(labels[item.state]||item.state)+' · '+stamp(item.ts)+
    (item.description?' · '+item.description:'');
  events.append(row);
 }
 if(!events.childNodes.length)events.textContent='Событий пока нет';
 const available=el('sayuriAvailableStates');
 available.replaceChildren();
 // Names are a glossary, not twelve fictitious active processes.
 for(const name of Object.keys(labels)){
  const item=document.createElement('span');item.className='status-pill';
  item.textContent=labels[name];
  item.title='Возможное состояние, показывается как активное только при фактическом событии';
  available.append(item);
 }
 const netState=netLabels[n.state]||'Нет свежих данных';
 el('networkCompact').textContent=n.backend==='online'?
   ('Сервер работает · '+netState):'Сервер недоступен';
 statusDot('networkStatusSymbol',n.backend!=='online'?'error':
    n.state==='online'?'good':n.state==='degraded'?'warning':n.state==='offline'?'error':'neutral');
 const netBody=el('networkDetailsBody');netBody.replaceChildren();
 addRow(netBody,'Внешняя сеть',netState);
 addRow(netBody,'Backend',n.backend==='online'?'Доступен':'Нет связи');
 addRow(netBody,'Отклик сервера',fmt(n.server_latency_ms));
 addRow(netBody,'Проверка GitHub',fmt(n.latency_ms));
 addRow(netBody,'Успешно',stamp(n.last_success_at));
 addRow(netBody,'Ошибка',n.failure_reason||'Нет');
 addRow(netBody,'Цель проверки',n.probe_target||'Нет данных');
 addRow(netBody,'Соединение',transportState==='connected'?'SSE · поток активен':
  transportState==='polling'?'REST · резервный опрос':
  transportState==='reconnecting'?'Повторное подключение':'Проверка');
 const cstate=cloudLabels[c.state]||cloudLabels.unknown;
 el('cloudCompact').textContent=cstate;
 statusDot('cloudStatusSymbol',c.state==='connected'?'good':
  ['rate_limited','degraded','timeout'].includes(c.state)?'warning':
  ['auth_error','insufficient_balance','unreachable'].includes(c.state)?'error':'neutral');
 const cloudBody=el('cloudDetailsBody');cloudBody.replaceChildren();
 addRow(cloudBody,'Состояние',cstate);
 addRow(cloudBody,'Модель',c.model_id||'Не выбрана');
 addRow(cloudBody,'Задержка',fmt(c.latency_ms));
 addRow(cloudBody,'Запросы',Number.isFinite(c.requests_count)?String(c.requests_count):'Нет данных');
 addRow(cloudBody,'Активно',Number.isFinite(c.active_requests)?String(c.active_requests):'Нет данных');
 addRow(cloudBody,'HTTP',Number.isInteger(c.last_http_status)?String(c.last_http_status):'Нет данных');
 addRow(cloudBody,'Последняя связь',stamp(c.last_success_at));
 addRow(cloudBody,'Ошибка',c.last_error||'Нет');
 if(c.token_usage&&typeof c.token_usage==='object'){
  addRow(cloudBody,'Токены',Object.entries(c.token_usage).map(([k,v])=>k+': '+v).join(', ')||'Нет данных');
 }else addRow(cloudBody,'Токены','Нет данных');
 addRow(cloudBody,'Стоимость','Нет подтверждённого расчёта');
}
function authToken(){return sessionStorage.getItem('sayuri_token')||''}
function schedulePoll(){
 if(polling||stopped)return;
 polling=setInterval(async()=>{
  if(last&&Date.now()-last<40000)return;
  await pollOnce();
 },20000);
 pollOnce();
}
async function pollOnce(){
 const t=authToken();if(!t)return;
 try{
  const response=await fetch('/api/runtime/status',{
   headers:{Authorization:'Bearer '+t},cache:'no-store'
  });
  if(!response.ok)throw Error('HTTP '+response.status);
  transportState=transportState==='connected'?'connected':'polling';
  render(await response.json());
 }catch{if(!last||Date.now()-last>65000)stale()}
}
async function stream(){
 const t=authToken();if(!t||stopped)return;
 aborter=new AbortController();
 const response=await fetch('/api/runtime/events',{
  headers:{Authorization:'Bearer '+t,Accept:'text/event-stream'},
  cache:'no-store',signal:aborter.signal
 });
 if(!response.ok||!response.body)throw Error('SSE unavailable');
 failed=0;
 if(polling){clearInterval(polling);polling=null}
 const streamReader=response.body.getReader();
 reader=streamReader;const decoder=new TextDecoder();
 let buffer='';
 while(!stopped){
  const {value,done}=await streamReader.read();if(done)break;
  buffer+=decoder.decode(value,{stream:true});
  while(buffer.includes('\n\n')){
   const i=buffer.indexOf('\n\n'),block=buffer.slice(0,i);
   buffer=buffer.slice(i+2);
   const line=block.split('\n').find(row=>row.startsWith('data: '));
   if(line)try{transportState='connected';render(JSON.parse(line.slice(6)))}catch{}
  }
  if(buffer.length>100000)buffer='';
 }
 throw Error('SSE disconnected');
}
async function connect(){
 if(stopped)return;
 try{
  await stream();
 }catch{
  if(stopped)return;
  failed++;
  transportState='reconnecting';
  schedulePoll();
  const wait=Math.min(30000,1000*Math.pow(2,Math.min(failed,5)))+Math.random()*800;
  setTimeout(connect,wait);
 }
}
async function startup(){
 if(stopped)return;
 const newToken=authToken();
 if(!newToken){setTimeout(startup,400);return}
 if(newToken===currentToken)return;
 currentToken=newToken;
 await pollOnce();
 connect();
}
stale();
startup();
staleTimer=setInterval(()=>{if(last&&Date.now()-last>65000)stale()},12000);
window.addEventListener('beforeunload',()=>{
 stopped=true;
 if(aborter)aborter.abort();
 if(reader)reader.cancel().catch(()=>{});
 if(polling)clearInterval(polling);
 if(staleTimer)clearInterval(staleTimer);
});
})();
