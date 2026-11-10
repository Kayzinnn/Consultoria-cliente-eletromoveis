-- =============================================================================
-- Zé&Maria — Financeiro (fonte: planilhas da Veronica, sempre no mesmo caminho)
--   BOLETOS A PAGAR  -> fato_conta_pagar
--   PLAN GERAL       -> fato_caixa_lancamento + fato_caixa_dia
-- psql -d ze_maria -f 03_financeiro.sql
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS financeiro;
SET search_path TO financeiro;

-- 1 linha por arquivo carregado (o hash evita recarregar arquivo que não mudou)
CREATE TABLE IF NOT EXISTS controle_carga (
    id_carga       serial      PRIMARY KEY,
    carregado_em   timestamptz NOT NULL DEFAULT now(),
    fonte          text        NOT NULL CHECK (fonte IN ('CONTAS_PAGAR','CAIXA_DIARIO')),
    arquivo        text        NOT NULL,          -- nome do arquivo
    caminho        text,
    sha256         char(64)    NOT NULL,
    modificado_em  timestamp,                     -- data de modificação do arquivo
    linhas         int,
    total_valor    numeric(16,2),
    alertas        jsonb
);

-- Contas a pagar / boletos -----------------------------------------------------
CREATE TABLE IF NOT EXISTS fato_conta_pagar (
    arquivo              text          NOT NULL,
    aba                  text          NOT NULL,
    linha_planilha       int           NOT NULL,      -- nº da linha no Excel (rastreio)
    data_vencimento      date,
    fornecedor           text,
    forma_pgto           text,                        -- DUPLICATA, CHEQUE, DINHEIRO, DEPOSITO/PIX, CARNE, DEBITO EM CONTA, OUTROS
    forma_pgto_original  text,
    num_cheque           text,
    banco_cheque         text,
    valor                numeric(14,2),
    parcela_original     text,
    parcela_num          int,
    parcela_total        int,
    loja                 text,                        -- GRAÇA | MUCAMBO | vazio
    loja_original        text,                        -- texto da coluna LOJA (muitas vezes é anotação)
    nota_fiscal          text,
    observacao           text,
    possivel_pessoal     boolean       NOT NULL DEFAULT false,
    cor_marcacao         text,                        -- cor de fundo da linha no Excel
    id_carga             int REFERENCES controle_carga,
    PRIMARY KEY (arquivo, aba, linha_planilha)
);
CREATE INDEX IF NOT EXISTS ix_cp_venc ON fato_conta_pagar (data_vencimento);

-- Caixa diário: lançamentos ----------------------------------------------------
CREATE TABLE IF NOT EXISTS fato_caixa_lancamento (
    arquivo          text          NOT NULL,
    aba              text          NOT NULL,
    celula           text          NOT NULL,          -- célula do valor no Excel (rastreio)
    data             date          NOT NULL,
    tipo             text          NOT NULL CHECK (tipo IN ('ENTRADA','SAIDA')),
    ordem            int,
    descricao        text,
    valor            numeric(14,2) NOT NULL,
    loja             text,                            -- só entradas (config/mapa_entradas_caixa.csv)
    meio             text,
    conta            text,
    entra_no_total   boolean       NOT NULL,          -- a fórmula de total da planilha soma esta linha?
    id_carga         int REFERENCES controle_carga,
    PRIMARY KEY (arquivo, aba, celula)
);
CREATE INDEX IF NOT EXISTS ix_caixa_data ON fato_caixa_lancamento (data);
-- ELETROMÓVEIS | ORTOBOM (pelo nome do arquivo da planilha)
ALTER TABLE fato_caixa_lancamento ADD COLUMN IF NOT EXISTS negocio text;

-- Caixa diário: saldos do dia ----------------------------------------------------
CREATE TABLE IF NOT EXISTS fato_caixa_dia (
    data                     date PRIMARY KEY,
    arquivo                  text NOT NULL,
    aba                      text, celula text,
    saldo_inicial            numeric(14,2),
    total_entrada            numeric(14,2),           -- como a planilha calcula
    total_saida              numeric(14,2),
    saldo_final              numeric(14,2),           -- como a planilha mostra
    saldo_final_recalculado  numeric(14,2),           -- saldo inicial + total entrada - total saída
    saldo_final_anterior     numeric(14,2),
    diferenca_abertura       numeric(14,2),           -- saldo inicial - saldo final do dia anterior
    entradas_fora_total      numeric(14,2),           -- linhas de entrada que a fórmula não soma
    saidas_fora_total        numeric(14,2),
    id_carga                 int REFERENCES controle_carga
);
-- várias planilhas de caixa (eletromóveis, Ortobom): a mesma data aparece uma vez por arquivo
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
               JOIN pg_namespace n ON n.oid = t.relnamespace
               WHERE n.nspname = 'financeiro' AND t.relname = 'fato_caixa_dia' AND c.contype = 'p'
                 AND array_length(c.conkey, 1) = 1) THEN
        ALTER TABLE financeiro.fato_caixa_dia DROP CONSTRAINT fato_caixa_dia_pkey;
        ALTER TABLE financeiro.fato_caixa_dia ADD PRIMARY KEY (arquivo, data);
    END IF;
END $$;

-- Views para o BI ------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_conta_pagar AS
SELECT c.*,
       date_trunc('month', data_vencimento)::date AS mes_vencimento,
       (cor_marcacao IS NOT NULL)                    AS marcado_na_planilha,     -- hipótese: colorido = pago
       CASE WHEN data_vencimento IS NULL           THEN 'Sem data'
            WHEN cor_marcacao IS NOT NULL          THEN 'Marcado (provável pago)'
            WHEN data_vencimento <  current_date   THEN 'Vencido sem marcação'
            ELSE 'A vencer' END                      AS situacao
FROM fato_conta_pagar c;

DROP VIEW IF EXISTS vw_caixa_lancamento;   -- l.* ganhou colunas novas
CREATE OR REPLACE VIEW vw_caixa_lancamento AS
SELECT l.*, date_trunc('month', l.data)::date AS mes,
       (l.tipo = 'SAIDA' AND l.descricao ~* '(PESSOAL|\mCASA\M|\mCPF\M)') AS possivel_pessoal
FROM fato_caixa_lancamento l;

DROP VIEW IF EXISTS vw_caixa_alertas;
CREATE OR REPLACE VIEW vw_caixa_alertas AS
SELECT data, arquivo, 'Saldo inicial diferente do saldo final do dia anterior' AS alerta, diferenca_abertura AS valor
  FROM fato_caixa_dia WHERE diferenca_abertura <> 0
UNION ALL
SELECT data, arquivo, 'Saldo final da planilha diferente do recalculado (fórmula)', saldo_final - saldo_final_recalculado
  FROM fato_caixa_dia WHERE saldo_final <> saldo_final_recalculado
UNION ALL
SELECT data, arquivo, 'Entradas listadas que a fórmula de total não soma', entradas_fora_total
  FROM fato_caixa_dia WHERE entradas_fora_total <> 0
ORDER BY arquivo, data, alerta;
