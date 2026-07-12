import axios from 'axios'

// Empty base in dev: Vite proxies /api to the local FastAPI server.
// In production, set VITE_API_URL to the Render backend origin.
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
