---
description: Academic color palettes for research figures and visualizations.
paths:
  - "**/*.py"
---

# Academic Color Palettes

All palettes degrade gracefully to B&W and meet contrast accessibility standards.

## Warm-Cool Diverging (Default)

A warm-to-cool diverging palette (11 colors). Works well for heatmaps, sequential pipelines, and any figure that needs a clear directional gradient.

| Index | Hex       | RGB             | Use                          |
|-------|-----------|-----------------|------------------------------|
| 1     | `#E76254` | (231, 98, 84)   | Warm extreme / alert         |
| 2     | `#EF8A47` | (239, 138, 71)  | Warm accent                  |
| 3     | `#F7AA58` | (247, 170, 88)  | Warm mid                     |
| 4     | `#FFD06F` | (255, 208, 111) | Warm-neutral                 |
| 5     | `#FFE6B7` | (255, 230, 183) | Neutral warm / background    |
| 6     | `#AADCE0` | (170, 220, 224) | Neutral cool / background    |
| 7     | `#72BCD5` | (114, 188, 213) | Cool mid                     |
| 8     | `#528FAD` | (82, 143, 173)  | Cool accent                  |
| 9     | `#376795` | (55, 103, 149)  | Cool deep                    |
| 10    | `#1E466E` | (30, 70, 110)   | Cool extreme / text on light |

### Quick-copy array

```
["#E76254","#EF8A47","#F7AA58","#FFD06F","#FFE6B7","#AADCE0","#72BCD5","#528FAD","#376795","#1E466E"]
```

### Suggested pairings

- **Two-class contrast**: `#E76254` vs `#376795`
- **Three-class**: `#E76254`, `#FFD06F`, `#376795`
- **Background fill**: `#FFE6B7` (warm) or `#AADCE0` (cool)
- **Text / stroke on white**: `#1E466E`

## Cool-Warm Arc

A cool-to-warm arc palette (7 colors) that moves from deep blue through lavender and pink to warm orange-brown. Works well for categorical comparisons, multi-class diagrams, and figures that need distinct but harmonious hues.

| Index | Hex       | RGB             | Use                          |
|-------|-----------|-----------------|------------------------------|
| 1     | `#4E659B` | (78, 101, 155)  | Deep blue / anchor           |
| 2     | `#8A8CBF` | (138, 140, 191) | Muted blue-violet            |
| 3     | `#B8A8CF` | (184, 168, 207) | Lavender / soft accent       |
| 4     | `#E7BCC6` | (231, 188, 198) | Pink / neutral mid           |
| 5     | `#FDCF9E` | (253, 207, 158) | Warm peach / highlight       |
| 6     | `#EFA484` | (239, 164, 132) | Warm coral                   |
| 7     | `#B6766C` | (182, 118, 108) | Warm brown / text on light   |

### Quick-copy array

```
["#4E659B","#8A8CBF","#B8A8CF","#E7BCC6","#FDCF9E","#EFA484","#B6766C"]
```

### Suggested pairings

- **Two-class contrast**: `#4E659B` vs `#EFA484`
- **Three-class**: `#4E659B`, `#E7BCC6`, `#B6766C`
- **Background fill**: `#B8A8CF` (cool) or `#FDCF9E` (warm)
- **Text / stroke on white**: `#4E659B`

## Teal-Coral Trio

A minimal three-color palette — teal, coral, and sand. Ideal for simple two- or three-class figures where you want strong contrast with few colors.

| Index | Hex       | RGB             | Use                        |
|-------|-----------|-----------------|----------------------------|
| 1     | `#3D5C6F` | (61, 92, 111)   | Dark teal / primary        |
| 2     | `#E47159` | (228, 113, 89)  | Coral / contrast accent    |
| 3     | `#F9AE78` | (249, 174, 120) | Sand / secondary / fill    |

### Quick-copy array

```
["#3D5C6F","#E47159","#F9AE78"]
```

## Blue-Sand Five

A five-color palette from deep blue through sky blue and pale cyan to warm sand and amber. Good for sequential steps, ranked categories, or cool-to-warm transitions with moderate granularity.

| Index | Hex       | RGB             | Use                        |
|-------|-----------|-----------------|----------------------------|
| 1     | `#203888` | (32, 56, 136)   | Deep blue / anchor         |
| 2     | `#518DDB` | (81, 141, 219)  | Mid blue / primary accent  |
| 3     | `#A7D2E4` | (167, 210, 228) | Light cyan / neutral cool  |
| 4     | `#F5D7A3` | (245, 215, 163) | Sand / neutral warm        |
| 5     | `#E19C66` | (225, 156, 102) | Amber / warm accent        |

### Quick-copy array

```
["#203888","#518DDB","#A7D2E4","#F5D7A3","#E19C66"]
```

## Ocean-Sunset Quad

A four-color palette pairing cool teals with warm yellow and coral. Clean and balanced — good for 2×2 comparisons, quadrant diagrams, or any figure needing four distinct but cohesive colors.

| Index | Hex       | RGB             | Use                        |
|-------|-----------|-----------------|----------------------------|
| 1     | `#46788E` | (70, 120, 142)  | Deep teal / primary        |
| 2     | `#78B7C9` | (120, 183, 201) | Light teal / secondary     |
| 3     | `#F6E093` | (246, 224, 147) | Warm yellow / highlight    |
| 4     | `#E58B7B` | (229, 139, 123) | Coral / contrast accent    |

### Quick-copy array

```
["#46788E","#78B7C9","#F6E093","#E58B7B"]
```

---

Use `strokeStyle` (solid, dashed, dotted) and shape types to add distinction beyond fill.
