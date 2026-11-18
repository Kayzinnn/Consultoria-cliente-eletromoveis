/* Páginas do BI: Resumo, Vendas, Atingir Meta, DRE e DRE do mês. */
(function () {
  const M = window.Motor;
  if (!M) return;
  const $ = (s, el = document) => el.querySelector(s);
  const h = (tag, attrs = {}, html = "") => { const e = document.createElement(tag); for (const k in attrs) e.setAttribute(k, attrs[k]); e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const MES_NOME = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

  // ---------- formatos ----------
  const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const vazio = (v) => v === null || v === undefined || Number.isNaN(v) || !Number.isFinite(v);
  const brl = (v) => vazio(v) ? "" : (v < 0 ? "-R$ " : "R$ ") + nf0.format(Math.abs(v));
  const brlC = (v) => {
    if (vazio(v)) return "—";
    const s = v < 0 ? "-" : "", y = Math.abs(v);
    if (y >= 1e6) return `${s}R$ ${nf2.format(y / 1e6)} mi`;
    if (y >= 1e4) return `${s}R$ ${nf0.format(y / 1e3)} mil`;
    if (y >= 1e3) return `${s}R$ ${nf1.format(y / 1e3)} mil`;
    return `${s}R$ ${nf0.format(y)}`;
  };
  const pct = (v) => vazio(v) ? "" : nf1.format(v * 100) + "%";
  const pctS = (v) => vazio(v) ? "" : (v > 0 ? "+" : "") + nf1.format(v * 100) + "%";
  const num = (v) => vazio(v) ? "" : nf0.format(v);
  const dataBR = (d) => { if (d === null) return ""; const [y, m, dd] = M.ymd(d); return `${String(dd).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`; };
  const div = (a, b) => (b ? a / b : null);

  // ---------- estado da tela ----------
  const ui = {
    pagina: "resumo",
    visaoDre: "Realizado",
    visoesMes: new Set(["Realizado", "Meta", "Meta mês cheio", "Desvio R$", "Desvio %"]),
    niveis: ["grupo_produto", "categoria_produto", "descricao"],
    aberto: { vendas: new Set(), dre: new Set(), dremes: new Set() },
  };
  try { const s = JSON.parse(localStorage.getItem("bi_ui") || "{}"); if (s.niveis) ui.niveis = s.niveis; if (s.visaoDre) ui.visaoDre = s.visaoDre; } catch (e) { /* sem armazenamento */ }
  const salvarUi = () => { try { localStorage.setItem("bi_ui", JSON.stringify({ niveis: ui.niveis, visaoDre: ui.visaoDre })); } catch (e) { /* ok */ } };

  let graficos = [];
  const novoGrafico = (el) => { const g = echarts.init(el, null, { renderer: "svg" }); graficos.push(g); return g; };
  window.addEventListener("resize", () => graficos.forEach((g) => g.resize()));

  // ---------- filtros ----------
  function filtro(rotulo, opcoes, sel, destaque, aoMudar, unico) {
    const wrap = h("div", { class: "filtro" + (destaque ? " destaque" : "") });
    const todos = sel.size === opcoes.length;
    const nomes = opcoes.filter((o) => sel.has(o.v)).map((o) => o.t);
    const resumo = todos ? (opcoes.length > 1 ? "Todos" : nomes[0]) : nomes.length === 0 ? "Nenhum" : nomes.length <= 2 ? nomes.join(", ") : `${nomes.length} selecionados`;
    const bt = h("button", { type: "button" }, `<small>${rotulo}</small><b>${esc(resumo)}</b>`);
    wrap.appendChild(bt);
    bt.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const aberto = wrap.querySelector(".menu");
      document.querySelectorAll(".menu").forEach((m) => m.remove());
      if (aberto) return;
      const menu = h("div", { class: "menu" });
      if (!unico) {
        const ac = h("div", { class: "acoes" }, `<button data-a="t">Selecionar todos</button>`);
        ac.addEventListener("click", (e) => {
          if (!e.target.dataset.a) return;
          opcoes.forEach((o) => sel.add(o.v)); aoMudar(true);
        });
        menu.appendChild(ac);
      }
      opcoes.forEach((o) => {
        const lb = h("label", {}, `<input type="${unico ? "radio" : "checkbox"}" ${sel.has(o.v) ? "checked" : ""}> ${esc(o.t)}`);
        lb.querySelector("input").addEventListener("change", (e) => {
          if (unico) { sel.clear(); sel.add(o.v); }
          else if (e.target.checked) sel.add(o.v); else sel.delete(o.v);
          if (sel.size === 0) { sel.add(o.v); e.target.checked = true; return; }
          aoMudar(true);
        });
        menu.appendChild(lb);
      });
      menu.addEventListener("click", (e) => e.stopPropagation());
      wrap.appendChild(menu);
    });
    return wrap;
  }
  document.addEventListener("click", () => { if (document.querySelector(".menu")) { document.querySelectorAll(".menu").forEach((m) => m.remove()); } });

  function desenharFiltros() {
    const box = $("#filtros"); box.innerHTML = "";
    const anos = []; for (let y = M.anoMax; y >= M.anoMin; y--) anos.push({ v: y, t: String(y) });
    const meses = MES_NOME.map((t, i) => ({ v: i + 1, t: t[0].toUpperCase() + t.slice(1) }));
    const lojas = M.lojas.map((l) => ({ v: l.i, t: l.nome })).sort((a, b) => a.t.localeCompare(b.t));
    const mudar = (manter) => { atualizar(manter); };
    box.appendChild(filtro("Ano", anos, M.estado.anos, true, mudar));
    box.appendChild(filtro("Filial", lojas, M.estado.lojas, false, mudar));
    box.appendChild(filtro("Mês", meses, M.estado.meses, false, mudar));
  }

  // ---------- textos do período ----------
  function rotuloPeriodo(c) {
    if (c.ref === null) return "";
    const lista = [...c.nMeses].sort((a, b) => a - b);
    const ym = (k) => `${MES[k % 100 - 1]}/${String(Math.floor(k / 100)).slice(2)}`;
    let cont = true; for (let i = 1; i < lista.length; i++) { const a = lista[i - 1], b = lista[i]; const prox = a % 100 === 12 ? (Math.floor(a / 100) + 1) * 100 + 1 : a + 1; if (b !== prox) cont = false; }
    if (lista.length === 1) return `${MES_NOME[lista[0] % 100 - 1]}/${Math.floor(lista[0] / 100)}`;
    return cont ? `${ym(lista[0])} a ${ym(lista[lista.length - 1])}` : `${lista.length} meses selecionados`;
  }
  const rotuloAnoAnterior = (c) => { if (c.ref === null) return ""; const anos = [...new Set([...c.nMeses].map((k) => Math.floor(k / 100) - 1))]; return `o mesmo período de ${anos.join(" e ")}`; };

  // ---------- cards ----------
  function selo(d, bom, formato, minimo) {
    if (d === null) return `<span class="selo neutro">sem comparação</span>`;
    if (Math.abs(d) < (minimo || 0)) return `<span class="selo neutro">= estável</span>`;
    const seta = d >= 0 ? "&#8599;" : "&#8600;";
    return `<span class="selo ${bom ? "bom" : "ruim"}">${seta} ${formato(Math.abs(d))}</span>`;
  }
  function card(titulo, valor, d, bom, formato, texto) {
    return `<div class="card"><h3>${titulo}</h3><div class="valor">${valor}</div><div class="rodape">${d === undefined ? "" : selo(d, bom, formato, formato.minimo)}<span class="texto">${texto}</span></div></div>`;
  }
  function desenharCards(c, a, py) {
    const el = $("#cards");
    if (c.ref === null) { el.innerHTML = ""; return; }
    const lbl = rotuloAnoAnterior(c);
    const varPct = (x, y) => (vazio(x) || vazio(y) || !y ? null : (x - y) / Math.abs(y));
    const varPp = (x, y) => (vazio(x) || vazio(y) || !y ? null : (x - y) * 100);
    const fP = (v) => pct(v), fPp = (v) => `${nf1.format(v)} ${v < 2 ? "ponto" : "pontos"}`;
    fP.minimo = 0.0005; fPp.minimo = 0.05;
    const dV = varPct(a.rl, py.rl), dG = varPp(a.mb, py.mb), dPe = varPp(a.perdaPct, py.perdaPct), dD = varPct(-a.desp, -py.desp), dL = varPct(a.res, py.res);
    el.innerHTML =
      card("Vendas", brlC(a.rl), dV, dV >= 0, fP, dV === null ? "sem dados do ano anterior" : `${dV >= 0 ? "a mais que" : "a menos que"} ${lbl}`) +
      card("Ganho na venda", pct(a.mb), dG, dG >= 0, fPp, dG === null ? "sobra após pagar os produtos" : `vs ${lbl}`) +
      card("Perdas", brlC(a.perda), dPe, dPe <= 0, fPp, `${pct(a.perdaPct)} das vendas · ${dPe === null ? "trocas e devoluções" : "vs " + lbl}`) +
      card("Despesas da loja", brlC(-a.desp), dD, dD <= 0, fP, dD === null ? "aluguel, salários e contas" : `${dD >= 0 ? "a mais que" : "a menos que"} ${lbl}`) +
      card("Lucro", brlC(a.res), dL, dL >= 0, fP, dL === null ? `${pct(a.ml)} de margem sobre as vendas` : `${pct(a.ml)} de margem · ${dL >= 0 ? "a mais que" : "a menos que"} ${lbl}`) +
      card("Estoque", "—", null, true, fP, "aguardando a base de estoque");
  }

  // ---------- RESUMO ----------
  function paginaResumo(c, a) {
    const pg = $("#pagina");
    pg.innerHTML = `
      <div class="grade g-2">
        <div class="bloco"><h2>Vendas e lucro nos últimos 12 meses</h2><p class="sub">Até ${dataBR(M.ultimaVenda)} · não muda com o filtro de mês</p><div class="grafico" id="g12"></div></div>
        <div class="bloco"><h2>Para onde vai o dinheiro</h2><p class="sub">Do total vendido até o lucro (em R$ mil)</p><div class="grafico" id="gcasc"></div></div>
      </div>
      <div class="bloco mt"><h2>Desempenho por filial</h2><p class="sub">Da filial que mais vende para a que menos vende · <span class="alerta"></span> perda acima de 2% das vendas</p><div class="rolagem" id="tfil"></div></div>`;

    // 12 meses
    const [uy, um] = M.ymd(M.ultimaVenda);
    const meses = []; for (let k = 11; k >= 0; k--) { let y = uy, m = um - k; while (m < 1) { m += 12; y--; } meses.push([y, m]); }
    const ini = M.dayOf(meses[0][0], meses[0][1], 1);
    const r12 = M.agregar(M.mascaraIntervalo(ini, M.ultimaVenda), (i) => { const [y, m] = M.ymd(M.F.d[i]); return [y * 100 + m]; });
    const v12 = meses.map(([y, m]) => r12.filhos.get(y * 100 + m)?.a || M.novo());
    const g = novoGrafico($("#g12"));
    g.setOption({
      textStyle: { fontFamily: "Manrope" },
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      legend: { top: 0, right: 0, icon: "roundRect", itemWidth: 12, itemHeight: 12, textStyle: { color: "#4B5563", fontWeight: 600 } },
      tooltip: { trigger: "axis", valueFormatter: (v) => brl(v) },
      xAxis: { type: "category", data: meses.map(([y, m]) => `${MES[m - 1]}/${String(y).slice(2)}`), axisLine: { lineStyle: { color: "#E6E8EF" } }, axisTick: { show: false }, axisLabel: { color: "#6B7280" } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#F0F1F5" } }, axisLabel: { color: "#9CA3AF", formatter: (v) => nf0.format(v / 1000) + " mil" } },
      series: [
        { name: "Vendas", type: "bar", data: v12.map((x) => Math.round(x.rl)), itemStyle: { color: "#4F6BED", borderRadius: [6, 6, 0, 0] }, barMaxWidth: 26 },
        { name: "Lucro", type: "bar", data: v12.map((x) => Math.round(x.res)), itemStyle: { color: "#1B2440", borderRadius: [6, 6, 0, 0] }, barMaxWidth: 26 },
      ],
    });

    // cascata por agrupamento
    const grpInfo = {}; M.D.grupos_dre.forEach((x) => (grpInfo[M.grupoIdx(x.grupo_dre)] = x));
    const porAg = new Map();
    for (const gi in a.g) {
      const info = grpInfo[gi] || { agrupamento: M.dic.grupo_dre[gi], ordem_agrupamento: 999 };
      const k = info.agrupamento || M.dic.grupo_dre[gi];
      const o = porAg.get(k) || { v: 0, ordem: info.ordem_agrupamento ?? 999 };
      o.v += a.g[gi]; porAg.set(k, o);
    }
    const itens = [...porAg.entries()].filter(([, o]) => Math.abs(o.v) >= 1).sort((x, y) => x[1].ordem - y[1].ordem);
    let acum = 0; const base = [], val = [], cores = [], nomes = [];
    itens.forEach(([k, o]) => {
      const v = o.v / 1000; nomes.push(k);
      if (v >= 0) { base.push(acum); val.push(v); cores.push("#4F6BED"); acum += v; }
      else { acum += v; base.push(acum); val.push(-v); cores.push("#E8A47C"); }
    });
    nomes.push("Lucro"); base.push(Math.min(0, acum)); val.push(Math.abs(acum)); cores.push(acum >= 0 ? "#15803D" : "#B91C1C");
    const gc = novoGrafico($("#gcasc"));
    gc.setOption({
      textStyle: { fontFamily: "Manrope" },
      grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (p) => { const i = p[0].dataIndex; const sinal = cores[i] === "#E8A47C" ? -1 : 1; return `${esc(nomes[i])}<br><b>${brl(sinal * val[i] * 1000 * (i === nomes.length - 1 ? Math.sign(acum) || 1 : 1))}</b>`; } },
      yAxis: { type: "category", inverse: true, data: nomes, axisTick: { show: false }, axisLine: { lineStyle: { color: "#E6E8EF" } }, axisLabel: { color: "#374151", fontWeight: 600, fontSize: 12 } },
      xAxis: { type: "value", splitLine: { lineStyle: { color: "#F0F1F5" } }, axisLabel: { color: "#9CA3AF", formatter: (v) => nf0.format(v) } },
      series: [
        { type: "bar", stack: "t", data: base, itemStyle: { color: "transparent" }, emphasis: { disabled: true }, tooltip: { show: false } },
        { type: "bar", stack: "t", data: val.map((v, i) => ({ value: v, itemStyle: { color: cores[i], borderRadius: 4 } })), barMaxWidth: 22,
          label: { show: true, position: "right", color: "#374151", fontWeight: 700, fontSize: 11, formatter: (p) => nf0.format(cores[p.dataIndex] === "#E8A47C" ? -p.value : p.value) } },
      ],
    });

    // tabela por filial
    const porLoja = M.agregar(c.P, (i) => [M.F.loja[i]]);
    const porLojaPY = M.agregar(c.PY, (i) => [M.F.loja[i]]);
    const linhas = [...porLoja.filhos.entries()].filter(([k]) => k >= 0).map(([k, n]) => ({ nome: M.dic.loja[k], a: M.der(n.a), py: M.der(porLojaPY.filhos.get(k)?.a || null) }))
      .filter((x) => x.a.rl || x.a.res).sort((x, y) => y.a.rl - x.a.rl);
    const max = Math.max(1, ...linhas.map((x) => x.a.rl));
    const varV = (x, y) => (y && y.rl ? (x.rl - y.rl) / Math.abs(y.rl) : null);
    const lin = (nome, x, y, cls = "") => {
      const v = varV(x, y);
      return `<tr class="${cls}"><td>${esc(nome)}${x.perdaPct > 0.02 ? '<span class="alerta" title="Perda acima de 2% das vendas"></span>' : ""}</td>
        <td>${brl(x.rl)}${cls ? "" : `<span class="barra"><span style="width:${(100 * x.rl) / max}%"></span></span>`}</td>
        <td class="${v === null ? "" : v >= 0 ? "var-up" : "var-down"}">${v === null ? "—" : pctS(v)}</td>
        <td>${pct(x.mb)}</td><td>${brl(x.perda)}</td><td>${brl(-x.desp)}</td>
        <td class="${x.res >= 0 ? "pos" : "neg"}">${brl(x.res)}</td><td>${pct(x.ml)}</td></tr>`;
    };
    $("#tfil").innerHTML = `<table><thead><tr><th>Filial</th><th>Vendas</th><th>vs ano anterior</th><th>Ganho na venda</th><th>Perdas</th><th>Despesas da loja</th><th>Lucro</th><th>Margem</th></tr></thead>
      <tbody>${linhas.map((x) => lin(x.nome, x.a, x.py)).join("")}${lin("Total", a, M.der(M.agregar(c.PY).a), "total")}</tbody></table>`;
  }

  // ---------- VENDAS ----------
  const NIVEIS = { grupo_produto: "Grupo", categoria_produto: "Categoria", descricao: "Produto", loja: "Filial" };
  function paginaVendas(c, a) {
    const pg = $("#pagina");
    const chips = Object.keys(NIVEIS).map((k) => { const pos = ui.niveis.indexOf(k); return `<button data-n="${k}" class="${pos >= 0 ? "on" : ""}">${pos >= 0 ? pos + 1 + ". " : ""}${NIVEIS[k]}</button>`; }).join("");
    pg.innerHTML = `<div class="bloco">
      <div class="bloco-topo"><div><h2>Vendas por ${ui.niveis.map((n) => NIVEIS[n].toLowerCase()).join(" › ")}</h2><p class="sub" style="margin:0">Clique nas linhas para abrir · clique em "Abrir por" para escolher a ordem dos níveis</p></div>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span class="sub" style="margin:0;font-weight:700">Abrir por</span><div class="chips" id="niveis">${chips}</div>
      <div class="chips"><button id="exp">Abrir 1º nível</button><button id="rec">Recolher</button></div></div></div>
      <div class="rolagem alta" id="mv"></div></div>`;
    $("#niveis").addEventListener("click", (e) => {
      const n = e.target.closest("button")?.dataset.n; if (!n) return;
      const i = ui.niveis.indexOf(n);
      if (i >= 0) { if (ui.niveis.length > 1) ui.niveis.splice(i, 1); } else ui.niveis.push(n);
      ui.aberto.vendas.clear(); salvarUi(); paginaVendas(c, a);
    });
    const ehVenda = (i) => M.F.origem[i] === M.iOrig.erp;
    const caminho = (i) => ui.niveis.map((n) => M.F[n][i]);
    const arv = M.agregar(c.P, caminho, ehVenda);
    const arvPY = M.agregar(c.PY, caminho, ehVenda);
    $("#exp").onclick = () => { arv.filhos.forEach((_, k) => ui.aberto.vendas.add(String(k))); render(); };
    $("#rec").onclick = () => { ui.aberto.vendas.clear(); render(); };
    const total = M.der(arv.a);
    const colunas = ["Qtd", "Receita bruta", "Descontos", "Vendas", "Part.", "vs ano ant.", "Custo produtos", "Ganho na venda", "Margem", "Preço médio", "Última venda"];
    const celulas = (x, y) => {
      M.der(x); const v = y && y.a.rl ? (x.rl - y.a.rl) / Math.abs(y.a.rl) : null;
      return `<td>${num(x.q)}</td><td>${brl(x.fat)}</td><td>${brl(x.desc)}</td><td><b>${brl(x.rl)}</b></td><td>${pct(div(x.rl, total.rl))}</td>
        <td class="${v === null ? "" : v >= 0 ? "var-up" : "var-down"}">${v === null ? "—" : pctS(v)}</td><td>${brl(x.cmvp)}</td><td>${brl(x.lbp)}</td><td>${pct(x.mbp)}</td><td>${brl(x.pm)}</td><td>${dataBR(x.ult)}</td>`;
    };
    function render() {
      const linhas = [];
      const percorrer = (no, noPY, nivel, chave) => {
        const filhos = [...no.filhos.entries()].sort((p, q) => q[1].a.rl - p[1].a.rl);
        const limite = 300;
        filhos.slice(0, limite).forEach(([k, f]) => {
          const ch = chave + "|" + k, temFilhos = nivel < ui.niveis.length - 1, ab = ui.aberto.vendas.has(ch);
          const nome = k >= 0 ? M.dic[ui.niveis[nivel]][k] : "(sem informação)";
          linhas.push(`<tr class="n${nivel}" data-k="${esc(ch)}"><td title="${esc(nome)}">${temFilhos ? `<span class="abrir"><i>${ab ? "▾" : "▸"}</i>${esc(nome)}</span>` : `<span class="abrir"><i></i>${esc(nome)}</span>`}</td>${celulas(f.a, noPY?.filhos.get(k))}</tr>`);
          if (temFilhos && ab) percorrer(f, noPY?.filhos.get(k), nivel + 1, ch);
        });
        if (filhos.length > limite) linhas.push(`<tr class="n${nivel}"><td colspan="12" style="color:#6B7280">+ ${filhos.length - limite} itens menores</td></tr>`);
      };
      percorrer(arv, arvPY, 0, "");
      $("#mv").innerHTML = arv.filhos.size === 0 ? `<div class="vazio">Sem vendas no período selecionado</div>` :
        `<table><thead><tr><th>${ui.niveis.map((n) => NIVEIS[n]).join(" › ")}</th>${colunas.map((x) => `<th>${x}</th>`).join("")}</tr></thead>
        <tbody>${linhas.join("")}<tr class="total"><td>Total</td>${celulas(arv.a, arvPY)}</tr></tbody></table>`;
    }
    $("#mv").addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-k]"); if (!tr || !tr.querySelector(".abrir i")?.textContent) return;
      const k = tr.dataset.k; ui.aberto.vendas.has(k) ? ui.aberto.vendas.delete(k) : ui.aberto.vendas.add(k); render();
    });
    render();
  }

  // ---------- ATINGIR META ----------
  function paginaMeta(c) {
    const pg = $("#pagina");
    if (c.ref === null) { pg.innerHTML = `<div class="bloco vazio">Sem vendas no período selecionado</div>`; return; }
    const [y, m, d] = M.ymd(c.ref); const dm = M.diasNoMes(y, m);
    const ini = M.dayOf(y, m, 1), fim = M.dayOf(y, m, dm);
    const metas = M.agregar(M.mascaraIntervalo(ini, fim), (i) => [M.F.loja[i]], (i) => M.F.origem[i] === M.iOrig.meta);
    const vend = M.agregar(M.mascaraIntervalo(ini, c.ref), (i) => [M.F.loja[i]], (i) => M.F.natureza[i] === M.iNat.rec);
    const linhas = [];
    metas.filhos.forEach((n, k) => { if (k >= 0 && n.a.temMeta) linhas.push({ nome: M.dic.loja[k], meta: n.a.meta, vendido: vend.filhos.get(k)?.a.rl || 0 }); });
    linhas.sort((p, q) => q.meta - p.meta);
    const tot = { nome: "Total", meta: linhas.reduce((s, x) => s + x.meta, 0), vendido: linhas.reduce((s, x) => s + x.vendido, 0) };
    const calc = (x) => Object.assign(x, { ritmo: (x.vendido / d) * dm, ating: div(x.vendido, x.meta) }, { desvio: (x.vendido / d) * dm - x.meta });
    linhas.forEach(calc); calc(tot);
    pg.innerHTML = `<div class="bloco">
      <h2 class="titulo-secao">Ritmo de vendas de ${MES_NOME[m - 1]}</h2>
      <p class="sub">Vendas realizadas até ${dataBR(c.ref).slice(0, 5)} &nbsp;|&nbsp; Projeção para ${dm} dias, no ritmo atual</p>
      ${linhas.length === 0 ? `<div class="vazio">Sem meta cadastrada para ${MES_NOME[m - 1]}/${y} (config/metas_vendas.csv)</div>` : `
      <div class="grafico" id="gmeta" style="height:${Math.max(220, 64 * linhas.length + 60)}px"></div>
      <div class="rolagem mt"><table><thead><tr><th>Filial</th><th>Meta do mês</th><th>Vendido até ${dataBR(c.ref).slice(0, 5)}</th><th>% da meta</th><th>Ritmo projetado</th><th>Desvio do ritmo</th></tr></thead><tbody>
      ${[...linhas, tot].map((x) => `<tr class="${x === tot ? "total" : ""}"><td>${esc(x.nome)}</td><td>${brl(x.meta)}</td><td>${brl(x.vendido)}</td>
        <td>${pct(x.ating)} <span class="progresso"><span style="width:${Math.min(100, 100 * (x.ating || 0))}%;background:${x.desvio >= 0 ? "#15803D" : "#4F6BED"}"></span></span></td>
        <td>${brl(x.ritmo)}</td><td><span class="meta-faixa ${x.desvio >= 0 ? "ok" : "nao"}">${x.desvio >= 0 ? "+ " : "- "}${brl(Math.abs(x.desvio))} (${pctS(div(x.desvio, x.meta))})</span></td></tr>`).join("")}
      </tbody></table></div>`}</div>`;
    if (!linhas.length) return;
    const g = novoGrafico($("#gmeta"));
    const nomes = linhas.map((x) => x.nome).reverse(), L = [...linhas].reverse();
    g.setOption({
      textStyle: { fontFamily: "Manrope" },
      grid: { left: 8, right: 40, top: 30, bottom: 8, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: "#4B5563", fontWeight: 600 } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => brl(v) },
      xAxis: { type: "value", splitLine: { lineStyle: { color: "#F0F1F5" } }, axisLabel: { color: "#9CA3AF", formatter: (v) => nf0.format(v / 1000) + " mil" } },
      yAxis: { type: "category", data: nomes, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: "#111827", fontWeight: 700 } },
      series: [
        { name: "Ritmo projetado", type: "bar", itemStyle: { color: "#BBF7D0" }, data: L.map((x) => ({ value: Math.round(x.ritmo), itemStyle: { color: x.desvio >= 0 ? "#BBF7D0" : "#FED7AA", borderRadius: 6 } })), barGap: "-100%", barWidth: 26 },
        { name: "Vendido", type: "bar", data: L.map((x) => Math.round(x.vendido)), itemStyle: { color: "#4F6BED", borderRadius: 6 }, barWidth: 26 },
        { name: "Meta", type: "scatter", symbol: "rect", symbolSize: [4, 38], data: L.map((x) => Math.round(x.meta)), itemStyle: { color: "#1B2440" }, z: 5 },
      ],
    });
  }

  // ---------- DRE ----------
  const LINHAS = [
    [10, "Receita bruta de vendas", "grupo", "Receita bruta de vendas"], [20, "(±) Descontos e acréscimos", "grupo", "Descontos e acréscimos"],
    [30, "Outras receitas", "grupo", "Outras receitas"], [40, "(=) RECEITA LÍQUIDA", "receita_liquida"],
    [50, "(-) Custo da mercadoria vendida", "grupo", "Custo da mercadoria vendida"], [60, "(=) LUCRO BRUTO", "lucro_bruto"],
    [65, "Margem bruta %", "margem_bruta"], [70, "(-) Despesas com pessoal", "grupo", "Despesas com pessoal"],
    [75, "(-) Despesas de ocupação", "grupo", "Despesas de ocupação"], [80, "(-) Despesas logísticas", "grupo", "Despesas logísticas"],
    [85, "(-) Despesas administrativas", "grupo", "Despesas administrativas"], [90, "(-) Despesas a classificar", "grupo", "A classificar"],
    [95, "(=) TOTAL DE DESPESAS OPERACIONAIS", "despesas_op"], [100, "(=) RESULTADO OPERACIONAL", "resultado_op"],
    [105, "Margem operacional %", "margem_operacional"], [110, "(-) Pró-labore", "grupo", "Pró-labore"],
    [115, "(-) Impostos", "grupo", "Impostos"], [120, "(-) Despesas financeiras", "grupo", "Despesas financeiras"],
    [130, "(=) LUCRO LÍQUIDO", "resultado"], [135, "Margem líquida %", "margem_liquida"],
  ].map(([ordem, nome, tipo, grupo]) => ({ ordem, nome, tipo, grupo, gi: grupo ? M.grupoIdx(grupo) : -1 }));
  const MARGENS = new Set(["margem_bruta", "margem_operacional", "margem_liquida"]);
  const SUBTOT = new Set(["receita_liquida", "lucro_bruto", "despesas_op"]);

  function valorReal(l, a) {
    if (!a) return null;
    const lb = a.rl + a.cmv, rop = lb + a.despOp;
    switch (l.tipo) {
      case "grupo": return a.g[l.gi] ?? null;
      case "receita_liquida": return a.rl;
      case "lucro_bruto": return lb;
      case "margem_bruta": return div(lb, a.rl);
      case "despesas_op": return a.despOp;
      case "resultado_op": return rop;
      case "margem_operacional": return div(rop, a.rl);
      case "resultado": return a.res;
      case "margem_liquida": return div(a.res, a.rl);
    }
    return null;
  }
  function valorOrc(l, o) {
    if (!o) return null;
    const rop = o.lb + o.despOp;
    switch (l.tipo) {
      case "grupo": return o.g[l.gi] ?? null;
      case "receita_liquida": return o.rl;
      case "lucro_bruto": return o.lb;
      case "margem_bruta": return div(o.lb, o.rl);
      case "despesas_op": return o.despOp;
      case "resultado_op": return rop;
      case "margem_operacional": return div(rop, o.rl);
      case "resultado": return o.res;
      case "margem_liquida": return div(o.res, o.rl);
    }
    return null;
  }
  // valor de uma linha numa visão
  function visao(v, l, a, o, oCheio, aDesv) {
    const real = valorReal(l, v.startsWith("Desvio") && aDesv !== undefined ? aDesv : a), orc = valorOrc(l, o);
    switch (v) {
      case "Realizado": return { v: real };
      case "Meta": return { v: orc };
      case "Meta mês cheio": return { v: valorOrc(l, oCheio) };
      case "Desvio R$": return { v: orc === null ? null : (real ?? 0) - orc, desvio: true };
      case "Desvio %": return MARGENS.has(l.tipo) || orc === null || !orc ? { v: null } : { v: ((real ?? 0) - orc) / Math.abs(orc), pctDesvio: true };
    }
  }
  function fmtCel(l, r) {
    if (vazio(r.v)) return "<td></td>";
    if (r.pctDesvio) return `<td class="${r.v >= 0 ? "pos" : "neg"}">${pctS(r.v)}</td>`;
    if (MARGENS.has(l.tipo)) return r.desvio ? `<td class="${r.v >= 0 ? "pos" : "neg"}">${(r.v >= 0 ? "+" : "") + nf1.format(r.v * 100)} p.p.</td>` : `<td>${pct(r.v)}</td>`;
    if (r.desvio) return `<td class="${r.v >= 0 ? "pos" : "neg"}">${brl(r.v)}</td>`;
    if (l.tipo === "resultado" || l.tipo === "resultado_op") return `<td class="${r.v >= 0 ? "pos" : "neg"}">${brl(r.v)}</td>`;
    return `<td>${brl(r.v)}</td>`;
  }
  const classeLinha = (l) => (MARGENS.has(l.tipo) ? "margem" : SUBTOT.has(l.tipo) ? "sub" : l.tipo === "resultado" || l.tipo === "resultado_op" ? "sub resultado" : "");

  // Meses do período que têm orçamento: o desvio compara o real só desses meses.
  function mesesComMeta(c) {
    const ym = new Set(), m = new Uint8Array(M.TAM);
    for (let i = 0; i < M.O.d.length; i++) { const k = M.O.d[i] - M.BASE; if (k >= 0 && k < M.TAM && c.P[k]) { const [y, mm] = M.ymd(M.O.d[i]); ym.add(y * 100 + mm); } }
    for (let k = 0; k < M.TAM; k++) if (c.P[k]) { const [y, mm] = M.ymd(k + M.BASE); if (ym.has(y * 100 + mm)) m[k] = 1; }
    return { ym, mascara: m };
  }
  const notaMeta = (c, mm) => {
    if (mm.ym.size === 0) return " · sem meta cadastrada no período";
    if (mm.ym.size === c.nMeses.size) return "";
    return " · meta e desvio só nos meses com meta: " + [...mm.ym].sort().map((k) => `${MES[k % 100 - 1]}/${String(Math.floor(k / 100)).slice(2)}`).join(", ");
  };

  function tituloMeta(c) {
    if (c.ref === null) return "Sem vendas no período selecionado";
    const mes = c.nMeses.size === 1 ? "em " + MES_NOME[[...c.nMeses][0] % 100 - 1] : "no período selecionado";
    return `O que aconteceu ${mes} comparado com a meta`;
  }

  // DRE por mês (colunas = meses, uma visão)
  function paginaDre(c) {
    const pg = $("#pagina");
    const VIS = ["Realizado", "Meta", "Meta mês cheio", "Desvio R$", "Desvio %"];
    pg.innerHTML = `<div class="bloco"><div class="bloco-topo"><div><h2>${ui.visaoDre === "Realizado" ? "Resultado mês a mês" : tituloMeta(c)}</h2>
      <p class="sub" style="margin:0">Clique numa linha para abrir por filial · Visão: ${ui.visaoDre}</p></div>
      <div class="chips" id="vis">${VIS.map((v) => `<button class="${v === ui.visaoDre ? "on" : ""}">${v}</button>`).join("")}</div></div>
      <div class="rolagem alta" id="tdre"></div></div>`;
    $("#vis").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; ui.visaoDre = b.textContent; salvarUi(); paginaDre(c); });
    if (c.ref === null) { $("#tdre").innerHTML = `<div class="vazio">Sem vendas no período selecionado</div>`; return; }
    const ymOf = (d) => { const [y, m] = M.ymd(d); return y * 100 + m; };
    const real = M.agregar(c.P, (i) => [ymOf(M.F.d[i]), M.F.loja[i]]);
    const realLoja = M.agregar(c.P, (i) => [M.F.loja[i]]);
    const mm = mesesComMeta(c), realMeta = M.agregar(mm.mascara, (i) => [M.F.loja[i]]);
    if (ui.visaoDre !== "Realizado") $("#pagina .sub").textContent += notaMeta(c, mm);
    const orcP = M.orcamento(c.P, (i) => ymOf(M.O.d[i]) + "|" + M.O.loja[i]);
    const orcC = M.orcamento(c.cal, (i) => ymOf(M.O.d[i]) + "|" + M.O.loja[i]);
    const somaOrc = (mapa, ym, loja) => {
      let o = null;
      mapa.forEach((x, k) => {
        const [a, b] = k.split("|").map(Number);
        if ((ym === null || a === ym) && (loja === null || b === loja)) {
          if (!o) o = { rl: 0, lb: 0, despOp: 0, desp: 0, res: 0, g: {} };
          o.rl += x.rl; o.lb += x.lb; o.despOp += x.despOp; o.desp += x.desp; o.res += x.res;
          for (const gi in x.g) o.g[gi] = (o.g[gi] || 0) + x.g[gi];
        }
      });
      return o;
    };
    const meses = [...c.nMeses].sort((a, b) => a - b);
    const lojas = [...realLoja.filhos.entries()].filter(([k]) => k >= 0).sort((p, q) => q[1].a.rl - p[1].a.rl).map(([k]) => k);
    const celulas = (l, loja) => {
      const cols = meses.map((ym) => {
        const a = loja === null ? real.filhos.get(ym)?.a : real.filhos.get(ym)?.filhos.get(loja)?.a;
        return fmtCel(l, visao(ui.visaoDre, l, a, somaOrc(orcP, ym, loja), somaOrc(orcC, ym, loja)));
      });
      const aT = loja === null ? real.a : realLoja.filhos.get(loja)?.a;
      const aD = loja === null ? realMeta.a : realMeta.filhos.get(loja)?.a || null;
      cols.push(fmtCel(l, visao(ui.visaoDre, l, aT, somaOrc(orcP, null, loja), somaOrc(orcC, null, loja), aD)).replace("<td", '<td style="font-weight:800;background:#F7F8FB"'));
      return cols.join("");
    };
    const render = () => {
      const rows = [];
      LINHAS.forEach((l) => {
        const ab = ui.aberto.dre.has(l.ordem);
        rows.push(`<tr class="${classeLinha(l)}" data-o="${l.ordem}"><td><span class="abrir"><i>${ab ? "▾" : "▸"}</i>${esc(l.nome)}</span></td>${celulas(l, null)}</tr>`);
        if (ab) lojas.forEach((lj) => rows.push(`<tr class="n1"><td>${esc(M.dic.loja[lj])}</td>${celulas(l, lj)}</tr>`));
      });
      $("#tdre").innerHTML = `<table><thead><tr><th>Linha da DRE</th>${meses.map((k) => `<th>${MES[k % 100 - 1]}/${String(Math.floor(k / 100)).slice(2)}</th>`).join("")}<th>Total</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
    };
    $("#tdre").addEventListener("click", (e) => { const tr = e.target.closest("tr[data-o]"); if (!tr) return; const o = +tr.dataset.o; ui.aberto.dre.has(o) ? ui.aberto.dre.delete(o) : ui.aberto.dre.add(o); render(); });
    render();
  }

  // DRE do período (colunas = visões), abre por filial e descrição
  function paginaDreMes(c) {
    const pg = $("#pagina");
    const VIS = ["Realizado", "Meta", "Meta mês cheio", "Desvio R$", "Desvio %"];
    pg.innerHTML = `<div class="bloco"><div class="bloco-topo"><div><h2>${tituloMeta(c)}</h2>
      <p class="sub" style="margin:0">Real × meta no período · clique para abrir por filial e por lançamento</p></div>
      <div class="chips" id="vis">${VIS.map((v) => `<button class="${ui.visoesMes.has(v) ? "on" : ""}">${v}</button>`).join("")}</div></div>
      <div class="rolagem alta" id="tdm"></div></div>`;
    $("#vis").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; const v = b.textContent; if (ui.visoesMes.has(v)) { if (ui.visoesMes.size > 1) ui.visoesMes.delete(v); } else ui.visoesMes.add(v); paginaDreMes(c); });
    if (c.ref === null) { $("#tdm").innerHTML = `<div class="vazio">Sem vendas no período selecionado</div>`; return; }
    const vis = VIS.filter((v) => ui.visoesMes.has(v));
    const realLoja = M.agregar(c.P, (i) => [M.F.loja[i]]);
    const mm = mesesComMeta(c), realMeta = M.agregar(mm.mascara, (i) => [M.F.loja[i]]);
    $("#pagina .sub").textContent += notaMeta(c, mm);
    const det = M.agregar(c.P, (i) => (M.F.dre[i] && M.F.grupo_dre[i] >= 0 ? [M.F.grupo_dre[i], M.F.loja[i], M.F.descricao[i]] : null));
    const orcP = M.orcamento(c.P, (i) => M.O.loja[i]), orcC = M.orcamento(c.cal, (i) => M.O.loja[i]);
    const tot = (mapa) => { let o = null; mapa.forEach((x) => { if (!o) o = { rl: 0, lb: 0, despOp: 0, desp: 0, res: 0, g: {} }; o.rl += x.rl; o.lb += x.lb; o.despOp += x.despOp; o.desp += x.desp; o.res += x.res; for (const gi in x.g) o.g[gi] = (o.g[gi] || 0) + x.g[gi]; }); return o; };
    const oP = tot(orcP), oC = tot(orcC);
    const lojas = [...realLoja.filhos.entries()].filter(([k]) => k >= 0).sort((p, q) => q[1].a.rl - p[1].a.rl).map(([k]) => k);
    const cel = (l, a, o, oc, ad) => vis.map((v) => fmtCel(l, visao(v, l, a, o, oc, ad))).join("");
    const render = () => {
      const rows = [];
      LINHAS.forEach((l) => {
        const ab = ui.aberto.dremes.has(String(l.ordem));
        rows.push(`<tr class="${classeLinha(l)}" data-k="${l.ordem}"><td><span class="abrir"><i>${ab ? "▾" : "▸"}</i>${esc(l.nome)}</span></td>${cel(l, realLoja.a, oP, oC, realMeta.a)}</tr>`);
        if (!ab) return;
        lojas.forEach((lj) => {
          const k2 = l.ordem + "|" + lj, ab2 = ui.aberto.dremes.has(k2), temDet = l.tipo === "grupo" && det.filhos.get(l.gi)?.filhos.get(lj);
          rows.push(`<tr class="n1" ${temDet ? `data-k="${k2}"` : ""}><td><span class="abrir"><i>${temDet ? (ab2 ? "▾" : "▸") : ""}</i>${esc(M.dic.loja[lj])}</span></td>${cel(l, realLoja.filhos.get(lj)?.a, orcP.get(lj), orcC.get(lj), realMeta.filhos.get(lj)?.a || null)}</tr>`);
          if (temDet && ab2) {
            const itens = [...temDet.filhos.entries()].sort((p, q) => Math.abs(q[1].a.res) - Math.abs(p[1].a.res));
            itens.slice(0, 200).forEach(([dk, n]) => {
              const nome = dk >= 0 ? M.dic.descricao[dk] : "(sem descrição)";
              rows.push(`<tr class="n2"><td title="${esc(nome)}">${esc(nome)}</td>${vis.map((v) => (v === "Realizado" ? `<td>${brl(n.a.res)}</td>` : "<td></td>")).join("")}</tr>`);
            });
            if (itens.length > 200) rows.push(`<tr class="n2"><td colspan="${vis.length + 1}" style="color:#6B7280">+ ${itens.length - 200} lançamentos menores</td></tr>`);
          }
        });
      });
      $("#tdm").innerHTML = `<table><thead><tr><th>Linha da DRE</th>${vis.map((v) => `<th>${v}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
    };
    $("#tdm").addEventListener("click", (e) => { const tr = e.target.closest("tr[data-k]"); if (!tr) return; const k = tr.dataset.k; ui.aberto.dremes.has(k) ? ui.aberto.dremes.delete(k) : ui.aberto.dremes.add(k); render(); });
    render();
  }

  // ---------- montagem ----------
  const PAGINAS = {
    resumo: ["Painel de Resultados", paginaResumo],
    vendas: ["Painel de Resultados – Vendas", paginaVendas],
    meta: ["Painel de Resultados – Atingir meta", paginaMeta],
    dre: ["Painel de Resultados – DRE mês a mês", paginaDre],
    dremes: ["Painel de Resultados – DRE real × meta", paginaDreMes],
  };

  function atualizar(manterMenu) {
    graficos.forEach((g) => g.dispose()); graficos = [];
    const c = M.recalcular();
    const a = M.der(M.agregar(c.P).a), py = M.der(M.agregar(c.PY).a);
    const [titulo, fn] = PAGINAS[ui.pagina];
    $("#titulo").textContent = titulo;
    $("#subtitulo").textContent = c.ref === null ? "Sem vendas no período selecionado" : `Período: ${rotuloPeriodo(c)} · vendas carregadas até ${dataBR(c.ref)}`;
    document.querySelectorAll("#nav a").forEach((x) => x.classList.toggle("ativo", x.dataset.pag === ui.pagina));
    if (!manterMenu) desenharFiltros(); else {
      // redesenha os botões, mantendo o menu aberto
      const aberto = document.querySelector(".filtro .menu")?.parentElement;
      const idx = aberto ? [...aberto.parentElement.children].indexOf(aberto) : -1;
      desenharFiltros();
      if (idx >= 0) $("#filtros").children[idx].querySelector("button").click();
    }
    desenharCards(c, a, py);
    fn(c, a);
  }

  function rota() {
    const p = location.hash.replace("#", "");
    ui.pagina = PAGINAS[p] ? p : "resumo";
    atualizar();
  }
  window.addEventListener("hashchange", rota);
  $("#atualizado").innerHTML = `Dados de<br>${esc(M.D.gerado_em)}`;
  rota();
})();
