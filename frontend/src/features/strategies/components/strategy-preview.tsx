import { Link } from "react-router-dom"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export interface StrategyContext {
  id: string
  name: string
  description: string
  version_id: string
  number: number
  source_code: string
}

export function StrategyPreview({
  strategy,
  versionId,
}: {
  strategy?: StrategyContext | null
  versionId: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{strategy?.name ?? "策略版本"}</CardTitle>
        <CardDescription>
          {strategy?.description} · {strategy ? `v${strategy.number}` : versionId}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {strategy ? (
          <>
            <Link
              className="underline"
              to={`/strategies?strategy=${encodeURIComponent(strategy.id)}&version=${encodeURIComponent(strategy.version_id)}`}
            >
              查看或编辑此策略版本
            </Link>
            <details>
              <summary className="cursor-pointer">预览策略代码</summary>
              <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs">
                {strategy.source_code}
              </pre>
            </details>
          </>
        ) : (
          <p>策略信息不可用，版本 {versionId}</p>
        )}
      </CardContent>
    </Card>
  )
}
