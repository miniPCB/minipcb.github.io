# miniPCB Netlist Schema v1.1

This folder contains netlist JSON files and the authoritative schema:

- Schema file: `netlist.schema.json`
- Schema dialect: JSON Schema Draft 2020-12
- Schema ID: `https://minipcb.com/schemas/netlist.schema.v1.1.json`
- Supported schema version value: `1.1`

## Required Top-Level Fields

Every valid netlist must include:

- `schema_version` (must be `"1.1"`)
- `identity`
- `metadata`
- `components`
- `nets`

## Top-Level Model

Defined top-level sections:

- `schema_version`: fixed schema version marker
- `identity`: strict board identity and netlist type
- `metadata`: project metadata (allows custom metadata keys)
- `components`: component and pin definitions
- `nets`: net definitions and connectivity
- `sheets` (optional): schematic sheet metadata
- `logical_blocks` (optional): functional grouping
- `test_integration` (optional): structured test coverage data
- `ports` (optional): external interface mapping
- `analysis` (optional): structured analysis results

Unknown top-level sections are rejected (`unevaluatedProperties: false`).

## Feature Highlights

### Conditional Validation (PCB Requires Placement)

If `identity.board_type` is `"pcb"`, each component item must include `placement`.

### Electrical Classification

The schema supports electrical semantics through:

- `pin.electrical_type` (input/output/passive/power/analog/digital classes)
- `net.type` (`signal`, `power`, `ground`, `analog`, `digital`, `clock`)
- `net.criticality` (`low`, `medium`, `high`, `safety`)
- `net.voltage_domain` for power-domain grouping

### Strict Identity Management

Identity is required and locked down:

- `identity.board_pn` (required, non-empty)
- `identity.board_rev` (required, non-empty)
- `identity.board_type` (required enum: `pcb`, `schematic`, `combined`)

Reference identifiers are pattern-validated:

- `component.refdes` and connection/test-point `refdes`: `^[A-Z]+[0-9]+$`
- `net.name`: `^[A-Za-z0-9_\\-]+$`

### Controlled Extensibility

The schema is strict by default, but intentionally extensible in controlled areas:

- Top-level is closed (`unevaluatedProperties: false`)
- Most structural objects use `additionalProperties: false`
- `metadata` is open for project/tool-specific keys

### Strong Pattern Enforcement

Pattern/enum constraints enforce predictable data:

- Fixed `schema_version` enum (`"1.1"`)
- Regex for identity-like symbols (`refdes`, `net.name`)
- Enums for board type, electrical types, net classes, criticality, directions, and measurement types

### Structured Analysis

`analysis` provides machine-consumable quality signals:

- `component_count`
- `net_count`
- `floating_nets`
- `unconnected_pins` with strict `{ refdes, pin }` shape

### Structured Test Coverage

`test_integration` supports explicit test readiness:

- `coverage_status` (`complete`, `partial`, `missing`)
- `auto_generated` (boolean)
- `test_plan_reference`
- `test_points[]` with typed measurements and optional required `expected_range { min, max }`

## Detailed Usage Examples

### 1. Minimal Valid Combined Netlist

```json
{
  "schema_version": "1.1",
  "identity": {
    "board_pn": "04B-005",
    "board_rev": "A",
    "board_type": "combined"
  },
  "metadata": {
    "project_name": "miniPCB Project",
    "revision": "A"
  },
  "components": [],
  "nets": []
}
```

## Additional Minimal Usage Snippets

These are intentionally small, schema-valid templates for quick starts.

### A. Minimal `schematic` Netlist

```json
{
  "schema_version": "1.1",
  "identity": {
    "board_pn": "04B-100",
    "board_rev": "A",
    "board_type": "schematic"
  },
  "metadata": {
    "project_name": "Quick Schematic",
    "revision": "A"
  },
  "components": [],
  "nets": []
}
```

### B. Minimal `pcb` Netlist (Placement Required)

```json
{
  "schema_version": "1.1",
  "identity": {
    "board_pn": "04B-101",
    "board_rev": "A",
    "board_type": "pcb"
  },
  "metadata": {
    "project_name": "Quick PCB",
    "revision": "A"
  },
  "components": [
    {
      "refdes": "R1",
      "placement": { "x": 0, "y": 0, "rotation": 0 },
      "pins": [
        { "pin_number": "1", "net": "N1" }
      ]
    }
  ],
  "nets": [
    {
      "name": "N1",
      "connections": [
        { "refdes": "R1", "pin": "1" }
      ]
    }
  ]
}
```

### C. Minimal `combined` Netlist

```json
{
  "schema_version": "1.1",
  "identity": {
    "board_pn": "04B-102",
    "board_rev": "A",
    "board_type": "combined"
  },
  "metadata": {
    "project_name": "Quick Combined",
    "revision": "A"
  },
  "components": [],
  "nets": []
}
```

### D. Minimal Test Coverage Block

Use this block inside an otherwise valid netlist.

```json
{
  "test_integration": {
    "test_points": [
      {
        "refdes": "TP1",
        "net": "N1",
        "measurement_type": "voltage"
      }
    ]
  }
}
```

### E. Minimal Analysis Block

Use this block inside an otherwise valid netlist.

```json
{
  "analysis": {}
}
```

### 2. Schematic Netlist with Logical Grouping

```json
{
  "schema_version": "1.1",
  "identity": {
    "board_pn": "04B-005",
    "board_rev": "B",
    "board_type": "schematic"
  },
  "metadata": {
    "project_name": "Amplifier Front End",
    "revision": "B",
    "source_tool": "SchematicEditor"
  },
  "sheets": [
    { "sheet_number": 1, "title": "Input Stage" },
    { "sheet_number": 2, "title": "Output Stage" }
  ],
  "logical_blocks": [
    { "name": "Bias Network", "members": ["R1", "R2", "Q1"] }
  ],
  "components": [
    {
      "refdes": "Q1",
      "value": "NPN",
      "pins": [
        { "pin_number": "1", "pin_name": "C", "net": "VCC", "electrical_type": "analog" },
        { "pin_number": "2", "pin_name": "B", "net": "BIAS", "electrical_type": "input" },
        { "pin_number": "3", "pin_name": "E", "net": "OUT_PRE", "electrical_type": "output" }
      ]
    }
  ],
  "nets": [
    {
      "name": "BIAS",
      "type": "analog",
      "criticality": "medium",
      "connections": [
        { "refdes": "Q1", "pin": "2" }
      ]
    }
  ]
}
```

### 3. PCB Netlist (Placement Required)

```json
{
  "schema_version": "1.1",
  "identity": {
    "board_pn": "04B-005",
    "board_rev": "C",
    "board_type": "pcb"
  },
  "metadata": {
    "project_name": "Controller Board",
    "revision": "C",
    "generated_on": "2026-02-14T17:30:00Z",
    "units": "mm"
  },
  "components": [
    {
      "refdes": "U1",
      "value": "MCU",
      "footprint": "QFN-32",
      "placement": { "x": 25.4, "y": 18.2, "rotation": 90, "side": "Top" },
      "pins": [
        { "pin_number": "1", "pin_name": "VDD", "net": "3V3", "electrical_type": "power_in" },
        { "pin_number": "2", "pin_name": "GND", "net": "GND", "electrical_type": "power_in" },
        { "pin_number": "5", "pin_name": "GPIO0", "net": "BTN_IN", "electrical_type": "input" }
      ]
    }
  ],
  "nets": [
    {
      "name": "3V3",
      "type": "power",
      "voltage_domain": "3V3_MAIN",
      "criticality": "high",
      "connections": [
        { "refdes": "U1", "pin": "1" }
      ]
    },
    {
      "name": "BTN_IN",
      "type": "digital",
      "criticality": "low",
      "connections": [
        { "refdes": "U1", "pin": "5" }
      ]
    }
  ],
  "ports": [
    { "name": "J1_PIN1", "direction": "input", "net": "BTN_IN" },
    { "name": "J1_PIN2", "direction": "bidirectional", "net": "GND" }
  ]
}
```

### 4. Test and Analysis Enriched Netlist

```json
{
  "schema_version": "1.1",
  "identity": {
    "board_pn": "04B-005",
    "board_rev": "D",
    "board_type": "combined"
  },
  "metadata": {
    "project_name": "5V Regulator Module",
    "revision": "D"
  },
  "components": [],
  "nets": [],
  "test_integration": {
    "coverage_status": "partial",
    "auto_generated": true,
    "test_plan_reference": "test_plan_04B-005.md",
    "test_points": [
      {
        "refdes": "TP1",
        "net": "VOUT",
        "measurement_type": "voltage",
        "expected_range": { "min": 4.8, "max": 5.2 }
      },
      {
        "refdes": "TP2",
        "net": "GND",
        "measurement_type": "continuity"
      }
    ]
  },
  "analysis": {
    "component_count": 24,
    "net_count": 31,
    "floating_nets": ["N$23"],
    "unconnected_pins": [
      { "refdes": "U3", "pin": "17" }
    ]
  }
}
```

## Authoring Notes

- Keep `components[*].pins[*].net` aligned with `nets[*].name`.
- Keep `nets[*].connections[*]` aligned with real `(refdes, pin_number)` pairs.
- Use `identity` as immutable board identity and `metadata.revision` as dataset release tracking.
- For PCB exports, always include `placement` data even before final placement freeze.

## Suitable Tooling and Workflows

This schema is now suitable for:

- Automated CI validation
- Git pre-commit enforcement
- EPSA automation
- TestBASE auto-generation
- AI graph reasoning
- Risk analysis tooling
