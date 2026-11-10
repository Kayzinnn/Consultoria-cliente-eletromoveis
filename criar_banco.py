"""
Cria o banco (se não existir) e roda os scripts da pasta "sql" — não precisa do psql.
Pode rodar de novo sem problema: os scripts só criam o que ainda não existe e
atualizam as views.

Uso: python criar_banco.py
Conexão: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD do arquivo .env
"""
import os, sys
from pathlib import Path

import psycopg2

RAIZ = Path(__file__).resolve().parent


def ler_env():
    env = RAIZ / ".env"
    if not env.exists():
        sys.exit("Arquivo .env não encontrado nesta pasta. Copie o .env.example para .env e preencha.")
    for l in env.read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main():
    ler_env()
    banco = os.environ.get("PGDATABASE", "ze_maria")
    params = dict(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                  user=os.environ.get("PGUSER", "postgres"), password=os.environ.get("PGPASSWORD"))
    try:
        adm = psycopg2.connect(dbname="postgres", **params)
    except psycopg2.OperationalError as e:
        sys.exit(f"Não consegui conectar no PostgreSQL em {params['host']}:{params['port']}.\n"
                 f"Confira se ele está instalado/rodando e a senha no .env.\nDetalhe: {e}")
    except UnicodeDecodeError:
        # PostgreSQL em português devolve o erro com acento e o psycopg2 no Windows não decodifica.
        sys.exit(f"O PostgreSQL recusou o login do usuário '{params['user']}'.\n"
                 "Quase sempre é senha errada: confira PGPASSWORD no .env "
                 "(a senha definida na instalação, sem aspas nem espaços).")
    adm.autocommit = True
    with adm.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (banco,))
        if cur.fetchone():
            print(f"Banco {banco} já existe.")
        else:
            cur.execute(f'CREATE DATABASE "{banco}" ENCODING \'UTF8\' TEMPLATE template0')
            print(f"Banco {banco} criado.")
    adm.close()

    conn = psycopg2.connect(dbname=banco, **params)
    try:
        with conn, conn.cursor() as cur:
            for f in sorted((RAIZ / "sql").glob("*.sql")):
                cur.execute(f.read_text(encoding="utf-8"))
                print(f"  ok  {f.name}")
            cur.execute("""SELECT table_schema, count(*) FROM information_schema.tables
                           WHERE table_schema IN ('vendas','financeiro') GROUP BY 1 ORDER BY 1""")
            for schema, n in cur.fetchall():
                print(f"  schema {schema}: {n} tabelas/views")
    finally:
        conn.close()
    print("Pronto. Próximo passo: processa_vendas.py e atualizar_financeiro.py")


if __name__ == "__main__":
    main()
