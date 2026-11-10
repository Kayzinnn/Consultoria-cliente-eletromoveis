-- =============================================================================
-- Zé&Maria — Banco de vendas (fonte: relatórios "Lucratividade" do ERP, em PDF)
-- PostgreSQL 13+. Rode uma vez no banco do cliente:  psql -d ze_maria -f 01_schema.sql
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS vendas;
SET search_path TO vendas;

-- Empresas / lojas (1 linha por CNPJ) ----------------------------------------
CREATE TABLE IF NOT EXISTS dim_empresa (
    cnpj               char(18)     PRIMARY KEY,          -- 21.539.993/0001-44
    razao_social       text         NOT NULL,
    nome_loja          text,                              -- preencher: ex. "Matriz", "Mucambo"
    uf                 char(2),
    inscricao_estadual text
);

-- Regras de categoria: o produto recebe a regra cujo prefixo da descrição é o mais longo.
-- Edite esta tabela (ou config/regras_categoria.csv) para reclassificar sem mexer em código.
CREATE TABLE IF NOT EXISTS regra_categoria (
    prefixo    text PRIMARY KEY,
    categoria  text NOT NULL,
    grupo      text NOT NULL
);

-- Produtos (cadastro deduzido dos relatórios) --------------------------------
CREATE TABLE IF NOT EXISTS dim_produto (
    cod_produto        varchar(20)  PRIMARY KEY,          -- código de barras interno (13 dígitos)
    descricao          text         NOT NULL,             -- última descrição vista
    categoria_manual   text,                              -- preencha para sobrepor a regra
    grupo_manual       text,
    primeira_venda     date,
    ultima_venda       date,
    atualizado_em      timestamptz  NOT NULL DEFAULT now()
);

-- Calendário para o BI ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_calendario (
    data          date PRIMARY KEY,
    ano           int, mes int, dia int, trimestre int,
    ano_mes       char(7),            -- 2026-01
    nome_mes      text,               -- Janeiro
    mes_abrev     text,               -- jan/26
    dia_semana    int,                -- 1 = segunda ... 7 = domingo
    nome_dia      text,
    fim_de_semana boolean
);

-- Controle de cargas (1 linha por execução) ------------------------------------
CREATE TABLE IF NOT EXISTS controle_carga (
    id_carga              serial       PRIMARY KEY,
    carregado_em          timestamptz  NOT NULL DEFAULT now(),
    cnpj                  char(18)     NOT NULL REFERENCES dim_empresa,
    arquivo_produto       text, periodo_produto_ini date, periodo_produto_fim date,
    arquivo_venda         text, periodo_venda_ini   date, periodo_venda_fim   date,
    linhas_item           int, linhas_venda int,
    total_liquido         numeric(14,2),
    observacao            text
);

-- Vendas (1 linha por controle/cupom) — relatório "Lucratividade por venda" ----
CREATE TABLE IF NOT EXISTS fato_venda (
    cnpj                 char(18)      NOT NULL REFERENCES dim_empresa,
    controle             varchar(20)   NOT NULL,           -- AAAAMMDDHHMMSS
    data_venda           date          NOT NULL,
    data_hora            timestamp,
    tipo                 text          NOT NULL CHECK (tipo IN ('VENDA','TROCA/DEVOLUÇÃO')),
    vr_bruto             numeric(14,2) NOT NULL,
    vr_desc_acres        numeric(14,2) NOT NULL,           -- negativo = desconto, positivo = acréscimo
    vr_liquido           numeric(14,2) NOT NULL,
    vr_custo             numeric(14,2) NOT NULL,
    vr_lucro             numeric(14,2) NOT NULL,
    vr_coluna_extra      numeric(14,2),                    -- valor sem título que aparece nas trocas
    arquivo_origem       text,
    pagina               int,
    id_carga             int REFERENCES controle_carga,
    PRIMARY KEY (cnpj, controle)
);
CREATE INDEX IF NOT EXISTS ix_fato_venda_data ON fato_venda (cnpj, data_venda);

-- Itens vendidos (produto x dia) — relatório "Lucratividade por produto" -------
-- Atenção: o ERP agrupa por dia o mesmo produto; qtd 2 pode ser 2 vendas diferentes.
CREATE TABLE IF NOT EXISTS fato_venda_item (
    cnpj                 char(18)      NOT NULL REFERENCES dim_empresa,
    data_venda           date          NOT NULL,
    seq_dia              int           NOT NULL,           -- ordem da linha no dia
    cod_produto          varchar(20)   NOT NULL REFERENCES dim_produto,
    descricao_original   text,
    qtd                  int           NOT NULL,
    vr_bruto             numeric(14,2) NOT NULL,
    vr_desc_acres        numeric(14,2) NOT NULL,
    vr_liquido           numeric(14,2) NOT NULL,
    vr_custo             numeric(14,2) NOT NULL,
    vr_lucro             numeric(14,2) NOT NULL,
    arquivo_origem       text,
    pagina               int,
    id_carga             int REFERENCES controle_carga,
    PRIMARY KEY (cnpj, data_venda, seq_dia)
);
CREATE INDEX IF NOT EXISTS ix_fato_item_produto ON fato_venda_item (cod_produto);

-- Ponte item x venda (deduzida pelo script vincular_itens_vendas.py) -----------
CREATE TABLE IF NOT EXISTS fato_venda_item_vinculo (
    cnpj            char(18)      NOT NULL,
    data_venda      date          NOT NULL,
    seq_dia         int           NOT NULL,
    controle        varchar(20)   NOT NULL DEFAULT '',     -- '' quando SEM_VINCULO
    qtd             int           NOT NULL,
    vr_liquido      numeric(14,2) NOT NULL,
    vr_custo        numeric(14,2) NOT NULL,
    status_vinculo  text          NOT NULL CHECK (status_vinculo IN ('UNICO','AMBIGUO','SEM_VINCULO')),
    id_carga        int REFERENCES controle_carga,
    PRIMARY KEY (cnpj, data_venda, seq_dia, controle),
    FOREIGN KEY (cnpj, data_venda, seq_dia) REFERENCES fato_venda_item ON DELETE CASCADE
);

-- Calendário 2024–2030 (idempotente) ------------------------------------------
INSERT INTO dim_calendario
SELECT d::date,
       extract(year from d)::int, extract(month from d)::int, extract(day from d)::int,
       extract(quarter from d)::int,
       to_char(d, 'YYYY-MM'),
       (ARRAY['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto',
              'Setembro','Outubro','Novembro','Dezembro'])[extract(month from d)::int],
       (ARRAY['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'])[extract(month from d)::int]
           || '/' || to_char(d, 'YY'),
       extract(isodow from d)::int,
       (ARRAY['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'])[extract(isodow from d)::int],
       extract(isodow from d) >= 6
FROM generate_series('2024-01-01'::date, '2030-12-31'::date, interval '1 day') d
ON CONFLICT (data) DO NOTHING;
