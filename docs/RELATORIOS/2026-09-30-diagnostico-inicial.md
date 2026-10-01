# Diagnóstico inicial — 2026-09-30

"Onze Ideal": ferramenta pessoal que lê `players.txt` (links do efhub.com), raspa atributos e o Community Tier Ranking, escolhe o melhor time (`select_team.py`) e gera um `dashboard.html` estático, servido em localhost:8765 por `serve_dashboard.py` (serviço systemd de usuário) com um botão "Limpar Cache". Sem git (baseline criado), sem testes, sem README.

## Percentual inicial
| Eixo | Peso | Nota | Pontos |
|---|---:|---:|---:|
| Produto | 30 | 65 | 19,5 |
| Backend | 15 | 55 | 8,25 |
| Frontend | 10 | 75 | 7,5 |
| Integrações | 10 | 55 | 5,5 |
| Testes | 15 | 0 | 0,0 |
| Segurança | 5 | 50 | 2,5 |
| Operação | 5 | 45 | 2,25 |
| Produção | 10 | 35 | 3,5 |
| **Total** | | | **49,0 → 49 % (MVP funcional)** |

## Problemas confirmados na leitura
1. **P1** — "Limpar Cache" roda `fetch_players --force` e `select_team`, mas não `build_dashboard`: o `dashboard.html` embute o time no build, então recarregar a página não mostra nada novo (a mensagem diz o contrário).
2. **P1** — com `--force` o cache antigo não é carregado: jogador cuja busca falha some do time (o fallback "usar dado antigo" só funciona sem `--force`).
3. **P2** — `POST /api/clear-cache` aceita requisição de qualquer site aberto no navegador (CSRF em localhost): uma página qualquer dispara uma raspagem completa do efhub.
4. **P2** — `players.json` gravado sem troca atômica: interrupção no meio corrompe o arquivo e a próxima rodada perde todo o cache.

## Plano
Corrigir 1–4 com testes (pytest, sem rede: busca e subprocessos simulados); README; vídeo do dashboard.
