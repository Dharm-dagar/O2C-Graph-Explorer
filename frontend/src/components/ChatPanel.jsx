import { useState, useRef, useEffect, useCallback } from 'react'

const SUGGESTIONS = [
  'Which products have the highest number of billing documents?',
  'Trace the full O2C flow of billing document 91150187',
  'Show top 5 customers by total revenue',
  'Find sales orders that have no delivery at all',
  'List all cancelled billing documents',
  'Which plants handle the most deliveries?',
]

const INITIAL_MESSAGE = {
  role: 'assistant',
  content: 'Hi! I can help you analyze the **Order to Cash** process. Ask me about sales orders, deliveries, billing documents, payments, or customers — or try one of the suggested queries below.',
  id: 'initial'
}

function parseMarkdown(text) {
  // Simple markdown: bold, code blocks, inline code
  const parts = []
  let remaining = text

  // Split on code blocks first
  const codeBlockRe = /```(?:sql)?\s*([\s\S]*?)```/g
  let lastIndex = 0
  let match

  while ((match = codeBlockRe.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: text.slice(lastIndex, match.index) })
    }
    parts.push({ type: 'code', content: match[1].trim() })
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    parts.push({ type: 'text', content: text.slice(lastIndex) })
  }

  return parts.map((part, i) => {
    if (part.type === 'code') {
      return <pre key={i}>{part.content}</pre>
    }
    // Process inline markdown in text
    const processed = part.content
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>')
    return (
      <span key={i} dangerouslySetInnerHTML={{ __html: processed }} />
    )
  })
}

function QueryResultsTable({ results }) {
  if (!results || results.error) {
    return results?.error ? (
      <div className="query-results" style={{ color: '#ef4444', fontSize: 11 }}>
        Query error: {results.error}
      </div>
    ) : null
  }
  if (!results.columns || results.rows?.length === 0) return null

  return (
    <div className="query-results">
      <table className="results-table">
        <thead>
          <tr>
            {results.columns.map(c => <th key={c}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {results.rows.slice(0, 20).map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j} title={String(cell ?? '')}>
                  {cell == null ? '—' : String(cell).length > 20 ? String(cell).slice(0, 20) + '…' : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {results.total > 20 && (
        <div className="results-count">Showing 20 of {results.total} rows</div>
      )}
    </div>
  )
}

export default function ChatPanel({ onHighlight }) {
  const [messages, setMessages] = useState([INITIAL_MESSAGE])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(true)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || loading) return

    const userMsg = { role: 'user', content: text, id: Date.now() }
    const history = messages.filter(m => m.id !== 'initial').map(m => ({
      role: m.role,
      content: m.content
    }))

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setShowSuggestions(false)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history })
      })
      const data = await res.json()

      const assistantMsg = {
        role: 'assistant',
        content: data.response,
        queryResults: data.query_results,
        id: Date.now() + 1
      }
      setMessages(prev => [...prev, assistantMsg])

      if (data.highlighted_nodes?.length && onHighlight) {
        onHighlight(data.highlighted_nodes)
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please check your API configuration and try again.',
        id: Date.now() + 1
      }])
    } finally {
      setLoading(false)
    }
  }, [loading, messages, onHighlight])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <>
      {/* Header */}
      <div className="panel-header">
        <div className="panel-header-title">Chat with Graph</div>
        <div className="panel-header-sub">Order to Cash</div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-row ${msg.role}`}>
            <div className={`msg-avatar ${msg.role === 'assistant' ? 'ai' : 'user'}`}>
              {msg.role === 'assistant' ? (
                <span style={{ fontWeight: 700, fontSize: 11, fontFamily: 'DM Mono' }}>D</span>
              ) : (
                <svg viewBox="0 0 24 24" style={{ width: 16, height: 16, fill: 'currentColor' }}>
                  <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
                </svg>
              )}
            </div>
            <div>
              <div className="msg-name">
                {msg.role === 'assistant' ? (
                  <>Dodge AI <small>Graph Agent</small></>
                ) : (
                  <>You</>
                )}
              </div>
              <div className={`message-bubble ${msg.role === 'assistant' ? 'ai' : 'user'}`}>
                {parseMarkdown(msg.content)}
                {msg.queryResults && (
                  <QueryResultsTable results={msg.queryResults} />
                )}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="message-row">
            <div className="msg-avatar ai">
              <span style={{ fontWeight: 700, fontSize: 11, fontFamily: 'DM Mono' }}>D</span>
            </div>
            <div>
              <div className="msg-name">Dodge AI <small>Graph Agent</small></div>
              <div className="message-bubble ai">
                <div className="loading-dots">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {showSuggestions && (
        <div className="suggestions">
          <div className="suggestions-label">Try asking</div>
          {SUGGESTIONS.map((s, i) => (
            <button
              key={i}
              className="suggestion-chip"
              onClick={() => sendMessage(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Status */}
      <div className="chat-status">
        <div className={`status-dot ${loading ? 'thinking' : ''}`} />
        <span>
          {loading ? 'Dodge AI is thinking...' : 'Dodge AI is awaiting instructions'}
        </span>
      </div>

      {/* Input */}
      <div className="chat-input-area">
        <div className="chat-input-wrap">
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="Analyze anything"
            value={input}
            onChange={e => {
              setInput(e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px'
            }}
            onKeyDown={handleKeyDown}
            rows={1}
          />
          <button
            className="send-btn"
            onClick={() => sendMessage(input)}
            disabled={loading || !input.trim()}
          >
            <svg viewBox="0 0 24 24">
              <path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/>
            </svg>
          </button>
        </div>
      </div>
    </>
  )
}
