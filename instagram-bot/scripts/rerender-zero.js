// One-off: re-render the current ZERO series from the plan stored in state,
// overwriting the committed PNGs in place. Used after a slide-style change.
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { renderSlides } from "../lib/slides.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATE_PATH = path.join(HERE, "..", "content", "zero-state.json");

const state = JSON.parse(await readFile(STATE_PATH, "utf8"));
if (!state.series) throw new Error("No active series in state.");

for (const part of state.series.parts) {
  const slides = await renderSlides({ slides: part.plan }, "zero");
  if (slides.length !== part.images.length) {
    throw new Error(`Slide count mismatch (${slides.length} vs ${part.images.length}).`);
  }
  for (let i = 0; i < slides.length; i++) {
    const abs = path.join(HERE, "..", part.images[i]);
    await writeFile(abs, slides[i].buffer);
    console.log("wrote", part.images[i]);
  }
}
console.log("Re-render complete.");
