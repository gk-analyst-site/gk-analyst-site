import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY

const SYSTEM = `あなたはGK用品ブランド「ZERO」(Just4Keepers Japan)のSNS担当者です。
GKグローブなどの商品写真から、Instagram用の「商品紹介カード」の文言を日本語で作ります。

厳守ルール:
- 商品名は写真に見える範囲(ロゴ・モデル名の刻印など)から判断する。読み取れない場合は無理に固有名を作らず、一般的な名称(例「ZERO GKグローブ」)にする。
- 特徴は写真から見て取れる要素(色、カット、ストラップ、パンチングゾーン等)や一般的なGKグローブの利点にとどめる。
- 価格・割引・在庫・発売日・具体的な数値スペック・型番は、写真や補足に明記されていない限り、絶対に書かない(捏造禁止)。
- 誇大表現は避け、簡潔で信頼感のある表現にする。
- 出力は指定のJSONのみ。前後に説明やコードフェンスを付けない。`;

function extractJson(text) {
  const cleaned = text.replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start === -1 || end === -1) throw new Error("No JSON found in model output.");
  return JSON.parse(cleaned.slice(start, end + 1));
}

/**
 * Generate branded product-card copy from a product photo.
 * @param {Buffer} imageBuffer
 * @param {string} mediaType   e.g. "image/png"
 * @param {string} [hint]      optional context (from context.json)
 * @returns {Promise<{title:string, features:string[], caption:string}>}
 */
export async function generateProductCard(imageBuffer, mediaType, hint) {
  const userText = `この写真はZEROのGK商品です。${hint ? `補足情報:「${hint}」。補足を優先してください。` : ""}
商品紹介カード用に、次のJSONだけを出力してください:
{
  "title": "商品名(短く。読み取れなければ一般名)",
  "features": ["特徴1(10〜18文字)", "特徴2", "特徴3"],
  "caption": "Instagram本文(2〜4文)。最後に #Just4Keepers #ZERO #ゴールキーパー #GK を含むハッシュタグ8〜12個。価格は書かない。"
}`;

  const res = await client.messages.create({
    model: "claude-opus-4-8",
    max_tokens: 1200,
    system: SYSTEM,
    messages: [
      {
        role: "user",
        content: [
          { type: "image", source: { type: "base64", media_type: mediaType, data: imageBuffer.toString("base64") } },
          { type: "text", text: userText },
        ],
      },
    ],
  });

  const text = res.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  const card = extractJson(text);
  if (!card.title || !Array.isArray(card.features)) throw new Error("Generated product card is malformed.");
  card.features = card.features.filter(Boolean).slice(0, 3);
  if (!card.caption) card.caption = `${card.title}\n\n#Just4Keepers #ZERO #ゴールキーパー #GK #GKグローブ #キーパーグローブ #goalkeeper #サッカー`;
  return card;
}
