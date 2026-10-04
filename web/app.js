const $=s=>document.querySelector(s);let token=sessionStorage.getItem('sayuri_token')||'',chats=[],active=null,busy=false;
async function api(path,method='GET',data=null){const opts={method,headers:{}};if(token)opts.headers.Authorization='Bearer '+token;if(data!==null){if(data instanceof FormData)opts.body=data;else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data)}}const r=await fetch('/api'+path,opts);let result;try{result=await r.json()}catch{result={}}if(!r.ok){const message=Array.isArray(result.detail)?result.detail.map(x=>x.msg||x.type).join('; '):result.detail;throw Error(message||'Ошибка '+r.status)}return result}
function fail(e){$('#error').textContent=e.message||String(e)}
function view(id){for(const x of document.querySelectorAll('.view'))x.classList.toggle('active',x.id===id+'View');$('#title').textContent=({account:'Личный кабинет Sayuri',files:'Документы / Облако / Sayuri',work:'Рабочие проекты',home:'Домашние проекты',updates:'Обновление проекта',chat:'Саюри · общий чат'})[id]||'Sayuri';if(id==='account')account();if(id==='files'){files();loadDrive()}if(id==='work'||id==='home')showProject(id)}
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
async function send(e){e.preventDefault();if(busy)return;const text=$('#draft').value.trim();if(!text)return;busy=true;$('#send').disabled=true;$('#error').textContent='Наставник отвечает; Sayuri изучает диалог…';try{if(!active)await refresh();await api('/chats/'+active+'/send','POST',{text});$('#draft').value='';await refresh();$('#error').textContent=''}catch(e){fail(e)}finally{busy=false;$('#send').disabled=false}}
async function account(){loadCloudSettings();loadPreferences();drawCandidates();loadDevelopment();try{const [p,m,s]=await Promise.all([api('/persona'),api('/memory'),api('/learning/stats')]);$('#persona').textContent=p.name+' · v'+p.version+' · '+p.sections+' разделов · '+p.dialogues+' диалогов ('+p.messages+' сообщений) · '+p.phrases+' реплик / '+p.categories+' категорий · '+p.chapters+' глав легенды · '+p.rituals+' ритуалов · '+p.rules+' правил · '+p.scenarios+' проверок. Режимы: '+p.modes.join(', ');$('#stats').textContent='Чаты: '+s.chats+' · Память: '+s.memories+' · Отзывы: '+s.feedback+' · Файлы: '+s.documents;const box=$('#memories');box.replaceChildren();for(const f of m){const div=document.createElement('div');div.className='line';const text=document.createElement('span');text.textContent=f.text;const b=document.createElement('button');b.textContent='Удалить';b.onclick=async()=>{await api('/memory/'+f.id,'DELETE');account()};div.append(text,b);box.append(div)}}catch(e){fail(e)}}
async function files(){try{const list=await api('/documents');const box=$('#files');box.replaceChildren();for(const f of list){
  const row=document.createElement('div');row.className='line';
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
    if(!data.items.length){
      const empty=document.createElement('p');empty.textContent='Папка пуста.';
      target.append(empty);
    }
    for(const item of data.items){
      const btn=document.createElement('button');
      btn.style.display='block';btn.style.textAlign='left';btn.style.margin='7px 0';btn.style.width='100%';
      btn.textContent=(item.is_dir?'📁 ':'📄 ')+item.name;
      if(item.is_dir)btn.onclick=()=>showProject(category,item.relative);
      else btn.onclick=()=>projectDownload(category,item.relative,item.name);
      target.append(btn);
    }
  }catch(e){const warning=document.createElement('p');warning.textContent=e.message;target.append(warning)}
}
async function projectDownload(category,path,name){
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

$('#menu').onclick=()=>document.body.classList.toggle('open');
$('#showUpdates').onclick=()=>view('updates');$('#showChat').onclick=()=>view('chat');$('#showWork').onclick=()=>view('work');$('#showHome').onclick=()=>view('home');$('#showAccount').onclick=()=>view('account');$('#showFiles').onclick=()=>view('files');
$('#composer').onsubmit=send;$('#draft').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#composer').requestSubmit()}};

$('#memoryForm').onsubmit=async e=>{e.preventDefault();try{await api('/memory','POST',{text:$('#fact').value});$('#fact').value='';account()}catch(x){fail(x)}};
$('#fileForm').onsubmit=async e=>{e.preventDefault();const f=$('#file').files[0];if(!f)return;const form=new FormData();form.append('file',f);try{await api('/documents','POST',form);$('#file').value='';files()}catch(x){fail(x)}};
async function bootstrapLocal() {
  $('#cloud').textContent='Подключение локальной сессии…';
  try {
    // Local-only endpoint never sends a password or Cloud.ru key to the browser.
    const authResponse=await api('/auth/local','POST');
    token=authResponse.token;
    sessionStorage.setItem('sayuri_token',token);
    await refresh();
    view('account');
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
let voiceEnabled=false,quietMotion=false,driveCurrent='',driveTimer=null;
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
    const small=document.createElement('small');small.textContent=(m.scope==='project'?'Проектная':'Личная')+' память · подтверждено';
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
function driveCard(name,kind,primary,rename,remove){
 const card=document.createElement('div');card.className='drive-file';
 const icon=document.createElement('div');icon.className='drive-file-icon';icon.textContent=kind==='folder'?'📁':kind==='shortcut'?'✦':'📄';
 const title=document.createElement('div');title.className='drive-file-name';title.textContent=name;
 const actions=document.createElement('div');actions.className='drive-file-actions';
 const open=document.createElement('button');open.textContent=kind==='folder'||kind==='shortcut'?'Открыть':'Скачать';open.onclick=primary;
 actions.append(open);
 if(rename){
  const edit=document.createElement('button');edit.textContent='✎';edit.title='Переименовать';edit.onclick=rename;actions.append(edit);
 }
 if(remove){
  const del=document.createElement('button');del.textContent='×';del.title='Удалить';del.onclick=remove;actions.append(del);
 }
 card.append(icon,title,actions);return card;
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
  const b=document.createElement('button');b.textContent=step.title;b.onclick=()=>loadDrive(step.path);crumbs.append(b);
 }
 try{
  const res=await api('/drive/list?path='+encodeURIComponent(relative));
  const search=$('#driveSearch').value.trim();
  const items=search?(await api('/drive/search?q='+encodeURIComponent(search))).items:res.items;
  info.textContent=search?'Результаты поиска · '+items.length:'Расположение: '+res.root+' · '+items.length+' объектов';
  if(!relative && !search){
   output.append(driveCard('Рабочие проекты','shortcut',()=>view('work')));
   output.append(driveCard('Домашние проекты','shortcut',()=>view('home')));
  }
  for(const item of items){
   const open=item.is_dir?()=>{ $('#driveSearch').value='';loadDrive(item.path)}:()=>driveDownload(item.path,item.name);
   const rename=async()=>{
    const next=prompt('Новое название',item.name);if(next===null||next===item.name)return;
    try{await api('/drive/rename','POST',{path:item.path,new_name:next});await loadDrive()}catch(e){alert(e.message)}
   };
   const remove=async()=>{
    if(!confirm('Удалить '+item.name+'? Папку можно удалить, только если она пуста.'))return;
    try{await api('/drive/item?path='+encodeURIComponent(item.path),'DELETE');await loadDrive()}catch(e){alert(e.message)}
   };
   output.append(driveCard(item.name,item.is_dir?'folder':'file',open,rename,remove));
  }
  if(!output.childElementCount)output.textContent='Папка пуста. Создайте папку или добавьте файлы.';
 }catch(e){info.textContent='Хранилище недоступно: '+e.message}
}
async function driveDownload(path,name){
 try{
  const res=await fetch('/api/drive/download?path='+encodeURIComponent(path),{headers:{Authorization:'Bearer '+token}});
  if(!res.ok)throw Error('Ошибка загрузки '+res.status);
  const blob=await res.blob(),link=document.createElement('a'),url=URL.createObjectURL(blob);
  link.href=url;link.download=name;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1500);
 }catch(e){alert(e.message)}
}
$('#driveNewFolder').onclick=async()=>{
 const name=prompt('Название новой папки');
 if(!name)return;
 try{await api('/drive/folder','POST',{parent:driveCurrent,name});await loadDrive()}catch(e){alert(e.message)}
};
$('#driveUpload').onclick=()=>$('#driveFileInput').click();
$('#driveFileInput').onchange=async()=>{
 const input=$('#driveFileInput');const files=[...input.files];
 $('#driveInfo').textContent='Загрузка '+files.length+' файлов…';
 for(const file of files){
  const payload=new FormData();payload.append('file',file);payload.append('path',driveCurrent);
  try{await api('/drive/upload','POST',payload)}catch(e){alert(file.name+': '+e.message)}
 }
 input.value='';await loadDrive();
};
$('#driveSearch').oninput=()=>{
 clearTimeout(driveTimer);
 driveTimer=setTimeout(()=>loadDrive(driveCurrent),280);
};

async function checkGithubUpdate(){
  const status=$('#updateStatus');
  $('#installUpdate').disabled=true;
  status.textContent='Проверка главной ветки GitHub…';
  try{
    const data=await api('/updates/status');
    if(data.supported===false){status.textContent=data.reason;return}
    status.textContent='Способ: '+(data.mode==='zip'?'ZIP':'Git')+' · Установлено: '+data.local+' · GitHub: '+data.latest+
      (data.update_available?' · Доступно обновление':' · Последняя версия')+
      (!data.clean?' · Найдены локальные изменения':'')+
      (data.mode==='zip'?' · Подготовка в новую папку':'');
    $('#installUpdate').disabled=!data.update_available||!data.clean;
    $('#installUpdate').textContent=data.mode==='zip'?'Скачать ZIP-обновление':'Обновить с GitHub';
  }catch(e){status.textContent='Проверка не удалась: '+e.message}
}
$('#checkUpdate').onclick=checkGithubUpdate;
$('#installUpdate').onclick=async()=>{
  if(!confirm('Скачать обновление из Aspksa/Sayuri? Для ZIP будет создана отдельная новая папка с вашей памятью и настройками. Старая версия останется нетронутой.'))return;
  $('#installUpdate').disabled=true;
  $('#updateStatus').textContent='Создание резервной копии и загрузка обновления…';
  try{
    const r=await api('/updates/apply','POST',{confirm:true});
    $('#updateStatus').textContent=r.updated?
      (r.mode==='zip'?'Новая Sayuri готова: '+r.new_folder+' . Закройте старую Sayuri и откройте Sayuri.bat в новой папке.':
      'Код обновлён. Закройте Sayuri и запустите Sayuri.bat заново.'):'Уже установлена последняя версия.';
  }catch(e){$('#updateStatus').textContent='Обновление отменено: '+e.message}
};
