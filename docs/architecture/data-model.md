# Модель данных

База данных: SQLite. Файл: `data/db.sqlite`. Создаётся автоматически при первом запуске бэкенда.

## Таблицы

### Document

Загруженный документ.

| Поле | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Идентификатор |
| `filename` | TEXT | Имя файла при загрузке |
| `file_type` | TEXT | Расширение: `pdf`, `docx`, `md`, `txt` |
| `file_path` | TEXT | Абсолютный путь к файлу на диске |
| `doc_type` | TEXT | Тип документа (выбирается пользователем) |
| `uploaded_at` | DATETIME | Дата и время загрузки |
| `last_evaluated_at` | DATETIME | Дата последней оценки |

Допустимые значения `doc_type`:
- Руководство по развёртыванию
- Руководство пользователя
- Руководство администратора
- Справочник по настройке источников
- Справочник по PDQL

### Instruction

Раздел документа — заголовок + тело текста.

| Поле | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Идентификатор |
| `document_id` | INTEGER FK | Ссылка на Document |
| `title` | TEXT | Заголовок раздела |
| `content` | TEXT | Тело раздела |
| `classification` | TEXT | `instruction` / `possible` / `non-instruction` |
| `page_number` | INTEGER | Номер страницы (для PDF и DOCX) |
| `section_path` | TEXT | Путь в дереве: «1 > 1.2 > 1.2.3» |
| `include_in_evaluation` | INTEGER | 1 — включён в оценку, 0 — исключён |

### Evaluation

Результат оценки одной инструкции через LLM.

| Поле | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Идентификатор |
| `instruction_id` | INTEGER FK | Ссылка на Instruction (уникальная) |
| `color` | TEXT | `green` / `yellow` / `orange` / `red` |
| `issues` | TEXT | JSON-массив выявленных проблем |
| `evaluated_at` | DATETIME | Дата оценки |
| `model_id` | TEXT | ID модели, которая выполняла оценку |

### Snapshot

Снимок состояния документа в момент времени.

| Поле | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Идентификатор |
| `document_id` | INTEGER FK | Ссылка на Document |
| `created_at` | DATETIME | Дата создания снимка |
| `is_baseline` | INTEGER | 1 — baseline-снимок |
| `data` | TEXT | JSON со статистикой на момент снимка |

### ApiKey

Зашифрованные API-ключи для LLM-провайдеров.

| Поле | Тип | Описание |
|---|---|---|
| `id` | INTEGER PK | Идентификатор |
| `provider` | TEXT | Название провайдера |
| `encrypted_key` | TEXT | Ключ, зашифрованный через Fernet |
| `created_at` | DATETIME | Дата сохранения |

## Связи между таблицами

```
Document ──< Instruction ──── Evaluation
                │
Document ──< Snapshot
```

- `Document` → `Instruction`: один-ко-многим (каскадное удаление)
- `Instruction` → `Evaluation`: один-к-одному (каскадное удаление)
- `Document` → `Snapshot`: один-ко-многим (каскадное удаление)
