#!/bin/bash
# Mac installer for OGW_ExportCabinetParams Fusion 360 Add-in

ADDIN_NAME="OGW_ExportCabinetParams"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
ADDINS_DIR="$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns"

echo ""
echo "  Installing $ADDIN_NAME for Fusion 360 (macOS)"
echo "  ================================================"
echo ""

if [ ! -d "$ADDINS_DIR" ]; then
    echo "  Could not find Fusion 360 AddIns folder at:"
    echo "    $ADDINS_DIR"
    echo ""
    echo "  Make sure Fusion 360 is installed for this user."
    echo "  (Run Fusion 360 at least once before installing add-ins.)"
    echo ""
    read -p "  Press Enter to exit..."
    exit 1
fi

DST_DIR="$ADDINS_DIR/$ADDIN_NAME"
mkdir -p "$DST_DIR"

cp -f "$SRC_DIR/OGW_ExportCabinetParams.py" "$DST_DIR/"
[ -f "$SRC_DIR/OGW_ExportCabinetParams.manifest" ] && cp -f "$SRC_DIR/OGW_ExportCabinetParams.manifest" "$DST_DIR/"
[ -f "$SRC_DIR/BodyPartsOrientation.csv" ] && cp -f "$SRC_DIR/BodyPartsOrientation.csv" "$DST_DIR/"
[ -f "$SRC_DIR/README-Fusion360-Addon.txt" ] && cp -f "$SRC_DIR/README-Fusion360-Addon.txt" "$DST_DIR/"

# Check manifest is present
if [ ! -f "$DST_DIR/OGW_ExportCabinetParams.manifest" ]; then
    echo "  WARNING: Missing OGW_ExportCabinetParams.manifest in $DST_DIR"
    echo "  Please copy the .manifest file alongside OGW_ExportCabinetParams.py."
    echo ""
fi

echo "  Installed to:"
echo "    $DST_DIR"
echo ""
echo "  Next steps:"
echo "    1) Start Fusion 360 (or restart if open)"
echo "    2) Utilities > Add-Ins > Add-Ins tab > Scripts and Add-Ins"
echo "    3) Select $ADDIN_NAME and click Run (optionally set Run at Startup)"
echo ""
read -p "  Press Enter to close..."
