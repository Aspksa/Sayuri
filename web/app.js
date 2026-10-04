const $=s=>document.querySelector(s);let token=sessionStorage.getItem('sayuri_token')||'',chats=[],active=null,busy=false;
async function api(path,method='GET',data=null){const opts={method,headers:{}};if(token)opts.headers.Authorization='Bearer '+token;if(data!==null){if(data instanceof FormData)opts.body=data;else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(data)}}const r=await fetch('/api'+path,opts);let result;try{result=await r.json()}catch{result={}}if(!r.ok)throw Error(result.detail||'Ошибка '+r.status);return result}
function fail(e){$('#error').textContent=e.message||String(e)}
async function sign(up=false){try{const password=$('#password').value;if(up)await api('/auth/setup','POST',{password});const v=await api('/auth/login','POST',{password});token=v.token;sessionStorage.setItem('sayuri_token',token);$('#gate').classList.add('hidden');$('#password').value='';await refresh()}catch(e){$('#gateError').textContent=e.message}}
function view(id){for(const x of document.querySelectorAll('.view'))x.classList.toggle('active',x.id===id+'View');document.body.classList.remove('open');if(id==='account')account();if(id==='files')files()}
function threads(){const box=$('#threads');box.replaceChildren();const q=$('#search').value.toLowerCase();for(const c of chats.filter(x=>x.title.toLowerCase().includes(q))){const b=document.createElement('button');b.textContent=c.title;b.className=active===c.id?'active':'';b.onclick=async()=>{active=c.id;threads();view('chat');await messages()};box.append(b)}}
async function refresh(){chats=await api('/chats');if(!chats.some(c=>c.id===active))active=chats[0]?.id||null;threads();await messages();const h=await api('/health');$('#cloud').textContent=h.cloud_configured?'Cloud.ru настроен':'Cloud.ru: требуется ключ'}
async function messages(){const box=$('#messages');box.replaceChildren();if(!active){box.textContent='Здравствуйте, Господин. Создайте чат, чтобы начать беседу.';return}for(const m of await api('/chats/'+active+'/messages')){const div=document.createElement('div');div.className='bubble '+m.role;const small=document.createElement('small');small.textContent=m.role==='user'?'Вы':'Саюри';const text=document.createElement('div');text.textContent=m.text;div.append(small,text);if(m.role==='assistant'){for(const [symbol,score] of [['👍',1],['👎',-1]]){const b=document.createElement('button');b.textContent=symbol;b.onclick=async()=>{try{await api('/feedback','POST',{message_id:m.id,rating:score});b.disabled=true}catch(e){fail(e)}};div.append(b)}}box.append(div)}box.scrollTop=box.scrollHeight}
async function newChat(){try{const c=await api('/chats','POST',{title:'Новый чат'});active=c.id;await refresh();view('chat')}catch(e){fail(e)}}
async function send(e){e.preventDefault();if(busy)return;const text=$('#draft').value.trim();if(!text)return;busy=true;$('#send').disabled=true;$('#error').textContent='Саюри отвечает…';try{if(!active){const c=await api('/chats','POST',{title:'Новый чат'});active=c.id}await api('/chats/'+active+'/send','POST',{text});$('#draft').value='';await refresh();$('#error').textContent=''}catch(e){fail(e)}finally{busy=false;$('#send').disabled=false}}
async function account(){try{const [p,m,s]=await Promise.all([api('/persona'),api('/memory'),api('/learning/stats')]);$('#persona').textContent=p.name+' · v'+p.version+' · '+p.modes.join(', ');$('#stats').textContent='Чаты: '+s.chats+' · Память: '+s.memories+' · Отзывы: '+s.feedback+' · Файлы: '+s.documents;const box=$('#memories');box.replaceChildren();for(const f of m){const div=document.createElement('div');div.className='line';const text=document.createElement('span');text.textContent=f.text;const b=document.createElement('button');b.textContent='Удалить';b.onclick=async()=>{await api('/memory/'+f.id,'DELETE');account()};div.append(text,b);box.append(div)}}catch(e){fail(e)}}
async function files(){await projectRoot();try{const list=await api('/documents');const box=$('#files');box.replaceChildren();for(const f of list){const div=document.createElement('p');div.textContent='📎 '+f.name;box.append(div)}}catch(e){fail(e)}}

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

$('#setup').onclick=()=>sign(true);$('#login').onclick=()=>sign();$('#password').onkeydown=e=>{if(e.key==='Enter')sign()};
$('#new').onclick=newChat;$('#search').oninput=threads;$('#menu').onclick=()=>document.body.classList.toggle('open');
$('#showChat').onclick=()=>view('chat');$('#showAccount').onclick=()=>view('account');$('#showFiles').onclick=()=>view('files');
$('#composer').onsubmit=send;$('#draft').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#composer').requestSubmit()}};
$('#logout').onclick=async()=>{try{await api('/auth/logout','POST')}catch{}sessionStorage.removeItem('sayuri_token');location.reload()};
$('#memoryForm').onsubmit=async e=>{e.preventDefault();try{await api('/memory','POST',{text:$('#fact').value});$('#fact').value='';account()}catch(x){fail(x)}};
$('#fileForm').onsubmit=async e=>{e.preventDefault();const f=$('#file').files[0];if(!f)return;const form=new FormData();form.append('file',f);try{await api('/documents','POST',form);$('#file').value='';files()}catch(x){fail(x)}};
(async()=>{if(token){try{await api('/chats');$('#gate').classList.add('hidden');await refresh()}catch{token='';sessionStorage.removeItem('sayuri_token')}}})();
