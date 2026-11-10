# Pendências — Zé&Maria

_Atualizado em 09/11/2026_

## Amanhã (10/11)

- [ ] **Mucambo — PDFs do ERP** (pedidos à Veronica)
  - Salvar em `entrada\vendas\MUCAMBO\` com os nomes `Lucratividade por produto AAAA.pdf` e `Lucratividade por venda clientes AAAA.pdf`, exportando o ano inteiro (2025 e 2026, se houver).
  - Rodar `python processa_vendas.py --loja MUCAMBO`.
  - Conferir: o CNPJ (mesmo da Graça ou filial?), os totais contra o ERP e os produtos "A classificar" (`SELECT descricao FROM vendas.vw_produto WHERE grupo='A classificar'`).
- [ ] **Confirmar que os PDFs atuais são da loja GRAÇA** (matriz). Se não forem, é só renomear a pasta e rodar de novo.
- [ ] **Validar a DRE com as duas lojas** em `financeiro.vw_fato_principal`. Ainda faltam as lojas Ortobom, então o resultado continua incompleto.

## Com a Veronica

- [ ] **Contas a pagar:** a cor de fundo da linha indica boleto pago? O que significa cada cor (verde, azul, amarelo)?
- [ ] **PLAN GERAL, Total Entrada:** a fórmula não soma STONE GRA / ITAU GRAÇA e BRAD MUC (R$ 110 mil em 2026). É proposital (para não contar em dobro) ou é erro?
- [ ] **PLAN GERAL, dias 30 e 31:** o "Saldo Operac" usa a linha BRAD GRA em vez do Total Entrada. Corrigir a fórmula na planilha.
- [ ] **Classificar saídas:** Hilux (empresa ou pessoal?), viagens a Gramado (feira ou pessoal?), compras na Casas Bahia (revenda?), cartões de crédito (o que é pago neles?).
- [ ] **Sistema de nota fiscal** das lojas de colchão: exportação de vendas (pedido ao Guilherme, fornecedor).

## Próximas fontes

- [ ] **Lojas Ortobom (outro sistema):** pedir um arquivo de exemplo da exportação de vendas. Com ele, criar um extrator em `src\` que gere os mesmos CSVs (`fato_venda` / `fato_venda_item`) com `loja = <nome da loja>`. Banco, carregador e fato principal não mudam.
- [ ] Ao incluir loja nova no caixa, conferir o `config\mapa_entradas_caixa.csv`.

## Banco e BI

- [ ] Revisar as saídas "A classificar" do caixa (R$ 61 mil em 2026) e completar `config\regras_conta_caixa.csv`.
- [ ] Decidir se a fato também terá a **DRE pelo caixa** (`entra_no_dre_caixa`) enquanto faltam lojas.
- [ ] Power BI: conectar em `financeiro.vw_fato_principal` + `dim_grupo_dre` + `vendas.dim_calendario`. Primeiras páginas: DRE mensal, vendas por categoria/loja, contas a vencer e alertas do caixa.
- [ ] Ao voltar de viagem: clonar no PC de mesa, `criar_banco.py` e recarregar tudo (README).
