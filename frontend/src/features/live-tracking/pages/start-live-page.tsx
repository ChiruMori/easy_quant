import { useState } from "react"

import { Button } from "@/components/ui/button"

import { startLive } from "../api"

export function StartLivePage({
  backtestId,
  strategyVersionId,
}: {
  backtestId: string
  strategyVersionId: string
}) {
  const [status, setStatus] = useState("")
  return (
    <div>
      <Button
        onClick={async () => setStatus((await startLive(backtestId, strategyVersionId)).status)}
      >
        从成功回测启动实盘
      </Button>
      <p aria-live="polite">{status}</p>
    </div>
  )
}
