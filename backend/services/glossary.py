"""
Извлечение глоссария продукта из документа.

Логика:
- Объединяет текст всех разделов документа
- Лемматизирует через pymorphy3 (для корректной работы YAKE с русским)
- Прогоняет через YAKE для извлечения ключевых терминов
- Фильтрует шум: слишком короткие слова, цифры, стоп-сокращения
- Возвращает список из не более MAX_TERMS уникальных терминов
"""

import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

MAX_TERMS = 30          # максимальное количество терминов в глоссарии
MIN_TERM_LEN = 4        # минимальная длина термина в символах
YAKE_MAX_NGRAM = 2      # максимальная длина n-граммы (1 или 2 слова)
YAKE_TOP = 60           # сколько кандидатов брать из YAKE до фильтрации

# Стоп-слова: технические аббревиатуры и слова, бесполезные в глоссарии
_STOP_TERMS = {
    # Сокращения
    "см", "т.е", "т.д", "т.п", "пр", "др", "стр", "рис", "табл",
    # Технические
    "http", "https", "www", "html", "json", "xml", "sql", "api",
    "true", "false", "null", "none",
    # Общеупотребительные глаголы и слова, не являющиеся терминами
    "нажать", "нажмите", "выбрать", "выберите", "указать", "укажите",
    "открыть", "открыть", "закрыть", "перейти", "добавить", "удалить",
    "настроить", "создать", "сохранить", "ввести", "введите",
    "отправить", "отправляет", "обрабатывает", "определяет",
    "данные", "значение", "значения", "параметр", "параметры",
    "настройка", "настройки", "система", "системе", "раздел",
    "пользователь", "пользователя", "пользователей",
    "подключение", "подключения", "подключению",
    "список", "строка", "поле", "кнопка", "вкладка", "окно",
    "файл", "папка", "путь", "адрес", "имя", "название",
    "этот", "этого", "этом", "этой", "тот", "той",
    "который", "которого", "которой", "которые",
}


def _lemmatize_text(text: str) -> str:
    """
    Лемматизирует текст через pymorphy3.
    Заменяет каждое слово его нормальной формой (именительный падеж, ед. число).
    Знаки препинания и структура предложений сохраняются — YAKE их использует.
    """
    try:
        import pymorphy3
        morph = pymorphy3.MorphAnalyzer()

        def lemmatize_word(word: str) -> str:
            parsed = morph.parse(word)
            if parsed:
                return parsed[0].normal_form
            return word.lower()

        # Обрабатываем только слова из кириллицы длиннее 2 символов
        return re.sub(
            r"[А-Яа-яЁё]{3,}",
            lambda m: lemmatize_word(m.group(0)),
            text,
        )
    except Exception as e:
        log.warning(f"Лемматизация недоступна: {e}")
        return text


def _is_valid_term(term: str) -> bool:
    """Проверяет, пригоден ли термин для включения в глоссарий."""
    t = term.strip().lower()
    if len(t) < MIN_TERM_LEN:
        return False
    # Только цифры или преимущественно цифры — не термин
    if re.fullmatch(r"[\d\s\-_.]+", t):
        return False
    # Нет ни одной кириллической или латинской буквы
    if not re.search(r"[А-Яа-яЁёA-Za-z]", t):
        return False
    # Каждое слово термина проверяем по стоп-списку
    words = re.findall(r"[А-Яа-яЁёA-Za-z]+", t)
    if not words:
        return False
    # Если все слова — стоп-слова, термин бесполезен
    if all(w in _STOP_TERMS for w in words):
        return False
    # Биграммы из двух одинаковых слов (МТА МТА) — артефакт YAKE
    if len(words) == 2 and words[0] == words[1]:
        return False
    # Одиночное слово из стоп-списка
    if len(words) == 1 and words[0] in _STOP_TERMS:
        return False
    # Фильтр глагольных форм 3-го лица (без лемматизации):
    # -ет, -ит, -ают, -яют, -ует, -ивает, -ывает
    _VERB_ENDINGS = ("ает", "яет", "ует", "ивает", "ывает", "обрабатывает",
                     "отправляет", "определяет", "связывает")
    if any(w.endswith(_VERB_ENDINGS) for w in words):
        return False
    return True


def extract_glossary(sections: list) -> list[str]:
    """
    Извлекает глоссарий продукта из списка разделов документа.

    Параметры:
        sections — список объектов с полями title и content (из parse_document)

    Возвращает:
        Список строк-терминов (не более MAX_TERMS), отсортированных по релевантности.
    """
    # Собираем полный текст документа из всех разделов
    parts = []
    for section in sections:
        if section.title:
            parts.append(section.title)
        if section.content:
            # Убираем markdown-маркеры жирного, чтобы не мешали YAKE
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", section.content)
            parts.append(clean)

    full_text = "\n".join(parts)
    if not full_text.strip():
        return []

    # Лемматизируем перед подачей в YAKE
    lemmatized = _lemmatize_text(full_text)

    try:
        import yake
        extractor = yake.KeywordExtractor(
            lan="ru",
            n=YAKE_MAX_NGRAM,
            dedupLim=0.7,        # порог дедупликации похожих терминов
            dedupFunc="seqm",
            windowsSize=2,
            top=YAKE_TOP,
        )
        keywords = extractor.extract_keywords(lemmatized)
        # YAKE возвращает (term, score), меньший score = более релевантный
        candidates = [kw for kw, _score in keywords]

    except Exception as e:
        log.error(f"Ошибка YAKE при извлечении глоссария: {e}")
        return []

    # Фильтруем и дедуплицируем
    seen = set()
    result = []
    for term in candidates:
        normalized = term.strip().lower()
        if not _is_valid_term(term):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(term.strip())
        if len(result) >= MAX_TERMS:
            break

    log.info(f"Глоссарий: извлечено {len(result)} терминов из {len(sections)} разделов")
    return result


def glossary_to_prompt_block(glossary: Optional[list]) -> str:
    """
    Формирует блок для промпта из списка терминов.
    Возвращает пустую строку если глоссарий пуст или не задан.
    """
    if not glossary:
        return ""
    terms = ", ".join(glossary)
    return (
        f"\n--- ТЕРМИНЫ ПРОДУКТА ---\n"
        f"Следующие термины являются устоявшимися в данном продукте "
        f"и не требуют расшифровки в каждом разделе: {terms}\n"
        f"--- КОНЕЦ ТЕРМИНОВ ---\n"
    )
