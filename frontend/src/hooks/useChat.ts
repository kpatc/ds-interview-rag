import { useState, useCallback, useRef } from "react";
import type { Message, Company, RoundType, Source, QualityResult } from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function uid() {
  return Math.random().toString(36).slice(2);
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (query: string, company: Company, roundType: RoundType) => {
      if (!query.trim() || isLoading) return;

      abortRef.current?.abort();
      abortRef.current = new AbortController();

      const userMsg: Message = { id: uid(), role: "user", content: query, company, roundType };
      const assistantId = uid();
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        sources: [],
        isStreaming: true,
        isRefining: false,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsLoading(true);

      try {
        const res = await fetch(`${API_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, company, round_type: roundType, use_hyde: true, use_multi_query: true }),
          signal: abortRef.current.signal,
        });

        if (!res.ok) throw new Error(`API error ${res.status}`);

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let sources: Source[] = [];
        let content = "";
        // Track whether the next tokens are for the refined answer
        let inRefining = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const evt = JSON.parse(line.slice(6));

              if (evt.type === "sources") {
                sources = evt.sources;
                setMessages((prev) =>
                  prev.map((m) => (m.id === assistantId ? { ...m, sources } : m))
                );

              } else if (evt.type === "token") {
                if (inRefining) {
                  // Refined answer replaces the first-pass content
                  content += evt.text;
                } else {
                  content += evt.text;
                }
                setMessages((prev) =>
                  prev.map((m) => (m.id === assistantId ? { ...m, content } : m))
                );

              } else if (evt.type === "quality") {
                const quality: QualityResult = {
                  score: evt.score,
                  pass: evt.pass,
                  dimensions: evt.dimensions ?? {},
                  gaps: evt.gaps ?? [],
                };
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, quality, isRefining: false } : m
                  )
                );

              } else if (evt.type === "refining") {
                inRefining = true;
                content = "";  // reset so refined answer builds fresh
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: "", isRefining: true }
                      : m
                  )
                );

              } else if (evt.type === "done") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, isStreaming: false, isRefining: false }
                      : m
                  )
                );

              } else if (evt.type === "error") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: `Error: ${evt.message}`, isStreaming: false, isRefining: false }
                      : m
                  )
                );
              }
            } catch {}
          }
        }
      } catch (err: unknown) {
        if ((err as Error).name === "AbortError") return;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "Connection error. Is the API running?", isStreaming: false, isRefining: false }
              : m
          )
        );
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false, isRefining: false } : m))
    );
    setIsLoading(false);
  }, []);

  const clearMessages = useCallback(() => setMessages([]), []);

  return { messages, isLoading, sendMessage, clearMessages, stop };
}
