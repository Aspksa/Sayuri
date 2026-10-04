"""Local development / Windows entry point."""
import os
from pathlib import Path
from dotenv import load_dotenv
import uvicorn
ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT/".env")
if __name__=="__main__":
    host=os.getenv("SAYURI_HOST","127.0.0.1")
    if os.getenv("SAYURI_LOCAL_ACCESS","1")=="1" and host not in ("127.0.0.1","localhost","::1"):
        raise SystemExit("Без пароля Sayuri может работать только на 127.0.0.1. Для внешнего доступа отключите SAYURI_LOCAL_ACCESS и настройте HTTPS + авторизацию.")
    uvicorn.run("server.app:app",host=host,port=int(os.getenv("SAYURI_PORT","8765")))
