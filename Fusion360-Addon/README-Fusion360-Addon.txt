# Fusion 360 Add-in Installation Guide

## Cabinet Parameters Export Add-in for Fusion 360

This add-in allows you to export cabinet dimensions directly from Fusion 360 to CSV format for use with the Cabinet Shop Material Optimizer.

### Installation Steps:

#### Method 1: Automatic Installation (Recommended)

1. **Run the Fusion 360 Add-in Installer**:
   - Double-click `Install-Fusion360-Addon.bat` in this folder
   - The installer will automatically place the add-in in the correct Fusion 360 directory

#### Method 2: Manual Installation

1. **Locate Fusion 360 Add-ins Folder**:
   ```
   C:\Users\[YourUsername]\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns\
   ```

2. **Create Add-in Folder**:
   - Create folder: `OGW_ExportCabinetParams`

3. **Copy Files**:
   - Copy `OGW_ExportCabinetParams.py` to the new folder
   - Copy any additional files (manifest, etc.) if present

### Usage Instructions:

1. **Enable the Add-in in Fusion 360**:
   - Open Fusion 360
   - Go to **Tools > Add-Ins**
   - Find "OGW Export Cabinet Params" in the list
   - Click **Run** (or set to run on startup)

2. **Export Cabinet Parameters**:
   - Open your cabinet design in Fusion 360
   - Run the add-in from the Tools menu
   - Select export location and filename
   - The CSV will be saved and ready for import into Cabinet Optimizer

3. **Import into Cabinet Optimizer**:
   - Launch Cabinet Optimizer
   - Click "Import CSV" 
   - Select the exported CSV file
   - Generate optimized cut lists!

### Workflow Overview:

```
Fusion 360 CAD Design
        ↓
OGW Export Add-in (creates CSV)
        ↓
Cabinet Optimizer (imports CSV)
        ↓
Optimized Cut Lists & Reports
```

### Troubleshooting:

- **Add-in doesn't appear**: Check that files are in correct Fusion 360 AddIns directory
- **Export fails**: Ensure your model has the required parameters and components
- **CSV import issues**: Verify the CSV format matches expected structure

### Support:

For technical support:
- Email: support@oldguywoodworks.com
- Website: oldguywoodworks.com
- YouTube: Old Guy Woodworks channel

---

© 2025 Old Guy Woodworks - Professional CAD Tools for Woodworkers