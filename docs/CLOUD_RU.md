# Подключение Sayuri к Cloud.ru Foundation Models

1. В Cloud.ru откройте **AI Factory → Foundation Models** и создайте **сервисный аккаунт**.
2. Создайте API-ключ для сервиса Foundation Models и сохраните **Key Secret** в безопасном месте.
3. В приватном `.env` проекта задайте:
   ```dotenv
   CLOUD_RU_API_KEY=<KEY_SECRET>
   CLOUD_RU_BASE_URL=https://foundation-models.api.cloud.ru/v1
   CLOUD_RU_MODEL=ai-sage/GigaChat3-10B-A1.8B
   # Для независимого наставника — ID другой доступной модели
   CLOUD_RU_TEACHER_MODEL=
   ```
   Имя модели приведено как пример из документации: проверьте доступность на своём аккаунте.
4. Перезапустите `Sayuri.bat`. Проверяйте подключение в личном кабинете; `GET /api/cloud/models` доступен только после авторизации владельца.
5. Не вставляйте ключ в браузер, мобильное приложение, чат, GitHub или публичные файлы.

## API
Официальная документация указывает:
- `GET https://foundation-models.api.cloud.ru/v1/models` — перечень моделей.
- `POST https://foundation-models.api.cloud.ru/v1/chat/completions` — запрос модели.
- Заголовок: `Authorization: Bearer <KEY_SECRET>`.

Ссылки:
- https://cloud.ru/docs/foundation-models/ug/topics/api-ref
- https://cloud.ru/docs/foundation-models/ug/topics/api-ref__authentication
- https://cloud.ru/docs/foundation-models/ug/topics/quickstart

## Как устроено обучение
Обычная модель отвечает на вопросы. Другая модель, указанная как `CLOUD_RU_TEACHER_MODEL`, проверяет выбранный диалог и **предлагает** знания для памяти. Предложения требуют подтверждения владельца. Настоящее дообучение весов через отдельный сервис и обучающий набор данных пока не реализовано.

## Безопасность
Для публичной установки обязательны HTTPS, серверная защита учётных данных и ограничение попыток входа. Перед передачей чатов в облако учитывайте конфиденциальность переписки и доступы к проектам. Если ключ компрометирован, отзовите его в Cloud.ru.
