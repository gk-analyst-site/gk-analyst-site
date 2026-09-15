import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY

const SYSTEM = `あなたはゴールキーパー(GK)専門の指導者兼SNSコンテンツ制作者です。
ブランド「ZERO」(Just4Keepers Japan)として、Instagramのカルーセル(スワイプ式)教育コンテンツを日本語で制作します。

厳守ルール:
- 実践的で根拠のあるGK指導内容にする(トレーニング設計、技術、戦術、認知・判断、フィジカル、メンタル、育成など)。
- 事実として断定する数値・統計・価格・製品スペック・固有の研究引用は、確実でない限り書かない(捏造禁止)。一般論として述べる。
- 押し付けがましい広告表現は避け、コーチ・保護者・選手に役立つ内容にする。
- 各パートは「1枚で完結しすぎず、続きが気になる」構成にする(小出し/連載)。
- 出力は指定のJSONのみ。前後に説明文やコードフェンスを付けない。`;

// Rotate the carousel format so the feed stays varied (all use the same slide
// types: cover / content / cta).
const FORMATS = [
  { key: "解説連載", directive: "オーソドックスな解説連載。各パートで技術・戦術を段階的に深掘りする。" },
  { key: "クイズ形式", directive: "クイズ形式。cover で実戦のGK状況を問いとして提示し、content で選択肢や考え方→答えと根拠を解説、cta で次の問題を予告する。" },
  { key: "GK用語集", directive: "GK用語をやさしく解説する用語集。各パートで1〜2個の用語を、意味・具体例・実戦での使いどころに分けて中学生でもわかるように説明する。" },
  { key: "よくある誤解", directive: "よくある誤解を正すミス解説。cover で「ありがちな思い込み(×)」を提示し、content で「正しい理解(○)」と理由・改善策を示す。" },
];

export function pickFormat() {
  return FORMATS[Math.floor(Math.random() * FORMATS.length)];
}

function buildUserPrompt(covered, format) {
  const avoid = covered.length
    ? `次のトピックは既出なので避けてください:\n- ${covered.join("\n- ")}`
    : "まだ何も投稿していません。";
  return `新しいGK指導テーマで、全3パートの連載カルーセルを日本語で作ってください。
今回のフォーマット: 「${format.key}」 — ${format.directive}
${avoid}

各パートの構成:
- 1枚目: type "cover"  { kicker(短い分野名), title(このパートの見出し), subtitle("Part 1/3" などを含める) }
- 中間: type "content" { badge(任意の番号 "1" 等), heading(見出し), body(本文。段落は改行、箇条書きは行頭 "- ") }
  - body は1枚あたり日本語で最大~280文字。詰め込みすぎない。
- 最後: type "cta"    { kicker "ZERO", title(次への引き, 例「続きは次回へ」), body(要約や次回予告) }
- 1パートは合計4〜6枚。

各パートに caption(日本語, 2〜4文 + ハッシュタグ8〜12個)を付ける。
ハッシュタグには必ず #Just4Keepers #ZERO #ゴールキーパー #GK を含める。

出力JSON(この形のみ):
{
  "topic": "連載全体の短いタイトル",
  "parts": [
    { "caption": "…", "slides": [ {"type":"cover","kicker":"…","title":"…","subtitle":"… Part 1/3"}, {"type":"content","badge":"1","heading":"…","body":"…"}, {"type":"cta","kicker":"ZERO","title":"…","body":"…"} ] },
    { "caption": "…", "slides": [ … Part 2/3 … ] },
    { "caption": "…", "slides": [ … Part 3/3 … ] }
  ]
}`;
}

function extractJson(text) {
  const cleaned = text.replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start === -1 || end === -1) throw new Error("No JSON found in model output.");
  return JSON.parse(cleaned.slice(start, end + 1));
}

/**
 * Generate a new 3-part Japanese GK carousel series (ZERO brand).
 * @param {string[]} covered  already-covered topic titles to avoid
 * @returns {Promise<{topic:string, parts:Array<{caption:string, slides:object[]}>}>}
 */
export async function generateSeries(covered = []) {
  const format = pickFormat();
  console.log(`Series format: ${format.key}`);
  const res = await client.messages.create({
    model: "claude-opus-4-8",
    max_tokens: 8000,
    system: SYSTEM,
    messages: [{ role: "user", content: buildUserPrompt(covered, format) }],
  });
  const text = res.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  const plan = extractJson(text);
  if (!plan.topic || !Array.isArray(plan.parts) || plan.parts.length === 0) {
    throw new Error("Generated series is malformed.");
  }
  return plan;
}
