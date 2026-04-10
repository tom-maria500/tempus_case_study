// If VITE_API_URL is set, always use it.
// Otherwise:
// - in dev, default to local backend
// - in production (single-service deploy), default to same-origin
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV ? 'http://localhost:8000' : '');

export async function getProviders(city = null, limit = 15) {
  const params = new URLSearchParams();
  if (city) params.append('city', city);
  params.append('limit', String(limit));
  const res = await fetch(`${BASE_URL}/providers?${params.toString()}`);
  if (!res.ok) {
    throw new Error('Failed to fetch providers');
  }
  return res.json();
}

export async function generateBrief(physician) {
  const body =
    physician && typeof physician === 'object'
      ? {
          physician_name: physician.name,
          physician_id: physician.physician_id,
        }
      : {
          physician_name: String(physician),
        };

  const res = await fetch(`${BASE_URL}/brief`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    if (res.status === 404) {
      throw new Error('Physician not found');
    }
    if (res.status === 503) {
      throw new Error('Service unavailable');
    }
    throw new Error('Failed to generate brief');
  }

  return res.json();
}

export async function getIntel(physicianId, options = 90) {
  const payload = { physician_id: physicianId };
  if (typeof options === 'number') {
    payload.days_lookback = options;
  } else if (options && typeof options === 'object') {
    if (typeof options.daysLookback === 'number') {
      payload.days_lookback = options.daysLookback;
    }
    if (options.startDate) {
      payload.start_date = options.startDate;
    }
    if (options.endDate) {
      payload.end_date = options.endDate;
    }
  } else {
    payload.days_lookback = 90;
  }
  const res = await fetch(`${BASE_URL}/intel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    if (res.status === 404) throw new Error('Physician not found');
    if (res.status === 503) throw new Error('Service unavailable');
    throw new Error('Failed to fetch intel');
  }
  return res.json();
}

export async function logOutcome(payload) {
  const res = await fetch(`${BASE_URL}/outcomes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    if (res.status === 404) throw new Error('Physician not found');
    if (res.status === 503) throw new Error('Failed to log outcome');
    throw new Error('Failed to log outcome');
  }
  return res.json();
}

export async function getOutcomeHistory(physicianId) {
  const res = await fetch(`${BASE_URL}/outcomes/${physicianId}`);
  if (!res.ok) throw new Error('Failed to fetch outcome history');
  return res.json();
}

export async function sendChat(payload) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    if (res.status === 404) throw new Error('Physician not found');
    if (res.status === 503) throw new Error('Service unavailable');
    throw new Error('Chat failed');
  }

  return res.json();
}


