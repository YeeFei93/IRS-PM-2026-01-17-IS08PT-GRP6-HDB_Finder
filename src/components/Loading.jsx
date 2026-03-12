export default function Loading({ mainText, stepText }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3.5 p-12">
      <div className="w-10 h-10 border-[3px] border-dk4 border-t-gold rounded-full animate-spin-slow" />
      <div className="font-mono text-[0.82rem] text-muted">{mainText}</div>
      <div className="text-[0.76rem] text-dk4 animate-pulse-slow">{stepText}</div>
    </div>
  );
}
