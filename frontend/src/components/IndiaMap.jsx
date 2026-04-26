import { MapContainer, TileLayer, CircleMarker, Marker, Tooltip, useMap } from 'react-leaflet'
import { useEffect, useMemo } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

function FlyTo({ city, cities }) {
  const map = useMap()
  useEffect(() => {
    const c = cities.find(x => x.city === city)
    if (c) map.flyTo([c.lat, c.lon], 8, { duration: 1.5, easeLinearity: 0.2 })
  }, [city])
  return null
}

const SCALE = [
  { lo: 0,   label: '0',   color: '#6EE7B7' },
  { lo: 51,  label: '51',  color: '#BEF264' },
  { lo: 101, label: '101', color: '#FDE047' },
  { lo: 201, label: '201', color: '#FB923C' },
  { lo: 301, label: '301', color: '#F87171' },
  { lo: 401, label: '401+', color: '#B91C1C' },
]

export default function IndiaMap({ cities, selected, onSelect }) {
  const activeCity = cities.find(c => c.city === selected)

  const activeIcon = useMemo(() => {
    if (!activeCity) return null
    const color = activeCity.color || '#FF8A3D'
    return L.divIcon({
      className: '',
      html: `<div class="cam-wrap" style="--mc:${color}">
        <div class="cam-ring cam-r2"></div>
        <div class="cam-ring cam-r1"></div>
        <div class="cam-core"></div>
      </div>`,
      iconSize: [64, 64],
      iconAnchor: [32, 32],
      tooltipAnchor: [0, -34],
    })
  }, [selected, activeCity?.color])

  return (
    <div className="mapcard">
      <MapContainer
        center={[22.0, 80.0]}
        zoom={4.6}
        zoomControl={true}
        scrollWheelZoom
        style={{ height: '100%', width: '100%' }}
        worldCopyJump={false}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
          subdomains={['a', 'b', 'c', 'd']}
        />
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png"
          opacity={0.55}
        />
        <FlyTo city={selected} cities={cities} />

        {cities.map(c => {
          if (c.city === selected) return null
          return (
            <CircleMarker
              key={c.city}
              center={[c.lat, c.lon]}
              radius={7}
              pathOptions={{
                color: c.color || '#52525B',
                weight: 1.5,
                fillColor: c.color || '#52525B',
                fillOpacity: 0.62,
              }}
              eventHandlers={{ click: () => onSelect(c.city) }}
            >
              <Tooltip direction="top" offset={[0, -8]} className="tooltip-card" opacity={1} permanent={false}>
                <div className="t-name">{c.city}</div>
                <div className="t-aqi">AQI {c.aqi != null ? Math.round(c.aqi) : '—'} · {c.category}</div>
              </Tooltip>
            </CircleMarker>
          )
        })}

        {activeCity && activeIcon && (
          <Marker
            position={[activeCity.lat, activeCity.lon]}
            icon={activeIcon}
            zIndexOffset={1000}
            eventHandlers={{ click: () => onSelect(activeCity.city) }}
          >
            <Tooltip
              direction="top"
              offset={[0, -8]}
              className="tooltip-card tooltip-pinned"
              opacity={1}
              permanent
            >
              <div className="t-name">{activeCity.city}</div>
              <div className="t-aqi" style={{ color: activeCity.color }}>
                AQI {activeCity.aqi != null ? Math.round(activeCity.aqi) : '—'}
                <span style={{ color: 'var(--mute)', marginLeft: 6 }}>· {activeCity.category}</span>
              </div>
            </Tooltip>
          </Marker>
        )}
      </MapContainer>

      <div className="map-overlay tl">
        <div className="map-eyebrow">Geo / Network</div>
        <div className="map-title">Air across the subcontinent</div>
      </div>

      <div className="map-overlay bl">
        <div className="scale">
          {SCALE.map(s => (
            <div key={s.lo} className="scale-step" style={{ background: s.color }}>{s.label}</div>
          ))}
        </div>
      </div>
    </div>
  )
}
