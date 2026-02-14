# miniPCB Netlist JSON Schema

This folder contains netlist JSON files and the schema that defines the base format:

- Schema file: `netlist.schema.json`
- Schema dialect: JSON Schema Draft 2020-12

## Required Top-Level Fields

Every valid netlist must include:

- `schema_version` (string, format like `1.0`)
- `metadata` (object)
- `components` (array)
- `nets` (array)

## Top-Level Structure

Supported top-level properties:

- `schema_version`: schema version string (`^\d+\.\d+$`)
- `metadata`: project/build metadata
- `components`: list of components and their pins
- `nets`: list of electrical nets and their connections
- `sheets` (optional): schematic sheet metadata
- `logical_blocks` (optional): grouped functional blocks
- `test_integration` (optional): test-point and test-plan data
- `ports` (optional): external I/O port definitions
- `hierarchy` (optional): hierarchical design data
- `analysis` (optional): analysis/simulation results or metadata

## `metadata`

Required fields:

- `project_name` (string)
- `revision` (string)

Optional fields:

- `source_tool` (string)
- `generated_on` (date-time string)
- `units` (string)

## `components`

Each component requires:

- `refdes` (string), e.g. `R1`, `U2`
- `pins` (array)

Optional component fields:

- `value`, `footprint`, `description`, `manufacturer_part_number`
- `attributes` (object)
- `placement` object with optional `x`, `y`, `rotation` numbers

### Pin Object

Each pin requires:

- `pin_number` (string)
- `net` (string)

Optional pin fields:

- `pin_name` (string)
- `electrical_type` (enum):
  - `input`
  - `output`
  - `bidirectional`
  - `passive`
  - `power_in`
  - `power_out`
  - `analog`
  - `digital`

## `nets`

Each net requires:

- `name` (string)
- `connections` (array)

Optional net field:

- `type` (string)

Each connection requires:

- `refdes` (string)
- `pin` (string)

## `ports` (Optional)

Each port requires:

- `name` (string)
- `net` (string)

Optional:

- `direction` (`input`, `output`, `bidirectional`)

## Minimal Valid Example

```json
{
  "schema_version": "1.0",
  "metadata": {
    "project_name": "miniPCB Project",
    "revision": "A"
  },
  "components": [],
  "nets": []
}
```

## Detailed Usage Examples

### 1. Basic Electrical Netlist

Use this as a starting point for simple circuits and validation pipelines.

```json
{
  "schema_version": "1.0",
  "metadata": {
    "project_name": "Power Filter",
    "revision": "B",
    "source_tool": "miniPCB Editor",
    "units": "mm"
  },
  "components": [
    {
      "refdes": "C1",
      "value": "10uF",
      "footprint": "0603",
      "pins": [
        { "pin_number": "1", "net": "VIN", "electrical_type": "passive" },
        { "pin_number": "2", "net": "GND", "electrical_type": "passive" }
      ]
    },
    {
      "refdes": "R1",
      "value": "1k",
      "footprint": "0603",
      "pins": [
        { "pin_number": "1", "net": "VIN", "electrical_type": "passive" },
        { "pin_number": "2", "net": "SENSE", "electrical_type": "passive" }
      ]
    }
  ],
  "nets": [
    {
      "name": "VIN",
      "type": "power",
      "connections": [
        { "refdes": "C1", "pin": "1" },
        { "refdes": "R1", "pin": "1" }
      ]
    },
    {
      "name": "GND",
      "type": "power",
      "connections": [
        { "refdes": "C1", "pin": "2" }
      ]
    },
    {
      "name": "SENSE",
      "connections": [
        { "refdes": "R1", "pin": "2" }
      ]
    }
  ]
}
```

### 2. Schematic-Oriented Netlist (`sheets` + `logical_blocks`)

Use `sheets` to track drawing organization and `logical_blocks` for functional grouping.

```json
{
  "schema_version": "1.0",
  "metadata": {
    "project_name": "Amplifier Front End",
    "revision": "A"
  },
  "sheets": [
    { "sheet_number": 1, "title": "Input Stage" },
    { "sheet_number": 2, "title": "Output Stage" }
  ],
  "logical_blocks": [
    { "name": "Bias Network", "members": ["R1", "R2", "Q1"] },
    { "name": "Output Buffer", "members": ["Q2", "R5", "R6"] }
  ],
  "components": [
    {
      "refdes": "Q1",
      "value": "NPN",
      "pins": [
        { "pin_number": "1", "pin_name": "C", "net": "VCC" },
        { "pin_number": "2", "pin_name": "B", "net": "BIAS" },
        { "pin_number": "3", "pin_name": "E", "net": "OUT_PRE" }
      ]
    }
  ],
  "nets": [
    {
      "name": "BIAS",
      "connections": [
        { "refdes": "Q1", "pin": "2" }
      ]
    }
  ]
}
```

### 3. PCB-Oriented Netlist (Placement + Ports)

Use this when netlist data is consumed by layout, assembly, or I/O export tools.

```json
{
  "schema_version": "1.0",
  "metadata": {
    "project_name": "Controller Board",
    "revision": "C",
    "generated_on": "2026-02-14T17:30:00Z"
  },
  "components": [
    {
      "refdes": "U1",
      "value": "MCU",
      "footprint": "QFN-32",
      "placement": { "x": 25.4, "y": 18.2, "rotation": 90 },
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
      "connections": [
        { "refdes": "U1", "pin": "1" }
      ]
    },
    {
      "name": "BTN_IN",
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

### 4. Manufacturing Test Integration (`test_integration`)

Use `test_integration` to define measurable conditions tied to nets and reference test plans.

```json
{
  "schema_version": "1.0",
  "metadata": {
    "project_name": "5V Regulator Module",
    "revision": "D"
  },
  "components": [],
  "nets": [],
  "test_integration": {
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
      },
      {
        "refdes": "TP3",
        "net": "CLK",
        "measurement_type": "frequency",
        "expected_range": { "min": 999000.0, "max": 1001000.0 }
      }
    ],
    "test_plan_reference": "test_plan_04B-005.md"
  }
}
```

## Authoring Tips

- Keep `components[*].pins[*].net` names synchronized with `nets[*].name`.
- Ensure each `nets[*].connections[*]` entry matches a real component `refdes` and `pin_number`.
- Use `metadata.revision` to track released dataset versions (A, B, C...) and avoid overwriting historical outputs.
- Prefer explicit `electrical_type` values for downstream ERC/DFT tooling.
- Use `generated_on` when files are produced by automation to improve traceability.

## Notes

- Component and net objects disallow unknown properties (`additionalProperties: false` in schema).
- `metadata` allows additional custom properties.
- Top-level unknown properties are disallowed (`additionalProperties: false`), so all top-level sections must be defined in the schema.
