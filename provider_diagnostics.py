"""Bounded, redacted error details; never persist a complete provider body."""
import re
from tavily_cli_adapter import sanitize_cli_diagnostic


def openai_error_detail(body,key=None,request_id=None):
    error=body.get('error') if isinstance(body,dict) else None
    if not isinstance(error,dict):return ''
    parts=[]
    for field in ('type','code','param'):
        value=error.get(field)
        if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_\.\[\]-]{1,120}',value):parts.append(field+'='+value)
    message=error.get('message')
    if isinstance(message,str):
        message=sanitize_cli_diagnostic(message,[key] if key else [])
        message=re.sub(r'https?://\S+','[URL]',message)
        message=re.sub(r'<[^>]*>','',message)
        message=' '.join(message.split())[:500]
        if message:parts.append(message)
    if isinstance(request_id,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',request_id):parts.append('request_id='+request_id)
    detail=sanitize_cli_diagnostic(' | '.join(parts),[key] if key else [])
    return ': '+detail if detail else ''
