import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export interface PortfolioView {
  cash: string
  positions: Record<string, string>
  costs: Record<string, string>
  ledger: Array<{ id: string; cash_delta: string; symbol?: string; quantity_delta: string }>
}

export function PortfolioPage({ portfolio }: { portfolio: PortfolioView }) {
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold">实际组合</h1>
      <p>现金：{portfolio.cash}</p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>标的</TableHead>
            <TableHead>持仓</TableHead>
            <TableHead>成本</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Object.entries(portfolio.positions).map(([symbol, quantity]) => (
            <TableRow key={symbol}>
              <TableCell>{symbol}</TableCell>
              <TableCell>{quantity}</TableCell>
              <TableCell>{portfolio.costs[symbol]}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <h2>不可变账本</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID</TableHead>
            <TableHead>现金变化</TableHead>
            <TableHead>标的</TableHead>
            <TableHead>数量变化</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {portfolio.ledger.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell>{entry.id}</TableCell>
              <TableCell>{entry.cash_delta}</TableCell>
              <TableCell>{entry.symbol ?? "-"}</TableCell>
              <TableCell>{entry.quantity_delta}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
