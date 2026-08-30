// Operational Panel headings, visibility, empty states, and unavailable text.
// Receives only reduced section data and Operational Row view-models.

function metadataUnavailableText(section) {
  return section && !section.available && section.reason === "output_exceeded_limit"
    ? "Unavailable — metadata response exceeded the collection limit" : ""
}

function configurationGuidance(state) {
  return state === "configuration_error"
    ? "Target is reachable, but no supported OpenClaw Gateway responded.\n"
      + "Update gateway.remote.url in OpenClaw settings."
    : ""
}

function create(data, rowSections) {
  var setupVisible = data.candidates.length > 0 || data.state === "setup_required"
    || (data.state === "configuration_error" && data.setup && data.setup.present)
  var configurationErrorVisible = data.state === "configuration_error"
  var operationalVisible = !setupVisible && !configurationErrorVisible
  var fleetUnavailable = data.state === "degraded" && data.fleet && !data.fleet.available
  var agentsUnavailable = data.state === "degraded"
    && data.agentsSection && !data.agentsSection.available
  var automationsUnavailable = data.state === "degraded"
    && data.automationsSection && !data.automationsSection.available

  return {
    historical: data.historical,
    observedAt: data.observedAt,
    generatedAt: data.generatedAt || "",
    setup: {
      visible: setupVisible,
      heading: "GATEWAY SETUP REQUIRED",
      guidance: data.setup && data.setup.present
        ? data.setup.guidance
        : "Connect Tailscale on this device, then refresh to find Gateway candidates.",
      error: data.setup ? data.setup.error : "",
      errorCritical: configurationErrorVisible,
      configurationGuidanceVisible: configurationErrorVisible && !setupVisible,
      configurationGuidance: configurationGuidance(data.state)
    },
    sections: [
      section("candidate", "", setupVisible, "", "", rowSections),
      section(
        "node", "FLEET", operationalVisible,
        fleetUnavailable
          ? metadataUnavailableText(data.fleet) || "Node metadata unavailable" : "",
        data.fleet && data.fleet.available && data.nodes.length === 0 ? "Empty Fleet" : "",
        rowSections
      ),
      section(
        "agent", "AGENTS",
        operationalVisible && (data.agents.length > 0 || agentsUnavailable),
        agentsUnavailable
          ? metadataUnavailableText(data.agentsSection) || "Agent and Task metadata unavailable" : "",
        "", rowSections
      ),
      section(
        "automation", "AUTOMATIONS", operationalVisible,
        automationsUnavailable
          ? data.automationsSection.reason === "more_than_500"
            ? "Unavailable — more than 500 Automations"
            : metadataUnavailableText(data.automationsSection) || "Unavailable"
          : "",
        data.automationsSection && data.automationsSection.available
          && data.automations.length === 0 ? "No Automations" : "",
        rowSections
      )
    ]
  }
}

function section(kind, heading, visible, unavailableText, emptyText, rowSections) {
  var rows = []
  for (var i = 0; i < rowSections.length; i++)
    if (rowSections[i].kind === kind) rows = rowSections[i].rows
  return {
    kind: kind,
    heading: heading,
    visible: visible,
    unavailableText: unavailableText,
    emptyText: emptyText,
    rows: rows
  }
}

function sectionForKind(sections, kind) {
  for (var i = 0; i < sections.length; i++)
    if (sections[i].kind === kind) return sections[i]
  return section(kind, "", false, "", "", [])
}

if (typeof module !== "undefined") {
  module.exports = {
    create: create,
    sectionForKind: sectionForKind
  }
}
