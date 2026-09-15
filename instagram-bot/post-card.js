import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { renderSlides } from "./lib/slides.js";
import { generateCaption, mediaTypeFor } from "./lib/caption.js";
import { generateTip, tipCaption } from "./lib/tip-content.js";
import { nextQueuedImage } from "./lib/images.js";
import { publishImage } from "./lib/instagram.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const IMAGES_DIR = path.join(HERE, "content", "images");
const POSTED_PATH = path.join(HERE, "content", "posted.json");
const CONTEXT_PATH = path.join(HERE, "content", "context.json");
const CARD_STATE_PATH = path.join(HERE, "content", "card-state.json");
const REL_TIP_SLIDES = "content/tip-slides"; // relative to instagram-bot
const DRY_RUN = process.env.DRY_RUN === "true";

function requireEnv(name) {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required environment variable: ${name}`);
  return v;
}

function git(cmd) {
  return execSync(`git ${cmd}`, { cwd: HERE, stdio: ["ignore", "pipe", "pipe"] }).toString().trim();
}

function commitPush(pathspecs, message) {
  try { git(`config user.email "github-actions[bot]@users.noreply.github.com"`); } catch {}
  try { git(`config user.name "github-actions[bot]"`); } catch {}
  git(`add ${pathspecs}`);
  try {
    git("diff --cached --quiet");
    return null; // nothing staged
  } catch { /* has staged changes */ }
  git(`commit -m ${JSON.stringify(message)}`);
  for (let i = 0; i < 4; i++) {
    try { git("push origin HEAD:main"); break; }
    catch (e) { if (i === 3) throw e; execSync("sleep " + 2 ** (i + 1)); }
  }
  return git("rev-parse HEAD");
}

async function readJson(filePath, fallback) {
  if (!existsSync(filePath)) return fallback;
  return JSON.parse(await readFile(filePath, "utf8"));
}

function buildImageUrl(repo, ref, relPath) {
  return `https://raw.githubusercontent.com/${repo}/${ref}/instagram-bot/${relPath}`;
}

// --- Path A: a queued product image exists → post it as a product promo. ---
async function postProductImage({ igUserId, accessToken, repo, image }) {
  const contextMap = await readJson(CONTEXT_PATH, {});
  console.log("Generating product caption with Claude (vision)...");
  const caption = await generateCaption(image.buffer, mediaTypeFor(image.name), contextMap[image.name]);
  console.log(`\n--- Caption ---\n${caption}\n---------------\n`);

  if (DRY_RUN) {
    console.log(`DRY RUN: would post product image ${image.name}. Not posting.`);
    return;
  }

  const ref = process.env.GITHUB_REF_NAME || "main";
  const imageUrl = buildImageUrl(repo, ref, `content/images/${encodeURIComponent(image.name)}`);
  console.log(`Publishing product image (${imageUrl})...`);
  const mediaId = await publishImage({ igUserId, accessToken, imageUrl, caption });
  console.log(`Published. Media ID: ${mediaId}`);

  const postedFile = await readJson(POSTED_PATH, { posted: [] });
  if (!Array.isArray(postedFile.posted)) postedFile.posted = [];
  postedFile.posted.push({ image: image.name, postedAt: new Date().toISOString(), caption, mediaId });
  await writeFile(POSTED_PATH, JSON.stringify(postedFile, null, 2) + "\n", "utf8");
  commitPush("content/posted.json", `chore(card): record product post ${image.name} [skip ci]`);
}

// --- Path B: no product image → generate & post an AI "GK tip" card. ---
async function postTipCard({ igUserId, accessToken, repo, state }) {
  console.log("No product image queued. Generating a GK tip card with Claude...");
  const tip = await generateTip(state.covered);
  console.log(`Tip: [${tip.category}] ${tip.title}`);
  const caption = tipCaption(tip);
  console.log(`\n--- Caption ---\n${caption}\n---------------\n`);

  const [slide] = await renderSlides({ slides: [{ type: "tip", ...tip }] }, "zero");

  if (DRY_RUN) {
    const previewDir = path.join(HERE, "preview-tip");
    await mkdir(previewDir, { recursive: true });
    await writeFile(path.join(previewDir, "dryrun.png"), slide.buffer);
    console.log(`DRY RUN: rendered tip to preview-tip/dryrun.png. Not posting.`);
    return;
  }

  const id = new Date().toISOString().slice(0, 10).replace(/-/g, "") + "-" + Math.random().toString(36).slice(2, 6);
  const relPath = `${REL_TIP_SLIDES}/${id}.png`;
  await mkdir(path.join(HERE, REL_TIP_SLIDES), { recursive: true });
  await writeFile(path.join(HERE, relPath), slide.buffer);
  const sha = commitPush(relPath, `chore(card): add tip slide "${tip.title}" [skip ci]`);
  if (!sha) throw new Error("Tip slide commit produced no SHA.");

  const imageUrl = buildImageUrl(repo, sha, relPath);
  console.log(`Publishing tip card (${imageUrl})...`);
  const mediaId = await publishImage({ igUserId, accessToken, imageUrl, caption });
  console.log(`Published. Media ID: ${mediaId}`);

  state.covered.push(tip.title);
  if (state.covered.length > 120) state.covered = state.covered.slice(-120);
  state.last = { category: tip.category, title: tip.title, image: relPath, mediaId, postedAt: new Date().toISOString() };
  await writeFile(CARD_STATE_PATH, JSON.stringify(state, null, 2) + "\n", "utf8");
  commitPush("content/card-state.json", `chore(card): record tip "${tip.title}" [skip ci]`);
}

async function main() {
  const igUserId = requireEnv("IG_USER_ID");
  const accessToken = requireEnv("IG_ACCESS_TOKEN");
  requireEnv("ANTHROPIC_API_KEY");
  const repo = requireEnv("GITHUB_REPOSITORY");

  const postedFile = await readJson(POSTED_PATH, { posted: [] });
  const postedNames = new Set((postedFile.posted || []).map((p) => p.image));
  const image = await nextQueuedImage(IMAGES_DIR, postedNames);

  const state = await readJson(CARD_STATE_PATH, { covered: [], last: null });
  if (!Array.isArray(state.covered)) state.covered = [];

  if (image) {
    console.log(`Product image queued: ${image.name}`);
    await postProductImage({ igUserId, accessToken, repo, image });
  } else {
    await postTipCard({ igUserId, accessToken, repo, state });
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
