import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType } from 'lightweight-charts'

const API = 'http://localhost:8000/api'
const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'VN30F1M', 'VN30']
const INTERVALS = ['1m', '5m', '15m', '1h']

export default function App() {
  const chartRef = useRef(null)
  const chartObjRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const rsiSeriesRef = useRef(null)
  const rsiChartRef = useRef(null)
  const rsiChartObjRef = useRef(null)

  const [symbol, setSymbol] = useState('BTC/USDT')
  const [interval, setInterval_] = useState('1m')
  const [latestRsi, setLatestRsi] = useState(null)
  const [alertState, setAlertState] = useState('neutral')
  const [loading, setLoading] = useState(false)
  const [paused, setPaused] = useState(false)
  const [alerts, setAlerts] = useState([])

  // Keep refs to always read latest symbol/interval inside async closures
  const symbolRef = useRef(symbol)
  const intervalRef = useRef(interval)
  useEffect(() => { symbolRef.current = symbol }, [symbol])
  useEffect(() => { intervalRef.current = interval }, [interval])

  // Fetch candle data from backend
  async function fetchCandles() {
    const sym = symbolRef.current
    const intv = intervalRef.current
    setLoading(true)
    try {
      let chartData
      if (sym === 'VN30F1M') {
        // VN30F1M uses dedicated endpoint with different data format
        const res = await fetch(`${API}/vn30f1m?res=${intv}&back=500`)
        if (!res.ok) {
          console.error(`VN30F1M fetch failed: ${res.status} ${res.statusText}`)
          return
        }
        const json = await res.json()
        chartData = json.data.map(d => {
          // Parse "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD" to Unix timestamp
          let ts
          if (d.time.includes(':')) {
            ts = new Date(d.time.replace(' ', 'T')).getTime() / 1000
          } else {
            ts = new Date(d.time + 'T00:00:00').getTime() / 1000
          }
          return {
            time: Math.floor(ts),
            open: parseFloat(d.open),
            high: parseFloat(d.high),
            low: parseFloat(d.low),
            close: parseFloat(d.close),
          }
        })
      } else {
        // BTC/ETH/SOL/VN30 all use standard OHLCV endpoint
        const res = await fetch(`${API}/ohlcv?symbol=${encodeURIComponent(sym)}&resolution=${intv}`)
        if (!res.ok) {
          console.error(`OHLCV fetch failed: ${res.status} ${res.statusText}`)
          return
        }
        const json = await res.json()
        chartData = json.data.map(d => ({
          time: Math.floor(d.time / 1000),
          open: parseFloat(d.open),
          high: parseFloat(d.high),
          low: parseFloat(d.low),
          close: parseFloat(d.close),
        }))
      }
      
      if (candleSeriesRef.current) {
        candleSeriesRef.current.setData(chartData)
      }
    } catch (e) {
      console.error('Fetch candles failed:', e)
    } finally {
      setLoading(false)
    }
  }

  // Switch symbol — clear old data immediately, then fetch new data
  async function switchSymbol(newSymbol) {
    // Clear old candle data immediately (no flash of old data)
    if (candleSeriesRef.current) {
      candleSeriesRef.current.setData([])
    }
    // Clear old RSI data immediately
    if (rsiSeriesRef.current) {
      rsiSeriesRef.current.setData([])
    }
    // Update refs so fetch functions read correct values
    symbolRef.current = newSymbol
    // Update state to trigger re-render
    setSymbol(newSymbol)
    // Fetch new data immediately (don't wait for useEffect)
    await fetchCandles()
    await fetchRsi()
  }

  // Fetch RSI data from backend
  async function fetchRsi() {
    const sym = symbolRef.current
    const intv = intervalRef.current
    try {
      // VN30F1M/VN30: no RSI from vnstock, skip RSI panel
      if (sym === 'VN30F1M' || sym === 'VN30') {
        setLatestRsi(null)
        setAlertState('neutral')
        return
      }
      const res = await fetch(`${API}/rsi?symbol=${encodeURIComponent(sym)}&interval=${intv}`)
      if (!res.ok) {
        console.error(`RSI fetch failed: ${res.status} ${res.statusText}`)
        return
      }
      const json = await res.json()
      
      const chartData = (json.data || []).map(d => ({
        time: Math.floor(d.time / 1000),
        value: parseFloat(d.rsi),
      }))

      if (rsiSeriesRef.current) {
        rsiSeriesRef.current.setData(chartData)
      }
      
      setLatestRsi(json.latest_rsi != null ? parseFloat(json.latest_rsi) : null)
      
      // Alert when state changes
      if (json.alert && json.alert !== alertState) {
        const newAlert = {
          time: new Date().toLocaleTimeString('vi-VN'),
          symbol: sym,
          type: json.alert,
          rsi: json.latest_rsi,
          timeframe: intv,
        }
        setAlerts(prev => [newAlert, ...prev].slice(0, 20))
      }
      setAlertState(json.alert || 'neutral')
    } catch (e) {
      console.error('Fetch RSI failed:', e)
    } finally {
      setLoading(false)
    }
  }

  // Initialize main chart
  useEffect(() => {
    if (!chartRef.current) return
    
    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 500,
      layout: {
        background: { type: ColorType.Solid, color: '#0a1020' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: 0 },
      priceScale: { borderColor: '#334155' },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    candleSeriesRef.current = candleSeries
    chartObjRef.current = chart

    // Resize observer
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width })
      }
    })
    ro.observe(chartRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [])

  // Initialize RSI sub-chart
  useEffect(() => {
    if (!rsiChartRef.current) return

    const rsiChart = createChart(rsiChartRef.current, {
      width: rsiChartRef.current.clientWidth,
      height: 150,
      layout: {
        background: { type: ColorType.Solid, color: '#0b1220' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      priceScale: { borderColor: '#334155' },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
    })

    const rsiSeries = rsiChart.addLineSeries({
      color: '#a78bfa',
      lineWidth: 2,
    })

    // Overbought/Oversold lines
    rsiSeries.createPriceLine({
      price: 70,
      color: '#ef4444',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: 'Quá mua (70)',
    })

    rsiSeries.createPriceLine({
      price: 30,
      color: '#22c55e',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: 'Quá bán (30)',
    })

    rsiSeriesRef.current = rsiSeries
    rsiChartObjRef.current = rsiChart

    const ro2 = new ResizeObserver(entries => {
      for (const entry of entries) {
        rsiChart.applyOptions({ width: entry.contentRect.width })
      }
    })
    ro2.observe(rsiChartRef.current)

    return () => {
      ro2.disconnect()
      rsiChart.remove()
    }
  }, [])

  // Load data on mount or symbol/interval change
  useEffect(() => {
    fetchCandles()
    fetchRsi()
  }, [symbol, interval])

  // Auto-refresh every 10s
  useEffect(() => {
    if (paused) return
    const timer = setInterval(() => {
      fetchCandles()
      fetchRsi()
    }, 10000)
    return () => clearInterval(timer)
  }, [symbol, interval, paused])

  // Sync time scales between charts
  useEffect(() => {
    const mainChart = chartObjRef.current
    const rsiChart = rsiChartObjRef.current
    if (!mainChart || !rsiChart) return

    let syncingMainToRsi = false
    let syncingRsiToMain = false

    mainChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (!range || syncingRsiToMain) return
      syncingRsiToMain = true
      rsiChart.timeScale().setVisibleLogicalRange(range)
      queueMicrotask(() => { syncingRsiToMain = false })
    })

    rsiChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (!range || syncingMainToRsi) return
      syncingMainToRsi = true
      mainChart.timeScale().setVisibleLogicalRange(range)
      queueMicrotask(() => { syncingMainToRsi = false })
    })

    return () => {
      // Cleanup subscriptions handled by chart.remove() in the init effects
    }
  }, [])

  const alertColor = alertState === 'oversold' ? '#ef4444' : alertState === 'overbought' ? '#22c55e' : '#94a3b8'
  const alertLabel = alertState === 'oversold' ? 'QUÁ BÁN' : alertState === 'overbought' ? 'QUÁ MUA' : 'TRUNG LẬP'

  return (
    <div style={styles.container}>
      {/* Top bar */}
      <div style={styles.topBar}>
        <span style={styles.logo}>📊 TradingViewKai</span>
        
        <select value={symbol} onChange={e => switchSymbol(e.target.value)} style={styles.select}>
          {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        {INTERVALS.map(iv => (
          <button
            key={iv}
            onClick={() => setInterval_(iv)}
            style={{ ...styles.btn, ...(interval === iv ? styles.btnActive : {}) }}
          >{iv}</button>
        ))}

        <button onClick={() => setPaused(!paused)} style={styles.btn}>
          {paused ? '▶ Resume' : '⏸ Pause'}
        </button>
        <button onClick={() => { fetchCandles(); fetchRsi() }} style={styles.btn}>🔄</button>
        
        {loading && <span style={{ color: '#94a3b8', fontSize: 12 }}>Loading...</span>}
      </div>

      {/* Main content */}
      <div style={styles.main}>
        {/* Watchlist */}
        <div style={styles.watchlist}>
          <div style={styles.watchlistTitle}>WATCHLIST</div>
          {SYMBOLS.map(s => (
            <div
              key={s}
              onClick={() => switchSymbol(s)}
              style={{ ...styles.watchItem, ...(symbol === s ? styles.watchItemActive : {}) }}
            >
              <span>{s}</span>
              <span style={{ color: '#22c55e', fontSize: 8 }}>●</span>
            </div>
          ))}
        </div>

        {/* Chart + RSI */}
        <div style={styles.chartArea}>
          <div style={styles.symbolHeader}>
            <h2 style={{ margin: 0, color: '#e2e8f0' }}>{symbol}</h2>
            <span style={{ fontSize: 14, color: alertColor, fontWeight: 'bold' }}>
              {alertLabel} {latestRsi !== null ? `RSI=${latestRsi}` : ''}
            </span>
          </div>

          <div ref={chartRef} style={styles.chartContainer} />
          
          <div style={{ height: 16 }} />
          <div style={styles.rsiLabel}>RSI (14)</div>
          <div ref={rsiChartRef} style={styles.rsiChartContainer} />
        </div>

        {/* Alert panel */}
        <div style={styles.alertPanel}>
          <div style={styles.watchlistTitle}>CẢNH BÁO</div>
          {alerts.length === 0 ? (
            <div style={{ color: '#64748b', fontSize: 13 }}>Chưa có cảnh báo</div>
          ) : (
            alerts.map((a, i) => (
              <div key={i} style={styles.alertItem}>
                <span style={{ 
                  color: a.type === 'oversold' ? '#ef4444' : '#22c55e', 
                  fontWeight: 'bold' 
                }}>
                  {a.type === 'oversold' ? '⬇ QUÁ BÁN' : '⬆ QUÁ MUA'}
                </span>
                <span>{a.symbol} RSI={a.rsi}</span>
                <span style={{ color: '#64748b', fontSize: 12 }}>{a.timeframe}</span>
                <span style={{ color: '#64748b', fontSize: 11 }}>{a.time}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

const styles = {
  container: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    background: '#0a1020',
    color: '#e2e8f0',
    minHeight: '100vh',
  },
  topBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '10px 16px',
    background: '#0f172a',
    borderBottom: '1px solid #1e293b',
    flexWrap: 'wrap',
  },
  logo: {
    fontWeight: 'bold',
    fontSize: 16,
    color: '#38bdf8',
  },
  select: {
    background: '#1e293b',
    color: '#e2e8f0',
    border: '1px solid #334155',
    borderRadius: 6,
    padding: '6px 10px',
    fontSize: 14,
  },
  btn: {
    background: '#1e293b',
    color: '#94a3b8',
    border: '1px solid #334155',
    borderRadius: 6,
    padding: '6px 12px',
    cursor: 'pointer',
    fontSize: 13,
  },
  btnActive: {
    background: '#38bdf8',
    color: '#0a1020',
    fontWeight: 'bold',
  },
  main: {
    display: 'flex',
    gap: 0,
    height: 'calc(100vh - 52px)',
  },
  watchlist: {
    width: 160,
    background: '#0f172a',
    borderRight: '1px solid #1e293b',
    padding: '12px 8px',
    flexShrink: 0,
  },
  watchlistTitle: {
    fontSize: 11,
    fontWeight: 'bold',
    color: '#64748b',
    letterSpacing: 1.5,
    marginBottom: 8,
    padding: '0 8px',
  },
  watchItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 8px',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    color: '#94a3b8',
  },
  watchItemActive: {
    background: '#1e293b',
    color: '#38bdf8',
  },
  chartArea: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  symbolHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 16px',
    background: '#0f172a',
    borderBottom: '1px solid #1e293b',
  },
  chartContainer: {
    flex: 1,
    minWidth: 0,
  },
  rsiLabel: {
    padding: '4px 16px',
    fontSize: 11,
    color: '#a78bfa',
    fontWeight: 'bold',
    background: '#0b1220',
  },
  rsiChartContainer: {
    height: 150,
    background: '#0b1220',
    borderTop: '1px solid #1e293b',
  },
  alertPanel: {
    width: 240,
    background: '#0f172a',
    borderLeft: '1px solid #1e293b',
    padding: '12px 8px',
    overflowY: 'auto',
    flexShrink: 0,
  },
  alertItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    padding: '8px',
    marginBottom: 6,
    background: '#1e293b',
    borderRadius: 6,
    fontSize: 12,
    color: '#cbd5e1',
  },
}
