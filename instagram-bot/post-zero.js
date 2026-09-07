import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { renderSlides } from "./lib/slides.js";
import { generateSeries } from "./lib/zero-content.js";
import { publishCarousel } from "./lib/carousel.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATE_PATH = path.join(HERE, "content", "zero-state.json");
const SLIDES_ROOT = path.join(HERE, "content", "zero-slides"); // absolute
const REL_SLIDES = "content/zero-slides"; // relative to instagram-bot (for repo paths)

function requireEnv(name) {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required environment variable: ${name}`);
  return v;
}

function git(cmd) {
  return execSync(`git ${cmd}`, { cwd: HERE, stdio: ["ignore", "pipe", "pipe"] })
    .toString()
    .trim();
}

function gitConfigOnce() {
  try { git(`config user.email "github-actions[bot]@users.noreply.github.com"`); } catch {}
  try { git(`config user.name "github-actions[bot]"`); } catch {}
}

function commitPush(pathspecs, message) {
  gitConfigOnce();
  git(`add ${pathspecs}`);
  // Nothing staged? skip.
  try {
    git("diff --cached --quiet");
    return null; // no changes
  } catch {
    /* has staged changes */
  }
  git(`commit -m ${JSON.stringify(message)}`);
  for (let i = 0; i < 4; i++) {
    try {
      git("push origin HEAD:main");
      break;
    } catch (e) {
      if (i === 3) throw e;
      execSync("sleep " + 2 ** (i + 1));
    }
  }
  return git("rev-parse HEAD");
}

async function readState() {
  if (!existsSync(STATE_PATH)) return { covered: [], series: null };
  const s = JSON.parse(await readFile(STATE_PATH, "utf8"));
  if (!Array.isArray(s.covered)) s.covered = [];
  return s;
}

async function writeState(state) {
  await writeFile(STATE_PATH, JSON.stringify(state, null, 2) + "\n", "utf8");
}

function buildUrl(repo, sha, relPath) {
  return `https://raw.githubusercontent.com/${repo}/${sha}/instagram-bot/${relPath}`;
}

async function createSeries(state) {
  console.log("No active series. Generating a new ZERO series with Claude...");
  const plan = await generateSeries(state.covered);
  console.log(`Topic: ${plan.topic} (${plan.parts.length} parts)`);

  const id = new Date().toISOString().slice(0, 10).replace(/-/g, "") + "-" + Math.random().toString(36).slice(2, 6);
  const parts = [];
  for (let pi = 0; pi < plan.parts.length; pi++) {
    const part = plan.parts[pi];
    const relDir = `${REL_SLIDES}/${id}/p${pi + 1}`;
    const absDir = path.join(HERE, relDir);
    await mkdir(absDir, { recursive: true });
    const slides = await renderSlides({ slides: part.slides }, "zero");
    const images = [];
    for (const s of slides) {
      await writeFile(path.join(absDir, s.name), s.buffer);
      images.push(`${relDir}/${s.name}`);
    }
    parts.push({ caption: part.caption, plan: part.slides, images, posted: false, mediaId: null, postedAt: null });
  }

  // Commit the slide images to get a content-addressed SHA for image URLs.
  const sha = commitPush(`${REL_SLIDES}/${id}`, `chore(zero): add slides for "${plan.topic}" [skip ci]`);
  if (!sha) throw new Error("Slide commit produced no SHA.");

  state.series = { id, sha, topic: plan.topic, parts };
  state.covered.push(plan.topic);
  if (state.covered.length > 60) state.covered = state.covered.slice(-60);
  await writeState(state);
  commitPush("content/zero-state.json", `chore(zero): start series "${plan.topic}" [skip ci]`);
  return state.series;
}

async function main() {
  const igUserId = requireEnv("IG_USER_ID");
  const accessToken = requireEnv("IG_ACCESS_TOKEN");
  requireEnv("ANTHROPIC_API_KEY");
  const repo = requireEnv("GITHUB_REPOSITORY");

  const state = await readState();
  let series = state.series;
  const active = series && series.parts.some((p) => !p.posted);
  if (!active) series = await createSeries(state);

  const partIndex = series.parts.findIndex((p) => !p.posted);
  const part = series.parts[partIndex];
  const total = series.parts.length;
  console.log(`Posting "${series.topic}" — Part ${partIndex + 1}/${total} (${part.images.length} slides)`);

  if (process.env.DRY_RUN === "true") {
    console.log("DRY RUN: series generated and slides committed, but NOT posting.");
    console.log(`Caption:\n${part.caption}`);
    return;
  }

  const imageUrls = part.images.map((rel) => buildUrl(repo, series.sha, rel));
  const mediaId = await publishCarousel({ igUserId, accessToken, imageUrls, caption: part.caption });
  console.log(`Published carousel. Media ID: ${mediaId}`);

  part.posted = true;
  part.mediaId = mediaId;
  part.postedAt = new Date().toISOString();
  // When the whole series is done, clear it so the next run starts a new one.
  if (series.parts.every((p) => p.posted)) state.series = null;
  await writeState(state);
  commitPush("content/zero-state.json", `chore(zero): record part ${partIndex + 1}/${total} of "${series.topic}" [skip ci]`);
  console.log("State updated.");
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
