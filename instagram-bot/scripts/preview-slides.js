import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { renderSlides } from "../lib/slides.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "..", "preview-slides");

const plan = {
  slides: [
    {
      type: "cover",
      kicker: "GK COACHING",
      title: "How to Plan a Goalkeeper Training Session",
      subtitle: "A 5-step framework to connect the game to your training.",
    },
    {
      type: "content",
      heading: "Start with the right question",
      body:
        "A good session isn't a collection of drills. Don't start with \"What drill should I do today?\"\n\nStart with: \"What does my goalkeeper need from the game?\"\n\nThe framework:\nMATCH → PROBLEM → OUTCOME → DESIGN → REFLECT",
    },
    {
      type: "content",
      badge: "1",
      heading: "MATCH — Start with the game",
      body:
        "Before choosing a drill, look at the match and find situations that deserve attention.\n\n- Was the starting position appropriate?\n- Did they recognise the situation early?\n- Was the decision and execution right?\n\nGoal: understand what the goalkeeper needs next.",
    },
    {
      type: "content",
      badge: "2",
      heading: "PROBLEM — Identify the real problem",
      body:
        "\"Needs to improve crosses\" isn't enough. Ask why it broke down:\n\n- Positioning\n- Perception (reading the flight & pressure)\n- Decision-making (attack, hold, adjust)\n- Timing\n- Technique\n\nDifferent problems need different training.",
    },
    {
      type: "content",
      badge: "3",
      heading: "OUTCOME — Define what to improve",
      body:
        "Avoid objectives that are too broad.\n\nToo broad: \"Improve crosses.\"\n\nBetter: \"Improve recognising when to attack a cross vs. hold position, based on ball trajectory, pressure and space.\"\n\nA clear outcome lets you evaluate the session afterwards.",
    },
    {
      type: "content",
      badge: "4",
      heading: "DESIGN — Build the session",
      body:
        "Only now design the exercises. One progression:\n\n- Activation\n- Technical foundation\n- Decision-making\n- Game-realistic situation\n\nAdd complexity only when it represents the real problem — not for difficulty's sake.",
    },
    {
      type: "content",
      badge: "5",
      heading: "REFLECT — Evaluate what changed",
      body:
        "The session isn't over at the last drill.\n\n- What behaviours did you observe?\n- Did the goalkeeper show the target behaviour?\n- Was the limit technical, tactical, perceptual or physical?\n- What comes next?\n\nThis creates a continuous development cycle.",
    },
    {
      type: "content",
      heading: "Stop collecting drills. Build a system.",
      body:
        "Knowing hundreds of drills doesn't create better training. Ask instead:\n\n- Why this exercise?\n- Why this goalkeeper?\n- Why today?\n\nConnect: GAME → TRAINING → DEVELOPMENT.",
    },
    {
      type: "cta",
      kicker: "KEEPIX",
      title: "Coach with purpose",
      body: "Save this framework for your next session. Follow for more GK coaching insight.",
    },
  ],
};

await mkdir(OUT, { recursive: true });
const slides = await renderSlides(plan);
for (const s of slides) {
  await writeFile(path.join(OUT, s.name), s.buffer);
}
console.log(`Rendered ${slides.length} slides to ${OUT}`);
