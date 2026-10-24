import "monaco-editor/languages/definitions/python/register"
import "monaco-editor/features/find/register"
import "monaco-editor/features/folding/register"
import "monaco-editor/features/suggest/register"
import "monaco-editor/editor/contrib/suggest/browser/suggestController"
import "monaco-editor/features/snippet/register"
import "monaco-editor/features/hover/register"
import "monaco-editor/features/tokenization/register"
import "monaco-editor/features/bracketMatching/register"
import "monaco-editor/features/clipboard/register"
import "monaco-editor/features/comment/register"
import "monaco-editor/features/wordOperations/register"

import Editor, { loader } from "@monaco-editor/react"
import * as monaco from "monaco-editor/editor"
import editorWorker from "monaco-editor/editor/editor.worker?worker"
import { useEffect, useState } from "react"

import type { LibraryEntry } from "@/features/strategies/types"

self.MonacoEnvironment = { getWorker: () => new editorWorker() }
loader.config({ monaco })

export default function MonacoSurface({
  value,
  onChange,
  readOnly,
  wrap,
  height,
  onReady,
  completions = [],
}: {
  value: string
  onChange?: (value: string) => void
  readOnly: boolean
  wrap: boolean
  height: string | number
  onReady: (editor: monaco.editor.IStandaloneCodeEditor) => void
  completions?: LibraryEntry[]
}) {
  const [editor, setEditor] = useState<monaco.editor.IStandaloneCodeEditor>()
  useEffect(() => {
    if (!editor || readOnly) return
    const provider = monaco.languages.registerCompletionItemProvider("python", {
      triggerCharacters: ["."],
      provideCompletionItems(model, position) {
        if (model !== editor.getModel()) return { suggestions: [] }
        const word = model.getWordUntilPosition(position)
        const prefix = model.getLineContent(position.lineNumber).slice(0, position.column - 1)
        const range = new monaco.Range(
          position.lineNumber,
          word.startColumn,
          position.lineNumber,
          word.endColumn,
        )
        const access = prefix.match(/context\.([\w.]*)$/)?.[1]
        const inContext = access !== undefined
        const qualifier = access?.slice(0, access.lastIndexOf(".") + 1) ?? ""
        const items: monaco.languages.CompletionItem[] = completions.flatMap((entry) => {
          const names =
            entry.key === "store"
              ? ["store.get", "store.set", "store.delete"].map((name) => ({ name, callable: true }))
              : Array.from(entry.signature.matchAll(/context\.([\w.]+)(\()?/g), (match) => ({
                  name: match[1],
                  callable: !!match[2],
                }))
          return names
            .filter(({ name }) => !inContext || name.startsWith(qualifier))
            .map(({ name, callable }) => {
              const relative = inContext ? name.slice(qualifier.length) : `context.${name}`
              return {
                label: relative,
                detail: entry.signature,
                documentation: `${entry.description}\n\n参数：${entry.parameters}\n返回值：${entry.output}`,
                kind: callable
                  ? monaco.languages.CompletionItemKind.Function
                  : monaco.languages.CompletionItemKind.Property,
                range,
                insertText: callable ? `${relative}(\${1})` : relative,
                insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
              }
            })
        })
        if (!inContext)
          for (const phase of ["before_market", "on_market", "after_market"])
            items.push({
              label: phase,
              detail: "策略阶段模板",
              documentation: "插入平台策略阶段函数。",
              kind: monaco.languages.CompletionItemKind.Snippet,
              range,
              insertText: `def ${phase}(context, parameters):\n    \${1:return []}`,
              insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            })
        return { suggestions: items }
      },
    })
    return () => provider.dispose()
  }, [editor, completions, readOnly])
  return (
    <Editor
      height={height}
      language="python"
      value={value}
      theme="vs"
      onChange={(value) => onChange?.(value ?? "")}
      onMount={(instance) => {
        setEditor(instance)
        onReady(instance)
      }}
      options={{
        readOnly,
        domReadOnly: readOnly,
        ariaLabel: readOnly ? "策略代码预览" : "策略代码",
        automaticLayout: true,
        editContext: false,
        minimap: { enabled: false },
        fontSize: 13,
        lineHeight: 22,
        lineNumbers: "on",
        scrollBeyondLastLine: false,
        wordWrap: wrap ? "on" : "off",
        padding: { top: 12, bottom: 12 },
        folding: true,
        renderLineHighlight: readOnly ? "none" : "line",
        tabSize: 4,
        insertSpaces: true,
        autoIndent: "full",
        autoClosingBrackets: "always",
        bracketPairColorization: { enabled: true },
        quickSuggestions: !readOnly,
        suggestOnTriggerCharacters: !readOnly,
        fixedOverflowWidgets: true,
      }}
    />
  )
}
