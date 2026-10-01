import { python } from "@codemirror/lang-python"
import { basicSetup, EditorView } from "codemirror"
import { useEffect, useRef } from "react"

export function StrategyEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  const host = useRef<HTMLDivElement>(null)
  const initialValue = useRef(value)
  const viewRef = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  useEffect(() => {
    if (!host.current) return
    const view = new EditorView({
      parent: host.current,
      doc: initialValue.current,
      extensions: [
        basicSetup,
        python(),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) onChangeRef.current(update.state.doc.toString())
        }),
      ],
    })
    viewRef.current = view
    return () => {
      viewRef.current = null
      view.destroy()
    }
  }, [])
  useEffect(() => {
    const view = viewRef.current
    if (view && view.state.doc.toString() !== value) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
    }
  }, [value])
  return <div aria-label="策略代码编辑器" className="rounded border" ref={host} />
}
