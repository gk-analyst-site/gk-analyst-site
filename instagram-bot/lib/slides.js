import { createCanvas, GlobalFonts, loadImage } from "@napi-rs/canvas";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.join(HERE, "..", "assets");
const FONTS = path.join(ASSETS, "fonts");

function firstExisting(paths) {
  return paths.find((p) => p && existsSync(p));
}

// Latin fonts: bundled if present, else system Liberation Sans (on the CI runner too).
const LIB = "/usr/share/fonts/truetype/liberation";
GlobalFonts.registerFromPath(
  firstExisting([path.join(FONTS, "Head.ttf"), `${LIB}/LiberationSans-Bold.ttf`]),
  "J4KHead",
);
GlobalFonts.registerFromPath(
  firstExisting([path.join(FONTS, "Body.ttf"), `${LIB}/LiberationSans-Regular.ttf`]),
  "J4KBody",
);
// Japanese (workflow installs fonts-noto-cjk). Register regular + bold as fallbacks.
const jpReg = firstExisting([
  path.join(FONTS, "JP.otf"),
  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
  "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]);
const jpBold = firstExisting([
  path.join(FONTS, "JP-Bold.otf"),
  "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
  "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]);
if (jpReg) GlobalFonts.registerFromPath(jpReg, "J4KJP");
if (jpBold) GlobalFonts.registerFromPath(jpBold, "J4KJPBold");

const HEAD = jpBold ? "J4KHead, J4KJPBold" : "J4KHead";
const BODY = jpReg ? "J4KBody, J4KJP" : "J4KBody";
const WHITE = "#FFFFFF";

// --- Brand presets. Reusable for both accounts (future "mixing"). ---
export const BRANDS = {
  keepix: {
    bg: "#0B1512", accent: "#5FE3A1", body: "#D7DEDA", ink: "#08110D",
    ctaBodyInk: "#123227", gray: "#93A29B",
    handle: "@KEEPIX.GK_OFFICIAL", wordmark: "KEEPIX", logo: "keepix-logo.png",
  },
  zero: {
    bg: "#0B0B0C", accent: "#FACC15", body: "#D6D8DB", ink: "#0B0B0C",
    ctaBodyInk: "#1a1a1a", gray: "#9AA0A6",
    handle: "@just4keepers_japan", wordmark: "ZERO", logo: "zero-logo.png",
    logoChip: true,
  },
};

const W = 1080;
const H = 1350;
const M = 96;

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
  const out = [];
  for (const rawWord of String(text).split(/\s+/).filter(Boolean)) {
    let word = rawWord;
    while (ctx.measureText(word).width > maxWidth) {
      let i = 1;
      while (i < word.length && ctx.measureText(word.slice(0, i + 1)).width <= maxWidth) i++;
      out.push({ w: word.slice(0, i), space: false });
      word = word.slice(i);
    }
    out.push({ w: word, space: true });
  }
  const lines = [];
  let line = "";
  for (const tok of out) {
    const test = line ? `${line}${tok.space ? " " : ""}${tok.w}` : tok.w;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = tok.w;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function bodyMetrics(ctx, text, maxWidth, size, lineHeight = 1.5) {
  ctx.font = `${size}px ${BODY}`;
  const lh = size * lineHeight;
  const blocks = [];
  let total = 0;
  for (const [pi, para] of String(text).split(/\n+/).map((p) => p.trim()).filter(Boolean).entries()) {
    const bullet = /^[-*・]\s*/.test(para);
    const content = para.replace(/^[-*・]\s*/, "");
    const indent = bullet ? 44 : 0;
    const lines = wrapLines(ctx, content, maxWidth - indent);
    blocks.push({ lines, bullet, indent });
    total += lines.length * lh;
    if (pi > 0) total += lh * 0.4;
  }
  return { blocks, lh, height: total + (blocks.length - 1) * lh * 0.4 };
}

function drawBody(ctx, b, text, x, y, maxWidth, size) {
  const { blocks, lh } = bodyMetrics(ctx, text, maxWidth, size);
  ctx.font = `${size}px ${BODY}`;
  ctx.textBaseline = "alphabetic";
  let cursor = y;
  blocks.forEach((blk, i) => {
    if (i > 0) cursor += lh * 0.4;
    blk.lines.forEach((ln, li) => {
      cursor += lh;
      if (blk.bullet && li === 0) {
        ctx.fillStyle = b.accent;
        ctx.fillText("•", x, cursor);
      }
      ctx.fillStyle = b.body;
      ctx.fillText(ln, x + blk.indent, cursor);
    });
  });
  return cursor;
}

function drawLogo(ctx, b, logo, x, y, boxH, onAccent) {
  if (logo) {
    const ratio = (logo.width || 1) / (logo.height || 1);
    let h = boxH;
    let w = boxH * ratio;
    const maxW = 520;
    if (w > maxW) {
      w = maxW;
      h = w / ratio;
    }
    // Logo art is dark-on-transparent; on the dark cover it needs a white chip.
    if (b.logoChip && !onAccent) {
      const pad = 18;
      ctx.fillStyle = "#FFFFFF";
      roundRect(ctx, x, y, w + pad * 2, h + pad * 2, 18);
      ctx.fill();
      ctx.drawImage(logo, x + pad, y + pad, w, h);
    } else {
      ctx.drawImage(logo, x, y, w, h);
    }
    return;
  }
  ctx.font = `bold ${Math.round(boxH * 0.92)}px ${HEAD}`;
  ctx.fillStyle = onAccent ? b.ink : b.accent;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(b.wordmark, x, y + boxH * 0.9);
}

function footer(ctx, b, rightText, onAccent) {
  const y = H - M;
  ctx.strokeStyle = onAccent ? "rgba(0,0,0,0.22)" : "rgba(255,255,255,0.14)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(M, y - 46);
  ctx.lineTo(W - M, y - 46);
  ctx.stroke();
  ctx.textBaseline = "alphabetic";
  ctx.font = `24px ${BODY}`;
  ctx.fillStyle = onAccent ? "rgba(0,0,0,0.72)" : b.gray;
  ctx.textAlign = "left";
  ctx.fillText(b.handle, M, y);
  if (rightText) {
    ctx.textAlign = "right";
    ctx.fillStyle = onAccent ? b.ink : b.accent;
    ctx.font = `bold 24px ${HEAD}`;
    ctx.fillText(rightText, W - M, y);
  }
  ctx.textAlign = "left";
}

function drawCover(ctx, b, s, logo) {
  ctx.fillStyle = b.bg;
  ctx.fillRect(0, 0, W, H);
  drawLogo(ctx, b, logo, M, 150, 96, false);

  ctx.fillStyle = b.accent;
  ctx.fillRect(M, 372, 64, 8);
  ctx.font = `bold 30px ${HEAD}`;
  ctx.fillStyle = b.accent;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(spaced((s.kicker || "GK COACHING")), M, 354);

  ctx.font = `86px ${HEAD}`;
  ctx.fillStyle = WHITE;
  let y = 470;
  for (const ln of wrapLines(ctx, s.title || "", W - M * 2)) {
    y += 94;
    ctx.fillText(ln, M, y);
  }
  if (s.subtitle) {
    ctx.font = `40px ${BODY}`;
    ctx.fillStyle = b.gray;
    y += 30;
    for (const ln of wrapLines(ctx, s.subtitle, W - M * 2)) {
      y += 56;
      ctx.fillText(ln, M, y);
    }
  }
  footer(ctx, b, "SWIPE →", false);
}

function drawContent(ctx, b, s, index, total) {
  ctx.fillStyle = b.bg;
  ctx.fillRect(0, 0, W, H);

  let y = 210;
  if (s.badge) {
    ctx.fillStyle = b.accent;
    roundRect(ctx, M, y, 96, 96, 22);
    ctx.fill();
    ctx.fillStyle = b.ink;
    ctx.font = `54px ${HEAD}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(s.badge), M + 48, y + 52);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    y += 150;
  } else {
    ctx.fillStyle = b.accent;
    ctx.fillRect(M, y, 64, 8);
    y += 40;
  }

  ctx.font = `56px ${HEAD}`;
  ctx.fillStyle = WHITE;
  for (const ln of wrapLines(ctx, s.heading || "", W - M * 2)) {
    y += 64;
    ctx.fillText(ln, M, y);
  }

  y += 34;
  const maxWidth = W - M * 2;
  const available = H - M - 70 - y;
  let size = 40;
  for (const trySize of [40, 37, 34, 31, 28, 26]) {
    size = trySize;
    if (bodyMetrics(ctx, s.body || "", maxWidth, trySize).height <= available) break;
  }
  drawBody(ctx, b, s.body || "", M, y, maxWidth, size);
  footer(ctx, b, `${index} / ${total}`, false);
}

function drawCta(ctx, b, s, logo) {
  ctx.fillStyle = b.accent;
  ctx.fillRect(0, 0, W, H);
  drawLogo(ctx, b, logo, M, 150, 96, true);

  ctx.fillStyle = b.ink;
  ctx.font = `bold 30px ${HEAD}`;
  ctx.fillText(spaced((s.kicker || b.wordmark)), M, 360);

  ctx.font = `78px ${HEAD}`;
  let y = 420;
  for (const ln of wrapLines(ctx, s.title || "", W - M * 2)) {
    y += 88;
    ctx.fillText(ln, M, y);
  }
  if (s.body) {
    ctx.font = `40px ${BODY}`;
    ctx.fillStyle = b.ctaBodyInk;
    y += 30;
    for (const ln of wrapLines(ctx, s.body, W - M * 2)) {
      y += 56;
      ctx.fillText(ln, M, y);
    }
  }
  ctx.font = `46px ${HEAD}`;
  ctx.fillStyle = b.ink;
  ctx.fillText(b.handle, M, H - M - 90);
  footer(ctx, b, "FOLLOW", true);
}

function spaced(str) {
  // Latin gets letter-spacing; leave CJK alone (spacing looks bad on kana/kanji).
  return /[^\x00-\x7F]/.test(str) ? str : String(str).toUpperCase().split("").join(" ");
}

function renderSlide(b, slide, index, total, logo) {
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext("2d");
  if (slide.type === "cover") drawCover(ctx, b, slide, logo);
  else if (slide.type === "cta") drawCta(ctx, b, slide, logo);
  else drawContent(ctx, b, slide, index, total);
  return canvas.toBuffer("image/png");
}

/**
 * Render a slide plan to PNG slides.
 * @param {object} plan  { slides: [...] }
 * @param {string|object} brand  brand name ('keepix' | 'zero') or a brand config object
 * @returns {Promise<Array<{name:string, buffer:Buffer}>>}
 */
export async function renderSlides(plan, brand = "keepix") {
  const b = typeof brand === "string" ? BRANDS[brand] || BRANDS.keepix : brand;
  const logoPath = firstExisting([path.join(ASSETS, b.logo), path.join(ASSETS, "logo.png")]);
  const logo = logoPath ? await loadImage(logoPath) : null;
  const slides = plan.slides || [];
  return slides.map((slide, i) => ({
    name: `${String(i + 1).padStart(2, "0")}.png`,
    buffer: renderSlide(b, slide, i + 1, slides.length, logo),
  }));
}
