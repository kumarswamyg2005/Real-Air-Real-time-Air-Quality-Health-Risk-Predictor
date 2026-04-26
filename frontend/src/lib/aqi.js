export const AQI_BANDS = [
  { min: 0,   max: 50,  label: 'Good',          color: '#6EE7B7' },
  { min: 51,  max: 100, label: 'Satisfactory',  color: '#BEF264' },
  { min: 101, max: 200, label: 'Moderate',      color: '#FDE047' },
  { min: 201, max: 300, label: 'Poor',          color: '#FB923C' },
  { min: 301, max: 400, label: 'Very Poor',     color: '#F87171' },
  { min: 401, max: 1000, label: 'Severe',       color: '#B91C1C' },
]

export function aqiBand(aqi) {
  if (aqi == null || isNaN(aqi)) return { label: 'No data', color: '#52525B' }
  return AQI_BANDS.find(b => aqi >= b.min && aqi <= b.max) || AQI_BANDS[AQI_BANDS.length - 1]
}

export function aqiTint(aqi) {
  const c = aqiBand(aqi).color
  // hex → rgba 18% as background tint
  const m = c.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i)
  if (!m) return 'rgba(255,138,61,0.18)'
  const [r, g, b] = m.slice(1).map(x => parseInt(x, 16))
  return `rgba(${r},${g},${b},0.18)`
}

export function fmtTime(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
  } catch { return '—' }
}

export function fmtRelative(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = Date.now()
  const min = Math.round((now - d.getTime()) / 60000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr} hr ago`
  return `${Math.round(hr / 24)} d ago`
}
