"""
Автономный скрипт для загрузки страницы через Playwright.
Запускается как отдельный процесс из web.py.
Принимает URL как аргумент, выводит JSON в stdout.

Возвращает список инструкций — каждый <instruction> на странице = отдельный элемент.
"""

import sys
import json
import traceback
import re


def write_result(data: dict):
    output = json.dumps(data, ensure_ascii=False) + "\n"
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.flush()


def clean_shy(text: str) -> str:
    return text.replace("\u00ad", "")


def get_text(el) -> str:
    text = el.get_text(separator=" ")
    text = clean_shy(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' ([.,:;!?»)])', r'\1', text)
    return text.strip()


def parse_page(page) -> list:
    """
    Парсит страницу и возвращает список инструкций.
    Каждый элемент: {"title": str, "content": str}

    Для PT Help Portal: каждый <instruction> = отдельная инструкция.
    Для других сайтов: вся страница = одна инструкция (fallback через markdownify).
    """
    from bs4 import BeautifulSoup

    html = page.inner_html("body")
    soup = BeautifulSoup(html, "html.parser")

    # Удаляем навигацию и лишние блоки
    for tag in soup.select("nav, header, footer, aside, .no-print, nav-bar"):
        tag.decompose()

    # Заголовок страницы
    title_el = soup.select_one(".project-page__title, h1")
    page_title = clean_shy(title_el.get_text()).strip() if title_el else page.title() or "Без названия"

    instructions_els = soup.find_all("instruction")

    if instructions_els:
        results = []
        for instr in instructions_els:
            # Вводная фраза как заголовок инструкции
            task = instr.find("task")
            task_text = get_text(task) if task else ""

            lines = []
            if task_text:
                lines.append(task_text)
                lines.append("")

            actions = instr.find_all("action")
            for i, action in enumerate(actions, 1):
                inter = action.find("intermediate-result")
                inter_text = ""
                if inter:
                    inter_text = get_text(inter)
                    inter.decompose()

                action_text = get_text(action)
                if action_text:
                    lines.append(f"{i}. {action_text}")
                if inter_text:
                    lines.append(f"   {inter_text}")

            content = "\n".join(lines).strip()
            if content:
                results.append({
                    "title": task_text or page_title,
                    "content": content,
                })

        return results

    else:
        # Fallback: markdownify для обычных сайтов
        import markdownify
        main = soup.select_one("main, article, [role=main]") or soup.find("body")
        md = markdownify.markdownify(
            str(main),
            heading_style="ATX",
            bullets="-",
            strip=["script", "style"],
        )
        md = clean_shy(md)
        md = re.sub(r'\n{3,}', '\n\n', md)
        return [{"title": page_title, "content": md.strip()}]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        write_result({"ok": False, "error": "URL not provided"})
        sys.exit(1)

    url = sys.argv[1]

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page_title = page.title() or url
            instructions = parse_page(page)
            browser.close()

        if not instructions:
            write_result({"ok": False, "error": "Не удалось извлечь текст со страницы"})
            sys.exit(1)

        write_result({"ok": True, "title": page_title, "instructions": instructions})

    except Exception as e:
        write_result({"ok": False, "error": repr(e), "tb": traceback.format_exc()})
        sys.exit(1)
