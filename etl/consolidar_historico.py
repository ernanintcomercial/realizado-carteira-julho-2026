from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Congela o fechamento do último mês encerrado na base histórica."
    )
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--as-of", required=True, help="Data de execução YYYY-MM-DD.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite refazer uma consolidação histórica durante um reparo manual.",
    )
    return parser.parse_args()


def parse_date(value: object) -> pd.Timestamp | None:
    date = pd.to_datetime(value, format="%d/%m/%Y", errors="coerce")
    return None if pd.isna(date) else date.normalize()


def find_period(payload: dict[str, object], month: int) -> dict[str, object] | None:
    period_id = f"M{month:02}"
    return next(
        (item for item in payload.get("periodos", []) if item.get("id") == period_id),
        None,
    )


def find_month(payload: dict[str, object], month: int) -> dict[str, object] | None:
    return next(
        (item for item in payload.get("mensal", []) if int(item.get("mes", 0)) == month),
        None,
    )


def assert_month_consistent(payload: dict[str, object], month: int) -> None:
    monthly = find_month(payload, month)
    period = find_period(payload, month)
    if not monthly or not period:
        raise SystemExit(
            f"BLOQUEADO: o dashboard anterior não possui o fechamento de M{month:02}."
        )

    records = period.get("registros", [])
    realized = round(sum(float(row.get("realizado", 0)) for row in records), 2)
    wallet = round(sum(float(row.get("carteira", 0)) for row in records), 2)
    if realized != round(float(monthly.get("realizado", 0)), 2):
        raise SystemExit(
            f"BLOQUEADO: realizado de M{month:02} diverge entre resumo e registros."
        )
    if wallet != round(float(monthly.get("carteira", 0)), 2):
        raise SystemExit(
            f"BLOQUEADO: carteira de M{month:02} diverge entre resumo e registros."
        )


def main() -> None:
    args = parse_args()
    as_of = pd.Timestamp(args.as_of).normalize()
    current_cutoff = as_of - pd.Timedelta(days=1)
    if current_cutoff.month == 1:
        print('{"status":"SKIP","reason":"primeiro mês do ano"}')
        return

    closed_end = pd.Timestamp(current_cutoff.year, current_cutoff.month, 1) - pd.Timedelta(days=1)
    closed_month = int(closed_end.month)

    history = json.loads(args.history.read_text(encoding="utf-8"))
    dashboard = json.loads(args.dashboard.read_text(encoding="utf-8"))
    history_cutoff = parse_date(history.get("cortes", {}).get("realizado"))
    dashboard_cutoff = parse_date(dashboard.get("cortes", {}).get("realizado"))

    if history_cutoff and history_cutoff >= closed_end and not args.force:
        print(
            json.dumps(
                {"status": "SKIP", "reason": "histórico já consolidado", "through": history_cutoff.strftime("%Y-%m-%d")}
            )
        )
        return

    if int(dashboard.get("ano", 0)) != current_cutoff.year or not dashboard_cutoff:
        raise SystemExit("BLOQUEADO: dashboard anterior sem corte válido para consolidar o histórico.")
    if dashboard_cutoff < closed_end:
        raise SystemExit(
            "BLOQUEADO: dashboard anterior ainda não alcança o último dia do mês a consolidar "
            f"({closed_end.strftime('%d/%m/%Y')})."
        )

    assert_month_consistent(dashboard, closed_month)

    # O dashboard do último dia útil do mês contém o fechamento já validado.
    # Congelar todos os seus componentes preserva cartões, filtros e metas quando
    # a fonte diária passa a trazer somente o mês seguinte.
    for key in [
        "titulo",
        "ano",
        "geradoEm",
        "cortes",
        "metaDiaria",
        "ordemRegioes",
        "ordemContratos",
        "mensal",
        "periodos",
        "carteiraDiaria",
        "carteiraDiariaRegistros",
        "qualidade",
        "fontes",
    ]:
        if key in dashboard:
            history[key] = dashboard[key]

    args.history.write_text(
        json.dumps(history, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    monthly = find_month(dashboard, closed_month) or {}
    print(
        json.dumps(
            {
                "status": "OK",
                "month": closed_month,
                "through": closed_end.strftime("%Y-%m-%d"),
                "realizado": round(float(monthly.get("realizado", 0)), 2),
                "carteira": round(float(monthly.get("carteira", 0)), 2),
            }
        )
    )


if __name__ == "__main__":
    main()
