"""Tavily CLI backend for KI. Only receives verified Yahoo issuer identity.

No market discovery, synthetic data, API mocks or hidden REST fallback.
CLI is never invoked unless the owner selects it in KI settings and enables analysis.
"""
from __future__ import annotations

import ipaddress
import json
import hashlib
import os
import shutil
import subprocess
from urllib.parse import urlsplit
from datetime import datetime, timezone


class CLITransportError(RuntimeError):
    """A Tavily CLI subprocess did not return a verified complete result."""


def _safe_url(url):
    """Only public https URLs supplied by Tavily Search may be sent to Extract."""
    if not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        part = urlsplit(url)
        if part.scheme != "https" or not part.hostname or part.username or part.password:
            return False
        hostname = part.hostname.lower().strip(".")
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            return False
        if "." not in hostname:
            return False
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            return True
        return ip.is_global
    except (ValueError, TypeError):
        return False


def _launch(args, api_key):
    """Do not interpret a web result as shell syntax. No API call without a key."""
    if not api_key or not isinstance(api_key, str):
        raise CLITransportError("Tavily CLI: brak zatwierdzonego klucza API.")
    executable = shutil.which("tvly")
    if not executable:
        raise CLITransportError("Tavily CLI: nie znaleziono polecenia tvly w PATH. Nie wykonano zapytania.")
    env = dict(os.environ)
    env["TAVILY_API_KEY"] = api_key
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        done = subprocess.run([executable, *args, "--json"], check=False,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=env, shell=False, timeout=110)
    except subprocess.TimeoutExpired:
        raise CLITransportError("Tavily CLI: limit czasu. Koszt zapytania nieznany; nie ponawiać automatycznie.") from None
    except OSError:
        raise CLITransportError("Tavily CLI: nie można uruchomić procesu. Nie ustalono kosztu.") from None
    if done.returncode != 0:
        raise CLITransportError("Tavily CLI: błąd procesu (kod "+str(done.returncode)+"). Koszt nieznany; bez ponowienia.")
    if len(done.stdout) > 12_000_000:
        raise CLITransportError("Tavily CLI: przekroczony rozmiar danych. Koszt nieznany; bez ponowienia.")
    try:
        data = json.loads(done.stdout)
    except (ValueError, TypeError):
        raise CLITransportError("Tavily CLI: niepoprawny JSON odpowiedzi. Koszt nieznany; bez ponowienia.") from None
    if not isinstance(data, dict) or data.get("error"):
        raise CLITransportError("Tavily CLI: odpowiedź zawiera błąd. Koszt nieznany; bez ponowienia.")
    return data


def _date(raw):
    if not isinstance(raw, str) or not raw.strip():
        return "Brak daty", "MISSING"
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return raw, "AMBIGUOUS"
        return raw, "KNOWN"
    except ValueError:
        return raw, "INVALID"


def _search_arguments(request):
    # Never forward REST-only options or local source-whitelist restrictions.
    args = ["search", str(request["query"]), "--depth", "basic", "--max-results", str(request["max_results"])]
    if request.get("topic") in ("general", "news", "finance"):
        args.extend(["--topic", request["topic"]])
    if request.get("start_date"):
        args.extend(["--start-date", request["start_date"]])
    if request.get("end_date"):
        args.extend(["--end-date", request["end_date"]])
    return args


def collect(snapshot, api_key, plan, reference_time_utc, checkpoint=None):
    """Run real Search/Extract. Retain every returned Search result and failures.

    `plan` originates from KI's existing approved search plan (max two automatic,
    three manual). Each search is followed by one Extract for all safe unique URLs.
    Raw Extract text stays recorded; GPT receives the original extract as content.
    """
    calls = []
    hits = []
    extracted = []
    attempts = []
    last_ids = set()
    for scope, request in plan:
        if scope == "fallback" and last_ids:
            continue
        if not request.get("query"):
            raise CLITransportError("Tavily CLI: brak nazwy/tickera wyszukiwania.")
        start = datetime.now(timezone.utc).isoformat()
        search_response = _launch(_search_arguments(request), api_key)
        if not isinstance(search_response.get("results"), list):
            raise CLITransportError("Tavily CLI: Search nie zwrócił listy results.")
        original = search_response["results"]
        last_ids = {str(x.get("url")) for x in original if isinstance(x, dict)}
        safe_request = {key: request.get(key) for key in ("query", "topic", "start_date", "end_date", "max_results")}
        call_id = "SEARCH"+str(len(calls)+1)
        calls.append({"call_id":call_id,"scope":scope,"request":safe_request,
                      "response":search_response,"requested_at":start,
                      "received_at":datetime.now(timezone.utc).isoformat()})
        urls = []
        for number, raw in enumerate(original, 1):
            item = raw if isinstance(raw, dict) else {"malformed_result":raw}
            url = item.get("url")
            is_safe = _safe_url(url)
            hits.append({"hit_id":"H"+str(len(hits)+1),"call_id":call_id,"position":number,
                         "search_hit":item,"url_original":url,"technical_state":"VALID_URL" if is_safe else "UNSAFE_URL",
                         "extract_state":"NOT_ATTEMPTED"})
            if is_safe and url not in urls:
                urls.append(url)
        if checkpoint is not None:
            checkpoint({"backend":"CLI","status":"SEARCH_RECEIVED","search_calls":calls,
                        "search_hits":hits,"extract_calls":extracted,
                        "received_results":len(hits),"cost_observation":"UNKNOWN"})
        for offset in range(0, len(urls), 20):
            batch = urls[offset:offset+20]
            extracted_start = datetime.now(timezone.utc).isoformat()
            extract_response = _launch(["extract", *batch, "--extract-depth", "basic", "--format", "markdown"], api_key)
            if not isinstance(extract_response.get("results"), list) or not isinstance(extract_response.get("failed_results", []), list):
                raise CLITransportError("Tavily CLI: Extract bez prawidłowych results/failed_results.")
            extracted.append({"call_id":call_id,"requested_urls":batch,"response":extract_response,
                              "requested_at":extracted_start,"received_at":datetime.now(timezone.utc).isoformat()})
            if checkpoint is not None:
                checkpoint({"backend":"CLI","status":"EXTRACT_RECEIVED","search_calls":calls,
                            "search_hits":hits,"extract_calls":extracted,
                            "received_results":len(hits),"cost_observation":"UNKNOWN"})
        attempts.append({"scope":scope,"status":"DONE","request":safe_request,"received_results":len(original),
                         "accepted":len(original),"excluded":0,"credits":None,"requested_at":start,
                         "received_at":calls[-1]["received_at"]})
    links = {}
    failures = {}
    for call in extracted:
        for r in call["response"]["results"]:
            if isinstance(r, dict) and isinstance(r.get("url"),str):
                links[r["url"]] = r
        for r in call["response"].get("failed_results",[]):
            if isinstance(r, dict) and isinstance(r.get("url"),str):
                failures[r["url"]] = r
    sources = []
    for hit in hits:
        raw = hit["search_hit"]
        url = hit["url_original"]
        page = links.get(url) if isinstance(url, str) else None
        error = failures.get(url) if isinstance(url,str) else None
        raw_content = page.get("raw_content") if isinstance(page,dict) else None
        snippet = raw.get("content") if isinstance(raw.get("content"),str) else ""
        content = raw_content if isinstance(raw_content,str) and raw_content.strip() else snippet
        state = "SUCCESS" if isinstance(raw_content,str) and raw_content.strip() else (
            "EMPTY_CONTENT" if page is not None else "FAILED" if error else "UNSAFE_URL" if hit["technical_state"]!="VALID_URL" else "UNMATCHED_RESULT")
        hit["extract_state"] = state
        date, date_state = _date(raw.get("published_date"))
        # A missing date is never invented and never removes a source.
        sources.append({"id":"S"+str(len(sources)+1),"hit_id":hit["hit_id"],"url":url or "",
                        "title":str(raw.get("title") or ""),"content":content or "",
                        "published_at":date,"published_date_raw":raw.get("published_date"),"date_state":date_state,
                        "scope":scope_for_hit(hit, calls),"source_provenance":"tavily_cli",
                        "search_snippet":snippet,"extract_state":state,
                        "extract_error":str(error.get("error") or "") if error else None,
                        "content_hash":hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None,
                        "content_length":len(content),
                        "content_delivery_state":"COMPLETE" if state=="SUCCESS" else "METADATA_OR_SEARCH_ONLY"})
    # Full responses are archived as obtained. The GPT input can be larger than
    # expected; no content is silently truncated or selectively censored here.
    return {"backend":"CLI","sources":sources,"search_hits":hits,
            "search_calls":calls,"extract_calls":extracted,"attempts":attempts,
            "request":calls[0]["request"] if calls else None,"received_at":datetime.now(timezone.utc).isoformat(),
            "cutoff":reference_time_utc,"received_results":len(hits),"excluded":0,"rejected_sources":[],
            "undated_sources":[],"date_unverified_count":sum(1 for s in sources if s["date_state"]!="KNOWN"),
            "issuer_filter_version":2,"usage":{"reported_credits":None,"reports_with_credits":0,"calls":len(calls)+len(extracted)},
            "date_basis":"Brak daty nie oznacza braku wartości informacji. Wydawca i czas mogą być niepotwierdzone.",
            "research_version":5}


def scope_for_hit(hit, calls):
    return next((call["scope"] for call in calls if call["call_id"]==hit["call_id"]),"unknown")
