import { useState, useRef, useEffect } from 'react'
import {
  Send, Square, Trash2, BookOpen, X, Sparkles, ChevronRight,
  CheckCircle, AlertTriangle, RefreshCw, AlertCircle,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useChat } from './hooks/useChat'
import { Sidebar } from './components/Sidebar'
import { SourceCard } from './components/SourceCard'
import type { Company, IndexStats, Message, RoundType, Source } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const EXAMPLE_PROMPTS = [
  'What is the BCG X CodeSignal OA format and how hard is it?',
  'Walk me through McKinsey QuantumBlack technical interview expectations',
  'How does the BCG X take-home case assignment work?',
  'What stories should I prepare for a McKinsey PEI round?',
]

const ROUND_LABEL: Record<string, string> = {
  All: 'All Rounds', General: 'General', OA: 'Online Assessment',
  Technical: 'Technical', LiveCoding: 'Live Coding',
  Case: 'Case Interview', PEI: 'PEI / Behavioral', TakeHome: 'Take-Home',
}

const COMPANY_BADGE: Record<string, string> = {
  BCG: 'text-bcg border-bcg/30 bg-bcg/10',
  McKinsey: 'text-mckinsey-light border-mckinsey/30 bg-mckinsey/10',
  Both: 'text-zinc-400 border-zinc-700 bg-zinc-800/50',
}

// ── Welcome screen ────────────────────────────────────────────────────

function WelcomeScreen({
  company, onSend,
}: { company: Company; onSend: (q: string) => void }) {
  const accentClass =
    company === 'BCG' ? 'text-bcg' :
    company === 'McKinsey' ? 'text-mckinsey-light' :
    'text-zinc-400'

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 gap-10 animate-fade-in">
      <div className="text-center space-y-4">
        <div className={`w-14 h-14 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto`}>
          <Sparkles size={22} className={accentClass} />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
            DS Interview Coach
          </h1>
          <p className="text-sm text-zinc-500 mt-2 max-w-xs mx-auto leading-relaxed">
            Answers grounded in 60+ sources — forums, Reddit, Glassdoor, YouTube, TeamBlind.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 w-full max-w-lg">
        {EXAMPLE_PROMPTS.map((p) => (
          <button
            key={p}
            onClick={() => onSend(p)}
            className="text-left text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-900 hover:bg-zinc-800/80 border border-zinc-800 hover:border-zinc-700 rounded-xl px-4 py-3 transition-all leading-relaxed"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Message bubbles ───────────────────────────────────────────────────

function UserMessage({ msg }: { msg: Message }) {
  const badge = COMPANY_BADGE[msg.company ?? 'Both']
  const showBadge = msg.company && msg.company !== 'Both'
  const showRound = msg.roundType && msg.roundType !== 'All'

  return (
    <div className="flex justify-end px-6 py-2 animate-slide-up">
      <div className="max-w-[65%] flex flex-col items-end gap-1.5">
        {(showBadge || showRound) && (
          <div className="flex items-center gap-1.5">
            {showBadge && (
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${badge}`}>
                {msg.company === 'BCG' ? 'BCG X' : 'McKinsey QB'}
              </span>
            )}
            {showRound && (
              <span className="text-[10px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded border border-zinc-700">
                {ROUND_LABEL[msg.roundType!]}
              </span>
            )}
          </div>
        )}
        <div className="bg-zinc-800 border border-zinc-700/60 rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-zinc-100 leading-relaxed">
          {msg.content}
        </div>
      </div>
    </div>
  )
}

const MD_COMPONENTS = {
  p: ({ children }: { children?: React.ReactNode }) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }: { children?: React.ReactNode }) => <ul className="list-disc list-inside mb-3 space-y-1 text-zinc-300">{children}</ul>,
  ol: ({ children }: { children?: React.ReactNode }) => <ol className="list-decimal list-inside mb-3 space-y-1 text-zinc-300">{children}</ol>,
  li: ({ children }: { children?: React.ReactNode }) => <li>{children}</li>,
  strong: ({ children }: { children?: React.ReactNode }) => <strong className="text-zinc-100 font-semibold">{children}</strong>,
  em: ({ children }: { children?: React.ReactNode }) => <em className="text-zinc-300">{children}</em>,
  h1: ({ children }: { children?: React.ReactNode }) => <h1 className="text-base font-semibold text-zinc-100 mb-2 mt-4 first:mt-0">{children}</h1>,
  h2: ({ children }: { children?: React.ReactNode }) => <h2 className="text-sm font-semibold text-zinc-100 mb-1.5 mt-3 first:mt-0">{children}</h2>,
  h3: ({ children }: { children?: React.ReactNode }) => <h3 className="text-sm font-medium text-zinc-200 mb-1.5 mt-3 first:mt-0">{children}</h3>,
  code: ({ children }: { children?: React.ReactNode }) => (
    <code className="bg-zinc-800 text-zinc-200 px-1.5 py-0.5 rounded text-[12px] font-mono border border-zinc-700/50">{children}</code>
  ),
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 overflow-x-auto text-xs font-mono text-zinc-300 mb-3">{children}</pre>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="border-l-2 border-zinc-700 pl-4 text-zinc-400 italic my-2">{children}</blockquote>
  ),
}

function QualityBadge({ quality }: { quality: NonNullable<Message['quality']> }) {
  const score = quality.score
  const passed = quality.pass
  const pct = Math.round((score / 10) * 100)

  const color = passed
    ? 'text-emerald-400 border-emerald-800/60 bg-emerald-950/40'
    : 'text-amber-400 border-amber-800/60 bg-amber-950/40'
  const Icon = passed ? CheckCircle : AlertCircle

  const dims = quality.dimensions
  const dimEntries = Object.entries(dims) as [string, number][]

  return (
    <div className={`mt-3 inline-flex flex-col gap-1.5 text-[11px] border rounded-lg px-3 py-2 ${color}`}>
      <div className="flex items-center gap-1.5 font-medium">
        <Icon size={12} />
        <span>Quality: {score.toFixed(1)}/10</span>
        <span className={`ml-1 px-1.5 py-0.5 rounded text-[10px] ${passed ? 'bg-emerald-900/60' : 'bg-amber-900/60'}`}>
          {passed ? 'PASSED' : 'REFINED'}
        </span>
        <div className="ml-2 w-16 h-1 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className={`h-full rounded-full ${passed ? 'bg-emerald-500' : 'bg-amber-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      {dimEntries.length > 0 && (
        <div className="flex gap-2 text-[10px] text-zinc-500">
          {dimEntries.map(([k, v]) => (
            <span key={k}>{k.replace('_', ' ')}: {v.toFixed(0)}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function AssistantMessage({
  msg, onViewSources,
}: { msg: Message; onViewSources: (sources: Source[]) => void }) {
  const hasSources = (msg.sources?.length ?? 0) > 0
  const conflictCount = msg.sources?.filter(s => s.conflict).length ?? 0

  return (
    <div className="flex gap-3 px-6 py-2 animate-slide-up">
      <div className="shrink-0 w-7 h-7 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center mt-0.5">
        <Sparkles size={13} className="text-zinc-500" />
      </div>
      <div className="flex-1 min-w-0">
        {/* Refining indicator */}
        {msg.isRefining && (
          <div className="flex items-center gap-1.5 text-[11px] text-amber-400 mb-2">
            <RefreshCw size={11} className="animate-spin" />
            <span>Refining with additional sources…</span>
          </div>
        )}

        <div className="text-sm text-zinc-200 leading-relaxed">
          {msg.isStreaming ? (
            <span>
              {msg.content || <span className="text-zinc-600">Thinking…</span>}
              <span className="inline-block w-0.5 h-[14px] bg-zinc-400 ml-0.5 align-middle animate-blink" />
            </span>
          ) : (
            <ReactMarkdown components={MD_COMPONENTS}>
              {msg.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Quality badge */}
        {msg.quality && !msg.isStreaming && (
          <QualityBadge quality={msg.quality} />
        )}

        {/* Sources + conflict warning */}
        {hasSources && !msg.isStreaming && (
          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={() => onViewSources(msg.sources!)}
              className="flex items-center gap-1 text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors"
            >
              <BookOpen size={11} />
              <span>{msg.sources!.length} sources</span>
              <ChevronRight size={11} />
            </button>
            {conflictCount > 0 && (
              <span className="flex items-center gap-1 text-[11px] text-amber-600">
                <AlertTriangle size={10} />
                {conflictCount} source{conflictCount > 1 ? 's' : ''} conflict
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sources drawer ────────────────────────────────────────────────────

function SourcesPanel({ sources, onClose }: { sources: Source[]; onClose: () => void }) {
  return (
    <aside className="w-72 shrink-0 flex flex-col border-l border-zinc-800 bg-zinc-950 overflow-hidden animate-fade-in">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-2">
          <BookOpen size={13} className="text-zinc-400" />
          <span className="text-sm font-medium text-zinc-200">Sources</span>
          <span className="text-[11px] text-zinc-600 bg-zinc-800/80 px-1.5 py-0.5 rounded font-mono">
            {sources.length}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-600 hover:text-zinc-300 transition-colors p-1 rounded hover:bg-zinc-800"
        >
          <X size={13} />
        </button>
      </div>
      <div className="flex-1 p-3 space-y-2 overflow-y-auto">
        {sources.map((s, i) => (
          <SourceCard key={i} source={s} index={i} />
        ))}
      </div>
    </aside>
  )
}

// ── Main app ──────────────────────────────────────────────────────────

export default function App() {
  const { messages, isLoading, sendMessage, clearMessages, stop } = useChat()
  const [company, setCompany] = useState<Company>('BCG')
  const [roundType, setRoundType] = useState<RoundType>('All')
  const [stats, setStats] = useState<IndexStats | null>(null)
  const [query, setQuery] = useState('')
  const [activeSources, setActiveSources] = useState<Source[] | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    fetch(`${API_URL}/api/stats`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setStats(data))
      .catch(() => {})
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSend() {
    const q = query.trim()
    if (!q || isLoading) return
    sendMessage(q, company, roundType)
    setQuery('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleTextareaChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setQuery(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
  }

  const accentBar =
    company === 'BCG' ? 'bg-bcg' :
    company === 'McKinsey' ? 'bg-mckinsey' :
    'bg-zinc-800'

  const companyLabel =
    company === 'BCG' ? 'BCG X' :
    company === 'McKinsey' ? 'McKinsey QuantumBlack' :
    'BCG X & McKinsey QB'

  return (
    <div className="h-screen flex bg-zinc-950 text-zinc-100 font-sans overflow-hidden">
      {/* Left sidebar */}
      <Sidebar
        company={company}
        roundType={roundType}
        onCompany={setCompany}
        onRound={setRoundType}
        stats={stats}
      />

      {/* Chat column */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Company accent line */}
        <div className={`h-px w-full transition-colors duration-500 ${accentBar}`} />

        {/* Header */}
        <header className="flex items-center justify-between px-6 h-12 border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-medium text-zinc-300">{companyLabel}</span>
            {roundType !== 'All' && (
              <>
                <span className="text-zinc-700">·</span>
                <span className="text-zinc-500">{ROUND_LABEL[roundType]}</span>
              </>
            )}
          </div>
          {messages.length > 0 && (
            <button
              onClick={clearMessages}
              className="flex items-center gap-1.5 text-[11px] text-zinc-600 hover:text-zinc-300 px-2.5 py-1.5 rounded-md hover:bg-zinc-800/60 transition-colors"
            >
              <Trash2 size={12} />
              Clear
            </button>
          )}
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto py-4">
          {messages.length === 0 ? (
            <WelcomeScreen
              company={company}
              onSend={(q) => sendMessage(q, company, roundType)}
            />
          ) : (
            <div className="max-w-3xl mx-auto">
              {messages.map((msg) =>
                msg.role === 'user' ? (
                  <UserMessage key={msg.id} msg={msg} />
                ) : (
                  <AssistantMessage
                    key={msg.id}
                    msg={msg}
                    onViewSources={setActiveSources}
                  />
                )
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <div className="shrink-0 border-t border-zinc-800 px-6 py-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-3 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 focus-within:border-zinc-700 transition-colors">
              <textarea
                ref={textareaRef}
                value={query}
                onChange={handleTextareaChange}
                onKeyDown={handleKeyDown}
                placeholder="Ask about interview formats, technical rounds, case frameworks…"
                disabled={isLoading && !query}
                rows={1}
                className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-600 resize-none outline-none leading-relaxed max-h-40 disabled:opacity-40"
              />
              <button
                onClick={isLoading ? stop : handleSend}
                disabled={!isLoading && !query.trim()}
                className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
                  isLoading
                    ? 'bg-zinc-700 hover:bg-zinc-600 text-zinc-300'
                    : query.trim()
                    ? 'bg-zinc-100 hover:bg-white text-zinc-900'
                    : 'bg-zinc-800 text-zinc-600 cursor-not-allowed'
                }`}
              >
                {isLoading ? <Square size={13} /> : <Send size={13} />}
              </button>
            </div>
            <p className="text-[11px] text-zinc-700 mt-2 text-center select-none">
              Enter to send · Shift+Enter for new line
            </p>
          </div>
        </div>
      </main>

      {/* Sources panel */}
      {activeSources && activeSources.length > 0 && (
        <SourcesPanel
          sources={activeSources}
          onClose={() => setActiveSources(null)}
        />
      )}
    </div>
  )
}
