-- =============================================================================
-- Views para o Power BI (conecte nelas, não nas tabelas)
-- =============================================================================
SET search_path TO vendas;
-- recria as views do zero (a estrutura mudou com a coluna loja); a fato principal é recriada no 04
DROP VIEW IF EXISTS vw_resumo_diario, vw_venda_item_por_controle, vw_venda, vw_venda_item, vw_produto CASCADE;

-- Produto com categoria (regra de prefixo mais longo; manual tem prioridade)
CREATE OR REPLACE VIEW vw_produto AS
SELECT p.cod_produto,
       p.descricao,
       COALESCE(p.categoria_manual, r.categoria, 'A classificar') AS categoria,
       COALESCE(p.grupo_manual,     r.grupo,     'A classificar') AS grupo,
       (COALESCE(p.grupo_manual, r.grupo) = 'Não é venda de mercadoria') AS nao_e_mercadoria,
       p.primeira_venda, p.ultima_venda
FROM dim_produto p
LEFT JOIN LATERAL (
    SELECT categoria, grupo FROM regra_categoria rc
    WHERE p.descricao = rc.prefixo OR p.descricao LIKE rc.prefixo || ' %'
    ORDER BY length(rc.prefixo) DESC
    LIMIT 1
) r ON true;

-- Fato de itens pronto para o BI
CREATE OR REPLACE VIEW vw_venda_item AS
SELECT i.cnpj, COALESCE(NULLIF(i.loja, ''), e.nome_loja, e.razao_social) AS loja, i.data_venda, i.seq_dia,
       i.cod_produto, p.descricao, p.categoria, p.grupo, p.nao_e_mercadoria,
       i.qtd, i.vr_bruto, i.vr_desc_acres, i.vr_liquido, i.vr_custo, i.vr_lucro,
       (i.vr_custo <= 0.01 * i.qtd) AS custo_nao_cadastrado
FROM fato_venda_item i
JOIN dim_empresa e USING (cnpj)
JOIN vw_produto  p USING (cod_produto);

-- Fato de vendas (cupons) pronto para o BI
CREATE OR REPLACE VIEW vw_venda AS
SELECT v.cnpj, COALESCE(NULLIF(v.loja, ''), e.nome_loja, e.razao_social) AS loja, v.controle, v.data_venda, v.data_hora,
       extract(hour from v.data_hora)::int AS hora,
       v.tipo, (v.tipo = 'VENDA') AS e_venda,
       v.vr_bruto, v.vr_desc_acres, v.vr_liquido, v.vr_custo, v.vr_lucro,
       q.itens, q.qtd_pecas, q.status_vinculo
FROM fato_venda v
JOIN dim_empresa e USING (cnpj)
LEFT JOIN (
    SELECT cnpj, loja, controle, count(*) AS itens, sum(qtd) AS qtd_pecas, min(status_vinculo) AS status_vinculo
    FROM fato_venda_item_vinculo WHERE controle <> ''
    GROUP BY cnpj, loja, controle
) q ON q.cnpj = v.cnpj AND q.loja = v.loja AND q.controle = v.controle;

-- Item dentro de cada venda (só onde o vínculo é confiável)
CREATE OR REPLACE VIEW vw_venda_item_por_controle AS
SELECT b.cnpj, b.loja, b.controle, b.data_venda, i.cod_produto, p.descricao, p.categoria, p.grupo,
       b.qtd, b.vr_liquido, b.vr_custo, b.vr_liquido - b.vr_custo AS vr_lucro, b.status_vinculo
FROM fato_venda_item_vinculo b
JOIN fato_venda_item i USING (cnpj, loja, data_venda, seq_dia)
JOIN vw_produto p USING (cod_produto)
WHERE b.status_vinculo = 'UNICO';

-- Resumo diário (conferência rápida e cartões do BI)
CREATE OR REPLACE VIEW vw_resumo_diario AS
SELECT v.cnpj, v.loja, v.data_venda,
       count(*) FILTER (WHERE v.tipo = 'VENDA')            AS qtd_vendas,
       count(*) FILTER (WHERE v.tipo <> 'VENDA')           AS qtd_trocas,
       sum(v.vr_liquido)                                    AS receita_liquida,
       sum(v.vr_custo)                                      AS custo,
       sum(v.vr_lucro)                                      AS lucro_bruto,
       round(sum(v.vr_liquido) / NULLIF(count(*) FILTER (WHERE v.tipo = 'VENDA'), 0), 2) AS ticket_medio
FROM fato_venda v
GROUP BY v.cnpj, v.loja, v.data_venda;
