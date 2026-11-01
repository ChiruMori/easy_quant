import { Link, useLocation } from "react-router-dom"

export function InstrumentLink({ symbol }: { symbol: string }) {
  const location = useLocation()
  return (
    <Link
      to={`/instruments/${encodeURIComponent(symbol)}`}
      state={{ from: `${location.pathname}${location.search}` }}
      className="font-medium text-primary hover:underline"
      aria-label={`查看 ${symbol} 股票详情`}
    >
      {symbol}
    </Link>
  )
}
