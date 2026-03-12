import { DATASET } from './constants';

async function apiCall(town, ftype, limit = 500, offset = 0) {
  const filters = { town };
  if (ftype && ftype !== 'any') filters.flat_type = ftype;

  const qs = new URLSearchParams({
    resource_id: DATASET,
    limit,
    offset,
    filters: JSON.stringify(filters),
    sort: 'month desc',
  }).toString();

  const directUrl = `https://data.gov.sg/api/action/datastore_search?${qs}`;
  const proxyUrl = `https://corsproxy.io/?url=${encodeURIComponent(directUrl)}`;

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

  const aoUrl = `https://api.allorigins.win/get?url=${encodeURIComponent(directUrl)}`;
  const ao = await fetch(aoUrl);
  const aoJ = await ao.json();
  return JSON.parse(aoJ.contents);
}

export async function fetchTown(town, ftype, cutoff) {
  const all = [];
  let offset = 0;
  while (true) {
    let data;
    try { data = await apiCall(town, ftype, 500, offset); }
    catch (e) { console.warn('Fetch fail', town, e); break; }

    const recs = data?.result?.records || [];
    if (!recs.length) break;

    const filtered = recs.filter(r => r.month >= cutoff);
    all.push(...filtered);

    const oldest = recs.reduce((mn, r) => r.month < mn ? r.month : mn, recs[0].month);
    if (oldest < cutoff || recs.length < 500) break;
    offset += 500;
  }
  return all;
}
