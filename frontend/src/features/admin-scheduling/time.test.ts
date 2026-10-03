import { describe, expect, it } from "vitest"

import { formatBeijingTime } from "./time"

describe("formatBeijingTime", () => {
  it("displays a UTC job time as Beijing time", () => {
    expect(formatBeijingTime("2026-10-03T11:23:32+00:00")).toContain("19:23:32")
  })
})
