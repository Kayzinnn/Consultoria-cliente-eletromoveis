/* Motor de cálculo do BI: mesmas regras das medidas DAX do Power BI.
   - Data de referência: último dia do período filtrado que tem venda carregada.
   - Período (P): dias filtrados (ano x mês) até a data de referência.
   - Ano anterior (PY): os mesmos dias de P, um ano antes.
   - Filial: filtra fato, metas e orçamento. */
(function () {
  const D = window.DADOS;
  if (!D) { const e = document.getElementById("erro"); e.hidden = false; e.textContent = "Arquivo de dados não encontrado. Rode: python BI_HTML/exportar_dados.py"; return; }
  const DIA_MS = 86400000;
  const dic = D.dic, F = D.fato, O = D.orc;
  const N = F.d.length;

  const idx = (col, nome) => dic[col].indexOf(nome);
  const iNat = { rec: idx("natureza", "Receita"), custo: idx("natureza", "Custo"), desp: idx("natureza", "Despesa") };
  const iGrp = {
    fat: idx("grupo_dre", "Receita bruta de vendas"),
    desc: idx("grupo_dre", "Descontos e acréscimos"),
  };
  const fora = ["Pró-labore", "Impostos", "Despesas financeiras"].map((g) => idx("grupo_dre", g));
  const iConta = { perda: idx("conta", "CMV - trocas e devoluções"), cmv: idx("conta", "CMV") };
  const iOrig = { erp: idx("origem", "ERP vendas"), meta: idx("origem", "Meta de vendas") };

  // ---- datas ----
  const toDate = (d) => new Date(d * DIA_MS);
  const ymd = (d) => { const x = toDate(d); return [x.getUTCFullYear(), x.getUTCMonth() + 1, x.getUTCDate()]; };
  const dayOf = (y, m, dd) => Math.round(Date.UTC(y, m - 1, dd) / DIA_MS);
  const diasNoMes = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
  const anoAntes = (d) => { const [y, m, dd] = ymd(d); return dayOf(y - 1, m, Math.min(dd, diasNoMes(y - 1, m))); };

  let dMin = Infinity, dMax = -Infinity, ultimaVenda = -Infinity;
  for (let i = 0; i < N; i++) {
    const d = F.d[i];
    if (d < dMin) dMin = d;
    if (d > dMax) dMax = d;
    if (F.origem[i] === iOrig.erp && d > ultimaVenda) ultimaVenda = d;
  }
  const anoMin = ymd(dMin)[0], anoMax = Math.max(ymd(dMax)[0], ymd(ultimaVenda)[0]);
  const BASE = dayOf(anoMin - 1, 1, 1);           // máscaras cobrem do ano anterior ao primeiro dado
  const TAM = dayOf(anoMax + 1, 1, 1) - BASE;

  const lojas = dic.loja.map((nome, i) => ({ nome, i, negocio: null }));
  for (let i = 0; i < N; i++) if (F.loja[i] >= 0 && F.negocio[i] >= 0) lojas[F.loja[i]].negocio = dic.negocio[F.negocio[i]];

  // ---- estado dos filtros ----
  const estado = {
    anos: new Set([ymd(ultimaVenda)[0]]),
    meses: new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
    lojas: new Set(lojas.map((l) => l.i)),
  };

  let ctx = null;
  function recalcular() {
    const cal = new Uint8Array(TAM), P = new Uint8Array(TAM), PY = new Uint8Array(TAM);
    let ref = null, nMeses = new Set();
    for (const y of estado.anos) for (const m of estado.meses) {
      for (let dd = 1; dd <= diasNoMes(y, m); dd++) {
        const d = dayOf(y, m, dd);
        cal[d - BASE] = 1;
        if (d <= ultimaVenda && (ref === null || d > ref)) ref = d;
      }
    }
    let pIni = null;
    if (ref !== null) for (let k = 0; k < TAM; k++) if (cal[k] && k + BASE <= ref) {
      P[k] = 1; const d = k + BASE; if (pIni === null) pIni = d;
      const a = anoAntes(d) - BASE; if (a >= 0) PY[a] = 1;
      const [y, m] = ymd(d); nMeses.add(y * 100 + m);
    }
    const lojaOk = new Uint8Array(dic.loja.length);
    for (const l of estado.lojas) lojaOk[l] = 1;
    const todas = estado.lojas.size === dic.loja.length;
    ctx = { cal, P, PY, ref, pIni, nMeses, lojaOk, todas };
    return ctx;
  }

  // ---- acumulador com as medidas base ----
  function novo() {
    return { rl: 0, fat: 0, desc: 0, cmv: 0, desp: 0, despOp: 0, res: 0, perda: 0, cmvp: 0, q: 0, ult: null, meta: 0, temMeta: false, g: {} };
  }
  function soma(a, i) {
    const v = F.v[i], nat = F.natureza[i], grp = F.grupo_dre[i];
    if (nat === iNat.rec) { a.rl += v; if (a.ult === null || F.d[i] > a.ult) a.ult = F.d[i]; }
    else if (nat === iNat.custo) a.cmv += v;
    else if (nat === iNat.desp) { a.desp += v; if (!fora.includes(grp)) a.despOp += v; }
    if (grp === iGrp.fat) a.fat += v;
    else if (grp === iGrp.desc) a.desc += v;
    if (F.dre[i]) { a.res += v; if (grp >= 0) a.g[grp] = (a.g[grp] || 0) + v; }
    const c = F.conta[i];
    if (c === iConta.perda) a.perda -= v;
    else if (c === iConta.cmv) a.cmvp -= v;
    a.q += F.q[i];
    if (F.origem[i] === iOrig.meta) { a.meta += v; a.temMeta = true; }
  }
  const der = (a) => a && Object.assign(a, {
    lb: a.rl + a.cmv,
    mb: a.rl ? (a.rl + a.cmv) / a.rl : null,
    lbp: a.rl - a.cmvp,
    mbp: a.rl ? (a.rl - a.cmvp) / a.rl : null,
    perdaPct: a.rl ? a.perda / a.rl : null,
    ml: a.rl ? a.res / a.rl : null,
    pm: a.q ? a.fat / a.q : null,
  });

  /* Agrega a fato numa máscara de dias, agrupando por chave(s).
     chaves: função (i) => array de chaves (caminho) ou null para ignorar a linha. */
  function agregar(mascara, chaveFn, filtroLinha) {
    const raiz = { a: novo(), filhos: new Map() };
    for (let i = 0; i < N; i++) {
      const k = F.d[i] - BASE;
      if (k < 0 || k >= TAM || !mascara[k]) continue;
      if (F.loja[i] >= 0 ? !ctx.lojaOk[F.loja[i]] : !ctx.todas) continue;
      if (filtroLinha && !filtroLinha(i)) continue;
      soma(raiz.a, i);
      if (!chaveFn) continue;
      const caminho = chaveFn(i);
      if (!caminho) continue;
      let no = raiz;
      for (const c of caminho) {
        let f = no.filhos.get(c);
        if (!f) { f = { a: novo(), filhos: new Map() }; no.filhos.set(c, f); }
        soma(f.a, i); no = f;
      }
    }
    return raiz;
  }

  function mascaraIntervalo(ini, fim) {
    const m = new Uint8Array(TAM);
    for (let d = Math.max(ini, BASE); d <= fim && d - BASE < TAM; d++) m[d - BASE] = 1;
    return m;
  }

  // Orçamento (vw_orcamento_dia) na máscara, por chave
  function orcamento(mascara, chaveFn) {
    const tot = new Map();
    for (let i = 0; i < O.d.length; i++) {
      const k = O.d[i] - BASE;
      if (k < 0 || k >= TAM || !mascara[k]) continue;
      if (O.loja[i] >= 0 ? !ctx.lojaOk[O.loja[i]] : !ctx.todas) continue;
      const ch = chaveFn ? chaveFn(i) : "_";
      if (ch === null) continue;
      let o = tot.get(ch);
      if (!o) { o = { rl: 0, lb: 0, despOp: 0, desp: 0, res: 0, g: {} }; tot.set(ch, o); }
      const v = O.v[i], nat = O.natureza[i], grp = O.grupo_dre[i];
      if (nat === iNat.rec) o.rl += v;
      if (nat === iNat.rec || nat === iNat.custo) o.lb += v;
      if (nat === iNat.desp) { o.desp += v; if (!fora.includes(grp)) o.despOp += v; }
      o.res += v;
      o.g[grp] = (o.g[grp] || 0) + v;
    }
    return tot;
  }

  window.Motor = {
    D, dic, F, O, estado, lojas, recalcular, agregar, orcamento, der, novo,
    ctx: () => ctx, BASE, TAM, ultimaVenda, anoMin, anoMax,
    ymd, dayOf, diasNoMes, toDate, mascaraIntervalo, iGrp, iNat, iOrig, fora,
    grupoIdx: (nome) => idx("grupo_dre", nome),
  };
})();
