interface Env {
  API_PUBLIC_BASE_URL: string;
}

export const onRequest: PagesFunction<Env> = async ({ request, env }) => {
  // Log all requests for debugging
  console.log('[CF Proxy] Request received:', {
    method: request.method,
    url: request.url,
    pathname: new URL(request.url).pathname,
    hasApiBase: !!env.API_PUBLIC_BASE_URL
  });
  
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
    console.error('[CF Proxy] API_PUBLIC_BASE_URL not configured!');
    return new Response(
      JSON.stringify({ 
        error: 'API_PUBLIC_BASE_URL not configured',
        message: 'The API_PUBLIC_BASE_URL environment variable must be set in Cloudflare Pages settings'
      }),
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
  
  // Preserve full /api path so backend routes like /api/ebay/browse/search work
  // without being stripped to /ebay/browse/search (which causes 404).
  const preservedPath = url.pathname || '/';
  upstream.pathname = preservedPath;
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
    console.log('[CF Proxy] Proxying to:', upstream.toString());
    const response = await fetch(upstream.toString(), init);
    console.log('[CF Proxy] Response:', {
      status: response.status,
      statusText: response.statusText,
      url: upstream.toString()
    });
    
    // Clone ALL headers from backend response (including Set-Cookie, X-Request-ID, etc.)
    const responseHeaders = new Headers(response.headers);
    
    // Add CORS headers (but don't override existing ones)
    if (!responseHeaders.has('Access-Control-Allow-Origin')) {
      responseHeaders.set('Access-Control-Allow-Origin', url.origin);
    }
    if (!responseHeaders.has('Access-Control-Allow-Methods')) {
      responseHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    }
    if (!responseHeaders.has('Access-Control-Allow-Headers')) {
      responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    }
    if (!responseHeaders.has('Access-Control-Allow-Credentials')) {
      responseHeaders.set('Access-Control-Allow-Credentials', 'true');
    }
    
    // Log Set-Cookie headers for debugging
    const setCookieHeaders = responseHeaders.get('set-cookie');
    if (setCookieHeaders) {
      console.log('[CF Proxy] Set-Cookie header:', setCookieHeaders);
    }
    
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
      path: preservedPath
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

