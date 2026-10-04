/* BEYOND 2.5 — animation engine plus spatial awareness and collision avoidance. */
(() => {
  "use strict";
  const el = id => document.getElementById(id);
  const shell = el("foxShell"), avatar = el("foxAvatar"), picture = el("foxAvatarImage");
  const frameA=el("foxAvatarFrameA"),frameB=el("foxAvatarFrameB");
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
  let animationMeta={installed:false,states:{}},animationTimer=null,animationRequest=0,activeFrameLayer=0;
  const animationCache=new Map(),animationUrls=new Set();
  let sleepWatchTimer=null,lastInteractionAt=Date.now();
  let spatialObserver=null,spatialResizeObserver=null,spatialReflowTimer=null;
  const spatialPadding=12;
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
    working:"Работает",happy:"Радуется",attention:"Требует внимания",sleep:"Спит"
  };
  const animationStateForMotion={
    idle:"idle",walking:"walk",thinking:"think",reading:"read",
    working:"work",happy:"happy",attention:"attention",sleep:"sleep"
  };
  function stopFrameAnimation(){
    if(animationTimer)clearInterval(animationTimer);
    animationTimer=null;
  }
  function clearAnimationCache(){
    stopFrameAnimation();
    for(const url of animationUrls)URL.revokeObjectURL(url);
    animationUrls.clear();
    animationCache.clear();
    shell.classList.remove("fox-frame-engine");
    if(frameA){frameA.removeAttribute("src");frameA.style.opacity="0";}
    if(frameB){frameB.removeAttribute("src");frameB.style.opacity="0";}
  }
  async function loadAnimationMeta(){
    if(!usable())return;
    try{
      const response=await fetch("/api/companion/animation",{headers:authHeaders(),cache:"no-store"});
      if(!response.ok)throw Error("HTTP "+response.status);
      animationMeta=await response.json();
    }catch{
      animationMeta={installed:false,states:{}};
    }
    const summary=el("foxAnimationSummary");
    if(summary){
      const entries=Object.entries(animationMeta.states||{});
      summary.textContent=entries.length?
        "Установлено: "+entries.map(([state,info])=>state+" · "+info.frames+" кадр.").join("  "):
        "Покадровый пакет ещё не установлен — используется обычный PNG.";
    }
  }
  async function ensureAnimationFrames(state){
    if(animationCache.has(state))return animationCache.get(state);
    const info=animationMeta.states?.[state];
    if(!info?.frames)return [];
    const urls=[];
    for(let i=1;i<=info.frames;i++){
      const response=await fetch("/api/companion/animation/"+state+"/"+i,{
        headers:authHeaders(),cache:"no-store"});
      if(!response.ok)throw Error("HTTP "+response.status);
      const url=URL.createObjectURL(await response.blob());
      animationUrls.add(url);urls.push(url);
    }
    animationCache.set(state,urls);
    return urls;
  }
  function showAnimationFrame(url){
    if(!frameA||!frameB)return;
    const next=activeFrameLayer===0?frameA:frameB;
    const previous=activeFrameLayer===0?frameB:frameA;
    next.src=url;
    next.style.opacity="1";
    previous.style.opacity="0";
    activeFrameLayer=activeFrameLayer===0?1:0;
  }
  async function playAnimationState(motion){
    const request=++animationRequest;
    stopFrameAnimation();
    const state=animationStateForMotion[motion];
    if(settings.mode==="compact"||!animationMeta.installed||!animationMeta.states?.[state]){
      shell.classList.remove("fox-frame-engine");
      return;
    }
    try{
      const frames=await ensureAnimationFrames(state);
      if(request!==animationRequest||motionState!==motion||!frames.length)return;
      shell.classList.add("fox-frame-engine");
      let index=0;
      showAnimationFrame(frames[index]);
      if(frames.length>1){
        const fps=bound(Number(animationMeta.states[state].fps)||6,1,24);
        animationTimer=setInterval(()=>{
          if(motionState!==motion){stopFrameAnimation();return;}
          index=(index+1)%frames.length;showAnimationFrame(frames[index]);
        },Math.round(1000/fps));
      }
    }catch{
      shell.classList.remove("fox-frame-engine");
    }
  }
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
    playAnimationState(state);
    if(motionTimer)clearTimeout(motionTimer);
    motionTimer=null;
    if(temporary>0)motionTimer=setTimeout(()=>setMotionState(motionFromRuntime(runtimeState)),temporary);
  }
  function noteInteraction(){
    lastInteractionAt=Date.now();
    if(motionState==="sleep")setMotionState(motionFromRuntime(runtimeState));
  }
  function startSleepWatch(){
    if(sleepWatchTimer)clearInterval(sleepWatchTimer);
    sleepWatchTimer=setInterval(()=>{
      const canSleep=settings.enabled&&runtimeState==="ready"&&
        ["stationary","event"].includes(settings.behavior)&&menu.hidden&&!drag;
      if(canSleep&&Date.now()-lastInteractionAt>90000&&motionState==="idle")
        setMotionState("sleep");
    },15000);
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
  window.SayuriSpatial = Object.freeze({
    getSnapshot:()=>({
      ...updateSpatialStatus(),
      activeView:moduleName,
      behavior:settings.behavior,
      viewport:{width:innerWidth,height:innerHeight}
    }),
    resolve:(x,y)=>resolveSafePosition(Number(x)||0,Number(y)||0)
  });
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
  function rectVisible(rect){
    return !!rect&&rect.width>1&&rect.height>1&&rect.bottom>0&&rect.right>0&&
      rect.top<innerHeight&&rect.left<innerWidth;
  }
  function elementVisible(node){
    if(!node||node===shell||node===menu||node.closest?.("#foxShell,#foxContextMenu"))return false;
    const style=getComputedStyle(node);
    if(style.display==="none"||style.visibility==="hidden"||Number(style.opacity)===0)return false;
    return rectVisible(node.getBoundingClientRect());
  }
  function expandRect(rect,padding=spatialPadding){
    return {left:rect.left-padding,top:rect.top-padding,right:rect.right+padding,
      bottom:rect.bottom+padding,width:rect.width+padding*2,height:rect.height+padding*2};
  }
  function spatialProtectedRects(){
    const selectors=[
      "#sayuriSidebar","main>header",".compose",".drive-toolbar",
      ".sidebar-fixed-bottom",".sidebar-fixed-profile",
      "[role=dialog]:not(#foxContextMenu):not([hidden])",
      ".prepared-update:not([hidden])"
    ];
    const nodes=new Set();
    for(const selector of selectors)
      document.querySelectorAll(selector).forEach(node=>{if(elementVisible(node))nodes.add(node);});
    const focused=document.activeElement;
    if(focused&&focused!==document.body&&focused!==avatar&&elementVisible(focused))
      nodes.add(focused);
    return [...nodes].map(node=>({node,rect:expandRect(node.getBoundingClientRect())}));
  }
  function candidateRect(point){
    const {w,h}=dimensions();
    return {left:point.x,top:point.y,right:point.x+w,bottom:point.y+h,width:w,height:h};
  }
  function overlapArea(a,b){
    const width=Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left));
    const height=Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
    return width*height;
  }
  function spatialScore(point,desired,protectedRects){
    const box=candidateRect(point);
    const overlap=protectedRects.reduce((sum,item)=>sum+overlapArea(box,item.rect),0);
    const distance=Math.hypot(point.x-desired.x,point.y-desired.y);
    return overlap*1000+distance;
  }
  function spatialCandidates(desired){
    const {w,h}=dimensions(),b=activeBounds(),gap=14;
    const raw=[
      desired,
      {x:b.right-w-gap,y:b.bottom-h-gap},
      {x:b.left+gap,y:b.bottom-h-gap},
      {x:b.right-w-gap,y:b.top+gap},
      {x:b.left+gap,y:b.top+gap},
      {x:b.right-w-gap,y:b.top+(b.bottom-b.top-h)*.5},
      {x:b.left+gap,y:b.top+(b.bottom-b.top-h)*.5},
      {x:b.left+(b.right-b.left-w)*.5,y:b.bottom-h-gap}
    ];
    const result=[],seen=new Set();
    for(const item of raw){
      const point=clampPosition(item.x,item.y);
      const key=Math.round(point.x)+":"+Math.round(point.y);
      if(!seen.has(key)){seen.add(key);result.push(point);}
    }
    return result;
  }
  function resolveSafePosition(x,y){
    const desired=clampPosition(x,y);
    const protectedRects=spatialProtectedRects();
    let best=desired,bestScore=Infinity;
    for(const point of spatialCandidates(desired)){
      const score=spatialScore(point,desired,protectedRects);
      if(score<bestScore){bestScore=score;best=point;}
    }
    const safe=protectedRects.every(item=>overlapArea(candidateRect(best),item.rect)===0);
    shell.dataset.spatialSafe=String(safe);
    const state=el("foxSpatialState"),detail=el("foxSpatialDetail");
    if(state)state.textContent=safe?"Свободная зона":"Компромиссная позиция";
    if(detail)detail.textContent="Защищённых зон: "+protectedRects.length+
      (safe?". Важные элементы не перекрываются.":". Свободного места недостаточно.");
    return best;
  }
  function updateSpatialStatus(){
    const protectedRects=spatialProtectedRects();
    const box=shell.getBoundingClientRect();
    const safe=!settings.enabled||protectedRects.every(item=>overlapArea(box,item.rect)===0);
    shell.dataset.spatialSafe=String(safe);
    const state=el("foxSpatialState"),detail=el("foxSpatialDetail");
    if(state)state.textContent=safe?"Свободная зона":"Перекрытие интерфейса";
    if(detail)detail.textContent="Защищённых зон: "+protectedRects.length+
      (safe?". Положение безопасно.":". Автопозиционирование исправит это при следующем движении.");
    return {safe,protected:protectedRects.length};
  }
  function scheduleSpatialReflow(){
    clearTimeout(spatialReflowTimer);
    spatialReflowTimer=setTimeout(()=>{
      updateSpatialStatus();
      if(settings.behavior==="follow")followActiveView();
    },90);
  }
  function startSpatialAwareness(){
    if(spatialObserver)spatialObserver.disconnect();
    spatialObserver=new MutationObserver(scheduleSpatialReflow);
    spatialObserver.observe(document.body,{subtree:true,attributes:true,
      attributeFilter:["class","hidden","open","aria-expanded"]});
    if("ResizeObserver" in window){
      spatialResizeObserver=new ResizeObserver(scheduleSpatialReflow);
      for(const node of [document.querySelector("main"),el("sayuriSidebar"),document.querySelector(".compose")])
        if(node)spatialResizeObserver.observe(node);
    }
    updateSpatialStatus();
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
    const p=resolveSafePosition(x,y);
    const facing=p.x<currentX?"-1":"1";
    for(const layer of [picture,frameA,frameB])layer?.style.setProperty("--fox-facing",facing);
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
    const rawX=settings.x===null ? recommendedX :
      settings.x*Math.max(0,innerWidth-w);
    const rawY=settings.y===null ? recommendedY :
      settings.y*Math.max(0,innerHeight-h);
    const p=(settings.x===null&&settings.y===null)||settings.behavior!=="stationary"?
      resolveSafePosition(rawX,rawY):clampPosition(rawX,rawY);
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
    await updateImage();
    await loadAnimationMeta();
    setMotionState("idle");
    scheduleBehavior();
    startSleepWatch();
    startSpatialAwareness();
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
    playAnimationState(motionState);
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
    noteInteraction();
    if(!menu.hidden && !menu.contains(e.target) && !avatar.contains(e.target))closeMenu();
  });
  document.addEventListener("keydown",noteInteraction,{passive:true});
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
        persistCoordinates();saveSettings();updateSpatialStatus();
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
  el("foxPickAnimationPack").addEventListener("click",()=>el("foxAnimationPackUpload").click());
  el("foxAnimationPackUpload").addEventListener("change",async e=>{
    const pack=e.target.files[0];if(!pack)return;
    el("foxAnimationPackName").textContent=pack.name;
    el("foxAnimationSummary").textContent="Проверяю и устанавливаю покадровые анимации…";
    const body=new FormData();body.append("pack",pack);
    try{
      const response=await fetch("/api/companion/animation-pack",{
        method:"POST",headers:authHeaders(),body});
      if(!response.ok)throw Error((await response.json()).detail||"HTTP "+response.status);
      clearAnimationCache();
      animationMeta=await response.json();
      await loadAnimationMeta();
      playAnimationState(motionState);
      el("foxAnimationSummary").textContent=
        "Animation Engine готов: "+Object.entries(animationMeta.states||{})
          .map(([state,info])=>state+" · "+info.frames+" кадр.").join("  ");
    }catch(error){
      el("foxAnimationSummary").textContent="Пакет анимаций не установлен: "+error.message;
    }finally{e.target.value="";}
  });
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
    updateSpatialStatus();
    if(!menu.hidden)openMenu();
  });
  window.addEventListener("pagehide",()=>{
    clearBehaviorTimers();
    if(autoMoveTimer)clearTimeout(autoMoveTimer);
    if(motionTimer)clearTimeout(motionTimer);
    if(sleepWatchTimer)clearInterval(sleepWatchTimer);
    if(spatialObserver)spatialObserver.disconnect();
    if(spatialResizeObserver)spatialResizeObserver.disconnect();
    clearTimeout(spatialReflowTimer);
    clearAnimationCache();
    if(lastObjectUrl)URL.revokeObjectURL(lastObjectUrl);
    if(portraitObjectUrl)URL.revokeObjectURL(portraitObjectUrl);
  });
  position();
  const loginWait=setInterval(()=>{
    if(usable()){clearInterval(loginWait);init();}
  },350);
  if(usable())init();
})();
