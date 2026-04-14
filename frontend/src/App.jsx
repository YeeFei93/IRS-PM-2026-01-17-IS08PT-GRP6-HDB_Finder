import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import Welcome from './components/Welcome';
import Loading from './components/Loading';
import Empty from './components/Empty';
import ResultsPane from './components/ResultsPane';
import MapView from './pages//MapView';
import TrendsView from './pages/TrendsView';
import { REGIONS, ALL_TOWNS, API_BASE } from './constants';
import { calcGrants, loanCapacity, checkEligibility, checkLoanLimit, checkLeaseAgeCriteria } from './engine';
import { fetchTown, checkBackendHealth, runSearchBackend, normaliseBackendRec } from './api';
import MainView from './pages/MainView';

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
  const [activeTab, setActiveTab] = useState('results');
  const [phase, setPhase] = useState('welcome'); // welcome | loading | results | empty
  const [recs, setRecs] = useState([]);
  const [rawCount, setRawCount] = useState(0);
  const [latestMonth, setLatestMonth] = useState(null);
  const [highlightedTown, setHighlightedTown] = useState(null);
  const [loadMainText, setLoadMainText] = useState('');
  const [loadStepText, setLoadStepText] = useState('');
  const loadStepRef = useRef(null);

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

    setPhase('loading');
    setActiveTab('map');
    const steps = [
      'Connecting to data.gov.sg…',
      'Fetching resale transactions…',
      'Running data quality checks…',
      'Analysing prices per town…',
      'Computing amenity scores…',
      'Ranking recommendations…',
    ];
    let si = 0;
    setLoadMainText('Connecting to data.gov.sg…');
    setLoadStepText(steps[0]);
    loadStepRef.current = setInterval(() => {
      si++;
      setLoadStepText(steps[Math.min(si, steps.length - 1)]);
    }, 900);

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
      setLoadMainText('Sending request to recommendation engine… (first run may take up to 60s)');
      try {
        const payload = { ...formState, effective: derived.effective, grants: derived.grants };
        const res = await runSearchBackend(payload);
        clearInterval(loadStepRef.current);
        // Express wraps the Python result in { status, result: {...} }
        const data = res.result ?? res;
        const topRecs = (data.recommendations || []).map(normaliseBackendRec).slice(0, 10);
        setRawCount(data.raw_count || topRecs.length);
        setLatestMonth(data.latest_month || null);
        setRecs(topRecs);
        setPhase(topRecs.length ? 'results' : 'empty');
        return;
      } catch (e) {
        clearInterval(loadStepRef.current);
        console.error('Backend search failed:', e);
        setPhase('empty');
        return;
      }
    }

    // No backend configured — show empty state
    clearInterval(loadStepRef.current);
    setPhase('empty');
  }, [formState, derived]);

  // Cleanup interval on unmount
  useEffect(() => {
    return () => { if (loadStepRef.current) clearInterval(loadStepRef.current); };
  }, []);

  

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
          isSearching={phase === 'loading'}
        />
        <main className="flex flex-col overflow-y-auto h-[calc(100vh-56px)]">
          {/* Results Tab */}
          {activeTab === 'results' && (
            <MainView phase={phase}
              loadMainText={loadMainText}
              loadStepText={loadStepText} 
              recs={recs}
              derived={derived}
              formState={formState}
              rawCount={rawCount}
              latestMonth={latestMonth}
              highlightedTown={highlightedTown}
              setHighlightedTown={setHighlightedTown}
            
            />
          )}

          {/* Map Tab */}
          {activeTab === 'map' && (
          <MapView recs={recs} highlightedTown={highlightedTown} formState={formState} effectiveBudget={derived.effective} derived={derived} rawCount={rawCount} latestMonth={latestMonth} />
          )}

          {/* Trends Tab */}
          {activeTab === 'trends' && (
            <TrendsView recs={recs} />
          )}
        </main>
      </div>
    </div>
  );
}
