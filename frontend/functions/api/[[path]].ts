interface Env {
  API_PUBLIC_BASE_URL: string;
}

export const onRequest: PagesFunction<Env> = async ({ request, env }) => {
  const apiBase = env.API_PUBLIC_BASE_URL;
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
    redirect: 'follow'
  };
  
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = request.body;
  }
  
  return fetch(upstream.toString(), init);
};
