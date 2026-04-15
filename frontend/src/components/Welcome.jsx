export default function Welcome() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-10 py-12 text-center bg-[radial-gradient(ellipse_at_50%_10%,rgba(192,57,43,0.05)_0%,transparent_65%)]">
      <h1 className="font-serif text-[2.6rem] text-white leading-tight mb-3.5">
        Find Your<br /><em className="text-gold italic">Perfect</em> HDB Flat
      </h1>
      <p className="text-[0.9rem] text-muted max-w-[460px] leading-relaxed mb-9">
        Set your profile, budget, and amenity preferences. We pull live resale data from
        data.gov.sg, compute all applicable grants, and rank the best options for you.
      </p>
      <div className="flex gap-4 flex-wrap justify-center">
        {[
          'Profile & eligibility',
          'Budget & flat type',
          'Amenity priorities',
          'Ranked flats by similarity',
        ].map((label, i) => (
          <div key={i} className="bg-dk2 border border-dk3 rounded-[10px] px-5 py-4 w-[148px] text-center">
            <div className="w-7 h-7 bg-gradient-to-br from-red to-gold rounded-full flex items-center justify-center text-[0.72rem] font-bold mx-auto mb-2">
              {i + 1}
            </div>
            <div className="text-[0.76rem] text-muted leading-snug">{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
