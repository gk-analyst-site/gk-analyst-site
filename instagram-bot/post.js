import { readFile, writeFile, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { generateCaption, mediaTypeFor } from "./lib/caption.js";
import { publishImage } from "./lib/instagram.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const IMAGES_DIR = path.join(HERE, "content", "images");
const POSTED_PATH = path.join(HERE, "content", "posted.json");
const CONTEXT_PATH = path.join(HERE, "content", "context.json");

const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp"]);

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

// Build the public raw.githubusercontent.com URL for an image so Meta can fetch it.
// Override with IMAGE_BASE_URL if you host images elsewhere.
function buildImageUrl(filename) {
  const explicitBase = process.env.IMAGE_BASE_URL;
  if (explicitBase) {
    return `${explicitBase.replace(/\/$/, "")}/${encodeURIComponent(filename)}`;
  }
  const repo = requireEnv("GITHUB_REPOSITORY"); // "owner/repo"
  const ref = process.env.GITHUB_REF_NAME || "main";
  return `https://raw.githubusercontent.com/${repo}/${ref}/instagram-bot/content/images/${encodeURIComponent(filename)}`;
}

async function readJson(filePath, fallback) {
  if (!existsSync(filePath)) return fallback;
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function main() {
  const igUserId = requireEnv("IG_USER_ID");
  const accessToken = requireEnv("IG_ACCESS_TOKEN");
  requireEnv("ANTHROPIC_API_KEY"); // used by lib/caption.js

  // Load the record of already-posted images.
  const postedFile = await readJson(POSTED_PATH, { posted: [] });
  if (!Array.isArray(postedFile.posted)) postedFile.posted = [];
  const postedNames = new Set(postedFile.posted.map((p) => p.image));

  // Optional per-image hints: { "photo.jpg": "context text" }. Entirely optional.
  const contextMap = await readJson(CONTEXT_PATH, {});

  // Discover every image in the folder, and pick the next unposted one in name order.
  const allFiles = await readdir(IMAGES_DIR);
  const candidates = allFiles
    .filter((f) => IMAGE_EXTENSIONS.has(path.extname(f).toLowerCase()))
    .filter((f) => !postedNames.has(f))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));

  if (candidates.length === 0) {
    console.log("No new images to post. Add images to content/images/ to queue more.");
    return;
  }

  const nextImage = candidates[0];
  const remaining = candidates.length - 1;
  console.log(`Next image: ${nextImage} (${remaining} more waiting after this)`);

  const imagePath = path.join(IMAGES_DIR, nextImage);
  const imageBuffer = await readFile(imagePath);
  const mediaType = mediaTypeFor(nextImage);

  console.log("Generating caption with Claude...");
  const caption = await generateCaption(imageBuffer, mediaType, contextMap[nextImage]);
  console.log(`\n--- Caption ---\n${caption}\n---------------\n`);

  const imageUrl = buildImageUrl(nextImage);
  console.log(`Publishing to Instagram (image: ${imageUrl})...`);
  const mediaId = await publishImage({ igUserId, accessToken, imageUrl, caption });
  console.log(`Published. Media ID: ${mediaId}`);

  // Record the result so this image is not posted again.
  postedFile.posted.push({
    image: nextImage,
    postedAt: new Date().toISOString(),
    caption,
    mediaId,
  });
  await writeFile(POSTED_PATH, JSON.stringify(postedFile, null, 2) + "\n", "utf8");
  console.log("Recorded in posted.json.");
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
