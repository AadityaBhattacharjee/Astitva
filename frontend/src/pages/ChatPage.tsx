import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";
import { toast } from "sonner";

import { AppLayout } from "@/layouts/AppLayout";
import { Button } from "@/components/ui/button";
import { SourceBadge } from "@/components/astitva/Badge";
import { agentApi, ApiError } from "@/api/client";
import type { ChatMessage } from "@/types";

const suggestedPrompts = [
  "What government schemes am I eligible for?",
  "How do I get legal aid?",
  "What healthcare support exists for me?",
  "How can I improve my financial situation?",
  "What employment opportunities are available?",
  "How do I find a mentor?",
  "What is my current risk level?",
  "Help me create a plan for the next 3 months.",
  "What documents do I need?",
  "How is my case progressing?",
];

const welcomeMessage: ChatMessage = {
  id: "msg_welcome",
  role: "guide",
  text: "I'm your Astitva AI guide, powered by IBM Granite 3.3 8B. I can help with government schemes, legal information, healthcare, finance, employment, mentorship, planning, progress tracking, risk assessment, and documents. What would you like to explore?",
  at: new Date().toISOString(),
};

function formatAgentResponse(agentName: string, data: Record<string, unknown>): string {
  // Extract the best text field from the agent response
  const answer =
    (data.answer as string) ||
    (data.case_summary as string) ||
    (data.summary as string) ||
    "";

  if (!answer || answer === "LLM provider placeholder response.") {
    return `[${agentName}] I processed your request but the AI model returned a placeholder response. Please ensure the Granite MLX server is running at http://127.0.0.1:8080.`;
  }
  return answer;
}

function extractSources(data: Record<string, unknown>): string[] {
  const s = data.sources;
  if (Array.isArray(s)) return s as string[];
  return [];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage]);
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const send = async (value: string) => {
    if (!value.trim() || thinking) return;

    const userMsg: ChatMessage = {
      id: `msg_${Date.now()}`,
      role: "user",
      text: value.trim(),
      at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setText("");
    setThinking(true);

    try {
      // First ask supervisor to route
      const routing = await agentApi.supervisor(value.trim());
      const routed = routing.routed_to;

      let replyText = "";
      let sources: string[] = [];
      let agentName = routed ?? "supervisor";

      // Call the routed specialist agent
      try {
        if (routed === "government") {
          const r = await agentApi.government({ query: value.trim() });
          replyText = formatAgentResponse("government", r as unknown as Record<string, unknown>);
          sources = r.sources;
        } else if (routed === "legal") {
          const r = await agentApi.legal({ query: value.trim() });
          replyText = formatAgentResponse("legal", r as unknown as Record<string, unknown>);
          sources = r.sources;
        } else if (routed === "healthcare") {
          const r = await agentApi.healthcare({ query: value.trim() });
          replyText = formatAgentResponse("healthcare", r as unknown as Record<string, unknown>);
          sources = r.sources;
        } else if (routed === "finance") {
          const r = await agentApi.finance({ query: value.trim() });
          replyText = formatAgentResponse("finance", r as unknown as Record<string, unknown>);
          sources = r.sources;
        } else if (routed === "employment") {
          const r = await agentApi.employment({ query: value.trim() });
          replyText = formatAgentResponse("employment", r as unknown as Record<string, unknown>);
          sources = r.sources;
        } else if (routed === "document") {
          const r = await agentApi.document(value.trim());
          replyText = formatAgentResponse("document", r as unknown as Record<string, unknown>);
          sources = r.sources;
        } else if (routed === "case_worker") {
          const r = await agentApi.case_worker(value.trim());
          replyText = r.case_summary;
          agentName = "case_worker";
        } else if (routed === "mentor_matching") {
          const r = await agentApi.mentor_matching(value.trim());
          replyText = r.answer;
          agentName = "mentor_matching";
        } else if (routed === "planning") {
          const r = await agentApi.planning(value.trim());
          replyText = r.answer;
          agentName = "planning";
        } else if (routed === "progress") {
          const r = await agentApi.progress(value.trim());
          replyText = r.answer;
          agentName = "progress";
        } else if (routed === "risk") {
          const r = await agentApi.risk(value.trim());
          replyText = r.answer;
          agentName = "risk";
        } else {
          // Unknown routing — use supervisor summary
          replyText = routing.summary;
        }
      } catch (agentErr: unknown) {
        if (agentErr instanceof ApiError && agentErr.status === 401) {
          throw agentErr; // bubble up to outer catch
        }
        replyText = `[${routed ?? "agent"}] I encountered an issue processing this request: ${agentErr instanceof Error ? agentErr.message : "Unknown error"}`;
      }

      const guideMsg: ChatMessage = {
        id: `msg_${Date.now()}`,
        role: "guide",
        text: replyText,
        at: new Date().toISOString(),
        agentType: agentName,
        sources: sources.length > 0 ? sources : undefined,
      };
      setMessages((m) => [...m, guideMsg]);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 401) {
        toast.error("Your session has expired. Please log in again.");
      } else {
        const errMsg: ChatMessage = {
          id: `msg_${Date.now()}`,
          role: "guide",
          text: `Sorry, I couldn't process that: ${err instanceof Error ? err.message : "Unknown error"}. Please try again.`,
          at: new Date().toISOString(),
        };
        setMessages((m) => [...m, errMsg]);
      }
    } finally {
      setThinking(false);
    }
  };

  return (
    <AppLayout title="Astitva Guide" subtitle="Powered by IBM Granite 3.3 8B · 12 specialist agents">
      <div className="space-y-5">
        {/* Messages */}
        <div className="space-y-4 pb-2" aria-live="polite">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`max-w-[85%] rounded-2xl border px-4 py-3 text-sm ${
                message.role === "user"
                  ? "ml-auto border-primary/30 bg-primary text-primary-foreground"
                  : "border-border bg-surface text-foreground"
              }`}
            >
              {message.role === "guide" && message.agentType ? (
                <p className="mb-1.5 text-xs font-semibold text-primary capitalize">
                  [{message.agentType.replace(/_/g, " ")} agent]
                </p>
              ) : null}
              <p className="leading-relaxed whitespace-pre-wrap">{message.text}</p>
              {message.sources && message.sources.length > 0 ? (
                <div className="mt-3">
                  <SourceBadge sources={message.sources} />
                </div>
              ) : null}
            </div>
          ))}
          {thinking ? (
            <p className="text-sm text-muted-foreground">Astitva is thinking…</p>
          ) : null}
          <div ref={bottomRef} />
        </div>

        {/* Suggested prompts */}
        <div className="flex flex-wrap gap-2">
          {suggestedPrompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => void send(prompt)}
              disabled={thinking}
              className="min-h-9 rounded-full border border-border bg-surface px-3.5 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Input */}
        <form
          className="grid grid-cols-[minmax(0,1fr)_auto] gap-2"
          onSubmit={(e) => { e.preventDefault(); void send(text); }}
        >
          <label htmlFor="guide-input" className="sr-only">Ask the Astitva Guide</label>
          <input
            id="guide-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask anything — government, legal, health, finance, employment…"
            disabled={thinking}
            className="min-h-12 rounded-full border border-input bg-surface px-4 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
          />
          <Button type="submit" size="icon" aria-label="Send message" loading={thinking}>
            <Send className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>

        <p className="rounded-2xl border border-border bg-secondary-soft px-4 py-3 text-xs text-muted-foreground">
          Astitva provides guidance based on available verified information. It does not replace
          professional legal, medical or financial advice. Responses are generated by IBM Granite
          3.3 8B running locally.
        </p>
      </div>
    </AppLayout>
  );
}
