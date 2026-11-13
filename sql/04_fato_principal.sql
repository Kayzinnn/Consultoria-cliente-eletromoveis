-- =============================================================================
-- Fato principal do BI: vendas (ERP) + caixa diário (entradas e saídas) numa tabela só.
-- Formato longo: 1 linha por fato; RECEITA positiva, CUSTO/DESPESA/SAÍDA negativos.
--   Resultado (DRE)    = SUM(valor) WHERE entra_no_dre
--   Fluxo de caixa     = SUM(valor) WHERE entra_no_fluxo
-- psql -d ze_maria -f 04_fato_principal.sql   (ou python criar_banco.py)
-- =============================================================================
SET search_path TO financeiro;
DROP VIEW IF EXISTS vw_fato_principal;
DROP VIEW IF EXISTS vw_caixa_saida_classificada;   -- recriada abaixo (ganhou a coluna negocio)
DROP VIEW IF EXISTS vendas.vw_item_custo;

-- Plano de contas por regra (config/regras_conta_caixa.csv). Menor prioridade vence.
CREATE TABLE IF NOT EXISTS regra_conta (
    prioridade    int     NOT NULL,
    padrao        text    PRIMARY KEY,      -- expressão regular (sem diferenciar maiúsc./minúsc.)
    conta         text    NOT NULL,
    grupo_dre     text    NOT NULL,
    entra_no_dre  boolean NOT NULL
);

-- De-para saída do caixa -> loja (config/regras_loja_caixa.csv). Menor prioridade vence.
-- loja com | divide o valor em partes iguais; negocio NULL = vale para as duas planilhas.
CREATE TABLE IF NOT EXISTS regra_loja (
    prioridade  int  NOT NULL,
    padrao      text NOT NULL,
    negocio     text,
    loja        text NOT NULL
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
    ('Não operacional - sócios',          240, 'Fora da DRE'),
    ('Meta de vendas',                    300, 'Metas')
ON CONFLICT (grupo_dre) DO UPDATE SET ordem = EXCLUDED.ordem, secao = EXCLUDED.secao;

-- Agrupamento resumido para o BI: as 4 despesas operacionais viram 'Despesas'; o resto mantém o próprio nome.
ALTER TABLE dim_grupo_dre ADD COLUMN IF NOT EXISTS agrupamento text;
ALTER TABLE dim_grupo_dre ADD COLUMN IF NOT EXISTS ordem_agrupamento int;
UPDATE dim_grupo_dre SET agrupamento = CASE WHEN grupo_dre IN ('Despesas administrativas', 'Despesas com pessoal',
                                                               'Despesas de ocupação', 'Despesas logísticas')
                                            THEN 'Despesas' ELSE grupo_dre END;
UPDATE dim_grupo_dre d SET ordem_agrupamento = x.ordem
FROM (SELECT agrupamento, min(ordem) AS ordem FROM dim_grupo_dre GROUP BY agrupamento) x
WHERE x.agrupamento = d.agrupamento;

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
       COALESCE(rl.loja,
       CASE WHEN l.negocio = 'ORTOBOM' THEN
                CASE WHEN l.descricao ~* '\m(MUC|MUCAMBO)\M'           THEN 'ORTOBOM MUCAMBO'
                     WHEN l.descricao ~* '\m(GRA|GRAÇA|GRACA)\M'       THEN 'ORTOBOM GRAÇA'
                     WHEN l.descricao ~* '\m(CAR|CARNAUBAL|CARNAÚBAL)\M' THEN 'ORTOBOM CARNAUBAL'
                     ELSE 'ORTOBOM' END
            WHEN l.descricao ~* '\m(MUC|MUCAMBO)\M'      THEN 'MUCAMBO'
            WHEN l.descricao ~* '\m(GRA|GRAÇA|GRACA)\M'  THEN 'GRAÇA'
            ELSE 'Geral' END)                                      AS loja_inferida,
       CASE WHEN rl.padrao IS NOT NULL THEN 'de-para: ' || rl.padrao
            ELSE 'texto da descrição' END                          AS origem_loja
FROM fato_caixa_lancamento l
LEFT JOIN LATERAL (
    SELECT * FROM regra_loja x
    WHERE l.descricao ~* x.padrao AND (x.negocio IS NULL OR x.negocio = COALESCE(l.negocio, 'ELETROMÓVEIS'))
    ORDER BY x.prioridade LIMIT 1
) rl ON true
LEFT JOIN LATERAL (
    SELECT * FROM regra_conta rc WHERE l.descricao ~* rc.padrao
    ORDER BY rc.prioridade LIMIT 1
) r ON true
LEFT JOIN vw_fornecedor_mercadoria f
       ON f.token = upper(split_part(regexp_replace(l.descricao, '^\W+', ''), ' ', 1))
WHERE l.tipo = 'SAIDA';

-- ============================================================================ CUSTO DE REFERÊNCIA
-- Mucambo recebe a mercadoria da Graça (centro de distribuição) e quase não tem custo no ERP.
-- Item sem custo (custo <= R$ 0,01 por peça) de loja do ERP ganha o custo da GRAÇA, nesta ordem:
--   1. mesmo código de produto;  2. mesma descrição;  3. % de custo da categoria na Graça no ano.
-- Em 1 e 2 usa o custo unitário do mês mais próximo da venda. A Ortobom tem custo próprio e fica de fora.
CREATE OR REPLACE VIEW vendas.vw_item_custo AS
WITH pd AS (
    SELECT cod_produto, categoria, upper(regexp_replace(trim(descricao), '\s+', ' ', 'g')) AS dn
    FROM vendas.vw_produto
), base AS (
    SELECT i.cnpj, i.loja, i.data_venda, i.seq_dia, i.cod_produto, i.qtd, i.vr_liquido, i.vr_custo, i.custo_informado,
           pd.dn, pd.categoria, date_trunc('month', i.data_venda)::date AS mes,
           (i.custo_informado AND i.qtd > 0 AND i.vr_custo <= 0.01 * i.qtd AND i.loja NOT ILIKE 'ORTOBOM%') AS sem_custo,
           (i.loja = 'GRAÇA' AND i.qtd > 0 AND i.vr_custo > 0.01 * i.qtd) AS eh_ref
    FROM vendas.fato_venda_item i
    JOIN pd USING (cod_produto)
), ref_cod AS (
    SELECT cod_produto, mes, sum(vr_custo) / sum(qtd) AS cu FROM base WHERE eh_ref GROUP BY 1, 2
), ref_desc AS (
    SELECT dn, mes, sum(vr_custo) / sum(qtd) AS cu FROM base WHERE eh_ref GROUP BY 1, 2
), ref_cat AS (
    SELECT categoria, extract(year FROM mes) AS ano, sum(vr_custo) / NULLIF(sum(vr_liquido), 0) AS pct
    FROM base WHERE eh_ref AND vr_liquido > 0 GROUP BY 1, 2
), c1 AS (   -- mesmo código, mês mais próximo
    SELECT DISTINCT ON (b.cnpj, b.loja, b.data_venda, b.seq_dia) b.cnpj, b.loja, b.data_venda, b.seq_dia, r.cu
    FROM base b JOIN ref_cod r ON r.cod_produto = b.cod_produto
    WHERE b.sem_custo
    ORDER BY b.cnpj, b.loja, b.data_venda, b.seq_dia, abs(r.mes - b.mes), r.mes DESC
), c2 AS (   -- mesma descrição, mês mais próximo
    SELECT DISTINCT ON (b.cnpj, b.loja, b.data_venda, b.seq_dia) b.cnpj, b.loja, b.data_venda, b.seq_dia, r.cu
    FROM base b JOIN ref_desc r ON r.dn = b.dn
    WHERE b.sem_custo
    ORDER BY b.cnpj, b.loja, b.data_venda, b.seq_dia, abs(r.mes - b.mes), r.mes DESC
), c3 AS (   -- % de custo da categoria, ano mais próximo
    SELECT DISTINCT ON (b.cnpj, b.loja, b.data_venda, b.seq_dia) b.cnpj, b.loja, b.data_venda, b.seq_dia, r.pct
    FROM base b JOIN ref_cat r ON r.categoria = b.categoria
    WHERE b.sem_custo
    ORDER BY b.cnpj, b.loja, b.data_venda, b.seq_dia, abs(r.ano - extract(year FROM b.data_venda)), r.ano DESC
)
SELECT b.cnpj, b.loja, b.data_venda, b.seq_dia, b.cod_produto,
       CASE WHEN NOT b.sem_custo   THEN b.vr_custo
            WHEN c1.cu  IS NOT NULL THEN round(c1.cu * b.qtd, 2)
            WHEN c2.cu  IS NOT NULL THEN round(c2.cu * b.qtd, 2)
            WHEN c3.pct IS NOT NULL THEN round(c3.pct * b.vr_liquido, 2)
            ELSE b.vr_custo END AS vr_custo,
       CASE WHEN NOT b.sem_custo   THEN CASE WHEN b.custo_informado THEN 'Custo do sistema' ELSE 'Sem custo' END
            WHEN c1.cu  IS NOT NULL THEN 'Custo da Graça (código)'
            WHEN c2.cu  IS NOT NULL THEN 'Custo da Graça (descrição)'
            WHEN c3.pct IS NOT NULL THEN 'Estimado (% da categoria na Graça)'
            ELSE 'Sem custo' END AS origem_custo
FROM base b
LEFT JOIN c1 USING (cnpj, loja, data_venda, seq_dia)
LEFT JOIN c2 USING (cnpj, loja, data_venda, seq_dia)
LEFT JOIN c3 USING (cnpj, loja, data_venda, seq_dia);

COMMENT ON VIEW vendas.vw_item_custo IS
 'Custo por item com o custo da Graça aplicado aos itens sem custo (Mucambo). origem_custo diz de onde veio.';

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
       'vendas.fato_venda_item ' || i.data_venda || ' #' || i.seq_dia AS rastreio,
       CASE WHEN i.loja ILIKE 'ORTOBOM%' THEN 'ORTOBOM' ELSE 'ELETROMÓVEIS' END AS negocio,
       CASE WHEN x.conta = 'CMV' THEN ic.origem_custo END AS origem_custo
FROM vendas.fato_venda_item i
JOIN vendas.vw_item_custo ic ON ic.cnpj = i.cnpj AND ic.loja = i.loja AND ic.data_venda = i.data_venda AND ic.seq_dia = i.seq_dia
JOIN vendas.dim_empresa e ON e.cnpj = i.cnpj
JOIN vendas.vw_produto  p ON p.cod_produto = i.cod_produto
CROSS JOIN LATERAL (VALUES
    ('Receita', CASE WHEN p.nao_e_mercadoria THEN 'Outras receitas' ELSE 'Receita bruta de vendas' END,
                CASE WHEN p.nao_e_mercadoria THEN p.categoria ELSE 'Venda de mercadorias' END, i.vr_bruto),
    ('Receita', 'Descontos e acréscimos', 'Descontos e acréscimos', i.vr_desc_acres),
    ('Custo',   'Custo da mercadoria vendida', 'CMV', -ic.vr_custo)
) AS x(natureza, grupo_dre, conta, valor)
WHERE x.valor <> 0

UNION ALL
-- 2) Trocas/devoluções (só existem no relatório por venda): custo da mercadoria trocada
SELECT v.data_venda, 'ERP vendas', 'Custo', 'Custo da mercadoria vendida', 'CMV - trocas e devoluções',
       COALESCE(NULLIF(v.loja, ''), e.nome_loja, e.razao_social), v.cnpj, NULL, NULL, NULL, 'Troca/devolução ' || v.controle, NULL,
       v.vr_lucro, true, false, 'vendas.fato_venda ' || v.controle,
       CASE WHEN v.loja ILIKE 'ORTOBOM%' THEN 'ORTOBOM' ELSE 'ELETROMÓVEIS' END, NULL
FROM vendas.fato_venda v
JOIN vendas.dim_empresa e USING (cnpj)
WHERE v.tipo <> 'VENDA' AND v.vr_lucro <> 0

UNION ALL
-- 3) Caixa diário: entradas (recebimentos)
SELECT l.data, 'Caixa diário', 'Recebimento', 'Recebimentos', COALESCE(NULLIF(l.conta, ''), l.descricao),
       COALESCE(NULLIF(l.loja, ''), CASE WHEN l.negocio = 'ORTOBOM' THEN 'ORTOBOM' ELSE 'Geral' END),
       NULL, NULL, NULL, NULL, l.descricao, NULL,
       l.valor, false, l.entra_no_total, 'financeiro.fato_caixa_lancamento ' || l.aba || '!' || l.celula,
       COALESCE(l.negocio, 'ELETROMÓVEIS'), NULL
FROM fato_caixa_lancamento l
WHERE l.tipo = 'ENTRADA'

UNION ALL
-- 4) Caixa diário: saídas classificadas pelo plano de contas
SELECT s.data, 'Caixa diário',
       CASE WHEN s.entra_no_dre THEN 'Despesa' ELSE 'Saída fora da DRE' END,
       s.grupo_dre, s.conta_gerencial, u.loja, NULL, NULL, NULL, NULL, s.descricao, NULL,
       -s.valor / cardinality(u.lojas), s.entra_no_dre, s.entra_no_total, 'financeiro.fato_caixa_lancamento ' || s.aba || '!' || s.celula,
       CASE WHEN u.loja ILIKE 'ORTOBOM%' THEN 'ORTOBOM' ELSE COALESCE(s.negocio, 'ELETROMÓVEIS') END, NULL
FROM vw_caixa_saida_classificada s
-- loja 'GRAÇA|MUCAMBO' vira duas linhas com metade do valor cada
CROSS JOIN LATERAL (SELECT string_to_array(s.loja_inferida, '|') AS lojas) a
CROSS JOIN LATERAL (SELECT trim(x) AS loja, a.lojas FROM unnest(a.lojas) x) u

UNION ALL
-- 5) Metas de venda (config/metas_vendas.csv): meta do dia, por loja e dia de venda. Fora da DRE e do fluxo.
SELECT m.data, 'Meta de vendas', 'Meta', 'Meta de vendas', 'Meta de venda líquida', m.loja, NULL, NULL, NULL, NULL,
       'Meta ' || lpad(m.mes::text, 2, '0') || '/' || m.ano, NULL,
       m.meta_dia, false, false, 'vendas.meta_venda ' || m.ano || '-' || m.mes || ' ' || m.loja, m.negocio, NULL
FROM vendas.vw_meta_venda_dia m;

COMMENT ON VIEW vw_fato_principal IS
 'Fato única do BI. valor: receita +, custo/despesa/saída -. DRE = SUM(valor) WHERE entra_no_dre; Fluxo = SUM(valor) WHERE entra_no_fluxo; Meta = SUM(valor) WHERE origem = ''Meta de vendas''.';
