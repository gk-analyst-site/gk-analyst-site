import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY from the environment

// Brand / voice context for J4K (Just4Keepers Japan) — a goalkeeper academy.
// Tweak this block to change the tone of every generated caption.
const BRAND_CONTEXT = `
あなたはJust4Keepers Japan（J4K）のSNS担当者です。
J4Kはゴールキーパー専門のトレーニングアカデミー／分析サービスです。
Instagramの投稿キャプションを日本語で作成してください。

トーン：
- プロフェッショナルだが親しみやすい
- GKの成長・上達を後押しする前向きな内容
- 大げさな絵文字の乱用は避け、1〜3個程度に留める

構成：
- 本文は2〜4文程度、簡潔に
- 最後に日本語＋英語のハッシュタグを8〜12個
- ハッシュタグには必ず #Just4Keepers #J4K #ゴールキーパー #GK を含める

重要なルール：
- 価格・割引率・在庫数・発売日・型番などの「具体的な数字や事実」は、画像や補足情報にはっきり書かれていない限り、絶対に記載・推測しないでください（間違った情報の投稿を防ぐため）。
- 補足情報が与えられている場合は、その内容を優先してください。
`;

const MEDIA_TYPES = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".gif": "image/gif",
  ".webp": "image/webp",
};

export function mediaTypeFor(filename) {
  const ext = filename.slice(filename.lastIndexOf(".")).toLowerCase();
  return MEDIA_TYPES[ext] || "image/jpeg";
}

/**
 * Generate an Instagram caption for an image using Claude (vision).
 *
 * @param {Buffer} imageBuffer   Raw image bytes.
 * @param {string} mediaType     e.g. "image/jpeg".
 * @param {string} [hint]        Optional context about the photo (from queue.json).
 * @returns {Promise<string>}    The caption text.
 */
export async function generateCaption(imageBuffer, mediaType, hint) {
  const userText = hint
    ? `この画像はJ4Kの投稿用です。補足情報：「${hint}」。画像の内容と補足を踏まえてキャプションを作成してください。`
    : `この画像はJ4Kの投稿用です。画像の内容を踏まえてキャプションを作成してください。`;

  const response = await client.messages.create({
    model: "claude-opus-4-8",
    max_tokens: 1024,
    system: BRAND_CONTEXT,
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image",
            source: {
              type: "base64",
              media_type: mediaType,
              data: imageBuffer.toString("base64"),
            },
          },
          { type: "text", text: userText },
        ],
      },
    ],
  });

  const caption = response.content
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("")
    .trim();

  if (!caption) {
    throw new Error("Claude returned an empty caption.");
  }
  return caption;
}
