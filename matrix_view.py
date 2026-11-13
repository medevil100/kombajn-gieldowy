"""Full-width, wrapping matrix presentation with all saved fields visible."""
from datetime import timezone
from html import escape
import math

from sl_tp import stamp


FIELDS = ('Ticker', 'Ruch od bazy', 'Stan', 'Cena bazowa', 'Czas bazy UTC',
          'Ostatnia cena', 'Zmiana od bazy (%)', 'Odczyty pod rząd',
          'Ostatni odczyt UTC', 'Powiadomienia')
WIDTHS = (8, 8, 9, 8, 12, 8, 10, 8, 12, 17)
COLORS = {'up':('#143b2c','#dcfce7'), 'down':('#4c1d24','#ffe4e6'),
          'flat':('#4a2c16','#fed7aa'), 'unknown':('#18212d','#c6d0dc')}


def movement(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return 'unknown', 'Brak danych'
    if math.isclose(value, 0., rel_tol=0., abs_tol=1e-9):
        return 'flat', '→ Bez zmiany'
    return ('up', '↑ Wzrost') if value > 0 else ('down', '↓ Spadek')


def display(key, value):
    if value is None:
        return 'Brak danych'
    if key.endswith('UTC'):
        moment = stamp(value)
        if moment:
            moment = moment.astimezone(timezone.utc)
            clock = moment.strftime('%H:%M:%S')
            if moment.microsecond:
                clock += '.' + moment.strftime('%f')
            return escape(moment.strftime('%d.%m.%Y')) + '<br>' + escape(clock) + '<br>UTC'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            return 'Brak danych'
        if key == 'Zmiana od bazy (%)':
            precision = 2 if abs(value) >= .005 or value == 0 else 6
            return format(value, '+.' + str(precision) + 'f').replace('.', ',') + '%'
        if key in ('Cena bazowa', 'Ostatnia cena'):
            return escape(format(value, '.8g').replace('.', ','))
    return escape(str(value))


def cards_table(rows):
    headers = ''.join('<th scope="col">' + escape(label) + '</th>' for label in FIELDS)
    columns = ''.join('<col style="width:' + str(width) + '%">' for width in WIDTHS)
    body = []
    for row in rows:
        color, label = movement(row.get('Zmiana od bazy (%)'))
        background, foreground = COLORS[color]
        values = {**row, 'Ruch od bazy': label}
        cells = ''.join('<td style="background-color:'+background+';color:'+foreground+'" data-label="' + escape(key, quote=True) + '" title="'
                        + escape(str(values.get(key) if values.get(key) is not None else 'Brak danych'), quote=True)
                        + '"><span class="ki-matrix-value">' + display(key, values.get(key)) + '</span></td>' for key in FIELDS)
        body.append('<tr class="ki-matrix-' + color + '">' + cells + '</tr>')
    return '''<style>
    .ki-matrix-wrap{width:100%;max-height:70vh;overflow-y:auto;border:1px solid #61758b;border-radius:8px}
    .ki-matrix-full{width:100%;table-layout:fixed;border-collapse:collapse;font-size:clamp(.78rem,.95vw,.95rem)}
    .ki-matrix-full th,.ki-matrix-full td{text-align:left;padding:10px 8px;vertical-align:top;white-space:normal;overflow-wrap:anywhere;border-bottom:1px solid #61758b55}
    .ki-matrix-full th{position:sticky;top:0;z-index:1;background:#182330;color:#edf2f7;font-weight:600}
    .ki-matrix-full tr.ki-matrix-up td{background:#143b2c;color:#dcfce7}
    .ki-matrix-full tr.ki-matrix-down td{background:#4c1d24;color:#ffe4e6}
    .ki-matrix-full tr.ki-matrix-flat td{background:#4a2c16;color:#fed7aa}
    .ki-matrix-full tr.ki-matrix-unknown td{background:#18212d;color:#c6d0dc}
    .ki-matrix-full td:first-child{font-weight:700}
    .ki-matrix-value{min-width:0}
    @media(max-width:900px){
      .ki-matrix-full,.ki-matrix-full tbody{display:block;width:100%;font-size:.9rem}
      .ki-matrix-full colgroup,.ki-matrix-full thead{display:none}
      .ki-matrix-full tr{display:block;width:100%;margin-bottom:12px;border-bottom:2px solid #61758b}
      .ki-matrix-full td{display:grid;grid-template-columns:minmax(0,42%) minmax(0,58%);width:100%;box-sizing:border-box;gap:0;padding:8px 10px}
      .ki-matrix-full td:before{content:attr(data-label);font-weight:600;padding-right:12px}
    }
    </style><div class="ki-matrix-wrap" role="region" aria-label="Wszystkie dane ruchu od stałej bazy" tabindex="0"><table class="ki-matrix-full"><colgroup>''' + columns + '</colgroup><thead><tr>' + headers + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>'
