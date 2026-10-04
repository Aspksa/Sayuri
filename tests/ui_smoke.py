"""Browser smoke tests: pixel widths, keyboard drawer, footer, real backend startup."""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
SITE="http://127.0.0.1:8765"


def wait_for_backend():
    for _ in range(70):
        try:
            with urllib.request.urlopen(SITE+"/api/health",timeout=1) as response:
                if response.status==200:return
        except Exception:time.sleep(.2)
    raise AssertionError("Sayuri backend did not start")


def run():
    with tempfile.TemporaryDirectory(prefix="sayuri-ui-ci-") as folder:
        env={**os.environ,"SAYURI_DATA_DIR":str(Path(folder)/"data"),
             "SAYURI_PROJECTS_DIR":str(Path(folder)/"cloud"),
             "SAYURI_LOCAL_ACCESS":"1","SAYURI_HOST":"127.0.0.1"}
        server=subprocess.Popen([sys.executable,"run.py"],cwd=ROOT,env=env,
                                stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            wait_for_backend()
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                try:
                    for width in (360,390,768,1024,1440):
                        context=browser.new_context(viewport={"width":width,"height":900},
                                                    reduced_motion="reduce")
                        page=context.new_page()
                        errors=[]
                        page.on("pageerror",lambda error:errors.append(str(error)))
                        page.goto(SITE,wait_until="domcontentloaded")
                        page.wait_for_selector("#showAccount")
                        # Exactly one coherent stylesheet, no three generations of overrides.
                        assert page.locator('link[href*="theme.css"]').count()==1,width
                        assert page.locator("head style").count()==0,width
                        page.wait_for_function("Array.from(document.styleSheets).some(s => s.href && s.href.includes('theme.css'))")
                        assert page.locator("#accountView").is_visible(),width
                        assert page.locator("#accountUiVersion").inner_text()=="4.12.0",width
                        assert page.locator("#accountProjectVersion").inner_text()=="4.12.0",width
                        assert page.locator("#accountCoreVersion").inner_text()=="3.4.0",width
                        assert page.locator("#accountMemoryVersion").inner_text()=="3.0.0",width
                        assert page.locator("#accountKnowledgeVersion").inner_text()=="3.1.0",width
                        assert page.locator("#accountInstinctVersion").inner_text()=="3.2.0",width
                        assert page.locator("#accountPersonalityVersion").inner_text()=="3.0.0",width
                        assert page.locator("#accountPersonaBaseVersion").inner_text()=="2.0.0",width
                        assert page.locator("#instinctBlock").is_visible(),width
                        assert page.locator("#instinctTestButton").is_visible(),width
                        page.wait_for_function("() => document.querySelector('#instinctSummary').children.length >= 5")
                        page.wait_for_function("() => document.querySelectorAll('#instinctCards .instinct32-card').length >= 9")
                        assert page.locator("#instinctSummary").is_visible(),width
                        assert page.locator("#instinctCards").is_visible(),width
                        protection=page.locator("#instinctCards .instinct32-card[data-instinct-id='data_protection']")
                        assert protection.is_visible(),width
                        assert "неизменяемый" in protection.inner_text(),width
                        assert protection.locator("[data-instinct-strength]").count()==0,width
                        assert page.locator("#libraryBlock").is_visible(),width
                        assert page.locator("#knowledgeSummary").is_visible(),width
                        assert page.locator("#knowledgeSearch").is_visible(),width
                        assert page.locator("#knowledgeSources").is_visible(),width
                        assert page.locator("#knowledgeConflicts").is_visible(),width
                        assert page.locator("#knowledgeLinkForm").is_visible(),width
                        assert page.locator("#memoryBlock").is_visible(),width
                        assert page.locator("#memorySummary").is_visible(),width
                        assert page.locator("#memoryScope").is_visible(),width
                        assert page.locator("#memoryType").is_visible(),width
                        page.locator("#memoryScope").select_option("project")
                        assert page.locator("#memoryProjectField").is_visible(),width
                        page.locator("#memoryScope").select_option("temporary")
                        assert page.locator("#memoryTtlField").is_visible(),width
                        page.locator("#memoryScope").select_option("personal")
                        assert not page.locator("#memoryProjectField").is_visible(),width
                        assert not page.locator("#memoryTtlField").is_visible(),width
                        page.locator("#instinctTestText").fill("Удали старые файлы проекта и отправь архив в облако")
                        page.locator("#instinctTestButton").click()
                        page.wait_for_function("() => document.querySelector('#instinctTestResult strong')?.textContent.includes('подтверждение')")
                        assert "Защита данных" in page.locator("#instinctTestResult").inner_text(),width
                        assert page.locator("#instinctEvents .instinct32-event").count()>=1,width
                        if width in (390,1440):
                            folder=ROOT/"ui-previews"
                            folder.mkdir(exist_ok=True)
                            page.locator("#accountView").screenshot(path=str(folder/("account-"+str(width)+".png")))
                        page.locator("#accountOpenBeyond").click()
                        assert page.locator("#beyondView").is_visible(),width
                        assert page.locator("#foxSettingsOpen").is_visible(),width
                        assert not page.locator("#foxContextMenu").is_visible(),width
                        page.locator("#foxSettingsOpen").click()
                        assert page.locator("#foxContextMenu").is_visible(),width
                        assert page.locator("#foxPackUpload").count()==1,width
                        assert page.locator("#foxPortraitUpload").count()==1,width
                        assert page.locator("#foxFullUpload").count()==1,width
                        assert page.locator("#foxPickPack").is_visible(),width
                        assert page.locator("#foxPickPack").inner_text().startswith("↑ Выбрать ZIP"),width
                        assert page.locator("#foxPickAnimationPack").is_visible(),width
                        assert page.locator("#foxAnimationSummary").is_visible(),width
                        assert page.locator("#foxScale").is_visible(),width
                        for behavior in ("Stationary","Wander","Follow","Event"):
                            assert page.locator("#foxBehavior"+behavior).is_visible(),(width,behavior)
                        page.locator("#foxBehaviorFollow").click()
                        assert page.locator("#foxBehaviorFollow").get_attribute("aria-pressed")=="true",width
                        page.locator("#foxBehaviorStationary").click()
                        assert page.locator("#foxBehaviorStationary").get_attribute("aria-pressed")=="true",width
                        assert page.locator("#foxMotionState").is_visible(),width
                        assert page.locator("#foxSpatialState").is_visible(),width
                        assert page.locator("#foxContextState").is_visible(),width
                        assert page.locator("#foxPresenceState").is_visible(),width
                        assert page.locator("#foxVoiceImportant").is_visible(),width
                        assert page.locator("#foxVoiceImportant").get_attribute("aria-pressed")=="true",width
                        page.locator("#foxVoiceImportant").click()
                        voice_off=page.evaluate("window.SayuriPresence.getSnapshot()")
                        assert voice_off["voiceImportant"] is False,(width,voice_off)
                        page.locator("#foxVoiceImportant").click()
                        voice_on=page.evaluate("window.SayuriPresence.getSnapshot()")
                        assert voice_on["voiceImportant"] is True,(width,voice_on)
                        for presence in ("Calm","Normal","Lively"):
                            assert page.locator("#foxPresence"+presence).is_visible(),(width,presence)
                        assert page.evaluate("typeof window.SayuriReactions.getSnapshot==='function'"),width
                        assert page.evaluate("typeof window.SayuriPresence.getSnapshot==='function'"),width
                        spatial=page.evaluate("window.SayuriSpatial.getSnapshot()")
                        assert spatial["protected"]>=1,(width,spatial)
                        assert spatial["viewport"]["width"]==width,(width,spatial)
                        page.locator("#foxPresenceCalm").click()
                        assert page.locator("#foxPresenceCalm").get_attribute("aria-pressed")=="true",width
                        calm=page.evaluate("window.SayuriPresence.getSnapshot()")
                        assert calm["mode"]=="calm",(width,calm)
                        before=calm["sequence"]
                        page.evaluate("window.SayuriPresence.test('document_opened')")
                        after=page.evaluate("window.SayuriPresence.getSnapshot()")
                        assert after["sequence"]==before,(width,before,after)
                        page.evaluate("window.SayuriPresence.test('task_failed',true)")
                        forced=page.evaluate("window.SayuriPresence.getSnapshot()")
                        assert forced["sequence"]==before+1,(width,before,forced)
                        page.locator("#foxPresenceNormal").click()
                        assert page.locator("#foxPresenceNormal").get_attribute("aria-pressed")=="true",width
                        assert page.locator("#foxAvatarFrameA").count()==1,width
                        assert page.locator("#foxAvatarFrameB").count()==1,width
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:personality',{detail:{state:'analytical'}}))")
                        page.wait_for_function("() => document.querySelector('#foxShell')?.dataset.personalityState === 'analytical'")
                        assert page.locator("#foxShell").get_attribute("data-personality-state")=="analytical",width
                        personality_presence=page.evaluate("window.SayuriPresence.getSnapshot()")
                        assert personality_presence["personalityState"]=="analytical",(width,personality_presence)
                        page.wait_for_function("() => document.querySelector('#foxShell')?.dataset.motionState === 'thinking'")
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:runtime',{detail:{state:'reasoning'}}))")
                        page.wait_for_function("() => document.querySelector('#foxShell')?.dataset.motionState === 'thinking'")
                        assert page.locator("#foxShell").get_attribute("data-motion-state")=="thinking",width
                        page.wait_for_function("() => document.querySelector('#foxMotionState')?.textContent === 'Размышляет'")
                        assert page.locator("#foxMotionState").inner_text()=="Размышляет",width
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:runtime',{detail:{state:'completed'}}))")
                        page.wait_for_function("() => document.querySelector('#foxShell')?.dataset.motionState === 'happy'")
                        assert page.locator("#foxShell").get_attribute("data-motion-state")=="happy",width
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'document_opened',module:'files',entity_type:'document',entity_id:'demo'}}))")
                        page.wait_for_function("() => document.querySelector('#foxShell')?.dataset.motionState === 'reading'")
                        assert page.locator("#foxShell").get_attribute("data-motion-state")=="reading",width
                        reaction=page.evaluate("window.SayuriReactions.getSnapshot()")
                        assert reaction and reaction["entity_type"]=="document",(width,reaction)
                        assert page.locator("#foxContextState").inner_text()=="Документ",width
                        page.evaluate("""() => {
                          const target=document.createElement('div');
                          target.id='contextReactionTarget';
                          target.dataset.sayuriEntityType='document';
                          target.dataset.sayuriEntityId='docs/exact-demo.txt';
                          target.dataset.sayuriModule='files';
                          Object.assign(target.style,{position:'fixed',left:'40px',top:'260px',width:'180px',
                            height:'70px',zIndex:'2',pointerEvents:'none'});
                          document.body.append(target);
                          window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{
                            type:'document_opened',module:'files',entity_type:'file',
                            entity_id:'docs/exact-demo.txt'}}));
                        }""")
                        exact_reaction=page.evaluate("window.SayuriReactions.getSnapshot()")
                        assert exact_reaction and exact_reaction["exact"] is True,(width,exact_reaction)
                        page.evaluate("document.getElementById('contextReactionTarget')?.remove()")
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'task_failed',module:'chat',entity_type:'task',entity_id:'smoke-task'}}))")
                        task_reaction=page.evaluate("window.SayuriReactions.getSnapshot()")
                        assert task_reaction and task_reaction["title"]=="Ошибка задачи",(width,task_reaction)
                        assert page.locator("#foxShell").get_attribute("data-motion-state")=="attention",width
                        page.locator("#foxResetPosition").click()
                        reset_fox=page.locator("#foxAvatar").bounding_box()
                        assert reset_fox,(width,reset_fox)
                        assert reset_fox["x"]>=-1 and reset_fox["x"]+reset_fox["width"]<=width+1,(width,reset_fox)
                        assert reset_fox["y"]>=-1 and reset_fox["y"]+reset_fox["height"]<=900+1,(width,reset_fox)
                        reset_spatial=page.evaluate("window.SayuriSpatial.getSnapshot()")
                        assert reset_spatial and reset_spatial["protected"]>=1,(width,reset_spatial)
                        page.locator("#foxVisibility").click()
                        assert not page.locator("#foxAvatar").is_visible(),width
                        page.locator("#foxVisibility").click()
                        assert page.locator("#foxAvatar").is_visible(),width
                        page.locator("#foxSettingsClose").click()
                        assert not page.locator("#foxContextMenu").is_visible(),width
                        page.evaluate("document.getElementById('showChat').click()")
                        page.wait_for_timeout(120)
                        spatial_chat=page.evaluate("window.SayuriSpatial.getSnapshot()")
                        assert spatial_chat["protected"]>=2,(width,spatial_chat)
                        fox_box=page.locator("#foxShell").bounding_box()
                        compose_box=page.locator(".compose").bounding_box()
                        assert fox_box and compose_box,(width,fox_box,compose_box)
                        separated=(fox_box["x"]+fox_box["width"]<=compose_box["x"] or
                                   compose_box["x"]+compose_box["width"]<=fox_box["x"] or
                                   fox_box["y"]+fox_box["height"]<=compose_box["y"] or
                                   compose_box["y"]+compose_box["height"]<=fox_box["y"])
                        assert separated,(width,fox_box,compose_box)
                        page.evaluate("document.getElementById('showBeyond').click()")
                        assert page.locator(".advanced-settings").count()==1,width
                        assert not page.locator(".advanced-settings").evaluate("(e)=>e.open"),width
                        bg=page.evaluate("getComputedStyle(document.documentElement).backgroundColor")
                        assert bg.startswith("rgb("),bg
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2"),width
                        if width in (390,1440):
                            folder=ROOT/"ui-previews"
                            folder.mkdir(exist_ok=True)
                            page.locator("#beyondView").screenshot(path=str(folder/("character-settings-entry-"+str(width)+".png")))
                        if width in (390,1440):
                            snapshot=ROOT/"ui-previews"/("beyond-"+str(width)+".png")
                            snapshot.parent.mkdir(exist_ok=True)
                            page.locator("#beyondView").screenshot(path=str(snapshot))
                            if width==1440:
                                page.screenshot(path=str(ROOT/"ui-previews"/"desktop-overview.png"))
                        
                        page.locator("#beyondBackAccount").click()
                        assert page.locator("#accountView").is_visible(),width
                        page.locator("#accountOpenUpdates").click()
                        assert page.locator("#updatesView").is_visible(),width
                        page.wait_for_function("document.querySelector('#runningVersion').textContent.includes('4.12.0')")
                        assert "Sayuri" in page.locator("#runningFolder").inner_text(),width
                        assert page.locator("#updatesBackCabinet").is_visible(),width
                        if width in (390,1440):
                            page.locator("#updatesView").screenshot(
                                path=str(ROOT/"ui-previews"/("updates-"+str(width)+".png")))
                        page.locator("#updatesBackCabinet").click()
                        assert page.locator("#accountView").is_visible(),width
                        assert page.locator("#showUpdates").count()==1,width
                        # Memory 3.0 functional smoke: create then remove a working note.
                        memory_suffix=page.evaluate("Date.now().toString().slice(-7)")
                        memory_text="UI Memory "+str(width)+" "+memory_suffix
                        page.locator("#memoryScope").select_option("working")
                        page.locator("#memoryType").select_option("note")
                        page.locator("#memoryPriority").select_option("4")
                        page.locator("#fact").fill(memory_text)
                        page.locator("#memoryForm button[type='submit']").click()
                        page.wait_for_function("""text => Array.from(document.querySelectorAll('#memories .memory3-card-text'))
                          .some(node => node.textContent === text)""",arg=memory_text)
                        memory_card=page.locator("#memories .memory3-card").filter(has_text=memory_text).first
                        assert memory_card.get_attribute("data-scope")=="working",(width,memory_text)
                        # Knowledge 3.1 indexes the confirmed memory and finds it locally.
                        page.locator("#knowledgeSearch").fill(memory_text)
                        page.locator("#knowledgeSearchButton").click()
                        page.wait_for_function("""text => Array.from(document.querySelectorAll('#knowledgeLibrary .knowledge31-result p'))
                          .some(node => node.textContent === text)""",arg=memory_text)
                        assert "Knowledge 3.1" in page.locator("#knowledgeSearchStatus").inner_text(),width
                        page.wait_for_function("() => Number(document.querySelector('#knowledgeSourceCount')?.textContent || 0) >= 1")
                        assert int(page.locator("#knowledgeSourceCount").inner_text())>=1,width
                        page.once("dialog",lambda dialog:dialog.accept())
                        memory_card.locator("button").filter(has_text="Удалить").click()
                        page.wait_for_function("""text => !Array.from(document.querySelectorAll('#memories .memory3-card-text'))
                          .some(node => node.textContent === text)""",arg=memory_text)
                        page.locator("#memoryScope").select_option("personal")
                        page.evaluate("document.getElementById('showFiles').click()")
                        page.wait_for_timeout(120)
                        assert page.locator("#filesView").is_visible(),width
                        assert page.locator("#documentsWorkspace").is_visible(),width
                        assert page.locator("#driveSearch").is_visible(),width
                        assert page.locator("#docsOpenWork").is_visible(),width
                        assert page.locator("#docsOpenHome").is_visible(),width
                        assert page.locator("#documentsLibrary").is_visible(),width
                        assert page.locator("#documentsFolderTree").is_visible(),width
                        assert page.locator("#documentsCurrentFolder").inner_text()=="Мои файлы",width
                        assert page.locator("#documentsParentFolder").is_disabled(),width
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2"),width
                        page.locator("#driveNewFolder").click()
                        assert page.locator("#newFolderDialog").is_visible(),width
                        suffix=page.evaluate("Date.now().toString().slice(-7)")
                        folder_name="UI Test "+str(width)+" "+suffix
                        page.locator("#newFolderName").fill(folder_name)
                        page.locator("#newFolderSubmit").click()
                        page.wait_for_function("""name => Array.from(document.querySelectorAll('#driveFiles .drive-file-name'))
                          .some(node => node.textContent === name)""",arg=folder_name)
                        assert not page.locator("#newFolderDialog").is_visible(),width
                        assert folder_name in page.locator("#documentsActionStatus").inner_text(),width
                        folder_card=page.locator("#driveFiles .drive-file").filter(has_text=folder_name).first
                        assert folder_card.get_attribute("data-kind")=="folder",(width,folder_name)

                        # Folder Identity: icon, accent and description persist in the local profile.
                        folder_card.locator("button[aria-label^='Действия:']").click()
                        page.locator("[data-doc-action='customize']").click()
                        page.locator("#folderIdentityDialog").wait_for(state="visible")
                        assert page.locator("#folderIdentityDialog").is_visible(),width
                        page.locator("[data-folder-icon='research']").click()
                        page.locator("[data-folder-color='cyan']").click()
                        description="Материалы UI "+str(width)
                        page.locator("#folderIdentityDescription").fill(description)
                        page.locator("#folderIdentitySubmit").click()
                        page.wait_for_function("""name => {
                          const card=Array.from(document.querySelectorAll('#driveFiles .drive-file'))
                            .find(node=>node.querySelector('.drive-file-name')?.textContent===name);
                          return card?.dataset.folderColor==='cyan' &&
                            card.querySelector('.drive-file-icon')?.textContent.includes('🔬');
                        }""",arg=folder_name)
                        folder_card=page.locator("#driveFiles .drive-file").filter(has_text=folder_name).first
                        assert description in folder_card.inner_text(),width

                        folder_card.locator("button").filter(has_text="Открыть").click()
                        page.wait_for_function("name => document.querySelector('#documentsCurrentFolder').textContent === name",arg=folder_name)
                        page.wait_for_function("() => document.querySelector('#documentsCurrentFolderCard')?.dataset.folderColor === 'cyan'")
                        assert not page.locator("#documentsParentFolder").is_disabled(),width
                        assert folder_name in page.locator("#documentsCurrentPath").inner_text(),width
                        assert page.locator("#documentsCurrentFolderCard").get_attribute("data-folder-color")=="cyan",width
                        assert "🔬" in page.locator("#documentsCurrentFolderIcon").inner_text(),width
                        assert page.locator("#documentsCurrentDescription").inner_text()==description,width
                        assert page.locator("#documentsFolderCount").inner_text()=="0",width
                        page.locator("#documentsParentFolder").click()
                        page.wait_for_function("() => document.querySelector('#documentsCurrentFolder').textContent === 'Мои файлы'")
                        # Context actions: pin, rename, move and cleanup.
                        folder_card=page.locator("#driveFiles .drive-file").filter(has_text=folder_name).first
                        folder_card.locator("button[aria-label^='Действия:']").click()
                        assert page.locator("#documentsContextMenu").is_visible(),width
                        page.locator("[data-doc-action='pin']").click()
                        assert page.locator("#documentsPinned").is_visible(),width
                        assert folder_name in page.locator("#documentsPinned").inner_text(),width
                        renamed=folder_name+" Renamed"
                        folder_card=page.locator("#driveFiles .drive-file").filter(has_text=folder_name).first
                        folder_card.locator("button[aria-label^='Действия:']").click()
                        page.locator("[data-doc-action='rename']").click()
                        assert page.locator("#renameItemDialog").is_visible(),width
                        page.locator("#renameItemName").fill(renamed)
                        page.locator("#renameItemSubmit").click()
                        page.wait_for_function("""name => Array.from(document.querySelectorAll('#driveFiles .drive-file-name'))
                          .some(node => node.textContent === name)""",arg=renamed)
                        assert renamed in page.locator("#documentsPinned").inner_text(),width
                        target_name="Move Target "+str(width)+" "+suffix
                        page.locator("#driveNewFolder").click()
                        page.locator("#newFolderName").fill(target_name)
                        page.locator("#newFolderSubmit").click()
                        page.wait_for_function("""name => Array.from(document.querySelectorAll('#driveFiles .drive-file-name'))
                          .some(node => node.textContent === name)""",arg=target_name)
                        renamed_card=page.locator("#driveFiles .drive-file").filter(has_text=renamed).first
                        renamed_card.locator("button[aria-label^='Действия:']").click()
                        page.locator("[data-doc-action='move']").click()
                        page.locator("#moveItemDialog").wait_for(state="visible")
                        page.wait_for_function("name => Array.from(document.querySelectorAll('#moveItemDestination option')).some(node => node.textContent.includes(name))",arg=target_name)
                        assert page.locator("#moveItemDialog").is_visible(),width
                        assert page.locator("#moveItemDestination option").filter(has_text=target_name).count()==1,width
                        page.locator("#moveItemCancel").click()
                        renamed_card=page.locator("#driveFiles .drive-file").filter(has_text=renamed).first
                        target_card=page.locator("#driveFiles .drive-file").filter(has_text=target_name).first
                        source_path=renamed_card.get_attribute("data-drive-path")
                        target_path=target_card.get_attribute("data-drive-path")
                        assert source_path and target_path,(width,source_path,target_path)
                        page.evaluate("""args => {
                          const cards=Array.from(document.querySelectorAll('#driveFiles .drive-file'));
                          const source=cards.find(node=>node.dataset.drivePath===args.source);
                          const target=cards.find(node=>node.dataset.drivePath===args.target);
                          if(!source||!target)throw new Error('DnD cards not found');
                          const transfer=new DataTransfer();
                          source.dispatchEvent(new DragEvent('dragstart',{
                            bubbles:true,cancelable:true,dataTransfer:transfer
                          }));
                          target.dispatchEvent(new DragEvent('dragover',{
                            bubbles:true,cancelable:true,dataTransfer:transfer
                          }));
                          target.dispatchEvent(new DragEvent('drop',{
                            bubbles:true,cancelable:true,dataTransfer:transfer
                          }));
                          source.dispatchEvent(new DragEvent('dragend',{
                            bubbles:true,cancelable:true,dataTransfer:transfer
                          }));
                        }""",{"source":source_path,"target":target_path})
                        page.wait_for_function("name => !Array.from(document.querySelectorAll('#driveFiles .drive-file-name')).some(node => node.textContent === name)",arg=renamed)
                        target_card=page.locator("#driveFiles .drive-file").filter(has_text=target_name).first
                        target_card.locator("button").filter(has_text="Открыть").click()
                        page.wait_for_function("name => document.querySelector('#documentsCurrentFolder').textContent === name",arg=target_name)
                        page.wait_for_function("""name => Array.from(document.querySelectorAll('#driveFiles .drive-file-name'))
                          .some(node => node.textContent === name)""",arg=renamed)
                        assert page.locator("#driveFiles .drive-file").filter(has_text=renamed).count()==1,(width,renamed)
                        # Delete moved test folder, then its empty destination; this keeps smoke tests repeatable.
                        moved_card=page.locator("#driveFiles .drive-file").filter(has_text=renamed).first
                        moved_card.locator("button[aria-label^='Действия:']").click()
                        page.once("dialog",lambda dialog:dialog.accept())
                        page.locator("[data-doc-action='delete']").click()
                        page.wait_for_function("name => !Array.from(document.querySelectorAll('#driveFiles .drive-file-name')).some(node => node.textContent === name)",arg=renamed)
                        page.locator("#documentsParentFolder").click()
                        page.wait_for_function("() => document.querySelector('#documentsCurrentFolder').textContent === 'Мои файлы'")
                        target_card=page.locator("#driveFiles .drive-file").filter(has_text=target_name).first
                        target_card.locator("button[aria-label^='Действия:']").click()
                        page.once("dialog",lambda dialog:dialog.accept())
                        page.locator("[data-doc-action='delete']").click()
                        page.wait_for_function("name => !Array.from(document.querySelectorAll('#driveFiles .drive-file-name')).some(node => node.textContent === name)",arg=target_name)
                        page.locator("#docsListView").click()
                        assert page.locator("#docsListView").get_attribute("aria-pressed")=="true",width
                        assert "drive-list-mode" in (page.locator("#driveFiles").get_attribute("class") or ""),width
                        page.locator("#docsGridView").click()
                        assert page.locator("#docsGridView").get_attribute("aria-pressed")=="true",width
                        browser_box=page.locator(".documents-browser").bounding_box()
                        aside_box=page.locator(".documents-aside").bounding_box()
                        assert browser_box and aside_box,(width,browser_box,aside_box)
                        if width<=1100:
                            assert aside_box["y"]>=browser_box["y"]+browser_box["height"]-2,(width,browser_box,aside_box)
                        else:
                            assert aside_box["x"]>=browser_box["x"]+browser_box["width"]-2,(width,browser_box,aside_box)
                        if width in (390,1440):
                            page.locator("#filesView").screenshot(path=str(ROOT/"ui-previews"/("documents-"+str(width)+".png")))
                        page.evaluate("document.getElementById('showAccount').click()")
                        assert page.locator("#accountView").is_visible(),width
                        if width<=767:
                            assert not page.locator("#sayuriSidebar").is_visible() or (
                                page.locator("#sayuriSidebar").bounding_box()["x"]<0),width
                            page.click("#menu")
                            page.wait_for_timeout(300)
                            sidebar=page.locator("#sayuriSidebar").bounding_box()
                            assert abs(sidebar["width"]-min(width*.88,320))<2,(width,sidebar)
                            assert sidebar["x"]>=-1,sidebar
                            # The fixed footer must remain visible after opening all diagnostics.
                            for id in ("sayuriStatusDetails","networkDetails","cloudDetails"):
                                page.locator("#"+id+" summary").click()
                            foot=page.locator(".sidebar-fixed-bottom").bounding_box()
                            nav=page.locator("#showChat").bounding_box()
                            assert nav and nav["y"]<foot["y"],(width,nav,foot)
                            assert foot["y"]+foot["height"]<=903,foot
                            if width==390:
                                snap=ROOT/"ui-previews"/"mobile-menu.png"
                                page.screenshot(path=str(snap))
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(50)
                            assert not page.locator("body").get_attribute("class") or (
                                "open" not in (page.locator("body").get_attribute("class") or "").split())
                            assert page.evaluate("document.activeElement.id")=="menu"
                        else:
                            expected=260 if width<=1023 else 280
                            panel=page.locator("#sayuriSidebar").bounding_box()
                            assert abs(panel["width"]-expected)<2,(width,panel)
                            for id in ("sayuriStatusDetails","networkDetails","cloudDetails"):
                                page.locator("#"+id+" summary").click()
                            foot=page.locator(".sidebar-fixed-bottom").bounding_box()
                            nav=page.locator("#showChat").bounding_box()
                            assert nav and nav["y"]<foot["y"],(width,nav,foot)
                            assert foot["y"]+foot["height"]<=903,foot
                            page.locator("#collapseSidebar").click()
                            page.wait_for_timeout(300)
                            assert abs(page.locator("#sayuriSidebar").bounding_box()["width"]-72)<2,width
                            page.locator("#showHome").click()
                            assert page.locator("#homeView").is_visible()
                            assert page.locator("#showHome").get_attribute("aria-current")=="page"
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2"),width
                        # BEYOND: one persistent character across SPA navigation.
                        fox=page.locator("#foxAvatar")
                        assert fox.count()==1 and fox.is_visible(),width
                        fox.click(button="right")
                        assert page.locator("#foxContextMenu").is_visible(),width
                        page.keyboard.press("Escape")
                        assert not page.locator("#foxContextMenu").is_visible(),width
                        if width in (390,1440):
                            original=fox.bounding_box()
                            page.mouse.move(original["x"]+original["width"]/2,original["y"]+original["height"]/2)
                            page.mouse.down()
                            page.mouse.move(15,35,steps=5)
                            page.mouse.up()
                            changed=fox.bounding_box()
                            assert changed["x"]>=0 and changed["y"]>=0,(width,changed)
                            assert changed["x"]+changed["width"]<=width+1,changed
                        assert not errors,(width,errors)
                        context.close()
                    print("Browser UI PASS: 360, 390, 768, 1024, 1440; focus, drawer, collapse, footer")
                finally:browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill()


if __name__=="__main__":run()
