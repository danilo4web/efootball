"""Escolha do time com um elenco fixo (tests/fixtures/elenco.json, cópia dos dados públicos do efhub)."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import select_team as st  # noqa: E402

ELENCO = json.loads((Path(__file__).parent / "fixtures" / "elenco.json").read_text())


def escolher(tmp_path, players):
    entrada, saida = tmp_path / "players.json", tmp_path / "best_team.json"
    entrada.write_text(json.dumps({"players": players, "errors": []}))
    st.IN_PATH, st.OUT_PATH = str(entrada), str(saida)
    st.main()
    return json.loads(saida.read_text())


def titulares(lineup):
    return [c for grupo in lineup.values() for c in grupo]


def test_time_completo_sem_repetir_jogador(tmp_path):
    time = escolher(tmp_path, copy.deepcopy(ELENCO["players"]))
    for lineup in (time["lineup"], time["formation2"]["lineup"]):
        nomes = [c["label"] for c in titulares(lineup)]
        assert len(nomes) == 11
        assert len(set(nomes)) == 11
    assert time["lineup"]["GK"][0]["native_position"] == "GK"


def test_jogador_abaixo_do_corte_nao_e_titular_quando_ha_opcao(tmp_path):
    jogadores = copy.deepcopy(ELENCO["players"])
    time = escolher(tmp_path, jogadores)
    baixos = {p["name"] for p in jogadores if st.is_low_tier(p)}
    assert baixos, "o elenco de teste precisa ter alguém abaixo do corte"
    for lineup in (time["lineup"], time["formation2"]["lineup"]):
        assert not ({c["name"] for c in titulares(lineup)} & baixos)


def test_resultado_deterministico(tmp_path):
    a = escolher(tmp_path, copy.deepcopy(ELENCO["players"]))
    b = escolher(tmp_path, copy.deepcopy(ELENCO["players"]))
    assert a == b


def _goleiros_abaixo_do_corte(jogadores):
    for p in jogadores:
        if p["position"] == "GK":
            p["tier"] = {"tierCounts": {}, "consensusTier": "E"}
    return jogadores


def test_sem_goleiro_acima_do_corte_escala_o_melhor_abaixo(tmp_path, capsys):
    """Regressão: antes quebrava com IndexError e o botão Limpar Cache falhava inteiro."""
    jogadores = _goleiros_abaixo_do_corte(copy.deepcopy(ELENCO["players"]))
    assert all(st.is_low_tier(p) for p in jogadores if p["position"] == "GK")
    time = escolher(tmp_path, jogadores)
    gk = time["lineup"]["GK"][0]["label"]
    assert time["formation2"]["lineup"]["GK"][0]["label"] == gk
    assert "GK sem ninguém acima do corte" in capsys.readouterr().err
    assert gk not in {e["label"] for e in time["excluded"]}


def test_elenco_sem_goleiro_explica_o_que_falta(tmp_path):
    jogadores = [p for p in copy.deepcopy(ELENCO["players"]) if p["position"] != "GK"]
    with pytest.raises(SystemExit) as erro:
        escolher(tmp_path, jogadores)
    assert "GK" in str(erro.value) and "players.txt" in str(erro.value)


def _cand(nome, score):
    return {"player": {"name": nome, "label": nome}, "score": score, "familiarity_factor": 1.0, "native": True}


def test_atribuicao_otima_ganha_da_gulosa_no_conjunto():
    # Caso Kounde: K é o melhor lateral (86), mas também é bom zagueiro (81);
    # M é lateral quase tão bom (83) e não joga de zagueiro; T é zagueiro fraco (73).
    candidatos = {
        "FB": [_cand("K", 86), _cand("M", 83)],
        "CB": [_cand("K", 81), _cand("T", 73)],
    }
    vagas = {"FB": 1, "CB": 1}
    gulosa, _ = st.greedy_assign_slots(candidatos, slot_count=vagas)
    otima, usados = st.optimal_assign_slots(candidatos, slot_count=vagas)
    soma = lambda t: sum(c["score"] for lst in t.values() for c in lst)
    assert soma(gulosa) == 86 + 73
    assert soma(otima) == 83 + 81
    assert [c["player"]["name"] for c in otima["CB"]] == ["K"]
    assert usados == {"K", "M"}


def test_atribuicao_otima_nao_escala_duas_cartas_do_mesmo_jogador():
    a = _cand("De Jong", 80)
    b = {**_cand("De Jong", 79), "player": {"name": "De Jong", "label": "De Jong (Holanda)"}}
    candidatos = {"DMF": [a, b, _cand("Rice", 70)]}
    otima, _ = st.optimal_assign_slots(candidatos, slot_count={"DMF": 2})
    assert sorted(c["player"]["label"] for c in otima["DMF"]) == ["De Jong", "Rice"]
