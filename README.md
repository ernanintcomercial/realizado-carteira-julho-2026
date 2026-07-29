# Realizado x Carteira — Julho 2026

Teste isolado dos repositórios existentes. Nenhum arquivo dos repositórios
`ETLdados` ou `Relat-rio-de-Vendas---Gerencial` foi alterado.

## Resultado

O site mostra, por contrato:

- realizado diário e acumulado;
- carteira diária e acumulada;
- potencial comercial (`realizado + carteira`);
- conciliação do realizado com `WWWPD010.xlsx`;
- verificação cadastral com `INDEX.xlsx`.

Contratos:

- `DL`: LED
- `DP`: Plástico
- `DU`: Alumínio
- `DX`: EX

## Atualizar os dados

Coloque em `dados/`:

- `carteira.xlsx`, com as colunas do arquivo “Extração em Tabela”;
- `WWWPD010.xlsx`;
- `INDEX.xlsx`.

Depois:

```bash
npm install
npm run gerar
```

O comando substitui `dados-julho.json`. O site contém somente dados agregados;
arquivos brutos devem permanecer privados.

## Conciliação encontrada

Total realizado fecha exatamente entre arquivo enviado e `WWWPD010.xlsx`.
Existe reclassificação de R$ 6.807,55 entre Plástico e Alumínio nas fontes.
Representante `9958` não consta no `INDEX.xlsx`.
