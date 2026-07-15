import { Check, Copy } from "lucide-react";
import { useState } from "react";

type ParsedPrompt = {
  model: string;
  positive: string;
  negative: string;
  source: string;
};

function parsePrompt(content: string): ParsedPrompt | null {
  const match = content.match(
    /^目标模型：([^\n]+)\s*\n\s*正向提示词\s*\n([\s\S]*?)\n\s*负向提示词\s*\n([\s\S]*?)\n\s*(Danbooru 来源标签：[^\n]+)\s*$/,
  );
  if (!match) return null;
  return {
    model: match[1].trim(),
    positive: match[2].trim(),
    negative: match[3].trim(),
    source: match[4].trim(),
  };
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }
  return (
    <button className="icon-text-button" onClick={copy} title={`复制${label}`} type="button">
      {copied ? <Check size={14} /> : <Copy size={14} />}
      {copied ? "已复制" : "复制"}
    </button>
  );
}

export function PromptResult({ content }: { content: string }) {
  const prompt = parsePrompt(content);
  if (!prompt) return <div className="message-text">{content}</div>;
  return (
    <div className="prompt-result">
      <header>
        <div>
          <span className="result-label">PROMPT RESULT</span>
          <strong>{prompt.model}</strong>
        </div>
        <CopyButton label="完整提示词" value={content} />
      </header>
      <section className="prompt-section positive">
        <div className="prompt-section-head">
          <span>正向提示词</span>
          <CopyButton label="正向提示词" value={prompt.positive} />
        </div>
        <p>{prompt.positive}</p>
      </section>
      <section className="prompt-section negative">
        <div className="prompt-section-head">
          <span>负向提示词</span>
          <CopyButton label="负向提示词" value={prompt.negative} />
        </div>
        <p>{prompt.negative}</p>
      </section>
      <footer>{prompt.source}</footer>
    </div>
  );
}
