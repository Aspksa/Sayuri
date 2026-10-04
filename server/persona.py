"""Load the complete user-authored Sayuri 2.0 bundle from versioned source parts."""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PERSONA_DIR=ROOT/"config"/"persona"
PARTS=PERSONA_DIR/"v2_parts"

@lru_cache(maxsize=1)
def load_persona() -> dict:
    files=sorted(PARTS.glob("part_*.txt"))
    if len(files)!=18:
        raise RuntimeError(f"Sayuri 2.0 requires 18 bundle segments; got {len(files)}")
    raw="".join(path.read_text(encoding="utf-8") for path in files)
    bundle=json.loads(raw)
    if (bundle.get("persona_version")!="2.0.0" or
        len(bundle)!=55 or
        len(bundle.get("lore_chapters",{}).get("chapters",[]))!=9 or
        len(bundle.get("ritual_engine",{}).get("records",[]))!=18 or
        len(bundle.get("dialogues",[]))!=100 or
        len(bundle.get("behavior_rules",[]))!=60 or
        len(bundle.get("acceptance_scenarios",[]))!=60 or
        sum(len(d["messages"]) for d in bundle["dialogues"])!=540 or
        sum(len(group["phrases"]) for group in bundle["phrase_library"]["groups"])!=400):
        raise RuntimeError("Sayuri 2.0 bundle integrity validation failed")
    return bundle

def rebuild_full_json() -> Path:
    """Optional: reconstruct a standalone full JSON file after cloning GitHub."""
    bundle=load_persona()
    result=PERSONA_DIR/"SAYURI_PERSONA_RU_v2.0.0.json"
    result.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    print(rebuild_full_json())
