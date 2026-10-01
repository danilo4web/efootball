"""Le data/card_database.json (listagem de cartas "reais" do efhub, geradas
por scripts/card_scraper/fetch_card_listing.js) e busca a Community Tier
Ranking de cada uma via /api/player-tier, classificando por tier
(S+/S/A/B/C/D/E) usando o tier mais votado (moda), igual common.mode_tier.

Resumivel: quem ja tem tier salvo em data/card_tiers.json e reaproveitado
sem bater na rede de novo (use --force pra rebuscar tudo). Salva o
progresso a cada CHECKPOINT_EVERY cartas, entao pode ser interrompido e
retomado sem perder o que ja foi buscado.

Uso:
    python3 scripts/fetch_all_tiers.py            # usa cache existente
    python3 scripts/fetch_all_tiers.py --force     # rebusca tudo
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from common import fetch_player_tier, mode_tier  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_PATH = os.path.join(ROOT, "data", "card_database.json")
OUT_PATH = os.path.join(ROOT, "data", "card_tiers.json")

REQUEST_DELAY = 0.35
CHECKPOINT_EVERY = 200


def load_cards():
    if not os.path.exists(IN_PATH):
        print(f"{IN_PATH} nao encontrado. Rode "
              f"scripts/card_scraper/fetch_card_listing.js primeiro.", file=sys.stderr)
        sys.exit(1)
    return json.load(open(IN_PATH, encoding="utf-8"))["cards"]


def load_cache():
    if not os.path.exists(OUT_PATH):
        return {}
    try:
        existing = json.load(open(OUT_PATH, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {c["id"]: c for c in existing.get("cards", []) if c.get("id")}


def save(results):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"fetchedAt": time.time(), "cards": results}, f, indent=2, ensure_ascii=False)


def main():
    force = "--force" in sys.argv
    cards = load_cards()
    cache = {} if force else load_cache()

    results = []
    fetched_count = 0
    cached_count = 0
    error_count = 0

    for i, card in enumerate(cards, 1):
        cid = card["id"]
        cached = cache.get(cid)
        if cached and cached.get("tierFetchOk"):
            results.append(cached)
            cached_count += 1
            continue

        try:
            tier_data = fetch_player_tier(cid)
            tier, votes = mode_tier(tier_data.get("tierCounts") or {})
            entry = {
                "id": cid,
                "name": card.get("name"),
                "team": card.get("team"),
                "position": card.get("position"),
                "overallRating": card.get("overallRating"),
                "playingStyle": card.get("playingStyle"),
                "playerType": card.get("playerType"),
                "consensusTier": tier,
                "consensusVotes": votes,
                "totalPlacements": tier_data.get("totalPlacements", 0),
                "tierFetchOk": True,
            }
            fetched_count += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(cards)}] ERRO em {card.get('name')} ({cid}): {e}", file=sys.stderr)
            entry = {
                "id": cid, "name": card.get("name"), "team": card.get("team"),
                "position": card.get("position"), "overallRating": card.get("overallRating"),
                "playingStyle": card.get("playingStyle"), "playerType": card.get("playerType"),
                "consensusTier": None, "consensusVotes": 0, "totalPlacements": 0,
                "tierFetchOk": False,
            }
            error_count += 1

        results.append(entry)

        if i % CHECKPOINT_EVERY == 0:
            save(results)
            print(f"[{i}/{len(cards)}] checkpoint salvo "
                  f"({fetched_count} buscadas, {cached_count} do cache, {error_count} erros)",
                  file=sys.stderr)

        time.sleep(REQUEST_DELAY)

    save(results)
    print(f"\nOK: {len(results)} cartas salvas em {OUT_PATH} "
          f"({fetched_count} buscadas agora, {cached_count} do cache, {error_count} erros)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
