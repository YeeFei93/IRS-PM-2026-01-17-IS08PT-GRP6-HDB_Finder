const TABS = ['map'];
const TAB_LABELS = ['Map View'];

export default function Header({ activeTab, onTabChange }) {
  return (
    <header className="bg-dk2 border-b border-dk4 px-6 flex items-center justify-between h-14 sticky top-0 z-[1000]">
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 bg-gradient-to-br from-red to-gold rounded-[7px] flex items-center justify-center text-base">
          🏠
        </div>
        <div>
          <div className="font-serif text-[1.15rem] text-white">HDB Finder</div>
          <div className="text-[0.62rem] text-muted tracking-[1.5px] uppercase">
            Singapore Estate Recommender
          </div>
        </div>
      </div>
      <div className="flex gap-0.5">
        {TABS.map((tab, i) => (
          <button
            key={tab}
            onClick={() => onTabChange(tab)}
            className={`px-3.5 py-1.5 border rounded-[5px] text-[0.8rem] font-sans cursor-pointer transition-all duration-150
              ${activeTab === tab
                ? 'bg-dk4 text-light border-mid'
                : 'bg-transparent text-muted border-transparent hover:bg-dk4 hover:text-light hover:border-mid'
              }`}
          >
            {TAB_LABELS[i]}
          </button>
        ))}
      </div>
    </header>
  );
}
