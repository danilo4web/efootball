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

## Testes

```bash
python3 -m pytest tests      # sem rede: busca e subprocessos simulados
```
