"""Bounded child-process logs and read-only production quality diagnostics."""
import collections
import json
import logging
import logging.handlers
import threading
import time


class ProcessLog:
    def __init__(self,path,max_bytes=20*1024*1024,backups=5):
        self.logger=logging.Logger('KI.'+str(path))
        self.handler=logging.handlers.RotatingFileHandler(path,maxBytes=max_bytes,backupCount=backups,encoding='utf-8')
        fmt=logging.Formatter('%(asctime)sZ %(levelname)s %(message)s',datefmt='%Y-%m-%dT%H:%M:%S')
        fmt.converter=time.gmtime;self.handler.setFormatter(fmt);self.logger.addHandler(self.handler)
        if self.handler.stream.tell()>=max_bytes:self.handler.doRollover()
        self.thread=None

    def attach(self,stream,label):
        def consume():
            try:
                for raw in iter(lambda:stream.readline(65536),b''):
                    text=raw.decode('utf-8',errors='replace').rstrip('\r\n')
                    level=logging.ERROR if any(x in text.lower() for x in ('traceback','cycle error','"status":"error"','failed:')) else logging.WARNING if 'warning' in text.lower() else logging.INFO
                    self.logger.log(level,label+' '+text)
            finally:stream.close()
        self.thread=threading.Thread(target=consume,name='KI-log-'+label,daemon=True);self.thread.start()

    def close(self):
        if self.thread:self.thread.join(timeout=10)
        self.handler.close()


def quality_metrics(connection):
    """Return aggregate data only. json_extract avoids loading multi-MB contexts."""
    versions=collections.defaultdict(collections.Counter);issues=collections.Counter();filters=collections.Counter()
    tokens=collections.Counter();extract=collections.Counter()
    sql="""SELECT state, coalesce(json_extract(context,'$.analysis_manifest.version'),0),
           json_extract(result,'$.analysis.quality_issues'),json_extract(result,'$.provider.usage'),
           coalesce(json_extract(result,'$.ai_preflight.skip_reasons'),json_extract(context,'$.ai_preflight.skip_reasons')),
           json_extract(context,'$.extract_diagnostics.status') FROM analysis_jobs"""
    for state,version,raw_issues,raw_usage,raw_filters,status in connection.execute(sql):
        versions[str(version)][state]+=1
        for item in json.loads(raw_issues or '[]'):issues[item.split(':',1)[0]]+=1
        for item in json.loads(raw_filters or '[]'):filters[item]+=1
        for key,value in json.loads(raw_usage or '{}').items():
            if isinstance(value,int) and not isinstance(value,bool):tokens[key]+=value
        if status:extract[status]+=1
    usage_count=connection.execute("SELECT count(*) FROM analysis_jobs WHERE json_type(result,'$.provider.usage.total_tokens')='integer'").fetchone()[0]
    sizes=connection.execute('SELECT count(*),coalesce(sum(length(context)),0),coalesce(max(length(context)),0) FROM analysis_jobs').fetchone()
    credits=collections.Counter();credit_records=collections.Counter()
    for search_usage,extract_usage in connection.execute("SELECT json_extract(raw_response,'$.usage'),json_extract(raw_response,'$.extract_diagnostics.usage') FROM research_requests"):
        for label,raw in (('Search',search_usage),('Extract',extract_usage)):
            usage=json.loads(raw or '{}');value=usage.get('credits') if isinstance(usage,dict) else None
            if isinstance(value,(int,float)) and not isinstance(value,bool):credits[label]+=value;credit_records[label]+=1
    return {'versions':[{'Wersja formatu':v,**dict(counts)} for v,counts in sorted(versions.items())],
            'issues':[{'Pole':k,'Usunięcia':v} for k,v in issues.most_common()],
            'filters':[{'Powód':k,'Zadania':v} for k,v in filters.most_common()],
            'tokens':dict(tokens),'usage_records':usage_count,'extract':dict(extract),
            'tavily_credits':dict(credits),'credit_records':dict(credit_records),
            'context_characters':sizes[1],'max_context_characters':sizes[2],'job_count':sizes[0]}


def latest_cycle_decisions(connection):
    row=connection.execute("SELECT id,started_at,payload FROM cycles WHERE finished_at IS NOT NULL ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row:return None,[]
    payload=json.loads(row[2]);rows=[]
    for item in payload.get('results',[]):
        matrix=item.get('price_matrix') or {}
        rows.append({'Ticker':item.get('ticker'),'Detekcja':item.get('status'),
                     'Matryca':matrix.get('state'),'Potwierdzenia':matrix.get('consecutive_reads'),
                     'Kwalifikacja':(item.get('opportunity') or {}).get('state'),
                     'Powód':'; '.join(map(str,item.get('reasons') or [])) or item.get('error') or item.get('error_code') or 'Brak dodatkowego powodu w zapisie'})
    return {'id':row[0],'started_at':row[1]},rows


def close_old_cycles(connection,cutoff,now):
    """Caller chooses a conservative cutoff; active/recent cycles remain untouched."""
    rows=connection.execute("SELECT id,payload FROM cycles WHERE status='RUNNING' AND started_at<?",(cutoff,)).fetchall()
    ids=[r[0] for r in rows]
    for cycle_id,raw in rows:
        payload=json.loads(raw);payload['recovery']={'at':now,'reason':'Historyczny osierocony cykl; czas zamknięcia oznacza porządkowanie zapisu.'}
        connection.execute("UPDATE cycles SET status='INTERRUPTED',finished_at=?,payload=? WHERE id=? AND status='RUNNING'",(now,json.dumps(payload,ensure_ascii=False),cycle_id))
    return ids
