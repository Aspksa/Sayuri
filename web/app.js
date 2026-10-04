const $=s=>document.querySelector(s);let token=sessionStorage.getItem('sayuri_token')||'',chats=[],active=null,busy=false,activeProjectMemoryId=null,memorySearchTimer=null;
async function api(path,method='GET',data=null){const opts={method,headers:{}};if(token)opts.headers.Authorization='Bearer '+token;if(data!==null){if(data instanceof FormData)opts.body=data;else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data)}}const r=await fetch('/api'+path,opts);let result;try{result=await r.json()}catch{result={}}if(!r.ok){const message=Array.isArray(result.detail)?result.detail.map(x=>x.msg||x.type).join('; '):result.detail;throw Error(message||'Ошибка '+r.status)}return result}
function fail(e){$('#error').textContent=e.message||String(e)}
function view(id){
  for(const x of document.querySelectorAll('.view'))x.classList.toggle('active',x.id===id+'View');
  $('#title').textContent=({account:'Личный кабинет Sayuri',beyond:'SAYURI BEYOND',files:'Документы',work:'Рабочие проекты',home:'Домашние проекты',updates:'Обновление проекта',chat:'Единый чат'})[id]||'Sayuri';
  if(id==='account')account();
  if(id==='updates')loadBuildInfo();
  if(id==='files'){files();loadDrive();requestAnimationFrame(()=>setDocumentsViewMode(localStorage.getItem('sayuri_documents_view')||'grid'))}
  if(id==='work'||id==='home')showProject(id);
  window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'route_changed',module:id}}));
}
async function refresh(){
  chats=await api('/chats');
  // Preserve existing records, but only the one mentor conversation is visible.
  const mentor=chats.filter(c=>c.kind==='teacher').sort((a,b)=>a.created-b.created)[0];
  if(mentor){active=mentor.id}else{
    const created=await api('/chats','POST',{title:'Общий чат',kind:'teacher'});
    active=created.id;chats.unshift({...created,kind:'teacher'});
  }
  if($('#chatView').classList.contains('active'))$('#title').textContent='Саюри · общий чат';
  await messages();
  const state=await api('/health');
  $('#cloud').textContent=state.mentor_configured?'Cloud.ru: проверка состояния…':'Cloud.ru: не настроено';
}
async function messages(){const box=$('#messages');box.replaceChildren();if(!active){box.textContent='Общий чат загружается…';return}for(const m of await api('/chats/'+active+'/messages')){const div=document.createElement('div');div.className='bubble '+m.role;const small=document.createElement('small');small.textContent=m.role==='user'?'Вы':'Наставник · Sayuri наблюдает';const text=document.createElement('div');text.textContent=m.text;div.append(small,text);if(m.role==='assistant'){for(const [symbol,score] of [['👍',1],['👎',-1]]){const b=document.createElement('button');b.textContent=symbol;b.onclick=async()=>{try{await api('/feedback','POST',{message_id:m.id,rating:score});b.disabled=true}catch(e){fail(e)}};div.append(b)}}box.append(div)}box.scrollTop=box.scrollHeight}
async function send(e){e.preventDefault();if(busy)return;const text=$('#draft').value.trim();if(!text)return;busy=true;$('#send').disabled=true;$('#error').textContent='Наставник отвечает; Sayuri изучает диалог…';try{if(!active)await refresh();const payload={text};if(activeProjectMemoryId)payload.project_id=activeProjectMemoryId;await api('/chats/'+active+'/send','POST',payload);$('#draft').value='';await refresh();$('#error').textContent=''}catch(e){fail(e)}finally{busy=false;$('#send').disabled=false}}
async function account(){
 loadCloudSettings();loadPreferences();drawCandidates();loadDevelopment();loadMemory3();loadMemoryProjectOptions();
 try{
  const [p,stats]=await Promise.all([api('/persona'),api('/learning/stats')]);
  $('#persona').textContent=p.name+' · v'+p.version+' · '+p.sections+' разделов · '+p.dialogues+' диалогов ('+p.messages+' сообщений) · '+p.phrases+' реплик / '+p.categories+' категорий · '+p.chapters+' глав легенды · '+p.rituals+' ритуалов · '+p.rules+' правил · '+p.scenarios+' проверок. Режимы: '+p.modes.join(', ');
  $('#stats').textContent='Чаты: '+stats.chats+' · Память: '+stats.memories+' · Отзывы: '+stats.feedback+' · Файлы: '+stats.documents;
 }catch(e){fail(e)}
}
const memoryScopeLabels={personal:'Личная',project:'Проектная',working:'Рабочая',temporary:'Временная'};
const memoryTypeLabels={fact:'Факт',preference:'Предпочтение',decision:'Решение',rule:'Правило',correction:'Исправление',note:'Заметка'};

function syncMemoryForm(){
 const scope=$('#memoryScope').value;
 $('#memoryProjectField').hidden=scope!=='project';
 $('#memoryTtlField').hidden=scope!=='temporary';
 if(scope==='project'&&activeProjectMemoryId&&!$('#memoryProject').value)$('#memoryProject').value=activeProjectMemoryId;
 updateMemoryActiveProject();
}
function updateMemoryActiveProject(){
 const node=$('#memoryActiveProject');if(!node)return;
 node.textContent=activeProjectMemoryId?'Активный проект: '+activeProjectMemoryId:'Активный проект: не выбран';
 node.classList.toggle('active',Boolean(activeProjectMemoryId));
}
async function loadMemoryProjectOptions(){
 const list=$('#memoryProjectList');if(!list)return;
 try{
  const root=await api('/projects'),ids=new Set();
  for(const category of root.categories||[]){
   if(category.memory_project_id)ids.add(category.memory_project_id);
   if(!category.available)continue;
   try{
    const data=await api('/projects/'+category.id+'/list');
    for(const item of data.items||[])if(item.is_dir&&item.memory_project_id)ids.add(item.memory_project_id);
   }catch{}
  }
  list.replaceChildren();
  for(const id of [...ids].sort()){
   const option=document.createElement('option');option.value=id;list.append(option);
  }
 }catch{}
}
function memoryQuery(){
 const params=new URLSearchParams();
 const scope=$('#memoryScopeFilter').value,status=$('#memoryStatusFilter').value,q=$('#memorySearch').value.trim();
 if(scope)params.set('scope',scope);
 if(status)params.set('status',status);
 if(q)params.set('q',q);
 params.set('limit','250');
 return '/memory?'+params.toString();
}
function memoryMetaText(item){
 const parts=[memoryScopeLabels[item.scope]||item.scope,memoryTypeLabels[item.memory_type]||item.memory_type,'P'+item.priority];
 if(item.project_id)parts.push(item.project_id);
 if(item.expires){
  const left=item.expires-Math.floor(Date.now()/1000);
  parts.push(left>0?'истекает через '+Math.max(1,Math.ceil(left/3600))+' ч':'срок истёк');
 }
 if(item.source)parts.push(item.source);
 return parts.join(' · ');
}
async function loadMemory3(){
 const box=$('#memories'),summaryBox=$('#memorySummary');if(!box||!summaryBox)return;
 try{
  const [summary,items]=await Promise.all([api('/memory/summary'),api(memoryQuery())]);
  summaryBox.replaceChildren();
  const values=[
   ['Активные',summary.active],['Личные',summary.by_scope.personal],
   ['Проектные',summary.by_scope.project],['Рабочие',summary.by_scope.working],
   ['Временные',summary.by_scope.temporary],['Проекты',summary.projects],['Архив',summary.archived]
  ];
  for(const pair of values)summaryBox.append(metric(pair[0],pair[1]));
  box.replaceChildren();
  if(!items.length){box.textContent='Записей с такими фильтрами нет.';return}
  for(const item of items){
   const card=document.createElement('article');card.className='memory3-card';
   card.dataset.scope=item.scope;card.dataset.priority=String(item.priority);
   const top=document.createElement('div');top.className='memory3-card-top';
   const badges=document.createElement('div');badges.className='memory3-badges';
   const scope=document.createElement('span');scope.textContent=memoryScopeLabels[item.scope]||item.scope;
   const type=document.createElement('span');type.textContent=memoryTypeLabels[item.memory_type]||item.memory_type;
   const priority=document.createElement('span');priority.textContent='P'+item.priority;
   badges.append(scope,type,priority);
   const confidence=document.createElement('small');confidence.textContent=Math.round((item.confidence??1)*100)+'%';
   top.append(badges,confidence);
   const text=document.createElement('p');text.className='memory3-card-text';text.textContent=item.text;
   const meta=document.createElement('small');meta.className='memory3-card-meta';meta.textContent=memoryMetaText(item);
   const actions=document.createElement('div');actions.className='memory3-card-actions';
   if(item.status==='active'){
    const archive=document.createElement('button');archive.type='button';archive.textContent='В архив';
    archive.onclick=async()=>{try{await api('/memory/'+item.id+'/archive','POST');await loadMemory3();await loadDevelopment()}catch(e){fail(e)}};
    actions.append(archive);
   }
   const del=document.createElement('button');del.type='button';del.textContent='Удалить';del.className='danger';
   del.onclick=async()=>{
    if(!confirm('Удалить эту запись памяти без возможности восстановления?'))return;
    try{await api('/memory/'+item.id,'DELETE');await loadMemory3();await loadDevelopment()}catch(e){fail(e)}
   };
   actions.append(del);
   card.append(top,text,meta,actions);box.append(card);
  }
 }catch(e){box.textContent='Memory 3.0 недоступна: '+e.message}
}
function openProjectMemory(projectId){
 activeProjectMemoryId=projectId||activeProjectMemoryId;
 view('account');
 requestAnimationFrame(()=>{
  $('#memoryScope').value='project';$('#memoryProject').value=activeProjectMemoryId||'';
  syncMemoryForm();
  $('#memoryBlock').scrollIntoView({behavior:'smooth',block:'start'});
  $('#fact').focus();
 });
}

async function files(){try{const list=await api('/documents');const box=$('#files');box.replaceChildren();for(const f of list){
  const row=document.createElement('div');row.className='line';
  row.dataset.sayuriEntityType='document';row.dataset.sayuriEntityId=f.name;row.dataset.sayuriModule='files';
  const name=document.createElement('span');name.textContent='📎 '+f.name;
  const del=document.createElement('button');del.textContent='Удалить';
  del.onclick=async()=>{
    if(!confirm('Удалить этот файл из Sayuri?'))return;
    try{await api('/documents/'+f.id,'DELETE');await files()}catch(e){fail(e)}
  };
  row.append(name,del);box.append(row)
}}catch(e){fail(e)}}


async function showProject(category,relative=''){
  const target=$(category==='work'?'#workBrowser':'#homeBrowser');
  target.replaceChildren();
  try{
    const root=await api('/projects');
    const actual=root.categories.find(x=>x.id===category);
    if(!actual||!actual.available){target.textContent='Папка проекта недоступна';return}
    const location=document.createElement('p');location.className='hint';
    location.textContent='Путь: '+root.root+' / '+actual.name;
    target.append(location);
    if(relative){
      const back=document.createElement('button');
      back.textContent='← Назад';
      const path=relative.split('/').slice(0,-1).join('/');
      back.onclick=()=>showProject(category,path);
      target.append(back);
    }
    const data=await api('/projects/'+category+'/list?path='+encodeURIComponent(relative));
    activeProjectMemoryId=data.memory_project_id||actual.memory_project_id||null;
    updateMemoryActiveProject();
    const memoryBar=document.createElement('div');memoryBar.className='project-memory-bar';
    const memoryText=document.createElement('span');memoryText.textContent='Memory 3.0 · '+(activeProjectMemoryId||'контекст не определён');
    const memoryButton=document.createElement('button');memoryButton.type='button';memoryButton.textContent='Память проекта';
    memoryButton.disabled=!activeProjectMemoryId;memoryButton.onclick=()=>openProjectMemory(activeProjectMemoryId);
    memoryBar.append(memoryText,memoryButton);target.append(memoryBar);
    if(!data.items.length){
      const empty=document.createElement('p');empty.textContent='Папка пуста.';
      target.append(empty);
    }
    for(const item of data.items){
      const btn=document.createElement('button');
      btn.style.display='block';btn.style.textAlign='left';btn.style.margin='7px 0';btn.style.width='100%';
      btn.textContent=(item.is_dir?'📁 ':'📄 ')+item.name;
      btn.dataset.sayuriEntityType=item.is_dir?'project':'file';
      btn.dataset.sayuriEntityId=item.relative;
      btn.dataset.sayuriModule=category;
      if(item.is_dir)btn.onclick=()=>{
        window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{
          type:'project_opened',module:category,entity_type:'project',entity_id:item.relative}}));
        showProject(category,item.relative);
      };
      else btn.onclick=()=>projectDownload(category,item.relative,item.name);
      target.append(btn);
    }
  }catch(e){const warning=document.createElement('p');warning.textContent=e.message;target.append(warning)}
}
async function projectDownload(category,path,name){
  window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'document_opened',module:category,entity_type:'file',entity_id:path}}));
  try{
    const url='/api/projects/'+category+'/file?path='+encodeURIComponent(path);
    const res=await fetch(url,{headers:{Authorization:'Bearer '+token}});
    if(!res.ok)throw Error('Ошибка загрузки: '+res.status);
    const blob=await res.blob();const urlObject=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=urlObject;a.download=name;a.click();
    setTimeout(()=>URL.revokeObjectURL(urlObject),1000);
  }catch(e){fail(e)}
}


async function drawCandidates(){
  const box=$('#suggestions');box.replaceChildren();
  try{
    const candidates=await api('/learning/candidates');
    if(!candidates.length){box.textContent='Пока нет предложений для подтверждения.';return}
    for(const c of candidates){
      const row=document.createElement('div');row.className='line';
      const text=document.createElement('span');text.textContent=c.text;
      const approve=document.createElement('button');approve.textContent='Запомнить';
      approve.onclick=async()=>{
        try{await api('/learning/candidates/'+c.id+'/approve','POST');await drawCandidates();await account()}
        catch(e){fail(e)}
      };
      const reject=document.createElement('button');reject.textContent='Отклонить';
      reject.onclick=async()=>{
        try{await api('/learning/candidates/'+c.id+'/reject','POST');await drawCandidates()}
        catch(e){fail(e)}
      };
      row.append(text,approve,reject);box.append(row);
    }
  }catch(e){box.textContent=e.message}
}
$('#reviewChat').onclick=async()=>{
  const box=$('#suggestions');
  if(!active){box.textContent='Сначала выберите диалог.';return}
  box.textContent='ИИ-наставник анализирует выбранный чат…';
  try{await api('/learning/analyze/'+active,'POST');await drawCandidates()}
  catch(e){box.textContent=e.message}
};
$('#datasetPreview').onclick=async()=>{
  try{const r=await api('/learning/dataset');$('#datasetStats').textContent='Примеров: '+r.samples.length+'. Перед обучением нужна проверка и согласие.'}
  catch(e){fail(e)}
};

$('#showBeyond').onclick=()=>view('beyond');
$('#accountOpenBeyond').onclick=()=>view('beyond');
$('#accountOpenUpdates').onclick=()=>view('updates');
$('#updatesBackCabinet').onclick=()=>view('account');
$('#beyondBackAccount').onclick=()=>view('account');
$('#showUpdates').onclick=()=>view('updates');$('#showChat').onclick=()=>view('chat');$('#showWork').onclick=()=>view('work');$('#showHome').onclick=()=>view('home');$('#showAccount').onclick=()=>view('account');$('#showFiles').onclick=()=>view('files');
function setDocumentsViewMode(mode){
  const normalized=mode==='list'?'list':'grid';
  const grid=$('#driveFiles');
  if(grid)grid.classList.toggle('drive-list-mode',normalized==='list');
  $('#docsGridView')?.setAttribute('aria-pressed',String(normalized==='grid'));
  $('#docsListView')?.setAttribute('aria-pressed',String(normalized==='list'));
  localStorage.setItem('sayuri_documents_view',normalized);
}
$('#docsGridView').onclick=()=>setDocumentsViewMode('grid');
$('#docsListView').onclick=()=>setDocumentsViewMode('list');
$('#docsOpenWork').onclick=()=>view('work');
$('#docsOpenHome').onclick=()=>view('home');
$('#docsOpenLibrary').onclick=()=>$('#documentsLibrary').scrollIntoView({behavior:'smooth',block:'start'});
$('#composer').onsubmit=send;$('#draft').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#composer').requestSubmit()}};

$('#memoryScope').onchange=syncMemoryForm;
$('#memoryScopeFilter').onchange=loadMemory3;
$('#memoryStatusFilter').onchange=loadMemory3;
$('#memorySearch').oninput=()=>{clearTimeout(memorySearchTimer);memorySearchTimer=setTimeout(loadMemory3,220)};
$('#memoryForm').onsubmit=async e=>{
 e.preventDefault();
 const scope=$('#memoryScope').value,project=$('#memoryProject').value.trim();
 const payload={
  text:$('#fact').value.trim(),scope,memory_type:$('#memoryType').value,
  priority:Number($('#memoryPriority').value),confidence:1
 };
 if(!payload.text)return;
 if(scope==='project'){
  payload.project_id=project||activeProjectMemoryId;
  if(!payload.project_id){$('#memoryFormStatus').textContent='Выберите проект для проектной памяти.';return}
 }
 if(scope==='temporary'){
  const hours=Math.max(1,Math.min(720,Number($('#memoryTtlHours').value)||24));
  payload.ttl_minutes=Math.round(hours*60);
 }
 $('#memoryFormStatus').textContent='Сохраняю…';
 try{
  await api('/memory','POST',payload);
  $('#fact').value='';$('#memoryFormStatus').textContent='Сохранено в Memory 3.0';
  await loadMemory3();await loadDevelopment();
  window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'memory_updated',module:'account',entity_type:'memory',entity_id:scope}}));
 }catch(x){$('#memoryFormStatus').textContent=x.message}
};
syncMemoryForm();
$('#fileForm').onsubmit=async e=>{e.preventDefault();const f=$('#file').files[0];if(!f)return;const form=new FormData();form.append('file',f);try{await api('/documents','POST',form);window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'document_uploaded',module:'files',entity_type:'document',entity_id:f.name}}));$('#file').value='';files()}catch(x){fail(x)}};
async function bootstrapLocal() {
  $('#cloud').textContent='Подключение локальной сессии…';
  try {
    // Local-only endpoint never sends a password or Cloud.ru key to the browser.
    const authResponse=await api('/auth/local','POST');
    token=authResponse.token;
    sessionStorage.setItem('sayuri_token',token);
    await refresh();
    // Preserve a section selected while the initial local session was loading.
    const visible=document.querySelector('.view.active');
    view(visible?.id?.endsWith('View')?visible.id.slice(0,-4):'account');
  } catch(e) {
    $('#cloud').textContent='Локальный доступ недоступен';
    fail(e);
  }
}
bootstrapLocal();;

if ('serviceWorker' in navigator && location.protocol!=='file:') {window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}))}

$('#cloudModels').onclick=async()=>{
  const target=$('#cloudModelList');
  target.textContent='Получаем список моделей…';
  try{
    const data=await api('/cloud/models');
    target.replaceChildren();
    if(!data.models.length){target.textContent='Доступных моделей не найдено.';return}
    for(const id of data.models){
      const row=document.createElement('div');row.className='line';
      const name=document.createElement('span');name.textContent=id;
      row.append(name);target.append(row);
    }
  }catch(e){target.textContent=e.message}
};

async function loadPreferences(){
  try{
    const r=await api('/preferences');
    $('#mode').value=r.mode;
    $('#intimacy').value=r.intimacy;
  }catch(e){$('#styleStatus').textContent=e.message}
}
$('#saveStyle').onclick=async()=>{
  const mode=$('#mode').value,intimacy=$('#intimacy').value;
  try{
    await api('/preferences','PUT',{mode,intimacy});
    $('#styleStatus').textContent=' Стиль сохранён';
  }catch(e){$('#styleStatus').textContent=e.message}
};

async function loadCloudSettings(){
  try{
    const c=await api('/cloud/config');
    $('#cloudSetupTitle').textContent=c.status;
    $('#mentorModel').value=c.mentor_model||'';
    $('#sayuriModel').value=c.sayuri_model||'';
    $('#cloudSaveStatus').textContent=c.key_configured?'API-ключ сохранён на сервере. Значение скрыто.':'Ключ ещё не введён.';
  }catch(e){
    $('#cloudSaveStatus').textContent=e.message;
  }
}
$('#saveCloud').onclick=async()=>{
  const key=$('#cloudKey').value.trim();
  $('#cloudSaveStatus').textContent='Сохраняем в закрытый .env…';
  try{
    const result=await api('/cloud/config','PUT',{
      api_key:key||null,
      mentor_model:$('#mentorModel').value,
      sayuri_model:$('#sayuriModel').value
    });
    $('#cloudKey').value='';
    $('#cloudSaveStatus').textContent=result.status+'. Ключ не отображается.';
    await loadCloudSettings();
    const h=await api('/health');
    $('#cloud').textContent=h.mentor_configured?'Cloud.ru: проверка состояния…':'Cloud.ru: не настроено';
  }catch(e){$('#cloudSaveStatus').textContent=e.message}
};
$('#testCloud').onclick=async()=>{
  $('#cloudSaveStatus').textContent='Проверяем доступ Cloud.ru и список моделей…';
  try{
    const data=await api('/cloud/models');
    const list=$('#availableCloudModels');list.replaceChildren();
    for(const id of data.models){
      const opt=document.createElement('option');opt.value=id;list.append(opt);
    }
    const target=$('#mentorModel').value.trim();
    const match=target && data.models.includes(target);
    $('#cloudSaveStatus').textContent='Cloud.ru доступен: '+data.models.length+' моделей. '+
      (target?(match?'Модель наставника найдена.':'Указанная модель наставника не найдена: проверьте её точный ID.'):'Выберите ID наставника из доступных моделей.');
  }catch(e){$('#cloudSaveStatus').textContent='Подключение не подтверждено: '+e.message}
};


/* The character is expressive artwork, not an AI emotional measurement. */
let voiceEnabled=false,quietMotion=false,driveCurrent='',driveTimer=null,driveMenuItem=null;
const sayuriGreetings=[
  {line:'Господин, рада снова вас видеть. К чему приступим сегодня?',expression:'✿ приветливая улыбка'},
  {line:'Все записи на своих местах, Господин. Я готова учиться дальше.',expression:'✧ внимательный взгляд'},
  {line:'Ваша кицунэ на посту. Может, сегодня откроем что-нибудь интересное?',expression:'❀ игривое настроение'},
  {line:'Буду бережно хранить наши решения и не торопиться с выводами, Господин.',expression:'☾ спокойствие'}
];
let greetingIndex=0;
function expressSayuri(index){
 const item=sayuriGreetings[index % sayuriGreetings.length];
 $('#characterGreeting').textContent=item.line;
 $('#characterExpression').textContent=item.expression;
 if(voiceEnabled && 'speechSynthesis' in window){
  window.speechSynthesis.cancel();
  const msg=new SpeechSynthesisUtterance(item.line);msg.lang='ru-RU';msg.rate=.92;msg.pitch=1.06;
  window.speechSynthesis.speak(msg);
 }
}
$('#goChat').onclick=()=>view('chat');
$('#greetSayuri').onclick=()=>{greetingIndex++;expressSayuri(greetingIndex)};
$('#characterStage').onclick=()=>{greetingIndex++;expressSayuri(greetingIndex)};
$('#speechToggle').onclick=()=>{
 if(!('speechSynthesis' in window)){$('#speechToggle').textContent='Голос в браузере недоступен';return}
 voiceEnabled=!voiceEnabled;
 if(!voiceEnabled)window.speechSynthesis.cancel();
 $('#speechToggle').textContent=voiceEnabled?'♫ Голос включён':'♫ Голос выключен';
 $('#speechToggle').setAttribute('aria-pressed',String(voiceEnabled));
};
$('#reduceMotion').onclick=()=>{
 quietMotion=!quietMotion;document.body.classList.toggle('reduce-motion',quietMotion);
 $('#reduceMotion').textContent=quietMotion?'◌ Анимации выключены':'◌ Без анимации';
 $('#reduceMotion').setAttribute('aria-pressed',String(quietMotion));
};
document.querySelectorAll('[data-jump]').forEach(btn=>btn.onclick=()=>{
 document.getElementById(btn.dataset.jump)?.scrollIntoView({behavior:'smooth',block:'start'});
});
const metric=(label,value)=>{
 const box=document.createElement('div');box.className='metric';
 const strong=document.createElement('strong');strong.textContent=String(value);
 const name=document.createElement('span');name.textContent=label;
 box.append(strong,name);return box;
};
async function loadDevelopment(){
 const skill=$('#skillSummary'),experience=$('#experienceSummary'),history=$('#developmentHistory');
 try{
  const [data,persona,memory,documents]=await Promise.all([api('/development/summary'),api('/persona'),api('/memory'),api('/documents')]);
  const n=data.counts;
  skill.replaceChildren();
  for(const [label,value] of [['Правила характера',persona.rules],['Контрольные сценарии (описаны)',persona.scenarios],['Оценки реальных ответов',n.feedback],['Проверенные навыки','Ещё не измерены']])skill.append(metric(label,value));
  experience.replaceChildren();
  for(const [label,value] of [['Сообщения',n.messages],['Диалоги',n.chats],['Знания',n.memories],['Документы',n.documents],['Предложения на проверке',n.memory_candidates]])experience.append(metric(label,value));
  $('#experienceJournal').textContent='Опыт собирается из фактической истории сообщений, исправлений и подтверждённой памяти. Автоматическая оценка способностей пока не проводилась.';
  const library=$('#knowledgeLibrary');
  const drawLibrary=()=>{
   const q=$('#knowledgeSearch').value.trim().toLowerCase();
   library.replaceChildren();
   const chapters=document.createElement('div');chapters.className='journal-entry';
   chapters.textContent='Библиотека персонажа: '+persona.dialogues+' учебных диалогов, '+persona.phrases+' реплик, '+persona.chapters+' глав легенды, '+persona.rituals+' ритуалов.';
   if(!q||chapters.textContent.toLowerCase().includes(q))library.append(chapters);
   const extra=[
     ...(persona.lore_titles||[]).map((title,i)=>({label:'Глава '+(i+1)+': '+title,source:'Легенда · профиль 2.0'})),
     ...(persona.ritual_titles||[]).map((title,i)=>({label:'Ритуал '+(i+1)+': '+title,source:'Ритуалы · профиль 2.0'})),
     ...documents.map(d=>({label:d.name,source:'Загруженный документ · ещё не индексирован'}))
   ];
   for(const item of extra.filter(x=>x.label.toLowerCase().includes(q))){
     const entry=document.createElement('div');entry.className='journal-entry';entry.textContent=item.label;
     const subtitle=document.createElement('small');subtitle.textContent=item.source;
     entry.append(subtitle);library.append(entry);
   }
   const relevant=memory.filter(m=>m.text.toLowerCase().includes(q));
   for(const m of relevant){
    const entry=document.createElement('div');entry.className='journal-entry';
    entry.textContent=m.text;
    const memoryScopeLabels={personal:'Личная',project:'Проектная',working:'Рабочая',temporary:'Временная'};
    const small=document.createElement('small');small.textContent=(memoryScopeLabels[m.scope]||m.scope)+' память · '+(m.memory_type||'fact')+' · '+(m.source||'подтверждено');
    entry.append(small);library.append(entry);
   }
   if(!library.childElementCount)library.textContent='Совпадений нет.';
  };
  $('#knowledgeSearch').oninput=drawLibrary;drawLibrary();
  history.replaceChildren();
  if(!data.history.length)history.textContent='События развития пока не записаны.';
  for(const event of data.history){
   const row=document.createElement('div');row.className='journal-entry';
   const date=new Date(event.at*1000).toLocaleString('ru-RU');
   row.textContent=event.kind+' · '+date;history.append(row);
  }
 }catch(e){history.textContent='Не удалось загрузить историю развития: '+e.message}
}
function driveRelativeParent(path){return path.split('/').slice(0,-1).join('/')}
const folderIcons={folder:'📁',book:'📚',project:'🗂️',archive:'🗄️',research:'🔬',personal:'🏠',star:'★'};
function normalizeFolderMeta(meta,path=''){
 const value=meta&&typeof meta==='object'?meta:{};
 return {
  path:value.path||path,icon:folderIcons[value.icon]?value.icon:'folder',
  color:['violet','rose','blue','cyan','green','amber','slate'].includes(value.color)?value.color:'violet',
  description:typeof value.description==='string'?value.description:''
 };
}
function folderIcon(meta){return folderIcons[normalizeFolderMeta(meta).icon]}
function applyFolderIdentity(node,meta){
 const value=normalizeFolderMeta(meta);
 node.dataset.folderColor=value.color;
 node.style.setProperty('--folder-accent','var(--folder-'+value.color+')');
 return value;
}

function loadDrivePins(){
 try{return JSON.parse(localStorage.getItem('sayuri_document_pins')||'[]').filter(x=>x&&typeof x.path==='string')}
 catch{return []}
}
function saveDrivePins(pins){localStorage.setItem('sayuri_document_pins',JSON.stringify(pins.slice(0,30)));renderDrivePins()}
function updateDrivePinsPrefix(oldPath,newPath=null){
 const pins=loadDrivePins(),prefix=oldPath+'/';
 const next=[];
 for(const pin of pins){
  if(pin.path===oldPath||pin.path.startsWith(prefix)){
   if(newPath===null)continue;
   const suffix=pin.path===oldPath?'':pin.path.slice(oldPath.length);
   next.push({...pin,path:newPath+suffix,name:pin.path===oldPath?newPath.split('/').pop():pin.name});
  }else next.push(pin);
 }
 saveDrivePins(next);
}
function renderDrivePins(){
 const box=$('#documentsPinnedItems'),wrap=$('#documentsPinned');if(!box||!wrap)return;
 box.replaceChildren();
 const pins=loadDrivePins();
 wrap.hidden=!pins.length;
 for(const pin of pins){
  const button=document.createElement('button');button.type='button';button.className='documents-pin';
  button.title=folderDisplayPath(pin.path);
  const icon=document.createElement('span');icon.textContent=pin.is_dir?'📁':'📄';
  const name=document.createElement('span');name.textContent=pin.name||pin.path.split('/').pop();
  const close=document.createElement('b');close.textContent='×';close.title='Открепить';
  close.onclick=event=>{event.stopPropagation();saveDrivePins(pins.filter(x=>x.path!==pin.path))};
  button.append(icon,name,close);
  button.onclick=()=>pin.is_dir?loadDrive(pin.path):driveDownload(pin.path,pin.name||pin.path.split('/').pop());
  box.append(button);
 }
}
function toggleDrivePin(item){
 const pins=loadDrivePins(),index=pins.findIndex(x=>x.path===item.path);
 if(index>=0)pins.splice(index,1);
 else pins.unshift({path:item.path,name:item.name,is_dir:item.is_dir});
 saveDrivePins(pins);
 if(driveMenuItem?.path===item.path)syncDocumentsContextMenu();
}

function driveCard(name,kind,primary,rename,remove,context=null){
 const card=document.createElement('div');card.className='drive-file';card.dataset.kind=kind;
 const managed=context&&context.module==='files'&&['project','file'].includes(context.type);
 if(managed){
  card.dataset.drivePath=String(context.id);
  card.dataset.driveName=name;
  card.dataset.driveIsDir=String(kind==='folder');
  card.draggable=true;
  card.addEventListener('contextmenu',event=>{
   if(event.target.closest('button'))return;
   event.preventDefault();openDocumentsContextMenu(card,event.clientX,event.clientY);
  });
  card.addEventListener('dragstart',event=>{
   event.dataTransfer.effectAllowed='move';
   event.dataTransfer.setData('text/x-sayuri-drive-path',String(context.id));
   card.classList.add('dragging');
  });
  card.addEventListener('dragend',()=>card.classList.remove('dragging'));
 }
 if(kind==='folder'){
  card.tabIndex=0;
  card.title='Двойной клик или Enter — открыть папку';
  card.addEventListener('dblclick',event=>{if(!event.target.closest('button'))primary()});
  card.addEventListener('keydown',event=>{
   if(event.key==='Enter'&&event.target===card){event.preventDefault();primary()}
  });
 }
 if(context){
  card.dataset.sayuriEntityType=context.type;
  card.dataset.sayuriEntityId=String(context.id);
  card.dataset.sayuriModule=context.module||'files';
 }
 const identity=kind==='folder'?normalizeFolderMeta(context?.folder_meta,String(context?.id||'')):null;
 if(identity)applyFolderIdentity(card,identity);
 const icon=document.createElement('div');icon.className='drive-file-icon';
 icon.textContent=kind==='folder'?folderIcon(identity):kind==='shortcut'?'✦':'📄';
 const title=document.createElement('div');title.className='drive-file-name';title.textContent=name;
 const meta=document.createElement('div');meta.className='drive-file-meta';
 meta.textContent=kind==='folder'?'Папка':kind==='shortcut'?'Быстрый доступ':'Файл';
 const description=document.createElement('div');description.className='drive-file-description';
 if(identity?.description)description.textContent=identity.description;else description.hidden=true;
 const actions=document.createElement('div');actions.className='drive-file-actions';
 const open=document.createElement('button');open.textContent=kind==='folder'||kind==='shortcut'?'Открыть':'Скачать';open.onclick=primary;
 actions.append(open);
 if(managed){
  const more=document.createElement('button');more.textContent='⋯';more.title='Действия';more.setAttribute('aria-label','Действия: '+name);
  more.onclick=event=>{const r=event.currentTarget.getBoundingClientRect();openDocumentsContextMenu(card,r.right,r.bottom+4)};
  actions.append(more);
 }else{
  if(rename){
   const edit=document.createElement('button');edit.textContent='✎';edit.title='Переименовать';edit.onclick=rename;actions.append(edit);
  }
  if(remove){
   const del=document.createElement('button');del.textContent='×';del.title='Удалить';del.onclick=remove;actions.append(del);
  }
 }
 card.append(icon,title,meta);
 if(kind==='folder')card.append(description);
 card.append(actions);
 if(kind==='folder'&&managed)setupDriveDropTarget(card,String(context.id));
 return card;
}
function driveItemFromCard(card){
 if(!card?.dataset.drivePath)return null;
 return {path:card.dataset.drivePath,name:card.dataset.driveName||card.dataset.drivePath.split('/').pop(),
   is_dir:card.dataset.driveIsDir==='true',card};
}
function closeDocumentsContextMenu(){
 const menu=$('#documentsContextMenu');menu.hidden=true;driveMenuItem=null;
}
function syncDocumentsContextMenu(){
 if(!driveMenuItem)return;
 const pinned=loadDrivePins().some(x=>x.path===driveMenuItem.path);
 $('#documentsContextKind').textContent=driveMenuItem.is_dir?'Папка':'Файл';
 $('#documentsContextName').textContent=driveMenuItem.name;
 const pin=$('[data-doc-action="pin"]');
 pin.querySelector('span').textContent=pinned?'Открепить':'Закрепить';
 pin.firstChild.textContent=pinned?'★ ':'☆ ';
 const customize=$('[data-doc-action="customize"]');
 if(customize)customize.hidden=!driveMenuItem.is_dir;
}
function openDocumentsContextMenu(card,x,y){
 const item=driveItemFromCard(card);if(!item)return;
 driveMenuItem=item;syncDocumentsContextMenu();
 const menu=$('#documentsContextMenu');menu.hidden=false;
 const pad=8,w=menu.offsetWidth||220,h=menu.offsetHeight||260;
 menu.style.left=Math.max(pad,Math.min(x,innerWidth-w-pad))+'px';
 menu.style.top=Math.max(pad,Math.min(y,innerHeight-h-pad))+'px';
}
function closeDocumentsDialog(id){
 const dialog=$(id);if(typeof dialog.close==='function'&&dialog.open)dialog.close();else dialog.removeAttribute('open');
}
function showDocumentsDialog(id){
 const dialog=$(id);if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
}
async function renameDriveItem(item,newName){
 const result=await api('/drive/rename','POST',{path:item.path,new_name:newName});
 updateDrivePinsPrefix(item.path,result.path);
 $('#documentsActionStatus').textContent='«'+item.name+'» переименован в «'+newName+'».';
 await loadDrive(driveCurrent);
 return result.path;
}
async function moveDriveItem(path,destination,{announce=true}={}){
 const card=[...document.querySelectorAll('#driveFiles [data-drive-path]')].find(node=>node.dataset.drivePath===path);
 const name=card?.dataset.driveName||path.split('/').pop();
 const result=await api('/drive/move','POST',{path,destination});
 if(result.path!==path)updateDrivePinsPrefix(path,result.path);
 if(announce)$('#documentsActionStatus').textContent=result.moved?
   '«'+name+'» перемещён в '+folderDisplayPath(destination)+'.':'Объект уже находится в выбранной папке.';
 await loadDrive(driveCurrent);
 return result;
}
async function deleteDriveItem(item){
 if(!confirm('Удалить «'+item.name+'»? Папка удаляется только если она пуста.'))return false;
 await api('/drive/item?path='+encodeURIComponent(item.path),'DELETE');
 updateDrivePinsPrefix(item.path,null);
 $('#documentsActionStatus').textContent='«'+item.name+'» удалён.';
 await loadDrive(driveCurrent);return true;
}
function setupDriveDropTarget(node,destination){
 node.dataset.dropDestination=destination;
 if(node.dataset.dropBound==='true')return;
 node.dataset.dropBound='true';
 node.addEventListener('dragover',event=>{
  const types=[...event.dataTransfer.types];
  const source=types.includes('text/x-sayuri-drive-path');
  if(!source)return;event.preventDefault();event.stopPropagation();
  event.dataTransfer.dropEffect='move';node.classList.add('drop-target');
 });
 node.addEventListener('dragleave',event=>{if(!node.contains(event.relatedTarget))node.classList.remove('drop-target')});
 node.addEventListener('drop',async event=>{
  event.preventDefault();event.stopPropagation();node.classList.remove('drop-target');
  const source=event.dataTransfer.getData('text/x-sayuri-drive-path');
  const target=node.dataset.dropDestination||'';
  if(!source||source===target)return;
  try{await moveDriveItem(source,target)}catch(error){$('#documentsActionStatus').textContent='Не удалось переместить: '+error.message}
 });
}
async function openRenameItemDialog(item){
 driveMenuItem=item;
 $('#renameItemCurrent').textContent=item.name;
 $('#renameItemName').value=item.name;
 $('#renameItemError').textContent='';
 showDocumentsDialog('#renameItemDialog');
 requestAnimationFrame(()=>{$('#renameItemName').focus();$('#renameItemName').select()});
}
let folderIdentityItem=null,folderIdentityIcon='folder',folderIdentityColor='violet';
function syncFolderIdentityChoices(){
 document.querySelectorAll('[data-folder-icon]').forEach(button=>
  button.setAttribute('aria-pressed',String(button.dataset.folderIcon===folderIdentityIcon)));
 document.querySelectorAll('[data-folder-color]').forEach(button=>
  button.setAttribute('aria-pressed',String(button.dataset.folderColor===folderIdentityColor)));
}
async function openFolderIdentityDialog(item){
 if(!item?.is_dir)return;
 folderIdentityItem=item;
 $('#folderIdentityTitle').textContent=item.name;
 $('#folderIdentityPath').textContent=folderDisplayPath(item.path);
 $('#folderIdentityError').textContent='';
 try{
  const meta=normalizeFolderMeta(await api('/drive/folder-meta?path='+encodeURIComponent(item.path)),item.path);
  folderIdentityIcon=meta.icon;folderIdentityColor=meta.color;
  $('#folderIdentityDescription').value=meta.description;
  $('#folderIdentityCounter').textContent=String(meta.description.length);
  syncFolderIdentityChoices();
  showDocumentsDialog('#folderIdentityDialog');
 }catch(error){$('#documentsActionStatus').textContent='Не удалось открыть оформление папки: '+error.message}
}
document.querySelectorAll('[data-folder-icon]').forEach(button=>button.onclick=()=>{
 folderIdentityIcon=button.dataset.folderIcon;syncFolderIdentityChoices();
});
document.querySelectorAll('[data-folder-color]').forEach(button=>button.onclick=()=>{
 folderIdentityColor=button.dataset.folderColor;syncFolderIdentityChoices();
});
$('#folderIdentityDescription').oninput=event=>{
 $('#folderIdentityCounter').textContent=String(event.target.value.length);
};
$('#folderIdentityClose').onclick=()=>closeDocumentsDialog('#folderIdentityDialog');
$('#folderIdentityCancel').onclick=()=>closeDocumentsDialog('#folderIdentityDialog');
$('#folderIdentityForm').onsubmit=async event=>{
 event.preventDefault();if(!folderIdentityItem)return;
 const submit=$('#folderIdentitySubmit'),error=$('#folderIdentityError');submit.disabled=true;error.textContent='';
 try{
  await api('/drive/folder-meta','PUT',{
   path:folderIdentityItem.path,icon:folderIdentityIcon,color:folderIdentityColor,
   description:$('#folderIdentityDescription').value
  });
  $('#documentsActionStatus').textContent='Оформление папки «'+folderIdentityItem.name+'» сохранено.';
  closeDocumentsDialog('#folderIdentityDialog');
  await loadDrive(driveCurrent);
 }catch(e){error.textContent=e.message}
 finally{submit.disabled=false}
};

async function openMoveItemDialog(item){
 driveMenuItem=item;
 $('#moveItemCurrent').textContent=item.name;
 $('#moveItemError').textContent='';
 const select=$('#moveItemDestination');select.replaceChildren();
 try{
  const data=await api('/drive/folders');
  const prefix=item.is_dir?item.path+'/':null;
  for(const folder of data.folders){
   if(item.is_dir&&(folder.path===item.path||folder.path.startsWith(prefix)))continue;
   const option=document.createElement('option');option.value=folder.path;
   option.textContent=folder.path?folderDisplayPath(folder.path):'Мои файлы';
   select.append(option);
  }
  const currentParent=driveRelativeParent(item.path);
  select.value=currentParent;
  showDocumentsDialog('#moveItemDialog');
  requestAnimationFrame(()=>select.focus());
 }catch(error){$('#documentsActionStatus').textContent='Не удалось получить список папок: '+error.message}
}
document.querySelectorAll('#documentsContextMenu [data-doc-action]').forEach(button=>button.onclick=async()=>{
 const item=driveMenuItem;if(!item)return;
 const action=button.dataset.docAction;
 closeDocumentsContextMenu();
 try{
  if(action==='open'){item.is_dir?loadDrive(item.path):driveDownload(item.path,item.name);return}
  if(action==='pin'){toggleDrivePin(item);return}
  if(action==='rename'){openRenameItemDialog(item);return}
  if(action==='customize'){openFolderIdentityDialog(item);return}
  if(action==='move'){openMoveItemDialog(item);return}
  if(action==='delete'){await deleteDriveItem(item);return}
 }catch(error){$('#documentsActionStatus').textContent=error.message}
});
$('#renameItemClose').onclick=()=>closeDocumentsDialog('#renameItemDialog');
$('#renameItemCancel').onclick=()=>closeDocumentsDialog('#renameItemDialog');
$('#renameItemForm').onsubmit=async event=>{
 event.preventDefault();if(!driveMenuItem)return;
 const input=$('#renameItemName'),error=$('#renameItemError'),submit=$('#renameItemSubmit');
 const next=input.value.trim(),problem=folderNameError(next);
 if(problem){error.textContent=problem;input.focus();return}
 if(next===driveMenuItem.name){closeDocumentsDialog('#renameItemDialog');return}
 submit.disabled=true;
 try{await renameDriveItem(driveMenuItem,next);closeDocumentsDialog('#renameItemDialog')}
 catch(e){error.textContent=e.message;input.focus()}
 finally{submit.disabled=false}
};
$('#moveItemClose').onclick=()=>closeDocumentsDialog('#moveItemDialog');
$('#moveItemCancel').onclick=()=>closeDocumentsDialog('#moveItemDialog');
$('#moveItemForm').onsubmit=async event=>{
 event.preventDefault();if(!driveMenuItem)return;
 const submit=$('#moveItemSubmit'),error=$('#moveItemError');submit.disabled=true;error.textContent='';
 try{await moveDriveItem(driveMenuItem.path,$('#moveItemDestination').value);closeDocumentsDialog('#moveItemDialog')}
 catch(e){error.textContent=e.message}
 finally{submit.disabled=false}
};
document.addEventListener('pointerdown',event=>{
 const menu=$('#documentsContextMenu');
 if(!menu.hidden&&!menu.contains(event.target)&&!event.target.closest('.drive-file'))closeDocumentsContextMenu();
});
window.addEventListener('resize',closeDocumentsContextMenu);

function folderDisplayPath(path){
 return path?'Мои файлы / '+path.split('/').join(' / '):'Корень хранилища';
}
function renderFolderHierarchy(steps,directItems,searching=false,currentMeta=null){
 const tree=$('#documentsFolderTree');if(!tree)return;
 tree.replaceChildren();renderDrivePins();
 const addNode=(title,path,{active=false,child=false,depth=0,meta=null}={})=>{
  const button=document.createElement('button');
  button.type='button';button.className='documents-folder-node'+(active?' active':'')+(child?' child':'');
  if(meta)applyFolderIdentity(button,meta);
  button.style.setProperty('--folder-indent',(8+Math.min(depth,6)*8)+'px');
  const icon=document.createElement('span');icon.textContent=meta?folderIcon(meta):(active?'▾':'▸');
  const text=document.createElement('span');text.textContent=title;
  button.append(icon,text);
  button.title=folderDisplayPath(path);
  button.onclick=()=>{if(path!==driveCurrent){$('#driveSearch').value='';loadDrive(path)}};
  setupDriveDropTarget(button,path);
  tree.append(button);
 };
 for(const [index,step] of steps.entries())
  addNode(step.title,step.path,{
   active:index===steps.length-1,depth:index,
   meta:index===steps.length-1?currentMeta:null
  });
 if(!searching){
  const folders=directItems.filter(item=>item.is_dir)
    .sort((a,b)=>a.name.localeCompare(b.name,'ru',{sensitivity:'base'}));
  if(folders.length){
    const label=document.createElement('div');label.className='documents-folder-children-label';
    label.textContent='Внутри этой папки';tree.append(label);
    for(const folder of folders)
      addNode(folder.name,folder.path,{child:true,depth:steps.length,meta:folder.folder_meta});
  }
 }
}
async function loadDrive(relative=driveCurrent){
 const output=$('#driveFiles'),crumbs=$('#driveBreadcrumbs'),info=$('#driveInfo');
 driveCurrent=relative;output.replaceChildren();crumbs.replaceChildren();
 const steps=[{title:'Мои файлы',path:''}];
 if(relative){
  let accum='';
  for(const piece of relative.split('/')){accum+=(accum?'/':'')+piece;steps.push({title:piece,path:accum})}
 }
 for(const [index,step] of steps.entries()){
  if(index){const sep=document.createElement('span');sep.textContent='›';crumbs.append(sep)}
  const b=document.createElement('button');b.textContent=step.title;b.onclick=()=>{
   $('#driveSearch').value='';loadDrive(step.path)
  };crumbs.append(b);
 }
 const current=steps[steps.length-1];
 $('#documentsCurrentFolder').textContent=current.title;
 $('#documentsCurrentPath').textContent=folderDisplayPath(relative);
 const fileArea=$('.documents-file-area');
 if(!fileArea.dataset.dropReady){
  fileArea.dataset.dropReady='true';
  setupDriveDropTarget(fileArea,relative);
 }else fileArea.dataset.dropDestination=relative;
 const parentButton=$('#documentsParentFolder');
 parentButton.disabled=!relative;
 parentButton.onclick=()=>{if(relative){$('#driveSearch').value='';loadDrive(driveRelativeParent(relative))}};
 try{
  const res=await api('/drive/list?path='+encodeURIComponent(relative));
  const search=$('#driveSearch').value.trim();
  const items=search?(await api('/drive/search?q='+encodeURIComponent(search))).items:res.items;
  renderFolderHierarchy(steps,res.items,Boolean(search),res.current_meta);
  const currentMeta=normalizeFolderMeta(res.current_meta,relative);
  const currentCard=$('#documentsCurrentFolderCard');
  applyFolderIdentity(currentCard,relative?currentMeta:{color:'slate',icon:'folder'});
  $('#documentsCurrentFolderIcon').textContent=relative?folderIcon(currentMeta):'📁';
  const currentDescription=$('#documentsCurrentDescription');
  currentDescription.textContent=currentMeta.description;
  currentDescription.hidden=!relative||!currentMeta.description;
  const directFolders=res.items.filter(item=>item.is_dir).length;
  const directFiles=res.items.filter(item=>!item.is_dir).length;
  $('#documentsFolderCount').textContent=String(directFolders);
  $('#documentsFileCount').textContent=String(directFiles);
  info.textContent=search?'Результаты поиска · '+items.length:'Расположение: '+res.root+' · '+items.length+' объектов';
  const count=$('#documentsObjectCount');
  if(count)count.textContent=items.length+' '+(items.length===1?'объект':'объектов');
  if(!relative && !search){
   output.append(driveCard('Рабочие проекты','shortcut',()=>{
    window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'project_opened',module:'work',entity_type:'project',entity_id:'work'}}));
    view('work');
   },null,null,{type:'project',id:'work',module:'files'}));
   output.append(driveCard('Домашние проекты','shortcut',()=>{
    window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'project_opened',module:'home',entity_type:'project',entity_id:'home'}}));
    view('home');
   },null,null,{type:'project',id:'home',module:'files'}));
  }
  const displayItems=[...items].sort((a,b)=>{
   if(Boolean(a.is_dir)!==Boolean(b.is_dir))return a.is_dir?-1:1;
   return a.name.localeCompare(b.name,'ru',{numeric:true,sensitivity:'base'});
  });
  for(const item of displayItems){
   const open=item.is_dir?()=>{
    window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{
      type:'project_opened',module:'files',entity_type:'project',entity_id:item.path}}));
    $('#driveSearch').value='';loadDrive(item.path)
   }:()=>driveDownload(item.path,item.name);
   const rename=()=>openRenameItemDialog({path:item.path,name:item.name,is_dir:item.is_dir});
   const remove=()=>deleteDriveItem({path:item.path,name:item.name,is_dir:item.is_dir});
   output.append(driveCard(item.name,item.is_dir?'folder':'file',open,rename,remove,{
    type:item.is_dir?'project':'file',id:item.path,module:'files',folder_meta:item.folder_meta
   }));
  }
  if(!output.childElementCount)output.textContent='Папка пуста. Создайте папку или добавьте файлы.';
 }catch(e){info.textContent='Хранилище недоступно: '+e.message}
}
async function driveDownload(path,name){
 window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'document_opened',module:'files',entity_type:'file',entity_id:path}}));
 try{
  const res=await fetch('/api/drive/download?path='+encodeURIComponent(path),{headers:{Authorization:'Bearer '+token}});
  if(!res.ok)throw Error('Ошибка загрузки '+res.status);
  const blob=await res.blob(),link=document.createElement('a'),url=URL.createObjectURL(blob);
  link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1500);
 }catch(e){alert(e.message)}
}
function folderNameError(value){
 const name=value.trim();
 if(!name)return 'Введите название папки.';
 if(name==='.'||name==='..')return 'Такое название использовать нельзя.';
 if(/[<>:"/\\|?*\u0000-\u001F]/.test(name))return 'Название содержит недопустимый символ.';
 if(/[. ]$/.test(name))return 'Название не должно заканчиваться точкой или пробелом.';
 if(/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i.test(name))
  return 'Это имя зарезервировано системой Windows.';
 return '';
}
function openNewFolderDialog(){
 const dialog=$('#newFolderDialog'),input=$('#newFolderName'),error=$('#newFolderError');
 $('#newFolderParent').textContent=folderDisplayPath(driveCurrent);
 input.value='';input.removeAttribute('aria-invalid');error.textContent='';
 if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
 requestAnimationFrame(()=>input.focus());
}
function closeNewFolderDialog(){
 const dialog=$('#newFolderDialog');
 if(typeof dialog.close==='function'&&dialog.open)dialog.close();else dialog.removeAttribute('open');
}
$('#driveNewFolder').onclick=openNewFolderDialog;
$('#newFolderClose').onclick=closeNewFolderDialog;
$('#newFolderCancel').onclick=closeNewFolderDialog;
$('#newFolderName').oninput=()=>{
 const input=$('#newFolderName'),error=$('#newFolderError'),problem=folderNameError(input.value);
 error.textContent=problem;input.setAttribute('aria-invalid',String(Boolean(problem)));
};
$('#newFolderForm').onsubmit=async event=>{
 event.preventDefault();
 const input=$('#newFolderName'),error=$('#newFolderError'),submit=$('#newFolderSubmit');
 const name=input.value.trim(),problem=folderNameError(name);
 if(problem){error.textContent=problem;input.setAttribute('aria-invalid','true');input.focus();return}
 submit.disabled=true;error.textContent='';
 try{
  const result=await api('/drive/folder','POST',{parent:driveCurrent,name});
  closeNewFolderDialog();
  await loadDrive(driveCurrent);
  $('#documentsActionStatus').textContent='Папка «'+name+'» создана в '+folderDisplayPath(driveCurrent)+'.';
  const created=[...document.querySelectorAll('#driveFiles [data-sayuri-entity-id]')]
    .find(node=>node.dataset.sayuriEntityId===result.path);
  created?.classList.add('just-created');
  created?.scrollIntoView({block:'nearest',behavior:'smooth'});
 }catch(e){
  error.textContent=e.message;input.setAttribute('aria-invalid','true');input.focus();
 }finally{submit.disabled=false}
};
$('#driveUpload').onclick=()=>$('#driveFileInput').click();
$('#driveFileInput').onchange=async()=>{
 const input=$('#driveFileInput');const files=[...input.files];
 $('#driveInfo').textContent='Загрузка '+files.length+' файлов…';
 for(const file of files){
  const payload=new FormData();payload.append('file',file);payload.append('path',driveCurrent);
  try{await api('/drive/upload','POST',payload);
   window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{
    type:'document_uploaded',module:'files',entity_type:'file',
    entity_id:(driveCurrent?driveCurrent+'/':'')+file.name}}));
  }catch(e){alert(file.name+': '+e.message)}
 }
 input.value='';await loadDrive();
};
$('#driveSearch').oninput=()=>{
 clearTimeout(driveTimer);
 driveTimer=setTimeout(()=>loadDrive(driveCurrent),280);
};
$('#newFolderDialog').addEventListener('click',event=>{
 if(event.target===$('#newFolderDialog'))closeNewFolderDialog();
});

async function loadBuildInfo(){
 const info=$('#runningVersion'),folder=$('#runningFolder');
 try{
  const data=await api('/build/info');
  const projectVersion=data.project_version||data.ui_version;
  const coreVersion=data.core_version||'3.0.0',memoryVersion=data.memory_version||'3.0.0';
  info.textContent='Проект '+projectVersion+' · Core '+coreVersion+' · Memory '+memoryVersion+' · Интерфейс '+data.ui_version;
  folder.textContent=data.running_folder;
  $('#accountUiVersion').textContent=data.ui_version;
  $('#accountProjectVersion').textContent=projectVersion;
  $('#accountCoreVersion').textContent=coreVersion;
  $('#accountMemoryVersion').textContent=memoryVersion;
  $('#runningVersionNote').textContent='Этот путь принадлежит серверу, который сейчас отвечает браузеру. Если вы скачали ZIP в другую папку, дизайн здесь не изменится.';
 }catch(e){
  info.textContent='Версия сервера не определена';
  folder.textContent='Не удалось получить расположение сервера: '+e.message;
 }
}
async function checkGithubUpdate(){
 const status=$('#updateStatus');
 $('#installUpdate').disabled=true;
 status.textContent='Проверка основной ветки main на GitHub…';
 await loadBuildInfo();
 try{
  const data=await api('/updates/status');
  if(data.supported===false){status.textContent=data.reason||'Проверка недоступна';return}
  const mode=data.mode==='zip'?'ZIP':'Git';
  const installed=data.local==='ZIP (неизвестна)'?'неизвестна (обычный ZIP без метки версии)':data.local;
  status.textContent='Установка: '+mode+' · Локальная ревизия: '+installed+
   ' · GitHub: '+data.latest+
   (data.update_available?' · Доступна подготовка новой версии':' · Ревизии совпадают')+
   (!data.clean?' · Локальные изменения: обновление недоступно':'');
  $('#installUpdate').disabled=!data.update_available||!data.clean;
  $('#installUpdate').textContent=data.mode==='zip'?'Подготовить новую ZIP-папку':'Обновить Git-клон';
 }catch(e){status.textContent='Проверка не удалась: '+e.message}
}
$('#checkUpdate').onclick=checkGithubUpdate;
$('#installUpdate').onclick=async()=>{
 if(!confirm('Обновление создаст новую папку рядом с текущей. ВНИМАНИЕ: запущенный сервер НЕ заменится автоматически. Продолжить?'))return;
 $('#installUpdate').disabled=true;
 $('#updateStatus').textContent='Создаём резервную копию и загружаем новую версию…';
 try{
  const r=await api('/updates/apply','POST',{confirm:true});
  if(r.mode==='zip' && r.updated){
   const notice=$('#preparedUpdate');
   notice.hidden=false;
   notice.dataset.sayuriEntityType='notification';
   notice.dataset.sayuriEntityId='update-prepared';
   notice.dataset.sayuriModule='updates';
   notice.replaceChildren();
   const title=document.createElement('strong');title.textContent='Новая версия скачана, но ещё НЕ запущена.';
   const path=document.createElement('div');path.className='monospace-path';path.textContent=r.new_folder||'Путь отсутствует';
   const instructions=document.createElement('p');
   instructions.textContent='Закройте старое окно Sayuri.bat, откройте папку выше и запустите Sayuri.bat из неё. Проверьте запущенную папку после перезапуска.';
   notice.append(title,path,instructions);
   window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{
    type:'notification_shown',module:'updates',entity_type:'notification',entity_id:'update-prepared'}}));
   $('#updateStatus').textContent='Архив подготовлен. Дизайн изменится только после запуска новой версии.';
  }else $('#updateStatus').textContent=r.updated?
   'Обновление загружено. Закройте Sayuri и перезапустите Sayuri.bat.':
   'Код уже совпадает с текущей ревизией.';
 }catch(e){$('#updateStatus').textContent='Обновление не выполнено: '+e.message}
};

