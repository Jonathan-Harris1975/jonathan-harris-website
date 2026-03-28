export async function onRequest(context) {
  const assetResponse = await context.next();
  const headers = new Headers(assetResponse.headers);
  return new Response(assetResponse.body, {
    status: 404,
    statusText: 'Not Found',
    headers,
  });
}
