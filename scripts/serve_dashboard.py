"""Sobe um servidor HTTP local pra abrir o dashboard em localhost, com um
endpoint extra pro botao "Limpar Cache" do dashboard (re-busca tudo no efhub
ignorando o cache de 6h e remonta o time).

Uso:
    python3 scripts/serve_dashboard.py [porta]

Depois abra http://localhost:<porta>/dashboard.html no navegador.
"""
import http.server
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(ROOT, "dashboard")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
STATUS_PATH = os.path.join(ROOT, "data", "refresh_status.json")
PLAYERS_JSON = os.path.join(ROOT, "data", "players.json")

DEFAULT_PORT = 8765

refresh_lock = threading.Lock()


def write_status(**fields):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(fields, f)


def read_status():
    if not os.path.exists(STATUS_PATH):
        return {"state": "idle"}
    try:
        return json.load(open(STATUS_PATH, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"state": "idle"}


def resumo_de_falhas():
    """Falhas da busca (jogador mantido com o dado anterior, ou linha inválida no players.txt) entram
    na mensagem final: antes o botão dizia só "Cache limpo" mesmo com metade do elenco falhando."""
    try:
        with open(PLAYERS_JSON, encoding="utf-8") as f:
            erros = json.load(f).get("errors") or []
    except (OSError, ValueError):
        return ""
    if not erros:
        return ""
    nomes = ", ".join(e.get("label", "?") for e in erros[:5]) + ("…" if len(erros) > 5 else "")
    return f" Atenção: {len(erros)} falha(s) na busca ({nomes}); os jogadores já conhecidos mantiveram o dado anterior."


def run_refresh():
    if not refresh_lock.acquire(blocking=False):
        return  # ja tem uma atualizacao rodando
    try:
        write_status(state="running", started_at=time.time(), step="buscando jogadores")
        fetch = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "fetch_players.py"), "--force"],
            capture_output=True, text=True, cwd=ROOT,
        )
        if fetch.returncode != 0:
            write_status(state="error", finished_at=time.time(),
                         message="fetch_players.py falhou: " + fetch.stderr[-500:])
            return

        write_status(state="running", started_at=time.time(), step="montando o time")
        select = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "select_team.py")],
            capture_output=True, text=True, cwd=ROOT,
        )
        if select.returncode != 0:
            write_status(state="error", finished_at=time.time(),
                         message="select_team.py falhou: " + select.stderr[-500:])
            return

        # O dashboard.html embute o time no build: sem esta etapa, recarregar a
        # página mostrava o time antigo.
        write_status(state="running", started_at=time.time(), step="gerando o dashboard")
        build = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "build_dashboard.py")],
            capture_output=True, text=True, cwd=ROOT,
        )
        if build.returncode != 0:
            write_status(state="error", finished_at=time.time(),
                         message="build_dashboard.py falhou: " + build.stderr[-500:])
            return

        write_status(state="done", finished_at=time.time(),
                     message="Cache limpo, time remontado e dashboard gerado. Recarregue a página pra ver os dados novos."
                     + resumo_de_falhas())
    finally:
        refresh_lock.release()


class Handler(http.server.SimpleHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/cache-status":
            return self._json(read_status())
        return super().do_GET()

    def _same_origin(self):
        """O endpoint dispara uma raspagem completa do efhub: só o próprio dashboard
        pode chamá-lo. Navegadores mandam Origin em POST de outro site (CSRF);
        sem Origin (curl, chamada local) é aceito."""
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}", f"https://{host}")

    def do_POST(self):
        if self.path == "/api/clear-cache":
            if not self._same_origin():
                return self._json({"state": "forbidden", "message": "origem não permitida"}, 403)
            if refresh_lock.locked():
                return self._json({"state": "running", "message": "já tem uma atualização rodando"}, 202)
            threading.Thread(target=run_refresh, daemon=True).start()
            return self._json({"state": "started"}, 202)
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        pass  # silencia o log padrao (fica so os prints do main())


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    os.chdir(DASHBOARD_DIR)
    write_status(state="idle")
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"Dashboard disponível em: http://localhost:{port}/dashboard.html")
        print("Ctrl+C pra parar.")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
