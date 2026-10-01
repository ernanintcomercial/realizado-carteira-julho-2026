import csv
import tempfile
import unittest
from pathlib import Path
from consolidar_eft018 import consolidate


class ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.output = self.directory / 'merged.LST'
        self.addCleanup(self.temp.cleanup)

    def write(self, name, rows, header=None):
        with (self.directory / name).open('w', encoding='latin1', newline='') as stream:
            writer = csv.writer(stream, delimiter='|')
            writer.writerow(header or ['Data Emissão', 'ROB', 'Descrição'])
            writer.writerows(rows)

    def test_merge_boundaries_and_preserve_rows(self):
        self.write('WWEFT018inicio.LST', [['01/01/26', '10,25', 'Peça'], ['31/05/26', '20,50', 'a|b']])
        self.write('WWEFT018fim.LST', [['01/06/26', '30,75', 'fim'], ['30/09/26', '40,00', 'fim']])
        self.write('WWEFT018.LST', [['30/09/26', '999,00', 'legado ignorado']])
        path, recent = consolidate(self.directory, self.output, 2026)
        with path.open(encoding='latin1', newline='') as stream:
            rows = list(csv.reader(stream, delimiter='|'))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[2][2], 'a|b')
        self.assertEqual(recent, 'WWEFT018fim.LST')
        self.assertEqual(sum(float(r[1].replace(',', '.')) for r in rows[1:]), 101.50)

    def test_overlap_rejected(self):
        self.write('WWEFT018inicio.LST', [['01/06/26', '10', 'sobreposição']])
        self.write('WWEFT018fim.LST', [['01/06/26', '10', 'fim']])
        with self.assertRaisesRegex(ValueError, 'fora do período'):
            consolidate(self.directory, self.output, 2026)
        self.assertFalse(self.output.exists())

    def test_partial_pair_rejected_even_with_legacy(self):
        self.write('WWEFT018inicio.LST', [['31/05/26', '10', 'inicio']])
        self.write('WWEFT018.LST', [['30/09/26', '20', 'antigo']])
        with self.assertRaisesRegex(ValueError, 'incompleto'):
            consolidate(self.directory, self.output, 2026)

    def test_legacy_transition(self):
        self.write('WWEFT018.LST', [['30/09/26', '20', 'antigo']])
        path, recent = consolidate(self.directory, self.output, 2026)
        self.assertEqual(path.name, 'WWEFT018.LST')
        self.assertEqual(recent, path.name)

    def test_header_mismatch_and_invalid_date(self):
        self.write('WWEFT018inicio.LST', [['31/05/26', '10', 'inicio']])
        self.write('WWEFT018fim.LST', [['01/06/26', '20', 'fim']], ['Data Emissão', 'ROL', 'Descrição'])
        with self.assertRaisesRegex(ValueError, 'Cabeçalhos'):
            consolidate(self.directory, self.output, 2026)
        self.write('WWEFT018fim.LST', [['31/06/26', '20', 'fim']])
        with self.assertRaisesRegex(ValueError, 'data inválida'):
            consolidate(self.directory, self.output, 2026)


if __name__ == '__main__':
    unittest.main()
