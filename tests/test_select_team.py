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
