import { useState, useCallback, useMemo } from 'react';
import Sidebar from './components/Sidebar';
import MapView from './pages//MapView';
import { REGIONS, ALL_TOWNS, API_BASE } from './constants';
import { calcGrants, loanCapacity, checkEligibility, checkLoanLimit, checkLeaseAgeCriteria } from './engine';
import { fetchTown, checkBackendHealth, runSearchBackend, normaliseBackendRec } from './api';


const INITIAL_FORM = {
  cit: 'SC_SC',
  age: 32,
  marital: 'married',
  inc: 6500,
  ftimer: 'first',
  prox: 'none',
  ftype: [],
  selRegions: [],
  floor: [],
  lease: 50,
  cash: 30000,
  cpf: 80000,
  loan: 1800,
  mustAmenities: [],
};

export default function App() {
  const [formState, setFormState] = useState(INITIAL_FORM);
  const [isSearching, setIsSearching] = useState(false);
  const [recs, setRecs] = useState([]);
  const [rawCount, setRawCount] = useState(0);
  const [latestMonth, setLatestMonth] = useState(null);
  const [highlightedTown, setHighlightedTown] = useState(null);
  const [warning, setWarning] = useState()

  const onFormChange = useCallback((key, value) => {
    setFormState(prev => ({ ...prev, [key]: value }));
  }, []);

  // Derived eligibility/grant/budget calculations
  const derived = useMemo(() => {
    const { cit, age, inc, ftimer, prox, ftype, cash, cpf, loan, marital, lease } = formState;
    const eligibility = checkEligibility(cit, inc, age, marital);
    // For grant calc, use conservative fallback when no specific type selected
    const ftypeForGrants = Array.isArray(ftype) && ftype.length > 0
      ? (ftype.every(t => ['5 ROOM', 'EXECUTIVE'].includes(t)) ? '5 ROOM' : '4 ROOM')
      : '4 ROOM';
    const grants = calcGrants(cit, inc, ftypeForGrants, ftimer, prox, marital);
    const loanAmt = loanCapacity(loan);
    const effective = cash + cpf + grants.total + loanAmt;
    const loanLimitWarning = checkLoanLimit(inc, loan, cash + cpf + grants.total + loanAmt);
    const leaseAgeWarning = checkLeaseAgeCriteria(age, lease);
    return { eligibility, grants, effective, loanAmt, loanLimitWarning, leaseAgeWarning };
  }, [formState]);

  const runSearch = useCallback(async () => {
    if (!derived.eligibility.eligible) {
      alert('Please resolve eligibility issues before searching.');
      return;
    }

    setIsSearching(true);

    const { selRegions, ftype, lease: minLease, age: buyerAge } = formState;
    const towns = selRegions.length
      ? selRegions.flatMap(r => REGIONS[r] || [])
      : ALL_TOWNS;

    // ── Try backend first ──
    let backendOk = false;
    if (API_BASE) {
      try {
        backendOk = await checkBackendHealth();
      } catch { backendOk = false; }
    }

    if (backendOk) {
      setWarning()
      try {
        const payload = { ...formState, effective: derived.effective, grants: derived.grants };
        const res = await runSearchBackend(payload);
        console.log({74: res})
        // Express wraps the Python result in { status, result: {...} }
        const data = res.result ?? res;
        if(data.recommendations && data.recommendations.length == 0){
          setWarning("No eligible flats found. Please re-adjust your inputs and try again.")
        }
        const topRecs = (data.recommendations || []).map(rec => normaliseBackendRec(rec, data.selected_model));
        setRawCount(data.raw_count || topRecs.length);
        setLatestMonth(data.latest_month || null);
        setRecs(topRecs);
        setIsSearching(false);
        return;
      } catch (e) {
        console.error('Backend search failed:', e);
        setIsSearching(false);
        return;
      }
    }

    // No backend configured
    setIsSearching(false);
  }, [formState, derived]);

  return (
    <div className="min-h-screen">
      <div className="grid grid-cols-[400px_1fr] min-h-screen">
        <Sidebar
          formState={formState}
          onFormChange={onFormChange}
          eligibility={derived.eligibility}
          grants={derived.grants}
          effective={derived.effective}
          loanAmt={derived.loanAmt}
          loanLimitWarning={derived.loanLimitWarning}
          leaseAgeWarning={derived.leaseAgeWarning}
          onSearch={runSearch}
          isSearching={isSearching}
        />
        <main className="flex flex-col overflow-y-auto h-screen">
          <div className="relative flex-1 z-0">
            <MapView recs={recs} highlightedTown={highlightedTown} formState={formState} effectiveBudget={derived.effective} derived={derived} rawCount={rawCount} latestMonth={latestMonth} />
            {warning && (
              <div className="absolute inset-0 z-[9999] flex items-center justify-center p-8 pointer-events-none">
                <div className="max-w-xl inline-flex min-w-[320px] bg-black/85 backdrop-blur-md border-2 border-yellow-400 rounded-2xl px-10 py-8 shadow-2xl items-center space-x-8">
                  <div className="flex-shrink-0 flex h-12 w-12 items-center justify-center  text-3xl">
                    ⚠️
                  </div>
                  <div className="min-w-0 text-white font-semibold text-lg leading-relaxed">
                    <span className="inline-block px-4 py-2">{warning}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
