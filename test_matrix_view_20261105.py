import copy
from html import unescape
from html.parser import HTMLParser
import unittest

from matrix_view import FIELDS, cards_table


class Cells(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = []
        self.active = False

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self.cells.append('')
            self.active = True

    def handle_endtag(self, tag):
        if tag == 'td':
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.cells[-1] += data


class MatrixViewTests(unittest.TestCase):
    def test_every_field_remains_visible_and_input_is_unchanged(self):
        row = {'Ticker': 'STX.WA', 'Stan': 'Potwierdzony', 'Cena bazowa': 1.25,
               'Czas bazy UTC': '2026-11-04T17:00:00+01:00', 'Ostatnia cena': 1.3,
               'Zmiana od bazy (%)': 4., 'Odczyty pod rząd': 3,
               'Ostatni odczyt UTC': '2026-11-05T18:30:12.123456+00:00',
               'Powiadomienia': 'Dozwolone tylko przy świeżej, otwartej świecy'}
        before = copy.deepcopy(row)
        parsed = Cells()
        parsed.feed(cards_table([row]))
        self.assertEqual(len(parsed.cells), len(FIELDS))
        self.assertEqual(parsed.cells, ['STX.WA', '↑ Wzrost', 'Potwierdzony', '1,25',
                                      '04.11.202616:00:00UTC', '1,3', '+4,00%', '3',
                                      '05.11.202618:30:12.123456UTC', row['Powiadomienia']])
        self.assertEqual(row, before)

    def test_untrusted_text_is_escaped_and_missing_change_is_not_flat(self):
        html = cards_table([{'Ticker': '<script>alert(1)</script>',
                             'Powiadomienia': '<img src=x onerror=alert(1)>',
                             'Zmiana od bazy (%)': None}])
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img ', html)
        self.assertIn('class="ki-matrix-unknown"', html)
        self.assertIn('&lt;script&gt;', html)


if __name__ == '__main__':
    unittest.main()
