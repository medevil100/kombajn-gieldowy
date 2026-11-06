"""Read-only, paginated company history assembled from existing KI records."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html import escape
import json
import re

from tavily_cli_adapter import sanitize_cli_diagnostic
from tracking_view import number_text, time_text


CATEGORIES = ('Rynek', 'Potwierdzenia', 'Kwalifikacja', 'Tavily', 'Analizy AI', 'Telegram', 'Analizy ręczne')
PAGE_SIZE = 20
SOURCES = {
    'observation': ('Rynek', """
        SELECT 'observation' AS source, CAST(id AS TEXT) AS id, acquired_at AS at, candle_status AS state
        FROM observations WHERE ticker=?
    """),
    'daily': ('Rynek', """
        SELECT 'daily' AS source, session_date AS id, closed_at AS at, 'CLOSED' AS state
        FROM daily_candles WHERE ticker=?
    """),
    'signal': ('Potwierdzenia', """
        SELECT 'signal' AS source, confirmed_at AS id, confirmed_at AS at, 'CONFIRMED' AS state
        FROM signal_confirmations WHERE ticker=?
    """),
    'opportunity': ('Kwalifikacja', """
        SELECT 'opportunity' AS source, sequence_id AS id, updated_at AS at, state
        FROM opportunities WHERE ticker=?
    """),
    'decision': ('Kwalifikacja', """
        SELECT 'decision' AS source, CAST(d.id AS TEXT) AS id, d.ts AS at,
               CASE WHEN d.should_alert=1 THEN 'ALLOWED' ELSE 'FILTERED' END AS state
        FROM opportunities o JOIN alert_decisions d ON d.seq=o.sequence_id WHERE o.ticker=?
    """),
    'research': ('Tavily', """
        SELECT 'research' AS source, r.event_id AS id, r.updated_at AS at, r.state
        FROM events e JOIN research_requests r ON r.event_id=e.id WHERE e.ticker=?
    """),
    'analysis': ('Analizy AI', """
        SELECT 'analysis' AS source, j.event_id AS id, j.updated_at AS at, j.state
        FROM events e JOIN analysis_jobs j ON j.event_id=e.id WHERE e.ticker=?
    """),
    'rejection': ('Analizy AI', """
        SELECT 'rejection' AS source, r.id, r.created_at AS at, 'FILTERED' AS state
        FROM events e JOIN analysis_rejections r ON r.event_id=e.id WHERE e.ticker=?
    """),
    'archived_rejection': ('Analizy AI', """
        SELECT 'archived_rejection' AS source, r.id, r.created_at AS at, 'FILTERED' AS state
        FROM events e JOIN archived_analysis_rejections r ON r.event_id=e.id WHERE e.ticker=?
    """),
    'telegram': ('Telegram', """
        SELECT 'telegram' AS source, o.id, COALESCE(r.delivered_at,o.delivered_at,o.created_at) AS at,
               o.status AS state
        FROM events e JOIN outbox o ON o.event_id=e.id
        LEFT JOIN delivery_receipts r ON r.outbox_id=o.id WHERE e.ticker=?
    """),
    'manual': ('Analizy ręczne', """
        SELECT 'manual' AS source, id, COALESCE(finished_at,created_at) AS at, state
        FROM gpt_chat_turns WHERE json_extract(CASE WHEN json_valid(context) THEN context ELSE '{}' END,'$.ticker')=?
    """),
    'deep': ('Analizy ręczne', """
        SELECT 'deep' AS source, id, COALESCE(finished_at,created_at) AS at, state
        FROM deep_reports WHERE ticker=?
    """),
}
STATE_LABELS = {
    'OPEN': 'Świeca w trakcie', 'CLOSED': 'Świeca zamknięta',
    'CONFIRMED': 'Ruch potwierdzony', 'CANDIDATE': 'Kandydat',
    'MONITORING': 'Obserwacja', 'RESERVED': 'Zarezerwowano',
    'SELECTED': 'Wybrano do analizy', 'EXPIRED': 'Zapis wygasł',
    'SKIPPED_LIMIT': 'Limit analiz', 'SKIPPED_RESTART': 'Przerwano przy restarcie',
    'ALLOWED': 'Warunki wysyłki spełnione', 'FILTERED': 'Zatrzymano na bramce',
    'PENDING_CONTEXT': 'Oczekuje na Tavily', 'BUSY_CONTEXT': 'Pobieranie kontekstu',
    'PENDING_AI': 'Oczekuje na AI', 'BUSY_AI': 'Analiza AI w toku',
    'DONE': 'Zapisano wynik', 'COMPLETED': 'Pobieranie zakończone',
    'FAILED': 'Błąd', 'REVIEW_REQUIRED': 'Wymaga sprawdzenia',
    'RESERVED_RESEARCH': 'Zarezerwowano zapytanie', 'SUBMITTED': 'Wysłano zapytanie',
    'CALL_UNCERTAIN': 'Wynik wywołania niepotwierdzony',
    'PENDING': 'Oczekuje na wysyłkę', 'PREVIEW': 'Podgląd wiadomości',
    'SENDING': 'Wysyłanie', 'DELIVERED': 'Zapisano doręczenie',
    'UNCERTAIN': 'Doręczenie niepotwierdzone', 'REQUESTED': 'Zapisano żądanie',
    'RUNNING': 'W toku', 'ERROR': 'Błąd', 'DISABLED': 'Wyłączono',
}


def tickers(store):
    with store.connection() as connection:
        return [row[0] for row in connection.execute("""
            SELECT ticker FROM watchlist UNION SELECT ticker FROM observations
            UNION SELECT ticker FROM opportunities UNION SELECT ticker FROM events
            UNION SELECT ticker FROM signal_confirmations UNION SELECT ticker FROM daily_candles
            UNION SELECT ticker FROM deep_reports
            UNION SELECT json_extract(CASE WHEN json_valid(context) THEN context ELSE '{}' END,'$.ticker') FROM gpt_chat_turns
            ORDER BY 1
        """) if isinstance(row[0], str) and row[0]]


def decoded(value, default=None):
    if value is None:
        return default
    try:
        result = json.loads(value)
        return result if default is None or isinstance(result, type(default)) else default
    except (TypeError, ValueError):
        return default


def details(connection, item, ticker):
    """Project small fields only, leaving chart histories and raw provider bodies in SQLite."""
    source, identifier = item['source'], item['id']
    title = CATEGORIES[0]
    summary = ''
    fields = []
    state = item['state']
    if source == 'observation':
        row = connection.execute("""
            SELECT interval,candle_time,
                   json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.price') AS price,json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.currency') AS currency,
                   json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.volume') AS volume,json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.rvol') AS rvol,
                   json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.price_matrix.change_pct') AS change_pct,
                   json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.price_matrix.state') AS matrix_state,
                   json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.price_matrix.consecutive_reads') AS reads
            FROM observations WHERE id=? AND ticker=?
        """, (identifier, ticker)).fetchone()
        title = 'Odczyt rynku · ' + row['interval']
        summary = number_text(row['price'], row['currency'] or '')
        fields = [('Świeca', time_text(row['candle_time'])),
                  ('Wolumen', number_text(row['volume'], digits=0)),
                  ('RVOL', number_text(row['rvol'], '×', 2)),
                  ('Zmiana od bazy', number_text(row['change_pct'], '%', 2)),
                  ('Matryca', STATE_LABELS.get(row['matrix_state'], row['matrix_state'] or 'Brak zapisu')),
                  ('Odczyty z aktywnością', str(row['reads']) if row['reads'] is not None else 'Brak zapisu')]
    elif source == 'daily':
        row = connection.execute('SELECT * FROM daily_candles WHERE ticker=? AND session_date=?',
                                 (ticker, identifier)).fetchone()
        title = 'Dane dzienne · ' + row['session_date']
        summary = 'Zamknięcie ' + number_text(row['close'])
        previous = connection.execute(
            'SELECT session_date,close FROM daily_candles WHERE ticker=? AND session_date<? '
            'ORDER BY session_date DESC LIMIT 1', (ticker, row['session_date'])).fetchone()
        movement = daily_movement(row['close'], previous['close'] if previous else None)
        item = {**item, 'daily_movement': movement['direction'], 'movement_label': movement['label']}
        fields = [('Porównanie zamknięcia', movement['label']),
                  ('Poprzednia zapisana sesja', previous['session_date'] if previous else 'Brak zapisu'),
                  ('Poprzednie zamknięcie', number_text(previous['close']) if previous else 'Brak zapisu'),
                  ('Otwarcie', number_text(row['open'])), ('Maksimum', number_text(row['high'])),
                  ('Minimum', number_text(row['low'])), ('Wolumen', number_text(row['volume'], digits=0)),
                  ('Źródło', row['source'])]
    elif source == 'signal':
        row = connection.execute("""
            SELECT s.price,s.change_pct,s.currency,t.payload
            FROM signal_confirmations s LEFT JOIN signal_technical_context t
            ON t.ticker=s.ticker AND t.confirmed_at=s.confirmed_at
            WHERE s.ticker=? AND s.confirmed_at=?
        """, (ticker, identifier)).fetchone()
        title = 'Potwierdzenie wzrostu' if row['change_pct'] > 0 else 'Potwierdzenie spadku'
        summary = number_text(row['change_pct'], '%', 2) + ' · ' + number_text(row['price'], row['currency'])
        context = decoded(row['payload'], {})
        events = context.get('events')
        fields = [('Zdarzenia techniczne', ', '.join(str(event.get('label', '')) for event in (events if isinstance(events, list) else []) if isinstance(event, dict))
                   or 'Brak zapisanego rodzaju zdarzenia')]
    elif source == 'opportunity':
        row = connection.execute("""
            SELECT json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.quality') AS quality,
                   json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.risk.label') AS risk FROM opportunities
            WHERE sequence_id=? AND ticker=?
        """, (identifier, ticker)).fetchone()
        title = 'Kwalifikacja do analizy'
        summary = STATE_LABELS.get(state, state)
        fields = [('Ocena', row['quality'] if row['quality'] is not None else 'Brak zapisu'), ('Ryzyko', row['risk'] or 'Brak zapisu')]
    elif source == 'decision':
        row = connection.execute('SELECT stage,reason,seq FROM alert_decisions WHERE id=?',
                                 (identifier,)).fetchone()
        title = 'Bramka wysyłki'
        summary = row['reason']
        fields = [('Etap', row['stage']), ('Powiązanie', row['seq'])]
    elif source == 'research':
        row = connection.execute("""
            SELECT r.query,r.created_at,r.last_error,
                   COALESCE(json_array_length(CASE WHEN json_valid(r.raw_response) THEN r.raw_response ELSE '{}' END,'$.results'),
                            json_array_length(CASE WHEN json_valid(r.raw_response) THEN r.raw_response ELSE '{}' END,'$.sources')) AS returned,
                   json_array_length(CASE WHEN json_valid(j.context) THEN j.context ELSE '{}' END,'$.sources') AS accepted,
                   json_extract(CASE WHEN json_valid(j.context) THEN j.context ELSE '{}' END,'$.excluded') AS excluded,
                   json_extract(CASE WHEN json_valid(j.context) THEN j.context ELSE '{}' END,'$.sources') AS sources,
                   json_extract(CASE WHEN json_valid(j.context) THEN j.context ELSE '{}' END,'$.rejected_sources') AS rejected
            FROM research_requests r LEFT JOIN analysis_jobs j ON j.event_id=r.event_id
            WHERE r.event_id=?
        """, (identifier,)).fetchone()
        title = 'Tavily · zapis wyszukiwania'
        summary = row['last_error'] or row['query']
        fields = [('Zapytanie', row['query']), ('Utworzono', time_text(row['created_at'])),
                  ('Wyniki źródła', row['returned']), ('Źródła przyjęte w KI', row['accepted']),
                  ('Odrzucono', row['excluded'])]
        for label, values in (('Przyjęte źródło', decoded(row['sources'], [])),
                              ('Odrzucone źródło', decoded(row['rejected'], []))):
            for value in values:
                if isinstance(value, dict):
                    fields.append((label, '\n'.join(str(value[key]) for key in ('title', 'url', 'published_at', 'reason') if value.get(key))))
    elif source == 'analysis':
        row = connection.execute("""
            SELECT last_error,attempts,next_attempt_at,
                   COALESCE(json_extract(CASE WHEN json_valid(result) THEN result ELSE '{}' END,'$.local_only'),json_extract(CASE WHEN json_valid(result) THEN result ELSE '{}' END,'$.provider.not_called')) AS local_only,
                   COALESCE(json_extract(CASE WHEN json_valid(result) THEN result ELSE '{}' END,'$.local_review.summary'),json_extract(CASE WHEN json_valid(result) THEN result ELSE '{}' END,'$.local_review.label')) AS local_summary,
                   json_extract(CASE WHEN json_valid(result) THEN result ELSE '{}' END,'$.analysis') AS analysis,
                   COALESCE(json_extract(CASE WHEN json_valid(result) THEN result ELSE '{}' END,'$.ai_preflight.skip_reasons'),json_extract(CASE WHEN json_valid(context) THEN context ELSE '{}' END,'$.ai_preflight.skip_reasons')) AS skip_reasons,
                   json_extract(CASE WHEN json_valid(result) THEN result ELSE '{}' END,'$.provider.usage.total_tokens') AS tokens
            FROM analysis_jobs WHERE event_id=?
        """, (identifier,)).fetchone()
        from ai_assessment import summary_text
        analysis = decoded(row['analysis'], {})
        title = 'Ocena lokalna' if row['local_only'] else 'Analiza AI · zachowany stan'
        summary = row['last_error'] or row['local_summary'] or summary_text(analysis) or STATE_LABELS.get(state, state)
        fields = [('Wspólny wniosek', summary_text(analysis)),
                  ('Powody pominięcia AI', ' · '.join(str(value) for value in decoded(row['skip_reasons'], []))),
                  ('Próby bieżącego etapu', row['attempts']), ('Zapisane tokeny', row['tokens']),
                  ('Ponowienie po', time_text(row['next_attempt_at']) if row['next_attempt_at'] else 'Brak terminu')]
        for key, label in (('technical', 'Technika'), ('context', 'Kontekst'),
                           ('hypotheses', 'Hipotezy'), ('risks', 'Ryzyka'), ('missing', 'Braki')):
            entries = analysis.get(key, [])
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, dict):
                    text = entry.get('interpretation') or entry.get('fact') or entry.get('text') or json.dumps(entry, ensure_ascii=False)
                else:
                    text = str(entry)
                fields.append((label, text))
    elif source in ('rejection', 'archived_rejection'):
        table = 'analysis_rejections' if source == 'rejection' else 'archived_analysis_rejections'
        row = connection.execute('SELECT reason FROM ' + table + ' WHERE id=?', (identifier,)).fetchone()
        title = 'Zatrzymanie analizy' + (' · archiwum' if source == 'archived_rejection' else '')
        summary = row['reason']
    elif source == 'telegram':
        row = connection.execute("""
            SELECT o.message,o.kind,o.last_error,o.attempts,o.created_at,
                   r.delivered_at AS receipt_at,r.message_id
            FROM outbox o LEFT JOIN delivery_receipts r ON r.outbox_id=o.id WHERE o.id=?
        """, (identifier,)).fetchone()
        proven = row['receipt_at'] is not None and row['message_id'] is not None
        title = 'Telegram · potwierdzono wysyłkę' if proven else 'Telegram · stan wiadomości'
        summary = row['last_error'] or row['message']
        fields = [('Wiadomość', row['message']), ('Próby wysyłki', row['attempts']),
                  ('Utworzono', time_text(row['created_at'])),
                  ('Potwierdzenie API', time_text(row['receipt_at']) if proven else 'Brak zapisanego potwierdzenia'),
                  ('Rodzaj', {'ANALYSIS': 'Analiza', 'EVIDENCE': 'Detekcja', 'REPORT': 'Raport'}.get(row['kind'], row['kind']))]
    elif source == 'manual':
        row = connection.execute('SELECT question,answer,error,created_at FROM gpt_chat_turns WHERE id=?',
                                 (identifier,)).fetchone()
        title = 'Rozmowa lub analiza ręczna'
        summary = row['error'] or row['question']
        fields = [('Pytanie', row['question']), ('Odpowiedź', row['answer'] or 'Brak zapisanej odpowiedzi'),
                  ('Utworzono', time_text(row['created_at']))]
    elif source == 'deep':
        row = connection.execute('SELECT error,created_at,payload FROM deep_reports WHERE id=?',
                                 (identifier,)).fetchone()
        title = 'Analiza pogłębiona'
        summary = row['error'] or STATE_LABELS.get(state, state)
        fields = [('Utworzono', time_text(row['created_at']))]
        report = decoded(row['payload'], {})
        fields.append(('Ocena zapisanego raportu', report.get('rating')))
        reports = report.get('reports')
        if isinstance(reports, dict):
            fields.extend((str(label), str(value)) for label, value in reports.items())
    return {**item, 'title': title, 'summary': summary or 'Brak zapisanego opisu',
            'fields': fields, 'category': SOURCES[source][0]}


def page(store, ticker, categories=CATEGORIES, days=30, index=1, at=None):
    now = at or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days) if days is not None else datetime(1970, 1, 1, tzinfo=timezone.utc)
    queries = [sql for category, sql in SOURCES.values() if category in categories]
    if not queries:
        return {'rows': [], 'count': 0, 'pages': 1, 'index': 1}
    union = ' UNION ALL '.join(queries)
    sql = f"SELECT * FROM ({union}) WHERE julianday(at) BETWEEN julianday(?) AND julianday(?)"
    args = [ticker] * len(queries) + [cutoff.isoformat(), now.isoformat()]
    with store.connection() as connection:
        connection.execute('BEGIN')
        count = connection.execute('SELECT COUNT(*) FROM (' + sql + ')', args).fetchone()[0]
        pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
        index = max(1, min(index, pages))
        records = connection.execute(
            sql + ' ORDER BY julianday(at) DESC,source DESC,id DESC LIMIT ? OFFSET ?',
            args + [PAGE_SIZE, (index - 1) * PAGE_SIZE]
        ).fetchall()
        rows = [details(connection, dict(row), ticker) for row in records]
    return {'rows': rows, 'count': count, 'pages': pages, 'index': index}


def daily_movement(close, previous):
    """Direction against the previous stored daily close; missing data is not flat."""
    try:
        current, base = Decimal(str(close)), Decimal(str(previous))
        if not current.is_finite() or not base.is_finite() or current <= 0 or base <= 0:
            raise ValueError('Invalid close')
    except (InvalidOperation, ValueError, TypeError):
        return {'direction': 'unknown', 'label': 'Brak poprawnego poprzedniego zamknięcia do porównania'}
    if current == base:
        return {'direction': 'flat', 'label': 'Cena bez zmian względem poprzedniej zapisanej sesji · 0,00%'}
    change = float((current / base - 1) * 100)
    direction = 'up' if current > base else 'down'
    return {'direction': direction,
            'label': ('Wzrost' if direction == 'up' else 'Spadek') +
                     ' względem poprzedniej zapisanej sesji · ' + number_text(change, '%', 2)}


def cards_html(rows):
    def safe(value):
        value = 'Brak zapisu' if value is None else str(value)
        value = re.sub(r'(?<!\d)\d{6,}:[A-Za-z0-9_-]{20,}', '[ukryto token]', value)
        cleaned = sanitize_cli_diagnostic(value)
        return cleaned + ('\n[Długi zapis skrócono w tym widoku.]' if len(value) > 3000 else '')
    def text(value):
        return escape(safe(value))
    cards = []
    for row in rows:
        state = row['state']
        color = ('bad' if state in ('FAILED', 'ERROR', 'UNCERTAIN', 'REVIEW_REQUIRED', 'CALL_UNCERTAIN')
                 else 'good' if state in ('CONFIRMED', 'DONE', 'COMPLETED', 'DELIVERED') else 'neutral')
        fields = ''.join('<p><strong>' + text(label) + '</strong><br>' + text(value) + '</p>'
                         for label, value in row['fields'])
        summary = safe(row['summary'])
        short = summary[:180] + ('…' if len(summary) > 180 else '')
        daily_class = (' daily-' + row.get('daily_movement', 'unknown')
                       if row.get('source') == 'daily' else '')
        movement = ('<p class="ki-history-movement">' + text(row['movement_label']) + '</p>'
                    if row.get('source') == 'daily' and row.get('movement_label') else '')
        cards.append('<article class="ki-history-card' + daily_class + '"><div class="ki-history-date">' + text(time_text(row['at']))
                     + ' · ' + text(row['category']) + '</div><strong class="ki-history-title">' + text(row['title'])
                     + '</strong><div class="ki-history-state ' + color + '">' + text(STATE_LABELS.get(state, state))
                     + '</div><p>' + text(short) + '</p>' + movement + '<details><summary>Szczegóły zapisu</summary>'
                     + '<p>' + text(summary) + '</p>' + fields
                     + '<p>Identyfikator zapisu<br>' + text(row['id']) + '</p></details></article>')
    return '''<style>
    .ki-history-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px}
    .ki-history-card{background:#182330;color:#edf2f7;border:1px solid #61758b;border-radius:10px;padding:14px;min-width:0;overflow-wrap:anywhere}
    .ki-history-card.daily-up{background:#123b2c;border-color:#4ade80;color:#ecfdf5}
    .ki-history-card.daily-down{background:#4c1d24;border-color:#fb7185;color:#fff1f2}
    .ki-history-card.daily-flat{background:#493c12;border-color:#facc15;color:#fef9c3}
    .ki-history-movement{font-weight:600}
    .ki-history-date{font-size:.85rem;color:#c6d0dc;margin-bottom:8px}
    .ki-history-title{font-size:1.05rem}.ki-history-state{border-left:3px solid;padding:6px 8px;margin-top:10px;font-size:.9rem}
    .ki-history-state.good{background:#143b2c;color:#dcfce7;border-color:#4ade80}
    .ki-history-state.bad{background:#4c1d24;color:#ffe4e6;border-color:#fb7185}
    .ki-history-state.neutral{background:#142b45;color:#bfdbfe;border-color:#60a5fa}
    .ki-history-card p{font-size:.9rem;white-space:pre-wrap}.ki-history-card summary{min-height:44px;cursor:pointer;padding:10px 0;box-sizing:border-box}
    @media(max-width:600px){.ki-history-grid{grid-template-columns:minmax(0,1fr)}}
    </style><div class="ki-history-grid">''' + ''.join(cards) + '</div>'


def render_ki_log(store):
    import streamlit as st
    st.subheader('Historia spółki w KI')
    st.caption('Dostępne zapisy rynku, potwierdzeń, analiz i wysyłek. Zadania pokazują zachowany stan '
               'z czasem ostatniej aktualizacji. Odczyty rynku podlegają ustawionej retencji.')
    def clear_ticker():
        st.session_state['company_history_symbol'] = ''
        st.session_state.pop('company_history_active_ticker', None)
        st.session_state.pop('company_history_selection', None)

    with st.form('company_history_search'):
        symbol = st.text_input('Ticker spółki', value='', placeholder='Wpisz ticker, np. STX.WA lub MREO',
                               key='company_history_symbol', max_chars=30)
        submitted = st.form_submit_button('Pokaż historię')
        st.form_submit_button('Wyczyść', on_click=clear_ticker)
    if submitted:
        st.session_state['company_history_active_ticker'] = symbol.strip().upper()
    ticker = st.session_state.get('company_history_active_ticker')
    if not ticker:
        st.info('Wpisz ticker i wybierz „Pokaż historię”.')
        return
    st.caption('Wyświetlana historia: ' + ticker)
    ranges = {'7 dni': 7, '30 dni': 30, '90 dni': 90, 'Cała zapisana historia': None}
    window = st.selectbox('Okres historii', list(ranges), index=3, key='company_history_range')
    categories = st.multiselect('Etapy historii', CATEGORIES, default=CATEGORIES, key='company_history_categories')
    selection = (ticker, window, tuple(categories))
    refresh = st.button('Odśwież historię spółki', key='company_history_refresh')
    if st.session_state.get('company_history_selection') != selection or refresh:
        st.session_state['company_history_selection'] = selection
        st.session_state['company_history_at'] = datetime.now(timezone.utc)
        st.session_state['company_history_page'] = 1
    @st.fragment(run_every=60)
    def timeline():
        if int(st.session_state.get('company_history_page', 1)) == 1:
            st.session_state['company_history_at'] = datetime.now(timezone.utc)
        at = st.session_state['company_history_at']
        result = page(store, ticker, categories, ranges[window],
                      int(st.session_state.get('company_history_page', 1)), at)
        if not result['count']:
            st.info('Brak zapisów dla wybranej spółki, okresu i etapów.')
            return
        st.session_state['company_history_page'] = result['index']
        selected = st.number_input('Strona historii', min_value=1, max_value=result['pages'], step=1,
                                   key='company_history_page')
        if selected != result['index']:
            result = page(store, ticker, categories, ranges[window], selected, at)
        st.caption(f'{ticker} · {result["count"]} zapisów · strona {result["index"]} z {result["pages"]} · najnowsze na początku')
        st.caption('Stan zapisów: ' + time_text(at.isoformat()) +
                   ' · pierwsza strona odświeża się co minutę. Starsze strony zachowują kolejność; '
                   'przycisk odświeżania wraca do najnowszych. Liczba stron wynika z zapisów i filtrów.')
        st.html(cards_html(result['rows']))
    timeline()


def render(store):
    from company_market_history import render as render_market_history
    render_market_history(store)
