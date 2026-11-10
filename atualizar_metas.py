r"""
Metas de venda: carrega config\metas_vendas.csv e config\dias_sem_venda.csv no banco.
Cada execução substitui todas as metas pelo conteúdo dos arquivos (o CSV é a fonte).

    python atualizar_metas.py

A meta diária (meta do mês / dias de venda, sem domingos e dias fechados) fica em
vendas.vw_meta_venda_dia e entra na fato principal com origem 'Meta de vendas'.
"""
import csv, os, sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

RAIZ = Path(__file__).resolve().parent


def ler_env():
    env = RAIZ / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.strip().startswith("#"):
                k, v = l.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def ler_csv(nome):
    p = RAIZ / "config" / nome
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader((l for l in f if l.strip() and not l.startswith("#")), delimiter=";"))


def valor(s):
    s = (s or "").replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def main():
    ler_env()
    erros, metas, vistos = [], [], set()
    for n, r in enumerate(ler_csv("metas_vendas.csv"), start=2):
        try:
            ano, mes, loja, v = int(r["ano"]), int(r["mes"]), r["loja"].strip().upper(), valor(r["meta_mes"])
            if not 1 <= mes <= 12 or not loja:
                raise ValueError("mês ou loja inválidos")
        except (KeyError, ValueError, InvalidOperation, TypeError) as e:
            erros.append(f"metas_vendas.csv linha {n}: {r} ({e})"); continue
        if (ano, mes, loja) in vistos:
            erros.append(f"metas_vendas.csv: {loja} {mes:02d}/{ano} aparece duas vezes"); continue
        vistos.add((ano, mes, loja)); metas.append((ano, mes, loja, v))
    fechados = []
    for n, r in enumerate(ler_csv("dias_sem_venda.csv"), start=2):
        try:
            d = r["data"].strip()
            if "/" in d:
                dd, mm, aa = d.split("/"); d = f"{aa}-{int(mm):02d}-{int(dd):02d}"
            fechados.append((d, (r.get("loja") or "").strip().upper(), (r.get("descricao") or "").strip()))
        except Exception as e:
            erros.append(f"dias_sem_venda.csv linha {n}: {r} ({e})")
    if erros:
        print("Nada foi gravado. Corrija:"); [print(" -", e) for e in erros]; sys.exit(1)

    conn = psycopg2.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                            dbname=os.environ.get("PGDATABASE", "ze_maria"), user=os.environ.get("PGUSER", "postgres"),
                            password=os.environ.get("PGPASSWORD"))
    with conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('vendas.meta_venda')")
        if cur.fetchone()[0] is None:
            sys.exit("Tabela vendas.meta_venda não existe: rode python criar_banco.py antes.")
        cur.execute("DELETE FROM vendas.meta_venda"); cur.execute("DELETE FROM vendas.dia_sem_venda")
        if metas:
            execute_values(cur, "INSERT INTO vendas.meta_venda (ano, mes, loja, meta_mes) VALUES %s", metas)
        if fechados:
            execute_values(cur, "INSERT INTO vendas.dia_sem_venda (data, loja, descricao) VALUES %s ON CONFLICT DO NOTHING", fechados)
        cur.execute("""SELECT ano, mes, loja, meta_mes, max(dias_venda_mes), round(max(meta_dia), 2)
                       FROM vendas.vw_meta_venda_dia GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 4 DESC""")
        linhas = cur.fetchall()
    conn.close()
    br = lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    print(f"Metas carregadas: {len(metas)} (loja x mês) | dias sem venda: {len(fechados)}")
    tot = {}
    for ano, mes, loja, meta, dias, dia in linhas:
        print(f"  {mes:02d}/{ano}  {loja:<20} meta {br(meta):>16}  {dias} dias  meta diária {br(dia)}")
        tot[(ano, mes)] = tot.get((ano, mes), 0) + meta
    for (ano, mes), t in sorted(tot.items()):
        print(f"  {mes:02d}/{ano}  {'TOTAL DO GRUPO':<20} meta {br(t):>16}")


if __name__ == "__main__":
    main()
