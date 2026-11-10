r"""
Vendas: extrai os PDFs "Lucratividade" do ERP, valida, liga itens às vendas e carrega no banco.

Organização da pasta (uma subpasta por loja — o nome da pasta vira a loja no banco):
    entrada\vendas\GRAÇA\Lucratividade por produto 2026.pdf
    entrada\vendas\GRAÇA\Lucratividade por venda clientes 2026.pdf
    entrada\vendas\MUCAMBO\Lucratividade por produto 2026.pdf
    entrada\vendas\MUCAMBO\Lucratividade por venda clientes 2026.pdf
Também aceita os nomes "RELATORIO POR PRODUTO 2026.pdf" + "RELATORIO POR CLIENTE 2026.pdf".
Em cada loja, os PDFs formam par pelo que vem depois do nome (normalmente o ano).
Rode sempre que chegar PDF novo: cada par substitui o próprio período daquela loja, sem duplicar.

Lojas Ortobom (outro sistema): na pasta entrada\vendas\ORTOBOM\, para cada filial e período,
    relatorio-de-venda-de-produtos-por-data*.pdf        (vendas por dia)
    relatorio-de-produtos-com-margem-de-lucro*.pdf      (custo por produto)
Os dois formam par pela filial e pelo Início/Fim do cabeçalho (o nome do arquivo não importa).
A loja no banco vira "ORTOBOM <FILIAL>" (ORTOBOM GRAÇA, ORTOBOM MUCAMBO, ORTOBOM CARNAUBAL).

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
        m = re.match(r"(?:lucratividade|relatorio|relatório) por produto\s*(.*)$", n)
        if m:
            prod[m.group(1).strip()] = p; continue
        m = re.match(r"(?:lucratividade por venda(?: clientes?)?|(?:relatorio|relatório) por (?:venda|cliente)s?)\s*(.*)$", n)
        if m:
            vend[m.group(1).strip()] = p
    for k in sorted(set(prod) ^ set(vend)):
        falta = "venda" if k in prod else "produto"
        print(f"Aviso: {pasta.name} '{k or '(sem ano)'}' não tem o PDF de {falta}; ignorado.")
    return {k: (prod[k], vend[k]) for k in sorted(set(prod) & set(vend))}


def eh_lucratividade(p: Path):
    """PDF do ERP (par produto/venda). Aceita 'Lucratividade por ...' e 'RELATORIO POR PRODUTO/CLIENTE ...'."""
    n = p.stem.lower().replace("_", " ")
    return n.startswith("lucratividade") or re.match(r"relat[oó]rio por (produto|venda|cliente)", n) is not None


def pares_ortobom(pasta: Path):
    """[(loja, chave, pdf_vendas, pdf_custos)] dos relatórios Ortobom, pareados por filial + período."""
    sys.path.insert(0, str(SRC))
    from extrair_vendas_ortobom import identificar, nome_loja
    grupos = {}
    for p in sorted(pasta.glob("*.pdf")):
        if eh_lucratividade(p):
            continue
        i = identificar(p)
        if i["tipo"] is None:
            print(f"Aviso: {pasta.name}\\{p.name} não é relatório Ortobom reconhecido (por data / margem de lucro); ignorado.")
            continue
        g = grupos.setdefault((i["filial"], i["inicio"], i["fim"]), {})
        if i["tipo"] in g:
            print(f"Aviso: dois relatórios de {i['tipo']} da {i['filial']} {i['inicio']}–{i['fim']}: "
                  f"{g[i['tipo']].name} e {p.name}; usando o mais recente.")
            if p.stat().st_mtime < g[i["tipo"]].stat().st_mtime:
                continue
        g[i["tipo"]] = p
    pares = []
    for (filial, ini, fim), g in sorted(grupos.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or 0)):
        if "vendas" not in g:
            print(f"Aviso: {filial} {ini}–{fim} tem só o relatório de margem; falta o de venda por data. Ignorado.")
            continue
        if "custos" not in g:
            print(f"Aviso: {filial} {ini}–{fim} sem relatório de margem: vendas entram com custo 0.")
        pares.append((nome_loja(pasta.name.upper(), filial), f"{ini:%Y%m%d}_{fim:%Y%m%d}", g["vendas"], g.get("custos")))
    return pares


def pares_na_entrada():
    """[(loja, chave, pdf1, pdf2, tipo)] para cada subpasta de entrada/vendas.
    tipo 'erp' = par Lucratividade produto/venda; 'ortobom' = par vendas por data / margem de lucro."""
    soltos = [p.name for p in ENTRADA.glob("*.pdf")]
    if soltos:
        print("Aviso: PDFs soltos na pasta entrada (fora de entrada\\vendas\\<LOJA>) foram ignorados:")
        for n in soltos:
            print("   -", n)
    pares = []
    for pasta in sorted(p for p in (ENTRADA / "vendas").glob("*") if p.is_dir()):
        for k, (p, v) in pares_da_pasta(pasta).items():
            pares.append((pasta.name.upper(), k, p, v, "erp"))
        if any(not eh_lucratividade(p) for p in pasta.glob("*.pdf")):
            pares += [(*x, "ortobom") for x in pares_ortobom(pasta)]
    return pares


def processar_ortobom(vendas, custos, saida, sem_banco, loja):
    rodar(SRC / "extrair_vendas_ortobom.py", "--vendas", vendas, *(["--custos", custos] if custos else []),
          "--loja", loja, "--saida", saida)
    if not sem_banco:
        rodar(SRC / "carregar_banco.py", saida)


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
        if a.loja:   # --loja ORTOBOM pega todas as filiais Ortobom
            pares = [x for x in pares if x[0] == a.loja.upper() or x[0].startswith(a.loja.upper() + " ")]
        if a.ano:
            pares = [x for x in pares if x[1] == a.ano or (x[4] == "ortobom" and x[1].startswith(a.ano))]
        if not pares:
            sys.exit(f"Nenhum par de PDFs encontrado em {ENTRADA / 'vendas'}\\<LOJA>\\")
        for loja, k, p, v, tipo in pares:
            if tipo == "ortobom":
                print(f"\n==================== {loja} {k}: {p.name}  +  {v.name if v else '(sem custos)'}")
                pasta_saida = "vendas_" + re.sub(r"\W+", "_", loja) + "_" + k
                processar_ortobom(p, v, RAIZ / "saida" / pasta_saida, a.sem_banco, loja)
                continue
            print(f"\n==================== {loja} {k}: {p.name}  +  {v.name}")
            processar(p, v, RAIZ / "saida" / f"vendas_{loja}_{k or 'unico'}", a.sem_banco, loja)
    print("\nPronto.")


if __name__ == "__main__":
    main()
