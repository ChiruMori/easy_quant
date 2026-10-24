import "@testing-library/jest-dom/vitest"

import { createElement } from "react"
import { vi } from "vitest"

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, "ResizeObserver", {
  writable: true,
  value: ResizeObserverMock,
})

vi.mock("@/components/monaco-surface", () => ({
  default: ({
    value,
    onChange,
    readOnly,
  }: {
    value: string
    onChange?: (value: string) => void
    readOnly: boolean
  }) =>
    createElement("textarea", {
      "aria-label": readOnly ? "策略代码预览" : "策略代码",
      value,
      readOnly,
      onChange: (event: { target: { value: string } }) => onChange?.(event.target.value),
    }),
}))
