"""Monta o melhor time 4-2-2-2 (estilo Contra-Ataque) a partir de
data/players.json e salva o resultado em data/best_team.json.

Uso: python3 scripts/select_team.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import (  # noqa: E402
    POSITION_GROUPS, SLOT_COUNT, SLOT_GROUP, eligible_slots, role_score,
    training_bonus, TIER_VALUE, resolve_tier, playstyle_pt, overmax_value,
    player_positions, projected_stats, FAMILIARITY_FACTOR, FORMATIONS,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_PATH = os.path.join(ROOT, "data", "players.json")
OUT_PATH = os.path.join(ROOT, "data", "best_team.json")


def build_slot_candidates(players, slot_count=None):
    """Para cada SLOT tatico da formacao (por padrao o 4-2-2-2, SLOT_COUNT
    global -- passe slot_count pra outra formacao, ex. 4-2-3-1), lista
    (score, player, familiarity_factor) elegiveis, ordenado do melhor pro
    pior. role_score ja e calculado com os pesos/playstyle_fit especificos
    daquele slot -- lateral defensivo e ofensivo, por exemplo, concorrem
    com formulas diferentes desde aqui."""
    slot_count = SLOT_COUNT if slot_count is None else slot_count
    candidates = {slot: [] for slot in slot_count}
    for p in players:
        slots = eligible_slots(p)
        for slot, factor in slots.items():
            if slot not in candidates:
                continue
            score = role_score(p, slot) * factor
            candidates[slot].append({
                "player": p,
                "score": round(score, 2),
                "familiarity_factor": factor,
                "native": factor == 1.0,
            })
    for slot in candidates:
        candidates[slot].sort(key=lambda c: c["score"], reverse=True)
    return candidates


def greedy_assign_slots(slot_candidates, slot_count=None):
    """Atribuicao gulosa global: ordena todos os pares (jogador, slot)
    elegiveis pelo score e vai fechando vaga por vaga, jogador so pode
    ser escalado uma vez (em UM slot, entre os slots da formacao)."""
    slot_count = SLOT_COUNT if slot_count is None else slot_count
    all_pairs = []
    for slot, lst in slot_candidates.items():
        for c in lst:
            all_pairs.append((c["score"], slot, c))
    all_pairs.sort(key=lambda x: x[0], reverse=True)

    used_players = set()
    slots_left = dict(slot_count)
    starters = {slot: [] for slot in slot_count}

    for score, slot, c in all_pairs:
        name = c["player"]["name"]
        if slots_left[slot] <= 0:
            continue
        if name in used_players:
            continue
        starters[slot].append(c)
        used_players.add(name)
        slots_left[slot] -= 1

    return starters, used_players


def group_candidates_from_slots(slot_candidates):
    """Colapsa os candidatos por SLOT de volta pros 6 GRUPOS genericos
    (GK/CB/FB/DMF/AMF/CF), usado so pro banco/excluidos -- cada jogador
    entra com o MELHOR score entre os slots daquele grupo (ex.: um lateral
    entra no banco de 'FB' com o maior entre o score dele como
    defensivo e como ofensivo)."""
    by_group = {group: {} for group in POSITION_GROUPS}
    for slot, lst in slot_candidates.items():
        group = SLOT_GROUP[slot]
        for c in lst:
            label = c["player"]["label"]
            existing = by_group[group].get(label)
            if existing is None or c["score"] > existing["score"]:
                by_group[group][label] = c
    return {
        group: sorted(d.values(), key=lambda c: c["score"], reverse=True)
        for group, d in by_group.items()
    }


def pick_side(player, other_side_taken=None):
    """Decide LB ou RB pra um lateral, evitando conflito com o outro lateral
    ja escalado."""
    positions = {player["position"]}
    for extra in player.get("additionalPositions") or []:
        positions.add(extra["position"])
    sides = positions & {"LB", "RB"}
    if len(sides) == 1:
        return next(iter(sides))
    if other_side_taken and other_side_taken in sides:
        sides = sides - {other_side_taken}
    return sorted(sides)[0] if sides else "LB"


def alternates_for(group, candidates, used_players, limit=2):
    out = []
    for c in candidates[group]:
        if c["player"]["name"] in used_players:
            continue
        out.append(c)
        if len(out) >= limit:
            break
    return out


def primary_playstyle_pt(p):
    """Estilo em PT-BR pra mostrar como titulo (embaixo do nome). Alguns
    cards so tem estilo DEFENSIVO preenchido (ex.: Caicedo -> playingStyle
    vem '$undefined', so playingStyleDefensive = 'Destroyer' / 'O
    destruidor') -- cai pro defensivo nesse caso em vez de mostrar nada."""
    return playstyle_pt(p["playingStyle"]) or playstyle_pt(p["playingStyleDefensive"])


def summarize(c):
    p = c["player"]
    tier = p.get("tier") or {}
    bonus = training_bonus(p)
    tier_counts = tier.get("tierCounts", {})
    top_tier, top_votes = resolve_tier(tier_counts, tier.get("consensusTier"))
    return {
        "label": p["label"],
        "name": p["name"],
        "url": p["url"],
        "overall": p["overall"],
        "overmax": min(99, round(p["overall"] + bonus)),
        "native_position": p["position"],
        "playing_style": p["playingStyle"],
        "playing_style_pt": primary_playstyle_pt(p),
        "playing_style_defensive": p["playingStyleDefensive"],
        "playing_style_defensive_pt": playstyle_pt(p["playingStyleDefensive"]),
        "role_score": c["score"],
        "native_fit": c["native"],
        "familiarity_factor": c["familiarity_factor"],
        "stats": p["stats"],
        "consensus_tier": top_tier,
        "consensus_tier_votes": top_votes,
        "tier_placements": tier.get("totalPlacements", 0),
        "tier_counts": tier_counts,
        "level_cap": p.get("levelCap", 1),
        "training_bonus": bonus,
        "community_skills": (p.get("community_skills") or {}).get("top_skills", []),
        "community_training": (p.get("community_training") or {}).get("top_build"),
    }


def roster_entry(p):
    tier = p.get("tier") or {}
    tier_counts = tier.get("tierCounts", {})
    top_tier, top_votes = resolve_tier(tier_counts, tier.get("consensusTier"))
    bonus = training_bonus(p)
    return {
        "label": p["label"],
        "name": p["name"],
        "url": p["url"],
        "overall": p["overall"],
        "overmax": min(99, round(p["overall"] + bonus)),
        "level_cap": p.get("levelCap", 1),
        "native_position": p["position"],
        "playing_style": p["playingStyle"],
        "playing_style_pt": primary_playstyle_pt(p),
        "playing_style_defensive": p["playingStyleDefensive"],
        "playing_style_defensive_pt": playstyle_pt(p["playingStyleDefensive"]),
        "consensus_tier": top_tier,
        "consensus_tier_votes": top_votes,
        "tier_placements": tier.get("totalPlacements", 0),
        "community_skills": (p.get("community_skills") or {}).get("top_skills", []),
    }


def build_roster(players):
    entries = [roster_entry(p) for p in players]

    def sort_key(e):
        tier_rank = TIER_VALUE.get(e["consensus_tier"], -1)
        return (tier_rank, e["consensus_tier_votes"])

    entries.sort(key=sort_key, reverse=True)
    return entries


# especificacao da aba de comparacao: (posicao "crua" do jogo, slot tatico
# ou None). Laterais ficam separados por LADO (LB/RB), nao por papel
# (defensivo/ofensivo) -- comparar "candidatos a lateral esquerdo entre
# si" e mais direto que pre-julgar quem e defensivo/ofensivo, essa decisao
# fica pro usuario ver nos atributos. Ja VOL/MLG vem os DOIS de jogadores
# DMF, mas cada um rankeado pelo role_score do papel especifico (1o
# volante/ancora vs box-to-box avancado) -- sem isso as duas abas
# mostrariam exatamente os mesmos 3 nomes, na mesma ordem.
COMPARISON_SPEC = {
    "GK": ("GK", None),
    "CB": ("CB", None),
    "LB": ("LB", None),
    "RB": ("RB", None),
    "VOL": ("DMF", "DMF_ANCHOR"),
    "MLG": ("DMF", "DMF_BOX"),
    "LMF": ("LMF", None),
    "AMF": ("AMF", None),
    "RMF": ("RMF", None),
    "CF": ("CF", None),
}


def comparison_entry(p, factor, slot=None):
    """Igual summarize(), mas usa os atributos JA COM a projecao de treino
    (projected_stats) -- a aba de comparacao existe pra decisao manual do
    usuario, entao mostra o jogador no potencial estimado, nao no card
    destreinado. Nao aplica o filtro de tier minimo/overmax minimo (essa
    aba e pra comparar candidatos livremente, inclusive os que o motor
    principal excluiu automaticamente). Quando 'slot' e passado (VOL/MLG),
    o desempate de ordenacao usa o role_score daquele papel especifico em
    vez do Overmax generico -- so pra decidir quem aparece primeiro, nao
    e mostrado como atributo na tabela."""
    tier = p.get("tier") or {}
    tier_counts = tier.get("tierCounts", {})
    top_tier, top_votes = resolve_tier(tier_counts, tier.get("consensusTier"))
    bonus = training_bonus(p)
    entry = {
        "label": p["label"],
        "name": p["name"],
        "url": p["url"],
        "overall": p["overall"],
        "overmax": min(99, round(p["overall"] + bonus)),
        "level_cap": p.get("levelCap", 1),
        "native_position": p["position"],
        "playing_style_pt": primary_playstyle_pt(p),
        "playing_style_defensive_pt": playstyle_pt(p["playingStyleDefensive"]),
        "consensus_tier": top_tier,
        "consensus_tier_votes": top_votes,
        "tier_placements": tier.get("totalPlacements", 0),
        "native_fit": factor == 1.0,
        "familiarity_factor": factor,
        "stats": projected_stats(p),
    }
    entry["_rank_value"] = round(role_score(p, slot) * factor, 2) if slot else entry["overmax"]
    return entry


def build_comparisons(players):
    """Pra cada entrada de COMPARISON_SPEC, lista TODOS os candidatos entre
    TODOS os jogadores do elenco que jogam ali (nativo ou posicao
    secundaria), sem filtro de tier/overmax minimo. A aba de comparacao
    mostra so os 3 primeiros por padrao, mas o usuario pode adicionar
    qualquer um dos outros -- por isso a lista inteira vai pro
    best_team.json, nao so um top-3 fixo."""
    out = {}
    for key, (raw_pos, slot) in COMPARISON_SPEC.items():
        candidates = []
        for p in players:
            for pos, fam in player_positions(p):
                if pos == raw_pos:
                    factor = FAMILIARITY_FACTOR[fam]
                    candidates.append(comparison_entry(p, factor, slot))
                    break
        # familiaridade primeiro (nativo > 2a posicao > 3a posicao) -- sem
        # isso um jogador excelente numa posicao secundaria mal marcada
        # (ex.: um volante com RB "C" de familiaridade) dominava a lista so
        # pelo Overall/role_score alto, mesmo sendo um encaixe ruim ali de
        # verdade. Desempate: role_score do papel (VOL/MLG) ou Overmax
        # geral (resto).
        candidates.sort(key=lambda c: (c["familiarity_factor"], c["_rank_value"]), reverse=True)
        for c in candidates:
            del c["_rank_value"]
        out[key] = candidates
    return out


# tier minimo (mais votado) pra um jogador sequer concorrer a titular/banco.
# Quem tem B, C, D ou E como tier mais votado vai direto pra "nao
# relacionados" -- entra na disputa quem e S+/S/A ou ainda nao tem voto.
MIN_QUALIFYING_TIERS = {"S+", "S", "A", None}

# Overmax minimo (overall + projecao de treino) pra concorrer a titular/banco.
MIN_OVERMAX = 90


def exclusion_reason(p):
    """None se o jogador pode disputar titular/banco; senao, o motivo do
    corte automatico (tier baixo ou Overmax abaixo do piso)."""
    tier = p.get("tier") or {}
    top, _ = resolve_tier(tier.get("tierCounts") or {}, tier.get("consensusTier"))
    if top not in MIN_QUALIFYING_TIERS:
        return f"tier {top}"
    omax = overmax_value(p)
    if omax < MIN_OVERMAX:
        return f"overmax {omax:.0f} < {MIN_OVERMAX}"
    return None


def is_low_tier(p):
    return exclusion_reason(p) is not None


# Vagas lidas com [0] na montagem: sem ninguém aqui não existe time.
OBRIGATORIOS = ("GK", "FB_DEF", "FB_OFF", "DMF_ANCHOR", "DMF_BOX")


def completar_vagas(starters, used_players, low_tier_players, slot_count, rotulo=""):
    """Vaga sem ninguem acima do corte de tier recebe o melhor jogador abaixo
    do corte (com aviso), em vez de deixar o time sem goleiro e estourar
    IndexError -- o que derrubava o botao Limpar Cache inteiro. Sem nenhum
    candidato nem abaixo do corte, encerra com a lista do que falta."""
    faltando = {s: n - len(starters[s]) for s, n in slot_count.items() if len(starters[s]) < n}
    if faltando:
        reserva = build_slot_candidates(low_tier_players, slot_count=slot_count)
        for slot, n in faltando.items():
            for c in reserva[slot]:
                if n <= 0:
                    break
                if c["player"]["name"] in used_players:
                    continue
                starters[slot].append(c)
                used_players.add(c["player"]["name"])
                n -= 1
                print(f"AVISO{rotulo}: {slot} sem ninguém acima do corte; usando {c['player']['name']} "
                      f"({exclusion_reason(c['player'])})", file=sys.stderr)
    sem = [s for s in OBRIGATORIOS if s in slot_count and not starters[s]]
    if sem:
        sys.exit(f"Elenco sem jogador para: {', '.join(sem)}. Adicione em players.txt um jogador "
                 f"dessas posições e rode de novo.")


def build_formation_4231(eligible_players, low_tier_players):
    """Monta a formacao 2 (4-2-3-1): reaproveita os MESMOS slots de
    defesa/meio do 4-2-2-2 (GK/CB/FB_DEF/FB_OFF/DMF_ANCHOR/DMF_BOX) --
    mesmos pesos, mesma logica -- e so troca a frente: em vez de 2 MAT +
    2 CA, vira 1 MLE + 1 MAT + 1 MLD + 1 CA (centroavante sozinho).
    Ataque e defesa usam a MESMA disposicao em campo (sem alternar como no
    4-2-2-2) -- ver FORMATIONS["4-2-3-1"]["same_attack_defense"]."""
    slot_count = FORMATIONS["4-2-3-1"]["slot_count"]
    groups = ["GK", "CB", "FB", "DMF", "MLE", "AMF", "MLD", "CF"]

    slot_candidates = build_slot_candidates(eligible_players, slot_count=slot_count)
    starters, used_players = greedy_assign_slots(slot_candidates, slot_count=slot_count)
    candidates = group_candidates_from_slots(slot_candidates)
    completar_vagas(starters, used_players, low_tier_players, slot_count, rotulo=" (4-2-3-1)")

    for slot, need in slot_count.items():
        got = len(starters[slot])
        if got < need:
            print(f"AVISO (4-2-3-1): slot {slot} só encontrou {got}/{need} jogadores elegíveis",
                  file=sys.stderr)

    fb_def_side = pick_side(starters["FB_DEF"][0]["player"])
    fb_off_side = pick_side(starters["FB_OFF"][0]["player"], other_side_taken=fb_def_side)
    if fb_def_side == fb_off_side:
        fb_off_side = "RB" if fb_def_side == "LB" else "LB"

    def one(slot, role):
        """Slots de 1 titular so (MLE/AMF/MLD/CF nessa formacao) -- lista
        vazia se ninguem do elenco atingiu o corte de tier pra essa vaga,
        em vez de estourar IndexError (ex.: elenco sem ninguem de LMF/RMF)."""
        return [dict(summarize(starters[slot][0]), role=role)] if starters[slot] else []

    lineup = {
        "GK": [dict(summarize(starters["GK"][0]), role="GK")],
        "CB": [dict(summarize(c), role="CB") for c in starters["CB"]],
        "FB": [
            dict(summarize(starters["FB_DEF"][0]), role="Lateral Defensivo", side=fb_def_side),
            dict(summarize(starters["FB_OFF"][0]), role="Lateral Ofensivo", side=fb_off_side),
        ],
        "DMF": [
            dict(summarize(starters["DMF_ANCHOR"][0]), role="1º Volante (Âncora)"),
            dict(summarize(starters["DMF_BOX"][0]), role="Volante Box-to-Box"),
        ],
        "MLE": one("MLE", "Meia-Lateral Esquerdo"),
        "AMF": one("AMF", "MAT"),
        "MLD": one("MLD", "Meia-Lateral Direito"),
        "CF": one("CF", "CA"),
    }

    bench = {}
    for group in groups:
        bench[group] = [summarize(c) for c in alternates_for(group, candidates, used_players)]

    squad_labels = {c["label"] for glist in lineup.values() for c in glist}
    squad_labels |= {c["label"] for glist in bench.values() for c in glist}

    best_by_player = {}
    for group, lst in candidates.items():
        for c in lst:
            label = c["player"]["label"]
            if label not in best_by_player or c["score"] > best_by_player[label][1]["score"]:
                best_by_player[label] = (group, c)

    excluded = []
    for label, (group, c) in best_by_player.items():
        if label not in squad_labels:
            entry = summarize(c)
            entry["best_group"] = group
            entry["excluded_reason"] = None
            excluded.append(entry)

    low_tier_slot_candidates = build_slot_candidates(low_tier_players, slot_count=slot_count)
    low_tier_candidates = group_candidates_from_slots(low_tier_slot_candidates)
    low_tier_best = {}
    for group, lst in low_tier_candidates.items():
        for c in lst:
            label = c["player"]["label"]
            if label not in low_tier_best or c["score"] > low_tier_best[label][1]["score"]:
                low_tier_best[label] = (group, c)
    for label, (group, c) in low_tier_best.items():
        if label in squad_labels:  # escalado por falta de opção (completar_vagas)
            continue
        entry = summarize(c)
        entry["best_group"] = group
        entry["excluded_reason"] = exclusion_reason(c["player"])
        excluded.append(entry)

    excluded.sort(key=lambda e: e["role_score"], reverse=True)

    all_starters = [p for glist in lineup.values() for p in glist]
    all_overmax = [p["overmax"] for p in all_starters]
    all_speeds = [p["stats"]["speed"] for p in all_starters]
    all_accel = [p["stats"]["acceleration"] for p in all_starters]
    avg_role_score = sum(p["role_score"] for p in all_starters) / len(all_starters)
    native_fit_pct = round(100 * sum(1 for p in all_starters if p["native_fit"]) / len(all_starters))

    bench_unique = {}
    for glist in bench.values():
        for p in glist:
            if p["label"] not in bench_unique or p["role_score"] > bench_unique[p["label"]]["role_score"]:
                bench_unique[p["label"]] = p
    squad_for_grade = all_starters + list(bench_unique.values())
    avg_squad_role_score = sum(p["role_score"] for p in squad_for_grade) / len(squad_for_grade)
    team_grade = min(TIER_VALUE.items(), key=lambda kv: abs(kv[1] - avg_squad_role_score))[0]

    outfield = [p for g in ("CB", "FB", "DMF", "MLE", "AMF", "MLD", "CF") for p in lineup[g]]

    def avg_stat(*keys):
        vals = [p["stats"][k] for p in outfield for k in keys]
        return round(sum(vals) / len(vals), 1)

    radar_off = {
        "Finalização": avg_stat("finishing"),
        "Criação": avg_stat("offensiveAwareness"),
        "Físico": avg_stat("physicalContact"),
        "Drible": avg_stat("dribbling"),
        "Velocidade": avg_stat("speed", "acceleration"),
        "Passe": avg_stat("lowPass", "loftedPass"),
    }
    radar_def = {
        "Desarme": avg_stat("ballWinning"),
        "Marcação": avg_stat("defensiveAwareness"),
        "Aéreo": avg_stat("heading", "jump"),
        "Posicionamento": avg_stat("trackingBack"),
        "Interceptação": avg_stat("defensiveAwareness", "ballWinning"),
        "Cobertura": avg_stat("trackingBack", "stamina"),
    }

    def group_avg_score(*grps):
        vals = [p["role_score"] for g in grps for p in lineup[g]]
        return round(sum(vals) / len(vals), 1)

    category_bars = {
        "Ataque": group_avg_score("MLE", "AMF", "MLD", "CF"),
        "Meio-campo": group_avg_score("DMF"),
        "Defesa": group_avg_score("CB", "FB"),
        "Goleiro": group_avg_score("GK"),
    }

    weakest_list = sorted(bench_unique.values(), key=lambda p: p["role_score"])[:3]
    next_to_leave = [
        {
            "label": p["label"],
            "name": p["name"],
            "url": p["url"],
            "role_score": p["role_score"],
            "consensus_tier": p["consensus_tier"],
            "consensus_tier_votes": p["consensus_tier_votes"],
            "reason": "Ranking baixo",
        }
        for p in weakest_list
    ]

    return {
        "formation": "4-2-3-1",
        "team_style": "Contra-Ataque",
        "same_attack_defense": True,
        "lineup": lineup,
        "bench": bench,
        "excluded": excluded,
        "team_summary": {
            "avg_overall": round(sum(all_overmax) / len(all_overmax), 1),
            "avg_speed": round(sum(all_speeds) / len(all_speeds), 1),
            "avg_acceleration": round(sum(all_accel) / len(all_accel), 1),
            "avg_role_score": round(avg_role_score, 1),
            "native_fit_pct": native_fit_pct,
            "team_grade": team_grade,
            "radar_off": radar_off,
            "radar_def": radar_def,
            "category_bars": category_bars,
            "next_to_leave": next_to_leave,
        },
    }


def main():
    data = json.load(open(IN_PATH, encoding="utf-8"))
    players = data["players"]

    eligible_players = [p for p in players if not is_low_tier(p)]
    low_tier_players = [p for p in players if is_low_tier(p)]

    slot_candidates = build_slot_candidates(eligible_players)
    starters, used_players = greedy_assign_slots(slot_candidates)
    candidates = group_candidates_from_slots(slot_candidates)
    completar_vagas(starters, used_players, low_tier_players, SLOT_COUNT)

    for slot, need in SLOT_COUNT.items():
        got = len(starters[slot])
        if got < need:
            print(f"AVISO: slot {slot} só encontrou {got}/{need} jogadores elegíveis",
                  file=sys.stderr)

    fb_def_side = pick_side(starters["FB_DEF"][0]["player"])
    fb_off_side = pick_side(starters["FB_OFF"][0]["player"], other_side_taken=fb_def_side)
    if fb_def_side == fb_off_side:
        fb_off_side = "RB" if fb_def_side == "LB" else "LB"

    lineup = {
        "GK": [dict(summarize(starters["GK"][0]), role="GK")],
        "CB": [dict(summarize(c), role="CB") for c in starters["CB"]],
        "FB": [
            dict(summarize(starters["FB_DEF"][0]), role="Lateral Defensivo", side=fb_def_side),
            dict(summarize(starters["FB_OFF"][0]), role="Lateral Ofensivo", side=fb_off_side),
        ],
        "DMF": [
            dict(summarize(starters["DMF_ANCHOR"][0]), role="1º Volante (Âncora)"),
            dict(summarize(starters["DMF_BOX"][0]), role="Volante Box-to-Box"),
        ],
        "AMF": [dict(summarize(c), role="MAT") for c in starters["AMF"]],
        "CF": [dict(summarize(c), role="CA") for c in starters["CF"]],
    }

    bench = {}
    for group in POSITION_GROUPS:
        bench[group] = [summarize(c) for c in alternates_for(group, candidates, used_players)]

    squad_labels = {c["label"] for glist in lineup.values() for c in glist}
    squad_labels |= {c["label"] for glist in bench.values() for c in glist}

    best_by_player = {}
    for group, lst in candidates.items():
        for c in lst:
            label = c["player"]["label"]
            if label not in best_by_player or c["score"] > best_by_player[label][1]["score"]:
                best_by_player[label] = (group, c)

    excluded = []
    for label, (group, c) in best_by_player.items():
        if label not in squad_labels:
            entry = summarize(c)
            entry["best_group"] = group
            entry["excluded_reason"] = None
            excluded.append(entry)

    # jogadores com tier abaixo de S (A/B/C/D/E) nem disputam vaga -- vao
    # direto pra cá, com o motivo explicito.
    low_tier_slot_candidates = build_slot_candidates(low_tier_players)
    low_tier_candidates = group_candidates_from_slots(low_tier_slot_candidates)
    low_tier_best = {}
    for group, lst in low_tier_candidates.items():
        for c in lst:
            label = c["player"]["label"]
            if label not in low_tier_best or c["score"] > low_tier_best[label][1]["score"]:
                low_tier_best[label] = (group, c)
    for label, (group, c) in low_tier_best.items():
        if label in squad_labels:  # escalado por falta de opção (completar_vagas)
            continue
        entry = summarize(c)
        entry["best_group"] = group
        entry["excluded_reason"] = exclusion_reason(c["player"])
        excluded.append(entry)

    excluded.sort(key=lambda e: e["role_score"], reverse=True)

    roster = build_roster(players)
    comparisons = build_comparisons(players)

    all_speeds = [c["player"]["stats"]["speed"] for glist in starters.values() for c in glist]
    all_accel = [c["player"]["stats"]["acceleration"] for glist in starters.values() for c in glist]

    all_starters = [p for glist in lineup.values() for p in glist]
    all_overmax = [p["overmax"] for p in all_starters]
    avg_role_score = sum(p["role_score"] for p in all_starters) / len(all_starters)
    native_fit_pct = round(100 * sum(1 for p in all_starters if p["native_fit"]) / len(all_starters))

    # nota do time considera titulares + reservas (nao so os 11 titulares).
    bench_unique = {}
    for glist in bench.values():
        for p in glist:
            if p["label"] not in bench_unique or p["role_score"] > bench_unique[p["label"]]["role_score"]:
                bench_unique[p["label"]] = p
    squad_for_grade = all_starters + list(bench_unique.values())
    avg_squad_role_score = sum(p["role_score"] for p in squad_for_grade) / len(squad_for_grade)
    team_grade = min(TIER_VALUE.items(), key=lambda kv: abs(kv[1] - avg_squad_role_score))[0]

    outfield = [p for g in ("CB", "FB", "DMF", "AMF", "CF") for p in lineup[g]]

    def avg_stat(*keys):
        vals = [p["stats"][k] for p in outfield for k in keys]
        return round(sum(vals) / len(vals), 1)

    radar_off = {
        "Finalização": avg_stat("finishing"),
        "Criação": avg_stat("offensiveAwareness"),
        "Físico": avg_stat("physicalContact"),
        "Drible": avg_stat("dribbling"),
        "Velocidade": avg_stat("speed", "acceleration"),
        "Passe": avg_stat("lowPass", "loftedPass"),
    }
    radar_def = {
        "Desarme": avg_stat("ballWinning"),
        "Marcação": avg_stat("defensiveAwareness"),
        "Aéreo": avg_stat("heading", "jump"),
        "Posicionamento": avg_stat("trackingBack"),
        "Interceptação": avg_stat("defensiveAwareness", "ballWinning"),
        "Cobertura": avg_stat("trackingBack", "stamina"),
    }

    def group_avg_score(*groups):
        vals = [p["role_score"] for g in groups for p in lineup[g]]
        return round(sum(vals) / len(vals), 1)

    category_bars = {
        "Ataque": group_avg_score("AMF", "CF"),
        "Meio-campo": group_avg_score("DMF"),
        "Defesa": group_avg_score("CB", "FB"),
        "Goleiro": group_avg_score("GK"),
    }

    # dica: os 3 jogadores mais fracos que ainda estao no banco -- candidatos
    # mais provaveis a serem cortados se aparecer carta melhor.
    weakest_list = sorted(bench_unique.values(), key=lambda p: p["role_score"])[:3]
    next_to_leave = [
        {
            "label": p["label"],
            "name": p["name"],
            "url": p["url"],
            "role_score": p["role_score"],
            "consensus_tier": p["consensus_tier"],
            "consensus_tier_votes": p["consensus_tier_votes"],
            "reason": "Ranking baixo",
        }
        for p in weakest_list
    ]

    formation2 = build_formation_4231(eligible_players, low_tier_players)

    result = {
        "formation": "4-2-2-2",
        "team_style": "Contra-Ataque",
        "lineup": lineup,
        "bench": bench,
        "excluded": excluded,
        "roster": roster,
        "comparisons": comparisons,
        "team_summary": {
            "avg_overall": round(sum(all_overmax) / len(all_overmax), 1),
            "avg_speed": round(sum(all_speeds) / len(all_speeds), 1),
            "avg_acceleration": round(sum(all_accel) / len(all_accel), 1),
            "avg_role_score": round(avg_role_score, 1),
            "native_fit_pct": native_fit_pct,
            "team_grade": team_grade,
            "radar_off": radar_off,
            "radar_def": radar_def,
            "category_bars": category_bars,
            "next_to_leave": next_to_leave,
        },
        "formation2": formation2,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Time salvo em {OUT_PATH}", file=sys.stderr)
    for group in ["GK", "CB", "FB", "DMF", "AMF", "CF"]:
        for c in lineup[group]:
            print(f"  {c['role']:22s} {c['label']:20s} score={c['role_score']}", file=sys.stderr)
    print("\n-- 4-2-3-1 --", file=sys.stderr)
    for group in ["GK", "CB", "FB", "DMF", "MLE", "AMF", "MLD", "CF"]:
        for c in formation2["lineup"][group]:
            print(f"  {c['role']:22s} {c['label']:20s} score={c['role_score']}", file=sys.stderr)


if __name__ == "__main__":
    main()
