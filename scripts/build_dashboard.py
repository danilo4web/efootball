"""Gera dashboard/dashboard.html a partir de data/best_team.json.

O HTML/CSS/JS do dashboard fica em scripts/dashboard_assets/template.html
(com os placeholders __TEAM_JSON__, __PHOTOS_JSON__ e __ANTON_B64__), pra
nao depender de nada fora do repositorio -- versoes anteriores desse script
viviam so no scratchpad da sessao e se perderam entre conversas.

Fotos das mini-cartas ficam cacheadas em
scripts/dashboard_assets/minicards_b64.json (label -> PNG em base64). Um
jogador novo em players.txt que ainda nao tem foto cacheada aparece com um
avatar de iniciais no lugar da carta (fallback ja suportado pelo template).

Uso: python3 scripts/build_dashboard.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT, "scripts", "dashboard_assets")
TEMPLATE_PATH = os.path.join(ASSETS_DIR, "template.html")
ANTON_PATH = os.path.join(ASSETS_DIR, "anton_b64.txt")
PHOTOS_PATH = os.path.join(ASSETS_DIR, "minicards_b64.json")
TEAM_PATH = os.path.join(ROOT, "data", "best_team.json")
OUT_PATH = os.path.join(ROOT, "dashboard", "dashboard.html")


def main():
    template = open(TEMPLATE_PATH, encoding="utf-8").read()
    anton_b64 = open(ANTON_PATH, encoding="utf-8").read().strip()
    photos = json.load(open(PHOTOS_PATH, encoding="utf-8"))
    team = json.load(open(TEAM_PATH, encoding="utf-8"))

    missing_photos = sorted({p["label"] for p in team["roster"]} - set(photos))
    if missing_photos:
        print(f"AVISO: sem foto cacheada pra {len(missing_photos)} jogador(es) "
              f"(vao aparecer com avatar de iniciais): {missing_photos}")

    html = template
    html = html.replace("__ANTON_B64__", anton_b64)
    html = html.replace("__TEAM_JSON__", json.dumps(team, ensure_ascii=False))
    html = html.replace("__PHOTOS_JSON__", json.dumps(photos, ensure_ascii=False))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {OUT_PATH} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
