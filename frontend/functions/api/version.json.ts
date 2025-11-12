export async function onRequest() {
  const branch = process.env.CF_PAGES_BRANCH || 'unknown';
  const commit = (process.env.CF_PAGES_COMMIT_SHA || '').slice(0, 7);
  const ts = new Date().toISOString();
  const body = { build: ts, branch, commit, ts, domain: 'ebay-connector-frontend.pages.dev' };
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' }
  });
}
