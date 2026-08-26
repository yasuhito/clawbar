const test = require("node:test")
const assert = require("node:assert/strict")
const Color = require("../ClawbarColor.js")

test("makePalette derives contrast-safe colors once for every row", () => {
  const palette = Color.makePalette({
    foreground: "#ffffff",
    accent: "#89b4fa",
    urgent: "#f38ba8",
    muted: "#a6adc8",
    healthy: "#a6e3a1",
    warning: "",
    panelSurface: "#11111b",
    selectedSurface: "#313244",
    fontFamily: "Sans"
  })

  assert.equal(palette.foreground, "#ffffff")
  assert.equal(palette.fontFamily, "Sans")
  assert.equal(typeof palette.signalColor, "function")
  assert.equal(typeof palette.selectedSignalColor, "function")
  assert.equal(
    palette.signalColor("critical"),
    Color.readableColor("#f38ba8", "#ffffff", "#11111b", 4.5)
  )
  assert.equal(
    palette.signalColor("healthy"),
    Color.readableColor("#a6e3a1", "#ffffff", "#11111b", 4.5)
  )
  assert.equal(
    palette.signalColor("warning"),
    Color.readableColor("#89b4fa", "#ffffff", "#11111b", 4.5)
  )
  assert.equal(
    palette.selectedSignalColor("critical"),
    Color.readableColor(palette.signalColor("critical"), "#ffffff", "#313244", 4.5)
  )
  assert.equal(palette.dim, Color.readableColor("#a6adc8", "#ffffff", "#11111b", 4.5))
  assert.equal(
    palette.selectedDim,
    Color.readableColor(palette.dim, "#ffffff", "#313244", 4.5)
  )
})

test("theme-aware colors remain readable on normal and selected surfaces", () => {
  for (const [name, background, foreground, muted, green, yellow, red] of [
    ["white", "#ffffff", "#000000", "#808080", "#3a3a3a", "#4a4a4a", "#2a2a2a"],
    ["catppuccin-latte", "#eff1f5", "#4c4f69", "#acb0be", "#40a02b", "#df8e1d", "#d20f39"],
    ["flexoki-light", "#fffcf0", "#100f0f", "#b7b5ac", "#879a39", "#d0a215", "#d14d41"],
    ["vantablack", "#000000", "#ffffff", "#7a7a7a", "#b6b6b6", "#cecece", "#a4a4a4"]
  ]) {
    const selectedSurface = Color.blendColor(foreground, background, 0.18)
    const secondary = Color.readableColor(muted, foreground, background, 4.5)
    const selectedSecondary = Color.readableColor(secondary, foreground, selectedSurface, 4.5)
    const semanticColors = { green, yellow, red }

    assert.ok(Color.contrastRatio(secondary, background) >= 4.5, `${name} secondary`)
    assert.ok(Color.contrastRatio(selectedSecondary, selectedSurface) >= 4.5, `${name} selected secondary`)
    for (const [tone, preferred] of Object.entries(semanticColors)) {
      const normal = Color.readableColor(preferred, foreground, background, 4.5)
      const selected = Color.readableColor(preferred, foreground, selectedSurface, 4.5)
      assert.ok(Color.contrastRatio(normal, background) >= 4.5, `${name} ${tone}`)
      assert.ok(Color.contrastRatio(selected, selectedSurface) >= 4.5, `${name} selected ${tone}`)
    }
  }
})

test("signal tones resolve to their theme role", () => {
  assert.equal(Color.signalColor("critical", "fg", "accent", "urgent", "dim"), "urgent")
  assert.equal(Color.signalColor("warning", "fg", "accent", "urgent", "dim"), "accent")
  assert.equal(Color.signalColor("registered", "fg", "accent", "urgent", "dim", "green"), "green")
  assert.equal(Color.signalColor("disabled", "fg", "accent", "urgent", "dim"), "dim")
  assert.equal(Color.signalColor("muted", "fg", "accent", "urgent", "dim"), "dim")
  assert.equal(Color.signalColor("healthy", "fg", "accent", "urgent", "dim"), "fg")
  assert.equal(Color.signalColor("healthy", "fg", "accent", "urgent", "dim", "green"), "green")
  assert.equal(Color.signalColor("warning", "fg", "accent", "urgent", "dim", "green", "yellow"), "yellow")
})

test("theme colors fall back through legacy alias keys", () => {
  assert.equal(Color.themeColorFromTheme('green = "#879A39"', "green", "fg"), "#879A39")
  assert.equal(Color.themeColorFromTheme('yellow = "#D0A215"', "yellow", "fg"), "#D0A215")
  assert.equal(Color.themeColorFromTheme('color2 = "#40A02B"', "green", "fg"), "#40A02B")
  assert.equal(Color.themeColorFromTheme('color3 = "#DF8E1D"', "yellow", "fg"), "#DF8E1D")
  assert.equal(Color.themeColorFromTheme("foreground = \"#100F0F\"", "green", "fg"), "fg")
})
