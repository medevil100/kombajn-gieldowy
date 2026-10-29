"""Read-only responsive presentation of locally computed tracking levels."""
from datetime import datetime, timezone
from html import escape
import math

from sl_tp import build_plan, stamp


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def level_view(snapshot, change, now=None, reference_ready=True):
    now = now or datetime.now(timezone.utc)
    at = stamp(snapshot.get('acquired_at'))
    empty = {'status': 'UNAVAILABLE', 'reason': 'Brak zapisanego odczytu ceny.'}
    if not at or at > now:
        return {'plan': empty, 'fresh': False, 'label': 'Brak wiarygodnego czasu danych', 'as_of': None}
    # Reconstruct the local calculation at its actual acquisition time. Never
    # present a reconstruction from an expired candle as a current trading plan.
    plan = build_plan(snapshot, change if reference_ready else None, now=at)
    start, end = stamp(snapshot.get('candle_time')), stamp(snapshot.get('candle_end'))
    fresh = bool(reference_ready and start and end and start <= at <= now < end
                 and 0 < (end-start).total_seconds() <= 3720
                 and (now-at).total_seconds() <= 900 and snapshot.get('candle_status') == 'OPEN'
                 and snapshot.get('latest_price_origin') != 'carried_previous_close')
    label = 'Bieżący odczyt · poziomy orientacyjne' if fresh else 'Dane historyczne · poziomy z chwili odczytu'
    if not reference_ready:
        label = 'Baza ruchu niepotwierdzona · tylko poziomy techniczne'
    return {'plan': plan, 'fresh': fresh, 'label': label, 'as_of': at.isoformat()}


def number_text(value, currency='', digits=4):
    if not numeric(value):
        return '—'
    return format(value, '.'+str(digits)+'f').replace('.', ',') + (' '+currency if currency else '')


def time_text(value):
    from zoneinfo import ZoneInfo
    moment = stamp(value)
    return moment.astimezone(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y %H:%M:%S %Z') if moment else 'brak czasu'


def level_values(row):
    plan = (row.get('levels') or {}).get('plan') or {}
    resistance = plan.get('resistance')
    if resistance is None and plan.get('resistances'):
        resistance = plan['resistances'][0].get('price')
    # SL/TP are a complete LONG plan only; partial plans show technical levels.
    usable = plan.get('status') == 'INDICATIVE' and plan.get('side') == 'LONG'
    return {
        'Wsparcie': (plan.get('support') or {}).get('price'),
        'Opór': resistance,
        'SL': plan.get('sl') if usable else None,
        'TP1': plan.get('tp1') if usable else None,
        'TP2': plan.get('tp2') if usable else None,
    }


def cards_html(rows):
    cards = []
    for row in rows:
        levels = row.get('levels') or {}
        plan = levels.get('plan') or {}
        currency = row.get('currency') or ''
        colors = {'Wsparcie': 'support', 'Opór': 'resistance', 'SL': 'sl', 'TP1': 'tp', 'TP2': 'tp'}
        cells = ''.join(
            '<div class="ki-track-level '+colors[label]+'"><dt>'+escape(label)+'</dt><dd>'
            +escape(number_text(value, currency))+'</dd></div>'
            for label, value in level_values(row).items()
        )
        reason = plan.get('reason') or 'Brak podstaw do wyliczenia poziomów.'
        down, up = plan.get('support_distance_pct'), plan.get('resistance_distance_pct')
        space = 'Do wsparcia: '+number_text(down, '%', 2)+' · do oporu: '+number_text(up, '%', 2)
        badge = 'fresh' if levels.get('fresh') else 'historical'
        availability = ('Plan kupna · poziomy orientacyjne; wykonanie niepotwierdzone.'
                        if plan.get('status') == 'INDICATIVE' else 'SL/TP: '+reason)
        cards.append(
            '<article class="ki-track-card"><div class="ki-track-title">'+escape(str(row['ticker']))+'</div>'
            '<div class="ki-track-badge '+badge+'">'+escape(levels.get('label', 'Brak danych'))+'</div>'
            '<div class="ki-track-price">Ostatnia cena: <strong>'+escape(number_text(row.get('current_price'), currency))+'</strong></div>'
            '<div class="ki-track-note">Zmiana od bazy śledzenia: '+escape(number_text(row.get('change_pct'), '%', 2))+'</div>'
            '<dl class="ki-track-levels">'+cells+'</dl>'
            '<div class="ki-track-note">'+escape(availability)+'</div>'
            '<div class="ki-track-note">'+escape(space)+'</div>'
            '<div class="ki-track-note">Odczyt ceny: '+escape(time_text(row.get('current_at')))+'</div>'
            '<div class="ki-track-note">Dane poziomów: '+escape(time_text(levels.get('as_of')))+'</div>'
            '<details><summary>Podstawa poziomów i ograniczenia</summary>'
            '<p>'+escape(reason)+'</p>'
            '<p>SL/TP: scenariusz pozycji kupna, bez automatycznego zlecenia. '
            'Dla ruchu spadkowego nie zakładamy krótkiej sprzedaży. '
            'Historia potwierdzeń nie jest bieżącą rekomendacją.</p>'
            '<p>Baza śledzenia: '+escape(number_text(row.get('anchor_price'), currency))
            +' · zapis śledzenia: '+escape(time_text(row.get('confirmed_at')))+'</p>'
            '<p>'+escape(plan.get('method', ''))+'</p></details></article>'
        )
    return '''<style>
    .ki-track-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:14px;width:100%}
    .ki-track-card{background:#182330;color:#edf2f7;border:1px solid #61758b;border-radius:12px;padding:16px;min-width:0;overflow-wrap:anywhere;box-sizing:border-box}
    .ki-track-title{font-size:1.35rem;font-weight:700;margin-bottom:8px}
    .ki-track-price{font-size:1.05rem;margin:12px 0 6px}
    .ki-track-badge{font-size:.9rem;padding:6px 8px;border-radius:6px}
    .ki-track-badge.fresh{background:#143b2c;color:#dcfce7}
    .ki-track-badge.historical{background:#443713;color:#fef9c3}
    .ki-track-levels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:14px 0}
    .ki-track-level{padding:9px;border-radius:7px;min-width:0;border-left:4px solid}
    .ki-track-level dt{font-size:.9rem;font-weight:600}.ki-track-level dd{font-size:1.05rem;font-weight:700;margin:4px 0 0;font-variant-numeric:tabular-nums}
    .ki-track-level.support{background:#142b45;color:#bfdbfe;border-color:#60a5fa}
    .ki-track-level.resistance{background:#322047;color:#e9d5ff;border-color:#c084fc}
    .ki-track-level.sl{background:#4c1d24;color:#ffe4e6;border-color:#fb7185}
    .ki-track-level.tp{background:#143b2c;color:#dcfce7;border-color:#4ade80}
    .ki-track-note{font-size:.9rem;color:#c6d0dc;margin:6px 0}
    .ki-track-card summary{cursor:pointer;min-height:44px;padding-top:12px;color:#c6d0dc}
    .ki-track-card details p{font-size:.9rem;color:#c6d0dc}
    @media(max-width:420px){.ki-track-card{padding:12px}.ki-track-level{padding:7px}.ki-track-level dd{font-size:1rem}}
    </style><div class="ki-track-grid">''' + ''.join(cards) + '</div>'
