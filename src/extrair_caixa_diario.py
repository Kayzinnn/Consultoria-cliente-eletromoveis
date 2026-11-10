"""
Extrai a PLAN GERAL (caixa diário Graça/Mucambo) para:
  saida/financeiro/fato_caixa_lancamento.csv  -> 1 linha por entrada/saída
  saida/financeiro/fato_caixa_dia.csv         -> saldos e totais de cada dia

Layout esperado: uma aba por mês; cada dia é um bloco de 2 colunas
(rótulo | valor) que começa com [dia da semana | data] e segue:
  Saldo inicial / linhas de ENTRADA / Total Entrada / linhas de SAÍDA /
  Total de saída / Saldo Operac / Saldo final

Valida cada dia: soma das entradas = Total Entrada, soma das saídas = Total de saída,
Saldo final = Saldo inicial + entradas - saídas. Diferença de abertura (saldo inicial
≠ saldo final do dia anterior) NÃO trava: vira alerta no banco.

Arquivo com senha: informe em PLAN_GERAL_SENHA (no .env).
Uso: python extrair_caixa_diario.py "caminho\\2026- PLAN GERAL.xlsx" [outro.xlsx ...] saida\\financeiro
"""
import csv, hashlib, io, json, os, re, sys
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

RAIZ = Path(__file__).resolve().parent.parent
FIXOS = {"SALDO INICIAL", "TOTAL ENTRADA", "TOTAL DE SAÍDA", "TOTAL DE SAIDA", "SALDO OPERAC", "SALDO FINAL"}


def ler_env():
    env = RAIZ / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.strip().startswith("#"):
                k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def abrir(arq: Path):
    """Abre o xlsx; se estiver criptografado, usa PLAN_GERAL_SENHA."""
    dados = arq.read_bytes()
    if dados[:4] == b"PK\x03\x04":
        return (openpyxl.load_workbook(io.BytesIO(dados), data_only=True),
                openpyxl.load_workbook(io.BytesIO(dados)), hashlib.sha256(dados).hexdigest())
    import msoffcrypto
    senha = os.environ.get("PLAN_GERAL_SENHA")
    if not senha:
        sys.exit(f"{arq.name} tem senha: preencha PLAN_GERAL_SENHA no .env")
    of = msoffcrypto.OfficeFile(io.BytesIO(dados)); of.load_key(password=senha)
    out = io.BytesIO(); of.decrypt(out); raw = out.getvalue()
    return (openpyxl.load_workbook(io.BytesIO(raw), data_only=True),
            openpyxl.load_workbook(io.BytesIO(raw)), hashlib.sha256(dados).hexdigest())


def num(v):
    if v is None or v == "":
        return Decimal(0)
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip().replace("R$", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def q2(d): return d.quantize(Decimal("0.01"), ROUND_HALF_UP)


def refs_formula(f):
    """Células somadas por uma fórmula simples (=B3+B4, =SUM(B10:B29)). None = valor digitado/não analisável."""
    if not (isinstance(f, str) and f.startswith("=")):
        return None
    from openpyxl.utils import column_index_from_string as ci
    out = set()
    for a, b in re.findall(r"\$?([A-Z]+\$?\d+)(?::\$?([A-Z]+\$?\d+))?", f.replace("$", "")):
        c1, r1 = re.match(r"([A-Z]+)(\d+)", a).groups()
        if b:
            c2, r2 = re.match(r"([A-Z]+)(\d+)", b).groups()
            for r in range(int(r1), int(r2) + 1):
                for c in range(ci(c1), ci(c2) + 1):
                    out.add((r, c))
        else:
            out.add((int(r1), ci(c1)))
    return out


def mapa_entradas():
    p = RAIZ / "config" / "mapa_entradas_caixa.csv"
    with open(p, encoding="utf-8") as f:
        return {r["rotulo"].strip().upper(): r for r in csv.DictReader(f, delimiter=";")}


def extrair(arq: Path, mapa):
    wb, wf, h = abrir(arq)
    lancs, dias, erros, avisos = [], [], [], []
    for ws in wb:
        maxr, maxc = ws.max_row, ws.max_column
        grid = {(c.row, c.column): c.value for row in ws.iter_rows() for c in row if c.value is not None}
        fws = wf[ws.title]
        for (r, c), v in sorted(grid.items()):
            if not (isinstance(v, datetime) and isinstance(grid.get((r, c - 1)), str)):
                continue
            col_l, col_v, d = c - 1, c, v.date()
            dia = dict(arquivo=arq.name, aba=ws.title, data=d.isoformat(), celula=f"{get_column_letter(col_v)}{r}")
            secao, ent, sai, ordem = "ENTRADA", Decimal(0), Decimal(0), 0
            pend = []          # lançamentos do bloco, para marcar se entram no total da planilha
            rr = r + 1
            while rr <= maxr:
                lab, val = grid.get((rr, col_l)), grid.get((rr, col_v))
                if isinstance(val, datetime):            # começou outro bloco na mesma coluna
                    break
                rot = re.sub(r"\s+", " ", str(lab)).strip() if lab is not None else ""
                ru = rot.upper()
                if ru in FIXOS:
                    nv = num(val)
                    if ru == "SALDO INICIAL": dia["saldo_inicial"] = nv
                    elif ru in ("TOTAL ENTRADA",) or ru.startswith("TOTAL DE SA"):
                        tipo_tot = "ENTRADA" if ru == "TOTAL ENTRADA" else "SAIDA"
                        dia["total_entrada" if tipo_tot == "ENTRADA" else "total_saida"] = nv
                        refs = refs_formula(fws.cell(rr, col_v).value)
                        for x in pend:
                            if x["tipo"] == tipo_tot:
                                x["entra_no_total"] = "1" if refs is None or x["_rc"] in refs else "0"
                        if tipo_tot == "ENTRADA": secao = "SAIDA"
                    elif ru == "SALDO FINAL": dia["saldo_final"] = nv; break
                elif rot or val not in (None, "", 0):
                    nv = num(val)
                    if nv is None:
                        erros.append(f"{arq.name} {ws.title}!{get_column_letter(col_v)}{rr}: valor não numérico {val!r} ({rot})")
                        nv = Decimal(0)
                    if nv != 0 or rot:
                        ordem += 1
                        m = mapa.get(ru) if secao == "ENTRADA" else None
                        if secao == "ENTRADA" and m is None and nv != 0:
                            avisos.append(f"rótulo de entrada sem mapa: {rot!r} ({ws.title} {d})")
                        if nv != 0:
                            pend.append(dict(_rc=(rr, col_v), entra_no_total="1",arquivo=arq.name, aba=ws.title, celula=f"{get_column_letter(col_v)}{rr}",
                                              data=d.isoformat(), tipo=secao, ordem=ordem, descricao=rot,
                                              valor=f"{q2(nv)}",
                                              loja=(m or {}).get("loja", ""), meio=(m or {}).get("meio", ""),
                                              conta=(m or {}).get("conta", "")))
                rr += 1
            for x in pend:
                v = Decimal(x["valor"])
                if x["entra_no_total"] == "1":
                    if x["tipo"] == "ENTRADA": ent += v
                    else: sai += v
                x.pop("_rc"); lancs.append(x)
            dia["entradas_fora_total"] = sum((Decimal(x["valor"]) for x in pend if x["tipo"] == "ENTRADA" and x["entra_no_total"] == "0"), Decimal(0))
            dia["saidas_fora_total"] = sum((Decimal(x["valor"]) for x in pend if x["tipo"] == "SAIDA" and x["entra_no_total"] == "0"), Decimal(0))
            for k in ("saldo_inicial", "total_entrada", "total_saida", "saldo_final"):
                if dia.get(k) is None:
                    erros.append(f"{arq.name} {ws.title} {d}: bloco sem '{k}'"); dia[k] = Decimal(0)
            if q2(ent) != q2(dia["total_entrada"]):
                erros.append(f"{arq.name} {d}: entradas somam {q2(ent)} mas Total Entrada = {q2(dia['total_entrada'])}")
            if q2(sai) != q2(dia["total_saida"]):
                erros.append(f"{arq.name} {d}: saídas somam {q2(sai)} mas Total de saída = {q2(dia['total_saida'])}")
            dia["saldo_final_recalculado"] = q2(dia["saldo_inicial"] + dia["total_entrada"] - dia["total_saida"])
            if dia["saldo_final_recalculado"] != q2(dia["saldo_final"]):
                avisos.append(f"{arq.name} {d}: saldo final não fecha ({q2(dia['saldo_inicial'])} + {q2(dia['total_entrada'])} - {q2(dia['total_saida'])} ≠ {q2(dia['saldo_final'])})")
            dias.append(dia)
    # mesmo dia em dois blocos = erro de digitação na data
    vistos = {}
    for d in dias:
        if d["data"] in vistos:
            erros.append(f"{arq.name}: data {d['data']} repetida em {vistos[d['data']]} e {d['aba']}!{d['celula']}")
        vistos[d["data"]] = f"{d['aba']}!{d['celula']}"
    return lancs, dias, erros, avisos, h


def main():
    ler_env()
    *arqs, saida = sys.argv[1:]
    saida = Path(saida); saida.mkdir(parents=True, exist_ok=True)
    mapa = mapa_entradas()
    L, D, E, A, metas = [], [], [], [], []
    for a in map(Path, arqs):
        l, d, e, av, h = extrair(a, mapa)
        L += l; D += d; E += e; A += av
        metas.append(dict(arquivo=str(a), nome=a.name, sha256=h, linhas=len(l), dias=len(d),
                          modificado_em=datetime.fromtimestamp(a.stat().st_mtime).isoformat(timespec="seconds")))
    D.sort(key=lambda x: x["data"])
    ant = None
    for d in D:   # diferença de abertura em relação ao dia anterior
        d["saldo_final_anterior"] = ant["saldo_final"] if ant else None
        d["diferenca_abertura"] = (q2(d["saldo_inicial"] - ant["saldo_final"]) if ant else None)
        ant = d
    with open(saida / "fato_caixa_lancamento.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(L[0].keys()), delimiter=";"); w.writeheader(); w.writerows(L)
    cols = ["arquivo", "aba", "celula", "data", "saldo_inicial", "total_entrada", "total_saida", "saldo_final",
            "saldo_final_recalculado", "saldo_final_anterior", "diferenca_abertura", "entradas_fora_total", "saidas_fora_total"]
    with open(saida / "fato_caixa_dia.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(cols)
        for d in D:
            w.writerow(["" if d.get(c) is None else (f"{q2(d[c])}" if isinstance(d[c], Decimal) else d[c]) for c in cols])
    avisos = sorted(set(A), key=lambda x: (not x.startswith("rótulo"), x))
    meta = dict(arquivos=metas, linhas=len(L), dias=len(D), validacao_ok=not E, erros=E, avisos=avisos,
                total_entradas=f"{sum(Decimal(x['valor']) for x in L if x['tipo']=='ENTRADA')}",
                total_saidas=f"{sum(Decimal(x['valor']) for x in L if x['tipo']=='SAIDA')}")
    (saida / "caixa_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    quebras = sum(1 for d in D if d["diferenca_abertura"] not in (None, Decimal("0.00")))
    print(f"Caixa diário: {len(D)} dias | {len(L)} lançamentos | entradas R$ {meta['total_entradas']} | "
          f"saídas R$ {meta['total_saidas']} | {quebras} dia(s) com saldo inicial ≠ final anterior")
    for a in avisos[:20]: print("  alerta da planilha:", a)
    if E:
        print(f"\n{len(E)} ERRO(S):"); [print("  -", e) for e in E[:40]]
        sys.exit(1)
    print("Validação OK: as linhas extraídas batem com Total Entrada e Total de saída de todos os dias.")


if __name__ == "__main__":
    main()
