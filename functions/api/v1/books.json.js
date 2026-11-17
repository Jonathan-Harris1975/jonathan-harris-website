// Serve the legacy public books.json contract directly from canonical KDP D1.
// The tracked JSON file is a build artefact, not an authority between deployments.
import { onRequestGet as getD1Ebooks } from "./ebooks.json.js";

export async function onRequestGet(context) {
  const response = await getD1Ebooks(context);
  if (!response.ok) return response;
  const payload = await response.json();
  if (!Array.isArray(payload?.books)) {
    return Response.json({ error: "Canonical KDP catalogue unavailable." }, {
      status: 503, headers: { "Cache-Control": "no-store" }
    });
  }
  return Response.json(payload.books, {
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" }
  });
}
