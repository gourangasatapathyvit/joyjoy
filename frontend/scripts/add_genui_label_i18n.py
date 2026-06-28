#!/usr/bin/env python3
"""One-shot: add `model.genui` (generative-UI toggle label) to all locales."""
import re
from pathlib import Path

LOC = Path(__file__).resolve().parent.parent / "src" / "i18n" / "locales"

T = {
    "en": "Generative UI",
    "de": "Generative UI",
    "es": "IU generativa",
    "fr": "UI générative",
    "it": "UI generativa",
    "pt": "IU generativa",
    "ru": "Генеративный UI",
    "uk": "Генеративний UI",
    "tr": "Üretken arayüz",
    "hu": "Generatív felület",
    "af": "Generatiewe UI",
    "ga": "Comhéadan giniúnach",
    "ja": "生成 UI",
    "ko": "생성형 UI",
    "zh": "生成式 UI",
    "zh-hant": "生成式 UI",
}


def esc(s: str) -> str:
    return s.replace('"', '\\"')


for code, val in T.items():
    path = LOC / f"{code}.ts"
    text = path.read_text(encoding="utf-8")
    if "genui:" in text:
        print(f"skip {code}.ts")
        continue
    m = re.search(r"\n\tmodel:\s*\{", text)
    if not m:
        raise SystemExit(f"no model block in {code}.ts")
    close = text.index("\n\t},", m.end())
    text = text[: close + 1] + f'\t\tgenui: "{esc(val)}",\n' + text[close + 1 :]
    path.write_text(text, encoding="utf-8")
    print(f"updated {code}.ts")

print("done")
