const GRAPH_VERSION = "v21.0";
const GRAPH_BASE = `https://graph.facebook.com/${GRAPH_VERSION}`;

async function graphPost(path, params) {
  const url = `${GRAPH_BASE}/${path}`;
  const body = new URLSearchParams(params);
  const res = await fetch(url, { method: "POST", body });
  const data = await res.json();
  if (!res.ok || data.error) {
    const msg = data.error ? JSON.stringify(data.error) : `HTTP ${res.status}`;
    throw new Error(`Instagram Graph API error on ${path}: ${msg}`);
  }
  return data;
}

/**
 * Publish a single image post to an Instagram Business/Creator account.
 *
 * Two-step flow required by the Graph API:
 *   1. create a media container from a publicly-reachable image URL
 *   2. publish that container
 *
 * @param {object}  opts
 * @param {string}  opts.igUserId      Instagram Business account ID.
 * @param {string}  opts.accessToken   Long-lived access token.
 * @param {string}  opts.imageUrl      Public URL of the image (must be reachable by Meta).
 * @param {string}  opts.caption       Caption text.
 * @returns {Promise<string>}          The published media ID.
 */
export async function publishImage({ igUserId, accessToken, imageUrl, caption }) {
  // Step 1: create the media container.
  const container = await graphPost(`${igUserId}/media`, {
    image_url: imageUrl,
    caption,
    access_token: accessToken,
  });

  // Step 2: publish it.
  const published = await graphPost(`${igUserId}/media_publish`, {
    creation_id: container.id,
    access_token: accessToken,
  });

  return published.id;
}
