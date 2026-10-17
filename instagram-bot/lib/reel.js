import "./slides.js"; // registers the J4K/Noto fonts (side effect)
import { createCanvas } from "@napi-rs/canvas";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

export const REEL = { W: 1080, H: 1920, fps: 24, seconds: 12 };
const { W, H } = REEL;
const M = 90;
const HEAD = "J4KHead, J4KJPBold";
const BODY = "J4KBody, J4KJP";

const ZERO = {
  bg: "#0B0B0C", accent: "#FACC15", body: "#E6E8EB", gray: "#9AA0A6",
  ink: "#0B0B0C", handle: "@just4keepers_japan", wordmark: "ZERO",
};

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function wrap(ctx, text, maxW) {
  // CJK-aware: break between any characters when needed.
  const out = [];
  let line = "";
  for (const ch of String(text)) {
    if (ch === "\n") { out.push(line); line = ""; continue; }
    const test = line + ch;
    if (ctx.measureText(test).width > maxW && line) { out.push(line); line = ch; }
    else line = test;
  }
  if (line) out.push(line);
  return out;
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1 - x, 3)); // easeOutCubic
// Alpha + upward slide for an element that appears at `start` over `dur` seconds.
function appear(t, start, dur = 0.6) {
  const p = ease(clamp((t - start) / dur, 0, 1));
  return { a: p, dy: (1 - p) * 42 };
}

function drawGoalNet(ctx, x, y, w, h, color, alpha) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  const gap = 42;
  ctx.beginPath();
  for (let i = -h; i < w + h; i += gap) {
    ctx.moveTo(x + i, y); ctx.lineTo(x + i + h, y + h);
    ctx.moveTo(x + i, y + h); ctx.lineTo(x + i + h, y);
  }
  ctx.stroke();
  ctx.restore();
  ctx.save();
  ctx.globalAlpha = Math.min(1, alpha * 3.2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 10;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(x, y + h); ctx.lineTo(x, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + h);
  ctx.stroke();
  ctx.restore();
}

function drawGloveBadge(ctx, cx, cy, r) {
  ctx.save();
  ctx.fillStyle = ZERO.accent;
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
  const s = r * 1.15, x = cx - s / 2, y = cy - s / 2;
  ctx.fillStyle = ZERO.ink;
  const fw = s * 0.18, fg = s * 0.065;
  for (let i = 0; i < 4; i++) { roundRect(ctx, x + s * 0.12 + i * (fw + fg), y + s * 0.02, fw, s * 0.52, fw / 2); ctx.fill(); }
  roundRect(ctx, x + s * 0.08, y + s * 0.42, s * 0.84, s * 0.5, s * 0.16); ctx.fill();
  roundRect(ctx, x + s * 0.8, y + s * 0.5, s * 0.28, fw, fw / 2); ctx.fill();
  ctx.restore();
}

function spacedLatin(str) {
  return /[^\x00-\x7F]/.test(str) ? str : String(str).toUpperCase().split("").join(" ");
}

// Split a tip body into a lead sentence + up to 3 bullet points.
export function reelContent(tip) {
  const blocks = String(tip.body).split(/\n+/).map((s) => s.trim()).filter(Boolean);
  const bullets = [];
  let lead = "";
  for (const b of blocks) {
    if (/^[-*・]/.test(b)) bullets.push(b.replace(/^[-*・]\s*/, ""));
    else if (!lead) lead = b;
  }
  if (bullets.length === 0) {
    // No bullets — use sentences as points.
    for (const s of blocks.join(" ").split(/(?<=。)/).map((x) => x.trim()).filter(Boolean)) {
      if (s !== lead) bullets.push(s.replace(/。$/, ""));
    }
  }
  return {
    category: tip.category || "GK豆知識",
    title: tip.title || "",
    lead,
    bullets: bullets.slice(0, 3),
    question: (tip.question || "あなたはどう意識してる?").trim(),
  };
}

function drawFrame(ctx, c, t) {
  // Background.
  ctx.fillStyle = ZERO.bg;
  ctx.fillRect(0, 0, W, H);

  // Goal-net header (fades in first).
  const intro = appear(t, 0.0, 0.8);
  drawGoalNet(ctx, M, 150, W - M * 2, 300, ZERO.accent, 0.16 * intro.a);

  // ZERO wordmark.
  ctx.globalAlpha = intro.a;
  ctx.font = `bold 92px ${HEAD}`;
  ctx.fillStyle = ZERO.accent;
  ctx.textBaseline = "alphabetic";
  ctx.fillText("ZERO", M + 24, 300);
  ctx.globalAlpha = 1;

  // Glove badge + category.
  const cat = appear(t, 0.5, 0.6);
  ctx.globalAlpha = cat.a;
  drawGloveBadge(ctx, M + 44, 556 + cat.dy, 44);
  ctx.font = `bold 34px ${HEAD}`;
  ctx.fillStyle = ZERO.accent;
  ctx.textBaseline = "middle";
  ctx.fillText(spacedLatin(c.category), M + 108, 560 + cat.dy);
  ctx.textBaseline = "alphabetic";
  ctx.globalAlpha = 1;

  // Title.
  const title = appear(t, 0.9, 0.7);
  ctx.globalAlpha = title.a;
  ctx.font = `78px ${HEAD}`;
  ctx.fillStyle = "#FFFFFF";
  let y = 680 + title.dy;
  for (const ln of wrap(ctx, c.title, W - M * 2)) { y += 88; ctx.fillText(ln, M, y); }
  ctx.globalAlpha = 1;

  // Lead subtitle.
  if (c.lead) {
    const lead = appear(t, 1.6, 0.7);
    ctx.globalAlpha = lead.a;
    ctx.font = `40px ${BODY}`;
    ctx.fillStyle = ZERO.gray;
    y += 30 + lead.dy;
    for (const ln of wrap(ctx, c.lead, W - M * 2)) { y += 54; ctx.fillText(ln, M, y); }
    ctx.globalAlpha = 1;
  }

  // Bullets, revealed one by one.
  let by = Math.max(y + 70, 1120);
  c.bullets.forEach((b, i) => {
    const bl = appear(t, 2.6 + i * 1.1, 0.6);
    if (bl.a <= 0) return;
    ctx.globalAlpha = bl.a;
    const yy = by + bl.dy;
    ctx.fillStyle = ZERO.accent;
    ctx.beginPath(); ctx.arc(M + 14, yy - 14, 12, 0, Math.PI * 2); ctx.fill();
    ctx.font = `46px ${BODY}`;
    ctx.fillStyle = ZERO.body;
    const lines = wrap(ctx, b, W - M * 2 - 56);
    lines.forEach((ln, li) => ctx.fillText(ln, M + 56, yy + li * 56));
    by += 56 * lines.length + 46;
    ctx.globalAlpha = 1;
  });

  // CTA band (bottom).
  const cta = appear(t, 2.6 + c.bullets.length * 1.1 + 0.4, 0.6);
  ctx.globalAlpha = cta.a;
  const bandY = H - 360;
  ctx.fillStyle = ZERO.accent;
  roundRect(ctx, M, bandY, W - M * 2, 180, 28); ctx.fill();
  ctx.fillStyle = ZERO.ink;
  ctx.font = `bold 46px ${HEAD}`;
  ctx.textAlign = "center";
  ctx.fillText("コメントで教えて", W / 2, bandY + 74);
  ctx.font = `36px ${BODY}`;
  ctx.fillText("保存して練習前に見返そう", W / 2, bandY + 134);
  ctx.textAlign = "left";
  ctx.globalAlpha = 1;

  // Handle + progress bar.
  ctx.font = `30px ${BODY}`;
  ctx.fillStyle = ZERO.gray;
  ctx.fillText(ZERO.handle, M, H - 110);
  const prog = clamp(t / REEL.seconds, 0, 1);
  ctx.fillStyle = "rgba(255,255,255,0.14)";
  roundRect(ctx, M, H - 70, W - M * 2, 8, 4); ctx.fill();
  ctx.fillStyle = ZERO.accent;
  roundRect(ctx, M, H - 70, (W - M * 2) * prog, 8, 4); ctx.fill();
}

/**
 * Render all reel frames as PNGs into `outDir`.
 * @returns {Promise<{count:number, fps:number, W:number, H:number}>}
 */
export async function renderReelFrames(tip, outDir) {
  await mkdir(outDir, { recursive: true });
  const c = reelContent(tip);
  const total = REEL.fps * REEL.seconds;
  for (let f = 0; f < total; f++) {
    const canvas = createCanvas(W, H);
    const ctx = canvas.getContext("2d");
    drawFrame(ctx, c, f / REEL.fps);
    await writeFile(path.join(outDir, `f${String(f).padStart(4, "0")}.png`), canvas.toBuffer("image/png"));
  }
  return { count: total, fps: REEL.fps, W, H };
}
