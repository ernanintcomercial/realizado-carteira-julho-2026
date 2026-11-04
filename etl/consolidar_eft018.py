"""Reúne os EFT018 sem sobreposição; mantém o formato original do TOTVS."""
import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
import unicodedata


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value)
                   if not unicodedata.combining(c)).strip().upper()


def consolidate(directory, output, year, allow_identical_overlap=False):
    beginning = directory / 'WWEFT018inicio.LST'
    ending = directory / 'WWEFT018fim.LST'
    if not beginning.exists() and not ending.exists():
        legacy = directory / 'WWEFT018.LST'
        if not legacy.is_file() or not legacy.stat().st_size:
            raise ValueError('Fonte de faturamento ausente.')
        return legacy, legacy.name
    if not beginning.is_file() or not ending.is_file():
        raise ValueError('Lote incompleto: são necessários WWEFT018inicio.LST e WWEFT018fim.LST.')
    # Compatibilidade com os dois lotes usados: jan-mai/jun-dez ou jan-jun/jul-dez.
    # Junho no primeiro arquivo exige que o segundo comece somente em julho.
    boundary = 5
    with beginning.open(encoding='latin1', newline='') as stream:
        reader = csv.reader(stream, delimiter='|')
        keys = next(reader, [])
        index = next((i for i, key in enumerate(keys) if norm(key) == 'DATA EMISSAO'), None)
        if index is not None:
            for row in reader:
                if len(row) > index and row[index].strip():
                    try:
                        if datetime.strptime(row[index].strip(), '%d/%m/%y').month == 6:
                            boundary = 6
                    except ValueError:
                        pass  # A leitura validada abaixo identifica a linha inválida.
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    header = None
    beginning_overlap = Counter()
    ending_overlap = Counter()
    try:
        with temporary.open('w', encoding='latin1', newline='') as destination:
            writer = csv.writer(destination, delimiter='|')
            for source, start_month, end_month in [(beginning, 1, boundary), (ending, boundary + 1, 12)]:
                count = 0
                with source.open(encoding='latin1', newline='') as stream:
                    reader = csv.reader(stream, delimiter='|')
                    current_header = next(reader, None)
                    if not current_header:
                        raise ValueError(f'{source.name}: arquivo vazio.')
                    # TOTVS termina o cabeçalho com |, mas não as linhas de dados.
                    while current_header and not current_header[-1].strip():
                        current_header.pop()
                    if header is None:
                        header = current_header
                        writer.writerow(header)
                        date_index = next((i for i, key in enumerate(header)
                                           if norm(key) == 'DATA EMISSAO'), None)
                        if date_index is None:
                            raise ValueError('Coluna Data Emissão ausente.')
                    elif [norm(x) for x in current_header] != [norm(x) for x in header]:
                        raise ValueError('Cabeçalhos dos dois EFT018 são diferentes.')
                    for row in reader:
                        if not row or not any(cell.strip() for cell in row):
                            continue
                        while len(row) > len(header) and not row[-1].strip():
                            row.pop()
                        if len(row) != len(header):
                            raise ValueError(f'{source.name}, linha {reader.line_num}: colunas inválidas.')
                        try:
                            date = datetime.strptime(row[date_index].strip(), '%d/%m/%y')
                        except ValueError as error:
                            raise ValueError(f'{source.name}, linha {reader.line_num}: data inválida.') from error
                        if (allow_identical_overlap and source == ending
                                and date.year == year and date.month == boundary):
                            ending_overlap[tuple(cell.strip() for cell in row)] += 1
                            continue
                        if date.year != year or not start_month <= date.month <= end_month:
                            raise ValueError(f'{source.name}, linha {reader.line_num}: data {date:%d/%m/%Y} fora do período; possível sobreposição.')
                        if source == beginning and date.month == boundary:
                            beginning_overlap[tuple(cell.strip() for cell in row)] += 1
                        writer.writerow(row)
                        count += 1
                if count == 0:
                    raise ValueError(f'{source.name}: nenhuma linha de faturamento.')
        if ending_overlap and beginning_overlap != ending_overlap:
            raise ValueError('Sobreposição divergente entre os EFT018; revisão necessária.')
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output, ending.name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--allow-identical-overlap', action='store_true')
    args = parser.parse_args()
    source, recent = consolidate(args.directory, args.output, args.year, args.allow_identical_overlap)
    print(f'EFT_INPUT={source.as_posix()}')
    print(f'EFT_RECENT={recent}')


if __name__ == '__main__':
    main()
