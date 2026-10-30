import unittest
from comparativo_d1 import attach_previous


def data(day, value=100):
    return {"ano": 2026, "cortes": {"realizado": day, "faturamento": day},
            "ordemRegioes": ["SUDESTE"], "periodos": [{"id": "M10", "registros": [{"realizado": value}]}],
            "faturamentoRegistros": [{"faturado": value}]}


class PreviousTests(unittest.TestCase):
    def test_new_cutoff(self):
        result = attach_previous(data("29/10/2026", 200), data("28/10/2026"))
        self.assertEqual(result["comparativoD1"]["periodos"][0]["registros"][0]["realizado"], 100)
        self.assertNotIn("comparativoD1", result["comparativoD1"])

    def test_same_day_retry(self):
        previous = attach_previous(data("29/10/2026", 200), data("28/10/2026"))
        current = attach_previous(data("29/10/2026", 250), previous)
        self.assertEqual(current["comparativoD1"], previous["comparativoD1"])

    def test_monday_uses_friday(self):
        current = attach_previous(data("02/11/2026"), data("30/10/2026"))
        self.assertEqual(current["comparativoD1"]["cortes"]["realizado"], "30/10/2026")

    def test_stale_and_first_run(self):
        self.assertEqual(attach_previous(data("29/10/2026"), {})["comparativoD1"]["cortes"], {})
        self.assertEqual(attach_previous(data("29/10/2026"), data("29/10/2026"))["comparativoD1"]["cortes"], {})

    def test_regression_rejected(self):
        with self.assertRaises(ValueError):
            attach_previous(data("28/10/2026"), data("29/10/2026"))

    def test_billing_cutoff_independent(self):
        previous = attach_previous(data("29/10/2026"), data("28/10/2026", 80))
        current = data("30/10/2026")
        current["cortes"]["faturamento"] = "29/10/2026"
        result = attach_previous(current, previous)["comparativoD1"]
        self.assertEqual(result["cortes"], {"realizado": "29/10/2026", "faturamento": "28/10/2026"})
        self.assertEqual(result["faturamentoRegistros"][0]["faturado"], 80)


if __name__ == "__main__":
    unittest.main()
