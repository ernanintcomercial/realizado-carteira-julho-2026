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
EFT_GROUP_CONTRACT = {
    1: "ALUMÍNIO", 5: "ALUMÍNIO", 8: "ALUMÍNIO", 51: "ALUMÍNIO", 74: "ALUMÍNIO",
    12: "PLÁSTICO", 13: "PLÁSTICO", 16: "PLÁSTICO", 18: "PLÁSTICO",
    19: "PLÁSTICO", 21: "PLÁSTICO", 23: "PLÁSTICO", 26: "PLÁSTICO",
    28: "PLÁSTICO", 29: "PLÁSTICO",
    4: "LED", 6: "LED", 7: "LED", 9: "LED", 24: "LED",
    2: "EX", 3: "EX",
}
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
    "TO": "TOCANTINS", "TOCANTIS": "TOCANTINS",
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
    text = norm(value)
    if text.startswith("ALUM"):
        return "ALUMÍNIO"
    if text.startswith("PLAST"):
        return "PLÁSTICO"
    if text.startswith("LED"):
        return "LED"
    if text.startswith("EX"):
        return "EX"
    return CONTRACTS.get(text[:2], "OUTROS")


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
    parser.add_argument("--eft018", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument(
        "--history",
        type=Path,
        help="JSON congelado dos meses encerrados, gerado pelo mesmo ETL.",
    )
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
    sources = [args.pd010, args.pd019, args.eft018, args.index]
    if args.history:
        sources.append(args.history)
    for source in sources:
        if not source.is_file() or source.stat().st_size == 0:
            raise SystemExit(f"ERRO: fonte ausente ou vazia: {source}")

    holidays: set[str] = set()
    if args.holidays and args.holidays.is_file():
        holidays = set(json.loads(args.holidays.read_text(encoding="utf-8")))

    today = pd.Timestamp(args.as_of).normalize() if args.as_of else pd.Timestamp.now().normalize()
    cutoff = (today - pd.Timedelta(days=1)).normalize()
    year = int(cutoff.year)
    current_month = int(cutoff.month)

    previous_payload: dict[str, object] = {}
    if args.output.is_file() and args.output.stat().st_size:
        candidate = json.loads(args.output.read_text(encoding="utf-8"))
        if int(candidate.get("ano", 0)) == year:
            previous_payload = candidate

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
    client_id_col = find_column(pd10, "Cliente")
    client_name_col = find_column(pd10, "Nome Cliente")

    pd10["Data"] = pd.to_datetime(pd10[date_col], errors="coerce").dt.normalize()
    source_year = pd10[pd10["Data"].dt.year == year].copy()
    source_months = sorted(int(x) for x in source_year["Data"].dt.month.dropna().unique())
    history_payload: dict[str, object] = {}
    history_months: list[int] = []
    history_records: list[dict[str, object]] = []
    if args.history:
        history_payload = json.loads(args.history.read_text(encoding="utf-8"))
        if int(history_payload.get("ano", 0)) != year:
            raise SystemExit(
                f"ERRO: base histórica pertence ao ano {history_payload.get('ano')}, "
                f"mas o corte pertence a {year}."
            )
        if current_month > 1:
            expected_history_cutoff = (
                pd.Timestamp(year, current_month, 1) - pd.Timedelta(days=1)
            ).normalize()
            history_cutoff = pd.to_datetime(
                history_payload.get("cortes", {}).get("realizado"),
                format="%d/%m/%Y",
                errors="coerce",
            )
            if pd.isna(history_cutoff) or history_cutoff.normalize() < expected_history_cutoff:
                received = "ausente" if pd.isna(history_cutoff) else history_cutoff.strftime("%d/%m/%Y")
                raise SystemExit(
                    "BLOQUEADO: histórico não está consolidado até o último dia do mês fechado. "
                    f"Esperado={expected_history_cutoff.strftime('%d/%m/%Y')}; recebido={received}."
                )
        for month in range(1, current_month):
            period_id = f"M{month:02}"
            period = next(
                (item for item in history_payload.get("periodos", []) if item["id"] == period_id),
                None,
            )
            if not period:
                continue
            history_months.append(month)
            for record in period["registros"]:
                history_records.append({"Mes": month, **record})

    required_months = list(range(1, current_month + 1))
    coverage_months = sorted(set(source_months) | set(history_months))
    missing_months = [month for month in required_months if month not in coverage_months]
    if missing_months and not args.allow_monthly:
        raise SystemExit(
            "BLOQUEADO: histórico + PD010 mensal estão incompletos. "
            f"Meses cobertos={coverage_months}; obrigatórios={required_months}."
        )

    if args.history:
        source_year = source_year[source_year["Data"].dt.month == current_month].copy()
        if current_month not in source_months:
            raise SystemExit(
                f"BLOQUEADO: PD010 mensal não contém o mês do corte ({current_month}). "
                f"Meses encontrados={source_months}."
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
    pd10["ClienteId"] = pd.to_numeric(pd10[client_id_col], errors="coerce").fillna(0).astype(int)
    pd10["ClienteNome"] = pd10[client_name_col].fillna(pd10[client_id_col]).astype(str)
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
    def sales_region(row):
        rep_id = int(row["RepId"])
        if rep_id in index_region:
            return index_region[rep_id]

        # Representantes sem cadastro no INDEX podem vender em mais de uma
        # região. Nesses casos, cada linha deve seguir a UF do cliente.
        uf_region = UF_REGION.get(row["UFNome"])
        if uf_region:
            return uf_region

        # Contingência apenas para linhas cuja UF esteja ausente ou inválida.
        return fallback_region.get(rep_id, "NORTE E NORDESTE")

    pd10["Regiao"] = pd10.apply(sales_region, axis=1)

    # As metas publicadas permanecem congeladas até a gerência validar uma
    # alteração. O PD019 continua sendo recebido e validado, mas não deve
    # reescrever retroativamente as metas já aprovadas.
    previous_meta_rows: list[dict[str, object]] = []
    for month in range(1, 13):
        period_id = f"M{month:02}"
        period = next(
            (item for item in previous_payload.get("periodos", []) if item["id"] == period_id),
            None,
        )
        if not period:
            continue
        for record in period.get("registros", []):
            previous_meta_rows.append({
                "Mes": month,
                "Regiao": record["regiao"],
                "RepId": int(record["repId"]),
                "RepNome": str(record["representante"]),
                "Contrato": record["contrato"],
                "Meta": float(record.get("meta", 0)),
            })

    if previous_meta_rows:
        meta_long = pd.DataFrame(previous_meta_rows)
        meta_mode = "preservadas da publicação anterior"
    else:
        meta_year_col = find_column(pd19, "Ano")
        meta_rep_col = find_column(pd19, "Cod", "Código", "Repres")
        meta_name_col = find_column(pd19, "Representante", "Nome Repres")
        meta_contract_col = find_column(pd19, "Contrato")
        pd19 = pd19[pd.to_numeric(pd19[meta_year_col], errors="coerce") == year].copy()
        pd19["RepId"] = pd.to_numeric(pd19[meta_rep_col], errors="coerce").fillna(0)
        pd19["RepNome"] = pd19[meta_name_col].fillna(pd19[meta_rep_col]).astype(str)
        pd19["Contrato"] = pd19[meta_contract_col].map(contract_name)
        pd19["Regiao"] = pd19["RepId"].map(
            lambda value: index_region.get(
                int(value),
                fallback_region.get(value, "NORTE E NORDESTE"),
            )
        )
        contract_position = list(pd19.columns).index(meta_contract_col)
        month_columns = list(pd19.columns)[contract_position + 2:contract_position + 14]
        if len(month_columns) != 12:
            raise SystemExit("ERRO: não foi possível identificar os 12 meses no PD019.")
        meta_long = pd19.melt(
            id_vars=["RepId", "RepNome", "Regiao", "Contrato"],
            value_vars=month_columns,
            var_name="MesNome",
            value_name="Meta",
        )
        month_number = {column: index + 1 for index, column in enumerate(month_columns)}
        meta_long["Mes"] = meta_long["MesNome"].map(month_number)
        meta_long["Meta"] = pd.to_numeric(meta_long["Meta"], errors="coerce").fillna(0)
        meta_mode = "ETLdados/WWWPD019.xlsx"

    keys = ["Mes", "Regiao", "RepId", "Contrato"]
    actual_current = (
        pd10[pd10["Contrato"].isin(CONTRACT_ORDER)]
        .groupby(keys, dropna=False)
        .agg(Realizado=("ROBValor", "sum"), Carteira=("CarteiraValor", "sum"))
        .reset_index()
    )
    history_names: dict[int, str] = {}
    if history_records:
        history_actual = pd.DataFrame([
            {
                "Mes": int(record["Mes"]),
                "Regiao": record["regiao"],
                "RepId": int(record["repId"]),
                "Contrato": record["contrato"],
                "Realizado": float(record.get("realizado", 0)),
                "Carteira": float(record.get("carteira", 0)),
            }
            for record in history_records
            if record["contrato"] in CONTRACT_ORDER
        ])
        history_names = {
            int(record["repId"]): str(record["representante"])
            for record in history_records
        }
        actual = pd.concat([history_actual, actual_current], ignore_index=True)
        actual = (
            actual.groupby(keys, dropna=False)[["Realizado", "Carteira"]]
            .sum().reset_index()
        )
    else:
        actual = actual_current
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
            history_names.get(
                int(value),
                pd10.loc[pd10["RepId"] == value, "RepNome"].iloc[0]
                if (pd10["RepId"] == value).any()
                else str(int(value)),
            ),
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

    def client_records_for(months: list[int]) -> list[dict[str, object]]:
        scope = pd10[pd10["Mes"].isin(months) & pd10["Contrato"].isin(CONTRACT_ORDER)]
        grouped = scope.groupby(["Regiao", "ClienteId", "ClienteNome"], dropna=False).agg(
            realizado=("ROBValor", "sum"), carteira=("CarteiraValor", "sum"),
        ).reset_index()
        return [{
            "regiao": row.Regiao, "clienteId": int(row.ClienteId),
            "cliente": row.ClienteNome, "realizado": money(row.realizado),
            "carteira": money(row.carteira),
        } for row in grouped.itertuples() if row.ClienteId]

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
            "clientes": client_records_for(months),
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

    # O Totvs pode gravar caracteres fora do cp1252 em descrições de produto.
    # Latin-1 preserva as colunas e evita bloquear a atualização por esse ruído.
    eft = pd.read_csv(args.eft018, sep="|", encoding="latin1", dtype=str)
    eft.columns = [str(column).strip() for column in eft.columns]
    eft_date_col = find_column(eft, "Data Emissão")
    eft_uf_col = find_column(eft, "U.F.", "UF")
    eft_rep_col = find_column(eft, "Representante")
    eft_group_col = find_column(eft, "Grp Estoque")
    eft_rob_col = find_column(eft, "ROB")
    eft["Data"] = pd.to_datetime(
        eft[eft_date_col], format="%d/%m/%y", errors="coerce",
    ).dt.normalize()
    eft["RepId"] = pd.to_numeric(eft[eft_rep_col], errors="coerce").fillna(0).astype(int)
    eft["Grupo"] = pd.to_numeric(eft[eft_group_col], errors="coerce").fillna(0).astype(int)
    eft["Contrato"] = eft["Grupo"].map(EFT_GROUP_CONTRACT).fillna("OUTROS")
    eft["Regiao"] = eft[eft_uf_col].map(
        lambda value: UF_REGION.get(
            UF_CODE_TO_NAME.get(norm(value), norm(value)),
            "NORTE E NORDESTE",
        )
    )
    eft["Faturado"] = pd.to_numeric(
        eft[eft_rob_col].astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0)
    eft = eft[(eft["Data"].dt.year == year) & (eft["Data"] <= cutoff)].copy()
    if eft.empty:
        raise SystemExit("ERRO: WWEFT018 ficou vazio após aplicar ano e corte.")
    eft["Mes"] = eft["Data"].dt.month.astype(int)
    eft_months = sorted(int(value) for value in eft["Mes"].unique())
    if current_month not in eft_months:
        raise SystemExit(
            f"BLOQUEADO: WWEFT018 não contém o mês do corte ({current_month}). "
            f"Meses encontrados={eft_months}."
        )

    current_billing = (
        eft.groupby(["Mes", "Regiao", "RepId", "Contrato"], dropna=False)["Faturado"]
        .sum().reset_index()
    )
    previous_billing = [
        record for record in previous_payload.get("faturamentoRegistros", [])
        if int(record.get("mes", 0)) not in eft_months
    ]
    if not previous_billing and eft_months != required_months:
        raise SystemExit(
            "BLOQUEADO: WWEFT018 mensal sem histórico de faturamento preservado. "
            f"Meses no arquivo={eft_months}; necessários={required_months}."
        )
    billing_records = previous_billing + [
        {
            "mes": int(row.Mes),
            "regiao": row.Regiao,
            "repId": int(row.RepId),
            "contrato": row.Contrato,
            "faturado": money(row.Faturado),
        }
        for row in current_billing.itertuples()
    ]
    eft_gross = money(eft["Faturado"].sum())
    eft_commercial = money(
        eft.loc[eft["Contrato"].isin(CONTRACT_ORDER), "Faturado"].sum()
    )
    eft_other_groups = sorted(
        int(value) for value in eft.loc[eft["Contrato"] == "OUTROS", "Grupo"].unique()
        if int(value) != 0
    )

    history_quality = history_payload.get("qualidade", {}) if history_payload else {}
    history_total = float(history_quality.get("totalGeral", 0))
    history_wallet = float(history_quality.get("carteira", 0))
    total_general = money(history_total + pd10["ROBValor"].sum())
    total_wallet = money(history_wallet + pd10["CarteiraValor"].sum())
    model_total = money(model["Realizado"].sum())
    model_wallet = money(model["Carteira"].sum())
    checks = {
        "coberturaCompleta": not missing_months,
        "totalGeralConciliado": abs(total_general - model_total) < 0.02,
        "carteiraConciliada": abs(total_wallet - model_wallet) < 0.02,
        "carteiraDentroTotal": total_wallet <= total_general + 0.01,
        "metasPresentes": float(model["Meta"].sum()) > 0,
        "faturamentoPresente": eft_gross > 0,
        "faturamentoDentroBruto": eft_commercial <= eft_gross + 0.01,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise SystemExit(f"ERRO: validações falharam: {failed_checks}")

    current_status_totals = (
        pd10.assign(Status=pd10[status_col].map(norm))
        .groupby("Status")["ROBValor"]
        .sum()
        .round(2)
        .to_dict()
    )
    status_totals = {
        str(key): float(value)
        for key, value in history_quality.get("totaisPorSituacao", {}).items()
    }
    for key, value in current_status_totals.items():
        status_totals[key] = status_totals.get(key, 0) + float(value)
    source_rep_ids = {int(value) for value in pd10["RepId"].dropna().unique()}
    source_rep_ids.update(int(value) for value in history_quality.get("representantesForaINDEX", []))
    outside_index = sorted(
        value for value in source_rep_ids
        if value != 0 and value not in index_region
    )
    payload = {
        "titulo": "Painel Comercial Integrado",
        "ano": year,
        "geradoEm": today.strftime("%d/%m/%Y %H:%M"),
        "cortes": {
            "realizado": cutoff.strftime("%d/%m/%Y"),
            "carteira": cutoff.strftime("%d/%m/%Y"),
            "faturamento": cutoff.strftime("%d/%m/%Y"),
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
        "faturamentoRegistros": billing_records,
        "qualidade": {
            "checks": checks,
            "mesesPD010": coverage_months,
            "mesesHistorico": history_months,
            "mesesFonteMensal": source_months,
            "linhasPD010": int(len(pd10)),
            "linhasHistoricoOrigem": int(history_quality.get("linhasPD010", 0)),
            "linhasPD019": int(len(pd19)),
            "linhasEFT018": int(len(eft)),
            "mesesEFT018": eft_months,
            "faturamentoBrutoEFT018": eft_gross,
            "faturamentoComercialEFT018": eft_commercial,
            "gruposFaturamentoOutros": eft_other_groups,
            "totalGeral": total_general,
            "carteira": total_wallet,
            "semCarteira": money(total_general - total_wallet),
            "totaisPorSituacao": {
                key: money(value) for key, value in status_totals.items()
            },
            "representantesForaINDEX": outside_index,
        },
        "fontes": [
            "dados-historicos.json — meses encerrados",
            "ETLdados/WWWPD010.xlsx — mês atual, total geral e carteira",
            "ETLdados/WWWPD019.xlsx — metas comerciais",
            f"Metas comerciais {meta_mode}",
            "ETLdados/WWEFT018.LST — faturamento bruto; grupos não comerciais mantidos no KPI e ocultos no desempenho por contrato",
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
        "faturamentoBruto": eft_gross,
        "faturamentoComercial": eft_commercial,
        "checks": checks,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
