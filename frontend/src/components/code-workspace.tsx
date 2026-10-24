import { Check, Code2, Copy, Maximize2, Search, WrapText } from "lucide-react"
import type { editor } from "monaco-editor"
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react"
import { ErrorBoundary } from "react-error-boundary"

import { IconButton } from "@/components/icon-button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import type { LibraryEntry } from "@/features/strategies/types"

export function CodeWorkspace({
  value,
  onChange,
  readOnly = true,
  expanded = false,
  completions,
}: {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
  expanded?: boolean
  completions?: LibraryEntry[]
}) {
  const [full, setFull] = useState(false)
  const [wrap, setWrap] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState("")
  useEffect(() => {
    setCopied(false)
  }, [value])
  const [attempt, setAttempt] = useState(0)
  const [ready, setReady] = useState(false)
  const instance = useRef<editor.IStandaloneCodeEditor>(null)
  const Surface = useMemo(() => {
    void attempt
    return lazy(() => import("./monaco-surface"))
  }, [attempt])
  const height = expanded ? "calc(85dvh - 11rem)" : readOnly ? 360 : 480
  return (
    <>
      <div
        className="min-w-0 overflow-hidden rounded-lg border bg-background"
        aria-label={readOnly ? "Python 代码预览容器" : "策略代码编辑器"}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/50 px-3 py-2">
          <div className="flex items-center gap-2">
            <Code2 className="size-4 text-primary" />
            <span className="font-mono text-xs">strategy.py</span>
            <Badge variant="secondary">Python · {readOnly ? "只读" : "草稿"}</Badge>
          </div>
          <div className="flex items-center gap-1">
            <IconButton
              icon={Search}
              label="搜索代码"
              size="icon-sm"
              disabled={!ready}
              onClick={() => void instance.current?.getAction("actions.find")?.run()}
            />
            <IconButton
              icon={WrapText}
              label="自动换行"
              size="icon-sm"
              aria-pressed={wrap}
              onClick={() => setWrap((value) => !value)}
            />
            <IconButton
              icon={copied ? Check : Copy}
              label={copied ? "已复制代码" : "复制代码"}
              size="icon-sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(value)
                  setCopied(true)
                  setError("")
                } catch {
                  setError("复制失败，请使用编辑器选择代码后复制。")
                }
              }}
            />
            {!expanded && (
              <IconButton
                icon={Maximize2}
                label="放大代码预览"
                size="icon-sm"
                onClick={() => setFull(true)}
              />
            )}
          </div>
        </div>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <ErrorBoundary
          key={attempt}
          fallbackRender={() => (
            <div className="flex flex-col gap-3 p-3">
              <Alert variant="destructive">
                <AlertDescription>
                  专业编辑器加载失败，当前代码已保留，可使用基础文本视图。
                </AlertDescription>
              </Alert>
              <Textarea
                aria-label="基础代码视图"
                value={value}
                readOnly={readOnly}
                onChange={(event) => onChange?.(event.target.value)}
                className="min-h-64 font-mono"
              />
              <Button
                variant="outline"
                onClick={() => {
                  setReady(false)
                  setAttempt((value) => value + 1)
                }}
              >
                重试加载编辑器
              </Button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <div role="status" className="p-3">
                <Skeleton className="h-80 w-full" />
                <span className="sr-only">正在加载代码编辑器</span>
              </div>
            }
          >
            <Surface
              value={value}
              onChange={onChange}
              readOnly={readOnly}
              height={height}
              wrap={wrap}
              completions={completions}
              onReady={(editor) => {
                instance.current = editor
                setReady(true)
              }}
            />
          </Suspense>
        </ErrorBoundary>
        <div className="flex flex-wrap justify-between gap-2 border-t px-3 py-2 text-xs text-muted-foreground">
          <span>{value.split("\n").length} 行 · UTF-8</span>
          <span>
            {readOnly ? "Ctrl/Cmd+F 搜索" : "Ctrl+Space 补全 · Tab 缩进 · Ctrl/Cmd+F 搜索"}
          </span>
        </div>
      </div>
      {!expanded && (
        <Dialog open={full} onOpenChange={setFull}>
          <DialogContent className="flex max-h-[95dvh] min-w-0 flex-col sm:max-w-[90vw]">
            <DialogHeader>
              <DialogTitle>{readOnly ? "策略代码预览" : "编辑策略代码"}</DialogTitle>
              <DialogDescription>
                Python · {readOnly ? "只读代码" : "修改同步至当前草稿，仍需保存"}
              </DialogDescription>
            </DialogHeader>
            {full && (
              <CodeWorkspace
                value={value}
                onChange={onChange}
                readOnly={readOnly}
                expanded
                completions={completions}
              />
            )}
          </DialogContent>
        </Dialog>
      )}
    </>
  )
}
