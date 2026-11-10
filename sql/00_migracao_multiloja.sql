-- =============================================================================
-- Migração: adiciona a coluna "loja" às tabelas de vendas de bancos criados antes
-- da versão multiloja. Só age se a coluna ainda não existir (pode rodar sempre).
-- As vendas antigas são apagadas: recarregue com  python processa_vendas.py
-- =============================================================================
DO $$
BEGIN
  IF to_regclass('vendas.fato_venda') IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'vendas' AND table_name = 'fato_venda' AND column_name = 'loja') THEN
    RAISE NOTICE 'Migrando vendas para multiloja: dados de vendas apagados, rode processa_vendas.py';
    DROP VIEW IF EXISTS financeiro.vw_fato_principal;
    DROP VIEW IF EXISTS vendas.vw_resumo_diario, vendas.vw_venda_item_por_controle, vendas.vw_venda,
                        vendas.vw_venda_item, vendas.vw_produto CASCADE;
    DROP TABLE vendas.fato_venda_item_vinculo, vendas.fato_venda_item, vendas.fato_venda;
    ALTER TABLE vendas.controle_carga ADD COLUMN IF NOT EXISTS loja text NOT NULL DEFAULT '';
  END IF;
END $$;
