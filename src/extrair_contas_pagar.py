"""
Extrai a planilha de BOLETOS A PAGAR da Zé&Maria (abas EMPRESA e IMPOSTOS OUTRO ESTADO)
para saida/financeiro/fato_conta_pagar.csv.

A planilha é preenchida à mão e não tem ID: cada linha é identificada por aba + nº da linha.
Como ela é sempre regravada no mesmo caminho, a carga substitui tudo a cada execução.

Campos normalizados (o texto original é mantido ao lado):
  forma_pgto  -> DUPLICATA | CHEQUE | DINHEIRO | DEPOSITO/PIX | CARNE | DEBITO EM CONTA | OUTROS
  parcela     -> parcela_num / parcela_total quando vier "2//5", "PG - 2/3" etc.
  loja        -> GRAÇA | MUCAMBO | outros textos ficam em loja_original (a coluna é usada como anotação)
  cor_marcacao-> cor de fundo da célula da data. HIPÓTESE a confirmar com a Veronica: linha colorida = paga.

Uso: python extrair_contas_pagar.py "caminho\\BOLETOS A PAGAR.xlsx" saida\\financeiro
"""
import csv, hashlib, json, re, sys
from datetime import datetime, date
from pathlib import Path

import openpyxl

ABAS = {"EMPRESA": "LOJA", "IMPOSTOS OUTRO ESTADO": "OBS"}   # aba -> nome da coluna F
LOJAS = {"GRAÇA": "GRAÇA", "GRACA": "GRAÇA", "MUCAMBO": "MUCAMBO"}
PESSOAL = re.compile(r"PESSOAL|\bCPF\b", re.I)


def sha256(p: Path):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def txt(v):
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def forma(v):
    s = (txt(v) or "").upper()
    num = banco = None
    if s.startswith("CHEQUE"):
        m = re.search(r"(\d+)", s); num = m.group(1) if m else None
        if re.search(r"\((CAIXA|CX)\)", s): banco = "CAIXA"
        return "CHEQUE", num, banco
    if s.startswith("DUPLICATA"): return "DUPLICATA", None, None
    if s.startswith("DINHEIRO"): return "DINHEIRO", None, None
    if "PIX" in s or s.startswith("DEPOSITO"): return "DEPOSITO/PIX", None, None
    if s.startswith("CARNE"): return "CARNE", None, None
    if s.startswith("DEBITO"): return "DEBITO EM CONTA", None, None
    return ("OUTROS" if s else None), None, None


def parcela(v):
    s = txt(v)
    if not s:
        return None, None
    m = re.search(r"(\d{1,3})\s*/{1,2}\s*(\d{1,3})(?!\d)", s)
    if m and "/" in s and not re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", s):
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= b <= 120:
            return a, b
    if s.upper() in ("ÚNICO", "ÚNICA", "UNICO", "UNICA"):
        return 1, 1
    return None, None


def cor(cell):
    f = cell.fill
    if f is None or f.fill_type in (None, "none"):
        return None
    c = f.fgColor
    if c.type == "rgb":
        return None if c.rgb in ("00000000", "FFFFFFFF") else c.rgb
    if c.type == "theme":
        return f"tema{c.theme}" + (f"{c.tint:+.2f}" if c.tint else "")
    return None


def main():
    arq, saida = Path(sys.argv[1]), Path(sys.argv[2])
    saida.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(arq, data_only=True)   # sem read_only: precisamos das cores
    linhas, avisos = [], []
    for aba, nome_f in ABAS.items():
        if aba not in wb.sheetnames:
            avisos.append(f"aba {aba!r} não encontrada"); continue
        ws = wb[aba]
        cab = [txt(c.value) for c in ws[1][:8]]
        if (cab[0] or "").upper() != "DATA" or (cab[3] or "").upper() != "VALOR":
            sys.exit(f"Cabeçalho inesperado na aba {aba}: {cab}. A planilha mudou de layout?")
        for row in ws.iter_rows(min_row=2, max_col=8):
            vals = [c.value for c in row]
            if all(v in (None, "") or (isinstance(v, str) and not v.strip()) for v in vals[:7]):
                continue
            n = row[0].row
            d, fornecedor, fpg, valor, parc, loja, nf, obs = vals
            if isinstance(d, datetime):
                d = d.date()
            elif not isinstance(d, date):
                avisos.append(f"{aba}!A{n}: data inválida {d!r} ({txt(fornecedor)}) — linha carregada sem data")
                d = None
            if d is not None and d.year < 2000:
                avisos.append(f"{aba}!A{n}: data {d} parece erro de digitação ({txt(fornecedor)})")
            if not isinstance(valor, (int, float)):
                avisos.append(f"{aba}!D{n}: valor vazio/inválido {valor!r} ({txt(fornecedor)})")
                valor = None
            f_norm, cheque, banco = forma(fpg)
            p_num, p_tot = parcela(parc)
            loja_t = txt(loja)
            loja_n = LOJAS.get((loja_t or "").upper()) if aba == "EMPRESA" else LOJAS.get((loja_t or "").upper())
            textos = " ".join(t for t in (txt(fornecedor), txt(fpg), txt(parc), loja_t, txt(obs)) if t)
            linhas.append(dict(
                aba=aba, linha_planilha=n, data_vencimento=d.isoformat() if d else "",
                fornecedor=(txt(fornecedor) or "").upper(), forma_pgto=f_norm or "", forma_pgto_original=txt(fpg) or "",
                num_cheque=cheque or "", banco_cheque=banco or "",
                valor=f"{valor:.2f}" if valor is not None else "",
                parcela_original=txt(parc) or "", parcela_num=p_num or "", parcela_total=p_tot or "",
                loja=loja_n or "", loja_original=loja_t or "",
                nota_fiscal=txt(nf) or "", observacao=txt(obs) or "",
                possivel_pessoal="1" if PESSOAL.search(textos) else "0",
                cor_marcacao=cor(row[0]) or ""))
    cols = list(linhas[0].keys())
    with open(saida / "fato_conta_pagar.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";"); w.writeheader(); w.writerows(linhas)
    total = sum(float(l["valor"]) for l in linhas if l["valor"])
    meta = dict(arquivo=str(arq), nome=arq.name, sha256=sha256(arq),
                modificado_em=datetime.fromtimestamp(arq.stat().st_mtime).isoformat(timespec="seconds"),
                linhas=len(linhas), total_valor=f"{total:.2f}", avisos=avisos)
    (saida / "contas_pagar_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Contas a pagar: {len(linhas)} linhas | R$ {total:,.2f} | {len(avisos)} aviso(s)")
    for a in avisos[:20]:
        print("  aviso:", a)


if __name__ == "__main__":
    main()
