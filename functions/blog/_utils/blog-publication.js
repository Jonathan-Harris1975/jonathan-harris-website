const MANIFEST_PATH = "/blog/posts.json";
const WEEKLY_ARCHIVE_URL = "https://jonathan-harris.online/blog/weekly/";

function normaliseItems(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (payload && Array.isArray(payload.items)) {
    return payload.items;
  }
  return [];
}

export async function getPublicationState(request) {
  try {
    const manifestUrl = new URL(MANIFEST_PATH, request.url);
    const response = await fetch(manifestUrl.toString(), {
      headers: {
        Accept: "application/json"
      }
    });

    if (!response.ok) {
      return { hasItems: false, itemCount: 0 };
    }

    const payload = await response.json();
    const items = normaliseItems(payload).filter((item) => item && typeof item === "object");
    return {
      hasItems: items.length > 0,
      itemCount: items.length,
    };
  } catch {
    return { hasItems: false, itemCount: 0 };
  }
}

export function getWeeklyArchiveUrl() {
  return WEEKLY_ARCHIVE_URL;
}
