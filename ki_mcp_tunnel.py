"""Private tunnel launcher. Credentials only in process environment, never argv."""
import json
import os
from pathlib import Path
import re
import shlex
import sys


def launch_parameters(directory,project,key,tunnel_id):
    if not re.fullmatch(r'tunnel_(?:[a-z0-9]{4}_)?[a-z0-9]{32}',tunnel_id):
        raise ValueError('Niepoprawny identyfikator tunelu.')
    if not isinstance(key,str) or not key.strip():raise ValueError('Brak klucza OpenAI dla tunelu.')
    directory,project=Path(directory).resolve(),Path(project).resolve()
    command=shlex.join([str(project/'.venv/bin/python'),'-I','-B',str(directory/'ki_mcp_server.py'),'--project',str(project)])
    args=[str(directory/'tunnel-client'),'run','--control-plane.tunnel-id',tunnel_id,
          '--control-plane.api-key','env:CONTROL_PLANE_API_KEY','--mcp.command',command,
          '--health.listen-addr','127.0.0.1:8788','--log.format','struct-text','--log.level','warn']
    # Do not inherit unrelated provider credentials or alternate tunnel routing.
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR')}
    env['CONTROL_PLANE_API_KEY']=key.strip()
    return args,env


def main():
    directory=Path(__file__).resolve().parent
    project=Path.home()/'ki2'
    config=json.loads((directory/'tunnel.json').read_text(encoding='utf-8'))
    sys.path.insert(0,str(project))
    import KI
    key_path=directory/'.runtime-key'
    key=key_path.read_text(encoding='utf-8').strip() if key_path.is_file() else KI.load_service_keys().get('OPENAI_API_KEY')
    args,env=launch_parameters(directory,project,key,config['tunnel_id'])
    os.execve(args[0],args,env)


if __name__=='__main__':
    try:main()
    except Exception:
        print('Tunel KI nie został uruchomiony. Sprawdź konfigurację, klucz runtime i uprawnienia Tunnels Read/Use.',file=sys.stderr)
        raise SystemExit(1)
