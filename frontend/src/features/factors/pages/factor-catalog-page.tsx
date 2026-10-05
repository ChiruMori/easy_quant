import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

import type { FactorDefinition } from "../api"
import { listFactors } from "../api"

export function FactorCatalogPage({ factors }: { factors?: FactorDefinition[] } = {}) {
  const [search, setSearch] = useState("")
  const query = useQuery({
    queryKey: ["factors"],
    queryFn: listFactors,
    initialData: factors,
    enabled: factors === undefined,
  })
  const visible = useMemo(
    () =>
      (query.data ?? []).filter((item) =>
        `${item.name}${item.key}${item.description}`.toLowerCase().includes(search.toLowerCase()),
      ),
    [query.data, search],
  )
  if (query.isLoading) return <LoadingState label="正在加载因子目录" />
  if (query.error) return <ErrorState title="无法加载因子目录" message={query.error.message} />
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">因子目录</h1>
        <p className="text-muted-foreground">
          因子由平台随版本提供，只读并可在策略中通过 context.factor 调用。
        </p>
      </div>
      <Input
        aria-label="搜索因子"
        placeholder="搜索名称、Key 或描述"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        {visible.map((factor) => (
          <Card key={factor.key}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <CardTitle>{factor.name}</CardTitle>
                <Badge variant="secondary">{factor.key}</Badge>
              </div>
              <CardDescription>{factor.description}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <section>
                <h3 className="text-sm font-medium">参数</h3>
                <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  {Object.entries(factor.parameters).map(([name, description]) => (
                    <span className="contents" key={name}>
                      <dt>
                        <code>{name}</code>
                      </dt>
                      <dd className="text-muted-foreground">{description}</dd>
                    </span>
                  ))}
                </dl>
              </section>
              <section>
                <h3 className="text-sm font-medium">输出</h3>
                <p className="text-sm text-muted-foreground">{factor.output}</p>
                <p className="mt-2 text-xs text-muted-foreground">输出示例（示意值）</p>
                <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-3 text-xs">
                  <code>{factor.output_example}</code>
                </pre>
              </section>
              <section>
                <h3 className="text-sm font-medium">策略用法</h3>
                <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-3 text-xs">
                  <code>{factor.example.replace("factor(", "context.factor(")}</code>
                </pre>
              </section>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
