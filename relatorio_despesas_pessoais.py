r"""
Relatório de despesas pessoais dos sócios (grupo "Não operacional - sócios").

    python relatorio_despesas_pessoais.py                  # ano atual
    python relatorio_despesas_pessoais.py --ano 2026
    python relatorio_despesas_pessoais.py --de 2026-08 --ate 2026-11

Gera saida\relatorios\Despesas pessoais <período>.xlsx com:
  - Resumo: total por mês e por caixa (Eletromóveis / Ortobom) e os maiores gastos por descrição;
  - Lançamentos: lista completa (data, caixa, loja, descrição, conta, valor), com filtro.
Rode depois de python atualizar_financeiro.py, para pegar as regras novas.
"""
import argparse, os, sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

RAIZ = Path(__file__).resolve().parent
GRUPO = "Não operacional - sócios"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

SQL = """
SELECT data::date, coalesce(negocio, ''), coalesce(loja, ''), coalesce(nullif(trim(descricao), ''), '(sem descrição)'),
       conta, -valor
FROM financeiro.vw_fato_principal
WHERE grupo_dre = %(grupo)s AND data >= %(ini)s AND data < %(fim)s
ORDER BY data, descricao
"""

NAVY = "0E1726"
F = lambda **k: Font(name="Arial", **k)
FILL_CAB = PatternFill("solid", fgColor=NAVY)
FILL_TOT = PatternFill("solid", fgColor="F2F3F7")
BORDA = Border(bottom=Side(style="thin", color="E6E8EF"))
MOEDA = '"R$" #,##0.00;-"R$" #,##0.00;-'


def ler_env():
    env = RAIZ / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.strip().startswith("#"):
                k, v = l.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def cabecalho(ws, linha, textos, col=1):
    for j, t in enumerate(textos):
        c = ws.cell(linha, col + j, t)
        c.font = F(bold=True, color="FFFFFF"); c.fill = FILL_CAB
        c.alignment = Alignment(horizontal="left" if j == 0 else "right", vertical="center")


def montar(linhas, destino, titulo):
    """linhas: (data, negocio, loja, descricao, conta, valor positivo = gasto)."""
    wb = Workbook()
    res = wb.active; res.title = "Resumo"
    lan = wb.create_sheet("Lançamentos")

    # ---- Lançamentos (base de tudo) ----
    cab = ["Data", "Caixa", "Loja", "Descrição", "Conta", "Valor"]
    cabecalho(lan, 1, cab)
    for i, (d, neg, loja, desc, conta, v) in enumerate(linhas, start=2):
        for j, x in enumerate([d, neg.title() if neg else "", loja, desc, conta, float(v)], start=1):
            c = lan.cell(i, j, x); c.font = F(); c.border = BORDA
        lan.cell(i, 1).number_format = "dd/mm/yyyy"
        lan.cell(i, 6).number_format = MOEDA
    ult = len(linhas) + 1
    t = ult + 1
    lan.cell(t, 5, "Total").font = F(bold=True)
    c = lan.cell(t, 6, f"=SUBTOTAL(9,F2:F{ult})"); c.font = F(bold=True); c.number_format = MOEDA
    for col in range(1, 7): lan.cell(t, col).fill = FILL_TOT
    lan.auto_filter.ref = f"A1:F{ult}"
    lan.freeze_panes = "A2"
    for col, w in zip("ABCDEF", [12, 14, 20, 52, 38, 16]): lan.column_dimensions[col].width = w

    # ---- Resumo ----
    res["A1"] = titulo; res["A1"].font = F(bold=True, size=14, color=NAVY)
    res["A2"] = "Saídas do caixa classificadas como despesa pessoal dos sócios (ficam fora da DRE). Valores positivos = gasto."
    res["A2"].font = F(italic=True, color="6B7280")

    meses = sorted({(d.year, d.month) for d, *_ in linhas})
    caixas = sorted({n for _, n, *_ in linhas}) or [""]
    r0 = 4
    res.cell(r0 - 0, 1, "Por mês").font = F(bold=True, size=12, color=NAVY)
    cabecalho(res, r0 + 1, ["Mês"] + [(c.title() if c else "Sem caixa") for c in caixas] + ["Total"])
    L = lambda col: get_column_letter(col)
    for i, (y, m) in enumerate(meses):
        r = r0 + 2 + i
        ini, fim = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)
        res.cell(r, 1, f"{MESES[m - 1]}/{y}").font = F()
        for j, cx in enumerate(caixas, start=2):
            f = (f'=SUMIFS(\'Lançamentos\'!$F$2:$F${ult},\'Lançamentos\'!$B$2:$B${ult},"{cx.title()}",'
                 f'\'Lançamentos\'!$A$2:$A${ult},">="&DATE({y},{m},1),\'Lançamentos\'!$A$2:$A${ult},"<"&DATE({fim.year},{fim.month},1))')
            c = res.cell(r, j, f); c.number_format = MOEDA; c.font = F()
        c = res.cell(r, len(caixas) + 2, f"=SUM({L(2)}{r}:{L(len(caixas) + 1)}{r})"); c.number_format = MOEDA; c.font = F(bold=True)
        for col in range(1, len(caixas) + 3): res.cell(r, col).border = BORDA
    rt = r0 + 2 + len(meses)
    res.cell(rt, 1, "Total").font = F(bold=True)
    for col in range(2, len(caixas) + 3):
        c = res.cell(rt, col, f"=SUM({L(col)}{r0 + 2}:{L(col)}{rt - 1})"); c.number_format = MOEDA; c.font = F(bold=True)
    for col in range(1, len(caixas) + 3): res.cell(rt, col).fill = FILL_TOT
    rm = rt + 1
    res.cell(rm, 1, "Média por mês").font = F(italic=True, color="6B7280")
    c = res.cell(rm, len(caixas) + 2, f"=IFERROR({L(len(caixas) + 2)}{rt}/{max(len(meses), 1)},0)")
    c.number_format = MOEDA; c.font = F(italic=True, color="6B7280")

    # maiores gastos por descrição
    por_desc = defaultdict(lambda: [0.0, 0])
    for d, neg, loja, desc, conta, v in linhas:
        por_desc[desc][0] += float(v); por_desc[desc][1] += 1
    top = sorted(por_desc.items(), key=lambda x: -x[1][0])[:30]
    r1 = rm + 3
    res.cell(r1, 1, "Maiores gastos no período (por descrição)").font = F(bold=True, size=12, color=NAVY)
    cabecalho(res, r1 + 1, ["Descrição", "Lançamentos", "Total", "% do total"])
    for i, (desc, (v, n)) in enumerate(top):
        r = r1 + 2 + i
        res.cell(r, 1, desc).font = F()
        res.cell(r, 2, n).font = F()
        c = res.cell(r, 3, f"=SUMIFS('Lançamentos'!$F$2:$F${ult},'Lançamentos'!$D$2:$D${ult},A{r})"); c.number_format = MOEDA; c.font = F()
        c = res.cell(r, 4, f"=IFERROR(C{r}/${L(len(caixas) + 2)}${rt},0)"); c.number_format = "0.0%"; c.font = F()
        for col in range(1, 5): res.cell(r, col).border = BORDA
    if len(por_desc) > len(top):
        r = r1 + 2 + len(top)
        res.cell(r, 1, f"… e mais {len(por_desc) - len(top)} descrições (veja a aba Lançamentos)").font = F(italic=True, color="6B7280")

    res.column_dimensions["A"].width = 48
    for col in range(2, max(len(caixas) + 3, 5)): res.column_dimensions[L(col)].width = 18
    res.freeze_panes = "A4"
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int)
    ap.add_argument("--de", help="AAAA-MM")
    ap.add_argument("--ate", help="AAAA-MM (inclusive)")
    a = ap.parse_args()
    if a.de or a.ate:
        y0, m0 = map(int, (a.de or f"{date.today().year}-01").split("-"))
        y1, m1 = map(int, (a.ate or f"{date.today():%Y-%m}").split("-"))
    else:
        ano = a.ano or date.today().year
        y0, m0, y1, m1 = ano, 1, ano, 12
    ini, fim = date(y0, m0, 1), date(y1 + (m1 == 12), m1 % 12 + 1, 1)
    rotulo = f"{MESES[m0 - 1]}-{y0}" + ("" if (y0, m0) == (y1, m1) else f" a {MESES[m1 - 1]}-{y1}")

    import psycopg2
    ler_env()
    conn = psycopg2.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                            dbname=os.environ.get("PGDATABASE", "ze_maria"), user=os.environ.get("PGUSER", "postgres"),
                            password=os.environ.get("PGPASSWORD"))
    with conn, conn.cursor() as cur:
        cur.execute(SQL, dict(grupo=GRUPO, ini=ini, fim=fim))
        linhas = cur.fetchall()
    conn.close()
    if not linhas:
        sys.exit(f"Nenhuma despesa pessoal entre {ini:%m/%Y} e {m1:02d}/{y1}.")
    destino = RAIZ / "saida" / "relatorios" / f"Despesas pessoais {rotulo}.xlsx"
    montar(linhas, destino, f"Despesas pessoais dos sócios — {rotulo.replace('-', '/')}")
    total = sum(float(x[5]) for x in linhas)
    br = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    print(f"{len(linhas)} lançamentos, total {br} -> {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
