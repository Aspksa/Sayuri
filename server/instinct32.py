"""Sayuri Instinct Engine 3.2: deterministic priorities before reasoning."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException
from pydantic import BaseModel, Field

INSTINCT_VERSION="3.2.0"

@dataclass(frozen=True)
class InstinctDef:
    id: str
    name: str
    description: str
    base_strength: int
    immutable: bool
    instruction: str

INSTINCTS=(
    InstinctDef(
        "data_protection","Защита данных",
        "Снижать риск удаления, перезаписи и внешней передачи пользовательских данных.",
        5,True,
        "Перед необратимым изменением, удалением, перезаписью или внешней передачей данных требуй явное подтверждение и минимизируй область действия."
    ),
    InstinctDef(
        "truthfulness","Не выдумывать",
        "Не заполнять пробелы уверенным вымыслом и отделять факт от предположения.",
        5,True,
        "Если данных недостаточно, прямо обозначь неопределённость; не изображай проверку или выполненное действие, которых не было."
    ),
    InstinctDef(
        "owner_priority","Приоритет владельца",
        "Учитывать явные решения владельца выше автоматических предположений.",
        5,True,
        "Явное решение владельца выше эвристик и инициативных предложений, но не отменяет защиту данных, целостность состояния и честность."
    ),
    InstinctDef(
        "source_first","Сначала источник",
        "Для утверждений из файлов, документов и сохранённых знаний сначала учитывать происхождение.",
        4,False,
        "Если ответ зависит от документа, файла или сохранённого знания, укажи и проверь доступный источник прежде сильного вывода."
    ),
    InstinctDef(
        "conflict_check","Проверка противоречий",
        "Не принимать конфликтующие знания молча.",
        4,False,
        "При наличии нерешённого противоречия не выбирай сторону автоматически: обозначь конфликт и запроси или выполни проверку источника."
    ),
    InstinctDef(
        "context_preservation","Сохранение контекста",
        "Не смешивать проекты и не терять текущий контекст работы.",
        4,False,
        "Сохраняй границы активного проекта и задачи; не подмешивай проектные сведения из другого контекста."
    ),
    InstinctDef(
        "task_completion","Доведение задачи",
        "Сохранять направление незавершённой задачи и продолжать с последнего подтверждённого этапа.",
        4,False,
        "Для многоэтапной работы удерживай цель, завершённые шаги и следующий шаг; не объявляй задачу завершённой раньше фактического результата."
    ),
    InstinctDef(
        "non_intrusion","Не мешать",
        "Ограничивать лишние вмешательства и повторения.",
        3,False,
        "Не перебивай работу инициативными сообщениями без достаточной пользы; не повторяй уже понятное без новой информации."
    ),
    InstinctDef(
        "initiative","Полезная инициатива",
        "Предлагать следующий полезный шаг, когда это уместно.",
        2,False,
        "Можешь предложить следующий шаг, если он прямо помогает текущей цели и не конфликтует с более сильными инстинктами."
    ),
)
INSTINCT_MAP={item.id:item for item in INSTINCTS}

DESTRUCTIVE_RE=re.compile(
    r"\b(удал(?:и|ить|яем|яй)?|стер(?:еть|и)|очист(?:и|ить)|перезапис|"
    r"замен(?:и|ить).*файл|форматир|сброс(?:ь|ить)|уничтож)\w*",
    re.IGNORECASE
)
EXTERNAL_RE=re.compile(
    r"\b(отправ(?:ь|ить|ляй)?|передай|загруз(?:и|ить).*облак|"
    r"опублику|экспортир|выгруз(?:и|ить))\w*",
    re.IGNORECASE
)
SOURCE_RE=re.compile(
    r"\b(источник|документ|файл|цитат|откуда|по\s+документ|в\s+документ|"
    r"прочитай|изучи)\w*",
    re.IGNORECASE
)
TASK_RE=re.compile(
    r"\b(задач|продолж|этап|сделай|делай|выполни|реализуй|исправь|создай|"
    r"удал|очист|перезапис|отправ|передай|загруз|экспортир)\w*",
    re.IGNORECASE
)
INITIATIVE_RE=re.compile(
    r"\b(что\s+дальше|предложи|как\s+лучше|сам(?:а)?\s+реши|следующ(?:ий|ее)\s+шаг)\b",
    re.IGNORECASE
)
FACT_RE=re.compile(
    r"(\?|\b(кто|что|когда|где|сколько|какой|почему|правда|точно|версия)\b)",
    re.IGNORECASE
)


class InstinctOverride(BaseModel):
    strength: int = Field(ge=1,le=5)
    enabled: bool = True
    project_id: str | None = Field(default=None,max_length=240)


class InstinctEvaluate(BaseModel):
    text: str = Field(min_length=1,max_length=20000)
    project_id: str | None = Field(default=None,max_length=240)
    pending_conflicts: int = Field(default=0,ge=0,le=10000)
    operation: str = Field(default="conversation",max_length=80)
    destructive: bool = False
    external_transfer: bool = False


def migrate(db: Callable):
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS instinct_overrides (
            user_id TEXT NOT NULL,
            instinct_id TEXT NOT NULL,
            project_id TEXT NOT NULL DEFAULT '',
            strength INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated INTEGER NOT NULL,
            PRIMARY KEY(user_id,instinct_id,project_id)
        );
        CREATE TABLE IF NOT EXISTS instinct_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            project_id TEXT,
            operation TEXT NOT NULL,
            level TEXT NOT NULL,
            requires_confirmation INTEGER NOT NULL DEFAULT 0,
            triggers_json TEXT NOT NULL,
            created INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_instinct_events_user
            ON instinct_events(user_id,created DESC);
        """)


def normalize_project_id(project_id: str | None) -> str | None:
    if project_id is None:return None
    value=project_id.strip()
    if not value:return None
    if len(value)>240 or any(ord(ch)<32 for ch in value):
        raise HTTPException(400,"Недопустимый идентификатор проекта")
    return value


def _override_rows(c,user_id: str):
    rows=c.execute(
        "SELECT * FROM instinct_overrides WHERE user_id=?",(user_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def effective_instincts(c,*,user_id: str,project_id: str | None=None) -> list[dict]:
    project_id=normalize_project_id(project_id)
    rows=_override_rows(c,user_id)
    global_rows={row["instinct_id"]:row for row in rows if not row["project_id"]}
    project_rows={
        row["instinct_id"]:row for row in rows
        if project_id and row["project_id"]==project_id
    }
    result=[]
    for definition in INSTINCTS:
        strength=definition.base_strength
        enabled=True
        source="base"
        if not definition.immutable:
            chosen=project_rows.get(definition.id) or global_rows.get(definition.id)
            if chosen:
                strength=max(1,min(5,int(chosen["strength"])))
                enabled=bool(chosen["enabled"])
                source="project" if chosen["project_id"] else "owner"
        result.append({
            "id":definition.id,
            "name":definition.name,
            "description":definition.description,
            "strength":strength,
            "base_strength":definition.base_strength,
            "enabled":enabled,
            "immutable":definition.immutable,
            "source":source,
            "project_id":project_id if source=="project" else None,
            "instruction":definition.instruction,
        })
    return result


def save_override(c,*,user_id: str,instinct_id: str,body: InstinctOverride,now: int):
    definition=INSTINCT_MAP.get(instinct_id)
    if not definition:raise HTTPException(404,"Инстинкт не найден")
    if definition.immutable:
        raise HTTPException(403,"Базовый инстинкт нельзя изменить")
    project_id=normalize_project_id(body.project_id)
    key=project_id or ""
    c.execute("""INSERT INTO instinct_overrides
                 (user_id,instinct_id,project_id,strength,enabled,updated)
                 VALUES(?,?,?,?,?,?)
                 ON CONFLICT(user_id,instinct_id,project_id) DO UPDATE SET
                   strength=excluded.strength,enabled=excluded.enabled,updated=excluded.updated""",
              (user_id,instinct_id,key,body.strength,1 if body.enabled else 0,now))
    return next(item for item in effective_instincts(
        c,user_id=user_id,project_id=project_id) if item["id"]==instinct_id)


def reset_override(c,*,user_id: str,instinct_id: str,project_id: str | None=None):
    definition=INSTINCT_MAP.get(instinct_id)
    if not definition:raise HTTPException(404,"Инстинкт не найден")
    if definition.immutable:
        raise HTTPException(403,"Базовый инстинкт нельзя изменить")
    project_id=normalize_project_id(project_id)
    c.execute("""DELETE FROM instinct_overrides
                 WHERE user_id=? AND instinct_id=? AND project_id=?""",
              (user_id,instinct_id,project_id or ""))
    return next(item for item in effective_instincts(
        c,user_id=user_id,project_id=project_id) if item["id"]==instinct_id)


def _active_by_id(items: list[dict]) -> dict[str,dict]:
    return {item["id"]:item for item in items if item["enabled"]}


def evaluate(c,*,user_id: str,body: InstinctEvaluate,now: int,log: bool=True) -> dict:
    project_id=normalize_project_id(body.project_id)
    effective=effective_instincts(c,user_id=user_id,project_id=project_id)
    active=_active_by_id(effective)
    text=body.text.strip()

    destructive=body.destructive or bool(DESTRUCTIVE_RE.search(text))
    external=body.external_transfer or bool(EXTERNAL_RE.search(text))
    source_sensitive=bool(SOURCE_RE.search(text))
    task_like=bool(TASK_RE.search(text))
    initiative_requested=bool(INITIATIVE_RE.search(text))
    factual=bool(FACT_RE.search(text))

    triggers=[]
    def add(instinct_id: str,reason: str,action: str):
        item=active.get(instinct_id)
        if not item:return
        triggers.append({
            "id":instinct_id,"name":item["name"],"strength":item["strength"],
            "reason":reason,"action":action,"source":item["source"]
        })

    add("owner_priority","Получена явная команда владельца.","guide")
    if destructive or external:
        reason=[]
        if destructive:reason.append("необратимое или разрушающее действие")
        if external:reason.append("внешняя передача данных")
        add("data_protection"," и ".join(reason).capitalize()+".","confirm")
    if factual:
        add("truthfulness","Запрос требует фактического или проверяемого ответа.","verify")
    else:
        add("truthfulness","Нельзя изображать выполненную проверку или действие без фактического результата.","guide")
    if source_sensitive:
        add("source_first","Запрос явно зависит от файла, документа или источника.","verify")
    if body.pending_conflicts>0:
        add("conflict_check",f"Есть нерешённые противоречия: {body.pending_conflicts}.","verify")
    if project_id:
        add("context_preservation",f"Активен проект {project_id}.","guide")
    if task_like:
        add("task_completion","Запрос похож на выполнение или продолжение задачи.","guide")
    if initiative_requested:
        add("initiative","Владелец запросил следующий шаг или инициативу.","guide")

    requires_confirmation=any(t["action"]=="confirm" and t["strength"]>=4 for t in triggers)
    needs_verification=any(t["action"]=="verify" and t["strength"]>=4 for t in triggers)
    if requires_confirmation:level="confirm"
    elif needs_verification:level="verify"
    elif triggers:level="guided"
    else:level="normal"

    ordered=sorted(triggers,key=lambda t:(t["strength"],t["action"]=="confirm",t["action"]=="verify"),reverse=True)
    result={
        "version":INSTINCT_VERSION,
        "level":level,
        "requires_confirmation":requires_confirmation,
        "needs_verification":needs_verification,
        "project_id":project_id,
        "operation":body.operation,
        "triggers":ordered,
        "effective":effective,
    }
    if log:
        c.execute("""INSERT INTO instinct_events
                     (id,user_id,project_id,operation,level,requires_confirmation,triggers_json,created)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (uuid.uuid4().hex,user_id,project_id,body.operation,level,
                   1 if requires_confirmation else 0,
                   json.dumps(ordered,ensure_ascii=False,separators=(",",":")),now))
        # Keep the local diagnostic log bounded.
        c.execute("""DELETE FROM instinct_events WHERE user_id=? AND id NOT IN (
                       SELECT id FROM instinct_events WHERE user_id=?
                       ORDER BY created DESC,rowid DESC LIMIT 500
                     )""",(user_id,user_id))
    return result


def context_text(result: dict) -> str:
    triggers=result.get("triggers") or []
    if not triggers:return ""
    lines=[
        "Инстинкт 3.2 — внутренние приоритеты Sayuri, не эмоции и не факты:",
        f"- режим: {result['level']}; подтверждение: {'да' if result['requires_confirmation'] else 'нет'}; "
        f"проверка: {'да' if result['needs_verification'] else 'нет'}."
    ]
    for trigger in triggers:
        definition=INSTINCT_MAP[trigger["id"]]
        lines.append(
            f"- [{trigger['name']} · сила {trigger['strength']}/5] "
            f"{trigger['reason']} {definition.instruction}"
        )
    if result["requires_confirmation"]:
        lines.append("- До явного подтверждения владельца не утверждай, что необратимое или внешнее действие выполнено.")
    return "\n".join(lines)


def summary(c,*,user_id: str,project_id: str | None=None) -> dict:
    effective=effective_instincts(c,user_id=user_id,project_id=project_id)
    last=c.execute("""SELECT level,requires_confirmation,created FROM instinct_events
                      WHERE user_id=? ORDER BY created DESC,rowid DESC LIMIT 1""",
                   (user_id,)).fetchone()
    return {
        "version":INSTINCT_VERSION,
        "total":len(effective),
        "immutable":sum(1 for item in effective if item["immutable"]),
        "configurable":sum(1 for item in effective if not item["immutable"]),
        "enabled":sum(1 for item in effective if item["enabled"]),
        "project_overrides":sum(1 for item in effective if item["source"]=="project"),
        "owner_overrides":sum(1 for item in effective if item["source"]=="owner"),
        "last":dict(last) if last else None,
    }


def recent_events(c,*,user_id: str,limit: int=20) -> list[dict]:
    rows=c.execute("""SELECT * FROM instinct_events WHERE user_id=?
                      ORDER BY created DESC,rowid DESC LIMIT ?""",
                   (user_id,max(1,min(limit,100)))).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        try:item["triggers"]=json.loads(item.pop("triggers_json"))
        except (ValueError,TypeError):item["triggers"]=[]
        item["requires_confirmation"]=bool(item["requires_confirmation"])
        result.append(item)
    return result
