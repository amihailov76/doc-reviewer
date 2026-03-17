# Установка и первый запуск

## Требования

| Компонент | Версия | Примечание |
|---|---|---|
| Python | **3.11.x строго** | 3.12+ не поддерживается — нет бинарных сборок PyMuPDF |
| Node.js | 18+ | Для фронтенда |
| Windows | 10/11 | Целевая платформа |

> ⚠️ **Важно:** Python 3.14 и 3.12 не совместимы с PyMuPDF==1.24.3. Используйте строго Python 3.11.

## Установка зависимостей

### Python

```
py -3.11 -m pip install -r requirements.txt
```

Ключевые зависимости:

| Пакет | Версия | Назначение |
|---|---|---|
| fastapi | 0.110.0 | Бэкенд API |
| uvicorn | 0.27.1 | ASGI-сервер |
| sqlalchemy | 2.0.28 | ORM для SQLite |
| PyMuPDF | 1.24.3 | Парсинг PDF |
| python-docx | 1.1.0 | Парсинг DOCX |
| pymorphy3 | 2.0.2 | Морфологический анализ (детектор инструкций) |
| openpyxl | 3.1.2 | Экспорт в Excel |
| pyinstaller | 6.5.0 | Сборка в .exe |

> **Примечание по pymorphy3:** используется вместо pymorphy2, которая несовместима с Python 3.11. Подробнее — в `development/pymorphy3.md`.

### Node.js

```
cd frontend
npm install
```

## Структура папок данных

Перед первым запуском создайте папку:

```
mkdir data
mkdir data\uploads
```

Файл `data/db.sqlite` создаётся автоматически при первом запуске бэкенда.

## Запуск в режиме разработки

В первом окне терминала (корень проекта):

```
py -3.11 run_dev.py
```

Во втором окне (папка `frontend`):

```
npm run dev
```

Адреса:
- Фронтенд: `http://localhost:5173`
- Бэкенд API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

## Известные предупреждения при запуске

Эти сообщения не являются ошибками и не влияют на работу:

| Сообщение | Причина |
|---|---|
| `Field "model_id" has conflict with protected namespace` | Pydantic резервирует префикс `model_`. Исправлено добавлением `model_config = {"protected_namespaces": ()}` |
| `The CJS build of Vite's Node API is deprecated` | Vite сообщает о будущих изменениях в следующей мажорной версии |
| `React Router Future Flag Warning` | React Router сообщает о будущих изменениях в v7 |
