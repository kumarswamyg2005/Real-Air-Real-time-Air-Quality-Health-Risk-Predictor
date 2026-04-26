import { useEffect, useState } from 'react'
import { fetchCurrent } from '../api/client.js'
import { aqiBand, aqiTint, fmtTime } from '../lib/aqi.js'

function useCount(target, duration = 800) {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (target == null) { setN(null); return }
    const start = performance.now()
    let raf
    const loop = (t) => {
      const k = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - k, 3)
      setN(Math.round(target * eased))
      if (k < 1) raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return n
}

export default function HeroCard({ city }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchCurrent(city.city)
      .then(d => alive && setData(d))
      .catch(() => alive && setData(null))
      .finally(() => alive && setLoading(false))
  }, [city.city])

  const aqi = data?.aqi ?? city.aqi ?? null
  const band = aqiBand(aqi)
  const tint = aqiTint(aqi)
  const animated = useCount(aqi)

  return (
    <article
      className="hero fade-in"
      style={{ '--hero-tint': tint, '--hero-color': band.color }}
    >
      <div className="hero-eyebrow">
        <span>City File · {String((Math.random() * 999) | 0).padStart(3, '0')}</span>
        <span className="div" />
        <span>{fmtTime(data?.timestamp || city.updated_at)}</span>
      </div>

      <h1 className="hero-name">
        {city.city}<em>↗</em>
      </h1>

      <div className="hero-row">
        <div className="hero-aqi">
          <div className="number">
            {loading ? '…' : (aqi == null ? '—' : animated)}
            <span className="unit">AQI</span>
          </div>
          <div className="label">
            <span className="dot" />
            <span>{band.label}</span>
            <span style={{ color: 'var(--mute-3)' }}>·</span>
            <span>India NAAQS</span>
          </div>
        </div>

        <div className="hero-stats">
          <div className="stat">
            <div className="k">PM 2.5</div>
            <div className="v">{data?.pm25 ?? '—'}<sup>µg/m³</sup></div>
          </div>
          <div className="stat">
            <div className="k">PM 10</div>
            <div className="v">{data?.pm10 ?? '—'}<sup>µg/m³</sup></div>
          </div>
          <div className="stat">
            <div className="k">NO₂</div>
            <div className="v">{data?.no2 ?? '—'}<sup>µg/m³</sup></div>
          </div>
          <div className="stat">
            <div className="k">Temp</div>
            <div className="v">{data?.temperature ?? '—'}<sup>°C</sup></div>
          </div>
          <div className="stat">
            <div className="k">Humidity</div>
            <div className="v">{data?.humidity ?? '—'}<sup>%</sup></div>
          </div>
          <div className="stat">
            <div className="k">Wind</div>
            <div className="v">{data?.wind_speed ?? '—'}<sup>km/h</sup></div>
          </div>
        </div>
      </div>

      <div className="hero-foot">
        <span>{city.lat?.toFixed(2)}° N <span className="sep">/</span> {city.lon?.toFixed(2)}° E</span>
        <span className="sep">—</span>
        <span>Source · OpenAQ</span>
        <span className="sep">—</span>
        <span>Forecast · LSTM 72→48h</span>
      </div>
    </article>
  )
}
