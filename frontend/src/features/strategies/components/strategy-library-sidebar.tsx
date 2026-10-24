import { useQuery } from "@tanstack/react-query"
import { ArrowUpRight } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { apiRequest } from "@/lib/api/client"

import type { LibraryEntry } from "../types"

export function StrategyLibrarySidebar() {
  const [search, setSearch] = useState("")
  const query = useQuery({
    queryKey: ["strategy-library"],
    queryFn: () => apiRequest<LibraryEntry[]>("/strategy-library"),
  })
  const entries = (query.data ?? []).filter((entry) =>
    `${entry.key} ${entry.name} ${entry.signature} ${entry.description}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  )
  return (
    <aside aria-label="策略公共库" className="min-w-0 xl:sticky xl:top-5 xl:self-start">
      <Card className="flex min-w-0 flex-col overflow-hidden xl:max-h-[calc(100dvh-8rem)]">
        <CardHeader className="shrink-0">
          <CardTitle>
            <h2>策略公共库</h2>
          </CardTitle>
          <CardDescription>快测、回测、实盘共用接口。</CardDescription>
          <Button variant="outline" size="sm" className="w-fit" asChild>
            <Link to="/factors">
              <ArrowUpRight />
              因子目录
            </Link>
          </Button>
          <Input
            aria-label="搜索库函数"
            placeholder="搜索名称、签名或描述"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </CardHeader>
        <CardContent className="min-h-0 overflow-y-auto">
          {query.isLoading && <LoadingState label="正在加载策略公共库" />}
          {query.error && <ErrorState title="无法加载策略公共库" message={query.error.message} />}
          {query.isSuccess && entries.length === 0 && (
            <p className="text-sm text-muted-foreground">没有匹配的库函数。</p>
          )}
          <Accordion type="multiple">
            {entries.map((entry) => (
              <AccordionItem key={entry.key} value={entry.key}>
                <AccordionTrigger>
                  <span className="min-w-0 break-words">
                    {entry.name}
                    <span className="block text-xs text-muted-foreground">{entry.key}</span>
                  </span>
                </AccordionTrigger>
                <AccordionContent className="flex min-w-0 flex-col gap-3">
                  <p>{entry.description}</p>
                  <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                    <code>{entry.signature}</code>
                  </pre>
                  <dl className="flex flex-col gap-2">
                    <dt className="font-medium">参数</dt>
                    <dd>{entry.parameters}</dd>
                    <dt className="font-medium">返回值</dt>
                    <dd>{entry.output}</dd>
                    <dt className="font-medium">运行时与限制</dt>
                    <dd>{entry.runtime}</dd>
                  </dl>
                  <p className="font-medium">调用示例</p>
                  <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                    <code>{entry.example}</code>
                  </pre>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </CardContent>
      </Card>
    </aside>
  )
}
