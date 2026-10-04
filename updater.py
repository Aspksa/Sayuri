"""Non-destructive GitHub Releases check. No unsigned code execution."""
import json
from urllib.request import Request, urlopen
from urllib.error import URLError
from pathlib import Path
VERSION="0.1.0"
URL="https://api.github.com/repos/Aspksa/Sayuri/releases/latest"
def main():
    try:
        request=Request(URL,headers={"User-Agent":"Sayuri-update-check/0.1","Accept":"application/vnd.github+json"})
        with urlopen(request,timeout=4) as response: data=json.load(response)
        tag=str(data.get("tag_name","")).lstrip("v")
        if not tag: print("Sayuri: релизы GitHub пока отсутствуют");return
        if tag==VERSION: print("Sayuri: актуальная версия",VERSION)
        else: print("Sayuri: опубликована версия",tag,"—",data.get("html_url",URL))
        print("Установка релизов вручную после проверки источника и резервного копирования")
    except (URLError, TimeoutError, ValueError, OSError):
        print("Sayuri: проверка GitHub недоступна, запуск продолжается")
if __name__=="__main__":main()
