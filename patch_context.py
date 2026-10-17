import io,shutil,datetime as dt,hashlib
from pathlib import Path

target = Path("KI_tradingagents_env/Lib/site-packages/tradingagents/agents/context.py")
if not target.is_file():
    raise SystemExit("BRAK context.py w env tradingagents")

original = target.read_bytes()
shutil.copy2(str(target), str(target)+".bak."+dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
s = original.decode("utf-8")
o = s

old = '''    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    # The labelled lines are read by the program, so they keep their English
    # label and value: a translated rating line leaves the reader prose to
    # search, where a negated rating ("not a Sell") reads as the call (#1435).
    return (
        f" Write your entire response in {lang}, except the labelled lines the format"
        f" asks for (the \\"**Rating**:\\" line, \\"FINAL TRANSACTION PROPOSAL:\\"):"
        f" keep their label and value in English, exactly as specified."
    )'''

new = '''    from tradingagents.dataflows.config import get_config
    _cfg = get_config()
    lang = _cfg.get("output_language", "English")
    _ki_contract = _cfg.get("ki_report_contract", "") or ""
    if lang.strip().lower() == "english":
        _base = ""
    else:
        # The labelled lines are read by the program, so they keep their English
        # label and value: a translated rating line leaves the reader prose to
        # search, where a negated rating ("not a Sell") reads as the call (#1435).
        _base = (
            f" Write your entire response in {lang}, except the labelled lines the format"
            f" asks for (the \\"**Rating**:\\" line, \\"FINAL TRANSACTION PROPOSAL:\\"):"
            f" keep their label and value in English, exactly as specified."
        )
    if _ki_contract:
        return (_base + "\\n\\n" + _ki_contract).strip()
    return _base'''

if old not in s:
    raise SystemExit("BRAK wzorca w context.py - patch nie pasuje")

s = s.replace(old, new, 1)
compile(s, str(target), "exec")
io.open(target, "w", encoding="utf-8").write(s)
print("SHA:", hashlib.sha256(o.encode()).hexdigest()[:12], "->", hashlib.sha256(s.encode()).hexdigest()[:12])
print("PATCH CONTEXT OK")
