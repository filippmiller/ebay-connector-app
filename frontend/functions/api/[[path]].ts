interface Env {
  API_PUBLIC_BASE_URL: string;
}

export const onRequest: PagesFunction<Env> = async ({ request, env }) => {
  const url = new URL(request.url);
  const upstreamBase = new URL(env.API_PUBLIC_BASE_URL);
  
  url.pathname = url.pathname.replace(/^\/api/, '');
  url.host = upstreamBase.host;
  url.protocol = upstreamBase.protocol;
  
  const headers = new Headers(request.headers);
  
  return fetch(url.toString(), {
    method: request.method,
    headers,
    body: request.body,
  });
};
