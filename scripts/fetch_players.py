"""Le players.txt, busca cada jogador no efhub.com e salva os atributos
normalizados em data/players.json.

Resumivel: quem ja foi buscado com sucesso ha menos de CACHE_HOURS horas e
reaproveitado direto do data/players.json existente, sem bater na rede de
novo. Quem deu erro na ultima vez (ou nunca foi buscado) e sempre tentado
de novo, com ate 3 tentativas cada (retry com backoff, ver common.py).

Uso:
    python3 scripts/fetch_players.py            # usa o cache de 6h
    python3 scripts/fetch_players.py --force     # ignora o cache, rebusca tudo
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from common import fetch_player, load_players_txt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYERS_TXT = os.path.join(ROOT, "players.txt")
OUT_PATH = os.path.join(ROOT, "data", "players.json")

CACHE_HOURS = 6


def load_cache():
    """Retorna {url: player_data} do players.json existente, se houver."""
    if not os.path.exists(OUT_PATH):
        return {}
    try:
        existing = json.load(open(OUT_PATH, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {p["url"]: p for p in existing.get("players", []) if p.get("url")}


def is_fresh(player_data):
    fetched_at = player_data.get("fetched_at")
    if not fetched_at:
        return False
    age_hours = (time.time() - fetched_at) / 3600
    return age_hours < CACHE_HOURS


def main():
    force = "--force" in sys.argv
    entries = load_players_txt(PLAYERS_TXT)
    cache = {} if force else load_cache()

    results = []
    errors = []
    fetched_count = 0
    cached_count = 0

    for i, (label, url) in enumerate(entries, 1):
        cached = cache.get(url)
        if cached and is_fresh(cached):
            age_min = round((time.time() - cached["fetched_at"]) / 60)
            print(f"[{i}/{len(entries)}] {label} -> cache ({age_min}min atras)", file=sys.stderr)
            results.append(cached)
            cached_count += 1
            continue

        print(f"[{i}/{len(entries)}] {label} -> {url}", file=sys.stderr)
        try:
            data = fetch_player(url, label=label)
            results.append(data)
            fetched_count += 1
        except Exception as e:
            print(f"  ERRO (depois de retries): {e}", file=sys.stderr)
            errors.append({"label": label, "url": url, "error": str(e)})
            # se tinha um dado antigo (mesmo vencido), mantem em vez de
            # perder o jogador inteiro so por essa rodada ter falhado
            if cached:
                print("  usando dado antigo em cache pra nao perder o jogador", file=sys.stderr)
                results.append(cached)
        time.sleep(0.6)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"players": results, "errors": errors}, f, indent=2, ensure_ascii=False)

    print(f"\nOK: {len(results)} jogadores salvos em {OUT_PATH} "
          f"({fetched_count} buscados agora, {cached_count} do cache)", file=sys.stderr)
    if errors:
        print(f"FALHAS: {len(errors)} -> {[e['label'] for e in errors]}", file=sys.stderr)


if __name__ == "__main__":
    main()
