# Pendências — Zé&Maria

_Atualizado em 10/11/2026_

## Amanhã (10/11)

- [x] **Mucambo — PDFs do ERP** carregados (2025 e 2026 até 10/11). Mesmo CNPJ da Graça, nenhum controle em comum com a Graça (são vendas diferentes). Os nomes "RELATORIO POR PRODUTO/CLIENTE AAAA.pdf" também são aceitos.
- [x] **Mucambo sem custo no ERP** (recebe da Graça, que funciona como CD): o custo vem da Graça — mesmo código, depois mesma descrição, depois % de custo da categoria (`vendas.vw_item_custo`, coluna `origem_custo`). ~44% do CMV do Mucambo ainda é estimado pela categoria: um de-para de código Mucambo → código Graça melhoraria.
- [ ] Mucambo 2026: o relatório por produto soma R$ 300 a menos que o por venda (diferença do ERP, como já aconteceu na Graça).
- [ ] **Confirmar que os PDFs atuais são da loja GRAÇA** (matriz). Se não forem, é só renomear a pasta e rodar de novo.
- [ ] **Validar a DRE com as duas lojas** em `financeiro.vw_fato_principal`. Ainda faltam as lojas Ortobom, então o resultado continua incompleto.

## Com a Veronica

- [ ] **Contas a pagar:** a cor de fundo da linha indica boleto pago? O que significa cada cor (verde, azul, amarelo)?
- [ ] **PLAN GERAL, Total Entrada:** a fórmula não soma STONE GRA / ITAU GRAÇA e BRAD MUC (R$ 110 mil em 2026). É proposital (para não contar em dobro) ou é erro?
- [ ] **PLAN GERAL, dias 30 e 31:** o "Saldo Operac" usa a linha BRAD GRA em vez do Total Entrada. Corrigir a fórmula na planilha.
- [ ] **Classificar saídas:** Hilux (empresa ou pessoal?), viagens a Gramado (feira ou pessoal?), compras na Casas Bahia (revenda?), cartões de crédito (o que é pago neles?).
- [ ] **Sistema de nota fiscal** das lojas de colchão: exportação de vendas (pedido ao Guilherme, fornecedor).

## Próximas fontes

- [x] Extrator das vendas Ortobom (`src\extrair_vendas_ortobom.py`) e caixa Ortobom no `atualizar_financeiro.py`.
- [x] Ortobom: vendas por dia + custo (relatórios por data e margem de lucro, por filial) carregados — jan–out/2026.
- [ ] Ortobom: o sistema só tem vendas a partir de 25/08/2026? Confirmar com a Veronica de onde vêm as vendas de antes (o caixa da Ortobom tem recebimentos desde dez/2025).
- [ ] **Ortobom: CNPJ** da EZM Colchões (hoje entra como "ORTOBOM SEM CNPJ"; dá para passar `--cnpj`).
- [ ] **PLAN GERAL Ortobom, aba NOVEMBRO:** está com as datas de 02/10 a 01/11 (cópia de outubro). Corrigir; até lá a aba é ignorada (15 lançamentos, R$ 17 mil).
- [ ] PLAN GERAL Ortobom: confirmar o que é a entrada genérica "BANCO" e as entradas sem loja (BLU, PIX, ENT.DINHEIRO).
- [ ] Ao incluir loja nova no caixa, conferir o `config\mapa_entradas_caixa.csv`.

## Banco e BI

- [x] De-para de loja das despesas (`config\regras_loja_caixa.csv`) com as respostas da Veronica de 10/11: "Geral" caiu de R$ 826 mil para R$ 527 mil. Polo e despesas de Teresina (filho) saíram da DRE.
- [ ] Veronica: Unimed (de quem?), fretes (Itatiaia, CHF, Rimo, Poquema: de qual loja?), Tenda/Letícia, "Diversos" R$ 18 mil, Ionário, câmeras Everardo, João Vitor (qual loja enquanto trabalhou).
- [ ] Definir o critério de rateio do "Compartilhado" (Strada, Hilux, Jeep) e do "Geral" (pró-labore, impostos, contador) entre as lojas.
- [ ] Revisar as saídas "A classificar" do caixa (R$ 61 mil em 2026) e completar `config\regras_conta_caixa.csv`.
- [ ] Decidir se a fato também terá a **DRE pelo caixa** (`entra_no_dre_caixa`) enquanto faltam lojas.
- [ ] Power BI: conectar em `financeiro.vw_fato_principal` + `dim_grupo_dre` + `vendas.dim_calendario`. Primeiras páginas: DRE mensal, vendas por categoria/loja, contas a vencer e alertas do caixa.
- [ ] Ao voltar de viagem: clonar no PC de mesa, `criar_banco.py` e recarregar tudo (README).
