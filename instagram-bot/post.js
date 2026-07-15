import { readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { generateCaption, mediaTypeFor } from "./lib/caption.js";
import { publishImage } from "./lib/instagram.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const QUEUE_PATH = path.join(HERE, "content", "queue.json");
const IMAGES_DIR = path.join(HERE, "content", "images");

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

// Build the public raw.githubusercontent.com URL for a queued image so Meta can fetch it.
// Override with IMAGE_BASE_URL if you host images elsewhere.
function buildImageUrl(filename) {
  const explicitBase = process.env.IMAGE_BASE_URL;
  if (explicitBase) {
    return `${explicitBase.replace(/\/$/, "")}/${filename}`;
  }
  const repo = requireEnv("GITHUB_REPOSITORY"); // "owner/repo"
  const ref = process.env.GITHUB_REF_NAME || "main";
  return `https://raw.githubusercontent.com/${repo}/${ref}/instagram-bot/content/images/${filename}`;
}

async function main() {
  const igUserId = requireEnv("IG_USER_ID");
  const accessToken = requireEnv("IG_ACCESS_TOKEN");
  requireEnv("ANTHROPIC_API_KEY"); // used by lib/caption.js

  const queue = JSON.parse(await readFile(QUEUE_PATH, "utf8"));
  if (!Array.isArray(queue.posts)) {
    throw new Error("queue.json must have a top-level `posts` array.");
  }

  const next = queue.posts.find((p) => !p.posted);
  if (!next) {
    console.log("No unposted items left in the queue. Nothing to do.");
    return;
  }

  const imagePath = path.join(IMAGES_DIR, next.image);
  if (!existsSync(imagePath)) {
    throw new Error(`Image not found: ${imagePath}`);
  }

  console.log(`Next post: ${next.image}`);
  const imageBuffer = await readFile(imagePath);
  const mediaType = mediaTypeFor(next.image);

  console.log("Generating caption with Claude...");
  const caption = await generateCaption(imageBuffer, mediaType, next.context);
  console.log(`\n--- Caption ---\n${caption}\n---------------\n`);

  const imageUrl = buildImageUrl(next.image);
  console.log(`Publishing to Instagram (image: ${imageUrl})...`);
  const mediaId = await publishImage({ igUserId, accessToken, imageUrl, caption });
  console.log(`Published. Media ID: ${mediaId}`);

  // Record the result and persist the queue.
  next.posted = true;
  next.postedAt = new Date().toISOString();
  next.caption = caption;
  next.mediaId = mediaId;
  await writeFile(QUEUE_PATH, JSON.stringify(queue, null, 2) + "\n", "utf8");
  console.log("Queue updated.");
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
