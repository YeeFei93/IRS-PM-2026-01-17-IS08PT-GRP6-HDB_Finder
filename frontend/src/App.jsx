import { useState, useCallback, useMemo } from 'react';
import Header from './components/Header';
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
  ftype: '4 ROOM',
  selRegions: [],
  floor: 'any',
  lease: 50,
  cash: 30000,
  cpf: 80000,
  loan: 1800,
  mustAmenities: [],
};

export default function App() {
  const [formState, setFormState] = useState(INITIAL_FORM);
  const [activeTab, setActiveTab] = useState('map');
  const [isSearching, setIsSearching] = useState(false);
  const [recs, setRecs] = useState([]);
  const [rawCount, setRawCount] = useState(0);
  const [latestMonth, setLatestMonth] = useState(null);
  const [highlightedTown, setHighlightedTown] = useState(null);

  const onFormChange = useCallback((key, value) => {
    setFormState(prev => ({ ...prev, [key]: value }));
  }, []);

  // Derived eligibility/grant/budget calculations
  const derived = useMemo(() => {
    const { cit, age, inc, ftimer, prox, ftype, cash, cpf, loan, marital, lease } = formState;
    const eligibility = checkEligibility(cit, inc, age, marital);
    const grants = calcGrants(cit, inc, ftype, ftimer, prox, marital);
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
    setActiveTab('map');

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
      try {
        const payload = { ...formState, effective: derived.effective, grants: derived.grants };
        const res = await runSearchBackend(payload);
        // Express wraps the Python result in { status, result: {...} }
        const data = res.result ?? res;
        const topRecs = (data.recommendations || []).map(normaliseBackendRec);
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
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="grid grid-cols-[400px_1fr] min-h-[calc(100vh-56px)]">
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
        <main className="flex flex-col overflow-y-auto h-[calc(100vh-56px)]">
          {/* Map Tab */}
          {activeTab === 'map' && (
          <MapView recs={recs} highlightedTown={highlightedTown} formState={formState} effectiveBudget={derived.effective} derived={derived} rawCount={rawCount} latestMonth={latestMonth} />
          )}

        </main>
      </div>
    </div>
  );
}
