// Baixa a listagem completa de cartas "reais" do efhub.com (exclui os
// jogadores genericos de academia, playerType=1 -- 33887 dos 47237 cards
// totais, sao nomes ficticios tipo "Safi Belal"/"Team Blue" que nunca
// recebem voto de tier).
//
// O endpoint /api/public/players tem protecao anti-bot: retorna 403
// "Forbidden" pra requisicoes simples (curl/urllib), mas funciona
// normalmente quando chamado de dentro de um browser real (confirmado com
// Playwright) -- entao esse script abre a pagina /players uma vez e faz
// os fetches paginados a partir do contexto JS da propria pagina.
//
// A API ordena por overallRating decrescente e nao aceita mudar o "limit"
// (sempre 24 por pagina) nem filtrar por overall minimo -- entao paginamos
// sequencialmente e paramos assim que aparecer uma carta abaixo do corte.
//
// Uso:
//   node fetch_card_listing.js [minOverall]   (default: 82)
// Salva em ../../data/card_database.json
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const MIN_OVERALL = Number(process.argv[2] || 82);
const PLAYER_TYPES = '2,3,4,5,6,7,8';
const OUT_PATH = path.join(__dirname, '..', '..', 'data', 'card_database.json');

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('https://efhub.com/players', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);

  async function fetchPage(pg) {
    return await page.evaluate(async ([types, p]) => {
      const r = await fetch(`/api/public/players?playerType=${types}&page=${p}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    }, [PLAYER_TYPES, pg]);
  }

  const first = await fetchPage(1);
  const totalPages = first.totalPages;
  console.error(`total cartas (tipos ${PLAYER_TYPES}): ${first.total}, ${totalPages} paginas, cortando em overall >= ${MIN_OVERALL}`);

  const cards = [];
  let stopped = false;
  const PAGE_DELAY_MS = 700; // ritmo educado -- a API deu 429 sem essa pausa

  for (let pg = 1; pg <= totalPages && !stopped; pg++) {
    await page.waitForTimeout(PAGE_DELAY_MS);
    let data;
    const backoffs = [5000, 15000, 30000];
    for (let attempt = 1; attempt <= 4; attempt++) {
      try {
        data = await fetchPage(pg);
        break;
      } catch (e) {
        const is429 = /429/.test(e.message);
        console.error(`  pagina ${pg} falhou (tentativa ${attempt}): ${e.message}`);
        if (attempt === 4) throw e;
        const wait = is429 ? backoffs[Math.min(attempt - 1, backoffs.length - 1)] : 1000 * attempt;
        await page.waitForTimeout(wait);
      }
    }
    for (const p of data.players) {
      if (p.overallRating < MIN_OVERALL) {
        stopped = true;
        break;
      }
      cards.push(p);
    }
    if (pg % 25 === 0 || stopped) {
      console.error(`  pagina ${pg}/${totalPages} -> ${cards.length} cartas ate agora`);
    }
  }

  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, JSON.stringify({ minOverall: MIN_OVERALL, fetchedAt: Date.now(), cards }, null, 2));
  console.error(`OK: ${cards.length} cartas com overall >= ${MIN_OVERALL} salvas em ${OUT_PATH}`);

  await browser.close();
}

main().catch((e) => {
  console.error('ERRO:', e);
  process.exit(1);
});
