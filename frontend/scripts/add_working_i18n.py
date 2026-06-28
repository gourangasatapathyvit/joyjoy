#!/usr/bin/env python3
"""One-shot: add chat.working (dot-matrix working indicator label) to locales."""
from pathlib import Path
import re

LOC = Path(__file__).resolve().parent.parent / "src" / "i18n" / "locales"

T = {
    "en": "Assistant is working",
    "de": "Assistent arbeitet",
    "es": "El asistente está trabajando",
    "fr": "L'assistant travaille",
    "it": "L'assistente sta lavorando",
    "pt": "O assistente está trabalhando",
    "ru": "Ассистент работает",
    "uk": "Асистент працює",
    "tr": "Asistan çalışıyor",
    "hu": "Az asszisztens dolgozik",
    "af": "Assistent werk",
    "ga": "Tá an cúntóir ag obair",
    "ja": "アシスタントが作業中です",
    "ko": "어시스턴트가 작업 중입니다",
    "zh": "助手正在处理",
    "zh-hant": "助手正在處理",
}

for code, val in T.items():
    path = LOC / f"{code}.ts"
    text = path.read_text(encoding="utf-8")
    if "working:" in text:
        print(f"skip {code}.ts (already has key)")
        continue
    m = re.search(r"\n\tchat:\s*\{", text)
    if not m:
        raise SystemExit(f"no chat block in {code}.ts")
    close = text.index("\n\t},", m.end())
    block = f'\t\tworking: "{val}",\n'
    text = text[: close + 1] + block + text[close + 1 :]
    path.write_text(text, encoding="utf-8")
    print(f"updated {code}.ts")

print("done")
