"""Safe startup update notification; no implicit download or code execution."""
from __future__ import annotations
from pathlib import Path
from server.updating import update_status, UpdateError

if __name__ == "__main__":
    try:
        state=update_status(Path(__file__).resolve().parent)
        if state["update_available"]:
            print("Sayuri: новая версия на GitHub. Обновите через Личный кабинет Sayuri.")
        else:
            print("Sayuri: текущая версия актуальна.")
        if state["mode"]=="zip" and state["local"]=="ZIP (неизвестна)":
            print("Sayuri: ZIP-версия без номера; можно безопасно подготовить новый ZIP в кабинете.")
    except UpdateError:
        print("Sayuri: проверка GitHub недоступна, запуск продолжается.")
