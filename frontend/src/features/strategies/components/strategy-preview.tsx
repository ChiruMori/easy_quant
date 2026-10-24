import { FilePenLine } from "lucide-react"
import { Link } from "react-router-dom"

import { CodePreview } from "@/components/code-preview"
import { Button } from "@/components/ui/button"
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
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="break-words">{strategy?.name ?? "策略版本"}</CardTitle>
        <CardDescription className="break-words">
          {strategy?.description} · {strategy ? `v${strategy.number}` : versionId}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-3">
        {strategy ? (
          <CodePreview
            value={strategy.source_code}
            actions={
              <Button variant="outline" size="sm" asChild>
                <Link
                  to={`/strategies/${encodeURIComponent(strategy.id)}/versions/${encodeURIComponent(strategy.version_id)}`}
                >
                  <FilePenLine />
                  查看或编辑此策略版本
                </Link>
              </Button>
            }
          />
        ) : (
          <p>策略信息不可用，版本 {versionId}</p>
        )}
      </CardContent>
    </Card>
  )
}
