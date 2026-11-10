r"""
Vendas: extrai os PDFs "Lucratividade" do ERP, valida, liga itens às vendas e carrega no banco.

Organização da pasta (uma subpasta por loja — o nome da pasta vira a loja no banco):
    entrada\vendas\GRAÇA\Lucratividade por produto 2026.pdf
    entrada\vendas\GRAÇA\Lucratividade por venda clientes 2026.pdf
    entrada\vendas\MUCAMBO\Lucratividade por produto 2026.pdf
    entrada\vendas\MUCAMBO\Lucratividade por venda clientes 2026.pdf
Em cada loja, os PDFs formam par pelo que vem depois do nome (normalmente o ano).
Rode sempre que chegar PDF novo: cada par substitui o próprio período daquela loja, sem duplicar.

    python processa_vendas.py                    # todas as lojas e anos
    python processa_vendas.py --loja MUCAMBO     # só uma loja
    python processa_vendas.py --ano 2026         # só um ano
    python processa_vendas.py --sem-banco        # só gera os CSVs em saida\
"""
import argparse, re, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SRC = RAIZ / "src"
ENTRADA = RAIZ / "entrada"


def rodar(script, *args):
    print(f"\n>> {script.name}", flush=True)
    r = subprocess.run([sys.executable, str(script), *map(str, args)])
    if r.returncode != 0:
        sys.exit(f"Parou: {script.name} falhou. Nada foi gravado no banco nesta etapa.")


def pares_da_pasta(pasta: Path):
    """{chave: (pdf_produto, pdf_venda)} dentro de uma pasta — chave = o que vem depois do nome (ex.: '2026')."""
    prod, vend = {}, {}
    for p in pasta.glob("*.pdf"):
        n = p.stem.lower().replace("_", " ")
        m = re.match(r"lucratividade por produto\s*(.*)$", n)
        if m:
            prod[m.group(1).strip()] = p; continue
        m = re.match(r"lucratividade por venda(?: clientes)?\s*(.*)$", n)
        if m:
            vend[m.group(1).strip()] = p
    for k in sorted(set(prod) ^ set(vend)):
        falta = "venda" if k in prod else "produto"
        print(f"Aviso: {pasta.name} '{k or '(sem ano)'}' não tem o PDF de {falta}; ignorado.")
    return {k: (prod[k], vend[k]) for k in sorted(set(prod) & set(vend))}


def pares_na_entrada():
    """[(loja, chave, pdf_produto, pdf_venda)] para cada subpasta de entrada/vendas."""
    soltos = [p.name for p in ENTRADA.glob("*.pdf")]
    if soltos:
        print("Aviso: PDFs soltos na pasta entrada (fora de entrada\\vendas\\<LOJA>) foram ignorados:")
        for n in soltos:
            print("   -", n)
    pares = []
    for pasta in sorted(p for p in (ENTRADA / "vendas").glob("*") if p.is_dir()):
        for k, (p, v) in pares_da_pasta(pasta).items():
            pares.append((pasta.name.upper(), k, p, v))
    return pares


def processar(produto, venda, saida, sem_banco, loja=""):
    rodar(SRC / "extrair_vendas_ze_maria.py", "--produto", produto, "--venda", venda, "--saida", saida, "--loja", loja)
    rodar(SRC / "vincular_itens_vendas.py", saida)
    if not sem_banco:
        rodar(SRC / "carregar_banco.py", saida)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--produto"); ap.add_argument("--venda")
    ap.add_argument("--ano", help="processa só esse ano (ex.: 2026)")
    ap.add_argument("--loja", help="processa só essa loja (nome da pasta)")
    ap.add_argument("--sem-banco", action="store_true")
    a = ap.parse_args()

    if a.produto or a.venda:
        if not (a.produto and a.venda and a.loja):
            sys.exit("Para arquivos específicos informe --produto, --venda e --loja.")
        processar(a.produto, a.venda, RAIZ / "saida" / "vendas", a.sem_banco, a.loja.upper())
    else:
        pares = pares_na_entrada()
        if a.loja:
            pares = [x for x in pares if x[0] == a.loja.upper()]
        if a.ano:
            pares = [x for x in pares if x[1] == a.ano]
        if not pares:
            sys.exit(f"Nenhum par de PDFs encontrado em {ENTRADA / 'vendas'}\\<LOJA>\\")
        for loja, k, p, v in pares:
            print(f"\n==================== {loja} {k}: {p.name}  +  {v.name}")
            processar(p, v, RAIZ / "saida" / f"vendas_{loja}_{k or 'unico'}", a.sem_banco, loja)
    print("\nPronto.")


if __name__ == "__main__":
    main()
