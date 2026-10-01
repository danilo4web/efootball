// Descobre quais cartas estiveram DISPONIVEIS (em algum pack/banner) nos
// ultimos N meses, cruzando com data/card_tiers.json pra filtrar o tier
// board so pras cartas realmente obteniveis recentemente.
//
// O efhub organiza toda carta "de verdade" (playerType 2-8: featured,
// trending, legend, epic, highlight, bigtime, showtime -- so o
// playerType=1 generico de academia fica de fora) em packs/banners
// datados (ex.: "POTW 20 Aug '26", date: "2026-08-20"). A listagem
// /api/public/packs tem a mesma protecao anti-bot de /api/public/players
// (403 fora de um browser real), entao usamos Playwright igual no outro
// script pra paginar so essa parte. Ja a pagina de detalhe de cada pack
// (/packs/<slug>) e renderizada no servidor (SSR) e funciona com fetch()
// puro do Node, sem precisar de browser -- e la que estao os links pros
// jogadores daquele pack.
//
// Uso:
//   node fetch_recent_packs.js [meses]   (default: 3)
// Salva em ../../data/recent_pack_players.json: {cutoffDate, packs: [...],
// playerIds: [...]}
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const MONTHS_BACK = Number(process.argv[2] || 3);
const OUT_PATH = path.join(__dirname, '..', '..', 'data', 'recent_pack_players.json');

function cutoffDateStr(monthsBack) {
  const d = new Date();
  d.setUTCMonth(d.getUTCMonth() - monthsBack);
  return d.toISOString().slice(0, 10);
}

async function fetchPackDetail(slug) {
  const res = await fetch(`https://efhub.com/packs/${slug}`, {
    headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const html = await res.text();
  const ids = new Set();
  for (const m of html.matchAll(/"\/players\/(\d+)"/g)) ids.add(m[1]);
  return [...ids];
}

async function main() {
  const cutoff = cutoffDateStr(MONTHS_BACK);
  console.error(`buscando packs com date >= ${cutoff} (ultimos ${MONTHS_BACK} meses)`);

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('https://efhub.com/packs', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);

  async function fetchPackPage(pg) {
    return await page.evaluate(async (p) => {
      const r = await fetch(`/api/public/packs?search=&page=${p}&limit=50`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    }, pg);
  }

  const recentPacks = [];
  let pg = 1;
  let done = false;
  while (!done) {
    let data;
    for (let attempt = 1; attempt <= 4; attempt++) {
      try {
        data = await fetchPackPage(pg);
        break;
      } catch (e) {
        console.error(`  pagina de packs ${pg} falhou (tentativa ${attempt}): ${e.message}`);
        if (attempt === 4) throw e;
        await page.waitForTimeout(attempt * 5000);
      }
    }
    for (const p of data.packs) {
      if (p.date < cutoff) { done = true; break; }
      recentPacks.push(p);
    }
    if (!data.hasMore) done = true;
    pg++;
    await page.waitForTimeout(500);
  }
  await browser.close();

  console.error(`${recentPacks.length} packs dentro da janela, buscando os jogadores de cada um...`);

  const playerIds = new Set();
  for (let i = 0; i < recentPacks.length; i++) {
    const p = recentPacks[i];
    try {
      const ids = await fetchPackDetail(p.slug);
      ids.forEach((id) => playerIds.add(id));
      if ((i + 1) % 20 === 0) console.error(`  [${i + 1}/${recentPacks.length}] packs processados, ${playerIds.size} jogadores unicos ate agora`);
    } catch (e) {
      console.error(`  pack ${p.slug} falhou: ${e.message}`);
    }
    await new Promise((r) => setTimeout(r, 200));
  }

  const out = {
    cutoffDate: cutoff,
    fetchedAt: Date.now(),
    packs: recentPacks.map((p) => ({ name: p.name, slug: p.slug, date: p.date })),
    playerIds: [...playerIds],
  };
  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2));
  console.error(`OK: ${recentPacks.length} packs, ${playerIds.size} jogadores unicos salvos em ${OUT_PATH}`);
}

main().catch((e) => {
  console.error('ERRO:', e);
  process.exit(1);
});
