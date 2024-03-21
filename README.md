[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Introduction
This is a plugin for [InvenTree](https://github.com/inventree/InvenTree/).
Installing this plugin enables the automatic generation if Internal Part Numbers (IPN) for parts.

## Installation
To automatically install the plugin when running `invoke install`:
Add `inventree-ipn-generator` to your plugins.txt file.

Or, install the plugin manually:

```
pip install inventree-ipn-generator
```

For the plugin to be listed as available, you need to enable "Event Integration" in your plugin settings.
This setting is located with the Plugin Settings on the settings page.

## Settings

- Active - Enables toggling of plugin without having to disable it
- On Create - If on, the plugin will assign IPNs to newly created parts
- On Change - If on, the plugin will assign IPNs to parts after a change has been made.
Enabling this setting will remove the ability to have parts without IPNs.

## Pattern
Part Number patterns follow three basic groups. Literals, Numerics, and characters.
When incrementing a part number, the rightmost group that is mutable will be incremented.
All groups can be combined in any order.

A pattern cannot consist of _only_ Literals.

For any pattern, only the rightmost non-literal group will be incremented.
When this group rolls over its max, the next non-literal group to the left will be incremented.
Example: Given the groups (named for demo): L1C1N1C2L2
Incrementing follows this order: C2, N1, C1.

> **_NOTE:_** When C1 in the above example rolls over, the plugin will loop back to the first IPN.
> This will cause duplicate IPNs if your InvenTree allows duplicate IPNs.
> If your InvenTree does not allow duplicate IPNs, this will cause an error at the moment!
> This will be addressed in an upcoming update.

### Literals (Immutable)
Anything encased in `()` will be rendered as-is. no change will be made to anything within.

Example: `(A6C)` will _always_ render as "A6C", regardless of other groups

### Numeric
Numbers that should change over time should be encased in `{}`
- `{5}` respresents a number with max 5 digits
- `{25+}` represents a number 25-99

Example: `{5+}{3}` will result in this range: 5000-9999

### Characters
Characters that change should be encased in `[]`
- `[abc]` represents looping through the letters `a`, `b`, `c` in order.
- `[a-f]` represents looping through the letters from `a` to `f` alphabetaically

These two directives can be combined.
- `[aQc-f]` represents:
- - `a`, `Q`, `c-f`

### Examples
1. `(AB){3}[ab]` -> AB001a, AB001b, AB002a, AB021b, AB032a, etc
2. `{2}[Aq](BD)` -> 01ABD, 01qBD, 02ABD, 02qBD, etc
3. `{1}[a-d]{8+}` -> 1a8, 1a9, 1b8, 1b9, 1c8, 1c9, 1d8, 1d9, 2a8, etc
