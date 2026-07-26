const SIGNUP = "/newsletter/";

function retired() {
  return new Response(JSON.stringify({
    ok: false,
    error: "retired",
    signup_url: SIGNUP,
    message: "AI Edge sign-up is handled by the governed Jotform page."
  }), {
    status: 410,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}

export function onRequestGet() { return retired(); }
export function onRequestPost() { return retired(); }
