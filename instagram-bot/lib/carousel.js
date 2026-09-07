const GRAPH_VERSION = "v21.0";
const GRAPH_BASE = `https://graph.facebook.com/${GRAPH_VERSION}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function graphPost(path, params) {
  const res = await fetch(`${GRAPH_BASE}/${path}`, {
    method: "POST",
    body: new URLSearchParams(params),
  });
  const data = await res.json();
  if (!res.ok || data.error) {
    const err = new Error(
      `Instagram Graph API error on ${path}: ${data.error ? JSON.stringify(data.error) : `HTTP ${res.status}`}`,
    );
    err.apiError = data.error;
    throw err;
  }
  return data;
}

async function graphGet(path, params) {
  const res = await fetch(`${GRAPH_BASE}/${path}?${new URLSearchParams(params)}`);
  const data = await res.json();
  if (!res.ok || data.error) {
    throw new Error(
      `Instagram Graph API error on ${path}: ${data.error ? JSON.stringify(data.error) : `HTTP ${res.status}`}`,
    );
  }
  return data;
}

async function waitUntilReady(containerId, accessToken, { attempts = 20, delayMs = 3000 } = {}) {
  for (let i = 0; i < attempts; i++) {
    const { status_code: status } = await graphGet(containerId, {
      fields: "status_code",
      access_token: accessToken,
    });
    if (status === "FINISHED") return;
    if (status === "ERROR" || status === "EXPIRED") {
      throw new Error(`Media container ${containerId} failed with status ${status}`);
    }
    await sleep(delayMs);
  }
  throw new Error(`Media container ${containerId} not ready after ${attempts} checks`);
}

/**
 * Publish a multi-image carousel to an Instagram Business/Creator account.
 *   1. create one item container per image (is_carousel_item)
 *   2. wait each FINISHED
 *   3. create a CAROUSEL parent container with children + caption
 *   4. wait FINISHED, then publish (retrying transient 9007)
 *
 * @returns {Promise<string>} published media id
 */
export async function publishCarousel({ igUserId, accessToken, imageUrls, caption }) {
  if (!Array.isArray(imageUrls) || imageUrls.length < 2 || imageUrls.length > 10) {
    throw new Error(`Carousel needs 2–10 images (got ${imageUrls?.length}).`);
  }

  // 1 + 2: item containers
  const childIds = [];
  for (const url of imageUrls) {
    const item = await graphPost(`${igUserId}/media`, {
      image_url: url,
      is_carousel_item: "true",
      access_token: accessToken,
    });
    await waitUntilReady(item.id, accessToken);
    childIds.push(item.id);
  }

  // 3: parent carousel container
  const parent = await graphPost(`${igUserId}/media`, {
    media_type: "CAROUSEL",
    children: childIds.join(","),
    caption,
    access_token: accessToken,
  });
  await waitUntilReady(parent.id, accessToken);

  // 4: publish with retry on "not ready yet" (9007)
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const published = await graphPost(`${igUserId}/media_publish`, {
        creation_id: parent.id,
        access_token: accessToken,
      });
      return published.id;
    } catch (err) {
      if (err.apiError?.code === 9007 && attempt < 4) {
        await sleep(5000);
        continue;
      }
      throw err;
    }
  }
}
