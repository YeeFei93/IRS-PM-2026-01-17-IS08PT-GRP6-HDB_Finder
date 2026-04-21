import { DATASET, API_BASE, AMENITY_THRESHOLDS } from './constants';
import { AMENITIES } from './constants';

// ── Backend API support ──

export async function checkBackendHealth() {
  // No health endpoint on the Express server — return true if API_BASE is configured.
  // runSearchBackend handles connection errors gracefully.
  return !!API_BASE;
}

export async function runSearchBackend(payload) {
  // Map frontend formState keys → backend BuyerProfile keys before sending.
  const mapped = {
    ...payload,
    regions:      payload.selRegions   ?? payload.regions      ?? [],
    income:       payload.inc          ?? payload.income        ?? 0,
    must_have:    payload.mustAmenities ?? payload.must_have    ?? [],
    min_lease:    payload.lease        ?? payload.min_lease      ?? 60,
  };
  const r = await fetch(`${API_BASE}/api/top-recommendations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(mapped),
  });
  if (!r.ok) throw new Error(`Backend ${r.status}`);
  return r.json();
}

export function normaliseBackendRec(r, selectedModel = null) {
  const resolvedModel = r.selected_model || selectedModel || null;
  const recommendationModel = r.recommendation_model || resolvedModel?.key || null;
  const recommendationModelLabel = r.recommendation_model_label || resolvedModel?.label || recommendationModel;
  // ── price data (price_data dict from backend) ──────────────────────────────
  const priceData = r.price_data || {};
  const pd = {
    median:  priceData.median    ?? 0,
    p25:     priceData.p25       ?? 0,
    p75:     priceData.p75       ?? 0,
    avgArea: priceData.avg_area  ?? 0,
    avgLease: priceData.avg_lease_years ?? null,
    psm:     priceData.psm       ?? 0,
    trend12: priceData.trend_pct ?? 0,
    mom:     0,
    conf:    priceData.low_confidence ? 'low' : (priceData.n ?? 0) >= 20 ? 'high' : 'medium',
    n:       priceData.n         ?? 0,
  };

  // ── amenity detail (amenities dict from backend) ───────────────────────────
  const amenities = r.amenities || {};
  const amenDetail = {};
  for (const k of ['mrt', 'hawker', 'park', 'school', 'mall', 'hospital']) {
    const a = amenities[k];
    if (a) {
      const thresh = AMENITY_THRESHOLDS[k];
      const ok = a.within_threshold ?? false;
      const mins = a.walk_mins ?? null;
      const count = a.count_within ?? (ok ? 1 : 0);
      // pts: 6 if within threshold, 3 if within 2× threshold, else 0
      const pts = ok ? 6 : (thresh && mins !== null && mins <= thresh.maxMins * 2) ? 3 : 0;
      amenDetail[k] = { pts, max: 6, ok, mins, count, name: null };
    } else {
      amenDetail[k] = { pts: 0, max: 6, ok: false, mins: null, count: 0, name: null };
    }
  }

  // ── cosine score → 0-100 for ResultCard colour thresholds ─────────────────
  const cosine = r.score ?? 0;
  const total  = Math.round(cosine * 100);
  const label  = total >= 75 ? 'Strong Match' : total >= 55 ? 'Good Match' : 'Exploratory';

  return {
    town:      r.town,
    ftype:     r.ftype || '4 ROOM',
    selected_model: resolvedModel,
    recommendation_model: recommendationModel,
    recommendation_model_label: recommendationModelLabel,
    pd,
    sc: {
      total,
      label,
      active:    r.active_criteria || [],
      amenity:   {
        pts:    Object.values(amenDetail).reduce((s, d) => s + d.pts, 0),
        max:    36,
        detail: amenDetail,
      },
      // Cosine scorer returns a single score — no per-criterion breakdown.
      // UI rows that reference these will show 0/0 and be filtered out.
      budget:    { pts: 0, max: 0, desc: '' },
      flat:      { pts: 0, max: 0, desc: '' },
      region:    { pts: 0, max: 0, desc: '' },
      lease:     { pts: 0, max: 0, desc: '' },
      transport: { pts: 0, max: 0, desc: '' },
    },
    grants:    r.grants           || { ehg: 0, cpfG: 0, phg: 0, total: 0, notes: [] },
    effective: r.effective_budget ?? 0,
    qualifying_flats: r.qualifying_flats || 0,
    avg_score:      r.avg_score      ?? 0,
    strong_matches: r.strong_matches ?? 0,
    baseline_price_rank: r.baseline_price_rank ?? null,
    baseline_pop_rank:   r.baseline_pop_rank   ?? null,
    top_flats: (r.top_flats || []).map((f, i) => ({
      ...f,
      _idx: i,
      resale_flat_id: f.resale_flat_id ?? null,
      latitude: f.latitude != null ? Number(f.latitude) : null,
      longitude: f.longitude != null ? Number(f.longitude) : null,
      recommendation_model: f.recommendation_model || recommendationModel,
      recommendation_model_label: f.recommendation_model_label || recommendationModelLabel,
    })),
  };
}

export async function runFlatLookup(payload) {
  const r = await fetch(`${API_BASE}/api/flats`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`Flat lookup ${r.status}`);
  return r.json();
}

export async function runFlatAmenities(block, streetName) {
  const r = await fetch(`${API_BASE}/api/flat-amenities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ block, street_name: streetName }),
  });
  if (!r.ok) throw new Error(`Flat parks ${r.status}`);
  return r.json();
}

export async function recordRecommendationFeedback({
  resaleFlatId,
  recommendation,
  event,
  viewed,
  favourite,
  sessionId,
  topKSnapshot,
}) {
  const body = {
    resale_flat_id: resaleFlatId,
  };
  if (recommendation) body.recommendation = recommendation;
  if (event !== undefined) body.event = event;
  if (viewed !== undefined) body.viewed = viewed;
  if (favourite !== undefined) body.favourite = favourite;
  if (sessionId) body.session_id = sessionId;
  if (topKSnapshot !== undefined) body.top_k_snapshot = topKSnapshot;

  const r = await fetch(`${API_BASE}/api/recommendation-feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    keepalive: true,
  });
  if (!r.ok) throw new Error(`Recommendation feedback ${r.status}`);
  return r.json();
}

export async function fetchFavourites() {
  if (!API_BASE) return { favourites: [] };
  const r = await fetch(`${API_BASE}/api/favourites`);
  if (!r.ok) throw new Error(`Favourites ${r.status}`);
  return r.json();
}

export async function toggleFavourite(resaleFlatId, recommendationModel = null) {
  const r = await fetch(`${API_BASE}/api/favourites/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      resale_flat_id: resaleFlatId,
      recommendation_model: recommendationModel,
    }),
  });
  if (!r.ok) throw new Error(`Toggle favourite ${r.status}`);
  return r.json();
}

export async function removeFavourite(resaleFlatId) {
  const r = await fetch(`${API_BASE}/api/favourites/${encodeURIComponent(resaleFlatId)}`, {
    method: 'DELETE',
  });
  if (!r.ok) throw new Error(`Remove favourite ${r.status}`);
  return r.json();
}

// ── data.gov.sg fallback API ──

async function apiCall(town, ftype, limit = 500, offset = 0) {
  const filters = { town };
  if (ftype && ftype !== 'any') filters.flat_type = ftype;

  const qs = new URLSearchParams({
    resource_id: DATASET,
    limit,
    offset,
    filters: JSON.stringify(filters),
    town: town,
    sort: 'month desc',
  }).toString();

  // const directUrl = `https://data.gov.sg/api/action/datastore_search?${qs}`;
  const directUrl = `http://localhost:3000/api/recommendations?${qs}`
  // const proxyUrl = `https://corsproxy.io/?url=${encodeURIComponent(directUrl)}`;
  const proxyUrl = `http://localhost:3000/api/recommendations?${qs}`

  const tryFetch = async (url) => {
    const r = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    if (j && j.success !== undefined) return j;
    if (j && j.result) return j;
    throw new Error('Unexpected response');
  };

  try { return await tryFetch(directUrl); } catch (_) { /* fallback */ }
  try { return await tryFetch(proxyUrl); } catch (_) { /* fallback */ }

  // const aoUrl = `https://api.allorigins.win/get?url=${encodeURIComponent(directUrl)}`;
  const aoUrl = `http://localhost:3000/api/recommendations?${qs}`
  const ao = await fetch(aoUrl);
  const aoJ = await ao.json();
  return JSON.parse(aoJ.contents);
}

export async function fetchTown(town, ftype, cutoff) {
  const all = [];
  let offset = 0;
  
    let data;
    try { data = await apiCall(town, ftype, 500, offset); }
    catch (e) { console.warn('Fetch fail', town, e); }

    const recs = data?.result?.records || [];
  
    const filtered = recs.filter(r => r.month >= cutoff);
    all.push(...filtered);  
  
  return all;
}
