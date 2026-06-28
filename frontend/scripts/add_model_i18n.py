#!/usr/bin/env python3
"""One-shot: add model selector i18n keys (searchPlaceholder, allProviders,
noModels) into each locale file's `model: { ... }` object."""
import re
from pathlib import Path

LOC = Path(__file__).resolve().parent.parent / "src" / "i18n" / "locales"

# locale -> (searchPlaceholder, allProviders, noModels)
T = {
    "en": ("Search models…", "All", "No models found."),
    "de": ("Modelle suchen…", "Alle", "Keine Modelle gefunden."),
    "es": ("Buscar modelos…", "Todos", "No se encontraron modelos."),
    "fr": ("Rechercher des modèles…", "Tous", "Aucun modèle trouvé."),
    "it": ("Cerca modelli…", "Tutti", "Nessun modello trovato."),
    "pt": ("Pesquisar modelos…", "Todos", "Nenhum modelo encontrado."),
    "ru": ("Поиск моделей…", "Все", "Модели не найдены."),
    "uk": ("Пошук моделей…", "Усі", "Моделі не знайдено."),
    "tr": ("Model ara…", "Tümü", "Model bulunamadı."),
    "hu": ("Modellek keresése…", "Összes", "Nincs találat."),
    "af": ("Soek modelle…", "Almal", "Geen modelle gevind nie."),
    "ga": ("Cuardaigh múnlaí…", "Gach ceann", "Níor aimsíodh aon mhúnla."),
    "ja": ("モデルを検索…", "すべて", "モデルが見つかりません。"),
    "ko": ("모델 검색…", "전체", "모델을 찾을 수 없습니다."),
    "zh": ("搜索模型…", "全部", "未找到模型。"),
    "zh-hant": ("搜尋模型…", "全部", "找不到模型。"),
}

FILES = {k: (k + ".ts") for k in T}


def esc(s: str) -> str:
    return s.replace('"', '\\"')


def block(v) -> str:
    search, allp, none = v
    return (
        f'\t\tsearchPlaceholder: "{esc(search)}",\n'
        f'\t\tallProviders: "{esc(allp)}",\n'
        f'\t\tnoModels: "{esc(none)}",\n'
    )


for code, fname in FILES.items():
    path = LOC / fname
    text = path.read_text(encoding="utf-8")
    if "allProviders:" in text:
        print(f"skip {fname} (already has keys)")
        continue
    m = re.search(r"\n\tmodel:\s*\{", text)
    if not m:
        raise SystemExit(f"no model block in {fname}")
    close = text.index("\n\t},", m.end())
    new = text[: close + 1] + block(T[code]) + text[close + 1 :]
    path.write_text(new, encoding="utf-8")
    print(f"updated {fname}")

print("done")
