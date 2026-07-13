import axios from 'axios'

// The frontend always calls the backend cross-origin, in dev and in prod alike
// (VITE_API_URL — see .env.development and vite.config.js). There is no dev proxy.
const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
  timeout: 120000, // a cold DESeq2 run takes ~15s, and Render free-tier dynos sleep
})

export async function getStudies() {
  const { data } = await client.get('/api/studies')
  return data.studies
}

export async function getAbtest(accession) {
  const { data } = await client.get(`/api/abtest/${accession}`)
  return data
}

/** The analyte / crew allowlist the forecast endpoint will accept. */
export async function getForecastOptions() {
  const { data } = await client.get('/api/forecast')
  return data
}

export async function getForecast(analyte, crew, extraDays) {
  const { data } = await client.get(`/api/forecast/${analyte}`, {
    params: { crew, extra_days: extraDays },
  })
  return data
}

export async function getIntegrate(accession, limit = 500) {
  const { data } = await client.get(`/api/integrate/${accession}`, {
    params: { limit },
  })
  return data
}
