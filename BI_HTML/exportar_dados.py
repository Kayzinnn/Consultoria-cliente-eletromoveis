"""
Exporta os dados do PostgreSQL para o BI em HTML.

Lê as mesmas views que o Power BI usa e grava BI_HTML/site/dados/dados.js
(um arquivo só, compacto, que o index.html carrega). Rode depois de atualizar o banco:

    python BI_HTML/exportar_dados.py

O arquivo gerado tem dados da cliente: fica fora do git (.gitignore) e só vai
para a hospedagem protegida por login.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import psycopg2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
SAIDA = AQUI / "site" / "dados" / "dados.js"
EPOCA = dt.date(1970, 1, 1)

# Colunas de texto viram índices de dicionário para o arquivo ficar pequeno.
TEXTOS = ["origem", "natureza", "grupo_dre", "conta", "loja", "negocio",
          "grupo_produto", "categoria_produto", "descricao"]

SQL_FATO = """
SELECT data::date, origem, natureza, grupo_dre, conta, loja, negocio,
       grupo_produto, categoria_produto, descricao,
       COALESCE(entra_no_dre, false), SUM(COALESCE(qtd, 0)), SUM(valor)
FROM financeiro.vw_fato_principal
WHERE data IS NOT NULL
GROUP BY 1,2,3,4,5,6,7,8,9,10,11
HAVING SUM(valor) <> 0 OR SUM(COALESCE(qtd, 0)) <> 0
ORDER BY 1
"""

SQL_ORC = """
SELECT data::date, natureza, grupo_dre, loja, SUM(valor)
FROM financeiro.vw_orcamento_dia
GROUP BY 1,2,3,4
HAVING SUM(valor) <> 0
ORDER BY 1
"""

SQL_GRUPOS = """
SELECT grupo_dre, ordem, secao, agrupamento, ordem_agrupamento
FROM financeiro.dim_grupo_dre
ORDER BY ordem
"""


def ler_env():
    env = RAIZ / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.strip().startswith("#"):
                k, v = l.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


class Dicionario:
    def __init__(self):
        self.valores, self.idx = [], {}

    def __call__(self, v):
        if v is None:
            return -1
        if v not in self.idx:
            self.idx[v] = len(self.valores)
            self.valores.append(v)
        return self.idx[v]


def dia(d):
    return (d - EPOCA).days


def main():
    ler_env()
    conn = psycopg2.connect("")
    cur = conn.cursor()
    dic = {c: Dicionario() for c in TEXTOS}

    cur.execute(SQL_FATO)
    fato = {c: [] for c in ["d"] + TEXTOS + ["dre", "q", "v"]}
    n = 0
    for r in cur:
        fato["d"].append(dia(r[0]))
        for i, c in enumerate(TEXTOS, start=1):
            fato[c].append(dic[c](r[i]))
        fato["dre"].append(1 if r[10] else 0)
        fato["q"].append(int(r[11] or 0))
        fato["v"].append(round(float(r[12] or 0), 2))
        n += 1

    cur.execute(SQL_ORC)
    orc = {"d": [], "natureza": [], "grupo_dre": [], "loja": [], "v": []}
    for d, nat, grp, loja, v in cur:
        orc["d"].append(dia(d))
        orc["natureza"].append(dic["natureza"](nat))
        orc["grupo_dre"].append(dic["grupo_dre"](grp))
        orc["loja"].append(dic["loja"](loja))
        orc["v"].append(round(float(v or 0), 2))

    cur.execute(SQL_GRUPOS)
    grupos = [dict(grupo_dre=g, ordem=o, secao=s, agrupamento=a, ordem_agrupamento=oa)
              for g, o, s, a, oa in cur]
    conn.close()

    dados = {
        "gerado_em": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "dic": {c: dic[c].valores for c in TEXTOS},
        "fato": fato,
        "orc": orc,
        "grupos_dre": grupos,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    SAIDA.write_text("window.DADOS=" + texto + ";\n", encoding="utf-8")
    print(f"BI HTML: {n:,} linhas da fato, {len(orc['d']):,} do orçamento "
          f"-> {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e6:.1f} MB)".replace(",", "."))


if __name__ == "__main__":
    try:
        main()
    except psycopg2.OperationalError as e:
        sys.exit(f"Não consegui conectar no banco (confira o .env): {e}")
