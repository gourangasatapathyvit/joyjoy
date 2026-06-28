#!/usr/bin/env python3
"""One-shot: add the `connection` namespace (heartbeat indicator) to locales."""
from pathlib import Path

LOC = Path(__file__).resolve().parent.parent / "src" / "i18n" / "locales"

# locale -> (connecting, connected, offline)
T = {
    "en": ("Connecting…", "Connected", "Offline"),
    "de": ("Verbinde…", "Verbunden", "Offline"),
    "es": ("Conectando…", "Conectado", "Sin conexión"),
    "fr": ("Connexion…", "Connecté", "Hors ligne"),
    "it": ("Connessione…", "Connesso", "Offline"),
    "pt": ("Conectando…", "Conectado", "Offline"),
    "ru": ("Подключение…", "Подключено", "Не в сети"),
    "uk": ("Підключення…", "Підключено", "Не в мережі"),
    "tr": ("Bağlanıyor…", "Bağlandı", "Çevrimdışı"),
    "hu": ("Csatlakozás…", "Csatlakozva", "Offline"),
    "af": ("Verbind…", "Verbind", "Vanlyn"),
    "ga": ("Ag nascadh…", "Nasctha", "As líne"),
    "ja": ("接続中…", "接続済み", "オフライン"),
    "ko": ("연결 중…", "연결됨", "오프라인"),
    "zh": ("连接中…", "已连接", "离线"),
    "zh-hant": ("連線中…", "已連線", "離線"),
}


def esc(s: str) -> str:
    return s.replace('"', '\\"')


for code, (a, b, c) in T.items():
    path = LOC / f"{code}.ts"
    text = path.read_text(encoding="utf-8")
    if "connection:" in text:
        print(f"skip {code}.ts (already has namespace)")
        continue
    anchor = "\n\tlanguage:"
    i = text.index(anchor)
    block = (
        f'\tconnection: {{\n'
        f'\t\tconnecting: "{esc(a)}",\n'
        f'\t\tconnected: "{esc(b)}",\n'
        f'\t\toffline: "{esc(c)}",\n'
        f'\t}},\n'
    )
    text = text[: i + 1] + block + text[i + 1 :]
    path.write_text(text, encoding="utf-8")
    print(f"updated {code}.ts")

print("done")
