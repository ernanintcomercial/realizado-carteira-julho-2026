from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

import pandas as pd


CONTRACTS = {
    "DL": "LED",
    "DP": "PLÁSTICO",
    "DU": "ALUMÍNIO",
    "DX": "EX",
    "EX": "EX",
}
CONTRACT_ORDER = ["ALUMÍNIO", "PLÁSTICO", "LED", "EX"]
REGION_ORDER = ["SUL E CENTRO OESTE", "SUDESTE", "NORTE E NORDESTE"]
MONTH_NAMES = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]
UF_CODE_TO_NAME = {
    "AC": "ACRE", "AL": "ALAGOAS", "AP": "AMAPA", "AM": "AMAZONAS",
    "BA": "BAHIA", "CE": "CEARA", "DF": "DISTRITO FEDERAL",
    "ES": "ESPIRITO SANTO", "GO": "GOIAS", "MA": "MARANHAO",
    "MT": "MATO GROSSO", "MS": "MATO GROSSO DO SUL",
    "MG": "MINAS GERAIS", "PA": "PARA", "PB": "PARAIBA",
    "PR": "PARANA", "PE": "PERNAMBUCO", "PI": "PIAUI",
    "RJ": "RIO DE JANEIRO", "RN": "RIO GRANDE DO NORTE",
    "RS": "RIO GRANDE DO SUL", "RO": "RONDONIA", "RR": "RORAIMA",
    "SC": "SANTA CATARINA", "SP": "SAO PAULO", "SE": "SERGIPE",
    "TO": "TOCANTINS",
}
UF_REGION = {
    **{x: "NORTE E NORDESTE" for x in [
        "ACRE", "ALAGOAS", "AMAPA", "AMAZONAS", "BAHIA", "CEARA",
        "MARANHAO", "PARA", "PARAIBA", "PERNAMBUCO", "PIAUI",
        "RIO GRANDE DO NORTE", "RONDONIA", "RORAIMA", "SERGIPE",
        "TOCANTINS",
    ]},
    **{x: "SUDESTE" for x in [
        "ESPIRITO SANTO", "MINAS GERAIS", "RIO DE JANEIRO", "SAO PAULO",
    ]},
    **{x: "SUL E CENTRO OESTE" for x in [
        "DISTRITO FEDERAL", "GOIAS", "MATO GROSSO",
        "MATO GROSSO DO SUL", "PARANA", "RIO GRANDE DO SUL",
        "SANTA CATARINA",
    ]},
}


def norm(value: object) -> str:
    return (
        unicodedata.normalize("NFD", str(value or ""))
        .encode("ascii", "ignore")
        .decode()
        .upper()
        .strip()
    )


def find_column(frame: pd.DataFrame, *names: str) -> str:
    normalized = {norm(column): column for column in frame.columns}
    for name in names:
        if norm(name) in normalized:
            return normalized[norm(name)]
    raise ValueError(f"Coluna ausente: {' / '.join(names)}")


def money(value: object) -> float:
    return round(float(value or 0), 2)


def contract_name(value: object) -> str:
    return CONTRACTS.get(norm(value)[:2], "OUTROS")


def region_name(value: object) -> str | None:
    text = " ".join(norm(value).split())
    if "SUDESTE" in text:
        return "SUDESTE"
    if "NORTE" in text:
        return "NORTE E NORDESTE"
    if "SUL" in text or "CENTRO" in text:
        return "SUL E CENTRO OESTE"
    return None


def is_wallet_status(value: object) -> bool:
    status = norm(value)
    return status.startswith("ABERTO") or status == "ATENDIDO PARCIAL"


def business_days(start: pd.Timestamp, end: pd.Timestamp, holidays: set[str]) -> int:
    if end < start:
        return 0
    days = pd.date_range(start, end, freq="D")
    return sum(
        1 for day in days
        if day.weekday() < 5 and day.strftime("%Y-%m-%d") not in holidays
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera os dados do dashboard comercial.")
    parser.add_argument("--pd010", type=Path, required=True)
    parser.add_argument("--pd019", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--holidays", type=Path)
    parser.add_argument("--as-of", help="Data de execução YYYY-MM-DD.")
    parser.add_argument(
        "--allow-monthly",
        action="store_true",
        help="Somente para testes locais; não usar na automação.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for source in (args.pd010, args.pd019, args.index):
        if not source.is_file() or source.stat().st_size == 0:
            raise SystemExit(f"ERRO: fonte ausente ou vazia: {source}")

    today = pd.Timestamp(args.as_of).normalize() if args.as_of else pd.Timestamp.now().normalize()
    cutoff = (today - pd.offsets.BDay(1)).normalize()
    year = int(cutoff.year)
    current_month = int(cutoff.month)

    holidays: set[str] = set()
    if args.holidays and args.holidays.is_file():
        holidays = set(json.loads(args.holidays.read_text(encoding="utf-8")))

    pd10 = pd.read_excel(args.pd010, sheet_name=0, header=1)
    pd19 = pd.read_excel(args.pd019, sheet_name=0, header=1)
    index_df = pd.read_excel(args.index, sheet_name=0)

    date_col = find_column(pd10, "Dt Implant")
    status_col = find_column(pd10, "Situação Item")
    rob_col = find_column(pd10, "ROB")
    type_col = find_column(pd10, "Tipo Pedido")
    rep_col = find_column(pd10, "Repres")
    rep_name_col = find_column(pd10, "Nome Repres")
    uf_col = find_column(pd10, "UF")

    pd10["Data"] = pd.to_datetime(pd10[date_col], errors="coerce").dt.normalize()
    source_year = pd10[pd10["Data"].dt.year == year].copy()
    source_months = sorted(int(x) for x in source_year["Data"].dt.month.dropna().unique())
    required_months = list(range(1, current_month + 1))
    missing_months = [month for month in required_months if month not in source_months]
    if missing_months and not args.allow_monthly:
        raise SystemExit(
            "BLOQUEADO: PD010 não é anual ou está incompleto. "
            f"Meses encontrados={source_months}; obrigatórios={required_months}."
        )

    pd10 = source_year[
        (source_year["Data"] <= cutoff)
        & ~source_year[status_col].astype(str).map(norm).str.contains("CANCELAD", na=False)
    ].copy()
    if pd10.empty:
        raise SystemExit("ERRO: PD010 ficou vazio após data e situação.")

    pd10["Mes"] = pd10["Data"].dt.month
    pd10["Contrato"] = pd10[type_col].map(contract_name)
    pd10["RepId"] = pd.to_numeric(pd10[rep_col], errors="coerce").fillna(0)
    pd10["RepNome"] = pd10[rep_name_col].fillna(pd10[rep_col]).astype(str)
    pd10["UFNome"] = pd10[uf_col].map(
        lambda x: UF_CODE_TO_NAME.get(norm(x), norm(x))
    )
    pd10["ROBValor"] = pd.to_numeric(pd10[rob_col], errors="coerce").fillna(0)
    pd10["CarteiraValor"] = pd10.apply(
        lambda row: row["ROBValor"] if is_wallet_status(row[status_col]) else 0,
        axis=1,
    )

    index_code_col = find_column(index_df, "codigo", "código")
    index_name_col = find_column(index_df, "nome")
    index_region_col = find_column(index_df, "região", "regiao")
    index_region = {
        int(row[index_code_col]): region_name(row[index_region_col])
        for _, row in index_df.dropna(subset=[index_code_col]).iterrows()
    }
    index_names = {
        int(row[index_code_col]): str(row[index_name_col])
        for _, row in index_df.dropna(subset=[index_code_col]).iterrows()
    }

    fallback_region = (
        pd10.groupby(["RepId", "UFNome"])["ROBValor"]
        .sum().reset_index()
        .sort_values(["RepId", "ROBValor"], ascending=[True, False])
        .drop_duplicates("RepId")
        .set_index("RepId")["UFNome"]
        .map(lambda uf: UF_REGION.get(uf, "NORTE E NORDESTE"))
        .to_dict()
    )
    pd10["Regiao"] = pd10.apply(
        lambda row: index_region.get(
            int(row["RepId"]),
            fallback_region.get(
                row["RepId"],
                UF_REGION.get(row["UFNome"], "NORTE E NORDESTE"),
            ),
        ),
        axis=1,
    )

    meta_rep_col = pd19.columns[1]
    meta_name_col = pd19.columns[2]
    meta_contract_col = pd19.columns[7]
    pd19["RepId"] = pd.to_numeric(pd19[meta_rep_col], errors="coerce").fillna(0)
    pd19["RepNome"] = pd19[meta_name_col].fillna(pd19[meta_rep_col]).astype(str)
    pd19["Contrato"] = pd19[meta_contract_col].map(contract_name)
    pd19["Regiao"] = pd19["RepId"].map(
        lambda value: index_region.get(
            int(value),
            fallback_region.get(value, "NORTE E NORDESTE"),
        )
    )
    month_columns = {norm(column): column for column in pd19.columns}
    missing_meta_columns = [
        name for name in MONTH_NAMES if norm(name) not in month_columns
    ]
    if missing_meta_columns:
        raise SystemExit(f"ERRO: meses ausentes no PD019: {missing_meta_columns}")

    meta_long = pd19.melt(
        id_vars=["RepId", "RepNome", "Regiao", "Contrato"],
        value_vars=[month_columns[norm(name)] for name in MONTH_NAMES],
        var_name="MesNome",
        value_name="Meta",
    )
    month_number = {
        norm(month_columns[norm(name)]): index + 1
        for index, name in enumerate(MONTH_NAMES)
    }
    meta_long["Mes"] = meta_long["MesNome"].map(
        lambda value: month_number[norm(value)]
    )
    meta_long["Meta"] = pd.to_numeric(meta_long["Meta"], errors="coerce").fillna(0)

    keys = ["Mes", "Regiao", "RepId", "Contrato"]
    actual = (
        pd10[pd10["Contrato"].isin(CONTRACT_ORDER)]
        .groupby(keys, dropna=False)
        .agg(Realizado=("ROBValor", "sum"), Carteira=("CarteiraValor", "sum"))
        .reset_index()
    )
    meta = (
        meta_long[meta_long["Contrato"].isin(CONTRACT_ORDER)]
        .groupby(keys, dropna=False)["Meta"]
        .sum().reset_index()
    )
    model = meta.merge(actual, how="outer", on=keys)
    model[["Meta", "Realizado", "Carteira"]] = model[
        ["Meta", "Realizado", "Carteira"]
    ].fillna(0)
    model["RepNome"] = model["RepId"].map(
        lambda value: index_names.get(
            int(value),
            pd10.loc[pd10["RepId"] == value, "RepNome"].iloc[0]
            if (pd10["RepId"] == value).any()
            else str(int(value)),
        )
    )

    def records_for(scope: pd.DataFrame) -> list[dict[str, object]]:
        grouped = (
            scope.groupby(
                ["Regiao", "RepId", "RepNome", "Contrato"],
                dropna=False,
            )
            .agg(
                meta=("Meta", "sum"),
                realizado=("Realizado", "sum"),
                carteira=("Carteira", "sum"),
            )
            .reset_index()
        )
        return [
            {
                "regiao": row.Regiao,
                "repId": int(row.RepId),
                "representante": row.RepNome,
                "contrato": row.Contrato,
                "meta": money(row.meta),
                "realizado": money(row.realizado),
                "carteira": money(row.carteira),
            }
            for row in grouped.itertuples()
        ]

    periods: list[dict[str, object]] = []
    period_defs = [
        ("YTD", f"Ano até {MONTH_NAMES[current_month - 1].lower()}", required_months),
        ("Q1", "1º trimestre", [1, 2, 3]),
        ("Q2", "2º trimestre", [4, 5, 6]),
        ("Q3", "3º trimestre", [7, 8, 9]),
        ("Q4", "4º trimestre", [10, 11, 12]),
    ] + [
        (f"M{month:02}", MONTH_NAMES[month - 1], [month])
        for month in range(1, 13)
    ]
    for key, label, months in period_defs:
        scope = model[model["Mes"].isin(months)]
        periods.append({
            "id": key,
            "label": label,
            "meses": months,
            "registros": records_for(scope),
        })

    monthly = []
    for month in range(1, 13):
        scope = model[model["Mes"] == month]
        monthly.append({
            "mes": month,
            "nome": MONTH_NAMES[month - 1][:3],
            "meta": money(scope["Meta"].sum()),
            "realizado": money(scope["Realizado"].sum()),
            "carteira": money(scope["Carteira"].sum()),
        })

    month_start = pd.Timestamp(year, current_month, 1)
    month_end = month_start + pd.offsets.MonthEnd(0)
    elapsed_business_days = business_days(month_start, cutoff, holidays)
    total_business_days = business_days(month_start, month_end, holidays)
    target_ratio = (
        elapsed_business_days / total_business_days
        if total_business_days else 0
    )
    current_meta = monthly[current_month - 1]["meta"]
    current_period = next(item for item in periods if item["id"] == f"M{current_month:02}")
    for record in current_period["registros"]:
        record["metaAteCorte"] = money(record["meta"] * target_ratio)

    daily_dates = pd.date_range(month_start, cutoff, freq="D")
    daily_source = (
        pd10[pd10["Mes"] == current_month]
        .groupby("Data")
        .agg(realizado=("ROBValor", "sum"), carteira=("CarteiraValor", "sum"))
    )
    real_acc = 0.0
    wallet_acc = 0.0
    daily_wallet = []
    for date in daily_dates:
        if date in daily_source.index:
            real_acc += float(daily_source.loc[date, "realizado"])
            wallet_acc += float(daily_source.loc[date, "carteira"])
        daily_wallet.append({
            "data": date.strftime("%Y-%m-%d"),
            "realizado": money(real_acc),
            "carteira": money(wallet_acc),
        })

    daily_detail = (
        pd10[
            (pd10["Mes"] == current_month)
            & pd10["Contrato"].isin(CONTRACT_ORDER)
        ]
        .groupby(
            ["Data", "Regiao", "RepId", "Contrato"],
            dropna=False,
        )
        .agg(
            realizado=("ROBValor", "sum"),
            carteira=("CarteiraValor", "sum"),
        )
        .reset_index()
    )
    daily_records = [
        {
            "data": row.Data.strftime("%Y-%m-%d"),
            "regiao": row.Regiao,
            "repId": int(row.RepId),
            "representante": index_names.get(int(row.RepId), str(int(row.RepId))),
            "contrato": row.Contrato,
            "realizado": money(row.realizado),
            "carteira": money(row.carteira),
        }
        for row in daily_detail.itertuples()
    ]

    total_general = money(pd10["ROBValor"].sum())
    total_wallet = money(pd10["CarteiraValor"].sum())
    model_total = money(model["Realizado"].sum())
    model_wallet = money(model["Carteira"].sum())
    checks = {
        "pd010Anual": not missing_months,
        "totalGeralConciliado": abs(total_general - model_total) < 0.02,
        "carteiraConciliada": abs(total_wallet - model_wallet) < 0.02,
        "carteiraDentroTotal": total_wallet <= total_general + 0.01,
        "metasPresentes": float(model["Meta"].sum()) > 0,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise SystemExit(f"ERRO: validações falharam: {failed_checks}")

    status_totals = (
        pd10.assign(Status=pd10[status_col].map(norm))
        .groupby("Status")["ROBValor"]
        .sum()
        .round(2)
        .to_dict()
    )
    outside_index = sorted(
        int(value)
        for value in pd10["RepId"].dropna().unique()
        if int(value) != 0 and int(value) not in index_region
    )
    payload = {
        "titulo": "Painel Comercial Integrado",
        "ano": year,
        "geradoEm": today.strftime("%d/%m/%Y %H:%M"),
        "cortes": {
            "realizado": cutoff.strftime("%d/%m/%Y"),
            "carteira": cutoff.strftime("%d/%m/%Y"),
            "metas": f"ano de {year}",
        },
        "metaDiaria": {
            "mes": current_month,
            "metaMensal": money(current_meta),
            "metaAteCorte": money(current_meta * target_ratio),
            "diasUteisTranscorridos": elapsed_business_days,
            "diasUteisMes": total_business_days,
            "feriadosConfigurados": sorted(holidays),
        },
        "ordemRegioes": REGION_ORDER,
        "ordemContratos": CONTRACT_ORDER,
        "mensal": monthly,
        "periodos": periods,
        "carteiraDiaria": daily_wallet,
        "carteiraDiariaRegistros": daily_records,
        "qualidade": {
            "checks": checks,
            "mesesPD010": source_months,
            "linhasPD010": int(len(pd10)),
            "linhasPD019": int(len(pd19)),
            "totalGeral": total_general,
            "carteira": total_wallet,
            "semCarteira": money(total_general - total_wallet),
            "totaisPorSituacao": {
                key: money(value) for key, value in status_totals.items()
            },
            "representantesForaINDEX": outside_index,
        },
        "fontes": [
            "ETLdados/WWWPD010.xlsx — total geral e carteira",
            "ETLdados/WWWPD019.xlsx — metas comerciais",
            "ETLdados/INDEX.xlsx — regiões e representantes",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = args.output.with_suffix(args.output.suffix + ".tmp")
    temp_output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temp_output.replace(args.output)
    print(json.dumps({
        "status": "OK",
        "output": str(args.output),
        "ano": year,
        "corte": cutoff.strftime("%Y-%m-%d"),
        "totalGeral": total_general,
        "carteira": total_wallet,
        "metaMensal": money(current_meta),
        "metaAteCorte": money(current_meta * target_ratio),
        "checks": checks,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
