"""
Carrega os CSVs gerados por extrair_vendas_ze_maria.py + vincular_itens_vendas.py
no PostgreSQL (schema "vendas").

Carga idempotente: para o CNPJ do relatório, apaga os dados do PERÍODO LISTADO
no PDF e insere de novo. Pode rodar quantas vezes quiser com o mesmo arquivo;
um relatório novo (ex.: só novembro) substitui só novembro.

Conexão: variáveis de ambiente padrão do PostgreSQL (PGHOST, PGPORT, PGDATABASE,
PGUSER, PGPASSWORD) ou arquivo .env na pasta do projeto.
Uso: python carregar_banco.py saida/
Requer: pip install psycopg2-binary
"""
import csv, json, os, sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

RAIZ = Path(__file__).resolve().parent.parent


def ler_env():
    env = RAIZ / ".env"
    if env.exists():
        for linha in env.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def ler_csv(path):
    with open(path, encoding="utf-8") as f:
        return [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(f, delimiter=";")]


def main():
    saida = Path(sys.argv[1] if len(sys.argv) > 1 else "saida")
    ler_env()
    meta = json.loads((saida / "carga_meta.json").read_text(encoding="utf-8"))
    if not meta["validacao_ok"]:
        sys.exit("A extração tem problemas de validação (ver carga_meta.json). Carga cancelada.")

    itens = ler_csv(saida / "fato_venda_item.csv")
    vendas = ler_csv(saida / "fato_venda.csv")
    vinc = ler_csv(saida / "fato_venda_item_vinculo.csv")
    empresa = ler_csv(saida / "dim_empresa.csv")[0]
    regras = ler_csv(RAIZ / "config" / "regras_categoria.csv")
    cnpj = meta["cnpj"]
    loja = meta.get("loja", "")
    p_ini, p_fim = meta["periodo_produto"]
    v_ini, v_fim = meta["periodo_venda"]

    conn = psycopg2.connect("")   # usa PG* do ambiente
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SET search_path TO vendas")

            cur.execute("""INSERT INTO dim_empresa (cnpj, razao_social, uf, inscricao_estadual)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT (cnpj) DO UPDATE SET razao_social = EXCLUDED.razao_social,
                               uf = EXCLUDED.uf, inscricao_estadual = EXCLUDED.inscricao_estadual""",
                        (cnpj, empresa["razao_social"], empresa["uf"], empresa["inscricao_estadual"]))

            execute_values(cur, """INSERT INTO regra_categoria (prefixo, categoria, grupo) VALUES %s
                                   ON CONFLICT (prefixo) DO UPDATE SET categoria = EXCLUDED.categoria,
                                       grupo = EXCLUDED.grupo""",
                           [(r["prefixo"], r["categoria"], r["grupo"]) for r in regras])

            # produtos: mantém categoria_manual/grupo_manual já preenchidos
            prods = {}
            for r in itens:
                p = prods.setdefault(r["cod_produto"], dict(desc=r["descricao"], ini=r["data_venda"], fim=r["data_venda"]))
                if r["data_venda"] >= p["fim"]:
                    p["fim"], p["desc"] = r["data_venda"], r["descricao"]
                p["ini"] = min(p["ini"], r["data_venda"])
            execute_values(cur, """INSERT INTO dim_produto (cod_produto, descricao, primeira_venda, ultima_venda) VALUES %s
                                   ON CONFLICT (cod_produto) DO UPDATE SET
                                       descricao = EXCLUDED.descricao,
                                       primeira_venda = LEAST(dim_produto.primeira_venda, EXCLUDED.primeira_venda),
                                       ultima_venda = GREATEST(dim_produto.ultima_venda, EXCLUDED.ultima_venda),
                                       atualizado_em = now()""",
                           [(k, v["desc"], v["ini"], v["fim"]) for k, v in prods.items()])

            cur.execute("""INSERT INTO controle_carga (cnpj, loja, arquivo_produto, periodo_produto_ini, periodo_produto_fim,
                                arquivo_venda, periodo_venda_ini, periodo_venda_fim, linhas_item, linhas_venda, total_liquido)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id_carga""",
                        (cnpj, loja, meta["arquivo_produto"], p_ini, p_fim, meta["arquivo_venda"], v_ini, v_fim,
                         meta["linhas_item"], meta["linhas_venda"], meta["total_liquido_vendas"]))
            id_carga = cur.fetchone()[0]

            # substitui o período do relatório
            cur.execute("DELETE FROM fato_venda_item WHERE cnpj=%s AND loja=%s AND data_venda BETWEEN %s AND %s", (cnpj, loja, p_ini, p_fim))
            n_del_i = cur.rowcount
            cur.execute("DELETE FROM fato_venda WHERE cnpj=%s AND loja=%s AND data_venda BETWEEN %s AND %s", (cnpj, loja, v_ini, v_fim))
            n_del_v = cur.rowcount

            execute_values(cur, """INSERT INTO fato_venda_item (cnpj, loja, data_venda, seq_dia, cod_produto, descricao_original, qtd,
                                       vr_bruto, vr_desc_acres, vr_liquido, vr_custo, vr_lucro,
                                       arquivo_origem, pagina, id_carga) VALUES %s""",
                           [(cnpj, loja, r["data_venda"], r["seq_dia"], r["cod_produto"], r["descricao"], r["qtd"], r["vr_bruto"],
                             r["vr_desc_acres"], r["vr_liquido"], r["vr_custo"], r["vr_lucro"],
                             r["arquivo_origem"], r["pagina"], id_carga) for r in itens], page_size=1000)
            execute_values(cur, """INSERT INTO fato_venda (cnpj, loja, controle, data_venda, data_hora, tipo, vr_bruto, vr_desc_acres,
                                       vr_liquido, vr_custo, vr_lucro, vr_coluna_extra,
                                       arquivo_origem, pagina, id_carga) VALUES %s""",
                           [(cnpj, loja, r["controle"], r["data_venda"], r["data_hora"], r["tipo"], r["vr_bruto"], r["vr_desc_acres"],
                             r["vr_liquido"], r["vr_custo"], r["vr_lucro"], r["vr_coluna_extra"],
                             r["arquivo_origem"], r["pagina"], id_carga) for r in vendas], page_size=1000)
            execute_values(cur, """INSERT INTO fato_venda_item_vinculo (cnpj, loja, data_venda, seq_dia, controle, qtd,
                                       vr_liquido, vr_custo, status_vinculo, id_carga) VALUES %s""",
                           [(cnpj, loja, r["data_venda"], r["seq_dia"], r["controle"] or "", r["qtd"], r["vr_liquido"],
                             r["vr_custo"], r["status_vinculo"], id_carga) for r in vinc], page_size=1000)

            # conferência dentro da transação: banco precisa bater com o PDF
            cur.execute("SELECT COALESCE(sum(vr_liquido),0) FROM fato_venda_item WHERE id_carga=%s", (id_carga,))
            tot_i = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(sum(vr_liquido),0) FROM fato_venda WHERE id_carga=%s", (id_carga,))
            tot_v = cur.fetchone()[0]
            if f"{tot_i:.2f}" != meta["total_liquido_itens"] or f"{tot_v:.2f}" != meta["total_liquido_vendas"]:
                raise RuntimeError(f"Totais no banco não batem com o PDF: itens {tot_i} / vendas {tot_v}")

        print(f"Carga {id_carga} OK — {meta['razao_social']} ({cnpj}) — loja {loja or '(sem loja)'}")
        print(f"  itens : {len(itens):5d} inseridos ({n_del_i} substituídos) — {p_ini} a {p_fim}")
        print(f"  vendas: {len(vendas):5d} inseridas ({n_del_v} substituídas) — {v_ini} a {v_fim}")
        print(f"  líquido conferido: R$ {tot_v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
