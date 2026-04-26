"""
Сервис генерации контекста продукта для проекта.

Логика:
- Принимает список non-instruction разделов из документов проекта
- Отправляет LLM-запрос с просьбой составить структурированное описание продукта
- Возвращает текст контекста (~400–700 слов)
- Использует ту же активную модель, что и evaluator
"""

import time
import urllib.request
from dataclasses import dataclass
from typing import Optional

import httpx

from backend.config import get_active_model


# ── Ошибка генерации ──────────────────────────────────────────────────────────

@dataclass
class ContextGenerationError(Exception):
    """Ошибка генерации контекста с человекочитаемым описанием."""
    message: str
    advice: str


# ── Промпт ────────────────────────────────────────────────────────────────────

CONTEXT_SYSTEM_PROMPT = """Ты — технический аналитик документации. Тебе предоставлены вводные разделы из документации к программному продукту.

Составь структурированное описание продукта, которое будет использоваться как контекст при автоматической проверке качества инструкций.

Описание должно содержать:
1. Название и класс продукта — 1–2 предложения
2. Целевые аудитории и их роли — 1–2 предложения
3. Ключевые термины с кратким определением — 10–15 терминов, каждый в отдельной строке
4. Основные компоненты или модули — если они явно упомянуты в тексте

Требования:
- Объём: 400–700 слов
- Пиши только факты из документации, без домыслов
- Формат: свободный текст с заголовками для каждого пункта
- Язык: русский"""


def _build_context_prompt(sections: list) -> str:
    """Формирует промпт из non-instruction разделов."""
    parts = []
    current_doc_id = None

    for section in sections:
        if section.document_id != current_doc_id:
            current_doc_id = section.document_id
            parts.append(f"\n=== Документ ID {current_doc_id} ===")

        title = section.title or ""
        content = (section.content or "")[:800]  # не более 800 символов на раздел
        parts.append(f"\n## {title}\n{content}")

    sections_text = "\n".join(parts)
    return f"Проанализируй следующие разделы документации и составь описание продукта.\n\n{sections_text}"


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _get_api_key(provider: str, model_cfg) -> Optional[str]:
    """Возвращает API-ключ для модели."""
    import os
    if provider == "local":
        return "local"
    if model_cfg and getattr(model_cfg, "api_key", None):
        return model_cfg.api_key
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY")
    return os.environ.get("OPENAI_API_KEY")


def _build_headers(provider: str, api_key: Optional[str]) -> dict:
    if provider == "anthropic":
        return {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01",
        }
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or 'none'}",
    }


# ── Основная функция ──────────────────────────────────────────────────────────

def generate_project_context(sections: list) -> str:
    """
    Генерирует текстовый контекст продукта из non-instruction разделов.

    Принимает список объектов Instruction с classification='non-instruction'.
    Возвращает строку с описанием продукта.
    Выбрасывает ContextGenerationError при неудаче.
    """
    model_cfg = get_active_model()
    if not model_cfg:
        raise ContextGenerationError(
            message="Не настроена активная модель LLM",
            advice="Перейдите в раздел «Настройки» и настройте модель.",
        )

    model_id = model_cfg.id
    base_url = model_cfg.base_url.rstrip("/")
    provider = model_cfg.provider

    api_key = _get_api_key(provider, model_cfg)
    if model_cfg.requires_key and not api_key:
        raise ContextGenerationError(
            message="API-ключ не настроен",
            advice="Перейдите в раздел «Настройки» и введите API-ключ.",
        )

    user_prompt = _build_context_prompt(sections)
    headers = _build_headers(provider, api_key)

    if provider == "anthropic":
        payload = {
            "model": model_id,
            "max_tokens": 2000,
            "system": CONTEXT_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
    else:
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": CONTEXT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }

    proxies = urllib.request.getproxies()
    proxy_url = proxies.get("https") or proxies.get("http") or None

    last_error = None
    for attempt in range(1, 4):
        try:
            client_kwargs = {"timeout": 120.0}
            if proxy_url:
                client_kwargs["proxies"] = proxy_url

            with httpx.Client(**client_kwargs) as client:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )

            if response.status_code == 401:
                raise ContextGenerationError(
                    message="Неверный API-ключ",
                    advice="Проверьте API-ключ в разделе «Настройки».",
                )
            if response.status_code == 429:
                raise ContextGenerationError(
                    message="Превышен лимит запросов к API",
                    advice="Подождите несколько минут и попробуйте снова.",
                )
            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                if attempt < 3:
                    time.sleep(2 * attempt)
                    continue
                raise ContextGenerationError(
                    message="Сервер LLM недоступен",
                    advice="Попробуйте через несколько минут.",
                )

            response.raise_for_status()
            resp_json = response.json()

            if "choices" in resp_json:
                return resp_json["choices"][0]["message"]["content"].strip()
            elif "content" in resp_json:
                return resp_json["content"][0]["text"].strip()
            else:
                raise ContextGenerationError(
                    message="Неизвестный формат ответа от API",
                    advice="Проверьте настройки модели.",
                )

        except ContextGenerationError:
            raise
        except Exception as e:
            last_error = str(e)
            if attempt < 3:
                time.sleep(2 * attempt)
                continue

    raise ContextGenerationError(
        message=f"Не удалось получить ответ от LLM после 3 попыток",
        advice="Проверьте подключение к интернету и доступность API.",
    )
