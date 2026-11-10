# Zé&Maria — Banco de dados para o BI

Banco PostgreSQL `ze_maria` alimentado pelos arquivos da Zé&Maria, com dois schemas:

| Schema | Fonte (pasta `entrada\`) | Tabelas principais |
|---|---|---|
| `vendas` | PDFs do ERP por loja: `entrada\vendas\<LOJA>\Lucratividade por produto AAAA.pdf` e `...por venda clientes AAAA.pdf` | `fato_venda`, `fato_venda_item`, `dim_produto`, `dim_calendario` |
| `financeiro` | Planilhas da Veronica: BOLETOS A PAGAR e PLAN GERAL (caixa diário) | `fato_conta_pagar`, `fato_caixa_lancamento`, `fato_caixa_dia` |

Para o Power BI, use a **fato principal** `financeiro.vw_fato_principal` (vendas + caixa numa tabela só) e as demais views (`vw_*`).

## Instalação (uma vez por computador)

```powershell
git clone https://github.com/Kayzinnn/ze-maria-dados.git
cd ze-maria-dados
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # preencha a senha do PostgreSQL, os caminhos e a senha da PLAN GERAL
python criar_banco.py         # cria o banco e roda sql\01, 02 e 03 (não precisa de psql)
```

Copie os arquivos do cliente para `entrada\`. Eles **não vão para o Git**:

```
entrada\
  BENÇÃOS A PAGAR GRAÇA.xlsx
  2026- PLAN GERAL GRAÇAMUCAMBO.xlsx
  vendas\
    GRAÇA\    Lucratividade por produto 2025.pdf, ...por venda clientes 2025.pdf, ... 2026
    MUCAMBO\  Lucratividade por produto 2026.pdf, ...por venda clientes 2026.pdf
```
O **nome da subpasta é a loja** no banco. Use os mesmos nomes do caixa (GRAÇA, MUCAMBO).
Loja nova é uma pasta nova. PDF solto direto em `entrada\` é ignorado com aviso.

## Atualizar (sempre que chegar arquivo novo)

Salve por cima na pasta `entrada\` e rode:

```powershell
python processa_vendas.py        # todas as lojas e anos de entrada\vendas\
python atualizar_financeiro.py   # planilhas; recarrega só a que mudou
```

- Nada é gravado se algum dia não bater com o SUB-TOTAL/TOTAL do PDF ou com os totais da planilha.
- Vendas: cada par de PDFs substitui o seu PERÍODO LISTADO **daquela loja**, então reprocessar não duplica nem mexe nas outras lojas. Exporte sempre o **ano inteiro** e salve por cima.
- Financeiro: cada planilha é recarregada inteira (é cumulativa e não tem ID). Se o hash do arquivo for o mesmo da última carga, ela é pulada (`--forcar` recarrega mesmo assim).
- Opções: `processa_vendas.py --loja MUCAMBO`, `--ano 2026`, `processa_vendas.py --sem-banco` (só gera os CSVs em `saida\`).

## Estrutura

```
criar_banco.py, processa_vendas.py, atualizar_financeiro.py   # comandos
src\        extratores (PDF/Excel), vínculo item x venda, carregadores
sql\        00_migracao_multiloja, 01_schema (vendas), 02_views (vendas), 03_financeiro, 04_fato_principal
config\     regras_categoria.csv (produtos), categoria_origem.csv e custo_estimado.csv (Ortobom), regras_conta_caixa.csv (plano de contas das saídas), mapa_entradas_caixa.csv
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

**Fato principal (`financeiro.vw_fato_principal`)**
- Uma linha por fato. `valor` positivo = receita; negativo = custo, despesa ou saída.
- `Resultado = CALCULATE(SUM(valor), entra_no_dre = TRUE())` · `Fluxo = CALCULATE(SUM(valor), entra_no_fluxo = TRUE())` · ordem das linhas: `financeiro.dim_grupo_dre`.
- As saídas do caixa são classificadas por `config\regras_conta_caixa.csv` (regex, menor prioridade vence). Fornecedor de mercadoria, empréstimo, investimento, gasto pessoal e transferência ficam **fora da DRE**, porque o CMV vem do ERP.
- A DRE só fecha quando **todas as lojas** tiverem receita carregada (ERP de cada loja + sistema das lojas Ortobom).

**Metas de venda (orçamento)**
- Edite `config\metas_vendas.csv` (ano; mês; loja; meta do mês em R$) e rode `python atualizar_metas.py`. O CSV é a fonte: cada execução substitui as metas do banco.
- A meta diária = meta do mês ÷ dias de venda (dias do mês sem domingos e sem os dias de `config\dias_sem_venda.csv`, para feriados).
- Ficam em `vendas.meta_venda` / `vendas.vw_meta_venda_dia` e entram na fato principal com `origem = 'Meta de vendas'` (fora da DRE e do fluxo), uma linha por loja e dia de venda.

**Lojas Ortobom (outro sistema)**
- Vendas: em `entrada\vendas\ORTOBOM\`, para cada filial, salve o **"Relatório de venda de produtos (por data)"** e o **"Relatório de produtos com margem de lucro"** do mesmo período. Os dois formam par pela filial e pelo Início/Fim do cabeçalho (o nome do arquivo não importa). A loja vira `ORTOBOM GRAÇA`, `ORTOBOM MUCAMBO`, `ORTOBOM CARNAUBAL`. Rode `python processa_vendas.py --loja ORTOBOM`; cada par substitui o próprio período daquela filial.
- O custo de cada venda = quantidade × custo unitário do produto no relatório de margem. Produto sem custo lá entra com custo 0 (`custo_informado = false`) ou pelo `config\custo_estimado.csv`.
- Os códigos de produto ganham o prefixo `ORT` (não colidem com o ERP). A categoria vem do próprio relatório e é traduzida por `config\categoria_origem.csv`.
- Caixa: a `2026- PLAN GERAL EZM COLCHOES ORTOBOM.xlsx` entra pelo `CAIXA_ARQUIVOS` do `.env` (o curinga `*PLAN GERAL*.xlsx` já pega). Tudo que vem de arquivo com "ORTOBOM" no nome ganha `negocio = ORTOBOM` e loja `ORTOBOM <LOJA>`.
- Aba de mês com datas de outro mês (ex.: NOVEMBRO copiada de outubro) é **ignorada com aviso**, em vez de travar a carga.
- `vw_fato_principal` tem a coluna `negocio` (ELETROMÓVEIS | ORTOBOM), que serve para segmentar no BI.

**Novas fontes de venda (outro sistema)**
- O formato é diferente, então precisa de um extrator novo em `src\` que gere os mesmos CSVs (`fato_venda`, `fato_venda_item`), com a coluna `loja`. O carregador e o banco não mudam.
