import { useEffect, useState } from 'react'
import { fetchHistorical } from '../api/client.js'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Tooltip,
} from 'chart.js'
import { Line } from 'react-chartjs-2'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip)

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export default function HistoricalTrends({ city }) {
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchHistorical(city, now.getFullYear(), month)
      .then(d => alive && setData(d))
      .catch(() => alive && setData(null))
      .finally(() => alive && setLoading(false))
  }, [city, month])

  const dailyAvg = (rows) => {
    const buckets = {}
    rows?.forEach(r => {
      if (r.aqi == null) return
      const day = new Date(r.timestamp).getUTCDate()
      ;(buckets[day] ||= []).push(r.aqi)
    })
    return Object.fromEntries(
      Object.entries(buckets).map(([d, arr]) => [d, arr.reduce((s, x) => s + x, 0) / arr.length])
    )
  }

  const curr = dailyAvg(data?.current_month?.data)
  const prev = dailyAvg(data?.previous_year?.data)
  const days = Array.from({ length: 31 }, (_, i) => i + 1)

  const chartData = {
    labels: days.map(String),
    datasets: [
      {
        label: `${data?.current_month?.year || 'This Year'}`,
        data: days.map(d => curr[d] ?? null),
        borderColor: '#FF8A3D',
        backgroundColor: '#FF8A3D',
        borderWidth: 1.75,
        tension: 0.4,
        spanGaps: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#FF8A3D',
        pointHoverBorderColor: '#0A0A0B',
        pointHoverBorderWidth: 2,
      },
      {
        label: `${data?.previous_year?.year || 'Last Year'}`,
        data: days.map(d => prev[d] ?? null),
        borderColor: 'rgba(229, 229, 228, 0.5)',
        backgroundColor: '#E5E5E4',
        borderWidth: 1,
        borderDash: [3, 4],
        tension: 0.4,
        spanGaps: true,
        pointRadius: 0,
        pointHoverRadius: 4,
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
        borderColor: 'rgba(255,255,255,0.10)', borderWidth: 1,
        titleFont: { size: 11, weight: 500, family: "'JetBrains Mono', monospace" },
        bodyFont: { size: 12 }, padding: 12, cornerRadius: 6,
        titleColor: '#A1A1AA', bodyColor: '#FAFAF9',
        callbacks: {
          title: (ctx) => `Day ${ctx[0].label}`,
          label: (ctx) => `  ${ctx.dataset.label}   AQI ${ctx.parsed.y?.toFixed(0)}`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#52525B', font: { size: 10, family: "'JetBrains Mono', monospace" }, maxTicksLimit: 16 },
        border: { color: 'rgba(255,255,255,0.10)' },
      },
      y: {
        grid: { color: 'rgba(255,255,255,0.04)', drawTicks: false },
        ticks: { color: '#52525B', font: { size: 10, family: "'JetBrains Mono', monospace" }, padding: 10 },
        border: { display: false },
      },
    },
  }

  const noData = !Object.keys(curr).length && !Object.keys(prev).length

  return (
    <>
      <div className="chart-meta">
        <span className="chart-key"><span className="swatch" />{data?.current_month?.year || ''}</span>
        <span className="chart-key"><span className="swatch dashed" />{data?.previous_year?.year || ''}</span>
        <span style={{ marginLeft: 'auto' }}>Daily mean AQI</span>
      </div>

      <div className="month-select">
        {MONTHS.map((m, i) => (
          <button
            key={m}
            className={`month ${month === i + 1 ? 'active' : ''}`}
            onClick={() => setMonth(i + 1)}
          >
            {m}
          </button>
        ))}
      </div>

      <div className="chart-frame" style={{ height: 280 }}>
        {loading ? (
          <div className="empty">Loading archive…</div>
        ) : noData ? (
          <div className="empty">No archive yet — keep the scheduler running for a month and it will populate here.</div>
        ) : (
          <Line data={chartData} options={chartOptions} />
        )}
      </div>
    </>
  )
}
