import { useState, useEffect, useCallback } from 'react'
import GraphView from './components/GraphView'
import ChatPanel from './components/ChatPanel'

const NODE_COLORS = {
  SalesOrder:     '#3b82f6',
  BillingDocument:'#8b5cf6',
  Delivery:       '#f59e0b',
  JournalEntry:   '#10b981',
  Payment:        '#ec4899',
  Customer:       '#ef4444',
  Product:        '#6366f1',
  Plant:          '#14b8a6',
}

export default function App() {
  const [graphData, setGraphData] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [highlightedNodes, setHighlightedNodes] = useState([])
  const [showLegend, setShowLegend] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('/api/graph').then(r => r.json()),
      fetch('/api/stats').then(r => r.json()),
    ]).then(([graph, stats]) => {
      setGraphData(graph)
      setStats(stats)
      setLoading(false)
    }).catch(err => {
      setError('Failed to load graph data. Is the backend running?')
      setLoading(false)
    })
  }, [])

  const handleHighlight = useCallback((nodes) => {
    setHighlightedNodes(nodes)
    // Highlight stays until next query (user can click empty space in graph to reset)
  }, [])

  return (
    <div className="app-layout">
      {/* Topbar */}
      <header className="topbar">
        <div className="topbar-icon" onClick={() => setSidebarOpen(v => !v)}>
          <svg viewBox="0 0 24 24">
            <rect x="3" y="6" width="18" height="2"/>
            <rect x="3" y="11" width="18" height="2"/>
            <rect x="3" y="16" width="18" height="2"/>
          </svg>
        </div>
        <span className="topbar-crumb">Mapping</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-crumb active">Order to Cash</span>
      </header>

      <div className="main-area">
        {/* Graph area */}
        <div className="graph-area">
          {/* Controls */}
          <div className="graph-controls">
            <button
              className="graph-btn"
              onClick={() => setSidebarOpen(v => !v)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15 3 21 3 21 9"/>
                <polyline points="9 21 3 21 3 15"/>
                <line x1="21" y1="3" x2="14" y2="10"/>
                <line x1="3" y1="21" x2="10" y2="14"/>
              </svg>
              {sidebarOpen ? 'Minimize' : 'Expand'}
            </button>
            <button
              className="graph-btn"
              onClick={() => setShowLegend(v => !v)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="7" height="7"/>
                <rect x="14" y="3" width="7" height="7"/>
                <rect x="14" y="14" width="7" height="7"/>
                <rect x="3" y="14" width="7" height="7"/>
              </svg>
              {showLegend ? 'Hide Granular Overlay' : 'Show Granular Overlay'}
            </button>
          </div>

          {/* Stats */}
          {stats && (
            <div className="stats-bar">
              <div className="stat-item">
                <div className="stat-num">{graphData?.nodes?.length || 0}</div>
                <div className="stat-label">Nodes</div>
              </div>
              <div className="stat-item">
                <div className="stat-num">{graphData?.edges?.length || 0}</div>
                <div className="stat-label">Edges</div>
              </div>
              <div className="stat-item">
                <div className="stat-num">{stats['Sales Orders'] || 0}</div>
                <div className="stat-label">Orders</div>
              </div>
              <div className="stat-item">
                <div className="stat-num">{stats['Billing Documents'] || 0}</div>
                <div className="stat-label">Invoices</div>
              </div>
            </div>
          )}

          {/* Legend */}
          {showLegend && (
            <div className="legend">
              <div className="legend-title">Entity Types</div>
              <div className="legend-items">
                {Object.entries(NODE_COLORS).map(([type, color]) => (
                  <div className="legend-item" key={type}>
                    <div className="legend-dot" style={{ background: color }} />
                    <span>{type.replace(/([A-Z])/g, ' $1').trim()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Highlight badge */}
          {highlightedNodes.length > 0 && (
            <div style={{
              position:'absolute', bottom:60, right:16, zIndex:5,
              background:'#1a1a18', color:'white', borderRadius:20,
              padding:'5px 14px', fontSize:12, fontWeight:500,
              display:'flex', alignItems:'center', gap:8,
              boxShadow:'0 2px 8px rgba(0,0,0,0.2)'
            }}>
              <span style={{width:8,height:8,borderRadius:'50%',background:'#f59e0b',display:'inline-block'}}/>
              {highlightedNodes.length} node{highlightedNodes.length>1?'s':''} highlighted
              <button
                onClick={() => setHighlightedNodes([])}
                style={{background:'none',border:'none',color:'#9b9b98',cursor:'pointer',fontSize:13,padding:0,marginLeft:4}}
              >✕</button>
            </div>
          )}

        {/* Graph */}
          {loading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column', gap: 12
            }}>
              <div style={{
                width: 36, height: 36, border: '3px solid #e5e5e3',
                borderTopColor: '#3b82f6', borderRadius: '50%',
                animation: 'spin 0.8s linear infinite'
              }} />
              <div style={{ fontSize: 13, color: '#9b9b98' }}>Loading graph…</div>
              <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
            </div>
          )}
          {error && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center'
            }}>
              <div style={{
                background: 'white', border: '1px solid #e5e5e3', borderRadius: 8,
                padding: '20px 24px', maxWidth: 320, textAlign: 'center'
              }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>⚠️</div>
                <div style={{ fontSize: 13, color: '#1a1a18', marginBottom: 8 }}>{error}</div>
                <div style={{ fontSize: 12, color: '#6b6b68' }}>
                  Run: <code>python backend/main.py</code>
                </div>
              </div>
            </div>
          )}
          {!loading && !error && graphData && (
            <GraphView
              graphData={graphData}
              highlightedNodes={highlightedNodes}
              showOverlay={showLegend}
              onNodeClick={() => {}}
            />
          )}
        </div>

        {/* Right panel */}
        {sidebarOpen && (
          <aside className="right-panel">
            <ChatPanel onHighlight={handleHighlight} />
          </aside>
        )}
      </div>
    </div>
  )
}
