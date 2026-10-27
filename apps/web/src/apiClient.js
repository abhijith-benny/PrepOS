import { supabase } from './supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function currentAccessToken(fallbackToken) {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token || fallbackToken
}

async function request(path, options, fallbackToken, hasRetried) {
  const token = await currentAccessToken(fallbackToken)
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (response.status === 401 && !hasRetried) {
    const { data } = await supabase.auth.refreshSession()
    if (data.session?.access_token) {
      return request(path, options, data.session.access_token, true)
    }
    await supabase.auth.signOut()
    window.location.assign('/')
  }

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || 'Request failed')
  }

  return response.status === 204 ? null : response.json()
}

export function apiRequest(path, options = {}, token) {
  return request(path, options, token, false)
}
