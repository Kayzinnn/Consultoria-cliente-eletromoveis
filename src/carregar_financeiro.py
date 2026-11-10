"""
Carrega no PostgreSQL (schema "financeiro") os CSVs de contas a pagar e caixa diário.

As planilhas são cumulativas e não têm ID; por isso cada arquivo é recarregado inteiro
(apaga o que veio dele e insere de novo, numa única transação). Se o arquivo não mudou
desde a última carga (mesmo hash), é pulado — use --forcar para recarregar mesmo assim.

Uso: python carregar_financeiro.py saida\\financeiro [--forcar]
"""
import csv, json, os, sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values, Json

RAIZ = Path(__file__).resolve().parent.parent


def ler_env():
    env = RAIZ / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.strip().startswith("#"):
                k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def ler_csv(p):
    with open(p, encoding="utf-8") as f:
        return [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(f, delimiter=";")]


def ja_carregado(cur, fonte, nome, sha):
    cur.execute("""SELECT sha256 FROM controle_carga WHERE fonte=%s AND arquivo=%s
                   ORDER BY id_carga DESC LIMIT 1""", (fonte, nome))
    r = cur.fetchone()
    return r is not None and r[0] == sha


def nova_carga(cur, fonte, m, linhas, total, alertas):
    cur.execute("""INSERT INTO controle_carga (fonte, arquivo, caminho, sha256, modificado_em, linhas, total_valor, alertas)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id_carga""",
                (fonte, m["nome"], m["arquivo"], m["sha256"], m["modificado_em"], linhas, total, Json(alertas)))
    return cur.fetchone()[0]


def carregar_contas_pagar(cur, d, forcar):
    meta = json.loads((d / "contas_pagar_meta.json").read_text(encoding="utf-8"))
    if not forcar and ja_carregado(cur, "CONTAS_PAGAR", meta["nome"], meta["sha256"]):
        print(f"Contas a pagar: {meta['nome']} sem alteração desde a última carga — pulado"); return
    rows = ler_csv(d / "fato_conta_pagar.csv")
    idc = nova_carga(cur, "CONTAS_PAGAR", meta, len(rows), meta["total_valor"], meta["avisos"])
    cur.execute("DELETE FROM fato_conta_pagar WHERE arquivo=%s", (meta["nome"],)); apagadas = cur.rowcount
    cols = ["aba", "linha_planilha", "data_vencimento", "fornecedor", "forma_pgto", "forma_pgto_original", "num_cheque",
            "banco_cheque", "valor", "parcela_original", "parcela_num", "parcela_total", "loja", "loja_original",
            "nota_fiscal", "observacao", "possivel_pessoal", "cor_marcacao"]
    execute_values(cur, f"INSERT INTO fato_conta_pagar (arquivo, {', '.join(cols)}, id_carga) VALUES %s",
                   [(meta["nome"], *[(r[c] == "1") if c == "possivel_pessoal" else r[c] for c in cols], idc) for r in rows],
                   page_size=2000)
    cur.execute("SELECT count(*), COALESCE(sum(valor),0) FROM fato_conta_pagar WHERE id_carga=%s", (idc,))
    n, tot = cur.fetchone()
    if n != len(rows) or f"{tot:.2f}" != meta["total_valor"]:
        raise RuntimeError(f"Contas a pagar: banco ({n} / {tot}) não bate com a planilha ({len(rows)} / {meta['total_valor']})")
    print(f"Contas a pagar: carga {idc} — {n} linhas (substituiu {apagadas}) | R$ {tot:,.2f} | {len(meta['avisos'])} aviso(s)")


def carregar_caixa(cur, d, forcar):
    meta = json.loads((d / "caixa_meta.json").read_text(encoding="utf-8"))
    if not meta["validacao_ok"]:
        raise RuntimeError("Caixa diário com erro de extração (ver caixa_meta.json)")
    lanc = ler_csv(d / "fato_caixa_lancamento.csv")
    dias = ler_csv(d / "fato_caixa_dia.csv")
    for m in meta["arquivos"]:
        if not forcar and ja_carregado(cur, "CAIXA_DIARIO", m["nome"], m["sha256"]):
            print(f"Caixa diário: {m['nome']} sem alteração desde a última carga — pulado"); continue
        L = [r for r in lanc if r["arquivo"] == m["nome"]]
        D = [r for r in dias if r["arquivo"] == m["nome"]]
        total = sum(float(r["valor"]) for r in L)
        idc = nova_carga(cur, "CAIXA_DIARIO", m, len(L), f"{total:.2f}", meta["avisos"])
        cur.execute("DELETE FROM fato_caixa_lancamento WHERE arquivo=%s", (m["nome"],))
        cur.execute("DELETE FROM fato_caixa_dia WHERE arquivo=%s", (m["nome"],))
        cl = ["aba", "celula", "data", "tipo", "ordem", "descricao", "valor", "loja", "meio", "conta", "entra_no_total"]
        execute_values(cur, f"INSERT INTO fato_caixa_lancamento (arquivo, {', '.join(cl)}, id_carga) VALUES %s",
                       [(m["nome"], *[(r[c] == "1") if c == "entra_no_total" else r[c] for c in cl], idc) for r in L],
                       page_size=2000)
        cd = ["aba", "celula", "data", "saldo_inicial", "total_entrada", "total_saida", "saldo_final",
              "saldo_final_recalculado", "saldo_final_anterior", "diferenca_abertura", "entradas_fora_total", "saidas_fora_total"]
        execute_values(cur, f"INSERT INTO fato_caixa_dia (arquivo, {', '.join(cd)}, id_carga) VALUES %s",
                       [(m["nome"], *[r[c] for c in cd], idc) for r in D])
        cur.execute("SELECT count(*), COALESCE(sum(valor),0) FROM fato_caixa_lancamento WHERE id_carga=%s", (idc,))
        n, tot = cur.fetchone()
        if n != len(L) or abs(float(tot) - total) > 0.005:
            raise RuntimeError(f"Caixa: banco ({n} / {tot}) não bate com a planilha ({len(L)} / {total:.2f})")
        print(f"Caixa diário: carga {idc} — {m['nome']}: {len(D)} dias, {n} lançamentos")


def main():
    d = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "saida/financeiro")
    forcar = "--forcar" in sys.argv
    ler_env()
    conn = psycopg2.connect("")
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SET search_path TO financeiro")
            if (d / "contas_pagar_meta.json").exists():
                carregar_contas_pagar(cur, d, forcar)
            if (d / "caixa_meta.json").exists():
                carregar_caixa(cur, d, forcar)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
