"""Read-only TOP 5 of fresh, accepted independent company reviews. No providers."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from html import escape
import json
import sqlite3
import company_orchestrator as orchestrator
import market_intelligence
import company_narrative
from urllib.parse import urlsplit

from sl_tp import stamp
from tracking_view import number_text, time_text, level_values

LIMIT = 5
VIEW = 'Wybrane okazje · TOP 5'


def collect(api, store, now=None, market='Wszystkie'):
    """Never recycle an older positive report after a newer pending/failed one."""
    current=stamp(now) if now is not None else datetime.now(timezone.utc)
    if not current:raise ValueError('Niepoprawny czas widoku TOP 5.')
    if market not in ('Wszystkie','GPW','USA'):raise ValueError('Nieznany rynek.')
    result={'cards':[],'rising_watch':[],'warnings':[],'excluded':{},'as_of':current.isoformat(),'market':market}
    ticks=set(store.load_section('tickers',[]));excluded=Counter()
    path=store.path.resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'events','analysis_jobs','company_review_batches','observations'}<=tables:return result
        rows=db.execute('''WITH latest AS (
            SELECT e.id,e.ticker,e.payload,e.created_at,j.state,j.context,j.result,j.updated_at,
                   ROW_NUMBER() OVER(PARTITION BY e.ticker ORDER BY e.created_at DESC,e.id DESC) AS position
            FROM events e JOIN analysis_jobs j ON j.event_id=e.id
            WHERE e.created_at>=? AND e.created_at<=? AND e.interval='1h'
              AND json_valid(e.payload)
              AND json_extract(e.payload,'$.company_review_batch') IS NOT NULL
        ) SELECT * FROM latest WHERE position=1''',
            ((current-timedelta(days=1)).isoformat(),current.isoformat())).fetchall()
        for row in rows:
            ticker=row['ticker']
            if market!='Wszystkie' and (ticker.endswith('.WA'))!=(market=='GPW'):continue
            try:
                if ticker not in ticks:excluded['Poza listą obserwowanych']+=1;continue
                if row['state']!='DONE':excluded['Nowsza ocena nie jest zakończona poprawnie']+=1;continue
                event=api.load_payload(row['payload']);snapshot=event['snapshot']
                context=api.load_payload(row['context']);manifest=context['analysis_manifest']
                if (snapshot.get('ticker')!=ticker or context.get('ticker',ticker)!=ticker
                    or manifest.get('identity',{}).get('ticker')!=ticker
                    or snapshot.get('interval')!='1h'
                    or manifest.get('purpose')!='FINAL_COMPANY_REVIEW'):
                    excluded['Niespójna tożsamość raportu']+=1;continue
                at=stamp(snapshot.get('acquired_at'))
                if not at or not 0<=(current-at).total_seconds()<=900:
                    excluded['Ocena nieaktualna']+=1;continue
                batch=db.execute('SELECT state,payload,created_at FROM company_review_batches WHERE id=?',
                                 (event['company_review_batch'],)).fetchone()
                if (not batch or batch['state']!='READY'
                    or row['id'] not in api.load_payload(batch['payload']).get('included',[])):
                    excluded['Nie zakwalifikowano do zestawienia']+=1;continue
                saved=api.load_payload(row['result'])['analysis']
                clean=api.validate_event_analysis(saved,snapshot,context)
                if (api.analysis_publication_issues(clean,True)
                    or (clean.get('final_review') or {}).get('attention')!='INFORM'
                    or (manifest.get('local_review') or {}).get('verdict')!='ALIGNED'
                    or (manifest.get('session_context') or {}).get('status')!='COMPLETE_TO_ASOF'):
                    excluded['Ocena nie spełnia bramek jakości']+=1;continue
                raw=db.execute("SELECT payload FROM observations WHERE ticker=? AND interval='1h' ORDER BY id DESC LIMIT 1",(ticker,)).fetchone()
                latest=api.load_payload(raw[0]) if raw else None
                if (not latest or not api.review_movement_valid(event,current,store.load_section('settings',{}))
                    or not api.same_opportunity_basis(latest,snapshot)
                    or not api.review_movement_valid({**event,'snapshot':latest},current,store.load_section('settings',{}),latest=True)
                    or (latest.get('price_matrix') or {}).get('change_pct',0)*(snapshot.get('price_matrix') or {}).get('change_pct',0)<=0):
                    excluded['Ruch wygasł lub zmieniła się baza']+=1;continue
                control=orchestrator.report_decision(api,event,context,clean,store.load_section('settings',{}),current,latest)
                if not control['notify']:
                    excluded['Najnowszy odczyt nie podtrzymuje kwalifikacji']+=1;continue
                score=(event.get('ranking') or {}).get('score')
                if not api.finite_number(score):score=(manifest.get('technical') or {}).get('directional_score')
                bucket='cards' if control['role']==orchestrator.TOP else 'warnings' if control['role']==orchestrator.WARNING else 'rising_watch'
                result[bucket].append({'event_id':row['id'],'ticker':ticker,'snapshot':snapshot,
                    'analysis':clean,'context':context,'manifest':manifest,'score':score,
                    'orchestration':control,
                    'evidence_review':(api.load_payload(row['result']).get('provider') or {}).get('evidence_review'),
                    'review_at':row['updated_at'],'latest_at':latest.get('acquired_at'),
                    'valid_until':min(at+timedelta(minutes=15),stamp(snapshot['candle_end'])).isoformat(),
                    'batch_at':batch['created_at']})
            except (ValueError,TypeError,KeyError,OverflowError):
                excluded['Niepoprawny zapis raportu']+=1
    for bucket in ('cards','rising_watch','warnings'):
        result[bucket].sort(key=lambda c:(-(c['score'] if api.finite_number(c['score']) else -1),
            -stamp(c['snapshot']['acquired_at']).timestamp(),c['ticker']))
        result[bucket]=result[bucket][:LIMIT]
    result['excluded']=dict(excluded)
    return result


def paragraph(value,css=''):
    return '<p'+(' class="'+css+'"' if css else '')+'>'+escape(str(value))+'</p>'


def table(rows):
    if not rows:return paragraph('Brak zapisanych danych.','ki-top5-note')
    keys=list(rows[0])
    return ('<div class="ki-top5-table"><table><thead><tr>'+''.join('<th>'+escape(k)+'</th>' for k in keys)
            +'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(row.get(k,'—')))+'</td>' for k in keys)
            +'</tr>' for row in rows)+'</tbody></table></div>')


def scenario_text(plan,now):
    until=stamp(plan.get('valid_until'))
    if plan.get('status')!='CONDITIONAL' or not until or now>=until:
        return [('Warunki dalszego ruchu','Brak bieżącego scenariusza. Zapisane warunki historyczne są w pełnej analizie.')]
    condition=plan.get('condition') or {};interval=plan.get('interval') or '1h'
    if condition.get('operator')=='BETWEEN':
        low,high=number_text(condition.get('lower')),number_text(condition.get('upper'))
        return [('W przedziale', 'Zamknięcie kolejnej pełnej świecy '+interval+' między '+low+' a '+high+' podtrzymuje wariant przedziału.'),
                ('Wyjście górą','Zamknięcie powyżej '+high+' kończy wariant przedziału; kierunek wymaga nowej oceny.'),
                ('Wyjście dołem','Zamknięcie poniżej '+low+' kończy wariant przedziału; kierunek wymaga nowej oceny.')]
    return [('Co podtrzymuje wariant',plan.get('base') or 'Brak zapisanego warunku.'),
            ('Co go unieważnia',plan.get('alternative') or 'Brak zapisanego warunku zanegowania.')]


def full_html(api,card,now):
    s=card['snapshot'];a=card['analysis'];m=card['manifest'];ctx=card['context']
    html='<details class="ki-top5-full"><summary>Pełna analiza · '+escape(card['ticker'])+'</summary>'
    if card.get('evidence_review'):
        html+=paragraph('AI wybrało werdykt i dowody. Pełny opis złożyło KI ze zweryfikowanych danych.','ki-top5-note')
        html+='<h4>Warunek obserwacji wybrany przez AI</h4>'+paragraph(card['evidence_review'].get('condition_text') or 'Brak zapisanego warunku.')
    for key,label in (('movement','Ruch i technika'),('activity','Wolumen i aktywność'),('risk','Ryzyko i ograniczenia')):
        html+='<h4>'+label+'</h4>'+paragraph(a['assessment'][key])
    html+=paragraph(api.activity_summary(s,ctx.get('previous_snapshot')),'ki-top5-note')
    html+='<h4>Wskaźniki — uzasadnienie AI</h4>'
    for item in a.get('technical',[]):html+=paragraph(api.polish_indicator(item['metric'])+': '+item['interpretation'])
    html+='<h4>Wszystkie wskaźniki</h4>'+api.indicator_table_html(s)
    events=(m.get('technical_events') or {}).get('events') or []
    html+='<h4>Zdarzenia techniczne</h4>'
    for item in events:html+=paragraph(str(item.get('label',''))+' · '+str(item.get('evidence','')))
    if not events:html+=paragraph('Brak zapisanych zdarzeń.','ki-top5-note')
    plan=m.get('trade_plan') or {}
    html+='<h4>Poziomy techniczne i SL/TP</h4>'
    for line in api.trade_plan_lines(plan,details=True,now=now):html+=paragraph(line)
    scenario=m.get('scenario_plan') or {}
    html+='<h4>Scenariusz — zapis z chwili oceny</h4>'
    html+=paragraph('Podstawa: '+time_text(scenario.get('candle_time'))+' · ważność do: '+time_text(scenario.get('valid_until')),'ki-top5-note')
    for field in ('base','alternative','reason','quote_limitation'):
        if scenario.get(field):html+=paragraph(scenario[field])
    for warning in scenario.get('warnings',[]):html+=paragraph(warning,'ki-top5-note')
    html+='<h4>Bid/ask — dane pomocnicze</h4>'+table(api.quote_report_rows(s))
    session=m.get('session_context') or {};summary=session.get('summary') or {}
    html+='<h4>Przebieg zapisanej sesji</h4>'+paragraph('Dane do: '+time_text(session.get('as_of'))+' · każda świeca liczona raz; odczyty wolumenu są narastające.','ki-top5-note')
    html+=table([{'Dane':label,'Wartość':number_text(summary.get(key),unit,2)} for key,label,unit in (
        ('session_open_price','Otwarcie sesji',s['currency']),('observed_low','Minimum sesji',s['currency']),
        ('observed_high','Maksimum sesji',s['currency']),('change_from_session_open_pct','Zmiana od otwarcia','%'),
        ('observed_volume','Wolumen zapisanych świec','szt.'))])
    html+=table([{'Świeca':time_text(b.get('time')),'Otwarcie':number_text(b.get('open')),
        'Maksimum':number_text(b.get('high')),'Minimum':number_text(b.get('low')),
        'Zamknięcie':number_text(b.get('close')),'Wolumen':number_text(b.get('volume'),digits=0),
        'Stan':b.get('status','—')} for b in session.get('candles',[])])
    html+='<details><summary>Odczyty kontrolne sesji</summary><pre>'+escape(json.dumps(session.get('observations',[]),ensure_ascii=False,indent=2))+'</pre></details>'
    html+='<h4>Źródła i fakty przyjęte do oceny</h4>'
    sources={x['id']:x for x in ctx.get('sources',[])}
    for fact in a.get('context',[]):
        source=sources.get(fact['source_id'],{});url=str(source.get('url') or '')
        html+=paragraph(fact['fact'])+paragraph(str(source.get('title') or '')+' · publikacja: '+time_text(source.get('published_at')),'ki-top5-note')
        try:safe_url=urlsplit(url).scheme in ('https','http') and bool(urlsplit(url).netloc)
        except ValueError:safe_url=False
        if safe_url:
            html+='<a href="'+escape(url,quote=True)+'" target="_blank" rel="noopener noreferrer">Otwórz źródło</a>'
    if not a.get('context'):html+=paragraph('Przyczyna ruchu nieustalona; brak przyjętego faktu źródłowego.','ki-top5-note')
    for key,title in (('risks','Co osłabia ocenę'),('missing','Brakujące dane')):
        if a.get(key):
            html+='<h4>'+title+'</h4>'+''.join(paragraph(x) for x in a[key])
    bg=m.get('company_background') or {};fund=bg.get('fundamentals') or {};financial=fund.get('summary') or {}
    html+='<h4>Zapisane fundamenty i historia tej spółki</h4>'
    if fund.get('status')=='ready' and financial:
        html+=paragraph('Alpha Vantage · kwartał do '+str(financial.get('period_end') or '—')+' · zapis: '+time_text(fund.get('cached_at')),'ki-top5-note')
        html+=table([{'Dane':label,'Wartość':number_text(financial.get(key),'USD',2)} for key,label in (
            ('net_income','Wynik netto kwartału'),('cash','Gotówka'),('equity','Kapitał własny'),
            ('operating_cashflow','Przepływy operacyjne z czterech kwartałów'))])
    else:html+=paragraph('Brak kompletnego zapisanego pakietu finansowego.','ki-top5-note')
    history=bg.get('daily_history') or {}
    html+=paragraph('Historia dzienna: '+str(history.get('sample_count',0))+' sesji · '+str(history.get('period_from') or '—')+' → '+str(history.get('period_to') or '—'),'ki-top5-note')
    for horizon,stats in (bg.get('own_signal_outcomes') or {}).get('groups',{}).items():
        html+=paragraph(str(horizon)+' · obliczono: '+str(stats.get('computed',0))+' · średnia zmiana ceny: '+number_text(stats.get('mean_price_change_pct'),'%',2),'ki-top5-note')
    return html+'</details>'


def cards_html(api,cards,now):
    content=[]
    for position,card in enumerate(cards,1):
        s=card['snapshot'];m=card['manifest'];a=card['analysis'];currency=s.get('currency') or ''
        change=(s.get('price_matrix') or {}).get('change_pct');up=api.finite_number(change) and change>0
        plan=m.get('trade_plan') or {};levels=level_values({'levels':{'plan':plan}})
        html='<article class="ki-top5-card '+('up' if up else 'down')+'"><header><span>'+str(position)+'. '+escape(card['ticker'])+'</span><b>'+('WZROST' if up else 'SPADEK')+'</b></header>'
        html+=paragraph(s.get('company_name') or card['ticker'],'ki-top5-note')
        if card.get('orchestration'):
            html+=paragraph(card['orchestration']['role_label'],'ki-top5-preliminary')
        if m.get('review_stage')=='PRELIMINARY':
            html+=paragraph('WSTĘPNA OCENA · '+str(s['price_matrix']['consecutive_reads'])+'/3 potwierdzeń w chwili oceny.','ki-top5-preliminary')
        html+='<div class="ki-top5-price">'+escape(number_text(s.get('price'),currency))+'</div>'
        html+=paragraph('Od stałej bazy: '+number_text(change,'%',2)+' · '+('GPW' if card['ticker'].endswith('.WA') else 'USA'))
        html+=paragraph('Cena i analiza dotyczą odczytu: '+time_text(s.get('acquired_at')),'ki-top5-note')
        html+=paragraph('AI zakończono: '+time_text(card.get('review_at'))+' · aktualność najpóźniej do '+time_text(card['valid_until']),'ki-top5-note')
        narrative=(card.get('evidence_review') or {}).get('narrative')
        if narrative:html+=company_narrative.html(narrative)
        else:
            html+='<h4>Werdykt AI · dlaczego obserwować</h4>'+paragraph(a['final_review']['explanation'])
            if card.get('evidence_review'):html+=paragraph('Wcześniejsza ocena: AI wybrało werdykt i dowody; opis składa KI.','ki-top5-note')
            html+='<h4>Co osłabia ocenę</h4>'+paragraph(a['assessment']['risk'])
        html+=market_intelligence.cards(s)
        for title,text in scenario_text(m.get('scenario_plan') or {},now):html+='<h4>'+title+'</h4>'+paragraph(text)
        colors={'Wsparcie':'support','Opór':'resistance','SL':'sl','TP1':'tp','TP2':'tp'}
        html+='<dl class="ki-top5-levels">'+''.join('<div class="'+colors[label]+'"><dt>'+label+'</dt><dd>'+escape(number_text(value,currency))+'</dd></div>' for label,value in levels.items())+'</dl>'
        if plan.get('status')=='INDICATIVE':html+=paragraph('Potencjał/ryzyko do TP1: '+number_text(plan.get('rr1'),digits=2)+' · poziomy techniczne od ceny z oceny.','ki-top5-note')
        else:html+=paragraph('SL/TP: '+str(plan.get('reason') or 'Brak kompletu danych.'),'ki-top5-note')
        html+=paragraph('Punktacja automatu: '+number_text(card.get('score'),digits=0)+' / 100 · '+api.activity_summary(s,card['context'].get('previous_snapshot')),'ki-top5-note')
        html+=full_html(api,card,now)+'</article>';content.append(html)
    return '''<style>
    .ki-top5-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
    .ki-top5-card{box-sizing:border-box;min-width:0;background:#14202d;color:#edf2f7;border:1px solid #53677e;border-top:5px solid #4ade80;border-radius:12px;padding:18px;overflow-wrap:anywhere}
    .ki-top5-card.down{border-top-color:#fb7185}.ki-top5-card header{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;font-size:1.25rem;font-weight:700}
    .ki-top5-card header b{font-size:.85rem;color:#a7f3d0}.ki-top5-card.down header b{color:#fecdd3}
    .ki-top5-card h4{font-size:1rem;margin:16px 0 6px;color:#edf2f7}.ki-top5-card p{font-size:1rem;line-height:1.55;margin:6px 0;white-space:pre-wrap}
    .ki-top5-card .ki-top5-note{font-size:.85rem;color:#c6d0dc}.ki-top5-price{font-size:1.6rem;font-weight:700;font-variant-numeric:tabular-nums;margin-top:10px}
    .ki-top5-card .ki-top5-preliminary{color:#fde68a;background:#423512;padding:10px;border-radius:6px;font-weight:600}
    .ki-top5-levels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:16px 0}
    .ki-top5-levels div{min-width:0;border-left:4px solid;padding:9px;border-radius:6px}.ki-top5-levels dt{font-size:.85rem}.ki-top5-levels dd{margin:4px 0 0;font-size:1.05rem;font-weight:700}
    .ki-top5-levels .support{background:#142b45;color:#bfdbfe;border-color:#60a5fa}.ki-top5-levels .resistance{background:#322047;color:#e9d5ff;border-color:#c084fc}
    .ki-top5-levels .sl{background:#4c1d24;color:#ffe4e6;border-color:#fb7185}.ki-top5-levels .tp{background:#143b2c;color:#dcfce7;border-color:#4ade80}
    .ki-top5-card summary{cursor:pointer;min-height:44px;box-sizing:border-box;padding:12px 0;font-weight:600}.ki-top5-full{border-top:1px solid #53677e;margin-top:12px}
    .ki-top5-table{max-width:100%;overflow-x:auto}.ki-top5-card table{border-collapse:collapse;width:100%;font-size:.9rem}.ki-top5-card th,.ki-top5-card td{border:1px solid #53677e;padding:8px;text-align:left;white-space:normal}
    .ki-top5-card pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#101820;color:#edf2f7;padding:10px;max-height:400px;overflow:auto}.ki-top5-card a{color:#93c5fd}
    @media(max-width:900px){.ki-top5-grid{grid-template-columns:minmax(0,1fr)}}
    @media(max-width:420px){.ki-top5-card{padding:12px}.ki-top5-price{font-size:1.35rem}}
    </style><div class="ki-top5-grid">'''+''.join(content)+'</div>'


def render(api,store,auto_refresh=True):
    import streamlit as st
    st.subheader(VIEW)
    st.caption('TOP 5: wyłącznie wzrosty z poprawną oceną AI i kompletnym technicznym planem SL/TP. Pozostałe obserwacje i ostrzeżenia spadkowe są pokazane osobno. Bez dodatkowych wywołań API.')
    market=st.radio('Rynek TOP 5',('Wszystkie','GPW','USA'),horizontal=True,key='top5_market')
    @st.fragment(run_every=60 if auto_refresh else None)
    def saved_view():
        st.button('Odśwież wybrane okazje',help='Czyta zapisane raporty i sprawdza ich aktualność; bez pobierania danych.')
        now=datetime.now(timezone.utc)
        try:view=collect(api,store,now,market)
        except sqlite3.Error:
            st.error('Nie udało się odczytać zapisanych ocen. Sprawdź diagnostykę bazy.');return
        st.caption('Odczyt panelu: '+time_text(now.isoformat())+' · '+str(len(view['cards']))+' / 5 spółek. Kolejność: zapisana punktacja automatu, potem świeżość danych.')
        st.caption('Cena, poziomy i AI mają wspólny czas odczytu. '+('Aktualność jest sprawdzana co minutę. ' if auto_refresh else 'Odświeżanie ręczne. ')
                   +'Nowe dane i analizy powstają według cyklu skanera.')
        if view['cards']:st.markdown(cards_html(api,view['cards'],now),unsafe_allow_html=True)
        else:st.info('Brak aktualnych wzrostów z kompletnym planem SL/TP. Wcześniejsze sygnały pozostają w obserwacjach poniżej i w „Końcowych ocenach AI”.')
        for bucket,title in (('rising_watch','Wzrosty do obserwacji · bez kompletnego planu'),('warnings','Ostrzeżenia spadkowe')):
            if view[bucket]:
                st.subheader(title);st.markdown(cards_html(api,view[bucket],now),unsafe_allow_html=True)
        if view['excluded']:
            with st.expander('Dlaczego lista jest krótsza'):
                for reason,count in view['excluded'].items():st.write(reason+': '+str(count))
    saved_view()
