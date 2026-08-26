// ColorKit: pure color arithmetic shared by the bar, panel, and tests.
// A palette object (makePalette) bundles every derived color plus the
// tone-resolving helpers so rows never re-thread theme colors.

function colorChannels(value) {
  var text = String(value || "").replace(/^#/, "")
  if (/^[0-9a-fA-F]{3}$/.test(text))
    text = text.split("").map(function(part) { return part + part }).join("")
  if (/^[0-9a-fA-F]{8}$/.test(text)) text = text.slice(2)
  if (!/^[0-9a-fA-F]{6}$/.test(text)) return null
  return [0, 2, 4].map(function(offset) {
    return parseInt(text.slice(offset, offset + 2), 16) / 255
  })
}

function colorHex(channels) {
  if (!channels) return "#000000"
  return "#" + channels.map(function(channel) {
    var value = Math.max(0, Math.min(255, Math.round(channel * 255))).toString(16)
    return value.length < 2 ? "0" + value : value
  }).join("")
}

function blendColor(foreground, background, amount) {
  var front = colorChannels(foreground)
  var back = colorChannels(background)
  if (!front || !back) return String(foreground || background || "#000000")
  var alpha = Math.max(0, Math.min(1, Number(amount)))
  return colorHex(front.map(function(channel, index) {
    return channel * alpha + back[index] * (1 - alpha)
  }))
}

function colorLuminance(value) {
  var channels = colorChannels(value)
  if (!channels) return 0
  var linear = channels.map(function(channel) {
    return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4)
  })
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
}

function contrastRatio(first, second) {
  var lighter = Math.max(colorLuminance(first), colorLuminance(second))
  var darker = Math.min(colorLuminance(first), colorLuminance(second))
  return (lighter + 0.05) / (darker + 0.05)
}

function readableColor(preferred, fallback, background, minimumContrast) {
  var preferredChannels = colorChannels(preferred)
  var fallbackChannels = colorChannels(fallback)
  var minimum = Math.max(1, Number(minimumContrast) || 4.5)
  if (!preferredChannels || !fallbackChannels || !colorChannels(background)) return String(fallback)
  var normalized = colorHex(preferredChannels)
  if (contrastRatio(normalized, background) >= minimum) return normalized
  for (var step = 1; step <= 100; step += 1) {
    var candidate = blendColor(fallback, preferred, step / 100)
    if (contrastRatio(candidate, background) >= minimum + 0.02) return candidate
  }
  return colorHex(fallbackChannels)
}

function signalColor(tone, foreground, accent, urgent, dim, healthy, warning) {
  if (tone === "critical") return urgent
  if (tone === "warning") return warning || accent
  if (tone === "registered") return healthy || foreground
  if (tone === "disabled" || tone === "muted") return dim
  if (tone === "healthy" && healthy) return healthy
  return foreground
}

function themeColorFromTheme(raw, name, fallback) {
  var aliases = name === "green" ? ["green", "color2"]
    : name === "yellow" ? ["yellow", "color3"] : [name]
  var text = String(raw || "")
  for (var i = 0; i < aliases.length; i++) {
    var pattern = new RegExp("^\\s*" + aliases[i] + "\\s*=\\s*[\"']?(#[0-9a-f]{6})", "im")
    var match = text.match(pattern)
    if (match) return match[1]
  }
  return fallback
}

// One palette object replaces per-call color threading across QML files.
// Derived colors are contrast-adjusted once against their target surface.
function makePalette(input) {
  var foreground = String(input.foreground)
  var accent = String(input.accent)
  var urgent = String(input.urgent)
  var healthy = input.healthy ? String(input.healthy) : ""
  var warning = input.warning ? String(input.warning) : ""
  var panelSurface = String(input.panelSurface)
  var selectedSurface = String(input.selectedSurface)
  var dim = readableColor(String(input.muted), foreground, panelSurface, 4.5)
  var selectedDim = readableColor(dim, foreground, selectedSurface, 4.5)

  function preferredTone(tone) {
    return signalColor(tone, foreground, accent, urgent, dim, healthy, warning)
  }

  return {
    fontFamily: String(input.fontFamily || ""),
    foreground: foreground,
    accent: accent,
    urgent: urgent,
    dim: dim,
    selectedDim: selectedDim,
    signalColor: function(tone) {
      return readableColor(preferredTone(tone), foreground, panelSurface, 4.5)
    },
    selectedSignalColor: function(tone) {
      return readableColor(preferredTone(tone), foreground, selectedSurface, 4.5)
    }
  }
}

if (typeof module !== "undefined") {
  module.exports = {
    colorChannels: colorChannels,
    colorHex: colorHex,
    blendColor: blendColor,
    colorLuminance: colorLuminance,
    contrastRatio: contrastRatio,
    readableColor: readableColor,
    signalColor: signalColor,
    themeColorFromTheme: themeColorFromTheme,
    makePalette: makePalette
  }
}
