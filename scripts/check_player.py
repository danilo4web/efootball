"""Modulo de verificacao: recebe um link efhub.com de um jogador e diz se
ele entraria no time titular 4-2-2-2 (Contra-Ataque) atual, e por que.

Compara o jogador contra data/best_team.json (gerado por select_team.py).
Roda select_team.py antes se quiser atualizar o time com o elenco mais
recente de data/players.json.

Uso:
    python3 scripts/check_player.py https://efhub.com/players/12345
    python3 scripts/check_player.py https://efhub.com/players/12345 --json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import (  # noqa: E402
    fetch_player, eligible_slots, SLOT_GROUP, role_score, training_bonus, resolve_tier,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEST_TEAM_PATH = os.path.join(ROOT, "data", "best_team.json")

# rotulo legivel de cada SLOT tatico (nao so a posicao generica -- lateral
# defensivo e ofensivo, 1o volante e volante box-to-box sao papeis
# diferentes desde a pontuacao, entao o candidato tem que ser comparado
# contra o titular EXATO daquele papel, nao contra o grupo inteiro).
SLOT_LABELS = {
    "GK": "Goleiro (GK)",
    "CB": "Zagueiro (CB)",
    "FB_DEF": "Lateral Defensivo (LB/RB)",
    "FB_OFF": "Lateral Ofensivo (LB/RB)",
    "DMF_ANCHOR": "1º Volante / Âncora (DMF)",
    "DMF_BOX": "Volante Box-to-Box (DMF)",
    "AMF": "Meia-Atacante (MAT)",
    "CF": "Centroavante (CA)",
}

# como cada slot filtra os titulares do grupo generico da lineup (CB/AMF/CF
# tem 2 titulares do MESMO papel -- compara contra o mais fraco dos dois;
# FB e DMF tem 2 titulares de papeis DIFERENTES -- compara so contra o
# titular daquele papel especifico).
def starters_for_slot(team, slot):
    group = SLOT_GROUP[slot]
    lineup_group = team["lineup"].get(group, [])
    role_filter = {
        "FB_DEF": "Lateral Defensivo",
        "FB_OFF": "Lateral Ofensivo",
        "DMF_ANCHOR": "1º Volante (Âncora)",
        "DMF_BOX": "Volante Box-to-Box",
    }.get(slot)
    if role_filter is None:
        return lineup_group
    return [s for s in lineup_group if s.get("role") == role_filter]


def load_best_team():
    if not os.path.exists(BEST_TEAM_PATH):
        print("data/best_team.json não encontrado. Rode scripts/select_team.py primeiro.",
              file=sys.stderr)
        sys.exit(1)
    return json.load(open(BEST_TEAM_PATH, encoding="utf-8"))


def evaluate(url: str, label: str = None):
    candidate = fetch_player(url, label=label)
    team = load_best_team()
    slots = eligible_slots(candidate)

    verdicts = []
    best_case = None  # melhor (margem positiva) encontrada

    for slot, factor in slots.items():
        starters = starters_for_slot(team, slot)
        if not starters:
            continue
        cand_score = round(role_score(candidate, slot) * factor, 2)
        weakest = min(starters, key=lambda s: s["role_score"])
        margin = round(cand_score - weakest["role_score"], 2)

        verdict = {
            "group": slot,
            "group_label": SLOT_LABELS[slot],
            "candidate_score": cand_score,
            "native_fit": factor == 1.0,
            "weakest_starter": weakest["label"],
            "weakest_starter_role": weakest["role"],
            "weakest_starter_score": weakest["role_score"],
            "margin": margin,
            "would_start": margin > 0,
        }
        verdicts.append(verdict)
        if margin > 0 and (best_case is None or margin > best_case["margin"]):
            best_case = verdict

    enters = best_case is not None

    return {
        "player": {
            "name": candidate["name"],
            "label": label or candidate["name"],
            "url": url,
            "overall": candidate["overall"],
            "position": candidate["position"],
            "additional_positions": [a["position"] for a in candidate["additionalPositions"]],
            "playing_style": candidate["playingStyle"],
            "consensus_tier": resolve_tier(
                (candidate.get("tier") or {}).get("tierCounts") or {},
                (candidate.get("tier") or {}).get("consensusTier"),
            )[0],
            "consensus_tier_votes": resolve_tier(
                (candidate.get("tier") or {}).get("tierCounts") or {},
                (candidate.get("tier") or {}).get("consensusTier"),
            )[1],
            "tier_placements": (candidate.get("tier") or {}).get("totalPlacements", 0),
            "level_cap": candidate.get("levelCap", 1),
            "training_bonus": training_bonus(candidate),
        },
        "eligible_groups": [v["group"] for v in verdicts],
        "verdicts": sorted(verdicts, key=lambda v: v["margin"], reverse=True),
        "enters_team": enters,
        "best_case": best_case,
    }


def print_report(result):
    p = result["player"]
    tier_txt = (f"{p['consensus_tier']} ({p['consensus_tier_votes']} votos, de {p['tier_placements']} no total)"
                if p["consensus_tier"] else "sem votos ainda")
    print(f"\n{p['label']} — {p['position']}"
          + (f" ({'/'.join(p['additional_positions'])})" if p["additional_positions"] else "")
          + f" | Overall {p['overall']} | Estilo: {p['playing_style']} | Tier: {tier_txt}")
    if p["level_cap"] > 1:
        print(f"Treinável até nível {p['level_cap']} · projeção de treino aplicada: +{p['training_bonus']} nos atributos")
    else:
        print("Já no nível máximo (não treinável)")
    print(f"URL: {p['url']}")

    if not result["verdicts"]:
        print("\n❌ NÃO ENTRA: nenhuma das posições desse jogador existe no esquema "
              "4-2-2-2 (GK, CB, LB/RB, DMF, AMF, CF).")
        return

    print()
    for v in result["verdicts"]:
        fit = "posição natural" if v["native_fit"] else "posição secundária"
        mark = "✅" if v["would_start"] else "—"
        sign = "+" if v["margin"] >= 0 else ""
        print(f"{mark} {v['group_label']:22s} ({fit}): sua nota {v['candidate_score']} "
              f"vs {v['weakest_starter']} ({v['weakest_starter_role']}) "
              f"= {v['weakest_starter_score']}  [{sign}{v['margin']}]")

    print()
    if result["enters_team"]:
        b = result["best_case"]
        print(f"✅ ENTRA NO TIME: supera {b['weakest_starter']} como {b['group_label']} "
              f"({b['weakest_starter_role']}) por {b['margin']} pontos na nota do papel.")
    else:
        closest = max(result["verdicts"], key=lambda v: v["margin"])
        print(f"❌ NÃO ENTRA: mesmo na sua melhor posição ({closest['group_label']}), "
              f"fica {abs(closest['margin'])} pontos abaixo de "
              f"{closest['weakest_starter']} ({closest['weakest_starter_role']}).")
    print()


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args:
        print("Uso: python3 scripts/check_player.py <url efhub> [--json]", file=sys.stderr)
        sys.exit(1)
    url = args[0]
    result = evaluate(url)
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
