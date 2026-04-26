import { useEffect, useState } from 'react'
import { fetchForecast } from '../api/client.js'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  Filler, Tooltip,
} from 'chart.js'
import { Line } from 'react-chartjs-2'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

ChartJS.defaults.font.family = "'Inter', sans-serif"
ChartJS.defaults.color = '#71717A'

export default function ForecastCard({ city }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchForecast(city)
      .then(d => alive && setData(d))
      .catch(() => alive && setData([]))
      .finally(() => alive && setLoading(false))
  }, [city])

  const labels = data.map(d => `+${d.hour}h`)
  const lstm = data.map(d => d.pm25_lstm)
  const prophet = data.map(d => d.pm25_prophet)

  const chartData = {
    labels,
    datasets: [
      {
        label: 'LSTM',
        data: lstm,
        borderColor: '#FF8A3D',
        backgroundColor: (ctx) => {
          const { chartArea } = ctx.chart
          if (!chartArea) return 'rgba(255, 138, 61, 0.10)'
          const g = ctx.chart.ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
          g.addColorStop(0, 'rgba(255, 138, 61, 0.32)')
          g.addColorStop(1, 'rgba(255, 138, 61, 0)')
          return g
        },
        borderWidth: 1.75,
        tension: 0.42,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#FF8A3D',
        pointHoverBorderColor: '#0A0A0B',
        pointHoverBorderWidth: 2,
      },
      {
        label: 'Prophet',
        data: prophet,
        borderColor: '#E5E5E4',
        backgroundColor: 'transparent',
        borderWidth: 1,
        borderDash: [3, 4],
        tension: 0.42,
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: '#E5E5E4',
      },
    ],
  }

  const chartOptions = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#16161A',
        borderColor: 'rgba(255,255,255,0.10)',
        borderWidth: 1,
        padding: 12,
        titleFont: { size: 11, weight: 500, family: "'JetBrains Mono', monospace" },
        bodyFont: { size: 12, family: "'Inter', sans-serif" },
        titleColor: '#A1A1AA',
        bodyColor: '#FAFAF9',
        displayColors: true,
        boxWidth: 8, boxHeight: 8, boxPadding: 6,
        cornerRadius: 6,
        callbacks: {
          label: (ctx) => `  ${ctx.dataset.label}   ${ctx.parsed.y?.toFixed(1)} µg/m³`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          color: '#52525B',
          font: { size: 10, family: "'JetBrains Mono', monospace" },
          maxTicksLimit: 9,
        },
        border: { color: 'rgba(255,255,255,0.10)' },
      },
      y: {
        grid: { color: 'rgba(255,255,255,0.04)', drawTicks: false },
        ticks: {
          color: '#52525B',
          font: { size: 10, family: "'JetBrains Mono', monospace" },
          padding: 10,
          callback: (v) => v,
        },
        border: { display: false },
      },
    },
  }

  if (loading) return <div className="empty">Computing forecast…</div>

  if (!data.length) return <div className="empty">No forecast available yet.</div>

  return (
    <>
      <div className="chart-meta">
        <span className="chart-key"><span className="swatch" />LSTM 72→48h</span>
        <span className="chart-key"><span className="swatch dashed" />Prophet baseline</span>
        <span style={{ marginLeft: 'auto' }}>µg/m³ PM 2.5</span>
      </div>
      <div className="chart-frame">
        <Line data={chartData} options={chartOptions} />
      </div>
    </>
  )
}
