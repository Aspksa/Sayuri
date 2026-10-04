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
                        assert page.locator("#accountUiVersion").inner_text()=="4.3.0",width
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
                        assert page.locator("#foxScale").is_visible(),width
                        for behavior in ("Stationary","Wander","Follow","Event"):
                            assert page.locator("#foxBehavior"+behavior).is_visible(),(width,behavior)
                        page.locator("#foxBehaviorFollow").click()
                        assert page.locator("#foxBehaviorFollow").get_attribute("aria-pressed")=="true",width
                        page.locator("#foxBehaviorStationary").click()
                        assert page.locator("#foxBehaviorStationary").get_attribute("aria-pressed")=="true",width
                        assert page.locator("#foxMotionState").is_visible(),width
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:runtime',{detail:{state:'reasoning'}}))")
                        assert page.locator("#foxShell").get_attribute("data-motion-state")=="thinking",width
                        assert page.locator("#foxMotionState").inner_text()=="Размышляет",width
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:runtime',{detail:{state:'completed'}}))")
                        assert page.locator("#foxShell").get_attribute("data-motion-state")=="happy",width
                        page.evaluate("window.dispatchEvent(new CustomEvent('sayuri:context',{detail:{type:'document_opened',module:'files',entity_type:'document',entity_id:'demo'}}))")
                        assert page.locator("#foxShell").get_attribute("data-motion-state")=="reading",width
                        page.locator("#foxResetPosition").click()
                        reset_fox=page.locator("#foxAvatar").bounding_box()
                        assert reset_fox and reset_fox["x"] > width/2,(width,reset_fox)
                        page.locator("#foxVisibility").click()
                        assert not page.locator("#foxAvatar").is_visible(),width
                        page.locator("#foxVisibility").click()
                        assert page.locator("#foxAvatar").is_visible(),width
                        page.locator("#foxSettingsClose").click()
                        assert not page.locator("#foxContextMenu").is_visible(),width
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
                        page.wait_for_function("document.querySelector('#runningVersion').textContent.includes('4.3.0')")
                        assert "Sayuri" in page.locator("#runningFolder").inner_text(),width
                        assert page.locator("#updatesBackCabinet").is_visible(),width
                        if width in (390,1440):
                            page.locator("#updatesView").screenshot(
                                path=str(ROOT/"ui-previews"/("updates-"+str(width)+".png")))
                        page.locator("#updatesBackCabinet").click()
                        assert page.locator("#accountView").is_visible(),width
                        assert page.locator("#showUpdates").count()==1,width
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
