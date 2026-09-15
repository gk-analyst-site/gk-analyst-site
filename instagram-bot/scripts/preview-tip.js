import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { renderSlides } from "../lib/slides.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "..", "preview-tip");

const samples = [
  {
    type: "tip",
    category: "ポジショニング",
    title: "シュートは「角度を消す」で半分防げる",
    body:
      "前に出る目的は、ボールを奪うことだけではありません。相手に近づくほど、シューターから見えるゴールの面積が小さくなります。\n\n- 遠くにいるGK → ゴールが広く見える\n- 前に詰めたGK → 打つコースが狭く見える\n\n「奪えなくても、コースを消せば仕事」。この意識が無理な飛び込みを減らします。",
  },
  {
    type: "tip",
    category: "キャッチング",
    title: "手は「W」の形で構える",
    body:
      "正面のボールをこぼさない基本は、両手の親指と人差し指で「W」を作ること。\n\n- 親指同士を近づけ、後ろに壁を作る\n- 手のひらではなく指全体で包む\n- 目線はボールを最後まで追う\n\nこの形が、弾いてしまう失点を確実に減らします。",
  },
];

await mkdir(OUT, { recursive: true });
for (let i = 0; i < samples.length; i++) {
  const [slide] = await renderSlides({ slides: [samples[i]] }, "zero");
  await writeFile(path.join(OUT, `${String(i + 1).padStart(2, "0")}.png`), slide.buffer);
}
console.log(`Rendered ${samples.length} tip cards to ${OUT}`);
