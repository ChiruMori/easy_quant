import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { apiRequest } from "@/lib/api/client"

export interface LibraryEntry {
  key: string
  name: string
  signature: string
  description: string
  parameters: string
  output: string
  example: string
  runtime: string
}

export function StrategyLibraryPage() {
  const [search, setSearch] = useState("")
  const query = useQuery({
    queryKey: ["strategy-library"],
    queryFn: () => apiRequest<LibraryEntry[]>("/strategy-library"),
  })
  if (query.isLoading) return <LoadingState label="正在加载策略公共库" />
  if (query.error) return <ErrorState title="无法加载策略公共库" message={query.error.message} />
  const visible = (query.data ?? []).filter((entry) =>
    `${entry.name}${entry.signature}${entry.description}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  )
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">策略公共库</h1>
        <p className="text-muted-foreground">
          快测、回测与实盘共用接口。计算指标请查阅{" "}
          <Link to="/factors" className="underline">
            因子目录
          </Link>
          。
        </p>
      </div>
      <Input
        aria-label="搜索库函数"
        placeholder="搜索名称、签名或描述"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {visible.length === 0 && <p>没有匹配的库函数。</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        {visible.map((entry) => (
          <Card key={entry.key}>
            <CardHeader>
              <CardTitle>
                {entry.name} <Badge variant="secondary">{entry.key}</Badge>
              </CardTitle>
              <CardDescription>{entry.description}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                <code>{entry.signature}</code>
              </pre>
              <section>
                <h2 className="font-medium">参数</h2>
                <p className="text-sm text-muted-foreground">{entry.parameters}</p>
              </section>
              <section>
                <h2 className="font-medium">返回值</h2>
                <p className="text-sm text-muted-foreground">{entry.output}</p>
              </section>
              <section>
                <h2 className="font-medium">运行时与限制</h2>
                <p className="text-sm text-muted-foreground">{entry.runtime}</p>
              </section>
              <section>
                <h2 className="font-medium">调用示例</h2>
                <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                  <code>{entry.example}</code>
                </pre>
              </section>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
