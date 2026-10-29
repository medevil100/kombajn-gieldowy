"""Portfolio cards separating manual alert thresholds from local analysis."""
from html import escape

from tracking_view import time_text, level_values, number_text


def text(value, default='—'):
    if value is None or str(value).strip().casefold() in ('', 'none', 'nan'):
        return default
    return str(value)


def threshold_status(value):
    return {'FIRED':'Wyzwolony', 'armed':'Ustawiony'}.get(value, 'Nie ustawiono')


def cards_html(rows):
    cards=[]
    for row in rows:
        def field(name):return escape(text(row.get(name)))
        change=text(row.get('Zmiana 1H'))
        direction='up' if change.startswith('+') else 'down' if change.startswith('-') else 'neutral'
        fresh=bool(row.get('_fresh'))
        label='Ostatni odczyt świeży' if fresh else 'Dane historyczne lub niepełne'
        levels=''
        for name, color in (('SL','sl'),('TP','tp')):
            levels+=('<div class="ki-pf-level '+color+'"><div>'+name+' · Twój próg</div>'
                     '<strong>'+field(name)+'</strong><small>'
                     +escape(threshold_status(row.get(name+' status')))+'</small></div>')
        analysis = row.get('_analysis_levels') or {}
        plan = analysis.get('plan') or {}
        analysis_cells = ''
        for name, value in level_values({'levels': analysis}).items():
            color = {'Wsparcie':'support','Opór':'resistance','SL':'sl','TP1':'tp','TP2':'tp'}[name]
            analysis_cells += ('<div class="ki-pf-level '+color+'"><div>'+escape(name)+'</div><strong>'
                              +escape(number_text(value,row.get('_currency') or ''))+'</strong></div>')
        analysis_note = (plan.get('reason') or 'Brak podstaw do wyliczenia poziomów.')
        if plan.get('status') == 'INDICATIVE':
            analysis_note = 'Plan kupna · poziomy orientacyjne, bez automatycznego zlecenia.'
            if plan.get('rr1') is not None:
                analysis_note += ' Zysk/ryzyko TP1: '+number_text(plan.get('rr1'),digits=2)+'.'
            if plan.get('rr1', 1) < 1:
                analysis_note += ' Potencjał TP1 mniejszy od ryzyka.'
        details=''.join('<div class="ki-pf-detail"><span>'+escape(label)+'</span><strong>'+field(key)+'</strong></div>'
                        for label,key in (('Otwarcie świecy','Otwarcie'),('Maksimum','Max'),('Minimum','Min'),
                            ('Cofnięcie od maksimum','Cofniecie %'),('Wolumen','Wolumen'),
                            ('Śr. wol. dostępnych świec','Sr. wol. 1M'),('Wolumen / średnia','Wol./Sr.'),
                            ('Spread z zapisu','Spread %')))
        cards.append('<article class="ki-pf-card"><div class="ki-pf-heading"><strong>'+field('Ticker')
            +'</strong><span class="'+direction+'">'+field('Zmiana 1H')+'</span></div>'
            '<div class="ki-pf-price">'+field('Cena')+'</div>'
            '<div class="ki-pf-caption">Zmiana ceny od otwarcia świecy 1h</div>'
            '<div class="ki-pf-badge '+('fresh' if fresh else 'old')+'">'+label+'</div>'
            '<div class="ki-pf-section">Moje progi alertów</div>'
            '<div class="ki-pf-levels">'+levels+'</div>'
            '<div class="ki-pf-caption">Odczyt: '+escape(time_text(row.get('_acquired_at')))+'</div>'
            '<section class="ki-pf-analysis"><div class="ki-pf-section">Poziomy z analizy KI</div>'
            '<div class="ki-pf-caption">'+escape(analysis.get('label','Brak danych do analizy'))+'</div>'
            '<div class="ki-pf-levels">'+analysis_cells+'</div>'
            '<div class="ki-pf-caption">'+escape(analysis_note)+'</div>'
            '<div class="ki-pf-caption">Dane analizy: '+escape(time_text(analysis.get('as_of')))+'</div></section>'
            '<details><summary>Ryzyko i dane</summary><p>'+escape(text(row.get('_fresh_reason')))+'</p>'
            +details+'<p>Ryzyko z zapisanej analizy: '+field('Ryzyko')+'</p>'
            '<p>Powody: '+field('Powody')+'</p><p>Braki: '+field('Braki')+'</p>'
            '<p>Czas danych ryzyka: '+escape(time_text(row.get('_risk_at')))+'</p>'
            '<p>Świeżość bid/ask niepotwierdzona. Twoje SL/TP są ustawieniami alertów; '
            'nie są wyliczonym planem technicznym ani zleceniami giełdowymi.</p></details></article>')
    return '''<style>
    .ki-pf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:10px;width:100%}
    .ki-pf-card{background:#182330;color:#edf2f7;border:1px solid #61758b;border-radius:10px;padding:12px;box-sizing:border-box;min-width:0;overflow-wrap:anywhere}
    .ki-pf-heading{display:flex;justify-content:space-between;align-items:center;gap:8px}.ki-pf-heading strong{font-size:1.1rem}
    .ki-pf-heading .up{color:#86efac}.ki-pf-heading .down{color:#fda4af}.ki-pf-heading .neutral{color:#cbd5e1}
    .ki-pf-price{font-size:1.3rem;font-weight:700;margin-top:8px;font-variant-numeric:tabular-nums}
    .ki-pf-caption{font-size:.85rem;color:#c6d0dc;margin:5px 0}
    .ki-pf-badge{font-size:.85rem;padding:5px 7px;margin-top:8px;border-radius:5px}
    .ki-pf-badge.fresh{background:#143b2c;color:#dcfce7}.ki-pf-badge.old{background:#443713;color:#fef9c3}
    .ki-pf-levels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin:10px 0}
    .ki-pf-section{font-size:.9rem;font-weight:700;margin-top:12px}.ki-pf-analysis{border-top:1px solid #43566c;margin-top:10px}
    .ki-pf-level{padding:8px;border-radius:6px;min-width:0;border-left:3px solid;font-size:.85rem}
    .ki-pf-level strong,.ki-pf-level small{display:block;margin-top:4px}.ki-pf-level strong{font-size:1.05rem}
    .ki-pf-level.sl{background:#4c1d24;color:#ffe4e6;border-color:#fb7185}.ki-pf-level.tp{background:#143b2c;color:#dcfce7;border-color:#4ade80}
    .ki-pf-level.support{background:#142b45;color:#bfdbfe;border-color:#60a5fa}.ki-pf-level.resistance{background:#322047;color:#e9d5ff;border-color:#c084fc}
    .ki-pf-card summary{cursor:pointer;min-height:44px;padding-top:10px;color:#c6d0dc}
    .ki-pf-card details p{font-size:.85rem;color:#c6d0dc}.ki-pf-detail{display:flex;justify-content:space-between;gap:12px;font-size:.85rem;margin:7px 0}.ki-pf-detail strong{text-align:right}
    @media(max-width:600px){.ki-pf-grid{grid-template-columns:minmax(0,1fr)}}
    </style><div class="ki-pf-grid">'''+''.join(cards)+'</div>'
