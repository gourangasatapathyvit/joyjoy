#!/usr/bin/env python3
"""One-shot: insert Context Display + Sources i18n keys into every locale file.

Adds, inside each file's `chat: { ... }` object (before its closing brace):
  copied, sources, context.{label,usage,input,cached,output,reasoning,total}
"""
import re
from pathlib import Path

LOC = Path(__file__).resolve().parent.parent / "src" / "i18n" / "locales"

# locale -> (copied, sources, label, usage, input, cached, output, reasoning, total)
T = {
    "en": ("Copied to clipboard", "Sources", "Context usage", "Usage", "Input", "Cached", "Output", "Reasoning", "Total"),
    "de": ("In die Zwischenablage kopiert", "Quellen", "Kontextnutzung", "Nutzung", "Eingabe", "Zwischengespeichert", "Ausgabe", "Denkprozess", "Gesamt"),
    "es": ("Copiado al portapapeles", "Fuentes", "Uso del contexto", "Uso", "Entrada", "En caché", "Salida", "Razonamiento", "Total"),
    "fr": ("Copié dans le presse-papiers", "Sources", "Utilisation du contexte", "Utilisation", "Entrée", "En cache", "Sortie", "Raisonnement", "Total"),
    "it": ("Copiato negli appunti", "Fonti", "Utilizzo del contesto", "Utilizzo", "Input", "In cache", "Output", "Ragionamento", "Totale"),
    "pt": ("Copiado para a área de transferência", "Fontes", "Uso do contexto", "Uso", "Entrada", "Em cache", "Saída", "Raciocínio", "Total"),
    "ru": ("Скопировано в буфер обмена", "Источники", "Использование контекста", "Использование", "Ввод", "Кэшировано", "Вывод", "Рассуждение", "Всего"),
    "uk": ("Скопійовано в буфер обміну", "Джерела", "Використання контексту", "Використання", "Вхід", "Кешовано", "Вихід", "Міркування", "Усього"),
    "tr": ("Panoya kopyalandı", "Kaynaklar", "Bağlam kullanımı", "Kullanım", "Giriş", "Önbellekte", "Çıkış", "Akıl yürütme", "Toplam"),
    "hu": ("Vágólapra másolva", "Források", "Kontextushasználat", "Használat", "Bemenet", "Gyorsítótárazott", "Kimenet", "Érvelés", "Összesen"),
    "af": ("Na knipbord gekopieer", "Bronne", "Konteksgebruik", "Gebruik", "Invoer", "Gekas", "Uitvoer", "Redenering", "Totaal"),
    "ga": ("Cóipeáilte chuig an ngearrthaisce", "Foinsí", "Úsáid comhthéacs", "Úsáid", "Ionchur", "I dtaisce", "Aschur", "Réasúnaíocht", "Iomlán"),
    "ja": ("クリップボードにコピーしました", "ソース", "コンテキスト使用量", "使用量", "入力", "キャッシュ", "出力", "推論", "合計"),
    "ko": ("클립보드에 복사됨", "출처", "컨텍스트 사용량", "사용량", "입력", "캐시됨", "출력", "추론", "합계"),
    "zh": ("已复制到剪贴板", "来源", "上下文用量", "用量", "输入", "缓存", "输出", "推理", "总计"),
    "zh-hant": ("已複製到剪貼簿", "來源", "上下文用量", "用量", "輸入", "快取", "輸出", "推理", "總計"),
}

FILES = {
    "en": "en.ts", "de": "de.ts", "es": "es.ts", "fr": "fr.ts", "it": "it.ts",
    "pt": "pt.ts", "ru": "ru.ts", "uk": "uk.ts", "tr": "tr.ts", "hu": "hu.ts",
    "af": "af.ts", "ga": "ga.ts", "ja": "ja.ts", "ko": "ko.ts", "zh": "zh.ts",
    "zh-hant": "zh-hant.ts",
}


def esc(s: str) -> str:
    return s.replace('"', '\\"')


def block(v) -> str:
    copied, sources, label, usage, inp, cached, output, reasoning, total = v
    return (
        f'\t\tcopied: "{esc(copied)}",\n'
        f'\t\tsources: "{esc(sources)}",\n'
        f'\t\tcontext: {{\n'
        f'\t\t\tlabel: "{esc(label)}",\n'
        f'\t\t\tusage: "{esc(usage)}",\n'
        f'\t\t\tinput: "{esc(inp)}",\n'
        f'\t\t\tcached: "{esc(cached)}",\n'
        f'\t\t\toutput: "{esc(output)}",\n'
        f'\t\t\treasoning: "{esc(reasoning)}",\n'
        f'\t\t\ttotal: "{esc(total)}",\n'
        f'\t\t}},\n'
    )


for code, fname in FILES.items():
    path = LOC / fname
    text = path.read_text(encoding="utf-8")
    if "context: {" in text and "copied:" in text:
        print(f"skip {fname} (already has keys)")
        continue
    # Find the chat: { ... } object and insert before its closing "\n\t},".
    m = re.search(r"\n\tchat:\s*\{", text)
    if not m:
        raise SystemExit(f"no chat block in {fname}")
    close = text.index("\n\t},", m.end())
    new = text[: close + 1] + block(T[code]) + text[close + 1 :]
    path.write_text(new, encoding="utf-8")
    print(f"updated {fname}")

print("done")
