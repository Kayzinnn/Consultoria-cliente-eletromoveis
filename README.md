# Zé&Maria — Banco de dados para o BI

Banco PostgreSQL `ze_maria` alimentado pelos arquivos da Zé&Maria, com dois schemas:

| Schema | Fonte (pasta `entrada\`) | Tabelas principais |
|---|---|---|
| `vendas` | PDFs do ERP: *Lucratividade por produto AAAA* e *Lucratividade por venda clientes AAAA* | `fato_venda`, `fato_venda_item`, `dim_produto`, `dim_calendario` |
| `financeiro` | Planilhas da Veronica: BOLETOS A PAGAR e PLAN GERAL (caixa diário) | `fato_conta_pagar`, `fato_caixa_lancamento`, `fato_caixa_dia` |

Para o Power BI, conecte nas **views** (`vw_*`).

## Instalação (uma vez por computador)

```powershell
git clone https://github.com/Kayzinnn/ze-maria-dados.git
cd ze-maria-dados
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # preencha a senha do PostgreSQL, os caminhos e a senha da PLAN GERAL
python criar_banco.py         # cria o banco e roda sql\01, 02 e 03 (não precisa de psql)
```

Copie os arquivos do cliente para `entrada\`. Eles **não vão para o Git**.

## Atualizar (sempre que chegar arquivo novo)

Salve por cima na pasta `entrada\` e rode:

```powershell
python processa_vendas.py        # todos os pares de PDF da pasta (um por ano)
python atualizar_financeiro.py   # planilhas; recarrega só a que mudou
```

- Nada é gravado se algum dia não bater com o SUB-TOTAL/TOTAL do PDF ou com os totais da planilha.
- Vendas: cada PDF substitui o seu PERÍODO LISTADO, então reprocessar não duplica.
- Financeiro: cada planilha é recarregada inteira (é cumulativa e não tem ID). Se o hash do arquivo for o mesmo da última carga, ela é pulada (`--forcar` recarrega mesmo assim).
- Opções: `processa_vendas.py --ano 2026`, `processa_vendas.py --sem-banco` (só gera os CSVs em `saida\`).

## Estrutura

```
criar_banco.py, processa_vendas.py, atualizar_financeiro.py   # comandos
src\        extratores (PDF/Excel), vínculo item x venda, carregadores
sql\        01_schema (vendas), 02_views (vendas), 03_financeiro
config\     regras_categoria.csv (categoria pelo início da descrição), mapa_entradas_caixa.csv
entrada\    arquivos do cliente (fora do Git)
saida\      CSVs intermediários (fora do Git)
```

## Pontos de atenção

**Vendas**
- **Vínculo item × venda.** O ERP não liga produto à venda; o script deduz pelo custo e pelo líquido. `status_vinculo` vale `UNICO` (confiável), `AMBIGUO` ou `SEM_VINCULO`. Análises por cesta e ticket usam só `UNICO` (`vw_venda_item_por_controle`).
- **Custo R$ 0,01** = custo não cadastrado no ERP (`custo_nao_cadastrado`). Infla o lucro.
- **RENEGOCIAÇÃO** aparece como produto, mas não é venda de mercadoria (`nao_e_mercadoria`).
- **Produto novo sem regra** de categoria aparece como "A classificar": inclua o prefixo em `config\regras_categoria.csv` ou preencha `dim_produto.categoria_manual`.
- **Diferença entre relatórios.** Os dois relatórios podem divergir em centavos ou acréscimos (ex.: 07/03/2025, R$ 200). É o ERP.

**Financeiro**
- **Boleto pago.** A planilha não tem coluna de "pago"; usamos a cor de fundo da linha como marcação (hipótese a confirmar com a Veronica).
- **Total Entrada.** A fórmula da PLAN GERAL não soma todas as linhas de entrada. Todas estão no banco, com `entra_no_total`.
- **Dias 30/31.** O "Saldo Operac" desses dias usa a linha errada. O banco guarda o saldo da planilha e o recalculado. Veja `vw_caixa_alertas`.
- **Rótulo de entrada novo** na PLAN GERAL: inclua em `config\mapa_entradas_caixa.csv`.
