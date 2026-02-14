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

## Notes

- Component and net objects disallow unknown properties (`additionalProperties: false` in schema).
- `metadata` allows additional custom properties.
- Some project files may include extra top-level sections (for example `test_integration` or `sheets`); these are project-specific and not defined in `netlist.schema.json`.
