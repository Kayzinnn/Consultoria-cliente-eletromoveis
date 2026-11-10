"""
Vendas: extrai os PDFs "Lucratividade" do ERP, valida, liga itens às vendas e carrega no banco.

Sem argumentos, procura na pasta entrada\ os pares de cada ano:
    Lucratividade por produto 2025.pdf  +  Lucratividade por venda clientes 2025.pdf
    Lucratividade por produto 2026.pdf  +  Lucratividade por venda clientes 2026.pdf
e processa todos (pode rodar sempre: cada par substitui o próprio período, sem duplicar).

    python processa_vendas.py                 # todos os pares da pasta entrada
    python processa_vendas.py --ano 2026      # só um ano
    python processa_vendas.py --produto X.pdf --venda Y.pdf   # arquivos específicos
    python processa_vendas.py --sem-banco     # só gera os CSVs em saida\
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


def pares_na_entrada():
    """{chave: (pdf_produto, pdf_venda)} — a chave é o que vem depois do nome (ex.: '2026')."""
    prod, vend = {}, {}
    for p in ENTRADA.glob("*.pdf"):
        n = p.stem.lower().replace("_", " ")
        m = re.match(r"lucratividade por produto\s*(.*)$", n)
        if m:
            prod[m.group(1).strip()] = p; continue
        m = re.match(r"lucratividade por venda(?: clientes)?\s*(.*)$", n)
        if m:
            vend[m.group(1).strip()] = p
    sem_par = sorted(set(prod) ^ set(vend))
    for k in sem_par:
        falta = "venda" if k in prod else "produto"
        print(f"Aviso: '{k or '(sem ano)'}' não tem o PDF de {falta}; ignorado.")
    return {k: (prod[k], vend[k]) for k in sorted(set(prod) & set(vend))}


def processar(produto, venda, saida, sem_banco):
    rodar(SRC / "extrair_vendas_ze_maria.py", "--produto", produto, "--venda", venda, "--saida", saida)
    rodar(SRC / "vincular_itens_vendas.py", saida)
    if not sem_banco:
        rodar(SRC / "carregar_banco.py", saida)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--produto"); ap.add_argument("--venda")
    ap.add_argument("--ano", help="processa só o par desse ano (ex.: 2026)")
    ap.add_argument("--sem-banco", action="store_true")
    a = ap.parse_args()

    if a.produto or a.venda:
        if not (a.produto and a.venda):
            sys.exit("Informe --produto e --venda juntos.")
        processar(a.produto, a.venda, RAIZ / "saida" / "vendas", a.sem_banco)
    else:
        pares = pares_na_entrada()
        if a.ano:
            pares = {k: v for k, v in pares.items() if k == a.ano}
        if not pares:
            sys.exit(f"Nenhum par de PDFs 'Lucratividade por produto/venda' encontrado em {ENTRADA}")
        for k, (p, v) in pares.items():
            print(f"\n==================== {k or 'arquivo'}: {p.name}  +  {v.name}")
            processar(p, v, RAIZ / "saida" / f"vendas_{k or 'unico'}", a.sem_banco)
    print("\nPronto.")


if __name__ == "__main__":
    main()
