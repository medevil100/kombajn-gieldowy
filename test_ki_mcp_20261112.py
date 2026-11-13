"""Real stdio MCP and SQLite reads, only temporary data and no providers."""
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import KI
import ki_mcp_server as m
import ki_mcp_tunnel as tunnel
import test_ki_assistant_20261111 as fixtures


class MCPTests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp
    market_dump=fixtures.AssistantTests.market_dump

    def server(self):
        s=m.Server(Path(KI.__file__).parent,self.path)
        r=s.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}})
        self.assertEqual(r['result']['protocolVersion'],'2025-06-18')
        return s

    def call(self,s,name,args=None):
        return s.dispatch({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':name,'arguments':args or {}}})

    def test_all_seven_tools_preserve_database_and_never_use_network(self):
        before=self.market_dump();s=self.server()
        definitions=s.dispatch({'jsonrpc':'2.0','id':2,'method':'tools/list'})['result']['tools']
        self.assertEqual(len(definitions),7)
        for d in definitions:
            self.assertTrue(d['annotations']['readOnlyHint'])
            self.assertFalse(d['annotations']['openWorldHint'])
            args={'ticker':'HUMA'} if d['name'] in ('ki_company','ki_reviews','ki_saved_news','ki_daily_history') else {}
            if d['name']=='ki_daily_history':args['days']=364
            r=self.call(s,d['name'],args)['result']
            self.assertFalse(r['isError'],r)
            self.assertNotIn('must-not-leak',json.dumps(r))
        self.assertEqual(before,self.market_dump())

    def test_no_web_writes_shell_sql_or_credentials_tools(self):
        s=self.server()
        for name in ('web_search','answer','ki_web_search','shell','sql','load_service_keys','clear_thread'):
            self.assertEqual(self.call(s,name)['error']['code'],-32602)
        for args in ({'ticker':"HUMA';DELETE FROM portfolio;--"},{'ticker':'HUMA','sql':'SELECT *'},{'ticker':None}):
            self.assertTrue(self.call(s,'ki_company',args)['result']['isError'])

    def test_missing_company_is_missing_not_zero(self):
        r=self.call(self.server(),'ki_company',{'ticker':'UNKNOWN'})['result']['structuredContent']
        self.assertEqual(r['data']['snapshots_newest_first'],[])
        self.assertIsNone(r['data']['orchestrator'])

    def test_read_failure_never_exposes_database_error(self):
        s=self.server()
        with patch.object(s.assistant.Reader,'run',side_effect=RuntimeError('secret-path sk-do-not-print')):
            r=self.call(s,'ki_company',{'ticker':'HUMA'})
        self.assertTrue(r['result']['isError']);self.assertNotIn('secret',str(r))

    def test_protocol_notifications_invalid_requests_and_initialization(self):
        s=m.Server(Path(KI.__file__).parent,self.path)
        self.assertEqual(s.dispatch({'jsonrpc':'2.0','id':1,'method':'tools/list'})['error']['code'],-32000)
        self.assertIsNone(s.dispatch({'jsonrpc':'2.0','method':'notifications/initialized'}))
        self.assertEqual(s.dispatch([])['error']['code'],-32600)
        self.assertEqual(s.dispatch({'jsonrpc':'2.0','id':True,'method':'ping'})['error']['code'],-32600)
        s=self.server()
        self.assertEqual(s.dispatch({'jsonrpc':'2.0','id':3,'method':'ping'})['result'],{})

    def test_stdio_json_lines_actual_subprocess(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'ki_company','arguments':{'ticker':'HUMA'}}}]
        p=subprocess.run([sys.executable,'-B',str(Path(m.__file__)),'--project',str(Path(KI.__file__).parent),'--db',str(self.path)],
                         input='\n'.join(json.dumps(r) for r in requests)+'\n',capture_output=True,text=True,encoding='utf-8',timeout=35)
        self.assertEqual(p.returncode,0,p.stderr)
        rows=[json.loads(line) for line in p.stdout.splitlines()]
        self.assertEqual([r['id'] for r in rows],[1,2,3])
        self.assertEqual(rows[2]['result']['structuredContent']['data']['snapshots_newest_first'][0]['price'],1.4)

    def test_bad_json_and_oversized_lines_fail_without_execution(self):
        s=self.server();out=io.StringIO()
        s.serve(io.StringIO('not-json\n'+('a'*(m.MAX_LINE+1))+'\n'),out)
        rows=[json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([r['error']['code'] for r in rows],[-32700,-32600])

    def test_missing_database_is_not_created(self):
        missing=self.path.parent/'absent.sqlite3'
        with self.assertRaises(ValueError):m.Server(Path(KI.__file__).parent,missing)
        self.assertFalse(missing.exists())

    def test_tunnel_command_has_no_literal_secret_and_no_shell(self):
        with patch.dict('os.environ',{'TAVILY_API_KEY':'other-secret','CONTROL_PLANE_BASE_URL':'https://untrusted.test','MCP_SERVER_URL':'https://untrusted.test'}):
            args,env=tunnel.launch_parameters('/home/ubuntu/ki2-chatgpt-mcp','/home/ubuntu/ki2','fixture-secret','tunnel_'+'a'*32)
        self.assertNotIn('fixture-secret',str(args))
        self.assertEqual(env['CONTROL_PLANE_API_KEY'],'fixture-secret')
        self.assertNotIn('TAVILY_API_KEY',env);self.assertNotIn('MCP_SERVER_URL',env)
        self.assertNotIn('CONTROL_PLANE_BASE_URL',env)
        self.assertIn('127.0.0.1:8788',args)
        self.assertNotIn('sh -c',str(args))

    def test_invalid_tunnel_and_missing_key_are_rejected(self):
        for key,ident in (('', 'tunnel_'+'a'*32),('key','tunnel_...'),('key',';shell')):
            with self.assertRaises(ValueError):tunnel.launch_parameters('/tmp/bundle','/tmp/ki2',key,ident)

    def modern(self,method,**params):
        return {'jsonrpc':'2.0','id':4,'method':method,'params':{
            '_meta':{'io.modelcontextprotocol/protocolVersion':m.MODERN,
                     'io.modelcontextprotocol/clientCapabilities':{},
                     'io.modelcontextprotocol/clientInfo':{'name':'fixture','version':'1'}},**params}}

    def test_modern_discovery_list_and_call_without_initialize(self):
        s=m.Server(Path(KI.__file__).parent,self.path)
        discovery=s.dispatch(self.modern('server/discover'))['result']
        self.assertEqual(discovery['resultType'],'complete')
        self.assertIn(m.MODERN,discovery['supportedVersions'])
        self.assertEqual(discovery['_meta']['io.modelcontextprotocol/serverInfo']['name'],'ki-private-reader')
        listing=s.dispatch(self.modern('tools/list'))['result']
        self.assertEqual(listing['resultType'],'complete');self.assertEqual(len(listing['tools']),7)
        call=s.dispatch(self.modern('tools/call',name='ki_company',arguments={'ticker':'HUMA'}))['result']
        self.assertEqual(call['resultType'],'complete');self.assertFalse(call['isError'])

    def test_modern_request_is_self_contained_after_other_legacy_client(self):
        s=self.server()
        for name,args in (('ki_system_status',{}),('ki_company',{'ticker':'HUMA'})):
            result=s.dispatch(self.modern('tools/call',name=name,arguments=args))['result']
            self.assertFalse(result['isError']);self.assertEqual(result['resultType'],'complete')
        self.assertFalse(self.call(s,'ki_company',{'ticker':'HUMA'})['result']['isError'])

    def test_unknown_protocol_and_bad_meta_fail_explicitly(self):
        s=self.server();r=self.modern('tools/list')
        r['params']['_meta']['io.modelcontextprotocol/protocolVersion']='future'
        result=s.dispatch(r)['error'];self.assertEqual(result['code'],-32022)
        self.assertIn(m.MODERN,result['data']['supported'])
        r['params']['_meta']=[];self.assertEqual(s.dispatch(r)['error']['code'],-32602)

    def test_protocol_logs_exclude_arguments_and_private_data(self):
        from contextlib import redirect_stderr
        s=self.server();output=io.StringIO();log=io.StringIO()
        with redirect_stderr(log):
            s.serve(io.StringIO(json.dumps(self.modern('tools/call',name='ki_company',arguments={'ticker':'HUMA'}))+'\n'),output)
        self.assertNotIn('HUMA',log.getvalue());self.assertNotIn('1.4',log.getvalue())
        self.assertEqual(json.loads(log.getvalue())['status'],'ok')


if __name__=='__main__':unittest.main()
