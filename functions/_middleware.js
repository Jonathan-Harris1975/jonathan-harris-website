import { withFunctionSecurityHeaders } from "./_shared/security.js";

export async function onRequest(context) {
  const response = await context.next();
  return withFunctionSecurityHeaders(response);
}
