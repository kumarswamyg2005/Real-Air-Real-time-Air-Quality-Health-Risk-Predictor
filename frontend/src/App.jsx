import { useEffect, useMemo, useState } from 'react'
import IndiaMap from './components/IndiaMap.jsx'
import HeroCard from './components/HeroCard.jsx'
import ForecastCard from './components/ForecastCard.jsx'
import HealthAlert from './components/HealthAlert.jsx'
import HistoricalTrends from './components/HistoricalTrends.jsx'
import { fetchCities, triggerRefresh } from './api/client.js'
import { fmtRelative } from './lib/aqi.js'

export default function App() {
  const [cities, setCities] = useState([])
  const [selected, setSelected] = useState(null)
  const [tab, setTab] = useState('forecast')
  const [now, setNow] = useState(new Date())

  const load = async () => {
    try {
      const data = await fetchCities()
      setCities(data)
      setSelected(prev => prev ?? data[0]?.city ?? null)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    load()
    const t1 = setInterval(load, 60_000)
    const t2 = setInterval(() => setNow(new Date()), 30_000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [])

  const onRefresh = async () => {
    await triggerRefresh()
    setTimeout(load, 2500)
  }

  const lastUpdate = useMemo(() => {
    const stamps = cities.map(c => c.updated_at).filter(Boolean).map(t => +new Date(t))
    if (!stamps.length) return null
    return new Date(Math.max(...stamps)).toISOString()
  }, [cities])

  const selectedCity = cities.find(c => c.city === selected)

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="mark">Real-Air</span>
          <span className="meta">Indian Subcontinent · {cities.length || '—'} cities</span>
        </div>
        <div className="topbar-right">
          <span><span className="live-dot" />Live · {now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })} IST</span>
          <span>Updated {fmtRelative(lastUpdate) || '—'}</span>
          <button className="refresh-link" onClick={onRefresh}>Refresh ↻</button>
        </div>
      </header>

      <nav className="rail" role="tablist" aria-label="Cities">
        {cities.map(c => (
          <button
            key={c.city}
            className={`pill ${c.city === selected ? 'active' : ''}`}
            onClick={() => setSelected(c.city)}
          >
            <span className="pip" style={{ background: c.color }} />
            <span>{c.city}</span>
            <span className="aqi">{c.aqi != null ? Math.round(c.aqi) : '—'}</span>
          </button>
        ))}
      </nav>

      <main className="canvas">
        <section className="col-left">
          {selectedCity && <HeroCard city={selectedCity} />}

          <article className="section fade-in">
            <div className="tabs">
              <button className={`tab ${tab === 'forecast' ? 'active' : ''}`} onClick={() => setTab('forecast')}>
                <span className="num">01</span>Forecast
              </button>
              <button className={`tab ${tab === 'health' ? 'active' : ''}`} onClick={() => setTab('health')}>
                <span className="num">02</span>Personal Risk
              </button>
              <button className={`tab ${tab === 'history' ? 'active' : ''}`} onClick={() => setTab('history')}>
                <span className="num">03</span>Historical
              </button>
            </div>
            {selected && tab === 'forecast' && <ForecastCard city={selected} />}
            {selected && tab === 'health' && <HealthAlert city={selected} />}
            {selected && tab === 'history' && <HistoricalTrends city={selected} />}
          </article>
        </section>

        <aside className="col-right">
          <IndiaMap cities={cities} selected={selected} onSelect={setSelected} />
        </aside>
      </main>

      <footer className="footer">
        <div className="left">
          <span>OpenAQ · Open-Meteo</span>
          <span>Forecast · LSTM + Prophet</span>
        </div>
        <div>India NAAQS · CPCB scale</div>
      </footer>
    </div>
  )
}
