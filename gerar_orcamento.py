r"""
Orçamento da DRE do mês: receitas, CMV e despesas por conta e loja.

    python gerar_orcamento.py                 # mês atual
    python gerar_orcamento.py --mes 2026-11   # um mês específico
    python gerar_orcamento.py --mes 2026-12 --base 3

Regra (base = os N meses fechados anteriores ao mês, padrão 3):
  - Despesas (caixa diário, linhas da DRE): média mensal da base, por conta e loja.
  - Loja com meta de vendas no mês (config/metas_vendas.csv):
        receita líquida orçada = meta;
        descontos, outras receitas e CMV = % sobre a receita líquida na base x meta;
        receita bruta = meta - descontos - outras receitas.
  - Loja sem meta: receitas e CMV também pela média da base.
Rodar de novo para o mesmo mês substitui o orçamento daquele mês (e só dele).
Rode python atualizar_metas.py antes, se a meta do mês mudou.
"""
import argparse, os, sys
from datetime import date
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


SQL = """
WITH base AS (
    SELECT natureza, grupo_dre, conta, loja, negocio, origem, sum(valor) AS valor
    FROM financeiro.vw_fato_principal
    WHERE entra_no_dre AND data >= %(ini)s AND data < %(alvo)s
      AND origem IN ('ERP vendas', 'Caixa diário')
    GROUP BY 1, 2, 3, 4, 5, 6
), rl AS (            -- receita líquida da base por loja
    SELECT loja, sum(valor) AS rl FROM base WHERE origem = 'ERP vendas' AND natureza = 'Receita' GROUP BY 1
), meta AS (
    SELECT loja, meta_mes FROM vendas.meta_venda WHERE ano = %(ano)s AND mes = %(mes)s
), vendas AS (        -- receitas e CMV: percentual da receita líquida x meta, ou média da base
    SELECT b.natureza, b.grupo_dre, b.conta, b.loja, b.negocio,
           CASE WHEN m.meta_mes IS NOT NULL AND rl.rl > 0 THEN b.valor / rl.rl * m.meta_mes
                ELSE b.valor / %(n)s END AS valor,
           CASE WHEN m.meta_mes IS NOT NULL AND rl.rl > 0 THEN 'meta x %% da receita líquida nos últimos ' || %(n)s || ' meses'
                ELSE 'média dos últimos ' || %(n)s || ' meses' END AS criterio,
           m.meta_mes IS NOT NULL AND rl.rl > 0 AS pela_meta
    FROM base b
    LEFT JOIN rl USING (loja)
    LEFT JOIN meta m USING (loja)
    WHERE b.origem = 'ERP vendas'
), ajuste AS (        -- receita bruta fecha a receita líquida na meta: meta - descontos - outras receitas
    SELECT loja, m.meta_mes - coalesce(sum(v.valor) FILTER (WHERE v.grupo_dre <> 'Receita bruta de vendas'), 0) AS bruta
    FROM vendas v JOIN meta m USING (loja)
    WHERE v.pela_meta AND v.natureza = 'Receita'
    GROUP BY loja, m.meta_mes
)
SELECT v.natureza, v.grupo_dre, v.conta, v.loja, v.negocio,
       round(CASE WHEN v.grupo_dre = 'Receita bruta de vendas' AND a.bruta IS NOT NULL THEN a.bruta ELSE v.valor END, 2),
       'venda', v.criterio
FROM vendas v LEFT JOIN ajuste a ON a.loja = v.loja AND v.grupo_dre = 'Receita bruta de vendas'
UNION ALL
SELECT natureza, grupo_dre, conta, loja, negocio, round(valor / %(n)s, 2), 'corridos',
       'média dos últimos ' || %(n)s || ' meses'
FROM base WHERE origem = 'Caixa diário'
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", help="AAAA-MM (padrão: mês atual)")
    ap.add_argument("--base", type=int, default=3, help="quantos meses fechados anteriores entram na média")
    a = ap.parse_args()
    hoje = date.today()
    ano, mes = map(int, a.mes.split("-")) if a.mes else (hoje.year, hoje.month)
    alvo = date(ano, mes, 1)
    m0 = ano * 12 + mes - 1 - a.base
    ini = date(m0 // 12, m0 % 12 + 1, 1)

    ler_env()
    conn = psycopg2.connect(host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
                            dbname=os.environ.get("PGDATABASE", "ze_maria"), user=os.environ.get("PGUSER", "postgres"),
                            password=os.environ.get("PGPASSWORD"))
    with conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('financeiro.orcamento')")
        if cur.fetchone()[0] is None:
            sys.exit("Tabela financeiro.orcamento não existe: rode python criar_banco.py antes.")
        cur.execute(SQL, dict(ini=ini, alvo=alvo, ano=ano, mes=mes, n=a.base))
        linhas = [r for r in cur.fetchall() if r[5] != 0]
        if not linhas:
            sys.exit(f"Sem dados de {ini:%m/%Y} a {alvo:%m/%Y} (exclusive) para montar a base. Nada foi gravado.")
        cur.execute("DELETE FROM financeiro.orcamento WHERE ano = %s AND mes = %s", (ano, mes))
        execute_values(cur, """INSERT INTO financeiro.orcamento
                               (ano, mes, natureza, grupo_dre, conta, loja, negocio, valor, distribuir, criterio) VALUES %s""",
                       [(ano, mes, *r) for r in linhas])
        cur.execute("""SELECT o.grupo_dre, sum(o.valor) FROM financeiro.orcamento o
                       LEFT JOIN financeiro.dim_grupo_dre g USING (grupo_dre)
                       WHERE ano = %s AND mes = %s GROUP BY o.grupo_dre, g.ordem ORDER BY g.ordem""", (ano, mes))
        resumo = cur.fetchall()
    conn.close()
    br = lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    print(f"Orçamento {mes:02d}/{ano}: {len(linhas)} linhas (conta x loja) | base {ini:%m/%Y} a {(alvo.replace(day=1)).strftime('%m/%Y')} exclusive, média de {a.base} meses")
    for g, v in resumo:
        print(f"  {g:<32} {br(v):>18}")
    print(f"  {'RESULTADO ORÇADO':<32} {br(sum(v for _, v in resumo)):>18}")


if __name__ == "__main__":
    main()
