import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { renderSlides } from "../lib/slides.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "..", "preview-zero");

const plan = {
  slides: [
    {
      type: "cover",
      kicker: "GKトレーニング",
      title: "GKトレーニングの組み立て方",
      subtitle: "「試合」から逆算する5つのステップ｜Part 1",
    },
    {
      type: "content",
      heading: "まず問いを変える",
      body:
        "セッションはドリルの寄せ集めではありません。「今日は何のドリルをやろう？」から始めない。\n\n問うべきはこれ：「このGKは試合で何を必要としている？」\n\n流れ：試合 → 課題 → 目標 → 設計 → 振り返り",
    },
    {
      type: "content",
      badge: "1",
      heading: "試合から始める",
      body:
        "ドリルを選ぶ前に、まず試合を見て、注目すべき場面を洗い出します。\n\n- 立ち位置は適切だったか\n- 状況を早く認知できたか\n- 判断と実行は正しかったか\n\n目的はミス探しではなく、次に必要なものを理解すること。",
    },
    {
      type: "content",
      badge: "2",
      heading: "本当の課題を見極める",
      body:
        "「クロスを改善」では不十分。なぜ崩れたのかを分解します。\n\n- ポジショニング\n- 認知（ボールの軌道・プレッシャー）\n- 判断（出る・留まる・調整）\n- タイミング\n- 技術\n\n課題が違えば、必要なトレーニングも違います。",
    },
    {
      type: "cta",
      kicker: "ZERO",
      title: "続きは水曜へ",
      body: "Part 2 では「目標設定」と「セッション設計」を解説します。保存して次回もチェック。",
    },
  ],
};

await mkdir(OUT, { recursive: true });
const slides = await renderSlides(plan, "zero");
for (const s of slides) await writeFile(path.join(OUT, s.name), s.buffer);
console.log(`Rendered ${slides.length} ZERO slides to ${OUT}`);
