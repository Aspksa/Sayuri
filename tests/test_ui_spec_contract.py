"""Static acceptance checks against the owner's exact UI JSON contract."""
import json
from pathlib import Path
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/"docs/SAYURI_MENU_UI_SPEC.json").read_text(encoding="utf-8"))
HTML=(ROOT/"web/index.html").read_text(encoding="utf-8")
CSS=(ROOT/"web/theme.css").read_text(encoding="utf-8")
SIDEBAR=(ROOT/"web/sidebar.js").read_text(encoding="utf-8")
SERVER=(ROOT/"server/app.py").read_text(encoding="utf-8")

class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=set()
        self.tags=[]
    def handle_starttag(self,tag,attrs):
        data=dict(attrs)
        if "id" in data:self.ids.add(data["id"])
        self.tags.append((tag,data))


def test_design_tokens_match_supplied_json():
    colors=SPEC["design_tokens"]["colors"]
    for value in colors.values():
        assert value.lower() in CSS.lower(), "Missing design color "+value
    for size in (280,72,260):
        assert (str(size)+"px") in CSS
    assert "min(88vw,320px)" in CSS or "min(88vw, 320px)" in CSS
    assert "rgba(0,0,0,.55)" in CSS or "rgba(0,0,0,0.55)" in CSS
    assert "env(safe-area-inset-top)" in CSS
    assert "env(safe-area-inset-bottom)" in CSS
    assert "prefers-reduced-motion" in CSS


def test_all_sections_and_layout_zones_exist():
    parsed=Tags()
    parsed.feed(HTML)
    required={"sayuriSidebar","showAccount","profileActivity",
              "sidebarScroller","sayuriStatusDetails","networkDetails",
              "cloudDetails","showChat","showWork","showFiles",
              "showHome","showUpdates","collapseSidebar","drawerBackdrop"}
    assert required <= parsed.ids
    for x in ("sidebar-fixed-profile","sidebar-scroller",
              "sidebar-fixed-bottom"):
        assert x in HTML
    for view in ("chatView","workView","homeView",
                 "filesView","accountView","updatesView"):
        assert view in parsed.ids


def test_twelve_states_are_glossary_not_simulation():
    states=next(x for x in SPEC["sidebar_structure"] if x["id"]=="sayuri_status")["statuses"]
    assert len(states)==12
    for obj in states:
        assert obj["id"] in SIDEBAR
        assert obj["label"] in SIDEBAR
    assert "runtime_status" in SIDEBAR
    assert "/api/runtime/events" in SIDEBAR
    assert "/api/runtime/status" in SIDEBAR
    assert "authorization" not in SIDEBAR.lower() or "Authorization" in SIDEBAR
    assert "cost_rub" not in SIDEBAR or "Нет подтверждённого расчёта" in SIDEBAR
    assert "SAYURI_LOCAL_ACCESS" in SERVER
    assert '"/api/runtime/status"' in SERVER


def test_mobile_keyboard_and_sidebar_interaction_are_wired():
    assert "aria-current" in SIDEBAR
    assert "aria-expanded" in SIDEBAR
    assert "e.key==='Escape'" in SIDEBAR
    assert "e.key!=='Tab'" in SIDEBAR
    assert "el('drawerBackdrop').addEventListener('click',closeDrawer)" in SIDEBAR
    assert "document.body.classList.toggle('sidebar-collapsed')" in SIDEBAR
    assert "localStorage.setItem('sayuri.sidebar.collapsed'" in SIDEBAR
    assert "getClientRects()" in SIDEBAR


def test_sidebar_text_contrast_wcag_aa():
    colors=SPEC["design_tokens"]["colors"]
    def luminance(value):
        srgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in srgb]
        return sum(a*b for a,b in zip((0.2126,0.7152,0.0722),linear))
    def contrast(foreground,background):
        a,b=sorted((luminance(colors[foreground]),luminance(colors[background])),reverse=True)
        return (a+0.05)/(b+0.05)
    for background in ("sidebar_background","surface"):
        for foreground in ("primary_text","secondary_text","tertiary_text",
                           "accent_pink","accent_purple","info","success","warning","error"):
            assert contrast(foreground,background)>=4.5,(foreground,background)
