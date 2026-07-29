# Realizado x Carteira â€” Julho 2026

Teste isolado dos repositÃ³rios existentes. Nenhum arquivo dos repositÃ³rios
`ETLdados` ou `Relat-rio-de-Vendas---Gerencial` foi alterado.

## Resultado

O site mostra, por contrato:

- realizado diÃ¡rio e acumulado;
- carteira diÃ¡ria e acumulada;
- potencial comercial (`realizado + carteira`);
- conciliaÃ§Ã£o do realizado com `WWWPD010.xlsx`;
- verificaÃ§Ã£o cadastral com `INDEX.xlsx`.

Contratos:

- `DL`: LED
- `DP`: PlÃ¡stico
- `DU`: AlumÃ­nio
- `DX`: EX

## Atualizar os dados

Coloque em `dados/`:

- `carteira.xlsx`, com as colunas do arquivo â€œExtraÃ§Ã£o em Tabelaâ€;
- `WWWPD010.xlsx`;
- `INDEX.xlsx`.

Depois:

```bash
npm install
npm run gerar
```

O comando substitui `dados-julho.json`. O site contÃ©m somente dados agregados;
arquivos brutos devem permanecer privados.

## ConciliaÃ§Ã£o encontrada

Total realizado fecha exatamente entre arquivo enviado e `WWWPD010.xlsx`.
Existe reclassificaÃ§Ã£o de R$ 6.807,55 entre PlÃ¡stico e AlumÃ­nio nas fontes.
Representante `9958` nÃ£o consta no `INDEX.xlsx`.
