-- =============================================================================
-- Orçamento mensal da DRE (receitas, CMV e despesas) por conta e loja.
-- Gerado por python gerar_orcamento.py --mes AAAA-MM (regra: média dos 3 meses anteriores;
-- receita e CMV seguem a meta de vendas da loja). Fica gravado: o orçamento de um mês não muda
-- quando o real muda, só se o script for rodado de novo para aquele mês.
-- =============================================================================
CREATE TABLE IF NOT EXISTS financeiro.orcamento (
    ano        int           NOT NULL,
    mes        int           NOT NULL CHECK (mes BETWEEN 1 AND 12),
    natureza   text          NOT NULL,           -- Receita | Custo | Despesa
    grupo_dre  text          NOT NULL,
    conta      text          NOT NULL,
    loja       text          NOT NULL,
    negocio    text,
    valor      numeric(14,2) NOT NULL,           -- mesmo sinal do real: receita +, custo/despesa -
    distribuir text          NOT NULL DEFAULT 'corridos',   -- 'venda' (dias de venda) | 'corridos' (todos os dias)
    criterio   text,
    gerado_em  timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (ano, mes, grupo_dre, conta, loja)
);

-- Orçamento distribuído por dia, para comparar com o real até a data de referência.
-- Receita e CMV: pelos dias de venda (sem domingos e dias fechados), como a meta. Despesas: dias corridos.
CREATE OR REPLACE VIEW financeiro.vw_orcamento_dia AS
WITH dias AS (
    SELECT o.*, d::date AS data
    FROM financeiro.orcamento o
    CROSS JOIN LATERAL generate_series(make_date(o.ano, o.mes, 1),
                                       (make_date(o.ano, o.mes, 1) + interval '1 month - 1 day')::date,
                                       interval '1 day') d
    WHERE o.distribuir = 'corridos'
       OR (extract(isodow FROM d) <> 7
           AND NOT EXISTS (SELECT 1 FROM vendas.dia_sem_venda f
                           WHERE f.data = d::date AND (f.loja = '' OR upper(f.loja) = upper(o.loja))))
)
SELECT data, ano, mes, natureza, grupo_dre, conta, loja, negocio, criterio,
       valor / count(*) OVER (PARTITION BY ano, mes, grupo_dre, conta, loja) AS valor
FROM dias;

COMMENT ON VIEW financeiro.vw_orcamento_dia IS
 'Orçamento da DRE por dia (financeiro.orcamento distribuído). valor com o mesmo sinal da vw_fato_principal.';
