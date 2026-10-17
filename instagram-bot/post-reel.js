import { readFile, writeFile, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { execSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { renderReelFrames, REEL } from "./lib/reel.js";
import { generateTip, tipCaption } from "./lib/tip-content.js";
import { publishReel } from "./lib/instagram.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATE_PATH = path.join(HERE, "content", "reel-state.json");
const REL_REELS = "content/reels"; // relative to instagram-bot
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

function buildUrl(repo, sha, relPath) {
  return `https://raw.githubusercontent.com/${repo}/${sha}/instagram-bot/${relPath}`;
}

function encodeMp4(framesDir, outPath, fps) {
  execFileSync("ffmpeg", [
    "-y",
    "-framerate", String(fps),
    "-i", path.join(framesDir, "f%04d.png"),
    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
    "-r", String(fps), "-c:a", "aac", "-shortest", "-movflags", "+faststart",
    outPath,
  ], { stdio: ["ignore", "pipe", "pipe"] });
}

async function main() {
  const igUserId = requireEnv("IG_USER_ID");
  const accessToken = requireEnv("IG_ACCESS_TOKEN");
  requireEnv("ANTHROPIC_API_KEY");
  const repo = requireEnv("GITHUB_REPOSITORY");

  const state = await readJson(STATE_PATH, { covered: [], last: null });
  if (!Array.isArray(state.covered)) state.covered = [];

  console.log("Generating a GK tip for the reel with Claude...");
  const tip = await generateTip(state.covered);
  console.log(`Reel tip: [${tip.category}] ${tip.title}`);
  const caption = tipCaption(tip);
  console.log(`\n--- Caption ---\n${caption}\n---------------\n`);

  const id = new Date().toISOString().slice(0, 10).replace(/-/g, "") + "-" + Math.random().toString(36).slice(2, 6);
  const framesDir = path.join(os.tmpdir(), `reel-${id}`);
  await renderReelFrames(tip, framesDir);

  if (DRY_RUN) {
    const previewDir = path.join(HERE, "preview-reel");
    await mkdir(previewDir, { recursive: true });
    encodeMp4(framesDir, path.join(previewDir, "dryrun.mp4"), REEL.fps);
    await rm(framesDir, { recursive: true, force: true });
    console.log("DRY RUN: encoded preview-reel/dryrun.mp4. Not posting.");
    return;
  }

  const relPath = `${REL_REELS}/${id}.mp4`;
  await mkdir(path.join(HERE, REL_REELS), { recursive: true });
  encodeMp4(framesDir, path.join(HERE, relPath), REEL.fps);
  await rm(framesDir, { recursive: true, force: true });

  const sha = commitPush(relPath, `chore(reel): add reel video "${tip.title}" [skip ci]`);
  if (!sha) throw new Error("Reel video commit produced no SHA.");

  const videoUrl = buildUrl(repo, sha, relPath);
  console.log(`Publishing reel (${videoUrl})...`);
  const mediaId = await publishReel({ igUserId, accessToken, videoUrl, caption });
  console.log(`Published reel. Media ID: ${mediaId}`);

  state.covered.push(tip.title);
  if (state.covered.length > 120) state.covered = state.covered.slice(-120);
  state.last = { category: tip.category, title: tip.title, video: relPath, mediaId, postedAt: new Date().toISOString() };
  await writeFile(STATE_PATH, JSON.stringify(state, null, 2) + "\n", "utf8");
  commitPush("content/reel-state.json", `chore(reel): record reel "${tip.title}" [skip ci]`);
  console.log("State updated.");
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
