# Onze Ideal (eFootball)

Monta o melhor time a partir dos jogadores que você tem, com atributos e o Community Tier Ranking do efhub.com, e mostra tudo num dashboard local.

## Fluxo

```bash
python3 scripts/fetch_players.py          # lê players.txt e busca cada jogador (cache de 6h; --force rebusca tudo)
python3 scripts/select_team.py            # escolhe o time -> data/best_team.json
python3 scripts/build_dashboard.py        # gera dashboard/dashboard.html (o time vai embutido no HTML)
python3 scripts/serve_dashboard.py [porta]  # http://localhost:8765/dashboard.html
```

- `players.txt`: uma linha por jogador, `Nome [Tier]: https://efhub.com/players/<id>`.
- O botão **Limpar Cache** do dashboard roda as três etapas (busca com `--force`, seleção e geração do HTML); depois é só recarregar a página. Se a busca de um jogador falhar, o dado anterior dele é mantido.
- O endpoint do botão só aceita chamadas do próprio dashboard (outro site aberto no navegador recebe 403).
- `data/` e `dashboard/dashboard.html` são gerados e não vão para o git.

Serviço local (systemd de usuário): `~/.config/systemd/user/efootball-dashboard.service` roda o `serve_dashboard.py`.

- Linha do `players.txt` fora do formato (ex.: URL que não é de jogador do efhub) não some mais em silêncio: vira erro "players.txt linha N" em `data/players.json` e a mensagem final do Limpar Cache diz quantas falhas houve.
- Elenco sem ninguém acima do corte de tier numa vaga (ex.: os dois goleiros com tier baixo): o melhor abaixo do corte é escalado, com aviso. Sem nenhum jogador da posição, o Limpar Cache termina com "Elenco sem jogador para: GK…".

## Backup e restauração

`data/` e `dashboard/dashboard.html` são regeneráveis: a fonte é o `players.txt` (versionado). Restaurar = `git checkout players.txt` e rodar as três etapas do Fluxo (ou o botão Limpar Cache). RPO: último commit do `players.txt`; RTO: ~1 min por 45 jogadores (busca no efhub).

## Testes e smoke

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests     # sem rede: busca, subprocessos e escolha do time com elenco fixo (tests/fixtures/elenco.json)
scripts/smoke-test.sh                # PASS/WARN/FAIL: serviço, dashboard, API, players.txt, idade dos dados, os dois times, testes
```
