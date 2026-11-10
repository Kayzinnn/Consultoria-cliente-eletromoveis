"""
Liga os itens do relatório "Lucratividade por produto" às vendas (controles) do
relatório "Lucratividade por venda". Os relatórios não trazem essa ligação:

  * o relatório por produto soma, por dia, todas as unidades do mesmo produto
    (ex.: "2 ventiladores" podem ser 2 vendas diferentes, com preços diferentes);
  * por isso cada linha é desmembrada em unidades (custo unitário = custo/qtd) e,
    dia a dia, buscamos a combinação em que cada venda soma exatamente o seu custo
    e o seu líquido; o líquido de uma linha dividida entre vendas é deduzido.

Gera saida/fato_venda_item_vinculo.csv (ponte item x venda), com:
  status UNICO        -> só existe uma combinação possível
         AMBIGUO      -> existe mais de uma (ficamos com a 1ª; não usar para análise por venda)
         SEM_VINCULO  -> nenhuma combinação fecha (ex.: custo do produto alterado no cadastro)
Uso: python vincular_itens_vendas.py saida/
"""
import csv, sys
from collections import defaultdict, Counter
from decimal import Decimal
from pathlib import Path

LIMITE = 300000


def cents(x): return int((Decimal(x) * 100).to_integral_value())


def unidades(linha):
    q, c = linha["qtd"], linha["custo"]
    base, resto = divmod(c, q)
    return [base + (1 if k < resto else 0) for k in range(q)]


def resolver(linhas, vendas):
    """linhas: [{id,qtd,liq,custo}]; vendas: [{controle,liq,custo}] -> soluções [{controle: Counter(id->qtd)}]"""
    units = []
    for l in linhas:
        for cu in unidades(l):
            units.append((l["id"], cu))
    units.sort(key=lambda u: -u[1])
    vendas = sorted(vendas, key=lambda v: -v["custo"])
    sols, nodes = [], [0]
    liq_linha = {l["id"]: l["liq"] for l in linhas}
    qtd_linha = {l["id"]: l["qtd"] for l in linhas}

    def consistente(atrib):
        # atrib: lista (venda_idx -> Counter(linha->qtd)). Deduz líquido de linhas divididas.
        aloc = {}
        for k, cnt in enumerate(atrib):
            inteiras = [lid for lid, q in cnt.items() if q == qtd_linha[lid]]
            parciais = [lid for lid, q in cnt.items() if q != qtd_linha[lid]]
            resto = vendas[k]["liq"] - sum(liq_linha[l] for l in inteiras)
            for l in inteiras: aloc[(k, l)] = liq_linha[l]
            if len(parciais) > 1:
                return None            # indeterminado: mais de uma linha dividida na mesma venda
            if parciais:
                if resto < 0: return None
                aloc[(k, parciais[0])] = resto
            elif resto != 0:
                return None
        soma = defaultdict(int)
        for (k, l), v in aloc.items(): soma[l] += v
        return aloc if all(soma[l] == liq_linha[l] for l in liq_linha) else None

    def rec(k, livres, atrib):
        if nodes[0] > LIMITE or len(sols) >= 2: return
        if k == len(vendas):
            if livres: return
            aloc = consistente(atrib)
            if aloc is None: return
            assin = frozenset((vendas[i]["controle"], l, q) for i, c in enumerate(atrib) for l, q in c.items())
            if all(s[0] != assin for s in sols):
                sols.append((assin, [dict(c) for c in atrib], aloc))
            return
        v = vendas[k]
        if v["custo"] == 0 and v["liq"] == 0 or v["tipo"] != "VENDA":
            atrib.append(Counter()); rec(k + 1, livres, atrib); atrib.pop(); return

        def sub(p, rest, esc):
            nodes[0] += 1
            if nodes[0] > LIMITE or len(sols) >= 2: return
            if rest == 0 and esc:
                cnt = Counter(units[j][0] for j in esc)
                atrib.append(cnt)
                rec(k + 1, [j for j in livres if j not in esc], atrib)
                atrib.pop(); return
            ult = None
            for idx in range(p, len(livres)):
                j = livres[idx]; u = units[j]
                if u[1] > rest or u == ult: continue   # pula unidades idênticas repetidas
                ult = u
                sub(idx + 1, rest - u[1], esc + [j])
        sub(0, v["custo"], [])
    rec(0, list(range(len(units))), [])
    return vendas, sols, nodes[0] > LIMITE


def main():
    d = Path(sys.argv[1])
    itens = list(csv.DictReader(open(d / "fato_venda_item.csv", encoding="utf-8"), delimiter=";"))
    vendas = list(csv.DictReader(open(d / "fato_venda.csv", encoding="utf-8"), delimiter=";"))
    por_i, por_v = defaultdict(list), defaultdict(list)
    for r in itens:
        por_i[r["data_venda"]].append(dict(id=int(r["seq_dia"]), qtd=int(r["qtd"]), liq=cents(r["vr_liquido"]),
                                           custo=cents(r["vr_custo"]), row=r))
    for r in vendas:
        por_v[r["data_venda"]].append(dict(controle=r["controle"], liq=cents(r["vr_liquido"]), custo=cents(r["vr_custo"]), tipo=r["tipo"]))
    out, st = [], Counter()
    for dia in sorted(por_i):
        ls = por_i[dia]
        vs, sols, estourou = resolver(ls, por_v.get(dia, []))
        status = "SEM_VINCULO" if not sols else ("UNICO" if len(sols) == 1 and not estourou else "AMBIGUO")
        byid = {l["id"]: l for l in ls}
        if not sols:
            for l in ls:
                out.append(dict(cnpj=l["row"]["cnpj"], loja=l["row"].get("loja", ""), data_venda=dia, seq_dia=l["id"], controle="", qtd=l["qtd"],
                                vr_liquido=f'{l["liq"]/100:.2f}', vr_custo=f'{l["custo"]/100:.2f}', status_vinculo=status))
                st[status] += 1
            continue
        _, atrib, aloc = sols[0]
        for k, cnt in enumerate(atrib):
            for lid, q in cnt.items():
                l = byid[lid]
                custo = sum(unidades(l)[:q]) if q != l["qtd"] else l["custo"]
                out.append(dict(cnpj=l["row"]["cnpj"], loja=l["row"].get("loja", ""), data_venda=dia, seq_dia=lid, controle=vs[k]["controle"], qtd=q,
                                vr_liquido=f'{aloc[(k, lid)]/100:.2f}', vr_custo=f'{custo/100:.2f}', status_vinculo=status))
        for l in ls: st[status] += 1
    cols = ["cnpj", "loja", "data_venda", "seq_dia", "controle", "qtd", "vr_liquido", "vr_custo", "status_vinculo"]
    with open(d / "fato_venda_item_vinculo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";"); w.writeheader(); w.writerows(out)
    tot = sum(st.values())
    for k in ("UNICO", "AMBIGUO", "SEM_VINCULO"):
        print(f"{k:12s} {st[k]:5d} linhas de item ({st[k]/tot:.1%})")


if __name__ == "__main__":
    main()
