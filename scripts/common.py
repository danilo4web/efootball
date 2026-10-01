"""Funcoes compartilhadas: buscar e parsear paginas de jogador do efhub.com,
alem das definicoes de posicoes/papeis e pesos de scoring usadas tanto por
select_team.py quanto por check_player.py.
"""
import functools
import json
import math
import re
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def with_retries(attempts=3, backoff=(1, 3, 8)):
    """Decorador: reexecuta a funcao ate `attempts` vezes se ela lancar
    excecao (timeout, erro de rede, HTTP 5xx etc.), esperando `backoff[i]`
    segundos entre tentativas. Na ultima tentativa, deixa a excecao subir
    normalmente pra quem chamou decidir o que fazer."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if i < attempts - 1:
                        time.sleep(backoff[min(i, len(backoff) - 1)])
            raise last_exc
        return wrapper
    return decorator

STAT_KEYS = [
    "offensiveAwareness", "ballControl", "dribbling", "tightPossession",
    "lowPass", "loftedPass", "finishing", "heading", "setPieceTaking",
    "curl", "speed", "acceleration", "kickingPower", "jump",
    "physicalContact", "balance", "stamina", "defensiveAwareness",
    "ballWinning", "trackingBack", "aggression",
    "gkAwareness", "gkCatching", "gkClearing", "gkReflexes", "gkReach",
]


@with_retries()
def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


@with_retries()
def fetch_player_tier(player_id: str) -> dict:
    """Busca a Community Tier Ranking real do jogador via a API publica que
    o proprio efhub usa (achada nos bundles JS do site):
    /api/player-tier?playerId=<id> -- retorna consensusTier (S+/S/A/B/C/D/E),
    a distribuicao de votos e o tier por posicao especifica."""
    url = f"https://efhub.com/api/player-tier?playerId={player_id}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ID numerico (usado no Firestore do efhub) -> nome da habilidade adicional
# em PT-BR. Achado cruzando o mapa id->chave dos bundles JS do site com o
# dicionario de traducao pt-BR (efhub.com/pt-BR/...).
SKILL_ID_TO_PT = {
    1: "Pedalada simples", 2: "Toque duplo", 3: "Elástico", 4: "360 graus",
    5: "Chapéu", 6: "Corte com virada", 7: "Puxada de letra", 8: "Finta de letra",
    9: "Controle com a sola", 10: "Cabeceio", 11: "Efeito de longe",
    12: "Controle da cavadinha", 13: "Precisão à distância",
    14: "Chute com o peito do pé", 15: "Folha seca", 16: "Chutes com decolagem",
    17: "Finaliz. acrobática", 18: "Heel Trick", 19: "Chute de primeira",
    20: "Passe de primeira", 21: "Passe em profundidade", 22: "Passe na medida",
    23: "Cruzamento preciso", 24: "Curva para fora", 25: "De letra",
    26: "Passe sem olhar", 27: "Passe aéreo baixo", 28: "Repos. baixa do GO",
    29: "Reposição alta do GO", 30: "Arrem. lateral longo",
    31: "Arrem. longo do GO", 32: "Especialista em pênalti",
    33: "Pegador de pênaltis", 34: "Malícia", 35: "Marcação ind.",
    36: "Volta para marcar", 37: "Interceptação", 38: "Afastamento acrobático",
    39: "Liderança", 40: "Super substituto", 41: "Espírito guerreiro",
    42: "Bloqueador", 43: "Superioridade Aérea", 44: "Carrinho",
}

FIRESTORE_PROJECT_ID = "efootballhub-501e4"


@with_retries()
def fetch_community_skill_picks(player_id: str, top_n: int = 5) -> dict:
    """Busca as habilidades adicionais mais escolhidas pela comunidade pra
    essa carta ('Community Picks' no modal de Habilidades Adicionais do
    efhub). Nao existe API REST publica pra isso -- o site le direto do
    Firestore usando o SDK do cliente (achado nos bundles JS: colecao
    'player_builds', doc = id do jogador). O Firestore tem uma REST API
    publica que espelha o SDK, e as regras de seguranca permitem leitura
    sem login (o mesmo dado que aparece sem precisar entrar no site)."""
    url = (
        f"https://firestore.googleapis.com/v1/projects/{FIRESTORE_PROJECT_ID}"
        f"/databases/(default)/documents/player_builds/{player_id}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"total_users": 0, "top_skills": []}
        raise

    fields = data.get("fields", {})
    total_users = int(fields.get("totalUserCount", {}).get("integerValue", 0))
    skill_fields = (
        fields.get("totalAdditionalSkillCounts", {})
        .get("mapValue", {})
        .get("fields", {})
    )
    counts = [
        (int(sid), int(v.get("integerValue", 0)))
        for sid, v in skill_fields.items()
    ]
    counts.sort(key=lambda x: x[1], reverse=True)
    top_skills = [
        {"name": SKILL_ID_TO_PT.get(sid, f"Skill {sid}"), "votes": votes}
        for sid, votes in counts[:top_n] if votes > 0
    ]
    return {"total_users": total_users, "top_skills": top_skills}


TRAINING_CATEGORIES = [
    "shooting", "passing", "dribbling", "dexterity", "lowerBodyStrength",
    "aerialStrength", "defending", "gk1", "gk2", "gk3",
]
TRAINING_CATEGORY_PT = {
    "shooting": "Tiro", "passing": "Passe", "dribbling": "Drible",
    "dexterity": "Destreza", "lowerBodyStrength": "Força de Perna",
    "aerialStrength": "Força Aérea", "defending": "Defesa",
    "gk1": "GO 1", "gk2": "GO 2", "gk3": "GO 3",
}


@with_retries()
def fetch_community_training(player_id: str, max_builds: int = 500) -> dict:
    """Acha a distribuicao de pontos de treino mais escolhida pela comunidade
    pra essa carta (o que o efhub chama de 'Community Picks' no seletor de
    build, aba 'Top Voted'). Tambem sem API publica -- o site le a colecao
    'builds' do Firestore (cada doc e uma build enviada por um usuario,
    com os pontos por categoria como campos), e o proprio efhub deve
    agrupar/contar builds identicas no cliente pra montar o 'Top Voted'
    (confirmado: pra uma carta com uma build usada por 16 pessoas segundo o
    site, a contagem aqui bateu 16 tambem). Filtra so cartas de nivel 1
    (baseStats) -- carta ja no teto (levelCap=1) nao tem pra onde treinar."""
    url = "https://firestore.googleapis.com/v1/projects/efootballhub-501e4/databases/(default)/documents:runQuery"
    body = {
        "structuredQuery": {
            "from": [{"collectionId": "builds"}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": "playerID"},
                    "op": "EQUAL",
                    "value": {"integerValue": int(player_id)},
                }
            },
            "limit": max_builds,
        }
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = json.loads(resp.read().decode())

    def get_int(fields, key, default=0):
        f = fields.get(key)
        return int(f.get("integerValue", default)) if f else default

    groups = {}
    for row in rows:
        doc = row.get("document")
        if not doc:
            continue
        fields = doc.get("fields", {})
        key = tuple(get_int(fields, c) for c in TRAINING_CATEGORIES) + (get_int(fields, "position"),)
        g = groups.setdefault(key, {"count": 0, "overall": get_int(fields, "overall")})
        g["count"] += 1

    if not groups:
        return {"total_builds": 0, "top_build": None}

    best_key, best = max(groups.items(), key=lambda kv: kv[1]["count"])
    points = {cat: best_key[i] for i, cat in enumerate(TRAINING_CATEGORIES) if best_key[i] > 0}
    return {
        "total_builds": len(rows),
        "top_build": {
            "points": points,
            "overall": best["overall"],
            "votes": best["count"],
        },
    }


def _unescape(fragment: str) -> str:
    return fragment.replace('\\"', '"').replace("\\\\", "\\")


def _extract_balanced(text: str, start_idx: int, open_ch: str, close_ch: str) -> str:
    """A partir de text[start_idx] == open_ch, retorna a substring balanceada
    (incluindo os delimitadores), ignorando chaves/colchetes dentro de strings."""
    assert text[start_idx] == open_ch
    depth = 0
    in_string = False
    i = start_idx
    while i < len(text):
        ch = text[i]
        if ch == '"' and text[i - 1] != "\\":
            in_string = not in_string
        elif not in_string:
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start_idx:i + 1]
        i += 1
    raise ValueError("Nao encontrou fechamento balanceado")


def parse_player_html(html: str, url: str) -> dict:
    marker = '\\"baseStats\\":{'
    idx = html.find(marker)
    if idx == -1:
        marker = '"baseStats":{'
        idx = html.find(marker)
        escaped = False
    else:
        escaped = True

    if idx == -1:
        raise ValueError(f"baseStats nao encontrado em {url}")

    brace_start = idx + len(marker) - 1  # posicao do '{'
    raw_block = _extract_balanced(html, brace_start, "{", "}")
    if escaped:
        raw_block = _unescape(raw_block)
    base_stats = json.loads(raw_block)
    # o efhub renomeou "Tracking Back" para "Defensive Engagement" -- mantem a
    # chave antiga, que e a usada nos pesos e nos radares
    if "trackingBack" not in base_stats and "defensiveEngagement" in base_stats:
        base_stats["trackingBack"] = base_stats["defensiveEngagement"]

    tail = html[idx + len(marker):idx + len(marker) + 4000]
    if escaped:
        tail_plain = _unescape(tail)
    else:
        tail_plain = tail

    def find_str(key, text):
        m = re.search(rf'"{key}":"([^"]*)"', text)
        return m.group(1) if m else None

    def find_num(key, text):
        m = re.search(rf'"{key}":(\d+)', text)
        return int(m.group(1)) if m else None

    position = find_str("position", tail_plain)
    height = find_num("height", tail_plain)
    weak_foot_accuracy = find_num("weakFootAccuracy", tail_plain)
    playing_style = find_str("playingStyle", tail_plain)
    playing_style_defensive = find_str("playingStyleDefensive", tail_plain)
    if playing_style_defensive == "$undefined":
        playing_style_defensive = None

    add_pos_marker = '"additionalPositions":['
    add_idx = tail_plain.find(add_pos_marker)
    additional_positions = []
    if add_idx != -1:
        bracket_start = add_idx + len(add_pos_marker) - 1
        try:
            arr_block = _extract_balanced(tail_plain, bracket_start, "[", "]")
            additional_positions = json.loads(arr_block)
        except (ValueError, json.JSONDecodeError):
            additional_positions = []

    # nome e overall vem mais adiante, no objeto "player":{...}
    player_marker = '\\"player\\":{' if escaped else '"player":{'
    player_idx = html.find(player_marker, idx)
    name = None
    overall = None
    team = None
    if player_idx != -1:
        p_start = player_idx + len(player_marker) - 1
        try:
            player_block_raw = _extract_balanced(html, p_start, "{", "}")
            if escaped:
                player_block_raw = _unescape(player_block_raw)
            name = find_str("name", player_block_raw)
            overall_m = re.search(r'"overallRating":(\d+)', player_block_raw)
            overall = int(overall_m.group(1)) if overall_m else None
            team = find_str("team", player_block_raw)
            level_cap_m = re.search(r'"levelCap":(\d+)', player_block_raw)
            level_cap = int(level_cap_m.group(1)) if level_cap_m else 1
            com_skills = []
            com_marker = '"comSkills":['
            com_idx = player_block_raw.find(com_marker)
            if com_idx != -1:
                try:
                    com_block = _extract_balanced(player_block_raw, com_idx + len(com_marker) - 1, "[", "]")
                    com_skills = json.loads(com_block)
                except (ValueError, json.JSONDecodeError):
                    com_skills = []
        except ValueError:
            level_cap = 1
            com_skills = []
    else:
        level_cap = 1
        com_skills = []

    return {
        "url": url,
        "name": name,
        "team": team,
        "position": position,
        "additionalPositions": additional_positions,
        "height": height,
        "weakFootAccuracy": weak_foot_accuracy,
        "playingStyle": playing_style,
        "playingStyleDefensive": playing_style_defensive,
        "levelCap": level_cap,
        "overall": overall,
        "comSkills": com_skills,
        "stats": base_stats,
    }


def fetch_player(url: str, label: str = None) -> dict:
    html = fetch_html(url)
    data = parse_player_html(html, url)
    player_id = url.rstrip("/").split("/")[-1]
    try:
        data["tier"] = fetch_player_tier(player_id)
    except Exception:
        data["tier"] = None
    try:
        data["community_skills"] = fetch_community_skill_picks(player_id)
    except Exception:
        data["community_skills"] = None
    if (data.get("levelCap") or 1) > 1:
        try:
            data["community_training"] = fetch_community_training(player_id)
        except Exception:
            data["community_training"] = None
    else:
        data["community_training"] = None
    data["fetched_at"] = time.time()
    data["label"] = label
    return data


EFHUB_PLAYER_URL = re.compile(r"https?://(www\.)?efhub\.com/([a-z]{2}(-[A-Za-z]{2})?/)?players/\d+")


def load_players_txt(path: str, invalid=None):
    """Le players.txt -> [(label, url)]. Linhas que nao seguem "Nome [Tier]: https://efhub.com/players/<id>"
    vao para `invalid` como (numero_da_linha, texto) -- antes sumiam em silencio."""
    entries = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line or not EFHUB_PLAYER_URL.search(line):
                if invalid is not None:
                    invalid.append((n, line))
                continue
            label, url = line.split(":", 1)
            # o formato usa "Nome [Card]: http..." -- so a partir do primeiro
            # "http" e que comeca a URL de fato
            http_idx = line.find("http")
            if http_idx == -1:
                continue
            label = line[:http_idx].rstrip(": ").strip()
            url = line[http_idx:].strip()
            entries.append((label, url))
    return entries


# ---------------------------------------------------------------------------
# Papeis do 4-2-2-2 (estilo Contra-Ataque). Cada FUNCAO TATICA (nao so cada
# posicao generica) tem seu proprio perfil de pesos -- lateral defensivo e
# lateral ofensivo sao papeis diferentes desde a selecao (nao so um rotulo
# pos-hoc), idem 1o volante (ancora) vs volante box-to-box.
# ---------------------------------------------------------------------------

POSITION_GROUPS = {
    "GK": {"GK"},
    "CB": {"CB"},
    "FB": {"LB", "RB"},
    "DMF": {"DMF"},
    "AMF": {"AMF"},
    "CF": {"CF"},
    # meias-laterais (raw position LMF/RMF) -- usados so pela formacao 2
    # (4-2-3-1), ver FORMATIONS abaixo. Ninguem no 4-2-2-2 usa esse grupo.
    "MLE": {"LMF"},
    "MLD": {"RMF"},
}

# cada SLOT titular mapeia pro POSITION_GROUP que define elegibilidade (raw
# position). SLOT_COUNT aqui e o do 4-2-2-2 (formacao 1) -- a formacao 2
# (4-2-3-1) usa FORMATIONS["4-2-3-1"]["slot_count"], que reaproveita os
# mesmos slots de defesa/meio (GK/CB/FB_DEF/FB_OFF/DMF_ANCHOR/DMF_BOX) e so
# troca a frente (AMF/CF viram MLE/AMF/MLD/CF em quantidades diferentes).
SLOT_GROUP = {
    "GK": "GK", "CB": "CB",
    "FB_DEF": "FB", "FB_OFF": "FB",
    "DMF_ANCHOR": "DMF", "DMF_BOX": "DMF",
    "AMF": "AMF", "CF": "CF",
    "MLE": "MLE", "MLD": "MLD",
}
SLOT_COUNT = {
    "GK": 1, "CB": 2, "FB_DEF": 1, "FB_OFF": 1,
    "DMF_ANCHOR": 1, "DMF_BOX": 1, "AMF": 2, "CF": 2,
}

# formacoes disponiveis: cada uma define quantas vagas cada slot tem
# (reaproveitando os MESMOS slots/pesos/playstyle_fit do dict global --
# so a CONTAGEM e os slots novos MLE/MLD mudam entre formacoes) e como
# rotular cada slot no resultado final (grupo de exibicao + rotulo PT-BR).
FORMATIONS = {
    "4-2-2-2": {
        "label": "4-2-2-2",
        "slot_count": {
            "GK": 1, "CB": 2, "FB_DEF": 1, "FB_OFF": 1,
            "DMF_ANCHOR": 1, "DMF_BOX": 1, "AMF": 2, "CF": 2,
        },
        "same_attack_defense": False,
    },
    "4-2-3-1": {
        "label": "4-2-3-1",
        "slot_count": {
            "GK": 1, "CB": 2, "FB_DEF": 1, "FB_OFF": 1,
            "DMF_ANCHOR": 1, "DMF_BOX": 1,
            "MLE": 1, "AMF": 1, "MLD": 1, "CF": 1,
        },
        "same_attack_defense": True,
    },
}

ROLE_WEIGHTS = {
    "GK": {
        "gkReflexes": 0.30, "gkCatching": 0.20, "gkClearing": 0.15,
        "gkReach": 0.15, "gkAwareness": 0.20,
    },
    # zagueiro: recomposicao rapida (o time joga recuado e sai em contra-ataque,
    # entao velocidade/salto/defesa aerea pesam mais que construcao curta)
    "CB": {
        "defensiveAwareness": 0.22, "ballWinning": 0.16, "heading": 0.10,
        "jump": 0.06, "physicalContact": 0.10, "speed": 0.14,
        "acceleration": 0.06, "loftedPass": 0.10, "aggression": 0.06,
    },
    # lateral DEFENSIVO: perfil de zagueiro-lateral -- prioriza marcacao e
    # cobertura, dribble/passe de ataque quase nao entram
    "FB_DEF": {
        "defensiveAwareness": 0.26, "ballWinning": 0.18, "trackingBack": 0.16,
        "physicalContact": 0.08, "aggression": 0.06, "speed": 0.12,
        "stamina": 0.08, "lowPass": 0.04, "dribbling": 0.02,
    },
    # lateral OFENSIVO: sobe a linha, cruza, dribla -- perfil de ala
    "FB_OFF": {
        "offensiveAwareness": 0.12, "dribbling": 0.14, "speed": 0.18,
        "acceleration": 0.12, "stamina": 0.08, "lowPass": 0.12,
        "loftedPass": 0.10, "tightPossession": 0.06, "curl": 0.08,
    },
    # 1o volante (ancora): so segura -- blindagem da defesa e saida curta
    "DMF_ANCHOR": {
        "defensiveAwareness": 0.28, "ballWinning": 0.20, "trackingBack": 0.14,
        "physicalContact": 0.10, "aggression": 0.08, "lowPass": 0.10,
        "loftedPass": 0.06, "stamina": 0.04,
    },
    # volante box-to-box: cobre os dois lados da bola, mais movel
    "DMF_BOX": {
        "stamina": 0.14, "speed": 0.10, "acceleration": 0.08,
        "dribbling": 0.10, "ballControl": 0.08, "lowPass": 0.10,
        "offensiveAwareness": 0.10, "defensiveAwareness": 0.12,
        "ballWinning": 0.10, "physicalContact": 0.08,
    },
    # meia-atacante (MAT): combinacao rapida + passe em profundidade pro
    # contra-ataque
    "AMF": {
        "offensiveAwareness": 0.16, "dribbling": 0.16, "ballControl": 0.12,
        "lowPass": 0.12, "loftedPass": 0.08, "speed": 0.14,
        "acceleration": 0.10, "finishing": 0.12,
    },
    # centroavante (CA): definicao + velocidade pra correr pro gol no
    # contra-ataque
    "CF": {
        "finishing": 0.24, "speed": 0.16, "acceleration": 0.14,
        "dribbling": 0.12, "offensiveAwareness": 0.12,
        "physicalContact": 0.12, "heading": 0.10,
    },
    # meia-lateral (MLE/MLD, formacao 4-2-3-1): ala que da largura pro time,
    # mistura de lateral ofensivo (drible/cruzamento/velocidade) com
    # armador (passe/visao), com alguma responsabilidade defensiva pra
    # ajudar o dobro de volante quando perde a bola.
    "MLE": {
        "offensiveAwareness": 0.10, "dribbling": 0.16, "speed": 0.16,
        "acceleration": 0.12, "stamina": 0.08, "lowPass": 0.10,
        "curl": 0.08, "tightPossession": 0.08, "defensiveAwareness": 0.06,
        "trackingBack": 0.06,
    },
    "MLD": {
        "offensiveAwareness": 0.10, "dribbling": 0.16, "speed": 0.16,
        "acceleration": 0.12, "stamina": 0.08, "lowPass": 0.10,
        "curl": 0.08, "tightPossession": 0.08, "defensiveAwareness": 0.06,
        "trackingBack": 0.06,
    },
}

# ---------------------------------------------------------------------------
# playstyle_fit: filtro BINARIO de encaixe tatico por SLOT. Combina o
# playingStyle principal da carta (catalogo completo, ver PLAYSTYLE_PT) com
# os comSkills (tracos especiais fixos da carta -- achado nos 42 jogadores
# do usuario: so 5 valores existem: trickster, mazingRun, longBallExpert,
# earlyCross, incisiveRun). Ter pelo menos 1 traco-chave daquele slot vale
# MAIS que uma pequena diferenca de atributos brutos (ver PLAYSTYLE_FIT_*).
# ---------------------------------------------------------------------------
KEY_PLAYSTYLES_BY_SLOT = {
    "GK": set(),
    "CB": set(),
    "FB_DEF": {"Defensive Full-back"},
    "FB_OFF": {"Full-back Finisher", "Offensive Wingback"},
    "DMF_ANCHOR": {"Anchor Man"},
    "DMF_BOX": {"Box To Box"},
    "AMF": {"Hole Player", "Creative Playmaker", "Classic No. 10", "Orchestrator"},
    "CF": {"Goal Poacher", "Fox In The Box", "Target Man"},
    "MLE": {"Roaming Flank", "Prolific Winger", "Cross Specialist"},
    "MLD": {"Roaming Flank", "Prolific Winger", "Cross Specialist"},
}
KEY_COMSKILLS_BY_SLOT = {
    "GK": set(),
    "CB": {"longBallExpert"},
    "FB_DEF": set(),
    "FB_OFF": {"earlyCross", "trickster", "mazingRun"},
    "DMF_ANCHOR": {"longBallExpert"},
    "DMF_BOX": {"incisiveRun", "mazingRun"},
    "AMF": {"incisiveRun", "mazingRun", "trickster"},
    "CF": {"incisiveRun", "mazingRun"},
    "MLE": {"earlyCross", "trickster", "mazingRun"},
    "MLD": {"earlyCross", "trickster", "mazingRun"},
}
PLAYSTYLE_FIT_MATCH = 99
PLAYSTYLE_FIT_NOMATCH = 40
PLAYSTYLE_FIT_WEIGHT = 0.19


def playstyle_fit_score(player: dict, slot: str) -> float:
    style = player.get("playingStyle")
    style_def = player.get("playingStyleDefensive")
    if style in KEY_PLAYSTYLES_BY_SLOT.get(slot, set()):
        return PLAYSTYLE_FIT_MATCH
    if style_def in KEY_PLAYSTYLES_BY_SLOT.get(slot, set()):
        return PLAYSTYLE_FIT_MATCH
    com_skills = set(player.get("comSkills") or [])
    if com_skills & KEY_COMSKILLS_BY_SLOT.get(slot, set()):
        return PLAYSTYLE_FIT_MATCH
    return PLAYSTYLE_FIT_NOMATCH

# fator aplicado ao score quando o jogador nao joga na posicao nativa
FAMILIARITY_FACTOR = {
    "native": 1.0,
    2: 0.93,
    1: 0.83,
}


def player_positions(player: dict):
    """Retorna [(posicao, familiaridade_ou_'native'), ...] para um jogador."""
    result = [(player["position"], "native")]
    for extra in player.get("additionalPositions") or []:
        result.append((extra["position"], extra.get("familiarity", 1)))
    return result


def eligible_groups(player: dict):
    """Quais POSITION_GROUPS esse jogador pode preencher, com o melhor fator
    de familiaridade encontrado em cada grupo."""
    out = {}
    for pos, fam in player_positions(player):
        for group, posset in POSITION_GROUPS.items():
            if pos in posset:
                factor = FAMILIARITY_FACTOR[fam]
                if group not in out or factor > out[group]:
                    out[group] = factor
    return out


def eligible_slots(player: dict):
    """Quais SLOTS taticos (GK/CB/FB_DEF/FB_OFF/DMF_ANCHOR/DMF_BOX/AMF/CF)
    esse jogador pode preencher, com o fator de familiaridade da posicao
    crua correspondente (a familiaridade e por posicao do jogo, nao por
    funcao tatica -- um lateral e um lateral pro efhub, defensivo ou
    ofensivo)."""
    groups = eligible_groups(player)
    out = {}
    for slot, group in SLOT_GROUP.items():
        if group in groups:
            out[slot] = groups[group]
    return out


# Pesos EXATOS da formula de role_score (somam 1.00):
#   role_score = 0.32*atributos + 0.32*meta + 0.19*playstyle_fit
#              + 0.10*votos + 0.07*overmax(desempate)
# "meta" = Community Tier Ranking real (via /api/player-tier) -- ainda pesa
# muito, mas nao mais domina sozinha: agora divide espaco com o encaixe
# tatico real (atributos ponderados por FUNCAO especifica + playstyle_fit).
ATTR_WEIGHT = 0.32
META_WEIGHT = 0.32
VOTES_TIEBREAK_WEIGHT = 0.10
OVERMAX_TIEBREAK_WEIGHT = 0.07

# Converte o tier letra (S+/S/A/B/C/D/E, como votado pela comunidade no
# efhub) pra um numero na mesma escala 0-99 dos atributos. Mantido como valor
# "de referencia" (topo da faixa -- ver TIER_BANDS) pra qualquer lugar que so
# precise de UM numero por tier.
TIER_VALUE = {
    "S+": 99, "S": 92, "A": 84, "B": 74, "C": 64, "D": 54, "E": 44,
}

# Cada tier tem uma FAIXA propria de valores, e nunca se sobrepoe a de outro
# tier -- S+ sempre > S sempre > A sempre > ... A % de votos no tier e a
# quantidade de votos (confianca) so decidem a posicao DENTRO da faixa do
# tier mais votado, nunca empurram pra faixa vizinha.
TIER_BANDS = {
    "S+": (95, 99), "S": (85, 94), "A": (75, 84), "B": (65, 74),
    "C": (55, 64), "D": (45, 54), "E": (35, 44),
}

# a API de tier usa as posicoes "cruas" do jogo (LB/RB, CB, DMF, AMF, CF...);
# mapeia cada um dos nossos GRUPOS (nao slots -- lateral defensivo e
# ofensivo votam nas mesmas posicoes cruas LB/RB) pras posicoes cruas que
# valem como voto especifico daquele papel.
ROLE_TO_RAW_POSITIONS = {
    "GK": ["GK"], "CB": ["CB"], "FB": ["LB", "RB"], "DMF": ["DMF"],
    "AMF": ["AMF"], "CF": ["CF"], "MLE": ["LMF"], "MLD": ["RMF"],
}

# quantos votos um tier precisa acumular pra sermos 100% confiantes nele.
# Abaixo disso, a nota "encolhe" (shrinkage) em direcao ao fallback baseado
# no Overall -- um card com 2 votos em S+ nao deve valer o mesmo que um com
# 1600 votos maioria em S+, mesmo os dois "sendo S+".
CONFIDENCE_VOTE_THRESHOLD = 50


# A carta so mostra os atributos do NIVEL 1 (destreinado). "levelCap" (real,
# vem do card) diz ate que nivel da pra treinar -- levelCap=1 significa "ja
# no teto". Nao existe endpoint publico com os atributos ja treinados no
# nivel maximo (a calculadora de treino do efhub roda so no navegador), entao
# aqui aplicamos uma ESTIMATIVA simples e transparente de ganho por nivel de
# treino, so pra nao penalizar cartas treinaveis por mostrarem o valor
# destreinado. Isso e uma projecao, nao um dado real do efhub -- e so entra
# nos ATRIBUTOS (attr_score). A nota de tier (meta) NAO recebe esse bonus de
# novo: o tier ja e um voto real da comunidade sobre a carta, e quem vota
# tipicamente already leva o potencial de treino em conta -- somar o bonus
# ali seria contar o mesmo ganho duas vezes. O bonus so entra na "meta" como
# ultimo fallback, quando a carta nem tem tier votado ainda (usamos so o
# Overall base, que tambem e destreinado).
TRAINING_RATE_PER_LEVEL = 0.35
TRAINING_MAX_BONUS = 14


def training_bonus(player: dict) -> float:
    level_cap = player.get("levelCap") or 1
    if level_cap <= 1:
        return 0.0
    return round(min(TRAINING_MAX_BONUS, TRAINING_RATE_PER_LEVEL * (level_cap - 1)), 1)


TIER_ORDER = ["S+", "S", "A", "B", "C", "D", "E"]

# traducao livre dos playing styles do efhub pra termos comuns do futebol em
# PT-BR (o "Anchor Man" do Paredes = "Primeiro Volante", o "Classic No. 10"
# do Neymar = "Camisa 10", etc.)
# traducao OFICIAL do efhub (nao uma traducao livre nossa) -- extraida do
# dicionario i18n embutido na propria pagina em pt-BR (ex.:
# https://efhub.com/pt-BR/players/<id>, procurando a chave camelCase do
# estilo no payload __next_f, tipo "destroyer":"O destruidor"). Sempre que
# um estilo aparecer errado/faltando, a fonte de verdade e essa pagina em
# pt-BR, nao um chute nosso -- "Attack Outlet"/"Front Line Pressure"/
# "High Line Master" ficam de fora de proposito porque o proprio efhub NAO
# traduz esses 3 (mostra em ingles mesmo), entao o fallback pro valor cru
# (ver playstyle_pt) ja reproduz o que a pagina real mostra.
PLAYSTYLE_PT = {
    "Anchor Man": "Primeiro volante",
    "Box To Box": "Meia versátil",
    "Build Up": "Provocador",
    "Classic No. 10": "Clássica nº 10",
    "Creative Playmaker": "Armador criativo",
    "Cross Specialist": "Especialista em cruz.",
    "Defensive Full-back": "Zagueiro defensivo",
    "Defensive Goalkeeper": "Goleiro defensivo",
    "Fox In The Box": "Homem de área",
    "Full-back Finisher": "Lateral atacante",
    "Goal Poacher": "Artilheiro",
    "Hole Player": "Jog. de infiltração",
    "Offensive Goalkeeper": "Goleiro ofensivo",
    "Offensive Wingback": "Zagueiro ofensivo",
    "Orchestrator": "Orquestrador",
    "Prolific Winger": "Ala produtivo",
    "Roaming Flank": "Lateral móvel",
    "Target Man": "Pivô",
    "Destroyer": "O destruidor",
}


def playstyle_pt(style):
    if not style or style == "$undefined":
        return None
    return PLAYSTYLE_PT.get(style, style)


# traducao oficial dos comSkills (mesma fonte -- dicionario i18n pt-BR do
# efhub). Os 5 valores encontrados no elenco do usuario ficam em ingles
# mesmo na pagina em pt-BR do efhub (nao e chute nosso): so "earlyCross"
# tem um nome oficial diferente do que a formatacao camelCase ingenua
# produziria ("Early Crosser", nao "Early Cross").
COM_SKILL_PT = {
    "mazingRun": "Mazing Run",
    "longBallExpert": "Long Ball Expert",
    "earlyCross": "Early Crosser",
    "incisiveRun": "Incisive Run",
    "trickster": "Trickster",
}


def comskill_pt(key: str) -> str:
    return COM_SKILL_PT.get(key) or humanize_skill_key(key)


def humanize_skill_key(key: str) -> str:
    """'longBallExpert' -> 'Long Ball Expert'. Os comSkills (tra&ccedil;os
    especiais fixos da carta, tipo Trickster/Incisive Run/Long Ball Expert)
    nao tem uma lista oficial catalogada aqui -- em vez de arriscar uma
    traducao errada, so formata a chave camelCase igual o efhub mostra em
    ingles."""
    if not key:
        return key
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    return words[0].upper() + words[1:]


def mode_tier(tier_counts: dict):
    """Tier com MAIS votos (moda). So usado como FALLBACK quando o card nao
    tem um consensusTier valido vindo da API (ver resolve_tier) -- o
    consensusTier calculado pelo proprio efhub e a fonte de verdade pra
    tier exibido, por pedido explicito do usuario (mesmo sabendo que
    diverge do tier mais votado em alguns casos, ex.: Suarez tem maioria
    de votos em S+ mas consensusTier "S"). Empate quebra pro tier mais
    alto. Retorna (tier, votos) ou (None, 0) se nao tem nenhum voto."""
    if not tier_counts:
        return None, 0
    best, best_count = None, -1
    for t in TIER_ORDER:
        c = tier_counts.get(t, 0)
        if c > best_count:
            best, best_count = t, c
    return (best, best_count) if best_count > 0 else (None, 0)


def resolve_tier(tier_counts: dict, consensus_tier=None):
    """Tier "oficial" pra exibir/pontuar: usa o consensusTier calculado pelo
    proprio efhub (campo real da API /api/player-tier) sempre que existir,
    com o numero de votos que sustentam ESSE tier especifico. So cai pro
    tier mais votado (mode_tier) quando nao ha consensusTier (card sem
    posicao votada, por exemplo). Retorna (tier, votos)."""
    if consensus_tier and consensus_tier in TIER_ORDER:
        return consensus_tier, (tier_counts or {}).get(consensus_tier, 0)
    return mode_tier(tier_counts)


def tier_confidence_score(tier_counts: dict, total: int, fallback: float, consensus_tier=None) -> float:
    """Nota de tier respeitando a hierarquia S+ > S > A > B > C > D > E --
    MAS so quando ha votos suficientes pra confiar no tier. Acha o tier
    "oficial" (resolve_tier -- consensusTier da API, com fallback pro mais
    votado) e calcula a posicao dentro da faixa propria desse tier
    (TIER_BANDS) usando a concentracao de votos (um S com 90% dos votos que
    sustentam ELE fica no topo da faixa, um S com 30% fica mais embaixo).
    Isso e o "band_value". Depois combina esse band_value com o fallback
    (Overall + treino) proporcional a CONFIANCA (quantidade de votos): com
    poucos votos, o resultado final encolhe em direcao ao fallback e PODE
    cair fora da faixa do tier -- um "S+" baseado em 1-2 votos nao deve
    valer 95+ so por causa da etiqueta; ele so vale isso de verdade quando
    tem volume de votos que sustente. Com votos >= CONFIDENCE_VOTE_THRESHOLD,
    confia 100% no band_value e a hierarquia fica garantida entre cards
    igualmente bem votados."""
    top_tier, top_votes = resolve_tier(tier_counts, consensus_tier)
    if top_tier is None or total <= 0:
        return fallback
    band_low, band_high = TIER_BANDS[top_tier]
    concentration = top_votes / total
    band_value = band_low + concentration * (band_high - band_low)
    confidence = min(1.0, total / CONFIDENCE_VOTE_THRESHOLD)
    return confidence * band_value + (1 - confidence) * fallback


def meta_score_for_role(player: dict, role: str) -> float:
    """Nota de 'meta' pro papel: prioriza a Community Tier Ranking votada
    especificamente naquela posicao, cai pro geral do card, e por ultimo pro
    Overall + projecao de treino (quando o card nao tem NENHUM voto ainda).
    Em ambos os casos usa media ponderada por % de votos, com a nota
    encolhendo pro fallback quando ha poucos votos (ver tier_confidence_score).
    'role' pode ser um GRUPO (GK/CB/FB/DMF/AMF/CF) ou um SLOT tatico
    (FB_DEF/FB_OFF/DMF_ANCHOR/DMF_BOX/...) -- a Community Tier Ranking vota
    por posicao crua do jogo, nao por funcao tatica, entao slots do mesmo
    grupo (ex. FB_DEF e FB_OFF) consultam o mesmo voto de LB/RB."""
    group = SLOT_GROUP.get(role, role)
    tier = player.get("tier")
    fallback = min(99, (player.get("overall") or 70) + training_bonus(player))
    if tier:
        for pos in ROLE_TO_RAW_POSITIONS.get(group, []):
            pr = (tier.get("positionRatings") or {}).get(pos)
            if pr and pr.get("totalPlacements", 0) > 0:
                return tier_confidence_score(
                    pr.get("tierCounts") or {}, pr["totalPlacements"], fallback,
                    consensus_tier=pr.get("consensusTier"),
                )
        total = tier.get("totalPlacements", 0)
        if total > 0:
            return tier_confidence_score(
                tier.get("tierCounts") or {}, total, fallback,
                consensus_tier=tier.get("consensusTier"),
            )
    return fallback


def votes_score(player: dict) -> float:
    """Escala o total de votos (0-99ish) pra usar como desempate: cartas mais
    votadas no ranking tem preferencia sobre cartas quase sem voto, mesmo com
    tier parecido -- escala log porque o numero de votos varia muito (de 0 a
    milhares)."""
    total = (player.get("tier") or {}).get("totalPlacements", 0)
    return min(99, 20 * math.log10(total + 1))


def projected_stats(player: dict) -> dict:
    """Atributos com a estimativa de treino somada (clampada em 99). Stats de
    goleiro so recebem o bonus se o jogador for GK -- nao faz sentido inflar
    'gkReflexes' de um centroavante."""
    bonus = training_bonus(player)
    if bonus == 0:
        return player["stats"]
    is_gk = player["position"] == "GK"
    out = {}
    for k, v in player["stats"].items():
        if k.startswith("gk") and not is_gk:
            out[k] = v
        else:
            out[k] = min(99, round(v + bonus, 1))
    return out


def overmax_value(player: dict) -> float:
    """Overall + projecao de treino, clampado em 99. Usado so como
    desempate -- nao e o valor 'smart' exato que o efhub calcula (esse roda
    inteiro no navegador, sem API publica; ver nota em training_bonus)."""
    return min(99, (player.get("overall") or 70) + training_bonus(player))


def role_score(player: dict, role: str) -> float:
    """role_score = 0.32*atributos(pesos taticos do SLOT) + 0.32*meta
    (Community Tier Ranking) + 0.19*playstyle_fit (traco-chave do slot,
    filtro binario) + 0.10*votos + 0.07*overmax(desempate). 'role' deve ser
    um SLOT tatico (GK/CB/FB_DEF/FB_OFF/DMF_ANCHOR/DMF_BOX/AMF/CF) -- cada
    um tem seu proprio perfil de pesos de atributo e seu proprio conjunto de
    tracos-chave, decidido JA na pontuacao (nao mais rotulado depois)."""
    weights = ROLE_WEIGHTS[role]
    stats = projected_stats(player)
    attr_score = sum(weights[k] * stats.get(k, 0) for k in weights)
    meta = meta_score_for_role(player, role)
    fit = playstyle_fit_score(player, role)
    return (
        ATTR_WEIGHT * attr_score
        + META_WEIGHT * meta
        + PLAYSTYLE_FIT_WEIGHT * fit
        + VOTES_TIEBREAK_WEIGHT * votes_score(player)
        + OVERMAX_TIEBREAK_WEIGHT * overmax_value(player)
    )


if __name__ == "__main__":
    import sys
    html = open(sys.argv[1], encoding="utf-8").read()
    data = parse_player_html(html, "test")
    print(json.dumps(data, indent=2, ensure_ascii=False))
