import { readFile, writeFile } from "node:fs/promises";
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { publishImage } from "./lib/instagram.js";

// One-off "launch" poster: publishes a single pre-made image (as-is) with a
// fixed, hand-written caption, from content/launch/post.json. Idempotent: once
// posted it records the media id and will not post again.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const POST_PATH = path.join(HERE, "content", "launch", "post.json");
const DRY_RUN = process.env.DRY_RUN === "true";

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
  try { git("diff --cached --quiet"); return; } catch { /* staged */ }
  git(`commit -m ${JSON.stringify(message)}`);
  for (let i = 0; i < 4; i++) {
    try { git("push origin HEAD:main"); break; }
    catch (e) { if (i === 3) throw e; execSync("sleep " + 2 ** (i + 1)); }
  }
}

async function main() {
  const igUserId = requireEnv("IG_USER_ID");
  const accessToken = requireEnv("IG_ACCESS_TOKEN");
  const repo = requireEnv("GITHUB_REPOSITORY");
  const sha = process.env.GITHUB_SHA || "main";

  const post = JSON.parse(await readFile(POST_PATH, "utf8"));
  if (post.posted) {
    console.log(`Already posted (media ${post.posted}). Nothing to do.`);
    return;
  }
  if (!post.image || !post.caption) throw new Error("post.json needs image and caption.");

  // Fail early if the image is missing from the checkout.
  await readFile(path.join(HERE, post.image));

  console.log(`Caption:\n${post.caption}\n`);
  const imageUrl = `https://raw.githubusercontent.com/${repo}/${sha}/instagram-bot/${post.image}`;
  console.log(`Image URL: ${imageUrl}`);

  if (DRY_RUN) {
    console.log("DRY RUN: validated image + caption. Not posting.");
    return;
  }

  const mediaId = await publishImage({ igUserId, accessToken, imageUrl, caption: post.caption });
  console.log(`Published. Media ID: ${mediaId}`);

  post.posted = mediaId;
  post.postedAt = new Date().toISOString();
  await writeFile(POST_PATH, JSON.stringify(post, null, 2) + "\n", "utf8");
  commitPush("content/launch/post.json", `chore(launch): record ZERO XTENSION PRO launch post [skip ci]`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
