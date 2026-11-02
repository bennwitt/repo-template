import { createServer } from 'node:http';
import { pathToFileURL } from 'node:url';
import {
  McpServer, createMcpHandler, hostHeaderValidationResponse, originValidationResponse,
  localhostAllowedHostnames, localhostAllowedOrigins, requireBearerAuth,
  OAuthError, OAuthErrorCode,
  type McpRequestContext, type AuthInfo,
} from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { toNodeHandler } from '@modelcontextprotocol/node';
import * as z from 'zod/v4';

export const state = {running: false, started: 0};
export const orders = {'A-1': {owner: 'alice', status: 'shipped'}, 'B-1': {owner: 'bob', status: 'pending'}};
export function buildServer(ctx: McpRequestContext): McpServer {
  const server = new McpServer({name: 'orders', version: '1.0.0'});
  server.registerTool('order_status', {
    description: 'Read an owned order status; IDs look like A-1.',
    inputSchema: z.object({id: z.string()}),
    outputSchema: z.object({id: z.string(), status: z.string(), era: z.string()}),
    annotations: {readOnlyHint: true},
  }, async ({id}) => {
    const order = orders[id as keyof typeof orders];
    if (!order || order.owner !== (ctx.authInfo?.clientId ?? 'alice')) {
      return {isError: true, content: [{type: 'text', text: 'Order not found'}]};
    }
    const result = {id, status: order.status, era: ctx.era};
    return {content: [{type: 'text', text: JSON.stringify(result)}], structuredContent: result};
  });
  server.registerTool('slow', {inputSchema: z.object({})}, async (_, context) => {
    state.running = true; state.started++;
    const signal = context.mcpReq.signal;
    try {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 30_000);
        const abort = () => {clearTimeout(timer); reject(new Error('Cancelled'));};
        if (signal.aborted) abort(); else signal.addEventListener('abort', abort, {once: true});
      });
      return {content: [{type: 'text', text: 'done'}]};
    } finally {state.running = false;}
  });
  return server;
}

// Synthetic tokens only, to exercise middleware. Production uses signature/introspection verification.
export function httpHandler(protectedService = false) {
  const handler = createMcpHandler(buildServer);
  const gate = requireBearerAuth({
    verifier: {async verifyAccessToken(token: string): Promise<AuthInfo> {
      if (!['alice', 'bob', 'wrong-audience', 'expired', 'wrong-scope'].includes(token)) {
        throw new OAuthError(OAuthErrorCode.InvalidToken, 'Invalid token');
      }
      return {token, clientId: token, scopes: token === 'wrong-scope' ? [] : ['read'],
        expiresAt: token === 'expired' ? 1 : Math.floor(Date.now()/1000)+60,
        resource: new URL(token === 'wrong-audience' ? 'https://other.example/mcp' : 'https://orders.example/mcp')};
    }}, requiredScopes: ['read'], expectedResource: new URL('https://orders.example/mcp'),
  });
  return {async fetch(request: Request): Promise<Response> {
    if (new URL(request.url).pathname !== '/mcp') return new Response('Not found', {status: 404});
    const rejected = hostHeaderValidationResponse(request, localhostAllowedHostnames())
      ?? originValidationResponse(request, localhostAllowedOrigins());
    if (rejected) return rejected;
    if (!protectedService) return handler.fetch(request);
    const auth = await gate(request);
    return auth instanceof Response ? auth : handler.fetch(request, {authInfo: auth});
  }};
}
export function httpServer(protectedService = false) {
  return createServer(toNodeHandler(httpHandler(protectedService)));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await serveStdio(buildServer);
}
