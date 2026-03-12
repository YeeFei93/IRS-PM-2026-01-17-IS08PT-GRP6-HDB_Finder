import { REGIONS, AMENITIES } from './constants';

// ── EHG Table A: First-Timer Couples & Families ──
function ehgFamilyBands(income) {
  const bands = [
    [1500, 120000], [2000, 110000], [2500, 105000], [3000, 95000], [3500, 90000],
    [4000, 80000], [4500, 70000], [5000, 65000], [5500, 55000], [6000, 50000],
    [6500, 40000], [7000, 30000], [7500, 25000], [8000, 20000], [8500, 10000], [9000, 5000],
  ];
  for (const [ceil, amt] of bands) if (income <= ceil) return amt;
  return 0;
}

// ── EHG Table B: Singles / Mixed Couples ──
function ehgSinglesBands(income) {
  const half = income / 2;
  if (half > 4500) return 0;
  const bands = [
    [750, 60000], [1000, 55000], [1250, 52500], [1500, 47500], [1750, 45000],
    [2000, 40000], [2250, 35000], [2500, 32500], [2750, 27500], [3000, 25000],
    [3250, 20000], [3500, 15000], [3750, 12500], [4000, 10000], [4250, 5000], [4500, 2500],
  ];
  for (const [halfCeil, amt] of bands) if (half <= halfCeil) return amt;
  return 0;
}

export function calcGrants(cit, income, ftype, ftimer, prox) {
  const isFirst = ftimer === 'first';
  const isSingle = cit === 'SC_single';
  const isPR = cit === 'PR_PR';
  const isMixed = cit === 'mixed';

  let ehg = 0;
  if (isFirst && !isPR) {
    if (isSingle || isMixed) {
      ehg = ehgSinglesBands(income);
    } else {
      if (income <= 9000) ehg = ehgFamilyBands(income);
    }
  }

  let cpfG = 0;
  if (isFirst && !isPR) {
    const ceil2 = isSingle ? 7000 : 14000;
    if (income <= ceil2) {
      const large = ['5 ROOM', 'EXECUTIVE'].includes(ftype);
      const base = large ? 40000 : 50000;
      if (cit === 'SC_SC') cpfG = base;
      else if (cit === 'SC_PR') cpfG = Math.floor(base / 2);
      else if (cit === 'SC_single') cpfG = Math.floor(base / 2);
    }
  }

  let phg = 0;
  if (!isPR) {
    if (prox === 'same') phg = 30000;
    else if (prox === 'near') phg = 20000;
  }

  return { ehg, cpfG, phg, total: ehg + cpfG + phg };
}

export function loanCapacity(monthly, rateAnnual = 0.026, years = 25) {
  const r = rateAnnual / 12;
  const n = years * 12;
  const factor = ((1 + r) ** n - 1) / (r * (1 + r) ** n);
  return Math.round(monthly * factor);
}

export function checkEligibility(cit, income, age) {
  let eligible = true, warns = [], notes = [];

  if (cit === 'PR_PR') { notes.push('PRs: resale flats only.'); }
  if (cit === 'SC_single' && age < 35) { eligible = false; warns.push('Singles must be ≥35 for BTO.'); }
  if (income > 16000) { eligible = false; warns.push('Income >$16k: HDB ineligible.'); }
  else if (income > 14000) { warns.push('Income $14k–$16k: resale only.'); }
  else if (income > 9000) { notes.push('Income >$9k: EHG not applicable. CPF Housing Grant may still apply (≤$14k).'); }

  return { eligible, warns, notes };
}

// ── Price Analysis ──
function pct(sorted, p) {
  const i = Math.max(0, Math.min(sorted.length - 1, Math.ceil(p / 100 * sorted.length) - 1));
  return sorted[i];
}

export function analyseRecords(records, town, ftype) {
  const rel = records.filter(r =>
    r.town === town && (ftype === 'any' || r.flat_type === ftype)
  );
  if (!rel.length) return null;

  const prices = rel.map(r => +r.resale_price).sort((a, b) => a - b);
  const areas = rel.map(r => +r.floor_area_sqm);

  const median = pct(prices, 50);
  const p25 = pct(prices, 25);
  const p75 = pct(prices, 75);
  const avgArea = areas.reduce((a, b) => a + b, 0) / areas.length;
  const psm = avgArea > 0 ? median / avgArea : 0;

  const byMonth = {};
  rel.forEach(r => {
    if (!byMonth[r.month]) byMonth[r.month] = [];
    byMonth[r.month].push(+r.resale_price);
  });
  const months = Object.keys(byMonth).sort();
  const vals = months.map(m => pct([...byMonth[m]].sort((a, b) => a - b), 50));

  const trend12 = vals.length >= 2
    ? ((vals[vals.length - 1] - vals[0]) / vals[0] * 100).toFixed(1)
    : 0;
  const mom = vals.length >= 2
    ? ((vals[vals.length - 1] - vals[vals.length - 2]) / vals[vals.length - 2] * 100).toFixed(1)
    : 0;

  const conf = rel.length >= 20 ? 'high' : rel.length >= 5 ? 'medium' : 'low';
  const latest = months[months.length - 1] || null;

  return {
    median, p25, p75, avgArea: +avgArea.toFixed(1), psm: Math.round(psm),
    trend12: +trend12, mom: +mom, conf, n: rel.length, latest, months, vals,
  };
}

// ── Scoring ──
function scoreBudget(median, budget) {
  const r = median / budget;
  if (r <= 0.75) return 20;
  if (r <= 0.85) return 18;
  if (r <= 0.95) return 15;
  if (r <= 1.00) return 12;
  if (r <= 1.05) return 8;
  if (r <= 1.15) return 4;
  return 1;
}

function scoreTransport(mins) {
  if (mins <= 5) return 20;
  if (mins <= 8) return 17;
  if (mins <= 12) return 13;
  if (mins <= 15) return 9;
  if (mins <= 20) return 5;
  return 2;
}

function scoreAmenities(town, mustArr, maxMrt) {
  const a = AMENITIES[town] || {};
  let s = 0;
  const detail = {};

  const mrtOk = a.mrtMin && a.mrtMin <= maxMrt;
  detail.mrt = { pts: mrtOk ? 10 : (mustArr.includes('mrt') ? -5 : 0), max: 10, ok: !!mrtOk, mins: a.mrtMin || null, name: a.mrt || null };
  s += detail.mrt.pts;

  const hawkerOk = !!a.hawker;
  detail.hawker = { pts: hawkerOk ? 7 : (mustArr.includes('hawker') ? -5 : 0), max: 7, ok: hawkerOk, name: a.hawker || null };
  s += detail.hawker.pts;

  const parkOk = !!a.park;
  detail.park = { pts: parkOk ? 5 : (mustArr.includes('park') ? -5 : 0), max: 5, ok: parkOk, name: a.park || null };
  s += detail.park.pts;

  detail.school = { pts: 4, max: 4, ok: true };
  s += 4;

  const mallOk = !['SEMBAWANG', 'BUANGKOK', 'PASIR RIS'].includes(town);
  detail.mall = { pts: mallOk ? 2 : (mustArr.includes('mall') ? -5 : 0), max: 2, ok: mallOk };
  s += detail.mall.pts;

  detail.clinic = { pts: 2, max: 2, ok: true };
  s += 2;

  const total = Math.max(0, Math.min(30, s));
  return { total, detail };
}

function scoreRegion(town, selRegions) {
  if (!selRegions.length) return 10;
  for (const [reg, towns] of Object.entries(REGIONS)) {
    if (towns.includes(town)) {
      return selRegions.includes(reg) ? 15 : 2;
    }
  }
  return 5;
}

export function computeScore(town, pd, effective, mustArr, maxMrt, selRegions) {
  const a = AMENITIES[town] || {};
  const mrt = a.mrtMin || 15;

  const sb = scoreBudget(pd.median, effective);
  const ratio = pd.median / effective;
  const budgetDetail = {
    pts: sb, max: 20,
    desc: ratio <= 1.0
      ? `Median $${pd.median.toLocaleString()} is within your effective budget of $${effective.toLocaleString()} (${(ratio * 100).toFixed(0)}% utilised)`
      : `Median price is ${((ratio - 1) * 100).toFixed(0)}% above effective budget — grants and negotiation may close the gap`,
  };

  const amenResult = scoreAmenities(town, mustArr, maxMrt);
  const sa = amenResult.total;

  const st = scoreTransport(mrt);
  const transportDetail = {
    pts: st, max: 20,
    desc: mrt <= 5
      ? `Excellent — ${a.mrt || 'MRT'} is ${mrt} min walk, within Singapore's 5-min walk-to-MRT benchmark`
      : mrt <= 10
        ? `Good — ${a.mrt || 'MRT'} is ${mrt} min walk. Comfortable for daily commuting`
        : mrt <= 15
          ? `Moderate — ${a.mrt || 'MRT'} is ${mrt} min walk. Cycling or feeder bus may help`
          : `${a.mrt || 'MRT'} is ${mrt} min walk. Bus feeder services recommended`,
  };

  const sr = scoreRegion(town, selRegions);
  let townRegionName = '—';
  for (const [reg, towns] of Object.entries(REGIONS)) {
    if (towns.includes(town)) {
      townRegionName = reg === 'northeast' ? 'North-East' : reg.charAt(0).toUpperCase() + reg.slice(1);
      break;
    }
  }
  const regionDetail = {
    pts: sr, max: 15,
    desc: selRegions.length === 0
      ? 'No region preference set — neutral score applied across all regions'
      : sr === 15
        ? `${town} is in the ${townRegionName} region, directly matching your preference`
        : sr >= 8
          ? `${town} is in the ${townRegionName} region, adjacent to your preferred region`
          : `${town} (${townRegionName}) does not match your preferred regions`,
  };

  const sf = 10;
  const flatDetail = {
    pts: sf, max: 15,
    desc: `Avg floor area ${pd.avgArea} sqm across ${pd.n} transactions (${pd.conf} confidence). Lease and floor-level data are town-level estimates`,
  };

  const total = Math.min(100, sb + sa + st + sr + sf);
  return {
    budget: budgetDetail,
    amenity: { pts: sa, max: 30, detail: amenResult.detail },
    transport: transportDetail,
    region: regionDetail,
    flat: flatDetail,
    total,
  };
}

export function whyText(town, ftype, score, pd, budget) {
  const savings = budget - pd.median;
  const under = savings > 0;
  const tr = pd.trend12;
  return `${town} offers ${ftype} flats ${under
    ? `within budget with ~$${Math.abs(savings).toLocaleString()} headroom`
    : 'slightly above base budget — grants and negotiation may close the gap'
    }. ${tr < 0
      ? 'Prices have softened over 12 months, presenting a potential buying window.'
      : tr > 3
        ? 'Prices are rising; acting sooner may be advantageous.'
        : 'Prices are stable, giving you time to compare options carefully.'
    }`;
}

export function scoreToColor(score) {
  const r = score / 100;
  if (r <= 0.5) {
    const t = r * 2;
    const green = Math.round(57 + t * (174 - 57));
    return `rgb(192,${green},43)`;
  } else {
    const t = (r - 0.5) * 2;
    const red = Math.round(192 - t * (192 - 39));
    return `rgb(${red},174,67)`;
  }
}
