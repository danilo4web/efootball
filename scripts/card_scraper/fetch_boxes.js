// Lista as boxes (packs) lançadas nos últimos N dias no efhub, com os
// jogadores de cada uma e a Community Tier Ranking (votos) de cada jogador,
// pra aba "Boxes" do dashboard.
//
// O efhub não informa preço, moeda nem data de término das boxes. A
// listagem /api/public/packs só funciona dentro de um browser real (403
// fora dele, ver fetch_recent_packs.js), por isso o Playwright; já a página
// de cada pack é SSR e traz os jogadores com playerType, então basta fetch().
//
// Classificação da forma de pagamento (heurística, mostrada no dashboard):
//   - nome com Reward/Rewards/Campaign/Ranking/"Road to"  -> "evento"
//     (recompensa de evento, não é box comprável)
//   - algum jogador playerType 3 (POTW/POTM) ou 8 (épico/destaque)  -> "moedas"
//   - só playerType 6 (packs "Selection" de jogadores padrão)  -> "troca"
//     (box resgatada trocando jogadores ★5/★4)
//
// Uso:
//   node fetch_boxes.js [dias]   (default: 14)
// Salva em ../../data/boxes.json
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const DAYS_BACK = Number(process.argv[2] || 14);
const OUT_PATH = path.join(__dirname, '..', '..', 'data', 'boxes.json');
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';

function cutoffDateStr(daysBack) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - daysBack);
  return d.toISOString().slice(0, 10);
}

function classify(pack) {
  if (/reward|campaign|ranking|road to/i.test(pack.name)) return 'evento';
  const types = new Set(pack.players.map(p => p.playerType));
  if (types.has(3) || types.has(8)) return 'moedas';
  return 'troca';
}

async function fetchText(url, tries = 3) {
  for (let i = 1; ; i++) {
    try {
      const res = await fetch(url, { headers: { 'User-Agent': UA, Accept: 'application/json,text/html' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.text();
    } catch (e) {
      if (i >= tries) throw e;
      await new Promise(r => setTimeout(r, 1000 * i));
    }
  }
}

async function fetchPackPlayers(slug) {
  const html = (await fetchText(`https://efhub.com/packs/${slug}`)).replace(/\\"/g, '"');
  const players = new Map();
  const re = /\{"id":"(\d+)","name":"([^"]*)"[^{}]*?"team":"([^"]*)"[^{}]*?"position":"([A-Z]+)","overallRating":(\d+),"playingStyle":"([^"]*)"[^{}]*?"imageUrl":"([^"]*)","playerType":(\d+)\}/g;
  for (const m of html.matchAll(re)) {
    players.set(m[1], {
      id: m[1], name: m[2], team: m[3], position: m[4], overall: Number(m[5]),
      playingStyle: m[6] === '$undefined' ? null : m[6], imageUrl: m[7], playerType: Number(m[8]),
    });
  }
  return [...players.values()];
}

async function fetchTier(id) {
  try {
    const t = JSON.parse(await fetchText(`https://efhub.com/api/player-tier?playerId=${id}`));
    return {
      consensusTier: t.consensusTier || null,
      tierCounts: t.tierCounts || {},
      totalPlacements: t.totalPlacements || 0,
    };
  } catch (e) {
    return { consensusTier: null, tierCounts: {}, totalPlacements: 0, error: String(e.message || e) };
  }
}

async function mapLimit(items, limit, fn) {
  const out = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: limit }, async () => {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i], i);
    }
  }));
  return out;
}

async function main() {
  const cutoff = cutoffDateStr(DAYS_BACK);
  console.error(`boxes com date >= ${cutoff} (últimos ${DAYS_BACK} dias)`);

  const browser = await chromium.launch();
  let listed = [];
  try {
    const page = await browser.newPage();
    await page.goto('https://efhub.com/packs', { waitUntil: 'networkidle', timeout: 45000 });
    for (let pg = 1; pg <= 10; pg++) {
      const r = await page.evaluate(async p => {
        const res = await fetch(`/api/public/packs?search=&page=${p}&limit=50`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      }, pg);
      const packs = r.packs || [];
      listed = listed.concat(packs.filter(p => p.date >= cutoff));
      // a API ordena por data decrescente: parou de aparecer pack recente, acabou
      if (!r.hasMore || packs.some(p => p.date < cutoff)) break;
    }
  } finally {
    await browser.close();
  }
  console.error(`${listed.length} boxes no período`);

  const packs = [];
  for (const pk of listed) {
    try {
      const players = await fetchPackPlayers(pk.slug);
      if (!players.length) { console.error(`  ${pk.name}: sem jogadores, ignorada`); continue; }
      packs.push({ name: pk.name, slug: pk.slug, date: pk.date, players });
    } catch (e) {
      console.error(`  ${pk.name}: falhou (${e.message})`);
    }
  }

  const ids = [...new Set(packs.flatMap(p => p.players.map(x => x.id)))];
  console.error(`buscando votos de ${ids.length} jogadores...`);
  const tiers = await mapLimit(ids, 8, fetchTier);
  const tierById = Object.fromEntries(ids.map((id, i) => [id, tiers[i]]));

  for (const pk of packs) {
    pk.payment = classify(pk);
    for (const p of pk.players) Object.assign(p, tierById[p.id]);
  }

  const out = { fetchedAt: Date.now(), cutoffDate: cutoff, daysBack: DAYS_BACK, packs };
  fs.writeFileSync(OUT_PATH + '.tmp', JSON.stringify(out, null, 1));
  fs.renameSync(OUT_PATH + '.tmp', OUT_PATH);
  const byPay = packs.reduce((a, p) => ((a[p.payment] = (a[p.payment] || 0) + 1), a), {});
  console.error(`OK: ${packs.length} boxes salvas em ${OUT_PATH} ${JSON.stringify(byPay)}`);
}

main().catch(e => { console.error(e); process.exit(1); });
