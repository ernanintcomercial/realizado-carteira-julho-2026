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
const REGION_ORDER = ['SUL E CENTRO OESTE', 'SUDESTE', 'NORTE E NORDESTE'];
const UF_REGION = {
  ACRE:'NORTE E NORDESTE',ALAGOAS:'NORTE E NORDESTE',AMAPA:'NORTE E NORDESTE',AMAZONAS:'NORTE E NORDESTE',
  BAHIA:'NORTE E NORDESTE',CEARA:'NORTE E NORDESTE',MARANHAO:'NORTE E NORDESTE',PARA:'NORTE E NORDESTE',
  PARAIBA:'NORTE E NORDESTE',PERNAMBUCO:'NORTE E NORDESTE',PIAUI:'NORTE E NORDESTE','RIO GRANDE DO NORTE':'NORTE E NORDESTE',
  RONDONIA:'NORTE E NORDESTE',RORAIMA:'NORTE E NORDESTE',SERGIPE:'NORTE E NORDESTE',TOCANTINS:'NORTE E NORDESTE',
  'ESPIRITO SANTO':'SUDESTE','MINAS GERAIS':'SUDESTE','RIO DE JANEIRO':'SUDESTE','SAO PAULO':'SUDESTE',
  'DISTRITO FEDERAL':'SUL E CENTRO OESTE',GOIAS:'SUL E CENTRO OESTE','MATO GROSSO':'SUL E CENTRO OESTE',
  'MATO GROSSO DO SUL':'SUL E CENTRO OESTE',PARANA:'SUL E CENTRO OESTE','RIO GRANDE DO SUL':'SUL E CENTRO OESTE',
  'SANTA CATARINA':'SUL E CENTRO OESTE',
};

const norm = v => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
const field = (row, wanted) => row[Object.keys(row).find(k => norm(k) === norm(wanted))];
const regionName = v => {
  const text = norm(v).replace(/\s+/g, ' ');
  if (text.includes('SUDESTE')) return 'SUDESTE';
  if (text.includes('NORTE')) return 'NORTE E NORDESTE';
  if (text.includes('SUL') || text.includes('CENTRO')) return 'SUL E CENTRO OESTE';
  return null;
};
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
const indexRegion = new Map(indexRows.map(r => [Number(r.codigo), regionName(field(r, 'regiao'))]).filter(x => Number.isFinite(x[0]) && x[1]));
for (const row of wallet) {
  const id = Number(row['ID Representante']);
  row._region = indexRegion.get(id) || UF_REGION[norm(row['Unidade Federativa'])] || 'NORTE E NORDESTE';
}
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
const buildRegion = region => {
  const scoped = wallet.filter(r => r._region === region);
  const ids = [...new Set(scoped.map(r => Number(r['ID Representante'])).filter(Number.isFinite))];
  const contratos = ORDER.map(c => {
    const rows = scoped.filter(r => contract(r.Contrato) === c);
    const realizado = money(rows.reduce((n, r) => n + (Number(r['Total Geral']) || 0), 0));
    const carteira = money(rows.reduce((n, r) => n + (Number(r.Carteira) || 0), 0));
    return { contrato:c, realizado, carteira, potencial:money(realizado + carteira) };
  });
  const serieDiaria = []; let real = 0, carteira = 0;
  for (const date of dates) {
    const rows = scoped.filter(r => dateKey(r.Data) === date);
    real += rows.reduce((n, r) => n + (Number(r['Total Geral']) || 0), 0);
    carteira += rows.reduce((n, r) => n + (Number(r.Carteira) || 0), 0);
    serieDiaria.push({ data:date, realizado:money(real), carteira:money(carteira) });
  }
  const representantes = ids.map(id => {
    const repRows = scoped.filter(r => Number(r['ID Representante']) === id);
    const repContracts = ORDER.map(c => {
      const rows = repRows.filter(r => contract(r.Contrato) === c);
      const realizado = money(rows.reduce((n, r) => n + (Number(r['Total Geral']) || 0), 0));
      const carteira = money(rows.reduce((n, r) => n + (Number(r.Carteira) || 0), 0));
      return { contrato:c, realizado, carteira, potencial:money(realizado + carteira) };
    });
    let repReal = 0, repWallet = 0;
    const repSeries = dates.map(date => {
      const rows = repRows.filter(r => dateKey(r.Data) === date);
      repReal += rows.reduce((n, r) => n + (Number(r['Total Geral']) || 0), 0);
      repWallet += rows.reduce((n, r) => n + (Number(r.Carteira) || 0), 0);
      return { data:date, realizado:money(repReal), carteira:money(repWallet) };
    });
    return { id, nome:String(repRows[0]['Nome Abreviado'] || id), regiao:region, realizado:money(repReal),
      carteira:money(repWallet), potencial:money(repReal + repWallet), foraINDEX:!indexCodes.has(id),
      contratos:repContracts, serieDiaria:repSeries };
  }).sort((a,b) => b.realizado - a.realizado);
  const realizado = money(contratos.reduce((n,x) => n+x.realizado,0));
  const carteiraTotal = money(contratos.reduce((n,x) => n+x.carteira,0));
  return { regiao:region, realizado, carteira:carteiraTotal, potencial:money(realizado+carteiraTotal),
    contratos, representantes, serieDiaria };
};
const regions = REGION_ORDER.map(buildRegion);
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
  regioes: regions,
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
