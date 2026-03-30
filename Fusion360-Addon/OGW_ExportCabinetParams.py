# ===== Old Guy Woodworks — Fusion 360 Cabinet Parameter Exporter =====
# Version: v0.1
# Author: ChatGPT for Old Guy Woodworks
#
# WHAT IT DOES
# - Scans a design for cabinets (top‑level occurrences) and exports per‑cabinet dimensions/parameters.
# - Tries (in order):
#     1) Named parameters on the component (ModelParameters whose names match common keys)
#     2) Design User Parameters whose names are prefixed with the component name or occurrence name
#     3) Fallback to the cabinet occurrence oriented bounding box (width/height/depth)
# - Writes a single CSV summary and a JSON file with detailed values for all cabinets.
#
# HOW TO INSTALL
# 1) Save this file as: OGW_ExportCabinetParams.py into your Fusion 360 Add‑ins folder:
#    Windows: %APPDATA%/Autodesk/Autodesk Fusion 360/API/AddIns/OGW_ExportCabinetParams
#    macOS:   ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/OGW_ExportCabinetParams
# 2) Restart Fusion 360 → Utilities → Add‑ins → Run → (optional) Run at Startup.
# 3) Command appears under the SOLID workspace, Create panel (or Add‑ins panel):
#       • OGW: Export Cabinet Parameters
#
# USAGE NOTES
# - Treats each *top‑level* occurrence as a cabinet unless you choose "Selected Only" in the dialog.
# - Recognizes (case‑insensitive) parameter names: Width, Height, Depth, Thickness, ToeKick, ToeKickHeight, FaceFrameWidth, DoorGap, DrawerGap, Overhang, BackThickness, ShelfThickness.
# - Prefix pattern for Design User Parameters: <OccurrenceName>_<ParamName> (e.g., "Base_30_Width").
# - Adds an attribute namespace 'OGW.Cab' to store a CabinetId if you want explicit IDs; otherwise uses occurrence/component name.
# - Exports to a chosen folder (default: Desktop) with custom filename as: <filename>.csv + <filename>.json

import adsk.core, adsk.fusion, adsk.cam, traceback, os, csv, json, math

APP = None
UI = None
HANDLERS = []

CMD_ID = 'OGW_ExportCabinetParams'
CMD_NAME = 'OGW: Export Cabinet Parameters'
CMD_TOOLTIP = 'Export dimensions/parameters for each cabinet (per top‑level occurrence) to CSV/JSON.'

ATTR_NS = 'OGW.Cab'
ATTR_ID = 'CabinetId'

# default prefs
DEFAULT_PREFS = {
    'units': 'in',
    'exportFolder': '',
    'exportFilename': 'CabinetParams',
    'usePartialMatch': True,
    'includeDebug': False,
    'useRules': False,
    'lockThicknessMin': True,
    'orientationRulesPath': ''
}

PREFS = DEFAULT_PREFS.copy()

PREFS_FILE = os.path.join(os.path.expanduser('~'), 'OGW_ExportCabinetParams.json')

# Orientation rules cache (loaded from CSV)
ORIENTATION_RULES = []

def _match_orientation_rule(body_name: str):
    """Match rule by exact name; if not found, try partial fallback like 'nailer(1)' -> 'nailer'."""
    try:
        if not ORIENTATION_RULES:
            return None
        n_ci = (body_name or '').strip().lower()
        # Exact first
        for r in ORIENTATION_RULES:
            if r.get('name') == n_ci:
                return r
        # Strip trailing parenthetical numbers and trailing digits/spaces
        import re
        stripped = re.sub(r"\(\d+\)$", "", n_ci).strip()
        stripped = re.sub(r"\s*\d+$", "", stripped).strip()
        if stripped and stripped != n_ci:
            for r in ORIENTATION_RULES:
                if r.get('name') == stripped:
                    return r
        # Optional partial contains-based fallback only if enabled
        if PREFS.get('usePartialMatch', True):
            for r in ORIENTATION_RULES:
                rn = r.get('name', '')
                if len(rn) >= 4 and rn in stripped:
                    return r
        return None
    except:
        return None

# Recognized parameter name map (lowercase) → export key
PARAM_KEYS = {
    'width': 'Width',
    'height': 'Height',
    'depth': 'Depth',
    'thickness': 'Thickness',
    'materialthickness': 'Thickness',
    'shelfthickness': 'ShelfThickness',
    'backthickness': 'BackThickness',
    'toekick': 'ToeKick',
    'toekickheight': 'ToeKickHeight',
    'faceframewidth': 'FaceFrameWidth',
    'doorgap': 'DoorGap',
    'drawergap': 'DrawerGap',
    'overhang': 'Overhang'
}


# -----------------------
# Utilities
# -----------------------

def _save_prefs():
    try:
        with open(PREFS_FILE, 'w') as f:
            json.dump(PREFS, f, indent=2)
    except:
        pass

def _load_prefs():
    try:
        if os.path.exists(PREFS_FILE):
            with open(PREFS_FILE, 'r') as f:
                PREFS.update(json.load(f))
    except:
        pass
    
    # Ensure default export folder exists and set it in prefs if not specified
    if not PREFS['exportFolder']:
        default_folder = os.path.join(os.path.expanduser('~'), 'Desktop')
        _ensure_folder(default_folder)
        PREFS['exportFolder'] = default_folder

    # Prefer project-root BodyPartsOrientation.csv if present
    try:
        here = os.path.dirname(__file__)
    except:
        here = os.getcwd()
    default_rules_csv = os.path.join(here, 'BodyPartsOrientation.csv')
    if os.name == 'nt':
        fallback_rules_csv = os.path.join('C:\\', 'Fusion Calculator', 'BodyPartsOrientation.csv')
    else:
        fallback_rules_csv = os.path.join(os.path.expanduser('~'), 'Library',
                                          'Application Support', 'OGW', 'BodyPartsOrientation.csv')
    # Prefer the CSV located alongside the add-in first, then fall back to the shared path
    if os.path.exists(default_rules_csv):
        PREFS['orientationRulesPath'] = default_rules_csv
    elif os.path.exists(fallback_rules_csv):
        PREFS['orientationRulesPath'] = fallback_rules_csv

def _axis_value_from_tuple(xyz: tuple, axis: str) -> float:
    a = (axis or '').lower()
    if a == 'x':
        return xyz[0]
    if a == 'y':
        return xyz[1]
    if a == 'z':
        return xyz[2]
    return 0.0

def _load_orientation_rules(path: str):
    global ORIENTATION_RULES
    ORIENTATION_RULES = []
    try:
        if not path or not os.path.exists(path):
            return
        # Handle UTF-8 BOM and normalize headers robustly
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            rdr = csv.DictReader(f)
            fns = rdr.fieldnames or []

            def _norm_key(k: str) -> str:
                return (k or '').strip().lstrip('\ufeff').lower().replace('_', ' ')

            def _find_key(candidates):
                for fn in fns:
                    n = _norm_key(fn)
                    if n in candidates:
                        return fn
                return None

            body_key = _find_key({'body name', 'body', 'part id', 'part name'}) or 'Body Name'
            w_key = _find_key({'width', 'w'}) or 'Width'
            l_key = _find_key({'length', 'l'}) or 'Length'
            t_key = _find_key({'thickness', 't'}) or 'Thickness'

            for idx, row in enumerate(rdr):
                try:
                    raw_name = (row.get(body_key, '') or '').strip()
                    name_ci = raw_name.lower()
                    w = (row.get(w_key, '') or '').strip().lower()
                    l = (row.get(l_key, '') or '').strip().lower()
                    t = (row.get(t_key, '') or '').strip().lower()
                    # Strict: only accept x|y|z for each axis
                    if name_ci and w in ('x','y','z') and l in ('x','y','z') and t in ('x','y','z'):
                        ORIENTATION_RULES.append({'idx': idx, 'name': name_ci, 'raw': raw_name, 'w': w, 'l': l, 't': t})
                except:
                    continue
    except:
        ORIENTATION_RULES = []

def _design():
    app = adsk.core.Application.get()
    return adsk.fusion.Design.cast(app.activeProduct)


# Units helpers

def _um():
    d = _design()
    return d.unitsManager if d else None


def _to_display(val_mm: float, units: str) -> float:
    if units == 'mm':
        return round(val_mm, 3)
    # inches
    return round(val_mm / 25.4, 4)


def _param_val_to_mm(param: adsk.fusion.Parameter) -> float:
    um = _um()
    try:
        return um.convert(param.value, um.internalUnits, 'mm')
    except:
        # fallback using param.expression
        try:
            return um.convert(um.evaluateExpression(param.expression, um.defaultLengthUnits), um.defaultLengthUnits, 'mm')
        except:
            return float('nan')


# Geometry helpers

def _occ_extents_mm(occ: adsk.fusion.Occurrence):
    # Use occurrence bounding box in world space
    bb = occ.boundingBox
    um = _um()
    dx = um.convert(bb.maxPoint.x - bb.minPoint.x, um.internalUnits, 'mm')
    dy = um.convert(bb.maxPoint.y - bb.minPoint.y, um.internalUnits, 'mm')
    dz = um.convert(bb.maxPoint.z - bb.minPoint.z, um.internalUnits, 'mm')
    # Try to infer orientation: assume XY is plan (Width x Depth) and Z is Height (standing cabinet)
    # We'll report the three extents sorted as W, H, D based on common cabinet proportions.
    dims = sorted([abs(dx), abs(dy), abs(dz)], reverse=True)  # largest → smallest
    # Heuristic: Height ~ largest, Width ~ middle, Depth ~ smallest (typical base/uppers). Tweakable later.
    H = dims[0]
    W = dims[1]
    D = dims[2]
    return W, H, D


# Simple visibility checks
def _is_body_visible(body: adsk.fusion.BRepBody) -> bool:
    """Simple, reliable visibility check"""
    try:
        return body.isLightBulbOn
    except:
        return False


def _is_occurrence_chain_visible(occ: adsk.fusion.Occurrence) -> bool:
    """Check visibility up the occurrence chain (parent lightbulbs)."""
    try:
        cur = occ
        while cur:
            try:
                # Prefer lightbulb flag; fall back to isVisible if needed
                if hasattr(cur, 'isLightBulbOn'):
                    if not cur.isLightBulbOn:
                        return False
                elif hasattr(cur, 'isVisible'):
                    if not cur.isVisible:
                        return False
            except:
                return False
            # Climb to parent occurrence when available
            try:
                cur = cur.parentOccurrence
            except:
                try:
                    cur = cur.assemblyContext
                except:
                    cur = None
        return True
    except:
        return False

def is_effectively_visible(body: adsk.fusion.BRepBody, occ: adsk.fusion.Occurrence = None) -> bool:
    """
    Returns True only if body is effectively visible in the design.
    Considers body-level visibility and all parent occurrence lightbulbs.
    """
    try:
        # Body-level visibility must be ON
        try:
            if hasattr(body, 'isVisible'):
                if not body.isVisible:
                    return False
            elif hasattr(body, 'isLightBulbOn'):
                if not body.isLightBulbOn:
                    return False
        except:
            return False

        # If under an occurrence, verify the entire chain is visible
        if occ is not None:
            if not _is_occurrence_chain_visible(occ):
                return False

        return True
    except:
        # Fail-safe: require body lightbulb
        try:
            return bool(getattr(body, 'isLightBulbOn', True))
        except:
            return True


# Nothing needed here - _is_body_visible is defined above




def _body_extents_mm(body: adsk.fusion.BRepBody):
    # Use body bounding box
    bb = body.boundingBox
    um = _um()
    dx = um.convert(bb.maxPoint.x - bb.minPoint.x, um.internalUnits, 'mm')
    dy = um.convert(bb.maxPoint.y - bb.minPoint.y, um.internalUnits, 'mm')
    dz = um.convert(bb.maxPoint.z - bb.minPoint.z, um.internalUnits, 'mm')
    # Try to infer orientation: assume XY is plan (Width x Depth) and Z is Height
    dims = sorted([abs(dx), abs(dy), abs(dz)], reverse=True)  # largest → smallest
    H = dims[0]  # Height (largest dimension)
    W = dims[1]  # Width (middle)
    D = dims[2]  # Depth (smallest)
    return W, H, D

def get_component_local_xyz_extents(body: adsk.fusion.BRepBody) -> dict:
    """
    Return extents along the component's local X/Y/Z axes as {"x": ex, "y": ey, "z": ez}
    No sorting. No min/mid/max heuristic.
     Component-local only: uses body.boundingBox (already in the owning component coordinates).
     Returns {"x": ex, "y": ey, "z": ez} in mm.
    """
    try:
        um = _um()
        bb = body.boundingBox
        dx = um.convert(bb.maxPoint.x - bb.minPoint.x, um.internalUnits, 'mm')
        dy = um.convert(bb.maxPoint.y - bb.minPoint.y, um.internalUnits, 'mm')
        dz = um.convert(bb.maxPoint.z - bb.minPoint.z, um.internalUnits, 'mm')
        return {"x": abs(dx), "y": abs(dy), "z": abs(dz)}
    except:
        # Fallback to previous method
        W, H, D = _body_extents_mm(body)
        return {"x": W, "y": H, "z": D}

def dims_from_rule(extents: dict, rule: dict) -> tuple:
    """
    rule holds axis letters like {'Thickness':'y','Length':'z','Width':'x'} (case-insensitive)
    Supports fallback keys 't','l','w'.
    Returns tuple (t, l, w) in mm.
    """
    def _get_axis_key(k_rule: str, alt: str):
        v = rule.get(k_rule)
        if v is None:
            v = rule.get(alt)
        return (v or '').lower()
    t_axis = _get_axis_key('Thickness', 't')
    l_axis = _get_axis_key('Length', 'l')
    w_axis = _get_axis_key('Width', 'w')
    t = extents[t_axis]
    l = extents[l_axis]
    w = extents[w_axis]
    return (t, l, w)


def _gather_for_body(body: adsk.fusion.BRepBody, units: str, include_obb: bool, occ: adsk.fusion.Occurrence = None):
    body_name = body.name or 'Unnamed Body'
    comp_name = body.parentComponent.name if body.parentComponent else 'Unknown'
    
    record = {
        'Body name': body_name,
        'Thickness': '',
        'Length': '',
        'Width': ''
    }

    # For bodies, we primarily use bounding box dimensions
    if include_obb:
        try:
            # Compute component-local axes extents (no sorting)
            ext = get_component_local_xyz_extents(body)
            x_mm, y_mm, z_mm = ext['x'], ext['y'], ext['z']
            # Debug capture of extents
            record['_x_mm'] = _to_display(x_mm, units)
            record['_y_mm'] = _to_display(y_mm, units)
            record['_z_mm'] = _to_display(z_mm, units)
            # Attach occurrence-scoped identifiers and units for export mapping
            try:
                record['_Occurrence'] = occ.fullPathName if occ else '(root)'
            except:
                record['_Occurrence'] = '(root)'
            try:
                record['CabinetId'] = _cabinet_id(occ) if occ else '(root)'
            except:
                record['CabinetId'] = '(root)'
            # ComponentName should reflect the parent component's name for export
            record['ComponentName'] = comp_name
            record['Units'] = units

            use_rules = PREFS.get('useRules', False)
            if use_rules:
                # Attempt rule-based mapping (with partial fallback). No sorting for rule bodies.
                n_ci = (body_name or '').strip().lower()
                rule = _match_orientation_rule(n_ci)
                if rule:
                    # Map directly via rule axes in component-local space
                    t_mm, l_mm, w_mm = dims_from_rule(ext, rule)

                    # Enforce thickness = smallest dimension when lockThicknessMin is on.
                    # Bodies oriented differently in component-local space can map axes
                    # inconsistently; sorting guarantees Thickness < Width < Length
                    # regardless of local orientation (correct for sheet goods).
                    if PREFS.get('lockThicknessMin', True):
                        vals = sorted([t_mm, l_mm, w_mm])
                        t_mm, w_mm, l_mm = vals[0], vals[1], vals[2]

                    record['_t_axis'] = (rule.get('Thickness') or rule.get('t','')).lower()
                    record['_l_axis'] = (rule.get('Length') or rule.get('l','')).lower()
                    record['_w_axis'] = (rule.get('Width') or rule.get('w','')).lower()

                    # Capture selected values for debug
                    record['_w_val'] = _to_display(w_mm, units)
                    record['_l_val'] = _to_display(l_mm, units)
                    record['_t_val'] = _to_display(t_mm, units)
                    record['Width'] = _to_display(w_mm, units)
                    record['Length'] = _to_display(l_mm, units)
                    record['Thickness'] = _to_display(t_mm, units)
                    record['_MatchedRule'] = True
                    if not record.get('_RuleName'):
                        record['_RuleName'] = rule.get('raw', '')
                    if not record.get('_Axes'):
                        record['_Axes'] = f"w:{record['_w_axis']}, l:{record['_l_axis']}, t:{record['_t_axis']}"
                    # Determine match type (exact/stripped/partial)
                    exact = next((r for r in ORIENTATION_RULES if r.get('name') == n_ci), None)
                    if exact and exact.get('raw','') == record['_RuleName']:
                        record['_MatchType'] = 'exact'
                    else:
                        record['_MatchType'] = 'partial'
                else:
                    # No rule found: fall back to simple heuristic using local axes
                    dims = sorted([x_mm, y_mm, z_mm])
                    thickness_mm = dims[0]
                    length_mm = dims[2]
                    width_mm = dims[1]
                    record['Thickness'] = _to_display(thickness_mm, units)
                    record['Length'] = _to_display(length_mm, units)
                    record['Width'] = _to_display(width_mm, units)
                    record['_MatchedRule'] = False
                    record['_RuleName'] = ''
                    if not record.get('_Axes'):
                        record['_Axes'] = 'heuristic: t=min, l=max, w=mid (local)'
                    record['_MatchType'] = 'heuristic'
                    record['_w_axis'] = record.get('_w_axis','mid') or 'mid'
                    record['_l_axis'] = record.get('_l_axis','max') or 'max'
                    record['_t_axis'] = record.get('_t_axis','min') or 'min'
            else:
                # Rules disabled: use simple heuristic (local axes)
                dims = sorted([x_mm, y_mm, z_mm])
                thickness_mm = dims[0]
                length_mm = dims[2]
                width_mm = dims[1]
                record['Thickness'] = _to_display(thickness_mm, units)
                record['Length'] = _to_display(length_mm, units)
                record['Width'] = _to_display(width_mm, units)
                record['_MatchedRule'] = False
                record['_RuleName'] = ''
                if not record.get('_Axes'):
                    record['_Axes'] = 'heuristic: t=min, l=max, w=mid (local)'
                record['_MatchType'] = 'heuristic'
                record['_w_axis'] = record.get('_w_axis','mid') or 'mid'
                record['_l_axis'] = record.get('_l_axis','max') or 'max'
                record['_t_axis'] = record.get('_t_axis','min') or 'min'
        except:
            pass

    return record


# Parameter extraction

def _collect_component_params(comp: adsk.fusion.Component):
    out = {}
    try:
        # ModelParameters (driven dimensions)
        mps = comp.modelParameters
        for i in range(mps.count):
            p = mps.item(i)
            nm = p.name.lower()
            if nm in PARAM_KEYS:
                key = PARAM_KEYS[nm]
                out[key] = _param_val_to_mm(p)
    except:
        pass
    return out


def _collect_named_user_params_for_occ(occ: adsk.fusion.Occurrence):
    out = {}
    try:
        des = _design()
        ups = des.userParameters
        occ_name = occ.name.replace(' ', '_')
        comp_name = occ.component.name.replace(' ', '_')
        prefixes = [occ_name + '_', comp_name + '_']
        for i in range(ups.count):
            p = ups.item(i)
            base = p.name.lower()
            # Match either exact base name or prefixed name
            for pref in prefixes:
                if p.name.lower().startswith(pref.lower()):
                    tail = p.name[len(pref):].lower()
                    if tail in PARAM_KEYS:
                        key = PARAM_KEYS[tail]
                        out[key] = _param_val_to_mm(p)
            if base in PARAM_KEYS:
                key = PARAM_KEYS[base]
                # only store if not already written by a prefixed version
                if key not in out:
                    out[key] = _param_val_to_mm(p)
    except:
        pass
    return out


# Cabinet ID helper

def _cabinet_id(occ: adsk.fusion.Occurrence) -> str:
    try:
        a = occ.attributes.itemByName(ATTR_NS, ATTR_ID)
        if a:
            return a.value
    except:
        pass
    # default to occurrence name
    return occ.name


# Exporters

def _ensure_folder(path_hint: str) -> str:
    if path_hint and len(path_hint.strip()) > 0:
        folder = path_hint.strip()
    else:
        folder = os.path.join(os.path.expanduser('~'), 'Desktop')
    
    try:
        os.makedirs(folder, exist_ok=True)
        return folder
    except Exception as e:
        # Fallback to desktop if there's an issue with the specified folder
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        os.makedirs(desktop, exist_ok=True)
        return desktop


def _export_csv_only(rows, folder: str, filename: str = 'CabinetParams', include_debug: bool = False):
    csv_path = os.path.join(folder, f'{filename}.csv')

    # Export with requested headers and naming (underscored)
    headers = ['Part_ID', 'Cabinet_ID', 'Width', 'Height', 'Depth', 'Units', 'Material']
    
    # Build output rows mapping internal fields to requested headers
    filtered_rows = []
    for r in rows:
        out = {
            'Part_ID': r.get('Body name', ''),
            'Cabinet_ID': r.get('ComponentName', r.get('Body name', '')),
            'Width': r.get('Width', ''),
            'Height': r.get('Length', ''),  # Map Length -> Height
            'Depth': r.get('Thickness', ''),  # Map Thickness -> Depth
            'Units': r.get('Units', 'in'),
            'Material': r.get('Material', '')
        }
        filtered_rows.append(out)

    # Use UTF-8 with BOM for Excel compatibility on Windows
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in filtered_rows:
            w.writerow(r)

    return csv_path


# Core logic

def _gather_for_occ(occ: adsk.fusion.Occurrence, units: str, include_obb: bool):
    comp = occ.component
    record = {
        'Part_ID': _cabinet_id(occ),
        'Cabinet_ID': comp.name,
        'Units': units,
        'Width': '',
        'Height': '',
        'Depth': ''
    }

    # 1) Component model parameters
    params = _collect_component_params(comp)
    for k, v in params.items():
        if k in ['Width', 'Height', 'Depth']:
            record[k] = _to_display(v, units)

    # 2) User parameters (global) with optional prefixes
    user_params = _collect_named_user_params_for_occ(occ)
    for k, v in user_params.items():
        if k in ['Width', 'Height', 'Depth']:
            record[k] = _to_display(v, units)

    # 3) Fallback: occurrence extents (only if not already set)
    if include_obb:
        try:
            W, H, D = _occ_extents_mm(occ)
            if not record['Width']:
                record['Width'] = _to_display(W, units)
            if not record['Height']:
                record['Height'] = _to_display(H, units)
            if not record['Depth']:
                record['Depth'] = _to_display(D, units)
        except:
            pass

    return record


# -----------------------
# Command Handlers
# -----------------------
class CmdCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.Command.cast(args.command)
            on_exec = CmdExecute()
            cmd.execute.add(on_exec)
            HANDLERS.append(on_exec)
            
            # Add input changed handler for browse button
            on_input_changed = CmdInputChanged()
            cmd.inputChanged.add(on_input_changed)
            HANDLERS.append(on_input_changed)

            inputs = cmd.commandInputs
            
            # Set compact dialog size that won't trigger maximization
            try:
                cmd.setDialogInitialSize(200, 180)  # Compact but reasonable size
                # Allow some flexibility to prevent forced maximization
                if hasattr(cmd, 'setDialogMinimumSize'):
                    cmd.setDialogMinimumSize(180, 160)
                if hasattr(cmd, 'setDialogMaximumSize'):
                    cmd.setDialogMaximumSize(250, 220)
            except:
                pass
            
            # Make inputs compact with reasonable widths
            def make_input_compact(input_obj):
                try:
                    input_obj.isFullWidth = False
                    # Set reasonable compact width
                    if hasattr(input_obj, 'preferredWidth'):
                        input_obj.preferredWidth = 80
                except:
                    pass
            
            # Units dropdown
            units_dropdown = inputs.addDropDownCommandInput('units', 'Units', adsk.core.DropDownStyles.TextListDropDownStyle)
            units_dropdown.listItems.add('in', PREFS['units'] == 'in')
            units_dropdown.listItems.add('mm', PREFS['units'] == 'mm')
            units_dropdown.listItems.add('cm', PREFS['units'] == 'cm')
            make_input_compact(units_dropdown)
            
            # Export folder (ultra-minimal display)
            export_path = PREFS['exportFolder'] or os.path.join(os.path.expanduser('~'), 'Desktop')
            # Show very short text to force smaller input
            folder_input = inputs.addStringValueInput('exportFolder', 'To', '...')
            folder_input.value = export_path
            make_input_compact(folder_input)
            
            # Filename (ultra-minimal)
            filename_short = PREFS.get('exportFilename', 'CabinetParams')[:25] + '...' if len(PREFS.get('exportFilename', '')) > 8 else PREFS.get('exportFilename', 'Parts')
            filename_input = inputs.addStringValueInput('exportFilename', 'Filename:', filename_short)
            make_input_compact(filename_input)
            
            # Browse options as a dropdown (with recent folders)
            browse_dd = inputs.addDropDownCommandInput('browseFolder', 'Browse', adsk.core.DropDownStyles.TextListDropDownStyle)
            try:
                li = browse_dd.listItems
                li.add('Browse...', False)
                # Recent folders (from prefs)
                recent = PREFS.get('recentFolders', []) if isinstance(PREFS.get('recentFolders'), list) else []
                # Avoid duplicates via normalized paths
                added = set()
                def _norm(p):
                    try:
                        return os.path.abspath(os.path.expanduser(p))
                    except:
                        return p
                def _add_item(p):
                    if not p:
                        return
                    np = _norm(p)
                    if np in added:
                        return
                    if os.path.isdir(np):
                        li.add(np, False)
                        added.add(np)
                for p in recent:
                    _add_item(p)
                # Common quick paths
                quick_desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
                quick_documents = os.path.join(os.path.expanduser('~'), 'Documents')
                current_folder = PREFS.get('exportFolder') or export_path
                for path_opt in [current_folder, quick_desktop, quick_documents]:
                    _add_item(path_opt)
                make_input_compact(browse_dd)
            except:
                pass

            # Removed checkboxes: always use partial match and rules; debug off
        except:
            UI.messageBox('CmdCreated failed\n' + traceback.format_exc())


class CmdInputChanged(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            cmd = args.firingEvent.sender
            changedInput = args.input
            
            if changedInput.id == 'browseFolder':
                # Handle dropdown selection for folder choices
                selectedFolder = None
                try:
                    sel_item = changedInput.selectedItem
                except:
                    sel_item = None

                if sel_item:
                    sel_name = sel_item.name
                    if sel_name == 'Browse...':
                        # Open folder browser dialog
                        folderDialog = UI.createFolderDialog()
                        folderDialog.title = 'Select Export Folder'
                        folderDialog.initialDirectory = PREFS.get('exportFolder', os.path.expanduser('~'))
                        dialogResult = folderDialog.showDialog()
                        if dialogResult == adsk.core.DialogResults.DialogOK:
                            selectedFolder = folderDialog.folder
                    else:
                        # Assume the selected item is a path
                        selectedFolder = sel_name

                if selectedFolder:
                    exportFolderInput = cmd.commandInputs.itemById('exportFolder')
                    if exportFolderInput:
                        exportFolderInput.value = selectedFolder
                        # Update tooltip with new folder path
                        self._update_tooltip(cmd.commandInputs)
                        # Track recent folder
                        try:
                            # Initialize recentFolders if missing
                            if 'recentFolders' not in PREFS or not isinstance(PREFS.get('recentFolders'), list):
                                PREFS['recentFolders'] = []
                            # Prepend and clamp
                            nf = os.path.abspath(selectedFolder)
                            PREFS['recentFolders'] = [nf] + [p for p in PREFS['recentFolders'] if os.path.abspath(p) != nf]
                            PREFS['recentFolders'] = PREFS['recentFolders'][:7]
                            with open(PREFS_FILE, 'w') as f:
                                json.dump(PREFS, f, indent=2)
                        except:
                            pass
            
            elif changedInput.id == 'exportFolder' or changedInput.id == 'exportFilename':
                # Update tooltip when folder or filename changes
                self._update_tooltip(cmd.commandInputs)
        except:
            UI.messageBox('Browse folder failed\n' + traceback.format_exc())
    
    def _update_tooltip(self, inputs):
        try:
            folder_input = inputs.itemById('exportFolder')
            filename_input = inputs.itemById('exportFilename')
            if folder_input and filename_input:
                folder_path = folder_input.value
                filename = filename_input.value or 'CabinetParams'
                folder_input.tooltip = f'{folder_path}\\{filename}.csv'
        except:
            pass


class CmdExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.Command.cast(args.firingEvent.sender)
            units = 'mm'
            visible_only = True
            selected_only = False
            include_obb = True
            export_all_bodies = True
            export_folder = ''
            export_filename = 'CabinetParams'
            # Force behavior: always partial match ON, rules ON, debug OFF
            use_partial = True
            include_debug = False
            use_rules = True

            for ci in cmd.commandInputs:
                if ci.id == 'units':
                    # Handle dropdown selection
                    try:
                        selected_item = ci.selectedItem
                        units = selected_item.name if selected_item else 'in'
                    except:
                        units = 'in'  # fallback
                elif ci.id == 'exportFolder':
                    export_folder = ci.value
                elif ci.id == 'exportFilename':
                    export_filename = ci.value or 'CabinetParams'
                # Removed parsing for usePartialMatch/includeDebug/useRules (fixed values)

            PREFS.update({'units': units, 'exportFolder': export_folder, 'exportFilename': export_filename, 'usePartialMatch': True, 'includeDebug': False, 'useRules': True})
            _save_prefs()

            des = _design()
            if not des:
                UI.messageBox('No active design.')
                return

            root = des.rootComponent

            # Always export all visible bodies with bounding box dimensions
            rows = []
            include_obb = True  # Always include bounding box dimensions
            
            # Reload orientation rules each run so CSV edits apply immediately
            try:
                _load_orientation_rules(PREFS.get('orientationRulesPath', ''))
            except:
                pass

            # Export all visible bodies in the design (track occurrences for local axes)
            def collect_pairs_from_component(comp, parent_occ=None):
                    pairs = []
                    # Collect bodies from this component (effective visibility)
                    for body in comp.bRepBodies:
                        if is_effectively_visible(body, parent_occ):
                            pairs.append((body, parent_occ))
                    # Recursively collect from child occurrences (skip hidden chains)
                    for occ in comp.occurrences:
                        if _is_occurrence_chain_visible(occ):
                            child_pairs = collect_pairs_from_component(occ.component, occ)
                            pairs.extend(child_pairs)
                    return pairs

            # Get all visible bodies from the design
            all_pairs = collect_pairs_from_component(root, None)

            # Pre-pass: capture RE Corner thickness per occurrence context
            re_corner_thickness_by_occ = {}
            try:
                for body, occ in all_pairs:
                    try:
                        if (body.name or '').strip() == 'RE Corner':
                            rec_rc = _gather_for_body(body, units, include_obb, occ)
                            occ_key = ''
                            try:
                                occ_key = occ.fullPathName if occ else '(root)'
                            except:
                                occ_key = '(root)'
                            # Cache the display-units thickness value
                            if rec_rc and rec_rc.get('Thickness') not in (None, ''):
                                re_corner_thickness_by_occ[occ_key] = rec_rc.get('Thickness')
                    except:
                        continue
            except:
                pass

            matched = 0
            unmatched = 0
            unmatched_rows = []
            unmatched_names = []
            for body, occ in all_pairs:
                rec = _gather_for_body(body, units, include_obb, occ)
                # Post-process override: CornerBack thickness equals RE Corner thickness (same occurrence context)
                try:
                    if (body.name or '').strip() == 'CornerBack':
                        occ_key = ''
                        try:
                            occ_key = occ.fullPathName if occ else '(root)'
                        except:
                            occ_key = '(root)'
                        if occ_key in re_corner_thickness_by_occ:
                            override_val = re_corner_thickness_by_occ.get(occ_key)
                            if override_val not in (None, ''):
                                rec['Thickness'] = override_val
                                # Keep debug in sync when present
                                rec['_t_val'] = override_val
                                # Optionally annotate axes string without adding columns
                                try:
                                    ax = rec.get('_Axes', '')
                                    if ax and '(t<-RE Corner value)' not in ax:
                                        rec['_Axes'] = f"{ax} (t<-RE Corner value)"
                                except:
                                    pass
                except:
                    pass
                try:
                    if rec.get('_MatchedRule'):
                        matched += 1
                    else:
                        unmatched += 1
                        unmatched_rows.append(rec)
                        try:
                            nm = rec.get('Body name', '(unnamed)')
                            if nm:
                                unmatched_names.append(nm)
                        except:
                            pass
                except:
                    pass
                rows.append(rec)

            if not rows:
                UI.messageBox('No visible bodies found. Please ensure components are visible in the design.')
                return

            folder = _ensure_folder(export_folder)
            csv_path = _export_csv_only(rows, folder, export_filename, include_debug)

            # If there are unmatched rows, write a separate CSV for quick review
            unmatched_path = ''
            try:
                if unmatched_rows:
                    unmatched_path = os.path.join(folder, f'{export_filename}-unmatched.csv')
                    headers = ['Part_ID', 'Cabinet_ID', 'Width', 'Height', 'Depth', 'Units', 'Material']
                    # Use UTF-8 with BOM for Excel compatibility on Windows
                    with open(unmatched_path, 'w', newline='', encoding='utf-8-sig') as uf:
                        uw = csv.DictWriter(uf, fieldnames=headers)
                        uw.writeheader()
                        for r in unmatched_rows:
                            out_r = {
                                'Part_ID': r.get('Body name', ''),
                                'Cabinet_ID': r.get('ComponentName', r.get('Body name', '')),
                                'Width': r.get('Width', ''),
                                'Height': r.get('Length', ''),
                                'Depth': r.get('Thickness', ''),
                                'Units': r.get('Units', 'in'),
                                'Material': r.get('Material', '')
                            }
                            uw.writerow(out_r)
            except:
                pass

            # Show minimal success message with option to open folder
            msg = 'Export complete!\n\n'
            msg += 'File created:\n'
            msg += f'   • {export_filename}.csv\n\n'
            msg += 'Open the export folder now?'
            
            result = UI.messageBox(msg, 'Export Complete', adsk.core.MessageBoxButtonTypes.YesNoButtonType)
            if result == adsk.core.DialogResults.DialogYes:
                try:
                    import subprocess
                    import os
                    
                    # Ensure the folder path is absolute and exists
                    abs_folder = os.path.abspath(folder)
                    if os.path.exists(abs_folder):
                        # Use the Windows explorer command with proper path formatting
                        subprocess.run(['explorer', abs_folder], shell=False, check=False)
                    else:
                        UI.messageBox(f'Folder not found: {abs_folder}', 'Error Opening Folder')
                except Exception as e:
                    UI.messageBox(f'Failed to open folder: {str(e)}\nFolder: {folder}', 'Error Opening Folder')
        except:
            UI.messageBox('CmdExecute failed\n' + traceback.format_exc())


# -----------------------
# Registration / Lifecycle
# -----------------------

def _add_cmd_to_ui(cmd_def: adsk.core.CommandDefinition, panel_id='SolidCreatePanel'):
    try:
        ws = UI.workspaces.itemById('FusionSolidEnvironment')
        panel = ws.toolbarPanels.itemById(panel_id)
        if not panel:
            # If the standard panel doesn't exist, try AddInsPanel
            panel = ws.toolbarPanels.itemById('AddInsPanel')
        if not panel:
            # Create our own panel as fallback
            panel = ws.toolbarPanels.add('OGWToolsPanel', 'OGW Tools', 'SolidCreatePanel', False)
        
        if panel.controls.itemById(CMD_ID):
            panel.controls.itemById(CMD_ID).deleteMe()
        panel.controls.addCommand(cmd_def)
    except:
        pass


def run(context):
    try:
        global APP, UI
        APP = adsk.core.Application.get()
        UI = APP.userInterface
        _load_prefs()

        cmd_defs = UI.commandDefinitions
        if cmd_defs.itemById(CMD_ID):
            cmd_defs.itemById(CMD_ID).deleteMe()
        cmd_def = cmd_defs.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP)

        created = CmdCreated()
        cmd_def.commandCreated.add(created)
        HANDLERS.append(created)

        _add_cmd_to_ui(cmd_def)

        UI.messageBox(f'✅ OGW Cabinet Parameter Exporter v0.1 loaded!\n\n📁 Export Location: {PREFS["exportFolder"]}\n\n🔍 Look for "OGW: Export Cabinet Parameters" in the toolbar.')
    except:
        if UI:
            UI.messageBox('Add‑in run failed\n' + traceback.format_exc())


def stop(context):
    try:
        ui = adsk.core.Application.get().userInterface
        cd = ui.commandDefinitions.itemById(CMD_ID)
        if cd:
            cd.deleteMe()
        ui.messageBox('OGW Cabinet Parameter Exporter unloaded.')
    except:
        pass
