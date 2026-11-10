"""
Extrai os relatórios do ERP da Eletromóveis Zé&Maria (PDF) para CSV:
  - "Lucratividade por produto"  -> fato_venda_item.csv + dim_produto.csv
  - "Lucratividade por venda"    -> fato_venda.csv
Valida cada dia contra o SUB-TOTAL e o TOTAL impressos no próprio relatório.

Uso:
  python extrair_vendas_ze_maria.py --produto Lucratividade_por_produto.pdf \
         --venda Lucratividade_por_venda.pdf --saida saida/
Requer: pip install pdfplumber
"""
import argparse, csv, json, re, sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

MONEY = r"-?R\$ ?-?[\d.]+,\d{2}"
NUM = r"-?[\d.]+,\d{2}"
HEADER_PREFIX = ("LUCRATIVIDADE POR", "* A informação", "PERÍODO LISTADO", "FILTRADO POR",
                 "LANÇAMENTOS CONFIRMADOS", "Página ", "Descrição", "Controle")
WEEKDAY = re.compile(r"^(segunda|terça|quarta|quinta|sexta|sábado|domingo)-?feira|^(sábado|domingo),", re.I)


def dec(s: str) -> Decimal:
    s = s.replace("R$", "").replace(" ", "")
    neg = s.count("-") % 2 == 1
    s = s.replace("-", "").replace(".", "").replace(",", ".")
    v = Decimal(s)
    return -v if neg else v


def pdf_lines(path: Path):
    """Linhas do PDF, uma por linha visual. Usa pdfplumber (pip install pdfplumber).
    As palavras são lidas na ordem do fluxo do PDF (use_text_flow) para não misturar
    caracteres de colunas que se sobrepõem (ex.: % de lucro gigante quando custo = 0,01)."""
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        for n, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False, x_tolerance=1.5)
            linhas = []
            for w in words:
                for ln in linhas:
                    if abs(ln["top"] - w["top"]) <= 3:
                        ln["w"].append(w); break
                else:
                    linhas.append(dict(top=w["top"], w=[w]))
            for ln in sorted(linhas, key=lambda l: l["top"]):
                ws = sorted(ln["w"], key=lambda w: w["x0"])
                yield n, " ".join(w["text"] for w in ws)


def cabecalho(path: Path):
    """Empresa, CNPJ, IE e período a partir do cabeçalho da 1ª página."""
    info = {}
    for _, l in pdf_lines(path):
        s = l.strip()
        m = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", s)
        if m and "cnpj" not in info:
            info["cnpj"] = m.group(1)
            info["razao"] = s[:m.start()].strip()
        m = re.match(r"^([A-Z]{2}) (\d+)$", s)
        if m and "ie" not in info:
            info["uf"], info["ie"] = m.groups()
        m = re.search(r"PERÍODO LISTADO: (\d{2}/\d{2}/\d{4}) à (\d{2}/\d{2}/\d{4})", s)
        if m:
            info["periodo_ini"], info["periodo_fim"] = m.groups()
            break
    return info


def is_noise(s: str, info) -> bool:
    if not s:
        return True
    if s.startswith(HEADER_PREFIX) or WEEKDAY.match(s):
        return True
    if info.get("cnpj") and info["cnpj"] in s:
        return True
    if info.get("ie") and s == f'{info["uf"]} {info["ie"]}':
        return True
    return False


# ----------------------------------------------------------------------------- produto
ITEM = re.compile(rf"^(\d{{13}}) -\s?(.*?)\s+(-?\d+)\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})(?:\s*(-?[\d.]+,\d{{2}})%)?\s*$")
PCT_SO = re.compile(r"^(-?[\d.]+,\d{2})%$")
SUB_P = re.compile(rf"^(SUB-TOTAL|TOTAL):\s+(-?\d+)\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s*(-?[\d.]+,\d{{2}})%")


def parse_produto(path: Path, info):
    itens, erros, dia, cur, subtot_dia = [], [], None, None, {}
    total = None
    seq = 0
    for page, raw in pdf_lines(path):
        s = raw.strip()
        if is_noise(s, info):
            continue
        m = re.match(r"^DATA DA VENDA (\d{2}/\d{2}/\d{4})$", s)
        if m:
            dia = datetime.strptime(m.group(1), "%d/%m/%Y").date(); cur = None; seq = 0
            continue
        m = ITEM.match(s)
        if m:
            seq += 1
            cod, desc0, qtd, *vals, pct = m.groups()
            cur = dict(data_venda=dia, seq_dia=seq, cod_produto=cod, descricao=[desc0] if desc0 else [],
                       qtd=int(qtd), vr_bruto=dec(vals[0]), vr_desc_acres=dec(vals[1]), vr_liquido=dec(vals[2]),
                       vr_custo=dec(vals[3]), vr_lucro=dec(vals[4]), pct_lucro_relatorio=dec(pct) if pct else None, pagina=page)
            itens.append(cur)
            continue
        m = SUB_P.match(s)
        if m:
            kind, qtd, *vals = m.groups()
            rec = dict(qtd=int(qtd), vr_bruto=dec(vals[0]), vr_desc_acres=dec(vals[1]), vr_liquido=dec(vals[2]),
                       vr_custo=dec(vals[3]), vr_lucro=dec(vals[4]))
            if kind == "TOTAL":
                total = rec
            else:
                subtot_dia[dia] = rec
            cur = None
            continue
        m = PCT_SO.match(s)
        if m and cur is not None and cur["pct_lucro_relatorio"] is None:
            cur["pct_lucro_relatorio"] = dec(m.group(1))   # % quebrou para a linha de baixo
            continue
        if cur is not None:
            cur["descricao"].append(s)      # continuação da descrição
            continue
        erros.append(f"[produto] pág {page}: linha não reconhecida: {s!r}")
    for it in itens:
        it["descricao"] = re.sub(r"\s+", " ", " ".join(it["descricao"])).strip()
    return itens, subtot_dia, total, erros


# ----------------------------------------------------------------------------- venda
VENDA = re.compile(rf"^(\d{{14}})\s+(?:({MONEY})\s+)?({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})(?:\s*(-?[\d.]+,\d{{2}})%)?\s*$")
SUB_V = re.compile(rf"^(SUB-TOTAL|TOTAL):\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})\s*(-?[\d.]+,\d{{2}})%")


def parse_venda(path: Path, info):
    vendas, erros, dia, cur, subtot_dia, total = [], [], None, None, {}, None
    for page, raw in pdf_lines(path):
        s = raw.strip()
        if is_noise(s, info):
            continue
        m = re.match(r"^VENDAS REALIZADAS EM (\d{2}/\d{2}/\d{4})$", s)
        if m:
            dia = datetime.strptime(m.group(1), "%d/%m/%Y").date(); cur = None
            continue
        m = VENDA.match(s)
        if m:
            ctrl, extra, *vals, pct = m.groups()
            try:
                dh = datetime.strptime(ctrl, "%Y%m%d%H%M%S")
            except ValueError:
                dh = None
            cur = dict(controle=ctrl, data_venda=dia, data_hora=dh, tipo="VENDA",
                       vr_bruto=dec(vals[0]), vr_desc_acres=dec(vals[1]), vr_liquido=dec(vals[2]),
                       vr_custo=dec(vals[3]), vr_lucro=dec(vals[4]), pct_lucro_relatorio=dec(pct) if pct else None,
                       vr_coluna_extra=dec(extra) if extra else None, pagina=page)
            vendas.append(cur)
            continue
        m = SUB_V.match(s)
        if m:
            kind, *vals = m.groups()
            rec = dict(vr_bruto=dec(vals[0]), vr_desc_acres=dec(vals[1]), vr_liquido=dec(vals[2]),
                       vr_custo=dec(vals[3]), vr_lucro=dec(vals[4]))
            if kind == "TOTAL":
                total = rec
            else:
                subtot_dia[dia] = rec
            cur = None
            continue
        m = PCT_SO.match(s)
        if m and cur is not None and cur["pct_lucro_relatorio"] is None:
            cur["pct_lucro_relatorio"] = dec(m.group(1))
            continue
        if cur is not None and s in ("TROCA/DEVOLUÇÃO",):
            cur["tipo"] = "TROCA/DEVOLUÇÃO"
            continue
        erros.append(f"[venda] pág {page}: linha não reconhecida: {s!r}")
    return vendas, subtot_dia, total, erros


# ----------------------------------------------------------------------------- validação
CAMPOS = ("vr_bruto", "vr_desc_acres", "vr_liquido", "vr_custo", "vr_lucro")


def validar(nome, linhas, subtot, total, com_qtd=False):
    problemas = []
    campos = CAMPOS + (("qtd",) if com_qtd else ())
    por_dia = {}
    for l in linhas:
        d = por_dia.setdefault(l["data_venda"], {c: 0 for c in campos})
        for c in campos:
            d[c] += l[c]
    for dia, st in subtot.items():
        soma = por_dia.get(dia, {c: 0 for c in campos})
        for c in campos:
            if soma[c] != st[c]:
                problemas.append(f"[{nome}] {dia}: {c} soma={soma[c]} subtotal={st[c]}")
    for dia in por_dia:
        if dia not in subtot:
            problemas.append(f"[{nome}] {dia}: dia sem SUB-TOTAL no relatório")
    if total:
        for c in campos:
            soma = sum(l[c] for l in linhas)
            if soma != total[c]:
                problemas.append(f"[{nome}] TOTAL {c}: soma={soma} relatório={total[c]}")
    else:
        problemas.append(f"[{nome}] TOTAL geral não encontrado")
    return problemas


# ----------------------------------------------------------------------------- saída
def fmt(v):
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v.isoformat() if hasattr(v, "isoformat") else v


def write_csv(path: Path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for r in rows:
            w.writerow([fmt(r.get(c)) for c in cols])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--produto", required=True, type=Path)
    ap.add_argument("--venda", required=True, type=Path)
    ap.add_argument("--saida", default=Path("saida"), type=Path)
    ap.add_argument("--loja", default="", help="nome da loja (ex.: GRAÇA, MUCAMBO)")
    a = ap.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)

    info_p, info_v = cabecalho(a.produto), cabecalho(a.venda)
    if info_p.get("cnpj") != info_v.get("cnpj"):
        sys.exit(f"CNPJ diferente entre os relatórios: {info_p.get('cnpj')} x {info_v.get('cnpj')}")
    cnpj = info_p["cnpj"]

    itens, st_p, tot_p, err_p = parse_produto(a.produto, info_p)
    vendas, st_v, tot_v, err_v = parse_venda(a.venda, info_v)
    probs = err_p + err_v + validar("produto", itens, st_p, tot_p, True) + validar("venda", vendas, st_v, tot_v)

    for it in itens:
        it["cnpj"] = cnpj; it["loja"] = a.loja.upper(); it["arquivo_origem"] = a.produto.name
    for v in vendas:
        v["cnpj"] = cnpj; v["loja"] = a.loja.upper(); v["arquivo_origem"] = a.venda.name

    # dim_produto: última descrição vista por código
    prods = {}
    for it in itens:
        p = prods.setdefault(it["cod_produto"], dict(cod_produto=it["cod_produto"], descricoes=set()))
        p["descricoes"].add(it["descricao"]); p["descricao"] = it["descricao"]
    dimp = [dict(cod_produto=k, descricao=v["descricao"], qtd_descricoes=len(v["descricoes"])) for k, v in sorted(prods.items())]

    write_csv(a.saida / "fato_venda_item.csv", itens,
              ["cnpj", "loja", "data_venda", "seq_dia", "cod_produto", "descricao", "qtd", "vr_bruto", "vr_desc_acres",
               "vr_liquido", "vr_custo", "vr_lucro", "arquivo_origem", "pagina"])
    write_csv(a.saida / "fato_venda.csv", vendas,
              ["cnpj", "loja", "controle", "data_venda", "data_hora", "tipo", "vr_bruto", "vr_desc_acres", "vr_liquido",
               "vr_custo", "vr_lucro", "vr_coluna_extra", "arquivo_origem", "pagina"])
    write_csv(a.saida / "dim_produto.csv", dimp, ["cod_produto", "descricao", "qtd_descricoes"])
    write_csv(a.saida / "dim_empresa.csv", [dict(cnpj=cnpj, razao_social=info_p.get("razao"), uf=info_p.get("uf"),
                                                inscricao_estadual=info_p.get("ie"))],
              ["cnpj", "razao_social", "uf", "inscricao_estadual"])

    def iso(d): return datetime.strptime(d, "%d/%m/%Y").date().isoformat()
    meta = dict(cnpj=cnpj, loja=a.loja.upper(), razao_social=info_p.get("razao"),
                arquivo_produto=a.produto.name, periodo_produto=[iso(info_p["periodo_ini"]), iso(info_p["periodo_fim"])],
                arquivo_venda=a.venda.name, periodo_venda=[iso(info_v["periodo_ini"]), iso(info_v["periodo_fim"])],
                linhas_item=len(itens), linhas_venda=len(vendas),
                total_liquido_itens=f"{sum(i['vr_liquido'] for i in itens):.2f}",
                total_liquido_vendas=f"{sum(v['vr_liquido'] for v in vendas):.2f}",
                validacao_ok=not probs, problemas=probs)
    (a.saida / "carga_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Empresa: {info_p.get('razao')} ({cnpj}) — loja: {a.loja.upper() or '(não informada)'}")
    print(f"Itens: {len(itens)} linhas | {len(dimp)} produtos | {min(i['data_venda'] for i in itens)} a {max(i['data_venda'] for i in itens)}")
    print(f"Vendas: {len(vendas)} controles ({sum(v['tipo'] != 'VENDA' for v in vendas)} trocas/devoluções)")
    print(f"Líquido itens: {sum(i['vr_liquido'] for i in itens)} | Líquido vendas: {sum(v['vr_liquido'] for v in vendas)}")
    if probs:
        print(f"\n{len(probs)} PROBLEMA(S):"); [print(" -", p) for p in probs[:50]]
        sys.exit(1)
    print("\nValidação OK: todos os dias batem com SUB-TOTAL e TOTAL dos dois relatórios.")


if __name__ == "__main__":
    main()
