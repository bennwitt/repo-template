import assert from 'node:assert/strict';
import {once} from 'node:events';
import {request} from 'node:http';
import * as z from 'zod/v4';
const resultSchema = z.object({id:z.string(),status:z.string(),era:z.string()});
import {test} from 'node:test';
import {mkdtemp, writeFile, readFile, rm, symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {Client, StreamableHTTPClientTransport} from '@modelcontextprotocol/client';
import {StdioClientTransport} from '@modelcontextprotocol/client/stdio';
import {httpServer, state} from './server.js';

for (const transport of ['stdio', 'http']) for (const mode of ['auto', 'legacy'] as const) {
  test(`${transport} ${mode}: schemas, results, errors and cleanup`, {timeout: 15_000}, async () => {
    const http = httpServer(); http.listen(0, '127.0.0.1'); await once(http, 'listening');
    const address = http.address(); assert(address && typeof address !== 'string');
    const url = `http://127.0.0.1:${address.port}/mcp`;
    const client = new Client({name:'test', version:'1'}, {versionNegotiation: {mode}});
    try {
      await client.connect(transport === 'stdio'
        ? new StdioClientTransport({command:process.execPath,args:['--import','tsx',resolve('server.ts')]})
        : new StreamableHTTPClientTransport(new URL(url)));
      assert.equal(client.getNegotiatedProtocolVersion(), mode === 'auto' ? '2026-07-28' : '2025-11-25');
      const tools = await client.listTools();
      assert.deepEqual(tools.tools.find(t=>t.name==='order_status')?.inputSchema.required, ['id']);
      assert(tools.tools.find(t=>t.name==='order_status')?.outputSchema);
      const result = await client.callTool({name:'order_status',arguments:{id:'A-1'}});
      assert.equal(resultSchema.parse(result.structuredContent).status,'shipped');
      assert.equal(resultSchema.parse(result.structuredContent).era,mode === 'auto' ? 'modern':'legacy');
      assert.equal((await client.callTool({name:'order_status',arguments:{id:'B-1'}})).isError,true);
      assert.equal((await client.callTool({name:'order_status',arguments:{id:3}})).isError,true);
      await assert.rejects(client.callTool({name:'missing',arguments:{}}));
    } finally {
      await client.close(); http.closeAllConnections(); await new Promise<void>(r=>http.close(()=>r()));
    }
  });
}

test('HTTP rejects hostile origins, paths and unauthorized calls; owners stay isolated', {timeout:15_000}, async () => {
  const http=httpServer(true);http.listen(0,'127.0.0.1');await once(http,'listening');
  const address=http.address();assert(address && typeof address!=='string');
  const url=`http://127.0.0.1:${address.port}/mcp`;
  try {
    assert.equal((await fetch(url+'/wrong')).status,404);
    assert.equal((await fetch(url,{headers:{Origin:'https://evil.example'}})).status,403);
    assert.equal(await new Promise<number | undefined>((resolve,reject)=>{
      const req=request(url,{headers:{Host:'evil.example'}},res=>{res.resume();resolve(res.statusCode);});
      req.on('error',reject);req.end();
    }),403);
    for (const token of ['', 'invalid','expired','wrong-audience','wrong-scope']) {
      const response=await fetch(url,{method:'POST',headers:token?{Authorization:`Bearer ${token}`}:{}});
      assert.equal(response.status,token==='wrong-scope'?403:401);
    }
    const client=new Client({name:'auth-test',version:'1'},{versionNegotiation:{mode:'auto'}});
    try {
      await client.connect(new StreamableHTTPClientTransport(new URL(url),{requestInit:{headers:{Authorization:'Bearer bob'}}}));
      assert.equal((await client.callTool({name:'order_status',arguments:{id:'A-1'}})).isError,true);
      assert.equal(resultSchema.parse((await client.callTool({name:'order_status',arguments:{id:'B-1'}})).structuredContent).status,'pending');
    } finally {await client.close();}
  } finally {http.closeAllConnections();await new Promise<void>(r=>http.close(()=>r()));}
});

test('HTTP timeout cancels server work', {timeout:10_000}, async () => {
  const http=httpServer();http.listen(0,'127.0.0.1');await once(http,'listening');
  const address=http.address();assert(address && typeof address!=='string');
  const client=new Client({name:'timeout-test',version:'1'},{versionNegotiation:{mode:'auto'}});
  try {
    await client.connect(new StreamableHTTPClientTransport(new URL(`http://127.0.0.1:${address.port}/mcp`)));
    const started=state.started;
    await assert.rejects(client.callTool({name:'slow',arguments:{}},{timeout:100}));
    assert.equal(state.started,started+1);
    for(let n=0;n<100 && state.running;n++) await new Promise(r=>setTimeout(r,10));
    assert.equal(state.running,false);
  } finally {await client.close();http.closeAllConnections();await new Promise<void>(r=>http.close(()=>r()));}
});

test('pinned codemod rewrites v1 but needs a separate modern entry point', {timeout:30_000}, async () => {
  const dir=await mkdtemp(join(tmpdir(),'mcp-migrate-'));
  try {
    await writeFile(join(dir,'package.json'),JSON.stringify({name:'migration-fixture',type:'module',dependencies:{'@modelcontextprotocol/sdk':'1.32.2',zod:'4.3.6'}}));
    await writeFile(join(dir,'server.ts'),`import {McpServer} from '@modelcontextprotocol/sdk/server/mcp.js';
import {StdioServerTransport} from '@modelcontextprotocol/sdk/server/stdio.js';
import {z} from 'zod';
const server = new McpServer({name:'example',version:'1'});
server.tool('add',{a:z.number(),b:z.number()},async({a,b})=>({content:[{type:'text',text:String(a+b)}]}));
await server.connect(new StdioServerTransport());`);
    execFileSync(resolve('node_modules/.bin/mcp-codemod'),['v1-to-v2',dir],{env:{...process.env,CI:'1'},stdio:'pipe'});
    const migrated=await readFile(join(dir,'server.ts'),'utf8');
    assert(migrated.includes('@modelcontextprotocol/server'));
    assert(migrated.includes('registerTool'));
    assert(migrated.includes('server.connect')); // migration alone remains legacy
    assert(!migrated.includes('serveStdio'));
    assert(!migrated.includes('@mcp-codemod-error'));
    const deps=JSON.parse(await readFile(join(dir,'package.json'),'utf8')).dependencies;
    assert(deps['@modelcontextprotocol/server']); assert(!deps['@modelcontextprotocol/sdk']);
    // Resolve only the fixture's locked packages: no install or network inside this test.
    const locked = JSON.parse(await readFile(resolve('package.json'), 'utf8'));
    await writeFile(join(dir, 'package.json'), JSON.stringify({...locked, name:'migration-fixture'}));
    await symlink(resolve('node_modules'), join(dir, 'node_modules'), 'dir');
    await writeFile(join(dir, 'tsconfig.json'), await readFile(resolve('tsconfig.json')));
    const compile = () => execFileSync(process.execPath,
      [resolve('node_modules/typescript/bin/tsc'), '--project', join(dir,'tsconfig.json')], {stdio:'pipe'});
    const exercise = async (filename: string, mode: 'auto' | 'legacy', version: string) => {
      const client = new Client({name:'migration-test',version:'1'}, {versionNegotiation:{mode}});
      try {
        await client.connect(new StdioClientTransport({command:process.execPath,
          args:['--import',resolve('node_modules/tsx/dist/loader.mjs'),join(dir,filename)]}));
        assert.equal(client.getNegotiatedProtocolVersion(),version);
        assert((await client.listTools()).tools.some(tool=>tool.name==='add'));
        const result = await client.callTool({name:'add',arguments:{a:2,b:3}});
        assert.deepEqual(result.content,[{type:'text',text:'5'}]);
      } finally {await client.close();}
    };
    compile();
    await exercise('server.ts','legacy','2025-11-25');
    // Adapt the actual codemod output to a per-request factory; keep its tool implementation.
    const modern = migrated
      .replace(/import \{\s*StdioServerTransport\s*\} from ['"][^'"]+['"];?/, '')
      .replace('const server =', 'function buildServer() { const server =')
      .replace(/await server\.connect\(new StdioServerTransport\(\)\);?/, 'return server; }\nawait serveStdio(buildServer);');
    await writeFile(join(dir,'modern.ts'), "import {serveStdio} from '@modelcontextprotocol/server/stdio';\n" + modern);
    compile();
    await exercise('modern.ts','auto','2026-07-28');
    await exercise('modern.ts','legacy','2025-11-25');
  } finally {await rm(dir,{recursive:true,force:true});}
});
