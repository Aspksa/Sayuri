/* BEYOND 2.3 — contextual character motion layered on real runtime state. */
(() => {
  "use strict";
  const el = id => document.getElementById(id);
  const shell = el("foxShell"), avatar = el("foxAvatar"), picture = el("foxAvatarImage");
  const menu = el("foxContextMenu"), panel = el("foxPanel");
  if (!shell || !avatar || !menu) return;
  const keys = ["mode", "quiet", "enabled", "scale", "x", "y", "behavior"];
  const eventTypes = new Set([
    "route_changed", "document_opened", "document_uploaded", "record_selected",
    "task_started", "task_progress", "task_failed", "task_finished",
    "memory_updated", "contradiction_detected"
  ]);
  const modules = {account:"Личный кабинет",beyond:"SAYURI BEYOND",chat:"Единый чат",
    files:"Документы / Облако / Sayuri",work:"Рабочие проекты",
    home:"Домашние проекты",updates:"Обновление проекта"};
  let settings = {mode:"compact",quiet:false,enabled:true,scale:1,x:null,y:null,behavior:"stationary"};
  let moduleName = "account", selected = null, recentEvent = null, liveStatus = null;
  let lastObjectUrl = null, portraitObjectUrl=null, initialized = false, savePending = false, queuedSave=false;
  let menuPreviouslyFocused = null, drag = null, longPress = null, suppressClick = false;
  let behaviorTimer=null,returnTimer=null,autoMoveTimer=null,motionTimer=null,waypointIndex=0,lastManualMoveAt=0;
  let runtimeState="ready",motionState="idle";
  const token = () => sessionStorage.getItem("sayuri_token") || "";
  const authHeaders = () => ({Authorization:"Bearer " + token()});
  const bound = (v,a,b) => Math.min(b,Math.max(a,v));
  function usable() { return !!token(); }
  function dispatch(detail) {
    if (!detail || !eventTypes.has(detail.type)) return;
    const moduleId = Object.hasOwn(modules,detail.module) ? detail.module : moduleName;
    // Metadata only — do not read screen text, form values or user documents.
    recentEvent = {id:crypto.randomUUID(),timestamp:new Date().toISOString(),
      actor:"owner",type:detail.type,module:moduleId,
      entity_type:detail.entity_type || null,
      entity_id:typeof detail.entity_id==="string" ? detail.entity_id.slice(0,180) : null,
      permission_scope:"local_ui"};
    if (detail.type==="route_changed") {
      moduleName=moduleId;
      document.body.dataset.activeView=moduleName;
      if(settings.behavior==="follow") followActiveView();
      else if(settings.x===null && settings.y===null) position();
    }
    if (detail.type==="document_opened" || detail.type==="record_selected")
      selected={module:moduleId,type:recentEvent.entity_type,id:recentEvent.entity_id};
    if(detail.type==="document_uploaded") selected={module:moduleId,
      type:recentEvent.entity_type,id:recentEvent.entity_id};
    if (detail.type==="route_changed" && selected && selected.module!==moduleId) selected=null;
    if(["document_opened","record_selected"].includes(detail.type))
      setMotionState("reading",{temporary:2200});
    if(["task_started","task_progress"].includes(detail.type))
      setMotionState("working",{temporary:1800});
    if(detail.type==="task_finished"||detail.type==="memory_updated")
      setMotionState("happy",{temporary:2600});
    if(detail.type==="task_failed"||detail.type==="contradiction_detected")
      setMotionState("attention",{temporary:3600});
    if(settings.behavior==="event" &&
      ["task_finished","task_failed","memory_updated","contradiction_detected"].includes(detail.type))
      approachEvent(detail.type);
  }
  window.addEventListener("sayuri:context",e=>dispatch(e.detail));
  const motionNames={
    idle:"Ожидает",walking:"Идёт",thinking:"Размышляет",reading:"Изучает",
    working:"Работает",happy:"Радуется",attention:"Требует внимания"
  };
  function motionFromRuntime(state){
    if(["reasoning","verifying","linking"].includes(state))return "thinking";
    if(["researching","studying","memorizing"].includes(state))return "reading";
    if(state==="executing")return "working";
    if(state==="completed")return "happy";
    if(["attention","disconnected"].includes(state))return "attention";
    return "idle";
  }
  function setMotionState(state,{temporary=0}={}){
    motionState=state;
    shell.dataset.motionState=state;
    const label=el("foxMotionState");
    if(label)label.textContent=motionNames[state]||motionNames.idle;
    if(motionTimer)clearTimeout(motionTimer);
    motionTimer=null;
    if(temporary>0)motionTimer=setTimeout(()=>setMotionState(motionFromRuntime(runtimeState)),temporary);
  }
  function setRuntimeState(state){
    runtimeState=state||"ready";
    el("foxStatus").dataset.state=runtimeState;
    if(motionState!=="walking")setMotionState(motionFromRuntime(runtimeState));
  }
  window.addEventListener("sayuri:runtime",e=>{
    const state=e.detail?.state;
    if(typeof state==="string")setRuntimeState(state);
  });
  window.SayuriContext = Object.freeze({getCurrent:()=>({module:moduleName,selected,
    latestEvent:recentEvent})});
  const fallbackImage="/static/assets/avatar.webp";
  const fallbackDimensions = () => {
    shell.dataset.mode=settings.mode;
    document.body.classList.toggle("fox-quiet",settings.quiet);
    shell.hidden=!settings.enabled;
    el("foxVisibility").textContent=settings.enabled?"Скрыть персонажа":"Показать персонажа";
    shell.style.setProperty("--fox-scale",settings.scale);
    el("foxModeCompact").setAttribute("aria-pressed",String(settings.mode==="compact"));
    el("foxModeFloating").setAttribute("aria-pressed",String(settings.mode==="floating"));
    el("foxModeExpanded").setAttribute("aria-pressed",String(settings.mode==="expanded"));
    el("foxContextMenu").querySelector('[data-fox-action="quiet"]')
      .setAttribute("aria-pressed",String(settings.quiet));
    const scaleControl=el("foxScale"),scaleValue=el("foxScaleValue");
    if(scaleControl)scaleControl.value=String(settings.scale);
    if(scaleValue)scaleValue.textContent=Math.round(settings.scale*100)+"%";
    document.querySelectorAll("[data-fox-behavior]").forEach(button=>
      button.setAttribute("aria-pressed",String(button.dataset.foxBehavior===settings.behavior)));
    const behaviorText={
      stationary:"Саюри стоит на выбранном месте.",
      wander:"Саюри свободно гуляет по безопасным точкам интерфейса.",
      follow:"Саюри следует за активным разделом.",
      event:"Саюри подходит ближе при важных событиях."
    };
    const behaviorStatus=el("foxBehaviorStatus");
    if(behaviorStatus)behaviorStatus.textContent=behaviorText[settings.behavior]||behaviorText.stationary;
  };
  const dimensions=()=> {
    // Visual scale only; pointer handlers clamp the actual transformed box.
    const rect=shell.getBoundingClientRect();
    return {w:rect.width*settings.scale,h:rect.height*settings.scale};
  };
  function clampPosition(x,y) {
    const {w,h}=dimensions(),margin=8;
    return {x:bound(x,margin,Math.max(margin,innerWidth-w-margin)),
      y:bound(y,margin,Math.max(margin,innerHeight-h-margin))};
  }
  function activeBounds() {
    const margin=innerWidth<768?12:24;
    const header=document.querySelector("main>header")?.getBoundingClientRect();
    const view=document.querySelector(".view.active")?.getBoundingClientRect();
    const left=Math.max(margin,view?.left??margin);
    const top=Math.max(margin,(header?.bottom??margin)+margin);
    const right=Math.min(innerWidth-margin,view?.right??innerWidth-margin);
    const bottom=Math.min(innerHeight-margin,view?.bottom??innerHeight-margin);
    return {left,top,right:Math.max(left+40,right),bottom:Math.max(top+40,bottom)};
  }
  function autonomousMove(x,y) {
    if(!settings.enabled||drag||!menu.hidden)return false;
    const currentX=parseFloat(shell.style.left)||0;
    const p=clampPosition(x,y);
    picture.style.setProperty("--fox-facing",p.x<currentX?"-1":"1");
    setMotionState("walking");
    shell.classList.add("fox-autonomous-move");
    shell.style.right="auto";shell.style.bottom="auto";
    shell.style.left=p.x+"px";shell.style.top=p.y+"px";
    clearTimeout(autoMoveTimer);
    autoMoveTimer=setTimeout(()=>{
      shell.classList.remove("fox-autonomous-move");
      setMotionState(motionFromRuntime(runtimeState));
    },900);
    return true;
  }
  function followActiveView() {
    if(settings.behavior!=="follow"||!settings.enabled)return;
    const {w,h}=dimensions(),b=activeBounds();
    const x=b.right-w-12;
    const y=moduleName==="chat" ? b.bottom-h-(innerWidth<768?92:102) :
      b.top+Math.max(12,(b.bottom-b.top-h)*.62);
    autonomousMove(x,y);
  }
  function wanderStep() {
    if(settings.behavior!=="wander"||document.hidden||
      matchMedia("(prefers-reduced-motion: reduce)").matches||
      Date.now()-lastManualMoveAt<6500)return;
    const {w,h}=dimensions(),b=activeBounds();
    const points=[[.82,.72],[.18,.68],[.28,.24],[.74,.27],[.5,.54]];
    const point=points[waypointIndex++%points.length];
    const spanX=Math.max(0,b.right-b.left-w),spanY=Math.max(0,b.bottom-b.top-h);
    autonomousMove(b.left+spanX*point[0],b.top+spanY*point[1]);
  }
  function clearBehaviorTimers() {
    if(behaviorTimer)clearInterval(behaviorTimer);
    if(returnTimer)clearTimeout(returnTimer);
    behaviorTimer=null;returnTimer=null;
  }
  function scheduleBehavior() {
    clearBehaviorTimers();
    if(settings.behavior==="wander"){
      setTimeout(wanderStep,1200);
      behaviorTimer=setInterval(wanderStep,7000);
    } else if(settings.behavior==="follow") {
      setTimeout(followActiveView,80);
    }
  }
  function approachEvent(type) {
    if(settings.behavior!=="event"||!settings.enabled)return;
    const {w,h}=dimensions(),b=activeBounds();
    const x=b.right-w-Math.max(16,(b.right-b.left)*.08);
    const y=b.top+Math.max(20,(b.bottom-b.top-h)*.42);
    if(!autonomousMove(x,y))return;
    const labels={
      task_finished:"Задача завершена.",
      task_failed:"В задаче возникла ошибка.",
      memory_updated:"Память обновлена.",
      contradiction_detected:"Обнаружено противоречие — нужна проверка."
    };
    message(labels[type]||"Появилось важное событие.");
    clearTimeout(returnTimer);
    returnTimer=setTimeout(()=>{if(settings.behavior==="event")position();},4500);
  }
  function position() {
    fallbackDimensions();
    const {w,h}=dimensions();
    const recommendedX=innerWidth-w-(innerWidth<768?12:24);
    const recommendedY=innerHeight-h-(
      moduleName==="chat" ? (innerWidth<768?95:105) :
      (innerWidth<768?16:24)
    );
    const p=clampPosition(settings.x===null ? recommendedX :
      settings.x*Math.max(0,innerWidth-w),
      settings.y===null ? recommendedY :
      settings.y*Math.max(0,innerHeight-h));
    shell.style.right="auto";shell.style.bottom="auto";
    shell.style.left=p.x+"px";shell.style.top=p.y+"px";
    return p;
  }
  function persistCoordinates() {
    const {w,h}=dimensions();
    const x=parseFloat(shell.style.left)||8,y=parseFloat(shell.style.top)||8;
    settings.x=bound(x/Math.max(1,innerWidth-w),0,1);
    settings.y=bound(y/Math.max(1,innerHeight-h),0,1);
  }
  async function saveSettings() {
    if (!usable()) return;
    if (savePending) { queuedSave=true;return; }
    savePending=true;
    try {
      const response=await fetch("/api/companion/settings",{
        method:"PUT",headers:{...authHeaders(),"Content-Type":"application/json"},
        body:JSON.stringify(settings)});
      if(!response.ok)throw Error("HTTP "+response.status);
    } catch {
      el("foxAppearanceStatus").textContent="Не удалось сохранить настройки; проверьте сервер.";
    } finally {
      savePending=false;
      if(queuedSave){queuedSave=false;saveSettings();}
    }
  }
  async function updateImage() {
    if (!usable()) return;
    const kind=settings.mode==="compact"?"portrait":"full";
    try {
      const response=await fetch("/api/companion/image/"+kind,{
        headers:authHeaders(),cache:"no-store"});
      if (!response.ok)throw Error("No uploaded image");
      const blob=await response.blob();
      const url=URL.createObjectURL(blob),old=lastObjectUrl;
      picture.src=url;
      lastObjectUrl=url;
      if(old)URL.revokeObjectURL(old);
    }catch{
      if(lastObjectUrl)URL.revokeObjectURL(lastObjectUrl);
      lastObjectUrl=null;
      picture.src=fallbackImage;
    }
    // The profile and dashboard reuse the same private portrait image.
    try{
      const portrait=await fetch("/api/companion/image/portrait",{
        headers:authHeaders(),cache:"no-store"});
      if(portrait.ok){
        const url=URL.createObjectURL(await portrait.blob());
        const old=portraitObjectUrl;portraitObjectUrl=url;
        document.querySelectorAll(".profile-avatar,.character-portrait")
          .forEach(node=>{node.src=url;});
        if(old)URL.revokeObjectURL(old);
      }
    }catch{}
  }
  async function init() {
    if(initialized || !usable())return;
    initialized=true;
    try {
      const response=await fetch("/api/companion/settings",{
        headers:authHeaders(),cache:"no-store"});
      if(response.ok){
        const value=(await response.json()).settings;
        for(const k of keys)if(Object.hasOwn(value,k))settings[k]=value[k];
      }
    }catch{}
    position();
    setMotionState("idle");
    scheduleBehavior();
    await updateImage();
    // Quiet state explicitly controls scripted greetings, not real warning events.
    el("foxAppearanceStatus").textContent="Образ хранится локально. Правый клик по Саюри открывает отдельное окно настроек.";
  }
  function message(text){
    if(settings.quiet && !/ошибка|нет связи|недоступн/i.test(text))return;
    panel.hidden=false;
    panel.style.transform="none";
    el("foxPanelMessage").textContent=text;
    const box=panel.getBoundingClientRect();
    const dx=box.left<8?8-box.left:box.right>innerWidth-8?innerWidth-8-box.right:0;
    const dy=box.top<8?8-box.top:box.bottom>innerHeight-8?innerHeight-8-box.bottom:0;
    panel.style.transform="translate("+dx+"px,"+dy+"px)";
  }
  function navigate(viewId){
    const button=el(({chat:"showChat",account:"showAccount",beyond:"showBeyond",files:"showFiles",
      work:"showWork",home:"showHome"})[viewId]);
    if(button)button.click();
    if(document.body.classList.contains("open")) el("menu")?.click();
  }
  const names={
    ready:"Готова помочь",reasoning:"Размышляет",researching:"Исследует",
    studying:"Изучает",memorizing:"Запоминает",linking:"Строит связи",
    verifying:"Проверяет",executing:"Выполняет задачу",attention:"Требует внимания",
    disconnected:"Нет подключения",completed:"Завершила"
  };
  async function statusInfo(){
    if(!usable()){message("Локальная сессия ещё не готова.");return}
    try{
      const response=await fetch("/api/runtime/status",{headers:authHeaders(),cache:"no-store"});
      if(!response.ok)throw Error("HTTP "+response.status);
      liveStatus=await response.json();
      setRuntimeState(liveStatus.sayuri?.state||"ready");
      const state=liveStatus.sayuri||{};
      message("Состояние: "+(names[state.state]||"Нет данных")+
        ". Активных операций: "+(state.active_jobs??"нет данных")+
        ". "+(state.description||""));
    }catch{message("Не удалось получить реальные события Саюри.");}
  }
  async function chooseMode(mode){
    settings.mode=mode;
    settings.enabled=true;
    position();
    await updateImage();
    await saveSettings();
  }
  async function chooseBehavior(behavior){
    if(!["stationary","wander","follow","event"].includes(behavior))return;
    settings.behavior=behavior;
    if(behavior==="stationary"){
      clearBehaviorTimers();
      persistCoordinates();
    }else{
      scheduleBehavior();
      if(behavior==="follow")followActiveView();
    }
    fallbackDimensions();
    await saveSettings();
  }
  const actions={
    chat:()=>navigate("chat"),
    voice:()=> {
      if(!("speechSynthesis" in window)){message("Синтез речи недоступен в браузере.");return}
      if(settings.quiet){message("Сначала выключите тихий режим.");return}
      speechSynthesis.cancel();
      const utterance=new SpeechSynthesisUtterance("Господин, я здесь, рядом с вами.");
      utterance.lang="ru-RU";utterance.rate=.95;
      speechSynthesis.speak(utterance);
    },
    activity:statusInfo,
    context:()=>message("Текущий раздел: "+(modules[moduleName]||"Не определён")+
      (selected?". Выбранный объект: "+selected.id:"")+
      ". Саюри не читает весь экран и другие приложения."),
    study:()=> {
      if(moduleName==="chat") {el("reviewChat")?.click();message(
        "Анализ диалога запрошен. Итог проверьте в кабинете, прежде чем добавлять в память.");}
      else message("Полноценный анализ выбранного документа с цитатами ещё не подключён.");
    },
    tasks:()=>statusInfo(),
    profile:()=>navigate("account"),
    settings:()=>openMenu(),
    quiet:async()=>{settings.quiet=!settings.quiet;fallbackDimensions();
      if(settings.quiet){panel.hidden=true;if("speechSynthesis" in window)speechSynthesis.cancel();}
      await saveSettings();},
    minimize:()=>chooseMode(settings.mode==="compact"?"floating":"compact"),
    reset:async()=>{settings.scale=1;settings.x=null;settings.y=null;
      position();await saveSettings();}
  };
  function closeMenu(restore=false){
    if(menu.hidden)return;
    menu.hidden=true;
    if(restore){
      const previous=settings.enabled?menuPreviouslyFocused:null;
      const fallback=settings.enabled?avatar:el("foxSettingsOpen");
      (previous&&previous.isConnected&&!previous.hidden?previous:fallback)?.focus();
    }
  }
  function openMenu() {
    menuPreviouslyFocused=document.activeElement;
    menu.hidden=false;
    menu.style.left="";
    menu.style.top="";
    requestAnimationFrame(()=>el("foxSettingsClose")?.focus());
  }
  menu.addEventListener("click",e=>{
    const item=e.target.closest("button[data-fox-action]");
    if(!item)return;
    const action=item.dataset.foxAction;
    actions[action]?.();
    if(!["quiet","minimize","reset"].includes(action))closeMenu();
  });
  avatar.addEventListener("contextmenu",e=>{
    e.preventDefault();e.stopPropagation();
    openMenu();
  });
  avatar.addEventListener("keydown",e=>{
    if(e.key==="ContextMenu"||(e.key==="F10"&&e.shiftKey)){
      e.preventDefault();
      openMenu();
    }
  });
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"){
      if(!menu.hidden){e.preventDefault();e.stopPropagation();closeMenu(true);}
      else if(!panel.hidden)panel.hidden=true;
    }
  });
  document.addEventListener("pointerdown",e=>{
    if(!menu.hidden && !menu.contains(e.target) && !avatar.contains(e.target))closeMenu();
  });
  el("foxPanelClose").onclick=()=>panel.hidden=true;
  // Long press 650ms; cancel on drag over 12px.
  avatar.addEventListener("pointerdown",e=>{
    if(e.button!==0)return;
    closeMenu();
    if(autoMoveTimer)clearTimeout(autoMoveTimer);
    shell.classList.remove("fox-autonomous-move");
    setMotionState(motionFromRuntime(runtimeState));
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,
      left:parseFloat(shell.style.left)||0,top:parseFloat(shell.style.top)||0,moved:false};
    avatar.setPointerCapture(e.pointerId);
    if(e.pointerType==="touch")longPress=setTimeout(()=>{
      if(drag&&!drag.moved){
        openMenu();drag=null;suppressClick=true;
      }
    },650);
  });
  function stopPress(){if(longPress)clearTimeout(longPress);longPress=null;}
  avatar.addEventListener("pointermove",e=>{
    if(!drag||drag.id!==e.pointerId)return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    if(Math.hypot(dx,dy)>12){drag.moved=true;stopPress();}
    if(!drag.moved)return;
    const p=clampPosition(drag.left+dx,drag.top+dy);
    shell.style.left=p.x+"px";shell.style.top=p.y+"px";
    panel.hidden=true;
  });
  avatar.addEventListener("pointerup",e=>{
    stopPress();
    if(drag?.id===e.pointerId){
      if(drag.moved){
        suppressClick=true;lastManualMoveAt=Date.now();
        persistCoordinates();saveSettings();
      }
      drag=null;
    }
  });
  avatar.addEventListener("pointercancel",()=>{stopPress();drag=null;});
  avatar.addEventListener("click",e=>{
    if(suppressClick){suppressClick=false;return}
    if(e.detail>=2)return;
    message("Господин, я рядом. Дважды нажмите, чтобы открыть чат, или нажмите правой кнопкой для настроек.");
  });
  avatar.addEventListener("dblclick",e=>{
    e.preventDefault();panel.hidden=true;navigate("chat");
  });
  avatar.addEventListener("wheel",e=>{
    if(!e.ctrlKey)return;
    e.preventDefault();
    settings.scale=bound(Math.round((settings.scale+(e.deltaY>0?-.05:.05))*100)/100,.7,1.4);
    position();saveSettings();
  },{passive:false});
  el("foxPackUpload").addEventListener("change",async e=>{
    const pack=e.target.files[0];
    if(!pack)return;
    el("foxPackName").textContent=pack.name;
    el("foxAppearanceStatus").textContent="Проверяю и загружаю комплект образов…";
    const form=new FormData();form.append("pack",pack);
    try{
      const result=await fetch("/api/companion/pack",{
        method:"POST",headers:authHeaders(),body:form});
      if(!result.ok)throw Error((await result.json()).detail||"HTTP "+result.status);
      settings.mode="floating";
      settings.enabled=true;
      position();
      await updateImage();
      await saveSettings();
      el("foxAppearanceStatus").textContent="Саюри появилась на экране в полный рост. Положение и размер можно менять.";
    }catch(error){
      el("foxAppearanceStatus").textContent="Комплект не установлен: "+error.message;
    }finally{e.target.value="";}
  });
  for(const [id,kind] of [["foxPortraitUpload","portrait"],["foxFullUpload","full"]]){
    el(id).addEventListener("change",async e=>{
      const file=e.target.files[0];if(!file)return;
      if(file.type!=="image/png"||file.size>9*1024*1024){
        el("foxAppearanceStatus").textContent="Нужен PNG размером до 9 МБ.";return;
      }
      const body=new FormData();body.append("image",file);
      try{
        const response=await fetch("/api/companion/image/"+kind,{
          method:"POST",headers:authHeaders(),body});
        if(!response.ok)throw Error((await response.json()).detail||response.status);
        el("foxAppearanceStatus").textContent=
          (kind==="portrait"?"Портрет":"Образ в полный рост")+" сохранён локально.";
        await updateImage();
      }catch(err){el("foxAppearanceStatus").textContent="Ошибка сохранения: "+err.message;}
      e.target.value="";
    });
  }
  el("foxVisibility").addEventListener("click",async()=>{
    settings.enabled=!settings.enabled;
    fallbackDimensions();
    if(!settings.enabled)panel.hidden=true;
    else position();
    await saveSettings();
  });
  el("foxPickPack").addEventListener("click",()=>el("foxPackUpload").click());
  el("foxResetPosition").addEventListener("click",async()=>{
    settings.x=null;settings.y=null;settings.scale=1;settings.enabled=true;
    position();await saveSettings();
    el("foxAppearanceStatus").textContent="Саюри возвращена в правый нижний угол.";
  });
  el("foxSettingsOpen").addEventListener("click",()=>openMenu());
  el("foxSettingsClose").addEventListener("click",()=>closeMenu(true));
  el("foxScale").addEventListener("input",e=>{
    settings.scale=bound(Number(e.target.value)||1,.7,1.4);
    fallbackDimensions();
    if(settings.enabled)position();
  });
  el("foxScale").addEventListener("change",()=>saveSettings());
  document.querySelectorAll("[data-fox-behavior]").forEach(button=>
    button.addEventListener("click",()=>chooseBehavior(button.dataset.foxBehavior)));
  for(const [id,kind] of [["foxModeCompact","compact"],
    ["foxModeFloating","floating"],["foxModeExpanded","expanded"]]){
    el(id).addEventListener("click",()=>chooseMode(kind));
  }
  window.addEventListener("resize",()=>{
    if(settings.behavior==="follow")followActiveView();else position();
    if(!menu.hidden)openMenu();
  });
  window.addEventListener("pagehide",()=>{
    clearBehaviorTimers();
    if(autoMoveTimer)clearTimeout(autoMoveTimer);
    if(motionTimer)clearTimeout(motionTimer);
    if(lastObjectUrl)URL.revokeObjectURL(lastObjectUrl);
    if(portraitObjectUrl)URL.revokeObjectURL(portraitObjectUrl);
  });
  position();
  const loginWait=setInterval(()=>{
    if(usable()){clearInterval(loginWait);init();}
  },350);
  if(usable())init();
})();
