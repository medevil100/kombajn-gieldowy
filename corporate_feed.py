"""Official Nasdaq corporate-action headlines, one bounded public GET/hour.

The RSS is a recent-items window, NOT a complete historical/event database.
An exact parenthesized watchlist ticker is required. No guessed event ratios/dates.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
import urllib.request
from urllib.parse import urlsplit, parse_qs, urlunsplit
import xml.etree.ElementTree as ET

import issuer_watch
from market_intelligence import stamp

URL='https://www.nasdaqtrader.com/rss.aspx?feed=currentheadlines&categorylist=105'
KEY='market_intelligence:nasdaq_feed'


def schedule(api, store, now):
    if not api.service_config(store.load_section('settings',{}))['pipeline_enabled']:
        return
    with store.transaction() as c:
        row=c.execute('SELECT payload,updated_at FROM runtime WHERE key=?',(KEY,)).fetchone()
        previous=api.load_payload(row[0]) if row else {}
        if row and (previous.get('state')=='QUEUED' or stamp(now)-stamp(row[1])<timedelta(hours=1)):
            return
        c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',(KEY,api.json_text({'state':'QUEUED','source':URL}),now))


def pending(api,store):
    with store.connection() as c:
        row=c.execute('SELECT payload FROM runtime WHERE key=?',(KEY,)).fetchone()
    return bool(row and api.load_payload(row[0]).get('state')=='QUEUED')


def fetch():
    request=urllib.request.Request(URL,headers={'User-Agent':'KI-private-reader/1.0','Accept':'application/rss+xml,text/xml'})
    with urllib.request.urlopen(request,timeout=10) as response:
        raw=response.read(1024*1024+1)
    if len(raw)>1024*1024 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Nieprawidłowy lub za duży kanał komunikatów.')
    return raw


def parse(raw,tickers,now):
    root=ET.fromstring(raw)
    if root.tag!='rss' or root.find('channel') is None:
        raise ValueError('Brak poprawnego kanału RSS.')
    result=[];at=stamp(now);watch=set(tickers)
    for item in root.findall('./channel/item')[:200]:
        title=item.findtext('title','').strip();url=item.findtext('link','').strip()
        try:
            published=parsedate_to_datetime(item.findtext('pubDate',''))
            parts=urlsplit(url);identifier=parse_qs(parts.query).get('id',[''])[0]
            if (parts.hostname!='www.nasdaqtrader.com' or parts.scheme not in ('http','https') or parts.username or parts.password
                or parts.path.lower()!='/tradernews.aspx' or not re.fullmatch(r'ECA\d{4}-\d+',identifier,re.I)
                or not published.tzinfo or not timedelta(0)<=at-published<=timedelta(days=7)):
                continue
            symbols=set(re.findall(r'\(([A-Z][A-Z0-9.\-]{0,11})\)',title)) & watch
            for ticker in sorted(symbols):
                result.append({'ticker':ticker,'title':title[:300],
                    'url':urlunsplit(('https',parts.netloc,parts.path,parts.query,'')),
                    'published_at':published.isoformat(),'observed_at':now,'source':'Nasdaq Corporate Actions RSS',
                    'status':'OFFICIAL_HEADLINE','scope':'Komunikat giełdy; stosunek wymiany i data skuteczności wymagają odczytu treści.'})
        except (TypeError,ValueError,OverflowError):
            continue
    return result


def process_once(api,store,now=None):
    iso=now or api.utc_now()
    if not api.service_config(store.load_section('settings',{}))['pipeline_enabled']:
        return False
    with store.transaction() as c:
        row=c.execute('SELECT payload FROM runtime WHERE key=?',(KEY,)).fetchone()
        if not row or api.load_payload(row[0]).get('state')!='QUEUED':
            return False
        # Crash leaves an explicit interrupted reservation until the next hourly poll.
        c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',(KEY,api.json_text({'state':'RUNNING','source':URL}),iso))
    try:
        raw=fetch();leads=parse(raw,store.load_section('tickers',[]),iso)
        cfg=api.service_config(store.load_section('settings',{}))
        with store.transaction() as c:
            for lead in leads:
                key='market_intelligence:official:'+lead['ticker']
                old=c.execute('SELECT payload FROM runtime WHERE key=?',(key,)).fetchone()
                known=api.load_payload(old[0]).get('sources',[]) if old else []
                by_url={source['url']:source for source in known}
                by_url[lead['url']]=lead
                c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',
                    (key,api.json_text({'sources':list(by_url.values())[-8:],'checked_at':iso}),iso))
                issuer_watch.notice(api,c,lead['ticker'],lead['url'],
                    'KOMUNIKAT GIEŁDY · '+lead['ticker']+'\n'+lead['title']+'\nPublikacja: '+lead['published_at']+
                    '\n'+lead['url']+'\nSprawdź treść: operacja na akcjach może zmieniać jednostkę ceny i historyczne SL/TP. To informacja, nie sygnał kupna.',iso,cfg['telegram_enabled'])
            c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',(KEY,api.json_text({'state':'COMPLETED','checked_at':iso,
                'matched':len(leads),'source':URL,'scope':'Ostatnie pozycje RSS Nasdaq; brak dopasowania nie wyklucza operacji.'}),iso))
    except Exception as exc:
        with store.transaction() as c:
            c.execute('INSERT OR REPLACE INTO runtime VALUES(?,?,?)',(KEY,api.json_text({'state':'FAILED','checked_at':iso,
                'error_type':type(exc).__name__,'source':URL}),iso))
    return True
