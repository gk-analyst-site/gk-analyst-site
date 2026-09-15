import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY

const SYSTEM = `あなたはゴールキーパー(GK)専門の指導者兼SNSコンテンツ制作者です。
ブランド「ZERO」(Just4Keepers Japan)として、Instagramの1枚完結「GK豆知識」カードを日本語で制作します。

厳守ルール:
- 実践的で根拠のあるGK指導内容にする(技術、戦術、ポジショニング、認知・判断、フィジカル、メンタル、育成など)。
- 事実として断定する数値・統計・価格・製品スペック・固有の研究引用は、確実でない限り書かない(捏造禁止)。一般論として述べる。
- 中学生でも理解できる、やさしく具体的な言葉で書く。
- 1枚で完結する読み切りにする(連載ではない)。
- 出力は指定のJSONのみ。前後に説明文やコードフェンスを付けない。`;

function buildUserPrompt(covered) {
  const avoid = covered.length
    ? `次の見出しは既出なので、内容もテーマも重複しないよう避けてください:\n- ${covered.join("\n- ")}`
    : "まだ何も投稿していません。";
  return `新しい「GK豆知識」を1枚、日本語で作ってください。
${avoid}

構成:
- category: 短い分野名(例「ポジショニング」「キャッチング」「1対1」「メンタル」「フットワーク」「クロス対応」など)
- title: 一目で得するとわかる見出し(20文字前後、キャッチーに)
- body: 本文。最大~240文字。まず要点を1〜2文、続けて具体策を行頭"- "の箇条書き2〜3個、最後に一言のまとめ。段落は改行で区切る。

出力JSON(この形のみ):
{ "category": "…", "title": "…", "body": "…" }`;
}

function extractJson(text) {
  const cleaned = text.replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start === -1 || end === -1) throw new Error("No JSON found in model output.");
  return JSON.parse(cleaned.slice(start, end + 1));
}

/**
 * Generate a single Japanese "GK tip" card (ZERO brand).
 * @param {string[]} covered  already-used tip titles to avoid
 * @returns {Promise<{category:string, title:string, body:string}>}
 */
export async function generateTip(covered = []) {
  const res = await client.messages.create({
    model: "claude-opus-4-8",
    max_tokens: 1500,
    system: SYSTEM,
    messages: [{ role: "user", content: buildUserPrompt(covered) }],
  });
  const text = res.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  const tip = extractJson(text);
  if (!tip.title || !tip.body) throw new Error("Generated tip is malformed.");
  tip.category = tip.category || "GK豆知識";
  return tip;
}

/**
 * Build an Instagram caption for a tip card (short body echo + hashtags).
 * @param {{category:string, title:string, body:string}} tip
 * @returns {string}
 */
export function tipCaption(tip) {
  const plain = String(tip.body).replace(/^[-*・]\s*/gm, "").replace(/\n+/g, " ").trim();
  const tags = [
    "#Just4Keepers", "#ZERO", "#ゴールキーパー", "#GK", "#GK豆知識",
    "#GKトレーニング", "#サッカー", "#キーパー", "#守護神", "#育成年代",
  ];
  return `【${tip.category}】${tip.title}\n\n${plain}\n\n保存して練習前に見返そう。\n${tags.join(" ")}`;
}
