"""Testes do fluxo "Limpar Cache" e do fetch resumível (sem rede: tudo simulado)."""
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fetch_players  # noqa: E402
import serve_dashboard  # noqa: E402


# --- fetch_players --------------------------------------------------------

@pytest.fixture
def projeto(tmp_path, monkeypatch):
    (tmp_path / "players.txt").write_text(
        "Mbappe [S]: https://efhub.com/players/1\nNeymar [A]: https://efhub.com/players/2\n", encoding="utf-8")
    out = tmp_path / "data" / "players.json"
    out.parent.mkdir()
    antigo = {"players": [
        {"label": "Mbappe [S]", "url": "https://efhub.com/players/1", "fetched_at": 1, "ovr": 99},
        {"label": "Neymar [A]", "url": "https://efhub.com/players/2", "fetched_at": 1, "ovr": 95},
    ], "errors": []}
    out.write_text(json.dumps(antigo), encoding="utf-8")
    monkeypatch.setattr(fetch_players, "PLAYERS_TXT", str(tmp_path / "players.txt"))
    monkeypatch.setattr(fetch_players, "OUT_PATH", str(out))
    monkeypatch.setattr(fetch_players.time, "sleep", lambda s: None)
    return out


def _efhub_falha_para(url_que_falha):
    def fake(url, label=None):
        if url == url_que_falha:
            raise urllib.error.URLError("efhub fora do ar")
        return {"label": label, "url": url, "fetched_at": 2, "ovr": 90}
    return fake


def test_force_mantem_dado_antigo_quando_a_busca_falha(projeto, monkeypatch):
    monkeypatch.setattr(fetch_players, "fetch_player", _efhub_falha_para("https://efhub.com/players/2"))
    monkeypatch.setattr(sys, "argv", ["fetch_players.py", "--force"])

    fetch_players.main()

    salvo = json.loads(projeto.read_text(encoding="utf-8"))
    por_url = {p["url"]: p for p in salvo["players"]}
    assert set(por_url) == {"https://efhub.com/players/1", "https://efhub.com/players/2"}
    assert por_url["https://efhub.com/players/2"]["ovr"] == 95  # dado antigo preservado
    assert por_url["https://efhub.com/players/1"]["fetched_at"] == 2  # o resto foi rebuscado
    assert [e["label"] for e in salvo["errors"]] == ["Neymar [A]"]


def test_force_rebusca_mesmo_com_cache_fresco(projeto, monkeypatch):
    dados = json.loads(projeto.read_text(encoding="utf-8"))
    for p in dados["players"]:
        p["fetched_at"] = fetch_players.time.time()
    projeto.write_text(json.dumps(dados), encoding="utf-8")
    chamadas = []
    monkeypatch.setattr(fetch_players, "fetch_player", lambda url, label=None: chamadas.append(url) or {"label": label, "url": url, "fetched_at": 3})
    monkeypatch.setattr(sys, "argv", ["fetch_players.py", "--force"])

    fetch_players.main()

    assert len(chamadas) == 2


def test_gravacao_atomica_nao_deixa_arquivo_pela_metade(projeto, monkeypatch):
    monkeypatch.setattr(fetch_players, "fetch_player", _efhub_falha_para(None))
    monkeypatch.setattr(sys, "argv", ["fetch_players.py"])

    def explode(*a, **k):
        raise KeyboardInterrupt  # processo interrompido no meio da gravação

    monkeypatch.setattr(fetch_players.json, "dump", explode)
    with pytest.raises(KeyboardInterrupt):
        fetch_players.main()

    # o arquivo anterior continua íntegro e não sobra temporário
    assert json.loads(projeto.read_text(encoding="utf-8"))["players"][0]["ovr"] == 99
    assert [p.name for p in projeto.parent.iterdir()] == ["players.json"]


# --- serve_dashboard -------------------------------------------------------

def test_limpar_cache_remonta_o_dashboard(tmp_path, monkeypatch):
    rodados = []

    class Ok:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(serve_dashboard.subprocess, "run", lambda cmd, **k: rodados.append(Path(cmd[1]).name) or Ok())
    monkeypatch.setattr(serve_dashboard, "STATUS_PATH", str(tmp_path / "status.json"))

    serve_dashboard.run_refresh()

    assert rodados == ["fetch_players.py", "select_team.py", "build_dashboard.py"]
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "done"


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_dashboard, "STATUS_PATH", str(tmp_path / "status.json"))
    disparos = []
    monkeypatch.setattr(serve_dashboard, "run_refresh", lambda: disparos.append(1))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve_dashboard.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", disparos
    httpd.shutdown()


def _post(url, origin=None):
    req = urllib.request.Request(url + "/api/clear-cache", method="POST", data=b"")
    if origin:
        req.add_header("Origin", origin)
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def test_outro_site_nao_dispara_raspagem(servidor):
    base, disparos = servidor
    assert _post(base, origin="https://site-qualquer.example") == 403
    assert disparos == []


def test_o_proprio_dashboard_dispara(servidor):
    base, disparos = servidor
    assert _post(base, origin=base) == 202
    assert _post(base.replace("127.0.0.1", "localhost"), origin=base.replace("127.0.0.1", "localhost")) == 202
