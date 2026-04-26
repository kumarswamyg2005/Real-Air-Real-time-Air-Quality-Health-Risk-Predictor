import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

export const fetchCities = () => api.get('/cities').then(r => r.data)
export const fetchCurrent = (city) => api.get(`/cities/${city}/current`).then(r => r.data)
export const fetchHourly = (city, hours = 72) =>
  api.get(`/cities/${city}/hourly`, { params: { hours } }).then(r => r.data)
export const fetchForecast = (city) => api.get(`/cities/${city}/forecast`).then(r => r.data)
export const fetchHistorical = (city, year, month) =>
  api.get(`/cities/${city}/historical`, { params: { year, month } }).then(r => r.data)
export const postHealthRisk = (payload) => api.post('/health/risk', payload).then(r => r.data)
export const triggerRefresh = (city) => api.post('/refresh', { city }).then(r => r.data)
export const fetchStats = () => api.get('/stats').then(r => r.data)

export default api
