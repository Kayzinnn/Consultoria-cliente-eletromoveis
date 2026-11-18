# BI em HTML — Painel de Resultados Zé&Maria

Versão web do Power BI (`PowerBI/BI_ze_maria_eletromoveis.pbip`), com as mesmas páginas, filtros e regras de cálculo, para abrir no navegador ou publicar num link com login.

## Páginas

| Página | Equivale a | O que tem |
|---|---|---|
| Resultados | Resumo Geral | 6 cards, vendas e lucro em 12 meses, cascata "para onde vai o dinheiro", desempenho por filial |
| Vendas | Vendas | Matriz que abre por grupo › categoria › produto (ou filial, na ordem que escolher) |
| Meta | Atingir Meta | Ritmo de vendas do mês por filial: meta, vendido, projeção e desvio |
| DRE | DRE Acum | DRE mês a mês, com visão Realizado / Meta / Meta mês cheio / Desvio R$ / Desvio %, abrindo por filial |
| Real × meta | DRE Mensal | DRE do período com real, meta e desvio lado a lado, abrindo por filial e por lançamento |

Filtros (valem para todas as páginas): **Ano**, **Filial** e **Mês**, com seleção múltipla. Um mês mostra só o mês; vários meses somam.

## Regras de cálculo (iguais às medidas DAX)

- **Data de referência:** último dia do período filtrado que tem venda carregada. O período é cortado nesse dia.
- **Ano anterior:** os mesmos dias do período, um ano antes.
- **Meta / desvio:** usam `financeiro.vw_orcamento_dia`. O desvio compara o real só dos meses que têm meta cadastrada (melhoria em relação ao Power BI, que comparava o período inteiro).
- **Vendas 12 meses:** sempre os 12 meses até a última venda, sem o filtro de mês.

## Como atualizar

Depois de atualizar o banco (`processa_vendas.py`, `atualizar_financeiro.py`, etc.):

```powershell
python BI_HTML\exportar_dados.py
```

Isso gera `BI_HTML\site\dados\dados.js` com os dados agregados. Para ver, abra `BI_HTML\site\index.html` no navegador (duplo clique).

> `site/dados/` tem dados da cliente: está no `.gitignore` e **nunca** vai para o GitHub.

## Estrutura

```
BI_HTML/
  exportar_dados.py    lê o PostgreSQL e gera site/dados/dados.js
  site/
    index.html         página única (navegação por #resumo, #vendas, #meta, #dre, #dremes)
    estilo.css         visual (mesmas cores e fonte dos mockups do Power BI)
    motor.js           filtros e cálculos (equivalente às medidas DAX)
    app.js             páginas, cards, gráficos e matrizes
    lib/               ECharts e fonte Manrope (sem depender de internet)
    dados/dados.js     gerado pelo exportar_dados.py (fora do git)
```

## Publicar com login (Cloudflare Pages + Access)

O site fica em `https://painel-zemaria.pages.dev` e só abre para os e-mails autorizados: a pessoa digita o e-mail, recebe um código e entra.

### Configuração (uma vez só)

**Ordem importa:** primeiro publica uma página vazia, depois liga o login, e só então publica os dados.

1. **Conta:** crie em https://dash.cloudflare.com/sign-up
2. **Node.js:** no terminal, `node -v`. Se não existir, instale a versão LTS em https://nodejs.org
3. **Login do terminal na Cloudflare** (abre o navegador para autorizar):
   ```
   npx wrangler login
   ```
4. **Criar o projeto com a página vazia** (sem dados):
   ```
   npx wrangler pages project create painel-zemaria --production-branch main
   npx wrangler pages deploy BI_HTML\site_inicial --project-name painel-zemaria --branch main
   ```
   Se o nome `painel-zemaria` já existir na Cloudflare, use outro e troque também a linha `set PROJETO=` do `publicar.bat`.
5. **Ligar o login (Access):**
   - No painel da Cloudflare, abra **Zero Trust**. Na primeira vez ele pede um nome de equipe e o plano: escolha **Free** (até 50 usuários).
   - **Access › Applications › Add an application › Self-hosted**.
   - Nome: `Painel Zé&Maria`. Domínio: `painel-zemaria.pages.dev`. Adicione também `*.painel-zemaria.pages.dev`, que protege as versões antigas de cada publicação.
   - **Policy:** Action = Allow; Include = Emails, com a lista de quem pode ver.
   - Login method: **One-time PIN** (código por e-mail).
6. **Testar numa janela anônima:** abrir o link tem que pedir e-mail e código. Só siga se pedir.
7. **Publicar os dados:** dois cliques em `BI_HTML\publicar.bat`.

### Dia a dia

Depois de atualizar o banco, rode `BI_HTML\publicar.bat`. Ele exporta os dados e publica. Para incluir ou tirar alguém, edite a lista de e-mails da policy no Zero Trust.

### Como está configurado hoje

- Site: `https://painel-zemaria.pages.dev` (projeto Pages `painel-zemaria`).
- Zero Trust (plano Free), equipe `rough-dew-5d7a`. Aplicação de Access `painel-zemaria - Cloudflare Pages` protegendo `painel-zemaria.pages.dev` e `*.painel-zemaria.pages.dev`.
- Regras: `Allow Members` (membros da conta Cloudflare) e `Colaboradores Ze&Maria` (lista de e-mails). Para incluir alguém: Zero Trust › Access controls › Policies › Colaboradores Ze&Maria › Edit.
- Login por código no e-mail (One-time PIN). Atenção: o código **não chegou em endereço Hotmail** no teste; no Gmail funcionou. Para quem usa Hotmail, usar outro e-mail ou configurar login com conta Microsoft.
