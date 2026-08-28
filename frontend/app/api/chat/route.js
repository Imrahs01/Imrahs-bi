// This file runs ONLY on the server (Vercel's backend), never in the browser.
// That's why it's safe to use process.env.ANTHROPIC_API_KEY here — it's never
// bundled into client-side JavaScript the way NEXT_PUBLIC_ variables are.

export async function POST(req) {
  const { messages, analysisData } = await req.json();

  const systemPrompt = `You are Vantage, an AI business intelligence analyst embedded in a company's dashboard. You have access to real computed KPIs and pre-detected signals (risks/opportunities) below as JSON. Answer the manager's question in plain, direct business language.

Rules:
- Ground every claim in the JSON data provided. Never invent numbers.
- Be concise: short paragraphs and/or bullet points, no long preambles.
- When relevant, explain a plausible reason behind a trend or gap using patterns visible in the data.
- Always end with 1-2 concrete recommended actions when the question concerns a problem or gap.
- If a field isn't present in the data (check "fields_missing"), say so honestly rather than guessing.

DATA (JSON):
${JSON.stringify(analysisData)}`;

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: 1000,
      system: systemPrompt,
      messages: messages.map((m) => ({ role: m.role, content: m.content })),
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    return Response.json({ error: errText }, { status: response.status });
  }

  const data = await response.json();
  const text = (data.content || [])
    .map((b) => (b.type === "text" ? b.text : ""))
    .filter(Boolean)
    .join("\n");

  return Response.json({ text });
}
