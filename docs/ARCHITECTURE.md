# Sayuri — архитектура (исторические разделы + актуальное состояние)

> **Актуально на 2026-10-04:** рабочая реализация включает локальный вход владельца без пароля при `127.0.0.1`, поддерживает ZIP-обновление, каталог `Мои файлы`, BEYOND-компаньона и Persona 2.0. Ранее написанные ниже описания **первого прототипа** не заменяют действующий код. Полная актуальная информация: [история и статус](PROJECT_HISTORY_AND_STATUS.md), [Windows ZIP](WINDOWS_ZIP_SETUP_AND_RECOVERY.md).

## Runtime
- `Sayuri.bat` → Python virtual environment → `run.py` → FastAPI.
- Web chat (responsive ChatGPT/Telegram-inspired) talks only to the authenticated API.
- Flutter client sources are in `mobile/` for Android/iOS. No APK/IPA is built yet.
- Server-side Cloud.ru API adapter uses `CLOUD_RU_API_KEY`, `CLOUD_RU_BASE_URL`, and `CLOUD_RU_MODEL`. A separate teacher model can be selected using `CLOUD_RU_TEACHER_MODEL`.
- Database is SQLite in `SAYURI_DATA_DIR` or `data/`. A chat owner is set up with a password on first launch.

## Personality
`config/persona/SAYURI_PERSONA_RU_v1.0.0.json` holds Sayuri's values, fictional soul and character, persona prompt, 30 example dialogues, and 100 phrases. These samples **must not** be imported as real conversation history.

## Memory and teacher
- Each authenticated message is stored with its chat in SQLite once the provider responds successfully.
- User-confirmed memory entries are stored separately.
- The teacher can analyze an explicitly selected chat and create **pending** memory candidates.
- Each candidate has **approve/reject** controls. Approval is required before it enters durable memory.
- Project scoped memory does not automatically get mixed into the general personal chat context.
- Feedback can be inspected to prepare data for future training, but no model finetuning is performed.

## Documents and projects
- Explicitly uploaded documents are stored in a data directory, not indexed or forwarded to Cloud.ru automatically.
- If `SAYURI_PROJECTS_DIR` is configured, owner-authenticated read-only browsing of `Рабочие проекты` and `Домашние проекты` is available.
- `Документы / Облако / Sayuri` is a proposed folder structure, **not** an integrated cloud syncing service. Backup and synchronization remain to be built.

## Updates and deployment
- `updater.py` checks GitHub Releases without installing or executing downloaded code.
- Production requires HTTPS, brute-force protection, session/device management, filesystem access review, monitoring and backup verification.
- API credentials stay on the server. Never commit `.env`.
- Available CI configuration runs Python syntax compilation and pytest on pushes.

## Roadmap
- Reliable document indexing and RAG.
- Memory extraction evaluation and project-specific access isolation.
- Dedicated teacher datasets and compatible Cloud.ru fine-tuning with safeguards and rollback.
- Verified release packages, signature checking and atomic updater.
- Full mobile parity, notification delivery, uploads and build/signing pipeline.
