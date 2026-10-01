#!/usr/bin/env bash
# Smoke test local do Onze Ideal: PASS/WARN/FAIL. Só leitura, sem rede externa.
#   scripts/smoke-test.sh
set -uo pipefail
cd "$(dirname "$0")/.."
URL="${DASHBOARD_URL:-http://localhost:8765}"
P=0; W=0; F=0
pass() { echo "[PASS] $*"; P=$((P+1)); }
warn() { echo "[WARN] $*"; W=$((W+1)); }
fail() { echo "[FAIL] $*"; F=$((F+1)); }

systemctl --user is-active --quiet efootball-dashboard.service && pass "serviço efootball-dashboard ativo" \
  || warn "serviço parado (systemctl --user start efootball-dashboard.service, ou python3 scripts/serve_dashboard.py)"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL/dashboard.html") || code=000
[ "$code" = 200 ] && pass "dashboard responde ($URL/dashboard.html → 200)" || fail "dashboard não responde ($code)"
st=$(curl -s --max-time 5 "$URL/api/cache-status" | python3 -c "import json,sys;print(json.load(sys.stdin)['state'])" 2>/dev/null) \
  && pass "API de status responde (estado: $st)" || fail "API /api/cache-status não responde"
[ "${st:-}" = error ] && warn "última atualização terminou em erro: veja data/refresh_status.json"

PYOUT=$(python3 - <<'PY'
import json, sys, time
sys.path.insert(0, "scripts")
from common import load_players_txt
inv = []
ok = load_players_txt("players.txt", inv)
print(("[PASS]" if not inv else "[WARN]") + f" players.txt: {len(ok)} jogadores" + (f", {len(inv)} linha(s) fora do formato: {inv[:3]}" if inv else ""))
d = json.load(open("data/players.json"))
idade = (time.time() - max(p.get("fetched_at", 0) for p in d["players"])) / 3600
print(("[PASS]" if idade < 24 * 7 else "[WARN]") + f" data/players.json: {len(d['players'])} jogadores, busca mais recente há {idade:.0f} h")
if d.get("errors"):
    print(f"[WARN] {len(d['errors'])} falha(s) na última busca: {[e['label'] for e in d['errors']][:5]}")
t = json.load(open("data/best_team.json"))
for nome, lineup in (("4-2-2-2", t["lineup"]), ("4-2-3-1", t["formation2"]["lineup"])):
    labels = [c["label"] for g in lineup.values() for c in g]
    print(("[PASS]" if len(labels) == 11 == len(set(labels)) else "[FAIL]") + f" time {nome}: {len(labels)} titulares distintos")
PY
) || PYOUT="[FAIL] dados de data/ ilegíveis (rode python3 scripts/select_team.py)"
echo "$PYOUT"
P=$((P + $(grep -c '^\[PASS\]' <<<"$PYOUT"))); W=$((W + $(grep -c '^\[WARN\]' <<<"$PYOUT"))); F=$((F + $(grep -c '^\[FAIL\]' <<<"$PYOUT")))

PYT="${PYTHON:-$HOME/Sandbox/_auditoria-projetos/.tools/venv/bin/python}"
if "$PYT" -m pytest --version >/dev/null 2>&1; then
  "$PYT" -m pytest -q tests >/dev/null 2>&1 && pass "testes (sem rede)" || fail "testes falharam ($PYT -m pytest tests)"
else
  warn "pytest indisponível (defina PYTHON=<python com pytest>)"
fi
echo; echo "PASS $P · WARN $W · FAIL $F"
[ "$F" -eq 0 ]
