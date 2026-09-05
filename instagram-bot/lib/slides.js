import { createCanvas, GlobalFonts } from "@napi-rs/canvas";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

// Register fonts. Prefer bundled fonts in assets/fonts (for Japanese support if
// added later); otherwise fall back to system Liberation Sans, which is present
// on both this machine and the GitHub Actions ubuntu runner.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const BUNDLED = path.join(HERE, "..", "assets", "fonts");

function register(family, bundledFile, systemPath) {
  const bundled = path.join(BUNDLED, bundledFile);
  if (existsSync(bundled)) return GlobalFonts.registerFromPath(bundled, family);
  if (existsSync(systemPath)) return GlobalFonts.registerFromPath(systemPath, family);
  return false;
}

const LIB = "/usr/share/fonts/truetype/liberation";
register("J4KHead", "Head.ttf", `${LIB}/LiberationSans-Bold.ttf`);
register("J4KBody", "Body.ttf", `${LIB}/LiberationSans-Regular.ttf`);

// --- Design tokens (match the J4K site: black + yellow) ---
const W = 1080;
const H = 1350;
const M = 96; // outer margin
const BG = "#0B0B0C";
const YELLOW = "#FACC15";
const WHITE = "#FFFFFF";
const GRAY = "#9AA0A6";
const HEAD = "J4KHead";
const BODY = "J4KBody";
const HANDLE = "@just4keepers_japan";

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function wrapLines(ctx, text, maxWidth) {
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

// Draw a block of body text (supports blank-line paragraphs and "- " bullets).
function drawBody(ctx, text, x, y, maxWidth, { size = 40, lineHeight = 1.42, color = "#D6D8DB" } = {}) {
  ctx.font = `${size}px ${BODY}`;
  ctx.fillStyle = color;
  ctx.textBaseline = "alphabetic";
  const lh = size * lineHeight;
  let cursor = y;
  const paragraphs = text.split(/\n+/).map((p) => p.trim()).filter(Boolean);
  paragraphs.forEach((para, pi) => {
    const bullet = /^[-*]\s+/.test(para);
    const content = bullet ? para.replace(/^[-*]\s+/, "") : para;
    const indent = bullet ? 44 : 0;
    const lines = wrapLines(ctx, content, maxWidth - indent);
    lines.forEach((ln, li) => {
      cursor += lh;
      if (bullet && li === 0) {
        ctx.fillStyle = YELLOW;
        ctx.fillText("•", x, cursor);
        ctx.fillStyle = color;
      }
      ctx.fillText(ln, x + indent, cursor);
    });
    if (pi < paragraphs.length - 1) cursor += lh * 0.45; // paragraph gap
  });
  return cursor;
}

function measureBodyHeight(ctx, text, maxWidth, size, lineHeight = 1.42) {
  ctx.font = `${size}px ${BODY}`;
  const lh = size * lineHeight;
  let h = 0;
  const paragraphs = text.split(/\n+/).map((p) => p.trim()).filter(Boolean);
  paragraphs.forEach((para, pi) => {
    const bullet = /^[-*]\s+/.test(para);
    const content = bullet ? para.replace(/^[-*]\s+/, "") : para;
    const indent = bullet ? 44 : 0;
    h += wrapLines(ctx, content, maxWidth - indent).length * lh;
    if (pi < paragraphs.length - 1) h += lh * 0.45;
  });
  return h;
}

function footer(ctx, rightText, { onYellow = false } = {}) {
  const y = H - M;
  ctx.strokeStyle = onYellow ? "rgba(11,11,12,0.25)" : "rgba(255,255,255,0.14)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(M, y - 46);
  ctx.lineTo(W - M, y - 46);
  ctx.stroke();
  ctx.font = `24px ${BODY}`;
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = onYellow ? "rgba(11,11,12,0.7)" : GRAY;
  ctx.textAlign = "left";
  ctx.fillText(HANDLE, M, y);
  if (rightText) {
    ctx.textAlign = "right";
    ctx.fillStyle = onYellow ? "#0B0B0C" : YELLOW;
    ctx.font = `bold 24px ${HEAD}`;
    ctx.fillText(rightText, W - M, y);
  }
  ctx.textAlign = "left";
}

function drawCover(ctx, s) {
  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, W, H);

  // kicker
  const kicker = (s.kicker || "GK COACHING").toUpperCase();
  ctx.fillStyle = YELLOW;
  ctx.fillRect(M, 250, 64, 8);
  ctx.font = `bold 30px ${HEAD}`;
  ctx.fillStyle = YELLOW;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(spaced(kicker), M, 232);

  // title
  ctx.font = `92px ${HEAD}`;
  ctx.fillStyle = WHITE;
  const titleLines = wrapLines(ctx, (s.title || "").toUpperCase(), W - M * 2);
  let y = 380;
  const tlh = 96;
  for (const ln of titleLines) {
    y += tlh;
    ctx.fillText(ln, M, y);
  }

  // subtitle
  if (s.subtitle) {
    ctx.font = `40px ${BODY}`;
    ctx.fillStyle = GRAY;
    const subLines = wrapLines(ctx, s.subtitle, W - M * 2);
    y += 40;
    for (const ln of subLines) {
      y += 54;
      ctx.fillText(ln, M, y);
    }
  }

  footer(ctx, "SWIPE →");
}

function drawContent(ctx, s, index, total) {
  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, W, H);

  let y = 210;
  // badge
  if (s.badge) {
    ctx.fillStyle = YELLOW;
    roundRect(ctx, M, y, 96, 96, 22);
    ctx.fill();
    ctx.fillStyle = "#0B0B0C";
    ctx.font = `56px ${HEAD}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(s.badge), M + 48, y + 52);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    y += 150;
  } else {
    ctx.fillStyle = YELLOW;
    ctx.fillRect(M, y, 64, 8);
    y += 40;
  }

  // heading
  ctx.font = `58px ${HEAD}`;
  ctx.fillStyle = WHITE;
  const headLines = wrapLines(ctx, s.heading || "", W - M * 2);
  for (const ln of headLines) {
    y += 66;
    ctx.fillText(ln, M, y);
  }

  // body (auto-fit)
  y += 30;
  const maxWidth = W - M * 2;
  const available = H - M - 70 - y;
  let size = 40;
  for (const trySize of [40, 37, 34, 31, 28]) {
    if (measureBodyHeight(ctx, s.body || "", maxWidth, trySize) <= available) {
      size = trySize;
      break;
    }
    size = trySize;
  }
  drawBody(ctx, s.body || "", M, y, maxWidth, { size });

  footer(ctx, `${index} / ${total}`);
}

function drawCta(ctx, s) {
  ctx.fillStyle = YELLOW;
  ctx.fillRect(0, 0, W, H);

  ctx.fillStyle = "#0B0B0C";
  ctx.font = `bold 30px ${HEAD}`;
  ctx.fillText(spaced((s.kicker || "JUST4KEEPERS JAPAN").toUpperCase()), M, 250);

  ctx.font = `84px ${HEAD}`;
  const titleLines = wrapLines(ctx, (s.title || "").toUpperCase(), W - M * 2);
  let y = 320;
  for (const ln of titleLines) {
    y += 92;
    ctx.fillText(ln, M, y);
  }

  if (s.body) {
    y += 30;
    ctx.font = `40px ${BODY}`;
    ctx.fillStyle = "#1a1a1a";
    const lines = wrapLines(ctx, s.body, W - M * 2);
    for (const ln of lines) {
      y += 56;
      ctx.fillText(ln, M, y);
    }
  }

  // handle big
  ctx.font = `52px ${HEAD}`;
  ctx.fillStyle = "#0B0B0C";
  ctx.fillText(HANDLE, M, H - M - 90);

  footer(ctx, "FOLLOW", { onYellow: true });
}

function spaced(str) {
  return str.split("").join(" "); // light letter-spacing via thin spaces
}

function renderSlide(slide, index, total) {
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext("2d");
  if (slide.type === "cover") drawCover(ctx, slide);
  else if (slide.type === "cta") drawCta(ctx, slide);
  else drawContent(ctx, slide, index, total);
  return canvas.toBuffer("image/png");
}

/**
 * Render a slide plan to an array of { name, buffer } PNG slides.
 * plan.slides: [{type:'cover'|'content'|'cta', ...}]
 */
export function renderSlides(plan) {
  const slides = plan.slides || [];
  return slides.map((slide, i) => ({
    name: `${String(i + 1).padStart(2, "0")}.png`,
    buffer: renderSlide(slide, i + 1, slides.length),
  }));
}
