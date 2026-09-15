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

// A dropped file can be empty or corrupt (e.g. a 2-byte placeholder). Verify the
// bytes actually start with a known image signature before trying to post it, so
// one bad file is skipped instead of halting the whole queue.
function looksLikeImage(buf) {
  if (!buf || buf.length < 100) return false;
  const isPng = buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47;
  const isJpeg = buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff;
  const isWebp =
    buf[0] === 0x52 && buf[1] === 0x49 && buf[2] === 0x46 && buf[3] === 0x46 &&
    buf[8] === 0x57 && buf[9] === 0x45 && buf[10] === 0x42 && buf[11] === 0x50;
  return isPng || isJpeg || isWebp;
}

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

  // Pick the next candidate whose bytes are a real image; skip corrupt/empty files.
  let nextImage;
  let imageBuffer;
  let skipped = 0;
  for (const candidate of candidates) {
    const buf = await readFile(path.join(IMAGES_DIR, candidate));
    if (looksLikeImage(buf)) {
      nextImage = candidate;
      imageBuffer = buf;
      break;
    }
    console.warn(`Skipping ${candidate}: not a valid image file.`);
    skipped++;
  }

  if (!nextImage) {
    console.log("No valid images to post (all remaining files were skipped).");
    return;
  }

  const remaining = candidates.length - skipped - 1;
  console.log(`Next image: ${nextImage} (${remaining} more waiting after this)`);

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
