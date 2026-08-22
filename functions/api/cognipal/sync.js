import { buildSyncPayload, enforceVisitorRateLimits, readVisitorRequest, signedAimsRequest } from '../../_shared/cognipal.js';

export async function onRequestPost(context) {
  const input = await readVisitorRequest(context);
  if (input.error) return input.error;
  const limited = await enforceVisitorRateLimits(context, input.payload, 'sync');
  if (limited) return limited;
  return signedAimsRequest(context, '/comms-hub/intake/chat/sync', buildSyncPayload(input.payload));
}

export function onRequestGet() {
  return new Response('Method Not Allowed', { status: 405, headers: { allow: 'POST' } });
}
