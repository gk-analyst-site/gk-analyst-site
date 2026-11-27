import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY

const SYSTEM = `あなたはGK用品ブランド「ZERO」(Just4Keepers Japan)のSNS担当者です。
GKグローブなど「新モデル／先行予約」の広告画像から、購買意欲を高めるInstagramの告知キャプションを日本語で作ります。

厳守ルール:
- 新モデルの魅力が伝わる、前向きで信頼感のあるセールス文にする(誇大・煽りすぎはNG)。
- 価格・割引・発売日・先行予約の日時・在庫数・具体的な数値スペック・型番は、画像にはっきり書かれている場合のみ記載してよい。書かれていない情報は絶対に推測・捏造しない。
- 商品名は画像に見える範囲で判断。読み取れない場合は無理に固有名を作らず「ZERO GKグローブ」等の一般名にする。
- 画像から見て取れる特徴(色、カット、ストラップ、パンチングゾーン等)や一般的なGKグローブの利点を魅力的に描写する。
- 「先行予約受付中/NEWモデル」という文脈を活かし、プロフィールのリンク/DMへ誘導する一文を入れる。
- コメントを促す問いかけを1文入れ「コメントで教えてください👇」で締める(コメント誘発のため)。
- 出力はキャプション本文のみ(JSONやコードフェンス不要)。最後に日本語+英語のハッシュタグを10〜14個。必ず #Just4Keepers #ZERO #ゴールキーパー #GK #先行予約 #新作グローブ を含める。`;

/**
 * Generate an enticing "new model / pre-order" caption from a product ad image.
 * @param {Buffer} imageBuffer
 * @param {string} mediaType   e.g. "image/jpeg" | "image/webp"
 * @param {string} [hint]      optional one-line detail (pre-order date, price, model...)
 * @returns {Promise<string>}
 */
export async function generateLaunchCopy(imageBuffer, mediaType, hint) {
  const userText = `この画像はZEROの新モデル(先行予約)の告知です。${hint ? `補足情報:「${hint}」。補足は正確な事実として優先的に使ってよい。` : "補足情報はありません。画像に書かれていない価格・日付・スペックは書かないでください。"}
購買意欲が高まるInstagramの告知キャプションを作成してください。`;

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

  const caption = res.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  if (!caption) throw new Error("Claude returned an empty launch caption.");
  return caption;
}
