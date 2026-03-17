import sys
sys.path.insert(0, '.')
import fitz
from statistics import median
from backend.services.parser.pdf_parser import _classify_size, _collect_font_sizes, _is_garbage_block, _clean_pua, _BODY_TEXT_PATTERNS, MIN_HEADING_TEXT_LEN

doc = fitz.open('data/uploads/pt_mc101.20_mc-adminguide_ru_20260220.pdf')
all_sizes = _collect_font_sizes(doc)
med = median(all_sizes)
print('median:', med)

page = doc[49]
for b in page.get_text('dict')['blocks']:
    if b['type'] != 0: continue
    parts = []
    max_size_all = 0      # максимум по всем спанам (старая логика)
    max_size_clean = 0    # максимум только по спанам без PUA (новая логика)
    for l in b['lines']:
        for sp in l['spans']:
            parts.append(sp['text'])
            if sp['size'] > max_size_all:
                max_size_all = sp['size']
            span_clean = _clean_pua(sp['text']).strip()
            if span_clean and sp['size'] > max_size_clean:
                max_size_clean = sp['size']
    text = _clean_pua(' '.join(parts).strip())
    if not text or _is_garbage_block(text): continue
    level_old = _classify_size(max_size_all, med)
    level_new = _classify_size(max_size_clean, med)
    if level_new > 0 and (_BODY_TEXT_PATTERNS.match(text) or len(text.strip()) < MIN_HEADING_TEXT_LEN):
        level_new = 0
    if level_old != level_new or level_new > 0:
        print(f'size_all={max_size_all} size_clean={max_size_clean} level_old={level_old} level_new={level_new} text={repr(text[:50])}')
