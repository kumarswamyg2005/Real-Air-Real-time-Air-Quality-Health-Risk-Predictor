import { useEffect, useState } from 'react'
import { postHealthRisk } from '../api/client.js'

const LEVEL_THEMES = {
  Safe:      { color: '#6EE7B7', bg: 'rgba(110, 231, 183, 0.06)', border: 'rgba(110, 231, 183, 0.2)' },
  Moderate:  { color: '#FDE047', bg: 'rgba(253, 224, 71, 0.06)',  border: 'rgba(253, 224, 71, 0.22)' },
  Unhealthy: { color: '#FB923C', bg: 'rgba(251, 146, 60, 0.06)',  border: 'rgba(251, 146, 60, 0.22)' },
  Hazardous: { color: '#F87171', bg: 'rgba(248, 113, 113, 0.08)', border: 'rgba(248, 113, 113, 0.28)' },
}

export default function HealthAlert({ city }) {
  const [profile, setProfile] = useState({ age_group: 'adult', condition: 'none' })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    postHealthRisk({ city, ...profile })
      .then(r => alive && setResult(r))
      .catch(() => alive && setResult(null))
      .finally(() => alive && setLoading(false))
  }, [city, profile])

  const theme = result ? LEVEL_THEMES[result.level] || LEVEL_THEMES.Moderate : LEVEL_THEMES.Moderate

  return (
    <div className="health">
      <div className="health-form">
        <div className="health-field">
          <label>Age Bracket</label>
          <select value={profile.age_group} onChange={e => setProfile(p => ({ ...p, age_group: e.target.value }))}>
            <option value="child">Child · under 12</option>
            <option value="adult">Adult · 12 to 60</option>
            <option value="elderly">Elderly · 60 plus</option>
          </select>
        </div>
        <div className="health-field">
          <label>Pre-existing Condition</label>
          <select value={profile.condition} onChange={e => setProfile(p => ({ ...p, condition: e.target.value }))}>
            <option value="none">None</option>
            <option value="asthma">Asthma · Respiratory</option>
            <option value="heart_disease">Cardiovascular</option>
            <option value="diabetes">Diabetes</option>
          </select>
        </div>
      </div>

      {loading && <div className="empty" style={{ padding: '32px' }}>Analysing exposure profile…</div>}

      {result && !loading && (
        <div
          className="alert fade-in"
          style={{
            '--alert-color': theme.color,
            '--alert-bg': theme.bg,
            '--alert-border': theme.border,
          }}
        >
          <div className="alert-eyebrow">Risk Level · {result.level}</div>
          <h3 className="alert-title">{result.headline}</h3>
          <ul className="alert-list">
            {result.recommendations.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          {result.next_24h_level && (
            <div className="alert-foot">
              <span>Next 24h Outlook</span>
              <strong>{result.next_24h_level}</strong>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
