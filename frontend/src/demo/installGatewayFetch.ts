// Add the gateway envelope without changing the strict V1.2 business DTOs.
// This is installed only by the demo entry point; it is not an authority check.
export function installGatewayFetch(): void {
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')
      || url.pathname.startsWith('/api/demo/') || ['GET', 'HEAD', 'OPTIONS'].includes(request.method)
      || request.headers.has('X-Operation-ID')) return original(request);
    let operation: string | undefined;
    if (request.headers.get('Content-Type')?.split(';', 1)[0].trim() === 'application/json') {
      try {
        const body = await request.clone().json();
        if (body && typeof body.operation_id === 'string') operation = body.operation_id;
      } catch { /* The backend owns malformed-body rejection. */ }
    }
    const headers = new Headers(request.headers);
    headers.set('X-Operation-ID', operation ?? crypto.randomUUID());
    return original(new Request(request, { headers }));
  };
}
