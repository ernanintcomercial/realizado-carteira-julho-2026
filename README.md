# Painel Comercial Integrado

Dashboard gerencial de metas, total geral e composição da carteira.

## Fontes

As fontes permanecem no repositório privado `ernanintcomercial/ETLdados`:

- `WWWPD010.xlsx`: total geral e carteira do mês atual;
- `WWWPD019.xlsx`: metas comerciais;
- `INDEX.xlsx`: regiões e representantes.

Nenhum Excel bruto é publicado neste repositório. O GitHub Pages usa somente
os arquivos agregados `dados-historicos.json` e `dados-gerenciais.json`.

## Regras principais

- corte no último dia útil anterior à execução;
- Total Geral: ROB, excluindo situações canceladas;
- Carteira: ROB das situações `Abertos` e `Atendido Parcial`;
- Sem Carteira: Total Geral menos Carteira;
- a Carteira já faz parte do Total Geral e nunca é somada novamente;
- os meses encerrados ficam congelados em `dados-historicos.json`;
- o PD010 diário precisa conter somente o mês atual;
- histórico ou mês atual incompleto bloqueia a publicação.

## Fechamento mensal e conciliação

No início de cada mês, o mês recém-encerrado deve ser incorporado ao
`dados-historicos.json` antes de o PD010 diário passar a representar o novo mês.
O PD010 anual permanece como fonte de auditoria quinzenal durante a estabilização
e, depois, mensal. Divergências bloqueiam a substituição automática do histórico.

## Meta acumulada

O ETL prepara a meta até o corte usando:

`Meta mensal × dias úteis transcorridos ÷ dias úteis totais do mês`

O arquivo `config/feriados.json` poderá receber datas no formato
`YYYY-MM-DD`. Enquanto estiver vazio, são considerados dias úteis de segunda
a sexta.

## Automação preparada, mas desativada

O workflow `.github/workflows/atualizar-dashboard.yml` possui somente execução
manual e ainda exige:

1. secret `ETL_REPO_TOKEN`, com leitura do repositório privado `ETLdados`;
2. variável `AUTOMACAO_ETL_ATIVA` com valor `true`.

Sem essa variável, o job não executa. Não há agendamento automático ativo.

Quando ativado, o workflow:

1. baixa as fontes do `ETLdados` sem alterá-lo;
2. verifica presença e idade dos arquivos mensais;
3. combina a base histórica com o PD010 do mês atual;
4. bloqueia a publicação se alguma conciliação falhar;
5. atualiza somente `dados-gerenciais.json`.

## Desenvolvimento local

```powershell
python etl/gerar_dashboard.py `
  --pd010 caminho/WWWPD010.xlsx `
  --pd019 caminho/WWWPD019.xlsx `
  --index caminho/INDEX.xlsx `
  --history dados-historicos.json `
  --holidays config/feriados.json `
  --output dados-gerenciais.json
```

Os repositórios `ETLdados` e `Relat-rio-de-Vendas---Gerencial` continuam
inalterados.
