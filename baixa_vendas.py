r"""
baixa_vendas.py — vendas + custo das lojas Ortobom direto do RP Sistema (Conception Web), sem PDF.

Substitui o par de PDFs "venda de produtos por data" + "produtos com margem de lucro":
a tela do sistema monta esses relatórios a partir de uma API interna em JSON, e o script
lê essa mesma API depois de fazer login pela tela (Playwright).

Para cada filial (Graça, Carnaubal, Mucambo) e período:
  1. modo "produtos-vendidos-data" -> data, produto, quantidade, valor, desconto, acréscimo
  2. modo "produtos-lucro"         -> custo total por produto no período
  custo da linha = quantidade x custo unitário do produto (custo total / quantidade no período)
  — a mesma regra do src/extrair_vendas_ortobom.py, inclusive config/custo_estimado.csv
  para produto sem custo.
Gera saida\vendas_ORTOBOM_<LOJA>_<inicio>_<fim>\ no mesmo layout do fluxo dos PDFs e carrega
no banco com src/carregar_banco.py (substitui só aquele período daquela loja).

    python baixa_vendas.py                                   # dia 1 do mês até ontem, todas as filiais
    python baixa_vendas.py --inicio 01/01/2026 --fim 31/10/2026
    python baixa_vendas.py --filial 4                        # só uma filial (id_empresa: 2, 3, 4)
    python baixa_vendas.py --sem-banco                       # só gera os arquivos em saida\
    python baixa_vendas.py --visivel                         # mostra o navegador (pra depurar)

.env: ERP_USUARIO e ERP_SENHA (além das variáveis do Postgres que o carregar_banco.py já usa).
"""
import argparse
import csv
import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))
from extrair_vendas_ortobom import custo_estimado, nome_loja  # noqa: E402  (mesmas regras dos PDFs)

BASE_URL = "https://lojaszemaria.rpsistema.com.br"
API = f"{BASE_URL}/controle/v1"
TIMEOUT_MS = 60_000
PAGE_SIZE = 5000
CNPJ = "ORTOBOM SEM CNPJ"

SEL_USUARIO = "input[placeholder='Usuario']"
SEL_SENHA = "input[placeholder='Senha de Acesso']"
SEL_ENTRAR = "button.primary-button:has-text('Entrar')"


def D(v) -> Decimal:
    return Decimal(str(v or 0))


def configura_log() -> None:
    pasta = RAIZ / "logs"
    pasta.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(pasta / f"baixa_vendas_{datetime.now():%Y%m%d}.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)])


def periodo_padrao() -> tuple[date, date]:
    """Do dia 1 do mês até ontem (no dia 1, pega o mês anterior inteiro)."""
    ontem = date.today() - timedelta(days=1)
    return ontem.replace(day=1), ontem


# --------------------------------------------------------------------------- sessão no RP Sistema
class SessaoRP:
    """Login pela tela e chamadas à API na mesma sessão do navegador."""

    def __init__(self, page, context):
        self.page, self.context, self.headers_api = page, context, {}
        page.on("request", self._captura_headers)

    def _captura_headers(self, request) -> None:
        # Reaproveita a autenticação que o próprio sistema usa nas chamadas dele à API
        if "/controle/v1/" in request.url and not self.headers_api:
            auth = {k: v for k, v in request.headers.items()
                    if k.lower() in ("authorization", "x-access-token", "x-token")}
            if auth:
                self.headers_api = auth

    def login(self, usuario: str, senha: str) -> None:
        self.page.goto(f"{BASE_URL}/login")
        self.page.fill(SEL_USUARIO, usuario)
        self.page.fill(SEL_SENHA, senha)
        self.page.click(SEL_ENTRAR)
        self.page.wait_for_url(lambda u: "/login" not in u, timeout=TIMEOUT_MS)
        self.page.goto(f"{BASE_URL}/cadastros/relatorio-vendas")
        self.page.wait_for_load_state("networkidle")
        if not self.headers_api:
            raise RuntimeError("login feito, mas não identifiquei a autenticação da API")

    def get(self, caminho: str, params: dict) -> dict:
        resp = self.context.request.get(f"{API}/{caminho}?{urlencode(params)}",
                                        headers=self.headers_api, timeout=TIMEOUT_MS)
        if not resp.ok:
            raise RuntimeError(f"{resp.status} em {caminho}: {resp.text()[:200]}")
        d = resp.json()
        if not d.get("success", True):
            raise RuntimeError(f"erro da API em {caminho}: {json.dumps(d)[:200]}")
        return d

    def filiais(self) -> list[dict]:
        d = self.get("filiais", {"page": 1, "pageSize": 500, "searchField": "f.id",
                                 "partial": "false", "showInactive": "true"})
        return [{"id_empresa": r["identificador_empresa"],
                 "filial": r["descricao"].split()[0].strip().upper()} for r in d["rows"]]

    def relatorio(self, modo: str, ini: date, fim: date, id_empresa: int) -> list[dict]:
        linhas, pagina = [], 1
        while True:
            d = self.get("relatorio-vendas", {
                "page": pagina, "pageSize": PAGE_SIZE, "partial": "false", "showInactive": "true",
                "modo_relatorio": modo, "data_inicial": ini.isoformat(), "data_final": fim.isoformat(),
                "id_empresa": id_empresa, "id_empresa_filtro": id_empresa})
            linhas += d.get("rows", [])
            if len(linhas) >= d.get("total", 0) or not d.get("rows"):
                return linhas
            pagina += 1


# --------------------------------------------------------------------------- mesma saída do fluxo PDF
def monta_saida(loja: str, ini: date, fim: date, vendas_api: list[dict], custos_api: list[dict], saida: Path) -> dict:
    erros, avisos = [], []
    vendas = []
    for r in vendas_api:
        vendas.append(dict(data=datetime.fromisoformat(r["data_emissao"][:19]).date(), cod=str(r["codigo"]).strip(),
                           descricao=re.sub(r"\s+", " ", r["descricao"] or "").strip(),
                           categoria=(r.get("categoria") or "").strip().upper(), qtd=int(D(r["quantidade"])),
                           valor=D(r["valor_total"]), desconto=D(r.get("valor_desconto")),
                           acrescimo=D(r.get("valor_acrescimo"))))
    fora = [x for x in vendas if not (ini <= x["data"] <= fim)]
    if fora:
        erros.append(f"{len(fora)} venda(s) fora do período {ini:%d/%m/%Y}–{fim:%d/%m/%Y}")

    # custo unitário por produto no período (relatório de margem de lucro)
    custo_unit, qtd_c, valor_c = {}, {}, Decimal(0)
    for r in custos_api:
        cod, q, c = str(r["codigo"]).strip(), int(D(r["quantidade"])), D(r["custo_total"])
        if q:
            custo_unit[cod] = c / q
        qtd_c[cod] = q
        valor_c += D(r["valor_total"])
    valor_v = sum((x["valor"] for x in vendas), Decimal(0))
    if valor_v.quantize(Decimal("0.01")) != valor_c.quantize(Decimal("0.01")):
        avisos.append(f"valor no relatório por data (R$ {valor_v:.2f}) ≠ no de margem (R$ {valor_c:.2f})")
    qtd_v = defaultdict(int)
    for x in vendas:
        qtd_v[x["cod"]] += x["qtd"]
    for cod in sorted(set(qtd_v) | set(qtd_c)):
        if qtd_v.get(cod, 0) != qtd_c.get(cod, 0):
            avisos.append(f"produto {cod}: {qtd_v.get(cod, 0)} un. no relatório por data x {qtd_c.get(cod, 0)} no de margem"
                          + ("" if cod in custo_unit else " (sem custo: entra com custo 0)"))

    regras = custo_estimado()
    origem = f"API relatorio-vendas {ini:%Y%m%d}_{fim:%Y%m%d}"
    linhas, seq = [], defaultdict(int)
    for x in sorted(vendas, key=lambda x: x["data"]):
        seq[x["data"]] += 1
        bruto = x["valor"] + x["desconto"] - x["acrescimo"]
        cu = custo_unit.get(x["cod"])
        fator = regras.get((loja, x["categoria"]), regras.get((loja, "*")))
        if cu is not None:
            custo, inf, est = (cu * x["qtd"]).quantize(Decimal("0.01")), "1", "0"
        elif fator is not None:
            custo, inf, est = (x["valor"] * fator).quantize(Decimal("0.01")), "0", "1"
        else:
            custo, inf, est = Decimal("0.00"), "0", "0"
        linhas.append(dict(cnpj=CNPJ, loja=loja, data_venda=x["data"].isoformat(), seq_dia=seq[x["data"]],
                           cod_produto="ORT" + x["cod"], descricao=x["descricao"], categoria_origem=x["categoria"],
                           qtd=x["qtd"], vr_bruto=f"{bruto:.2f}", vr_desc_acres=f"{(x['acrescimo'] - x['desconto']):.2f}",
                           vr_liquido=f"{x['valor']:.2f}", vr_custo=f"{custo:.2f}", vr_lucro=f"{(x['valor'] - custo):.2f}",
                           custo_informado=inf, custo_estimado=est, arquivo_origem=origem, pagina=0))

    saida.mkdir(parents=True, exist_ok=True)
    cols = ["cnpj", "loja", "data_venda", "seq_dia", "cod_produto", "descricao", "categoria_origem", "qtd", "vr_bruto",
            "vr_desc_acres", "vr_liquido", "vr_custo", "vr_lucro", "custo_informado", "custo_estimado", "arquivo_origem", "pagina"]
    with open(saida / "fato_venda_item.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";"); w.writeheader(); w.writerows(linhas)
    (saida / "fato_venda.csv").write_text("cnpj;loja;controle;data_venda;data_hora;tipo;vr_bruto;vr_desc_acres;vr_liquido;"
                                          "vr_custo;vr_lucro;vr_coluna_extra;arquivo_origem;pagina\n", encoding="utf-8")
    (saida / "fato_venda_item_vinculo.csv").write_text("cnpj;loja;data_venda;seq_dia;controle;qtd;vr_liquido;vr_custo;"
                                                       "status_vinculo\n", encoding="utf-8")
    (saida / "dim_empresa.csv").write_text(f"cnpj;razao_social;uf;inscricao_estadual\n{CNPJ};Lojas Ortobom;;\n", encoding="utf-8")
    with open(saida / "dim_produto.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["cod_produto", "descricao", "categoria_origem", "qtd_descricoes"])
        vistos = {}
        for l in linhas:
            vistos.setdefault(l["cod_produto"], l)
        for cod in sorted(vistos):
            w.writerow([cod, vistos[cod]["descricao"], vistos[cod]["categoria_origem"], 1])

    tot = sum((Decimal(l["vr_liquido"]) for l in linhas), Decimal(0))
    tot_custo = sum((Decimal(l["vr_custo"]) for l in linhas), Decimal(0))
    meta = dict(fonte="ORTOBOM", cnpj=CNPJ, loja=loja, razao_social="Lojas Ortobom",
                arquivo_produto=origem + " (produtos-vendidos-data)", periodo_produto=[ini.isoformat(), fim.isoformat()],
                arquivo_venda=origem + " (produtos-lucro)", periodo_venda=[ini.isoformat(), fim.isoformat()],
                linhas_item=len(linhas), linhas_venda=0, total_liquido_itens=f"{tot:.2f}", total_liquido_vendas="0.00",
                total_custo=f"{tot_custo:.2f}", validacao_ok=not erros, problemas=erros, avisos=avisos)
    (saida / "carga_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["sem_custo"] = sum(1 for l in linhas if l["custo_informado"] == "0")
    meta["pecas"] = sum(l["qtd"] for l in linhas)
    return meta


def br(v) -> str:
    return f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------------------------- principal
def main() -> int:
    load_dotenv(RAIZ / ".env")
    ap = argparse.ArgumentParser(description="Vendas + custo Ortobom pelo RP Sistema")
    ap.add_argument("--inicio", help="DD/MM/AAAA")
    ap.add_argument("--fim", help="DD/MM/AAAA")
    ap.add_argument("--filial", type=int, action="append", help="id_empresa (2, 3, 4); padrão = todas")
    ap.add_argument("--sem-banco", action="store_true", help="só gera os arquivos em saida\\")
    ap.add_argument("--visivel", action="store_true", help="mostra o navegador")
    a = ap.parse_args()
    configura_log()

    if a.inicio and a.fim:
        ini, fim = (datetime.strptime(x, "%d/%m/%Y").date() for x in (a.inicio, a.fim))
    else:
        ini, fim = periodo_padrao()

    resultados, falhas = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not a.visivel)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        rp = SessaoRP(page, context)
        try:
            rp.login(os.environ["ERP_USUARIO"], os.environ["ERP_SENHA"])
            logging.info("Login OK")
        except Exception as e:  # noqa: BLE001
            page.screenshot(path=RAIZ / "logs" / "erro_login.png")
            logging.error("Falha no login (%s) — veja logs\\erro_login.png", e)
            browser.close()
            return 1

        filiais = rp.filiais()
        if a.filial:
            filiais = [f for f in filiais if f["id_empresa"] in a.filial]
        logging.info("Período %s a %s | %d filial(is)", f"{ini:%d/%m/%Y}", f"{fim:%d/%m/%Y}", len(filiais))

        for fil in filiais:
            loja = nome_loja("ORTOBOM", fil["filial"]).upper()
            try:
                vendas = rp.relatorio("produtos-vendidos-data", ini, fim, fil["id_empresa"])
                custos = rp.relatorio("produtos-lucro", ini, fim, fil["id_empresa"])
                pasta = RAIZ / "saida" / f"vendas_{re.sub(r'\W+', '_', loja)}_{ini:%Y%m%d}_{fim:%Y%m%d}"
                m = monta_saida(loja, ini, fim, vendas, custos, pasta)
                logging.info("%-18s %4d linhas | %4d peças | vendas R$ %s | custo R$ %s%s", loja, m["linhas_item"],
                             m["pecas"], br(m["total_liquido_itens"]), br(m["total_custo"]),
                             f" | {m['sem_custo']} linha(s) sem custo" if m["sem_custo"] else "")
                for av in m["avisos"]:
                    logging.warning("  aviso: %s", av)
                for er in m["problemas"]:
                    logging.error("  problema: %s", er)
                resultados.append((loja, pasta, m))
            except Exception as e:  # noqa: BLE001
                logging.error("Falha em %s: %s", loja, e)
                falhas.append(loja)
        browser.close()

    if not a.sem_banco:
        for loja, pasta, m in resultados:
            if not m["validacao_ok"] or not m["linhas_item"]:
                logging.warning("%s não foi carregada no banco (%s)", loja,
                                "sem vendas no período" if not m["linhas_item"] else "validação com problema")
                continue
            r = subprocess.run([sys.executable, str(SRC / "carregar_banco.py"), str(pasta)])
            if r.returncode != 0:
                falhas.append(loja + " (carga no banco)")

    if falhas:
        logging.error("Com falha: %s", ", ".join(falhas))
        return 2
    logging.info("Pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
