"""
Atualiza o banco com as planilhas da Veronica. Rode sempre que elas forem atualizadas:

    python atualizar_financeiro.py            # só recarrega o que mudou
    python atualizar_financeiro.py --forcar   # recarrega tudo

Caminhos e senha ficam no .env:
    CONTAS_PAGAR_ARQUIVO=C:\\...\\BENS OS A PAGAR GRAÇA.xlsx
    CAIXA_ARQUIVOS=C:\\...\\2026- PLAN GERAL GRAÇA E MUCAMBO.xlsx    (vários: separe por ;  aceita curinga *)
    PLAN_GERAL_SENHA=...
"""
import glob, os, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SRC = RAIZ / "src"
SAIDA = RAIZ / "saida" / "financeiro"


def ler_env():
    env = RAIZ / ".env"
    if not env.exists():
        sys.exit("Crie o arquivo .env (copie de .env.example) com os caminhos das planilhas.")
    for l in env.read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))


def rodar(script, *args):
    print(f"\n>> {script.name}", flush=True)
    r = subprocess.run([sys.executable, str(script), *map(str, args)])
    if r.returncode != 0:
        sys.exit(f"Parou: {script.name} falhou. Nada foi gravado no banco nesta etapa.")


def main():
    ler_env()
    cp = os.environ.get("CONTAS_PAGAR_ARQUIVO", "")
    cx = []
    for padrao in filter(None, (p.strip() for p in os.environ.get("CAIXA_ARQUIVOS", "").split(";"))):
        achados = sorted(glob.glob(padrao))
        if not achados:
            sys.exit(f"Planilha de caixa não encontrada: {padrao}")
        cx += achados
    if not cp or not Path(cp).exists():
        sys.exit(f"Planilha de contas a pagar não encontrada: {cp!r} (confira CONTAS_PAGAR_ARQUIVO no .env)")
    SAIDA.mkdir(parents=True, exist_ok=True)
    rodar(SRC / "extrair_contas_pagar.py", cp, SAIDA)
    if cx:
        rodar(SRC / "extrair_caixa_diario.py", *cx, SAIDA)
    rodar(SRC / "carregar_financeiro.py", SAIDA, *(["--forcar"] if "--forcar" in sys.argv else []))
    print("\nPronto.")


if __name__ == "__main__":
    main()
