const $=s=>document.querySelector(s);let token=sessionStorage.getItem('sayuri_token')||'',chats=[],active=null,busy=false;
async function api(path,method='GET',data=null){const opts={method,headers:{}};if(token)opts.headers.Authorization='Bearer '+token;if(data!==null){if(data instanceof FormData)opts.body=data;else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data)}}const r=await fetch('/api'+path,opts);let result;try{result=await r.json()}catch{result={}}if(!r.ok){const message=Array.isArray(result.detail)?result.detail.map(x=>x.msg||x.type).join('; '):result.detail;throw Error(message||'Ошибка '+r.status)}return result}
function fail(e){$('#error').textContent=e.message||String(e)}
function view(id){for(const x of document.querySelectorAll('.view'))x.classList.toggle('active',x.id===id+'View');$('#title').textContent=id==='account'?'Личный кабинет Саюри':id==='files'?'Документы':'Саюри · общий чат';document.body.classList.remove('open');if(id==='account')account();if(id==='files')files()}
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
  $('#cloud').textContent=state.mentor_configured?'Наставник подключён':'Наставник: настройте Cloud.ru';
}
async function messages(){const box=$('#messages');box.replaceChildren();if(!active){box.textContent='Общий чат загружается…';return}for(const m of await api('/chats/'+active+'/messages')){const div=document.createElement('div');div.className='bubble '+m.role;const small=document.createElement('small');small.textContent=m.role==='user'?'Вы':'Наставник · Sayuri наблюдает';const text=document.createElement('div');text.textContent=m.text;div.append(small,text);if(m.role==='assistant'){for(const [symbol,score] of [['👍',1],['👎',-1]]){const b=document.createElement('button');b.textContent=symbol;b.onclick=async()=>{try{await api('/feedback','POST',{message_id:m.id,rating:score});b.disabled=true}catch(e){fail(e)}};div.append(b)}}box.append(div)}box.scrollTop=box.scrollHeight}
async function send(e){e.preventDefault();if(busy)return;const text=$('#draft').value.trim();if(!text)return;busy=true;$('#send').disabled=true;$('#error').textContent='Наставник отвечает; Sayuri изучает диалог…';try{if(!active)await refresh();await api('/chats/'+active+'/send','POST',{text});$('#draft').value='';await refresh();$('#error').textContent=''}catch(e){fail(e)}finally{busy=false;$('#send').disabled=false}}
async function account(){loadCloudSettings();loadPreferences();drawCandidates();try{const [p,m,s]=await Promise.all([api('/persona'),api('/memory'),api('/learning/stats')]);$('#persona').textContent=p.name+' · v'+p.version+' · '+p.sections+' разделов · '+p.dialogues+' диалогов ('+p.messages+' сообщений) · '+p.phrases+' реплик / '+p.categories+' категорий · '+p.chapters+' глав легенды · '+p.rituals+' ритуалов · '+p.rules+' правил · '+p.scenarios+' проверок. Режимы: '+p.modes.join(', ');$('#stats').textContent='Чаты: '+s.chats+' · Память: '+s.memories+' · Отзывы: '+s.feedback+' · Файлы: '+s.documents;const box=$('#memories');box.replaceChildren();for(const f of m){const div=document.createElement('div');div.className='line';const text=document.createElement('span');text.textContent=f.text;const b=document.createElement('button');b.textContent='Удалить';b.onclick=async()=>{await api('/memory/'+f.id,'DELETE');account()};div.append(text,b);box.append(div)}}catch(e){fail(e)}}
async function files(){await projectRoot();try{const list=await api('/documents');const box=$('#files');box.replaceChildren();for(const f of list){
  const row=document.createElement('div');row.className='line';
  const name=document.createElement('span');name.textContent='📎 '+f.name;
  const del=document.createElement('button');del.textContent='Удалить';
  del.onclick=async()=>{
    if(!confirm('Удалить этот файл из Sayuri?'))return;
    try{await api('/documents/'+f.id,'DELETE');await files()}catch(e){fail(e)}
  };
  row.append(name,del);box.append(row)
}}catch(e){fail(e)}}

async function projectRoot(){
  const target=$('#projects');if(!target)return;target.replaceChildren();
  try{
    const result=await api('/projects');
    if(!result.root_configured){target.textContent='Укажите SAYURI_PROJECTS_DIR в закрытом файле .env для разрешённого доступа.';return}
    for(const category of result.categories){
      const b=document.createElement('button');b.textContent=category.name+(category.available?'':' — отсутствует');
      b.disabled=!category.available;b.onclick=()=>projectBrowse(category.id,'',category.name);target.append(b);
    }
  }catch(e){target.textContent=e.message}
}
async function projectBrowse(category,relative,title){
  const target=$('#projects');target.replaceChildren();
  const back=document.createElement('button');back.textContent='← Разделы';back.onclick=projectRoot;target.append(back);
  const name=document.createElement('h4');name.textContent=title+(relative?' / '+relative:'');target.append(name);
  try{
    const result=await api('/projects/'+category+'/list?path='+encodeURIComponent(relative));
    for(const entry of result.items){
      const b=document.createElement('button');b.style.display='block';b.style.margin='7px 0';
      b.textContent=(entry.is_dir?'📁 ':'📄 ')+entry.name;target.append(b);
      if(entry.is_dir)b.onclick=()=>projectBrowse(category,entry.relative,title);
      else b.onclick=()=>projectDownload(category,entry.relative,entry.name);
    }
  }catch(e){const p=document.createElement('p');p.textContent=e.message;target.append(p)}
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
$('#showChat').onclick=()=>view('chat');$('#showAccount').onclick=()=>view('account');$('#showFiles').onclick=()=>view('files');
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
    $('#cloud').textContent=h.mentor_configured?'Наставник подключён':'Наставник: настройте Cloud.ru';
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
