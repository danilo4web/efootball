# Evolução autônoma — Onze Ideal (efootball) — 2026-09-30

## Resumo executivo

Ferramenta pessoal (Python, ~2.100 linhas) que monta o melhor time de eFootball a partir das cartas do usuário, com dados raspados do efhub.com, e mostra um dashboard rico em localhost. O botão principal de manutenção, **"Limpar Cache", não funcionava**: rebuscava e remontava o time, mas não gerava o HTML de novo — recarregar mostrava o time antigo. Além disso, ele **apagava do time** o jogador cuja busca falhasse, e o endpoint aceitava chamadas de **qualquer site** aberto no navegador (disparando uma raspagem completa do efhub). Tudo corrigido com 6 testes sem rede; repositório criado; README.

**Maturidade: 49% → 60% (+11 p.p.) — MVP funcional.** Ganho alto por partir de zero testes, sem git e com a função de atualização quebrada.

## Objetivo do projeto

Dizer qual é o melhor onze (e reservas) com as cartas que o usuário tem, com atributos, tier da comunidade, análises, treino ideal e comparação de jogadores.

## Estado inicial

- Sem git (baseline `93a82a0`, sem `data/`, `dashboard.html` gerado, `node_modules` e `.claude/settings.local.json`).
- Serviço systemd de usuário `efootball-dashboard` ativo em 127.0.0.1:8765.
- Sem testes nem README. Diagnóstico registrado antes das mudanças: `docs/RELATORIOS/2026-09-30-diagnostico-inicial.md`.

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
| **Total** | | | **49,0 %** (MVP funcional) |

## Evidências usadas

Leitura de `serve_dashboard.py`, `fetch_players.py`, `build_dashboard.py`, `common.py`, do template do dashboard e da unidade systemd; testes com busca e subprocessos simulados; teste do servidor real (POST com Origin externo); navegação com Playwright.

## Principais riscos

1. Atualização do dashboard não acontecia pelo botão.
2. Perda de jogadores quando o efhub falha durante "Limpar Cache".
3. CSRF em localhost disparando raspagem (risco de bloqueio do IP no efhub).
4. Dependência de raspagem de site de terceiros (mudança de layout/API do efhub).

## P0 encontrados

Nenhum.

## P1 encontrados

| # | Problema | Status |
|---|---|---|
| 1 | "Limpar Cache" não regerava o `dashboard.html` (time antigo após recarregar; mensagem dizia o contrário) | Corrigido |
| 2 | Com `--force`, jogador cuja busca falhava sumia do time | Corrigido |

## P2 encontrados

| # | Problema | Status |
|---|---|---|
| 3 | `POST /api/clear-cache` aceitava qualquer origem (CSRF em localhost) | Corrigido (403 para outra origem) |
| 4 | `players.json` gravado sem troca atômica | Corrigido |
| 5 | Porta lida de `sys.argv` na importação (impedia testar) | Corrigido (lida no `main`) |

## Bugs confirmados

4 (itens 1–4), cada um reproduzido por teste que falhava antes.

## Bugs corrigidos

4 de 4.

## Melhorias implementadas

- `serve_dashboard.py`: terceira etapa `build_dashboard.py` no refresh (com status "gerando o dashboard" e erro tratado); `_same_origin()` recusa POST de outra origem; porta lida no `main()`.
- `fetch_players.py`: cache sempre carregado (o `--force` só ignora a validade de 6 h); gravação em temporário + `os.replace`.
- README com o fluxo, o botão, a proteção e os testes; `.gitignore` para dados gerados.
- Serviço `efootball-dashboard` reiniciado com o código novo (conferido: POST com `Origin` externo → 403).

## Testes adicionados

`tests/test_refresh.py` (6): `--force` mantém dado antigo quando a busca falha; `--force` rebusca mesmo com cache fresco; gravação atômica; "Limpar Cache" roda as três etapas; outra origem recebe 403 sem disparar nada; o próprio dashboard (127.0.0.1 e localhost) dispara.

## Testes executados

`pytest tests` e `ruff check scripts tests --select E9,F`.

## Resultado das suítes

Antes: nenhuma. Depois: **6 passed**.

## Resultado de lint

ruff (E9, F): All checks passed.

## Resultado de static analysis

N/A.

## Resultado de build

`build_dashboard.py` faz parte do refresh; o `dashboard.html` atual continua servido normalmente.

## Fluxos validados

Playwright contra o serviço real: onze titular (duas formações), análises, elenco por posição, votos por carta, treinamento ideal, comparar jogadores, botão Limpar Cache (sem acionar — evitaria uma raspagem real), página externa tentando chamar o endpoint (recusada; `/api/cache-status` continua `idle`).

## Screenshots gerados

`docs/evidencias/2026-09-30/`: `01-onze-titular.png`, `02-comparar.png`, `03-limpar-cache.png`, `04-melhoria-origem.png` (+ `outro-site.html`, a página de teste).

## Vídeo gerado

Sim — MP4 H.264, 1440×900, 1 min 02 s, 1.521.420 bytes. Script: `docs/evidencias/2026-09-30/demo.py`.

## Caminho do vídeo

- `docs/evidencias/2026-09-30/demo-final.mp4`
- cópia: `~/Sandbox/_auditoria-projetos/videos/efootball.mp4`

## Estado final

Commitado; serviço local rodando o código corrigido.

## Percentual final

| Eixo | Peso | Antes | Depois | Pontos |
|---|---:|---:|---:|---:|
| Produto | 30 | 65 | 69 | 20,7 |
| Backend | 15 | 55 | 63 | 9,45 |
| Frontend | 10 | 75 | 75 | 7,5 |
| Integrações | 10 | 55 | 58 | 5,8 |
| Testes | 15 | 0 | 40 | 6,0 |
| Segurança | 5 | 50 | 65 | 3,25 |
| Operação | 5 | 45 | 50 | 2,5 |
| Produção | 10 | 35 | 50 | 5,0 |
| **Total** | | **49,0** | | **60,2 ≈ 60 %** (MVP funcional) |

## Comparativo antes x depois

ANTES — Produto 65 · Backend 55 · Frontend 75 · Integrações 55 · Testes 0 · Segurança 50 · Operação 45 · Produção 35 → **TOTAL 49 %**

DEPOIS — Produto 69 · Backend 63 · Frontend 75 · Integrações 58 · Testes 40 · Segurança 65 · Operação 50 · Produção 50 → **TOTAL 60 %**

## Ganho percentual

**+11 p.p.**

## Pendências restantes

- Testes do `select_team.py` (o coração da escolha do time) com um elenco fixo.
- Validação do `players.txt` (linha malformada) e aviso no dashboard quando o efhub muda o formato.
- Scrapers em Node (`card_scraper`) sem testes.

## Dependências externas

efhub.com (páginas públicas e `/api/player-tier`).

## Dependências humanas

Manter o `players.txt` atualizado.

## O que impede chegar a 100%

Dependência de raspagem de site de terceiros sem contrato; lógica de seleção sem testes; sem histórico das escolhas.

## Próximas 5 ações de maior impacto

1. Testes de `select_team.py` com um elenco de referência (pega regressão de pesos/papéis).
2. Validar `players.txt` e mostrar no dashboard os jogadores com erro de busca.
3. Detectar mudança de formato do efhub (página sem os campos esperados → erro claro).
4. Histórico do time (data + escolhas) para comparar rodadas.
5. Testes dos scrapers Node.

## Arquivos alterados

`scripts/serve_dashboard.py`, `scripts/fetch_players.py`, `tests/test_refresh.py` (novo), `README.md` (novo), `.gitignore` (novo), `docs/*`.

## Commits da sessão

- `93a82a0` chore: baseline do Onze Ideal (eFootball)
- `3b0886d` fix(fetch): --force não apaga jogador quando a busca falha; gravação atômica
- `cecd8c9` fix(dashboard): Limpar Cache gera o dashboard de novo; endpoint recusa outros sites
- `b84523b` test: fetch resumível e Limpar Cache sem rede; README
- (este relatório) docs: relatório e evidências

## Git status final

Limpo após o commit de documentação.
