interface Env {
  API_PUBLIC_BASE_URL: string;
}

export const onRequest: PagesFunction<Env> = async ({ request, env }) => {
  // Handle CORS preflight
  if (request.method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '86400',
      },
    });
  }
  
  const apiBase = env.API_PUBLIC_BASE_URL;
  
  if (!apiBase) {
    return new Response(
      JSON.stringify({ error: 'API_PUBLIC_BASE_URL not configured' }),
      { 
        status: 500,
        headers: { 
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        }
      }
    );
  }
  
  const url = new URL(request.url);
  const upstream = new URL(apiBase);
  
  const strippedPath = url.pathname.replace(/^\/api/, '') || '/';
  upstream.pathname = strippedPath;
  upstream.search = url.search;
  
  const headers = new Headers(request.headers);
  headers.delete('host'); // avoid passing CF host upstream
  
  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: 'follow',
    // Increase timeout for Cloudflare Functions (max 30s for free tier)
    signal: AbortSignal.timeout(25000)
  };
  
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    // For POST/PUT/PATCH, we need to read the body
    const contentType = request.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      init.body = await request.text();
      headers.set('Content-Type', 'application/json');
    } else {
      init.body = await request.arrayBuffer();
    }
  }
  
  try {
    const response = await fetch(upstream.toString(), init);
    
    // Clone response to modify headers
    const responseHeaders = new Headers(response.headers);
    responseHeaders.set('Access-Control-Allow-Origin', url.origin);
    responseHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders
    });
  } catch (error: any) {
    const errorDetails = {
      url: upstream.toString(),
      method: request.method,
      error: error.message,
      errorName: error.name,
      apiBase: apiBase,
      path: strippedPath
    };
    
    console.error('[CF Proxy] Error proxying request:', errorDetails);
    
    return new Response(
      JSON.stringify({ 
        error: 'Backend request failed',
        message: error.message,
        details: errorDetails,
        troubleshooting: {
          check: 'Verify API_PUBLIC_BASE_URL is set in Cloudflare Pages environment variables',
          expectedFormat: 'https://your-backend-url.up.railway.app'
        }
      }),
      { 
        status: 502,
        headers: { 
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': url.origin
        }
      }
    );
  }
};
