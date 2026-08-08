const GRAPH_VERSION = "v21.0";
const GRAPH_BASE = `https://graph.facebook.com/${GRAPH_VERSION}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${GRAPH_BASE}/${path}?${query}`);
  const data = await res.json();
  if (!res.ok || data.error) {
    throw new Error(
      `Instagram Graph API error on ${path}: ${data.error ? JSON.stringify(data.error) : `HTTP ${res.status}`}`,
    );
  }
  return data;
}

// Wait until the freshly-created media container is FINISHED (ready to publish).
// Newly created image containers are briefly not publishable and return
// error 9007 ("Media ID is not available") if published too early.
async function waitUntilReady(containerId, accessToken, { attempts = 15, delayMs = 3000 } = {}) {
  for (let i = 0; i < attempts; i++) {
    const { status_code: status } = await graphGet(containerId, {
      fields: "status_code",
      access_token: accessToken,
    });
    if (status === "FINISHED") return;
    if (status === "ERROR" || status === "EXPIRED") {
      throw new Error(`Media container ${containerId} failed with status ${status}`);
    }
    await sleep(delayMs); // still IN_PROGRESS — wait and check again
  }
  throw new Error(`Media container ${containerId} was not ready after ${attempts} checks`);
}

/**
 * Publish a single image post to an Instagram Business/Creator account.
 *
 *   1. create a media container from a publicly-reachable image URL
 *   2. wait until the container is ready
 *   3. publish it (retrying if Instagram still reports it as not-ready)
 *
 * @returns {Promise<string>} the published media ID.
 */
export async function publishImage({ igUserId, accessToken, imageUrl, caption }) {
  const container = await graphPost(`${igUserId}/media`, {
    image_url: imageUrl,
    caption,
    access_token: accessToken,
  });

  await waitUntilReady(container.id, accessToken);

  // Publish, retrying the transient "not ready yet" error a few more times.
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const published = await graphPost(`${igUserId}/media_publish`, {
        creation_id: container.id,
        access_token: accessToken,
      });
      return published.id;
    } catch (err) {
      const notReady = err.apiError?.code === 9007;
      if (notReady && attempt < 4) {
        await sleep(5000);
        continue;
      }
      throw err;
    }
  }
}
