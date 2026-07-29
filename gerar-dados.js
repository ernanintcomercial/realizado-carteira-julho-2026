const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');

const DIR = path.join(__dirname, 'dados');
const FILES = {
  carteira: path.join(DIR, 'carteira.xlsx'),
  pedidos: path.join(DIR, 'WWWPD010.xlsx'),
  index: path.join(DIR, 'INDEX.xlsx'),
};
const CONTRACTS = { DL: 'LED', DP: 'PLÁSTICO', DU: 'ALUMÍNIO', DX: 'EX' };
const ORDER = ['ALUMÍNIO', 'PLÁSTICO', 'LED', 'EX'];

const norm = v => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
const money = v => Math.round((Number(v) || 0) * 100) / 100;
const contract = v => CONTRACTS[norm(v).slice(0, 2)] || 'OUTROS';
const dateKey = v => {
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  if (typeof v === 'number') return new Date(Date.UTC(1899, 11, 30) + v * 86400000).toISOString().slice(0, 10);
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 10);
};
const read = (file, rawHeader = false) => {
  const wb = XLSX.readFile(file, { cellDates: true });
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!rawHeader) return XLSX.utils.sheet_to_json(ws, { defval: null });
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null });
  const headerIndex = (rows[0] || []).filter(x => x !== null && x !== '').length <= 1 ? 1 : 0;
  return rows.slice(headerIndex + 1).map(row => Object.fromEntries(rows[headerIndex].map((h, i) => [h, row[i] ?? null])));
};
const add = (map, key, value) => map.set(key, (map.get(key) || 0) + (Number(value) || 0));

for (const file of Object.values(FILES)) {
  if (!fs.existsSync(file)) throw new Error(`Arquivo ausente: ${file}`);
}

const wallet = read(FILES.carteira).filter(r => dateKey(r.Data).startsWith('2026-07'));
const orders = read(FILES.pedidos, true).filter(r =>
  dateKey(r['Dt Implant']).startsWith('2026-07') && !norm(r['Situação Item']).includes('CANCELAD')
);
const indexRows = read(FILES.index);
const indexCodes = new Set(indexRows.map(r => Number(r.codigo)).filter(Number.isFinite));
const reps = new Set();
const walletRepIds = new Set();

const walletDaily = new Map();
const walletBacklogDaily = new Map();
const repDaily = new Map();
const repBacklogDaily = new Map();
const repContractSales = new Map();
const repContractBacklog = new Map();
const repNames = new Map();
for (const row of wallet) {
  const date = dateKey(row.Data), c = contract(row.Contrato);
  if (!ORDER.includes(c)) continue;
  add(walletDaily, `${date}|${c}`, row['Total Geral']);
  add(walletBacklogDaily, `${date}|${c}`, row.Carteira);
  const repId = Number(row['ID Representante']);
  if (Number.isFinite(repId)) {
    reps.add(repId); walletRepIds.add(repId);
    repNames.set(repId, String(row['Nome Abreviado'] || repId));
    add(repDaily, `${date}|${repId}`, row['Total Geral']);
    add(repBacklogDaily, `${date}|${repId}`, row.Carteira);
    add(repContractSales, `${repId}|${c}`, row['Total Geral']);
    add(repContractBacklog, `${repId}|${c}`, row.Carteira);
  }
}
const orderDaily = new Map();
for (const row of orders) {
  const date = dateKey(row['Dt Implant']), c = contract(row['Tipo Pedido']);
  if (!ORDER.includes(c)) continue;
  add(orderDaily, `${date}|${c}`, row.ROB);
  if (Number.isFinite(Number(row.Repres))) reps.add(Number(row.Repres));
}

const dates = Array.from({ length: 31 }, (_, i) => `2026-07-${String(i + 1).padStart(2, '0')}`);
const cumulative = Object.fromEntries(ORDER.map(c => [c, { real: 0, wallet: 0, check: 0 }]));
const series = dates.map(date => {
  const point = { data: date };
  for (const c of ORDER) {
    cumulative[c].real += walletDaily.get(`${date}|${c}`) || 0;
    cumulative[c].wallet += walletBacklogDaily.get(`${date}|${c}`) || 0;
    cumulative[c].check += orderDaily.get(`${date}|${c}`) || 0;
    const slug = norm(c).toLowerCase().replace('ç', 'c');
    point[`${slug}_realizado`] = money(cumulative[c].real);
    point[`${slug}_carteira`] = money(cumulative[c].wallet);
  }
  return point;
});
const contracts = ORDER.map(c => ({
  contrato: c,
  realizado: money(cumulative[c].real),
  carteira: money(cumulative[c].wallet),
  potencial: money(cumulative[c].real + cumulative[c].wallet),
  participacaoCarteira: cumulative[c].real + cumulative[c].wallet
    ? money(cumulative[c].wallet / (cumulative[c].real + cumulative[c].wallet))
    : 0,
  diferencaVerificacao: money(cumulative[c].real - cumulative[c].check),
}));
const representatives = [...walletRepIds].map(id => {
  let real = 0, walletValue = 0;
  const serieDiaria = dates.map(date => {
    real += repDaily.get(`${date}|${id}`) || 0;
    walletValue += repBacklogDaily.get(`${date}|${id}`) || 0;
    return { data: date, realizado: money(real), carteira: money(walletValue) };
  });
  const contratos = ORDER.map(c => {
    const realizado = money(repContractSales.get(`${id}|${c}`) || 0);
    const carteira = money(repContractBacklog.get(`${id}|${c}`) || 0);
    return { contrato: c, realizado, carteira, potencial: money(realizado + carteira) };
  });
  return {
    id,
    nome: repNames.get(id) || String(id),
    realizado: money(real),
    carteira: money(walletValue),
    potencial: money(real + walletValue),
    foraINDEX: !indexCodes.has(id),
    contratos,
    serieDiaria,
  };
}).sort((a, b) => b.realizado - a.realizado);
const sum = field => money(contracts.reduce((n, row) => n + row[field], 0));
const lastDate = wallet.map(r => dateKey(r.Data)).sort().at(-1);
const totalCheck = money(orders.reduce((n, r) => n + (Number(r.ROB) || 0), 0));
const totalSource = sum('realizado');
const payload = {
  titulo: 'Realizado x Carteira — Julho 2026',
  periodo: { inicio: '2026-07-01', fim: lastDate },
  geradoEm: new Date().toLocaleString('pt-BR'),
  totais: { realizado: totalSource, carteira: sum('carteira'), potencial: sum('potencial') },
  contratos: contracts,
  representantes: representatives,
  serieDiaria: series,
  verificacoes: {
    totalWWWPD010: totalCheck,
    totalArquivoEnviado: totalSource,
    diferencaTotal: money(totalSource - totalCheck),
    valorReclassificadoEntreContratos: money(contracts.reduce((n, x) => n + Math.abs(x.diferencaVerificacao), 0) / 2),
    representantesForaINDEX: [...reps].filter(x => !indexCodes.has(x)).sort((a, b) => a - b),
    status: contracts.some(x => Math.abs(x.diferencaVerificacao) > 0.01) ? 'ATENÇÃO' : 'OK',
  },
  fontes: [
    'carteira.xlsx — realizado, carteira e contrato',
    'WWWPD010.xlsx — verificação do realizado',
    'INDEX.xlsx — verificação cadastral dos representantes',
  ],
};

fs.writeFileSync(path.join(__dirname, 'dados-julho.json'), JSON.stringify(payload, null, 2));
console.log(`dados-julho.json gerado. Realizado=${payload.totais.realizado}; carteira=${payload.totais.carteira}`);
