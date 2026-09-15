import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

export const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp"]);

// A dropped file can be empty or corrupt (e.g. a 2-byte placeholder). Verify the
// bytes actually start with a known image signature before trying to post it.
export function looksLikeImage(buf) {
  if (!buf || buf.length < 100) return false;
  const isPng = buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47;
  const isJpeg = buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff;
  const isWebp =
    buf[0] === 0x52 && buf[1] === 0x49 && buf[2] === 0x46 && buf[3] === 0x46 &&
    buf[8] === 0x57 && buf[9] === 0x45 && buf[10] === 0x42 && buf[11] === 0x50;
  return isPng || isJpeg || isWebp;
}

/**
 * Find the next queued, unposted, valid image in a folder (numeric name order).
 * @param {string} imagesDir      absolute path to the images folder
 * @param {Set<string>} postedNames  filenames already posted
 * @returns {Promise<{name:string, buffer:Buffer}|null>}
 */
export async function nextQueuedImage(imagesDir, postedNames) {
  let allFiles;
  try {
    allFiles = await readdir(imagesDir);
  } catch {
    return null; // folder missing
  }
  const candidates = allFiles
    .filter((f) => IMAGE_EXTENSIONS.has(path.extname(f).toLowerCase()))
    .filter((f) => !postedNames.has(f))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));

  for (const name of candidates) {
    const buffer = await readFile(path.join(imagesDir, name));
    if (looksLikeImage(buffer)) return { name, buffer };
    console.warn(`Skipping ${name}: not a valid image file.`);
  }
  return null;
}
