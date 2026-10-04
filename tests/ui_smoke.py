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
                        page.wait_for_function("!!document.querySelector('link[href*=theme.css]').sheet")
                        assert page.locator("#accountView").is_visible(),width
                        assert page.locator(".advanced-settings").count()==1,width
                        assert not page.locator(".advanced-settings").evaluate("(e)=>e.open"),width
                        bg=page.evaluate("getComputedStyle(document.body).backgroundColor")
                        assert bg.startswith("rgb("),bg
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2"),width
                        if width in (390,1440):
                            snapshot=ROOT/"ui-previews"/("account-"+str(width)+".png")
                            snapshot.parent.mkdir(exist_ok=True)
                            page.locator("#accountView").screenshot(path=str(snapshot))
                        
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
                            assert foot["y"]+foot["height"]<=903,foot
                            page.locator("#collapseSidebar").click()
                            page.wait_for_timeout(300)
                            assert abs(page.locator("#sayuriSidebar").bounding_box()["width"]-72)<2,width
                            page.locator("#showHome").click()
                            assert page.locator("#homeView").is_visible()
                            assert page.locator("#showHome").get_attribute("aria-current")=="page"
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2"),width
                        assert not errors,(width,errors)
                        context.close()
                    print("Browser UI PASS: 360, 390, 768, 1024, 1440; focus, drawer, collapse, footer")
                finally:browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill()


if __name__=="__main__":run()
