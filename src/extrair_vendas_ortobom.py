"""
Vendas das lojas Ortobom (sistema próprio delas) -> mesmos CSVs do fluxo do ERP.

Usa DOIS relatórios da mesma filial e do mesmo período (Início/Fim iguais):
  1. "RELATÓRIO DE VENDA DE PRODUTOS (POR DATA)"  -> data, produto, quantidade, valor, desconto, acréscimo
  2. "RELATÓRIO DE PRODUTOS COM MARGEM DE LUCRO"  -> custo total por produto no período
O custo de cada linha do relatório por data = quantidade x custo unitário do produto
(custo total / quantidade no relatório de margem). Lucro e margem são calculados no BI.

Valida as somas contra a linha "Totais" e o "Total vendido" de cada relatório.
Produto vendido sem custo no relatório de margem entra com custo 0 (custo_informado = 0)
ou com o percentual de config/custo_estimado.csv, se houver.

Uso: python extrair_vendas_ortobom.py --vendas "relatorio-de-venda-...pdf" --custos "relatorio-...-margem-de-lucro.pdf"
                                      --loja "ORTOBOM GRAÇA" --saida saida\\x
"""
import argparse, csv, json, re, sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FILIAIS = {"LJ_GRACA": "GRAÇA", "LJ_MUCAMBO": "MUCAMBO", "LJ_CARNAUBAL": "CARNAUBAL"}


def dec(s):
    s = s.replace("R$", "").replace(" ", "")
    neg = s.startswith("-")
    v = Decimal(s.lstrip("-").replace(".", "").replace(",", "."))
    return -v if neg else v


def linhas_com_x(path):
    """[(pagina, [(x0, texto), ...])] — uma entrada por linha visual."""
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        for n, page in enumerate(pdf.pages, start=1):
            grupos = []
            for w in page.extract_words(use_text_flow=True, x_tolerance=1.5):
                for g in grupos:
                    if abs(g["top"] - w["top"]) <= 3:
                        g["w"].append(w); break
                else:
                    grupos.append(dict(top=w["top"], w=[w]))
            for g in sorted(grupos, key=lambda g: g["top"]):
                yield n, [(w["x0"], w["text"]) for w in sorted(g["w"], key=lambda w: w["x0"])]


def identificar(path):
    """Lê só o cabeçalho: dict(tipo='vendas'|'custos'|None, filial, inicio, fim)."""
    info = dict(tipo=None, filial=None, inicio=None, fim=None)
    for pg, ws in linhas_com_x(path):
        t = " ".join(w for _, w in ws)
        if "VENDA DE PRODUTOS (POR DATA)" in t:
            info["tipo"] = "vendas"
        elif "PRODUTOS COM MARGEM DE LUCRO" in t:
            info["tipo"] = "custos"
        m = re.match(r"Filial:\s*\d+\s*-\s*(\S+)", t)
        if m: info["filial"] = m.group(1).upper()
        m = re.match(r"Inicio:\s*(\d{2}-\d{2}-\d{4})", t)
        if m: info["inicio"] = datetime.strptime(m.group(1), "%d-%m-%Y").date()
        m = re.match(r"Fim:\s*(\d{2}-\d{2}-\d{4})", t)
        if m: info["fim"] = datetime.strptime(m.group(1), "%d-%m-%Y").date()
        if t.startswith(("Data Codigo", "Codigo Descricao")) or pg > 1:
            break
    return info


def nome_loja(prefixo, filial):
    return f"{prefixo} {FILIAIS.get(filial, (filial or '').replace('LJ_', ''))}".strip()


def ler_relatorio(path):
    """(cabeçalho, itens, totais, erros). Colunas mapeadas pelo x do cabeçalho; descrição que quebra linha é juntada."""
    cab, itens, totais, erros, pos = {}, [], None, [], None
    for pg, ws in linhas_com_x(path):
        t = " ".join(w for _, w in ws)
        m = re.search(r"Total vendido:\s*(R\$\s*[\d.]+,\d{2})", t)
        if m: cab["total_vendido"] = dec(m.group(1))
        if t.startswith(("Data Codigo", "Codigo Descricao")):
            pos, i = [], 0
            while i < len(ws):
                x, w = ws[i]
                if w in ("Valor", "Custo") and i + 1 < len(ws) and ws[i + 1][1] == "Total":
                    pos.append((x, w + " Total")); i += 2; continue
                pos.append((x, w)); i += 1
            continue
        if pos is None or re.fullmatch(r"Pagina \d+", t):
            continue
        cols = defaultdict(list)
        for x, w in ws:
            c = pos[0][1]
            for cx, cn in pos:
                if x >= cx - 4: c = cn
            cols[c].append(w)
        v = {k: " ".join(x) for k, x in cols.items()}
        if t.startswith("Totais"):
            totais = v; continue
        if set(v) == {"Descricao"} and itens:          # continuação da descrição
            itens[-1]["Descricao"] += " " + v["Descricao"]; continue
        if not re.fullmatch(r"\S{1,14}", v.get("Codigo", "")) or "Quantidade" not in v:
            erros.append(f"{path.name} pág {pg}: linha não reconhecida: {t!r}"); continue
        v["pagina"] = pg
        itens.append(v)
    return cab, itens, totais, erros


def custo_estimado():
    """{(loja, categoria): fator} de config/custo_estimado.csv (categoria * = todas)."""
    p = RAIZ / "config" / "custo_estimado.csv"
    regras = {}
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader((l for l in f if not l.startswith("#")), delimiter=";"):
                if r.get("percentual_custo"):
                    regras[(r["loja"].strip().upper(), r["categoria"].strip().upper())] = Decimal(r["percentual_custo"].replace(",", "."))
    return regras


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendas", required=True, type=Path, help="relatório de venda de produtos por data")
    ap.add_argument("--custos", type=Path, help="relatório de produtos com margem de lucro (mesma filial e período)")
    ap.add_argument("--loja", help="nome da loja no banco (padrão: ORTOBOM + filial do PDF)")
    ap.add_argument("--saida", required=True, type=Path)
    ap.add_argument("--cnpj", default="ORTOBOM SEM CNPJ")
    a = ap.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)
    erros, avisos = [], []

    iv = identificar(a.vendas)
    if iv["tipo"] != "vendas":
        sys.exit(f"{a.vendas.name} não é o 'Relatório de venda de produtos (por data)'.")
    loja = (a.loja or nome_loja("ORTOBOM", iv["filial"])).upper()
    ini, fim = iv["inicio"], iv["fim"]

    # ---------- vendas por data
    cab_v, itens_v, tot_v, e = ler_relatorio(a.vendas); erros += e
    vendas = []
    for v in itens_v:
        try:
            vendas.append(dict(data=datetime.strptime(v["Data"], "%d-%m-%Y").date(), cod=v["Codigo"],
                               descricao=re.sub(r"\s+", " ", v["Descricao"]).strip(), categoria=v["Categoria"].strip().upper(),
                               qtd=int(v["Quantidade"]), valor=dec(v["Valor Total"]), desconto=dec(v["Desconto"]),
                               acrescimo=dec(v["Acrescimo"]), pagina=v["pagina"]))
        except Exception as ex:
            erros.append(f"{a.vendas.name} pág {v.get('pagina')}: valores inválidos {v} ({ex})")
    if tot_v is None:
        erros.append(f"{a.vendas.name}: linha 'Totais' não encontrada")
    else:
        for nome, soma, tot in [("quantidade", sum(x["qtd"] for x in vendas), int(tot_v["Quantidade"])),
                                ("valor", sum(x["valor"] for x in vendas), dec(tot_v["Valor Total"])),
                                ("desconto", sum(x["desconto"] for x in vendas), dec(tot_v["Desconto"])),
                                ("acréscimo", sum(x["acrescimo"] for x in vendas), dec(tot_v["Acrescimo"]))]:
            if soma != tot:
                erros.append(f"{a.vendas.name}: soma de {nome} ({soma}) ≠ Totais ({tot})")
    if cab_v.get("total_vendido") is not None and tot_v and cab_v["total_vendido"] != dec(tot_v["Valor Total"]):
        erros.append(f"{a.vendas.name}: Total vendido do cabeçalho ≠ Totais")
    fora = [x for x in vendas if not (ini <= x["data"] <= fim)]
    if fora:
        erros.append(f"{a.vendas.name}: {len(fora)} venda(s) fora do período {ini:%d/%m/%Y}–{fim:%d/%m/%Y}")

    # ---------- custo unitário por produto
    custo_unit = {}
    if a.custos:
        ic = identificar(a.custos)
        if ic["tipo"] != "custos":
            erros.append(f"{a.custos.name} não é o 'Relatório de produtos com margem de lucro'")
        elif (ic["filial"], ic["inicio"], ic["fim"]) != (iv["filial"], ini, fim):
            erros.append(f"os relatórios não são da mesma filial/período: vendas {iv['filial']} {ini}–{fim}, "
                         f"custos {ic['filial']} {ic['inicio']}–{ic['fim']}")
        cab_c, itens_c, tot_c, e = ler_relatorio(a.custos); erros += e
        qtd_c = {}
        for v in itens_c:
            q, c = int(v["Quantidade"]), dec(v["Custo Total"])
            if q:
                custo_unit[v["Codigo"]] = c / q
            qtd_c[v["Codigo"]] = q
        if tot_c is None:
            erros.append(f"{a.custos.name}: linha 'Totais' não encontrada")
        else:
            sc = sum(dec(v["Custo Total"]) for v in itens_c)
            if sc != dec(tot_c["Custo Total"]):
                erros.append(f"{a.custos.name}: soma do custo ({sc}) ≠ Totais ({tot_c['Custo Total']})")
        qtd_v = defaultdict(int)
        for x in vendas: qtd_v[x["cod"]] += x["qtd"]
        for cod in sorted(set(qtd_v) | set(qtd_c)):
            if qtd_v.get(cod, 0) != qtd_c.get(cod, 0):
                avisos.append(f"produto {cod}: {qtd_v.get(cod, 0)} un. no relatório por data x {qtd_c.get(cod, 0)} no de margem"
                              + ("" if cod in custo_unit else " (sem custo: entra com custo 0)"))
    else:
        avisos.append("sem relatório de margem: custo 0 (ou estimado por config/custo_estimado.csv)")

    # ---------- saída no layout do fluxo do ERP
    regras = custo_estimado()
    linhas, seq = [], defaultdict(int)
    for x in sorted(vendas, key=lambda x: (x["data"], x["pagina"])):
        seq[x["data"]] += 1
        bruto = x["valor"] + x["desconto"] - x["acrescimo"]
        cu = custo_unit.get(x["cod"])
        fator = regras.get((loja, x["categoria"]), regras.get((loja, "*")))
        if cu is not None:
            custo, inf, est = (cu * x["qtd"]).quantize(Decimal("0.01")), "1", "0"
        elif fator is not None:
            custo, inf, est = (x["valor"] * fator).quantize(Decimal("0.01")), "0", "1"
        else:
            custo, inf, est = Decimal("0.00"), "0", "0"
        linhas.append(dict(cnpj=a.cnpj, loja=loja, data_venda=x["data"].isoformat(), seq_dia=seq[x["data"]],
                           cod_produto="ORT" + x["cod"],   # prefixo: não colide com os códigos do ERP
                           descricao=x["descricao"], categoria_origem=x["categoria"], qtd=x["qtd"],
                           vr_bruto=f"{bruto:.2f}", vr_desc_acres=f"{(x['acrescimo'] - x['desconto']):.2f}",
                           vr_liquido=f"{x['valor']:.2f}", vr_custo=f"{custo:.2f}", vr_lucro=f"{(x['valor'] - custo):.2f}",
                           custo_informado=inf, custo_estimado=est, arquivo_origem=a.vendas.name, pagina=x["pagina"]))
    cols_item = ["cnpj", "loja", "data_venda", "seq_dia", "cod_produto", "descricao", "categoria_origem", "qtd", "vr_bruto",
                 "vr_desc_acres", "vr_liquido", "vr_custo", "vr_lucro", "custo_informado", "custo_estimado", "arquivo_origem", "pagina"]
    with open(a.saida / "fato_venda_item.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols_item, delimiter=";"); w.writeheader(); w.writerows(linhas)
    with open(a.saida / "fato_venda.csv", "w", newline="", encoding="utf-8") as f:
        f.write("cnpj;loja;controle;data_venda;data_hora;tipo;vr_bruto;vr_desc_acres;vr_liquido;vr_custo;vr_lucro;vr_coluna_extra;arquivo_origem;pagina\n")
    with open(a.saida / "fato_venda_item_vinculo.csv", "w", newline="", encoding="utf-8") as f:
        f.write("cnpj;loja;data_venda;seq_dia;controle;qtd;vr_liquido;vr_custo;status_vinculo\n")
    with open(a.saida / "dim_empresa.csv", "w", newline="", encoding="utf-8") as f:
        f.write(f"cnpj;razao_social;uf;inscricao_estadual\n{a.cnpj};Lojas Ortobom;;\n")
    with open(a.saida / "dim_produto.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["cod_produto", "descricao", "categoria_origem", "qtd_descricoes"])
        for cod in sorted({l["cod_produto"] for l in linhas}):
            l = next(l for l in linhas if l["cod_produto"] == cod)
            w.writerow([cod, l["descricao"], l["categoria_origem"], 1])
    tot = sum(Decimal(l["vr_liquido"]) for l in linhas)
    tot_custo = sum(Decimal(l["vr_custo"]) for l in linhas)
    meta = dict(fonte="ORTOBOM", cnpj=a.cnpj, loja=loja, razao_social="Lojas Ortobom",
                arquivo_produto=a.vendas.name, periodo_produto=[ini.isoformat(), fim.isoformat()],
                arquivo_venda=a.custos.name if a.custos else None, periodo_venda=[ini.isoformat(), fim.isoformat()],
                linhas_item=len(linhas), linhas_venda=0, total_liquido_itens=f"{tot:.2f}", total_liquido_vendas="0.00",
                total_custo=f"{tot_custo:.2f}", validacao_ok=not erros, problemas=erros, avisos=avisos)
    (a.saida / "carga_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    sem = sum(1 for l in linhas if l["custo_informado"] == "0")
    print(f"{loja}: {len(linhas)} linhas | {sum(l['qtd'] for l in linhas)} peças | vendas R$ {tot:,.2f} | custo R$ {tot_custo:,.2f} | "
          f"{min(l['data_venda'] for l in linhas) if linhas else '-'} a {max(l['data_venda'] for l in linhas) if linhas else '-'}"
          + (f" | {sem} linha(s) sem custo" if sem else ""))
    for av in avisos: print("  aviso:", av)
    if erros:
        print(f"\n{len(erros)} PROBLEMA(S):"); [print(" -", e) for e in erros]
        sys.exit(1)
    print("Validação OK: linhas batem com Totais e Total vendido.")


if __name__ == "__main__":
    main()
