export default function Empty() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-12 text-center gap-2.5">
      <div className="text-[2.5rem] opacity-25">🔍</div>
      <div className="font-serif text-[1.1rem] text-muted">No matching flats found</div>
      <div className="text-[0.76rem] text-dk4 max-w-[300px] leading-relaxed">
        Try increasing your budget, choosing more regions, or relaxing the amenity filters.
      </div>
    </div>
  );
}
