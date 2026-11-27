import { readFile, writeFile, mkdir, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execSync, execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { generateLaunchCopy } from "./lib/launch-content.js";
import { looksLikeImage } from "./lib/images.js";
import { publishImage } from "./lib/instagram.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const QUEUE_DIR = path.join(HERE, "content", "launch-queue");
const REL_QUEUE = "content/launch-queue";
const POSTED_PATH = path.join(QUEUE_DIR, "posted.json");
const CONTEXT_PATH = path.join(QUEUE_DIR, "context.json"); // optional {file: "hint"}
const DRY_RUN = process.env.DRY_RUN === "true";

const IMAGE_EXTS = new Set([".jpg", ".jpeg", ".png", ".webp"]);
const MEDIA_TYPES = { ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp" };

function requireEnv(name) {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required environment variable: ${name}`);
  return v;
}

function git(cmd) {
  return execSync(`git ${cmd}`, { cwd: HERE, stdio: ["ignore", "pipe", "pipe"] }).toString().trim();
}

function commitPush(pathspec, message) {
  try { git(`config user.email "github-actions[bot]@users.noreply.github.com"`); } catch {}
  try { git(`config user.name "github-actions[bot]"`); } catch {}
  git(`add ${pathspec}`);
  try { git("diff --cached --quiet"); return null; } catch { /* staged */ }
  git(`commit -m ${JSON.stringify(message)}`);
  for (let i = 0; i < 4; i++) {
    try { git("push origin HEAD:main"); break; }
    catch (e) { if (i === 3) throw e; execSync("sleep " + 2 ** (i + 1)); }
  }
  return git("rev-parse HEAD");
}

async function readJson(p, fallback) {
  if (!existsSync(p)) return fallback;
  return JSON.parse(await readFile(p, "utf8"));
}

async function main() {
  const igUserId = requireEnv("IG_USER_ID");
  const accessToken = requireEnv("IG_ACCESS_TOKEN");
  requireEnv("ANTHROPIC_API_KEY");
  const repo = requireEnv("GITHUB_REPOSITORY");

  if (!existsSync(QUEUE_DIR)) {
    console.log("No launch-queue folder. Nothing to post.");
    return;
  }
  const postedFile = await readJson(POSTED_PATH, { posted: [] });
  if (!Array.isArray(postedFile.posted)) postedFile.posted = [];
  const postedNames = new Set(postedFile.posted.map((p) => p.image));
  const contextMap = await readJson(CONTEXT_PATH, {});

  const files = (await readdir(QUEUE_DIR))
    .filter((f) => IMAGE_EXTS.has(path.extname(f).toLowerCase()))
    .filter((f) => !postedNames.has(f))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));

  // Pick the next valid image.
  let name;
  let buffer;
  for (const f of files) {
    const buf = await readFile(path.join(QUEUE_DIR, f));
    if (looksLikeImage(buf)) { name = f; buffer = buf; break; }
    console.warn(`Skipping ${f}: not a valid image.`);
  }
  if (!name) {
    console.log("No new launch images queued. Add images to content/launch-queue/ to queue more.");
    return;
  }

  const ext = path.extname(name).toLowerCase();
  const mediaType = MEDIA_TYPES[ext] || "image/jpeg";
  console.log(`Next launch image: ${name}`);

  console.log("Generating launch caption with Claude (vision)...");
  const caption = await generateLaunchCopy(buffer, mediaType, contextMap[name]);
  console.log(`\n--- Caption ---\n${caption}\n---------------\n`);

  if (DRY_RUN) {
    console.log(`DRY RUN: would post ${name}. Not posting.`);
    return;
  }

  // Instagram needs JPEG/PNG. Convert webp to jpg and commit it so it has a public URL.
  let relImage = `${REL_QUEUE}/${name}`;
  let sha = process.env.GITHUB_SHA || "main";
  if (ext === ".webp") {
    const jpgName = name.replace(/\.webp$/i, ".jpg");
    const jpgAbs = path.join(QUEUE_DIR, jpgName);
    execFileSync("ffmpeg", ["-y", "-i", path.join(QUEUE_DIR, name), jpgAbs], { stdio: ["ignore", "pipe", "pipe"] });
    relImage = `${REL_QUEUE}/${jpgName}`;
    const newSha = commitPush(relImage, `chore(launch-queue): add jpg for ${name} [skip ci]`);
    if (newSha) sha = newSha;
  }

  const imageUrl = `https://raw.githubusercontent.com/${repo}/${sha}/instagram-bot/${encodeURI(relImage)}`;
  console.log(`Publishing launch image (${imageUrl})...`);
  const mediaId = await publishImage({ igUserId, accessToken, imageUrl, caption });
  console.log(`Published. Media ID: ${mediaId}`);

  postedFile.posted.push({ image: name, postedAt: new Date().toISOString(), caption, mediaId });
  await mkdir(QUEUE_DIR, { recursive: true });
  await writeFile(POSTED_PATH, JSON.stringify(postedFile, null, 2) + "\n", "utf8");
  commitPush(`${REL_QUEUE}/posted.json`, `chore(launch-queue): record post ${name} [skip ci]`);
  console.log("State updated.");
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
