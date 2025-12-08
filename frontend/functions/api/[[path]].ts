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

  // Backend has mixed route prefixes:
  // - /auth, /ebay, /orders, /messages, /offers, /migration, /ebay-accounts, /webhooks - NO /api prefix
  // - /api/grid, /api/grids, /api/admin, /api/orders, /api/transactions, etc. - WITH /api prefix
  // 
  // Routes WITH /api prefix: keep the path as-is
  // Routes WITHOUT /api prefix: strip /api from the path

  const pathWithoutApi = url.pathname.replace(/^\/api/, '') || '/';

  // Check if this is a route that expects /api prefix (newer routes)
  // Note: /grid/preferences lives at /grid (no /api). Do NOT force /api prefix for it.
  const apiPrefixRoutes = ['/api/grids', '/api/admin', '/api/orders', '/api/transactions',
    '/api/financials', '/api/inventory', '/api/offers', '/api/buying',
    '/api/listing', '/api/sq', '/api/shipping', '/api/timesheets', '/api/tasks',
    '/api/ai', '/api/accounting', '/api/ui-tweak'];
  const isGridPreferences = url.pathname.startsWith('/api/grid/preferences');
  const needsApiPrefix = !isGridPreferences && apiPrefixRoutes.some(route => url.pathname.startsWith(route));

  upstream.pathname = needsApiPrefix ? url.pathname : pathWithoutApi;
  upstream.search = url.search;

  const headers = new Headers(request.headers);
  headers.delete('host'); // avoid passing CF host upstream

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: 'follow',
    // Increase timeout for Cloudflare Functions (max 30s for free tier).
    // Gmail sync and other heavy admin operations can legitimately take
    // longer than 25s on the backend, so we push this close to the
    // platform limit.
    signal: AbortSignal.timeout(29000)
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
      path: url.pathname
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
