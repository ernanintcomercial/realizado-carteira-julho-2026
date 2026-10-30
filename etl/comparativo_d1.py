"""Preserva uma única referência anterior por corte, sem encadear históricos."""
from copy import deepcopy
from datetime import datetime


def date(value):
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def snapshot(payload):
    return deepcopy({
        "ano": payload.get("ano"),
        "cortes": payload.get("cortes", {}),
        "ordemRegioes": payload.get("ordemRegioes", []),
        "periodos": [{"id": p["id"], "meses": p.get("meses", []),
                      "registros": p.get("registros", [])}
                     for p in payload.get("periodos", [])],
        "faturamentoRegistros": payload.get("faturamentoRegistros", []),
    })


def attach_previous(current, previous):
    """Referência por métrica: corte igual preserva D-1; regressão é recusada.

    A referência é o último corte publicado anterior, não a última execução.
    Finais de semana/feriados sem novo corte não promovem a referência.
    """
    result = snapshot({})
    for metric in ("realizado", "faturamento"):
        now = date(current.get("cortes", {}).get(metric))
        before = date(previous.get("cortes", {}).get(metric))
        if now and before and now < before:
            raise ValueError(f"Corte de {metric} regrediu: {before} -> {now}")
        source = previous if now and before and before < now else previous.get("comparativoD1", {})
        reference = date(source.get("cortes", {}).get(metric))
        if not now or not reference or reference >= now:
            continue
        result["cortes"][metric] = source["cortes"][metric]
        result["ano"] = source.get("ano")
        result["ordemRegioes"] = list(source.get("ordemRegioes", []))
        if metric == "realizado":
            result["periodos"] = snapshot(source)["periodos"]
        else:
            result["faturamentoRegistros"] = deepcopy(source.get("faturamentoRegistros", []))
    current["comparativoD1"] = result
    return current
