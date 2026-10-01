import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import { commitImport, previewImport } from "../api"
import type { ImportPreview } from "../types"

export function ImportPage() {
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [message, setMessage] = useState("")
  const [datasetKey, setDatasetKey] = useState("daily-bars")
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>上传行情数据</CardTitle>
        <CardDescription>
          日线使用固定行情列；其他数据至少包含 symbol 与 available_at。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Select value={datasetKey} onValueChange={setDatasetKey}>
          <SelectTrigger aria-label="导入数据集">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="daily-bars">日线 K 线</SelectItem>
            <SelectItem value="market-values">估值与市值</SelectItem>
            <SelectItem value="pledge-ratios">股票质押率</SelectItem>
            <SelectItem value="financial-indicators">财务指标</SelectItem>
            <SelectItem value="industry-memberships">行业归属</SelectItem>
            <SelectItem value="security-profiles">证券资料</SelectItem>
          </SelectContent>
        </Select>
        <Input
          aria-label="选择 CSV 文件"
          type="file"
          accept=".csv"
          onChange={async (event) => {
            setMessage("")
            const file = event.target.files?.[0]
            if (file) setPreview(await previewImport(file, datasetKey))
          }}
        />
        {preview && (
          <p>
            {preview.valid
              ? `预检通过：${preview.rows} 行`
              : `发现 ${preview.issues.length} 个错误`}
          </p>
        )}
        {preview?.issues.map((issue) => (
          <p className="text-sm text-destructive" key={`${issue.row}-${issue.field}`}>
            第 {issue.row} 行 · {issue.field}：{issue.message}
          </p>
        ))}
        {message && <p className="text-sm text-muted-foreground">{message}</p>}
        <Button
          disabled={!preview?.valid}
          onClick={async () => {
            if (preview?.preview_id) {
              const result = await commitImport(preview.preview_id)
              setMessage(
                result.status === "succeeded"
                  ? `已导入 ${result.rows} 行数据，覆盖 ${result.overwritten} 行`
                  : "导入失败",
              )
              setPreview(null)
            }
          }}
        >
          确认导入
        </Button>
      </CardContent>
    </Card>
  )
}
