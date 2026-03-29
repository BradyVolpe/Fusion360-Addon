# Fusion 360 Cabinet Optimizer — Mac Edition

A macOS-compatible toolset for optimizing cabinet sheet goods cuts from Fusion 360 designs. Includes a Fusion 360 add-in to export cabinet part dimensions and a standalone browser-based cut list optimizer.

Originally based on the [Old Guy Woodworks](https://oldguywoodworks.com) Cabinet Optimizer Distribution 2.0 (Windows). This repo contains a Mac-native port of the Fusion 360 add-in and a completely new single-file cut list optimizer that runs in any browser.

---

## Quick Start

### 1. Install the Fusion 360 Add-in

```bash
cd Fusion360-Addon
chmod +x Install-Fusion360-Addon.sh
./Install-Fusion360-Addon.sh
```

This copies the add-in files to:
```
~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/OGW_ExportCabinetParams/
```

Then in Fusion 360:
1. Go to **Utilities > Add-Ins > Scripts and Add-Ins**
2. Find **OGW_ExportCabinetParams** in the Add-Ins tab
3. Click **Run** (optionally check "Run on Startup")

### 2. Export Parts from Fusion 360

1. Open your cabinet design in Fusion 360
2. The add-in command appears under the **SOLID** workspace, **Create** panel: **OGW: Export Cabinet Parameters**
3. Choose an export folder and filename
4. The add-in scans all top-level occurrences (cabinets) and exports a CSV

### 3. Optimize Your Cut List

1. Open **CutListOptimizer.html** in any browser (just double-click it)
2. Drag & drop the exported CSV onto the upload area
3. Adjust settings if needed (sheet size, kerf, rotation)
4. Click **Optimize Cut List**
5. View and print your optimized sheet layouts

---

## What's in This Repo

| File | Description |
|------|-------------|
| `CutListOptimizer.html` | Standalone cut list optimizer — runs entirely in the browser, no server needed |
| `BodyPartsOrientation.csv` | Master orientation rules mapping 100+ cabinet part names to local X/Y/Z axes |
| `Fusion360-Addon/OGW_ExportCabinetParams.py` | Fusion 360 add-in that exports cabinet dimensions to CSV |
| `Fusion360-Addon/OGW_ExportCabinetParams.manifest` | Add-in metadata (declares Windows + Mac support) |
| `Fusion360-Addon/Install-Fusion360-Addon.sh` | Mac installer script for the add-in |
| `Fusion360-Addon/BodyPartsOrientation.csv` | Starter orientation rules (installed alongside the add-in) |
| `Fusion360-Addon/README-Fusion360-Addon.txt` | Additional add-in documentation |

---

## How It Works

### Workflow

```
Fusion 360 Cabinet Design
        |
        v
OGW Export Add-in (scans design, extracts dimensions)
        |
        v
CSV File: Part_ID, Cabinet_ID, Width, Height, Depth, Units, Material
        |
        v
CutListOptimizer.html (browser-based optimizer)
        |
        v
Optimized cut layouts with visual sheet maps (printable)
```

### CSV Format

The add-in exports a CSV with these columns:

| Column | Description |
|--------|-------------|
| `Part_ID` | Part/body name (e.g., "Left Side", "Back Panel") |
| `Cabinet_ID` | Parent cabinet name (e.g., "Base_30", "Wall_36") |
| `Width` | Panel face dimension 1 |
| `Height` | Panel face dimension 2 |
| `Depth` | Material thickness |
| `Units` | `in` or `mm` |
| `Material` | Material name (can be empty — optimizer auto-labels by thickness) |

### Cut List Optimizer Features

- **Guillotine bin packing** — all cuts go edge-to-edge, matching how real table saws and panel saws work
- **Automatic grouping** — parts are grouped by material and thickness (e.g., 3/4" plywood and 1/4" plywood get separate sheet layouts)
- **Configurable settings:**
  - Sheet size (default: 48" x 96" / 4' x 8')
  - Saw kerf (default: 0.125" / 1/8")
  - Part rotation (on/off for grain direction control)
- **Color-coded SVG layouts** — each cabinet gets a distinct color, parts are labeled with IDs and dimensions
- **Per-sheet cut lists** — expandable table under each sheet showing every part
- **Print-friendly** — click Print to get clean layouts without UI chrome
- **Zero dependencies** — no server, no installs, just one HTML file

### Fusion 360 Add-in Features

- Scans top-level occurrences as cabinets
- Three-tier dimension lookup:
  1. Named model parameters on components
  2. Design user parameters with prefix matching (e.g., `Base_30_Width`)
  3. Fallback to oriented bounding box
- Body orientation rules via `BodyPartsOrientation.csv` for accurate dimension mapping
- Supports partial name matching (e.g., "nailer(1)" matches "nailer")
- Exports unmatched parts to a separate CSV for rule refinement
- Preferences saved to `~/OGW_ExportCabinetParams.json`

---

## Customizing Orientation Rules

The `BodyPartsOrientation.csv` file maps part names to X/Y/Z axis assignments:

```csv
Body Name,Thickness,Length,Width
Back,y,z,x
Bottom,z,x,y
Door Face,y,z,x
Shelf,z,x,y
```

Each axis value (`x`, `y`, or `z`) tells the add-in which local axis corresponds to that dimension. Edit this file to match your shop's naming conventions. The master copy (122 rules) is in the repo root; a starter copy (9 rules) is installed alongside the add-in.

---

## Requirements

- **macOS** (tested on macOS Sonoma+)
- **Fusion 360** (for the export add-in)
- **Any modern browser** — Safari, Chrome, Firefox, etc. (for the optimizer)
- No Python, Node.js, or other runtime needed for the optimizer

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Add-in doesn't appear in Fusion 360 | Make sure `.manifest` file was copied alongside `.py`. Restart Fusion 360. |
| Installer says "AddIns folder not found" | Run Fusion 360 at least once before installing to create the folder. |
| CSV has empty Material column | The optimizer auto-labels parts by thickness (e.g., "Plywood 3/4""). |
| Parts show as "exceeds sheet size" | Check dimensions — part may be larger than your configured sheet. |
| Orientation rules not loading | Verify `BodyPartsOrientation.csv` is next to the `.py` file in the AddIns folder. |

---

## Credits

- Original Windows distribution: [Old Guy Woodworks](https://oldguywoodworks.com)
- Mac port and cut list optimizer: Built with Claude Code
