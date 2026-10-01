"""Demo gravada do Onze Ideal (Playwright) contra o serviço local em http://localhost:8765.

Não aciona o "Limpar Cache" de verdade (seria uma raspagem real do efhub);
mostra o dashboard e a recusa de uma chamada vinda de outra origem.
"""
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path.home() / "Sandbox/_auditoria-projetos/.tools"))
from demo_helpers import Demo, finalize_video, video_info  # noqa: E402

BASE = "http://localhost:8765/dashboard.html"
OUT = Path(__file__).parent

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(OUT / "_raw"),
                              record_video_size={"width": 1440, "height": 900}, locale="pt-BR")
    page = ctx.new_page()
    d = Demo(page, OUT)
    seen = []
    page.on("request", lambda r: seen.append(r.url) if "clear-cache" in r.url else None)

    d.goto(BASE, "Onze Ideal — melhor time a partir das suas cartas, com atributos e tier do efhub", 4)
    d.shot("01-onze-titular.png")
    page.get_by_role("button", name="OPÇÃO 2 · 4-2-3-1").click(); d.pause(2)
    d.caption("Duas opções de formação, com reservas e não relacionados", 3)
    page.mouse.wheel(0, 900); d.pause(2); page.mouse.wheel(0, -900)
    for aba, legenda in [("ANÁLISES", "Análises ofensiva e defensiva do time"),
                         ("ELENCO POR POSIÇÃO", "Elenco por posição, com a nota de cada carta"),
                         ("VOTOS POR CARTA", "Community Tier Ranking: votos por carta"),
                         ("TREINAMENTO IDEAL", "Treinamento ideal (Overmax estimado)"),
                         ("COMPARAR JOGADORES", "Comparar jogadores lado a lado")]:
        page.get_by_role("button", name=aba).click(); page.wait_for_timeout(1200)
        d.caption(legenda, 2.6)
        page.mouse.wheel(0, 500); d.pause(1.2); page.mouse.wheel(0, -500)
    d.shot("02-comparar.png")
    page.get_by_role("button", name="ONZE TITULAR").click(); d.pause(1)
    page.get_by_role("button", name="🗑️ Limpar Cache").hover(); d.pause(1)
    d.caption("Correção: 'Limpar Cache' agora também gera o dashboard de novo (antes, recarregar mostrava o time antigo)", 5)
    d.caption("e não apaga mais do time quem o efhub não respondeu (mantém o dado anterior)", 4)
    d.shot("03-limpar-cache.png")

    d.goto((OUT / "outro-site.html").as_uri(), "Correção: outro site aberto no navegador tentando disparar a raspagem…", 3)
    page.wait_for_timeout(1500)
    status = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST",
                             "-H", "Origin: https://site-qualquer.example", "http://localhost:8765/api/clear-cache"],
                            capture_output=True, text=True).stdout
    d.caption(f"…é recusado pelo servidor (HTTP {status}); antes, qualquer página disparava uma raspagem completa do efhub", 5)
    d.shot("04-melhoria-origem.png")
    d.goto("http://localhost:8765/api/cache-status", "Status do cache: nenhuma raspagem foi disparada", 3)

    video = page.video.path()
    ctx.close()
    browser.close()

final = finalize_video(video, OUT)
print(video_info(final))
