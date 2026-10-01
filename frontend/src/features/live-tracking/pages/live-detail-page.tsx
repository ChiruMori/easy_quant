import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { localizedLabel } from "@/lib/labels"

import type { LiveInstance } from "../api"
import { actOnRecommendation, pauseLive, terminateLive } from "../api"
import { RecommendationActions } from "../components/recommendation-actions"

export function LiveDetailPage({ instance }: { instance: LiveInstance }) {
  const [current, setCurrent] = useState(instance)
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">实盘实例 {current.id}</h1>
        <p className="text-muted-foreground">状态：{localizedLabel(current.status)}</p>
      </div>
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={current.status !== "active"}
          onClick={async () => setCurrent(await pauseLive(current.id))}
        >
          暂停
        </Button>
        <Button
          variant="destructive"
          disabled={current.status === "terminated"}
          onClick={async () => setCurrent(await terminateLive(current.id))}
        >
          终止
        </Button>
      </div>
      <h2 className="text-lg font-semibold">建议</h2>
      <div className="flex flex-col gap-4">
        {current.recommendations?.map((item) => (
          <Card key={item.id}>
            <CardHeader>
              <CardTitle>
                {item.instrument_id} · {localizedLabel(item.action)} {item.quantity}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-4 text-sm text-muted-foreground">
                {item.reason} · {localizedLabel(item.status)}
              </p>
              <RecommendationActions
                onSubmit={(kind, values) =>
                  void actOnRecommendation(item.id, kind, item.version, values)
                }
              />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
