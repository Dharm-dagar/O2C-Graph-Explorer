import { useEffect, useRef, useCallback, useState } from 'react'
import * as d3 from 'd3'

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

const NODE_RADIUS = {
  SalesOrder:     7,
  BillingDocument:7,
  Delivery:       6,
  JournalEntry:   6,
  Payment:        5,
  Customer:       9,
  Product:        5,
  Plant:          6,
}

export default function GraphView({ graphData, highlightedNodes, showOverlay = true, onNodeClick }) {
  const svgRef = useRef(null)
  const gRef = useRef(null)           // main <g> for zoom
  const nodesRef = useRef(null)       // d3 selection of node groups
  const linksRef = useRef(null)       // d3 selection of links
  const simulationRef = useRef(null)
  const zoomRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)

  useEffect(() => {
    if (!graphData || !svgRef.current) return

    const container = svgRef.current.parentElement
    const W = container.clientWidth
    const H = container.clientHeight

    d3.select(svgRef.current).selectAll('*').remove()
    if (simulationRef.current) simulationRef.current.stop()

    const svg = d3.select(svgRef.current)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('width', W)
      .attr('height', H)

    // ── defs: glow filter ───────────────────────────────────────────────────
    const defs = svg.append('defs')
    defs.append('filter')
      .attr('id', 'glow')
      .html(`
        <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
        <feMerge>
          <feMergeNode in="coloredBlur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      `)

    // ── zoom ────────────────────────────────────────────────────────────────
    const g = svg.append('g')
    gRef.current = g

    const zoom = d3.zoom()
      .scaleExtent([0.05, 5])
      .on('zoom', (event) => g.attr('transform', event.transform))
    zoomRef.current = zoom
    svg.call(zoom)

    const nodes = graphData.nodes.map(n => ({ ...n }))
    const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]))

    const links = graphData.edges
      .filter(e => nodeMap[e.source] && nodeMap[e.target])
      .map(e => ({ ...e, source: nodeMap[e.source], target: nodeMap[e.target] }))

    // ── simulation ──────────────────────────────────────────────────────────
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(65).strength(0.4))
      .force('charge', d3.forceManyBody().strength(-180))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collision', d3.forceCollide(d => (NODE_RADIUS[d.type] || 5) + 4))
      .force('x', d3.forceX(W / 2).strength(0.03))
      .force('y', d3.forceY(H / 2).strength(0.03))
      .alphaDecay(0.02)
    simulationRef.current = simulation

    // ── links ───────────────────────────────────────────────────────────────
    const link = g.append('g').attr('class', 'links')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('class', 'link')
      .attr('stroke', 'rgba(147,197,253,0.4)')
      .attr('stroke-width', 1)
    linksRef.current = link

    // ── nodes ───────────────────────────────────────────────────────────────
    const node = g.append('g').attr('class', 'nodes')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .call(
        d3.drag()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x; d.fy = d.y
          })
          .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null; d.fy = null
          })
      )
    nodesRef.current = node

    // pulse ring (hidden by default)
    node.append('circle')
      .attr('class', 'pulse-ring')
      .attr('r', d => (NODE_RADIUS[d.type] || 5) + 6)
      .attr('fill', 'none')
      .attr('stroke', d => NODE_COLORS[d.type] || '#999')
      .attr('stroke-width', 2)
      .attr('opacity', 0)

    // main circle
    node.append('circle')
      .attr('class', 'main-circle')
      .attr('r', d => NODE_RADIUS[d.type] || 5)
      .attr('fill', d => NODE_COLORS[d.type] || '#999')
      .attr('stroke', 'white')
      .attr('stroke-width', 1.5)
      .style('cursor', 'pointer')

    // labels for hub nodes
    node.filter(d => ['Customer', 'SalesOrder'].includes(d.type))
      .append('text')
      .attr('class', 'node-label')
      .attr('dy', d => -(NODE_RADIUS[d.type] || 5) - 3)
      .attr('text-anchor', 'middle')
      .attr('font-size', '8px')
      .attr('fill', '#9b9b98')
      .text(d => d.label.slice(0, 12))

    // click
    node.on('click', function(event, d) {
      event.stopPropagation()
      const rect = svgRef.current.getBoundingClientRect()
      const px = event.clientX - rect.left
      const py = event.clientY - rect.top
      setTooltip({ node: d, x: Math.min(px + 12, W - 360), y: Math.min(py - 10, H - 380) })
      if (onNodeClick) onNodeClick(d)
    })

    svg.on('click', () => setTooltip(null))

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    return () => simulation.stop()
  }, [graphData])

  // ── Highlight effect ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!nodesRef.current || !linksRef.current || !svgRef.current) return

    const hlSet = new Set(highlightedNodes || [])
    const hasHighlight = hlSet.size > 0

    // Dim / brighten nodes
    nodesRef.current
      .select('.main-circle')
      .transition().duration(300)
      .attr('opacity', d => !hasHighlight ? 1 : hlSet.has(d.id) ? 1 : 0.12)
      .attr('r', d => hlSet.has(d.id)
        ? (NODE_RADIUS[d.type] || 5) + 3
        : (NODE_RADIUS[d.type] || 5))

    // Pulse rings on highlighted nodes
    nodesRef.current
      .select('.pulse-ring')
      .transition().duration(300)
      .attr('opacity', d => hlSet.has(d.id) ? 0.7 : 0)
      .attr('r', d => (NODE_RADIUS[d.type] || 5) + 7)

    // Animated pulse for highlighted
    nodesRef.current.filter(d => hlSet.has(d.id))
      .select('.pulse-ring')
      .attr('opacity', 0.8)
      .attr('r', d => (NODE_RADIUS[d.type] || 5) + 4)

    // Glow filter on highlighted
    nodesRef.current
      .select('.main-circle')
      .attr('filter', d => hlSet.has(d.id) ? 'url(#glow)' : null)

    // Highlight connecting edges
    linksRef.current
      .transition().duration(300)
      .attr('stroke', d => {
        const srcId = typeof d.source === 'object' ? d.source.id : d.source
        const tgtId = typeof d.target === 'object' ? d.target.id : d.target
        if (!hasHighlight) return 'rgba(147,197,253,0.4)'
        if (hlSet.has(srcId) && hlSet.has(tgtId)) return '#f59e0b'  // amber = highlighted edge
        if (hlSet.has(srcId) || hlSet.has(tgtId)) return 'rgba(147,197,253,0.35)'
        return 'rgba(147,197,253,0.08)'
      })
      .attr('stroke-width', d => {
        const srcId = typeof d.source === 'object' ? d.source.id : d.source
        const tgtId = typeof d.target === 'object' ? d.target.id : d.target
        if (hlSet.has(srcId) && hlSet.has(tgtId)) return 2.5
        return 1
      })
      .attr('opacity', d => {
        if (!hasHighlight) return 1
        const srcId = typeof d.source === 'object' ? d.source.id : d.source
        const tgtId = typeof d.target === 'object' ? d.target.id : d.target
        return (hlSet.has(srcId) && hlSet.has(tgtId)) ? 1 : 0.2
      })

    // Zoom to fit highlighted nodes
    if (hasHighlight && gRef.current && zoomRef.current && svgRef.current) {
      const svg = d3.select(svgRef.current)
      const container = svgRef.current.parentElement
      const W = container.clientWidth
      const H = container.clientHeight

      // Find positions of highlighted nodes
      const positions = []
      nodesRef.current.each(d => {
        if (hlSet.has(d.id) && d.x != null && d.y != null) {
          positions.push([d.x, d.y])
        }
      })

      if (positions.length > 0) {
        const xs = positions.map(p => p[0])
        const ys = positions.map(p => p[1])
        const minX = Math.min(...xs), maxX = Math.max(...xs)
        const minY = Math.min(...ys), maxY = Math.max(...ys)
        const padX = Math.max(80, (maxX - minX) * 0.6)
        const padY = Math.max(80, (maxY - minY) * 0.6)

        const bW = maxX - minX + padX * 2
        const bH = maxY - minY + padY * 2
        const scale = Math.min(W / bW, H / bH, 3)
        const tx = W / 2 - scale * ((minX + maxX) / 2)
        const ty = H / 2 - scale * ((minY + maxY) / 2)

        svg.transition().duration(700).ease(d3.easeCubicOut)
          .call(zoomRef.current.transform, d3.zoomIdentity.translate(tx, ty).scale(scale))
      }
    }

    // Reset zoom when highlight is cleared
    if (!hasHighlight && gRef.current && zoomRef.current && svgRef.current) {
      // don't auto-reset zoom — let user stay where they are
    }

  }, [highlightedNodes])

  const closeTooltip = useCallback(() => setTooltip(null), [])

  const renderTooltip = () => {
    if (!tooltip) return null
    const { node, x, y } = tooltip
    const props = node.properties || {}

    const fieldMap = {
      SalesOrder: [['Sales Order','salesOrder'],['Sold To','soldToParty'],['Amount','totalNetAmount'],['Currency','transactionCurrency'],['Delivery Status','overallDeliveryStatus'],['Billing Status','overallOrdReltdBillgStatus'],['Created','creationDate']],
      BillingDocument: [['Billing Doc','billingDocument'],['Sold To','soldToParty'],['Amount','totalNetAmount'],['Currency','transactionCurrency'],['Accounting Doc','accountingDocument'],['Cancelled','billingDocumentIsCancelled'],['Date','billingDocumentDate']],
      Delivery: [['Delivery Doc','deliveryDocument'],['GI Date','actualGoodsMovementDate'],['GI Status','overallGoodsMovementStatus'],['Picking Status','overallPickingStatus'],['Shipping Point','shippingPoint']],
      JournalEntry: [['Accounting Doc','accountingDocument'],['Company Code','companyCode'],['Fiscal Year','fiscalYear'],['Doc Type','accountingDocumentType'],['Amount','amountInCompanyCodeCurrency'],['Currency','companyCodeCurrency'],['Posting Date','postingDate']],
      Payment: [['Payment Doc','accountingDocument'],['Customer','customer'],['Amount','amountInCompanyCodeCurrency'],['Currency','companyCodeCurrency'],['Clearing Date','clearingDate']],
      Customer: [['Partner','businessPartner'],['Customer ID','customer'],['Full Name','businessPartnerFullName'],['Org Name','organizationBpName1'],['Industry','industry']],
      Product: [['Product','product'],['Description','productDescription'],['Type','productType'],['Group','productGroup'],['Base Unit','baseUnit']],
      Plant: [['Plant','plant'],['Name','plantName'],['City','cityName'],['Country','country']],
    }

    const fields = fieldMap[node.type] || Object.keys(props).slice(0, 6).map(k => [k, k])
    const shown = fields.filter(([, key]) => props[key] != null && props[key] !== '')
    const extra = Object.keys(props).length - shown.length

    const connections = graphData?.edges?.filter(e =>
      e.source === node.id || e.target === node.id ||
      e.source?.id === node.id || e.target?.id === node.id
    ).length || 0

    const fmt = v => {
      if (typeof v === 'string' && v.includes('T00:00:00')) return v.split('T')[0]
      return String(v)
    }

    const isHighlighted = (highlightedNodes || []).includes(node.id)

    return (
      <div
        className="node-tooltip"
        style={{ left: x, top: y, border: isHighlighted ? `2px solid ${NODE_COLORS[node.type]}` : undefined }}
        onClick={e => e.stopPropagation()}
      >
        <button className="tooltip-close" onClick={closeTooltip}>✕</button>
        <div className="tooltip-title">
          <span style={{ color: NODE_COLORS[node.type], marginRight: 6 }}>●</span>
          {node.type}
          {isHighlighted && (
            <span style={{
              marginLeft: 8, fontSize: 10, background: '#fef3c7',
              color: '#92400e', padding: '1px 6px', borderRadius: 4, fontWeight: 600
            }}>HIGHLIGHTED</span>
          )}
        </div>
        {shown.map(([label, key]) => (
          <div className="tooltip-row" key={key}>
            <span className="tooltip-key">{label}:</span>
            <span className="tooltip-val">{fmt(props[key])}</span>
          </div>
        ))}
        {extra > 0 && <div className="tooltip-more">+{extra} additional fields hidden for readability</div>}
        <div className="tooltip-connections">Connections: {connections}</div>
      </div>
    )
  }

  return (
    <>
      <svg ref={svgRef} className="graph-svg" />
      {renderTooltip()}
    </>
  )
}
