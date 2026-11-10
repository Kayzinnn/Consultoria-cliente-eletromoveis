-- =============================================================================
-- Metas de venda (orçamento) por loja e mês -> meta diária por dia de venda.
-- Alimentado por config/metas_vendas.csv e config/dias_sem_venda.csv (python atualizar_metas.py).
-- As metas também entram na financeiro.vw_fato_principal com origem 'Meta de vendas' (04_fato_principal.sql). Arquivo 03b: roda antes do 04.
-- =============================================================================
CREATE TABLE IF NOT EXISTS vendas.meta_venda (
    ano          int           NOT NULL,
    mes          int           NOT NULL CHECK (mes BETWEEN 1 AND 12),
    loja         text          NOT NULL,
    meta_mes     numeric(14,2) NOT NULL,
    atualizado_em timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (ano, mes, loja)
);

CREATE TABLE IF NOT EXISTS vendas.dia_sem_venda (
    data       date NOT NULL,
    loja       text NOT NULL DEFAULT '',     -- '' = todas as lojas
    descricao  text,
    PRIMARY KEY (data, loja)
);

-- Um registro por loja e dia de venda (sem domingos e sem os dias fechados), com a meta do dia.
CREATE OR REPLACE VIEW vendas.vw_meta_venda_dia AS
WITH dias AS (
    SELECT m.ano, m.mes, m.loja, m.meta_mes, d::date AS data
    FROM vendas.meta_venda m
    CROSS JOIN LATERAL generate_series(make_date(m.ano, m.mes, 1),
                                       (make_date(m.ano, m.mes, 1) + interval '1 month - 1 day')::date,
                                       interval '1 day') d
    WHERE extract(isodow FROM d) <> 7
      AND NOT EXISTS (SELECT 1 FROM vendas.dia_sem_venda f
                      WHERE f.data = d::date AND (f.loja = '' OR upper(f.loja) = upper(m.loja)))
)
SELECT data, ano, mes, loja,
       CASE WHEN loja ILIKE 'ORTOBOM%' THEN 'ORTOBOM' ELSE 'ELETROMÓVEIS' END AS negocio,
       meta_mes,
       count(*) OVER (PARTITION BY ano, mes, loja)                         AS dias_venda_mes,
       meta_mes / count(*) OVER (PARTITION BY ano, mes, loja)             AS meta_dia
FROM dias;

COMMENT ON VIEW vendas.vw_meta_venda_dia IS
 'Meta diária de venda líquida por loja = meta do mês / dias de venda do mês (sem domingos e dias fechados).';
