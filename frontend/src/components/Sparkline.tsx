export default function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) {
    return <div className="spark spark-empty" aria-hidden="true" />;
  }
  const w = 280;
  const h = 44;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - 3 - ((v - min) / span) * (h - 6);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="var(--amber)" strokeWidth="1.6" />
    </svg>
  );
}
