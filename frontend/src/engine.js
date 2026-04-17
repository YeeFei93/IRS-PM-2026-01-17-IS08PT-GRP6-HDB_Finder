import { REGIONS, AMENITIES } from './constants';

// ════════════════════════════════════════════════════════════
//  EHG TABLES (mirrors HTML reference)
// ════════════════════════════════════════════════════════════

// TABLE A — SC/SC or SC/PR, BOTH first-timers (Families / Couples)
// Full household income; ceiling $9,000
function ehgFamilyBands(income) {
  const bands = [
    [1500, 120000], [2000, 110000], [2500, 105000], [3000, 95000], [3500, 90000],
    [4000, 80000], [4500, 70000], [5000, 65000], [5500, 55000], [6000, 50000],
    [6500, 40000], [7000, 30000], [7500, 25000], [8000, 20000], [8500, 10000], [9000, 5000],
  ];
  for (const [ceil, amt] of bands) if (income <= ceil) return amt;
  return 0;
}

// TABLE B — SC Single (solo or buying with parents)
// Individual's average monthly income; ceiling $4,500
function ehgSoloBands(income) {
  if (income > 4500) return 0;
  const bands = [
    [750, 60000], [1000, 55000], [1250, 52500], [1500, 47500], [1750, 45000],
    [2000, 40000], [2250, 35000], [2500, 32500], [2750, 27500], [3000, 25000],
    [3250, 20000], [3500, 15000], [3750, 12500], [4000, 10000], [4250, 5000], [4500, 2500],
  ];
  for (const [ceil, amt] of bands) if (income <= ceil) return amt;
  return 0;
}

// TABLE C — SC + Non-Resident Spouse (EHG Singles scheme)
// Indexed by HALF of the combined household income; ceiling half-income $4,500
function ehgNonResidentSpouseBands(income) {
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

// TABLE D — Joint Singles Scheme: Two or more first-timer SC singles
// Full household income (combined); ceiling $9,000
function ehgJointSinglesBands(income) {
  if (income > 9000) return 0;
  const bands = [
    [1500, 120000], [2000, 110000], [2500, 105000], [3000, 95000], [3500, 90000],
    [4000, 80000], [4500, 70000], [5000, 65000], [5500, 55000], [6000, 50000],
    [6500, 40000], [7000, 30000], [7500, 25000], [8000, 20000], [8500, 10000], [9000, 5000],
  ];
  for (const [ceil, amt] of bands) if (income <= ceil) return amt;
  return 0;
}

// ════════════════════════════════════════════════════════════
//  GRANT / ELIGIBILITY ENGINE
// ════════════════════════════════════════════════════════════

export function calcGrants(cit, income, ftype, ftimer, prox, marital) {
  const isFirst = ftimer === 'first';
  const isPR = cit === 'PR_PR';

  const isSingleScheme = (cit === 'SC_single' && marital === 'single');
  const isJointSingle = (cit === 'SC_single' && marital === 'joint');
  const isWithSCParents = (cit === 'SC_single' && marital === 'with_SC_parents');
  const isPRWithSCParents = (cit === 'PR_PR' && marital === 'with_SC_parents');

  // ── EHG ──
  let ehg = 0;
  if (isFirst && (!isPR || isPRWithSCParents)) {
    if (cit === 'SC_NR') {
      ehg = ehgNonResidentSpouseBands(income);
    } else if (isJointSingle) {
      ehg = ehgJointSinglesBands(income);
    } else if (isSingleScheme || isWithSCParents) {
      ehg = ehgSoloBands(income);
    } else if (cit !== 'SC_single') {
      if (income <= 9000) ehg = ehgFamilyBands(income);
    }
  }

  // ── CPF Housing Grant (Resale only) ──
  let cpfG = 0;
  if (isFirst && (!isPR || isPRWithSCParents)) {
    const large = ['5 ROOM', 'EXECUTIVE'].includes(ftype);
    if (cit === 'SC_SC') {
      if (income <= 14000) cpfG = large ? 50000 : 80000;
    } else if (cit === 'SC_PR') {
      if (income <= 14000) cpfG = large ? 40000 : 70000;
    } else if (cit === 'SC_NR') {
      if (income <= 7000) cpfG = large ? 25000 : 40000;
    } else if (isJointSingle) {
      if (income <= 14000) cpfG = large ? 50000 : 80000;
    } else if (isSingleScheme) {
      if (income <= 7000) cpfG = large ? 25000 : 40000;
    } else if (isWithSCParents) {
      if (income <= 7000) cpfG = large ? 25000 : 40000;
    } else if (isPRWithSCParents) {
      if (income <= 14000) cpfG = large ? 40000 : 70000;
    }
  }

  // ── PHG (Proximity Housing Grant) ──
  let phg = 0;
  if ((!isPR || isPRWithSCParents) && cit !== 'SC_NR') {
    const isSinglesPhg = isSingleScheme || isWithSCParents || isPRWithSCParents;
    if (prox === 'same') phg = isSinglesPhg ? 15000 : 30000;
    else if (prox === 'near') phg = isSinglesPhg ? 10000 : 20000;
  }

  return { ehg, cpfG, phg, total: ehg + cpfG + phg };
}

// ════════════════════════════════════════════════════════════
//  LOAN ENGINE
// ════════════════════════════════════════════════════════════

export function loanCapacity(monthly, rateAnnual = 0.026, years = 25) {
  const r = rateAnnual / 12;
  const n = years * 12;
  const factor = ((1 + r) ** n - 1) / (r * (1 + r) ** n);
  return Math.round(monthly * factor);
}

export function checkLoanLimit(monthlyIncome, monthlyRepayment, effectiveBudget, rateAnnual = 0.026, years = 25) {
  // effectiveBudget should include cash + CPF + grants + loan capacity
  // Cap the maximum monthly repayment at 30% of income
  const maxMonthly = monthlyIncome * 0.30;
  
  // Re-use your existing loan capacity math
  const r = rateAnnual / 12;
  const n = years * 12;
  const factor = ((1 + r) ** n - 1) / (r * (1 + r) ** n);
  
  // Calculate the maximum loan value based on the capped monthly payment
  const maxLoanFromIncome = Math.round(maxMonthly * factor);
  
  // Cap the maximum loan at 75% of the effective budget
  const maxLoanFromBudget = Math.round(effectiveBudget * 0.75);
  
  // The overall maximum loan is the minimum of the two caps
  const maxLoan = Math.min(maxLoanFromIncome, maxLoanFromBudget);
  
  // Calculate the proposed loan amount from the monthly repayment
  const proposedLoan = Math.round(monthlyRepayment * factor);
  
  // Determine the limiting factor
  let limitReason = '';
  if (maxLoanFromIncome < maxLoanFromBudget) {
    limitReason = 'Monthly repayment exceeds 30% of your monthly income';
  } else if (maxLoanFromBudget < maxLoanFromIncome) {
    limitReason = 'Max loan principal exceeds 75% of your effective budget';
  } else {
    limitReason = 'Both your monthly repayment exceeds 30% of your monthly income and max loan principal exceeds 75% of your effective budget';
  }
  
  // Format numbers with commas for a clean output string
  const formattedLoan = maxLoan.toLocaleString('en-US');
  const formattedPayment = Math.round(maxMonthly).toLocaleString('en-US');
  const formattedProposedLoan = proposedLoan.toLocaleString('en-US');

  if (proposedLoan <= maxLoan) {
    return null; // No warning needed, loan is within limits
  } else {
    return `${limitReason}. Adjust your monthly repayment to be no more than $${formattedPayment} or ensure that your max loan principal does not exceed $${formattedLoan}. `;
  }
}

export function checkLeaseAgeCriteria(age, lease) {
  const combined = age + lease;
  if (combined < 95) {
    return `Age + Lease must be at least 95 years (currently ${combined} yrs). If below 95, CPF withdrawal will be pro-rated.`;
  }
  return null;
}

export function checkEligibility(cit, income, age, marital, ftimer) {
  let eligible = true, warns = [], notes = [];

  const isJointSingle = (cit === 'SC_single' && marital === 'joint');
  const isWithSCParents = (cit === 'SC_single' && marital === 'with_SC_parents');
  const isSingleScheme = (cit === 'SC_single' && marital === 'single');
  const isPRWithPRParents = (cit === 'PR_PR' && marital === 'with_PR_parents');
  const isPRWithSCParents = (cit === 'PR_PR' && marital === 'with_SC_parents');

  if (cit === 'PR_PR' && (marital === 'married' || marital === 'fiancee')) {
    notes.push('PRs: resale flats only. Both must be PRs for at least 3 years.');
  }
  if (cit === 'PR_PR' && (marital === 'single')) {
    eligible = false;
    warns.push('PR Singles must form a family nucleus to buy flats.');
  }
  if (cit === 'SC_NR') {
    notes.push('SC + Non-Resident Spouse: resale flats only. BTO requires both applicants to be SC/PR.');
  }
  if (cit === 'SC_single' && age < 35) {
    eligible = false;
    warns.push('Singles must be ≥35 years old to buy under the Singles / JSS / Single with Parents scheme.');
  }
  if (isJointSingle) {
    notes.push('Joint Singles Scheme: 2 or more SC singles buying together. Each applicant must be ≥35. EHG uses combined household income (≤$9k).');
  }
  if (isWithSCParents) {
    notes.push('Single with Parents: PHG (Singles) applies — $15,000 to live with parents/child (same flat), $10,000 within 4km.');
  }
  if (isSingleScheme) {
    notes.push('Singapore Single Scheme: PHG (Singles) available — $15,000 to live with parents/child, $10,000 within 4km.');
  }
  if (isPRWithPRParents) {
    notes.push('PR + PR Parents: At least one parent must be PR for at least 3 years. No grants apply.');
  }
  if (isPRWithSCParents) {
    notes.push('PR + SC Parents: At least one parent must be SC for grants to apply.');
  }
  if (income > 14000) {
    warns.push('Income >$14k: No HDB grants eligible.');
  } else if (income > 9000 && !isJointSingle && ftimer === 'first') {
    notes.push('Income >$9k: EHG not applicable. CPF Housing Grant still applies (≤$14k for some; ≤$7k for singles).');
  } else if (income > 9000 && isJointSingle && ftimer === 'first') {
    notes.push('JSS: Combined household income >$9k — EHG not applicable. CPF Housing Grant still applies up to $14k combined income.');
  }

  return { eligible, warns, notes };
}

export function whyText(town, ftype, score, pd, budget, active = [], avgScore = 0, qualifyingFlats = 0) {
  const savings = budget - pd.median;
  const under = savings > 0;
  const tr = pd.trend12;

  // Amenity criteria the user actively selected (exclude budget/flat/region/floor/lease)
  const NON_PREF = new Set(['budget', 'flat', 'region', 'floor', 'lease']);
  const amenLabels = { mrt: 'MRT stations', hawker: 'hawker centres', mall: 'shopping malls', park: 'parks', school: 'schools', hospital: 'hospitals' };
  const userPrefs = active.filter(c => !NON_PREF.has(c));
  const prefNames = userPrefs.map(c => amenLabels[c] || c);

  // Scoring methodology sentence
  const methodNote = userPrefs.length === 0
    ? `Score is based on general amenity proximity (weighted cosine similarity with low confidence — no must-have amenities selected).`
    : userPrefs.length <= 2
      ? `Score is driven by proximity to ${prefNames.join(' and ')} using weighted cosine similarity, with ${userPrefs.length} of 7 preference dimensions active.`
      : `Score reflects a ${userPrefs.length}-dimension weighted cosine similarity across ${prefNames.join(', ')}.`;

  // Budget context
  const budgetNote = under
    ? `Median price is ~$${Math.abs(savings).toLocaleString()} under your budget, offering good value.`
    : 'Median price is slightly above base budget — grants and negotiation may close the gap.';

  // Supply context
  const supplyNote = qualifyingFlats > 0
    ? `${qualifyingFlats} qualifying ${ftype} listings were evaluated in ${town}.`
    : '';

  return [methodNote, budgetNote, supplyNote].filter(Boolean).join(' ');
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

// Colour by rank position (1 = best = green, n = worst = red)
// rank: 1-based rank; total: total number of estates
export function rankToColor(rank, total) {
  const t = total <= 1 ? 1 : 1 - (rank - 1) / (total - 1); // 1.0 for rank 1, 0.0 for rank N
  // gradient: red(192,57,43) → gold(192,174,43) → green(39,174,67)
  if (t <= 0.5) {
    const s = t * 2;
    const green = Math.round(57 + s * (174 - 57));
    return `rgb(192,${green},43)`;
  } else {
    const s = (t - 0.5) * 2;
    const red = Math.round(192 - s * (192 - 39));
    return `rgb(${red},174,67)`;
  }
}
