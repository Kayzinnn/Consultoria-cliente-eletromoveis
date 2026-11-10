-- =============================================================================
-- Fato principal do BI: vendas (ERP) + caixa diário (entradas e saídas) numa tabela só.
-- Formato longo: 1 linha por fato; RECEITA positiva, CUSTO/DESPESA/SAÍDA negativos.
--   Resultado (DRE)    = SUM(valor) WHERE entra_no_dre
--   Fluxo de caixa     = SUM(valor) WHERE entra_no_fluxo
-- psql -d ze_maria -f 04_fato_principal.sql   (ou python criar_banco.py)
-- =============================================================================
SET search_path TO financeiro;
DROP VIEW IF EXISTS vw_fato_principal;

-- Plano de contas por regra (config/regras_conta_caixa.csv). Menor prioridade vence.
CREATE TABLE IF NOT EXISTS regra_conta (
    prioridade    int     NOT NULL,
    padrao        text    PRIMARY KEY,      -- expressão regular (sem diferenciar maiúsc./minúsc.)
    conta         text    NOT NULL,
    grupo_dre     text    NOT NULL,
    entra_no_dre  boolean NOT NULL
);

-- Ordem das linhas da DRE (para ordenar no BI)
CREATE TABLE IF NOT EXISTS dim_grupo_dre (
    grupo_dre  text PRIMARY KEY,
    ordem      int  NOT NULL,
    secao      text NOT NULL
);
INSERT INTO dim_grupo_dre VALUES
    ('Receita bruta de vendas',            10, 'DRE'),
    ('Descontos e acréscimos',             20, 'DRE'),
    ('Outras receitas',                    30, 'DRE'),
    ('Custo da mercadoria vendida',        40, 'DRE'),
    ('Despesas com pessoal',               50, 'DRE'),
    ('Pró-labore',                         55, 'DRE'),
    ('Impostos',                           60, 'DRE'),
    ('Despesas de ocupação',               70, 'DRE'),
    ('Despesas logísticas',                80, 'DRE'),
    ('Despesas administrativas',           90, 'DRE'),
    ('Despesas financeiras',              100, 'DRE'),
    ('A classificar',                     110, 'DRE'),
    ('Recebimentos',                      200, 'Fora da DRE'),
    ('Compras de mercadoria',             210, 'Fora da DRE'),
    ('Financeiro - amortização',          220, 'Fora da DRE'),
    ('Transferências',                    225, 'Fora da DRE'),
    ('Investimentos',                     230, 'Fora da DRE'),
    ('Não operacional - sócios',          240, 'Fora da DRE')
ON CONFLICT (grupo_dre) DO UPDATE SET ordem = EXCLUDED.ordem, secao = EXCLUDED.secao;

-- Fornecedores de mercadoria: 1ª palavra dos fornecedores pagos por DUPLICATA no contas a pagar
CREATE OR REPLACE VIEW vw_fornecedor_mercadoria AS
SELECT DISTINCT upper(split_part(fornecedor, ' ', 1)) AS token
FROM fato_conta_pagar
WHERE forma_pgto = 'DUPLICATA'
  AND length(split_part(fornecedor, ' ', 1)) >= 3
  AND upper(split_part(fornecedor, ' ', 1)) NOT IN
      ('SÃO','SAO','NEW','AÇO','ACO','HOT','GPS','ART','C&A','CASAS','DEP','ENT','DAS','DAE','PIS');

-- Saídas do caixa classificadas
CREATE OR REPLACE VIEW vw_caixa_saida_classificada AS
SELECT l.*,
       COALESCE(r.conta,
                CASE WHEN f.token IS NOT NULL THEN 'Fornecedores de mercadoria' END,
                'A classificar')                                   AS conta_gerencial,
       COALESCE(r.grupo_dre,
                CASE WHEN f.token IS NOT NULL THEN 'Compras de mercadoria' END,
                'A classificar')                                   AS grupo_dre,
       COALESCE(r.entra_no_dre, f.token IS NULL)                   AS entra_no_dre,
       CASE WHEN r.padrao IS NOT NULL THEN 'regra: ' || r.padrao
            WHEN f.token IS NOT NULL THEN 'fornecedor do contas a pagar: ' || f.token
            ELSE 'sem regra' END                                   AS origem_classificacao,
       CASE WHEN l.descricao ~* '\m(MUC|MUCAMBO)\M'      THEN 'MUCAMBO'
            WHEN l.descricao ~* '\m(GRA|GRAÇA|GRACA)\M'  THEN 'GRAÇA'
            ELSE 'Geral' END                                       AS loja_inferida
FROM fato_caixa_lancamento l
LEFT JOIN LATERAL (
    SELECT * FROM regra_conta rc WHERE l.descricao ~* rc.padrao
    ORDER BY rc.prioridade LIMIT 1
) r ON true
LEFT JOIN vw_fornecedor_mercadoria f
       ON f.token = upper(split_part(regexp_replace(l.descricao, '^\W+', ''), ' ', 1))
WHERE l.tipo = 'SAIDA';

-- ============================================================================ FATO PRINCIPAL
CREATE OR REPLACE VIEW vw_fato_principal AS
-- 1) Vendas do ERP: receita bruta, descontos/acréscimos e CMV por item
SELECT i.data_venda                         AS data,
       'ERP vendas'::text                   AS origem,
       x.natureza,
       x.grupo_dre,
       x.conta,
       COALESCE(NULLIF(i.loja, ''), e.nome_loja, e.razao_social) AS loja,
       i.cnpj,
       p.grupo                              AS grupo_produto,
       p.categoria                          AS categoria_produto,
       i.cod_produto,
       p.descricao,
       CASE WHEN x.natureza = 'Receita' AND x.conta = 'Venda de mercadorias' THEN i.qtd END AS qtd,
       x.valor,
       true                                 AS entra_no_dre,
       false                                AS entra_no_fluxo,
       'vendas.fato_venda_item ' || i.data_venda || ' #' || i.seq_dia AS rastreio
FROM vendas.fato_venda_item i
JOIN vendas.dim_empresa e USING (cnpj)
JOIN vendas.vw_produto  p USING (cod_produto)
CROSS JOIN LATERAL (VALUES
    ('Receita', CASE WHEN p.nao_e_mercadoria THEN 'Outras receitas' ELSE 'Receita bruta de vendas' END,
                CASE WHEN p.nao_e_mercadoria THEN p.categoria ELSE 'Venda de mercadorias' END, i.vr_bruto),
    ('Receita', 'Descontos e acréscimos', 'Descontos e acréscimos', i.vr_desc_acres),
    ('Custo',   'Custo da mercadoria vendida', 'CMV', -i.vr_custo)
) AS x(natureza, grupo_dre, conta, valor)
WHERE x.valor <> 0

UNION ALL
-- 2) Trocas/devoluções (só existem no relatório por venda): custo da mercadoria trocada
SELECT v.data_venda, 'ERP vendas', 'Custo', 'Custo da mercadoria vendida', 'CMV - trocas e devoluções',
       COALESCE(NULLIF(v.loja, ''), e.nome_loja, e.razao_social), v.cnpj, NULL, NULL, NULL, 'Troca/devolução ' || v.controle, NULL,
       v.vr_lucro, true, false, 'vendas.fato_venda ' || v.controle
FROM vendas.fato_venda v
JOIN vendas.dim_empresa e USING (cnpj)
WHERE v.tipo <> 'VENDA' AND v.vr_lucro <> 0

UNION ALL
-- 3) Caixa diário: entradas (recebimentos)
SELECT l.data, 'Caixa diário', 'Recebimento', 'Recebimentos', COALESCE(NULLIF(l.conta, ''), l.descricao),
       COALESCE(NULLIF(l.loja, ''), 'Geral'), NULL, NULL, NULL, NULL, l.descricao, NULL,
       l.valor, false, l.entra_no_total, 'financeiro.fato_caixa_lancamento ' || l.aba || '!' || l.celula
FROM fato_caixa_lancamento l
WHERE l.tipo = 'ENTRADA'

UNION ALL
-- 4) Caixa diário: saídas classificadas pelo plano de contas
SELECT s.data, 'Caixa diário',
       CASE WHEN s.entra_no_dre THEN 'Despesa' ELSE 'Saída fora da DRE' END,
       s.grupo_dre, s.conta_gerencial, s.loja_inferida, NULL, NULL, NULL, NULL, s.descricao, NULL,
       -s.valor, s.entra_no_dre, s.entra_no_total, 'financeiro.fato_caixa_lancamento ' || s.aba || '!' || s.celula
FROM vw_caixa_saida_classificada s;

COMMENT ON VIEW vw_fato_principal IS
 'Fato única do BI. valor: receita +, custo/despesa/saída -. DRE = SUM(valor) WHERE entra_no_dre; Fluxo = SUM(valor) WHERE entra_no_fluxo.';
