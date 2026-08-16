import { buildInboundPayload, readVisitorRequest, signedAimsRequest } from '../../_shared/cognipal.js';

export async function onRequestPost(context) {
  const input = await readVisitorRequest(context, { requireMessage: true });
  if (input.error) return input.error;
  return signedAimsRequest(context, '/comms-hub/intake/chat', buildInboundPayload(input.payload));
}

export function onRequestGet() {
  return new Response('Method Not Allowed', { status: 405, headers: { allow: 'POST' } });
}
