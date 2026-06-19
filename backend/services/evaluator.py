"""
Сервис оценки инструкций через LLM.

Логика:
- Формирует промпт с текстом инструкции и критериями оценки из criteria.md
- Отправляет запрос к OpenAI-совместимому API
- Парсит JSON-ответ в структуру EvaluationResult
- При ошибке повторяет запрос до 3 раз, затем выбрасывает EvaluationError
  с человекочитаемым описанием и рекомендацией что делать
"""

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional
import httpx

from backend.config import get_active_model
from backend.services.glossary import glossary_to_prompt_block

# ── Путь к файлу критериев ────────────────────────────────────────────────────
import sys as _sys

def _find_criteria() -> str:
    """
    Ищет criteria.md в следующем порядке:
    1. Рядом с .exe (пользователь может положить свою версию)
    2. Внутри PyInstaller-архива (_MEIPASS)
    3. Корень проекта (режим разработки)
    """
    if getattr(_sys, "frozen", False):
        # 1. Рядом с .exe — приоритет, чтобы пользователь мог переопределить
        candidate = os.path.join(os.path.dirname(_sys.executable), "criteria.md")
        if os.path.exists(candidate):
            return candidate
        # 2. Внутри архива PyInstaller
        meipass = getattr(_sys, "_MEIPASS", None)
        if meipass:
            candidate = os.path.join(meipass, "criteria.md")
            if os.path.exists(candidate):
                return candidate
    # 3. Режим разработки
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "criteria.md"
    )

CRITERIA_PATH = _find_criteria()

# ── Настройки повторных попыток ───────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2.0       # пауза между попытками
REQUEST_TIMEOUT_SEC = 120.0  # таймаут одного запроса

# ── Цветовая схема по количеству проблем ─────────────────────────────────────
# Проблема = критерий с результатом "missing" или "partial"
# ok      → 0 проблем
# warning → предупреждение (minor issues)
# error   → критическая проблема (missing)


def _compute_color(criteria_results: dict) -> str:
    """
    Вычисляет итоговый цвет оценки по результатам критериев.

    Цветовая схема:
      🟢 green  — нет error, не более одного warning
      🟡 yellow — есть warning, нет error или не более одного error
      🟠 orange — 2–3 error
      🔴 red    — 4 и более error
    """
    errors = sum(1 for v in criteria_results.values() if v == "error")
    warnings = sum(1 for v in criteria_results.values() if v == "warning")

    if errors == 0 and warnings <= 1:
        return "green"
    if errors <= 1:
        return "yellow"
    if errors <= 3:
        return "orange"
    return "red"


# ── Структуры данных ──────────────────────────────────────────────────────────

@dataclass
class EvaluationResult:
    color: str                              # green / yellow / orange / red
    criteria_results: dict                  # {"1.1": "ok"/"warning"/"error", ...}
    recommendations: list[dict]             # [{"criterion": "1.1", "text": "...", "example": "..."}]
    model_used: str


@dataclass
class EvaluationError(Exception):
    """Ошибка оценки с человекочитаемым описанием."""
    message: str        # краткое сообщение для UI
    detail: str         # подробности для разработчика (лог)
    advice: str         # рекомендация пользователю что делать


# ── Загрузка критериев ────────────────────────────────────────────────────────

def _load_criteria() -> str:
    """Возвращает активный набор критериев из БД."""
    from backend.database import get_active_criteria_content
    content = get_active_criteria_content()
    if not content:
        raise EvaluationError(
            message="Критерии оценки не найдены",
            detail="Таблица criteria_sets пуста и файл criteria.md не найден.",
            advice="Перейдите в раздел «Настройки» и добавьте набор критериев.",
        )
    return content


# ── Промпт ────────────────────────────────────────────────────────────────────

# Часть системного промпта с инструкциями по формату ответа.
# Роль подставляется динамически из секции ## Роль активного набора критериев.
# Если секция ## Роль отсутствует — используется SYSTEM_PROMPT с дефолтной ролью.
_SYSTEM_PROMPT_TASK = """Перед оценкой по критериям мысленно ответь на три вопроса:
1. Понятна ли инструкция пользователю без дополнительного контекста из других разделов?
2. Какие предварительные условия или термины подразумеваются, но не объяснены?
3. Есть ли в тексте ссылки на объекты, настройки или процедуры, которые нигде в инструкции не раскрыты?

Используй ответы как основу при оценке критериев 1.1, 1.2, 1.3 и при формулировке рекомендаций.

Твоя задача — проверить инструкцию на соответствие заданным критериям и вернуть результат строго в формате JSON.

Для каждого критерия укажи одно из трёх значений:
- "ok"      — критерий полностью выполнен
- "warning" — критерий выполнен частично или с замечаниями
- "error"   — критерий не выполнен

Если для критерия есть замечания (warning или error), добавь рекомендацию в список recommendations.

Важно: некоторые критерии помечены как <опциональные>. Для таких критериев:
- Если соответствующий раздел или элемент в инструкции отсутствует — ставь "ok".
- Оценивай содержание только если раздел реально присутствует в тексте.

Важно: текст инструкции извлечён из PDF автоматически. Символы иконочных шрифтов (графические значки кнопок) не извлекаются как текст и заменяются меткой [иконка]. Эта метка обозначает декоративный графический символ — не название элемента интерфейса. Названия кнопок, полей и пунктов меню всегда присутствуют в тексте отдельно, рядом с меткой или без неё. Например: «Нажмите [иконка] Сохранить» — здесь «Сохранить» и есть название кнопки. Никогда не считай метку [иконка] отсутствующим или нераскрытым названием элемента интерфейса.

Формат ответа — строго JSON, без markdown-блоков, без пояснений:
{
  "criteria_results": {
    "1.1": "ok",
    "1.2": "warning",
    ...
  },
  "recommendations": [
    {
      "criterion": "1.2",
      "text": "Описание проблемы и что нужно исправить",
      "example": "Пример как это должно выглядеть (необязательно)"
    }
  ]
}"""

# Фоллбэк-промпт с дефолтной ролью — используется если в критериях нет секции ## Роль
SYSTEM_PROMPT = "Ты — эксперт по оценке качества технической документации.\n" + _SYSTEM_PROMPT_TASK


def _extract_role(criteria_content: str) -> Optional[str]:
    """
    Извлекает текст секции ## Роль из набора критериев.
    Возвращает текст секции без заголовка или None если секция отсутствует.
    """
    match = re.search(
        r"^##\s+Роль\s*\n(.*?)(?=\n##\s|\Z)",
        criteria_content,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return None


def _strip_role_section(criteria_content: str) -> str:
    """
    Удаляет секцию ## Роль и разделитель после неё из набора критериев.
    Используется чтобы не дублировать роль в пользовательском промпте.
    """
    # Убираем блок ## Роль вместе с возможным горизонтальным разделителем (---)
    cleaned = re.sub(
        r"^##\s+Роль\s*\n.*?(?=\n##\s|\Z)",
        "",
        criteria_content,
        flags=re.MULTILINE | re.DOTALL,
    )
    # Убираем висячие разделители --- которые могли остаться после блока
    cleaned = re.sub(r"\n---\s*\n", "\n", cleaned)
    return cleaned.strip()


def _build_user_prompt(
    title: str,
    content: str,
    criteria: str,
    product_context: Optional[str] = None,
    section_path: Optional[str] = None,
    neighbor_titles: Optional[list] = None,
    glossary: Optional[list] = None,
    diff_hint: Optional[str] = None,
) -> str:
    # Блок контекста продукта — подставляется только если задан
    context_block = ""
    if product_context:
        context_block = f"\n--- КОНТЕКСТ ПРОДУКТА ---\n{product_context}\n--- КОНЕЦ КОНТЕКСТА ---\n"

    # Блок терминов продукта из глоссария
    glossary_block = glossary_to_prompt_block(glossary)

    # Блок изменений при обновлении документа
    diff_block = ""
    if diff_hint:
        diff_block = (
            f"\n--- ИЗМЕНЕНИЯ В РАЗДЕЛЕ ---\n"
            f"Раздел обновлён по сравнению с предыдущей версией документа. "
            f"Изменения: {diff_hint}\n"
            f"Оценивай актуальный текст раздела, а не предыдущую версию.\n"
            f"--- КОНЕЦ ИЗМЕНЕНИЙ ---\n"
        )

    # Структурный контекст — путь раздела и соседи
    structural_lines = []
    if section_path:
        structural_lines.append(f"Путь в документе: {section_path}")
    if neighbor_titles:
        structural_lines.append(f"Соседние разделы: {' | '.join(neighbor_titles)}")
    structural_block = ("\n" + "\n".join(structural_lines)) if structural_lines else ""

    return f"""Оцени следующую инструкцию по критериям ниже.
{context_block}{glossary_block}{diff_block}{structural_block}

--- ИНСТРУКЦИЯ ---
Заголовок: {title}

{content}
--- КОНЕЦ ИНСТРУКЦИИ ---

--- КРИТЕРИИ ОЦЕНКИ ---
{criteria}
--- КОНЕЦ КРИТЕРИЕВ ---

Верни результат в формате JSON."""


# ── Получение API-ключа ───────────────────────────────────────────────────────

def _get_api_key(provider: str, model_cfg=None) -> Optional[str]:
    """
    Возвращает API-ключ для модели.
    Приоритет: ключ модели из БД → переменная окружения.
    """
    if provider == "local":
        return "local"
    # Ключ, сохранённый в самой модели
    if model_cfg and getattr(model_cfg, "api_key", None):
        return model_cfg.api_key
    # Fallback — переменные окружения
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY")
    return os.environ.get("OPENAI_API_KEY")


def _build_headers(provider: str, api_key: Optional[str]) -> dict:
    """Формирует заголовки запроса в зависимости от провайдера."""
    if provider == "anthropic":
        return {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01",
        }
    # OpenAI и OpenAI-совместимые провайдеры
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'none'}",
    }


# ── Основная функция оценки ───────────────────────────────────────────────────

def evaluate_instruction(
    title: str,
    content: str,
    product_context: Optional[str] = None,
    section_path: Optional[str] = None,
    neighbor_titles: Optional[list] = None,
    glossary: Optional[list] = None,
    diff_hint: Optional[str] = None,
) -> EvaluationResult:
    """
    Оценивает одну инструкцию через LLM.
    При ошибке повторяет запрос до MAX_RETRIES раз.
    Выбрасывает EvaluationError если все попытки исчерпаны.
    """
    criteria = _load_criteria()
    model_cfg = get_active_model()
    model_id = model_cfg.id
    base_url = model_cfg.base_url.rstrip("/")
    provider = model_cfg.provider

    api_key = _get_api_key(provider, model_cfg)
    if model_cfg.requires_key and not api_key:
        raise EvaluationError(
            message="API-ключ не настроен",
            detail=f"Для модели {model_id} требуется API-ключ, но он не найден.",
            advice=(
                "Перейдите в раздел «Настройки», введите API-ключ для выбранного провайдера. "
                "Или переключитесь на локальную модель, если она доступна."
            ),
        )

    # Извлекаем роль из секции ## Роль и строим системный промпт динамически.
    # Если секции нет — используем фоллбэк с дефолтной ролью.
    role_text = _extract_role(criteria)
    active_system_prompt = (
        role_text + "\n\n" + _SYSTEM_PROMPT_TASK if role_text else SYSTEM_PROMPT
    )
    # Убираем секцию ## Роль из критериев — в пользовательский промпт она не идёт
    criteria_for_prompt = _strip_role_section(criteria)

    user_prompt = _build_user_prompt(
        title, content, criteria_for_prompt,
        product_context=product_context,
        section_path=section_path,
        neighbor_titles=neighbor_titles,
        glossary=glossary,
        diff_hint=diff_hint,
    )
    headers = _build_headers(provider, api_key)

    # Anthropic и OpenAI используют разные форматы payload
    if provider == "anthropic":
        payload = {
            "model": model_id,
            "max_tokens": 1500,
            "system": active_system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
    else:
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": active_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
        }

    last_error = None
    # Подхватываем системный прокси (корпоративные сети)
    proxies = urllib.request.getproxies()
    proxy_url = proxies.get("https") or proxies.get("http") or None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client_kwargs = {"timeout": REQUEST_TIMEOUT_SEC, "verify": False}
            if proxy_url:
                client_kwargs["proxies"] = proxy_url

            with httpx.Client(**client_kwargs) as client:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )

            if response.status_code == 401:
                raise EvaluationError(
                    message="Неверный API-ключ",
                    detail=f"HTTP 401 от {base_url}",
                    advice=(
                        "Проверьте API-ключ в разделе «Настройки». "
                        "Убедитесь, что ключ скопирован полностью и не содержит лишних пробелов."
                    ),
                )

            if response.status_code == 429:
                raise EvaluationError(
                    message="Превышен лимит запросов к API",
                    detail=f"HTTP 429 от {base_url}",
                    advice=(
                        "Подождите несколько минут и попробуйте снова. "
                        "Если проблема повторяется — переключитесь на модель с меньшей нагрузкой."
                    ),
                )

            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code} от сервера"
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC * attempt)
                    continue
                raise EvaluationError(
                    message="Сервер LLM недоступен",
                    detail=last_error,
                    advice=(
                        "Сервис временно недоступен. Попробуйте через несколько минут. "
                        "Если используется локальная модель — убедитесь, что она запущена."
                    ),
                )

            response.raise_for_status()
            resp_json = response.json()

            # OpenAI-формат: choices[0].message.content
            # Anthropic-формат: content[0].text
            if "choices" in resp_json:
                raw_text = resp_json["choices"][0]["message"]["content"]
            elif "content" in resp_json:
                raw_text = resp_json["content"][0]["text"]
            else:
                raise EvaluationError(
                    message="Неизвестный формат ответа от API",
                    detail=f"Ответ не содержит ни 'choices', ни 'content': {str(resp_json)[:200]}",
                    advice="Проверьте настройки модели в models.yml.",
                )
            return _parse_llm_response(raw_text, model_id)

        except EvaluationError:
            raise  # пробрасываем наши ошибки без повторов

        except httpx.ProxyError as e:
            last_error = f"Ошибка прокси-сервера: {e}"
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC * attempt)
                continue

        except httpx.ConnectError:
            last_error = f"Не удалось подключиться к {base_url}"
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC * attempt)
                continue

        except httpx.TimeoutException:
            last_error = f"Таймаут запроса ({REQUEST_TIMEOUT_SEC}с)"
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC * attempt)
                continue

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC * attempt)
                continue

    # Все попытки исчерпаны
    raise EvaluationError(
        message=f"Не удалось получить ответ от LLM после {MAX_RETRIES} попыток",
        detail=last_error or "Неизвестная ошибка",
        advice=(
            "Проверьте подключение к интернету и доступность API. "
            "Если используется локальная модель — убедитесь, что она запущена на порту 11434. "
            "Попробуйте переключиться на другую модель в разделе «Настройки»."
        ),
    )


def _parse_llm_response(raw_text: str, model_id: str) -> EvaluationResult:
    """
    Парсит JSON-ответ LLM.
    Устойчив к:
    - markdown-блокам ```json ... ```
    - <think>...</think> блокам reasoning-моделей
    - незначительным отклонениям формата
    """
    # Убираем <think>...</think> блоки — используются reasoning-моделями
    clean = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

    # Убираем markdown-блоки ```json ... ``` если модель их добавила
    clean = re.sub(r"```(?:json)?\s*", "", clean).replace("```", "").strip()

    # Если после очистки текст не начинается с { — ищем JSON внутри
    if not clean.startswith("{"):
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            clean = match.group(0)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        raise EvaluationError(
            message="LLM вернула некорректный ответ",
            detail=f"Ошибка парсинга JSON: {e}\nОтвет модели: {raw_text[:300]}",
            advice=(
                "Попробуйте запустить оценку повторно. "
                "Если ошибка повторяется — попробуйте другую модель."
            ),
        )

    criteria_results = data.get("criteria_results", {})
    recommendations = data.get("recommendations", [])

    # Нормализуем значения — приводим к допустимым
    allowed = {"ok", "warning", "error"}
    criteria_results = {
        k: v if v in allowed else "warning"
        for k, v in criteria_results.items()
    }

    color = _compute_color(criteria_results)

    return EvaluationResult(
        color=color,
        criteria_results=criteria_results,
        recommendations=recommendations,
        model_used=model_id,
    )
