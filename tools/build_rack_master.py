# MDC Family Builder v1: Telecom rack / cabinet master
# Run in Dynamo (CPython3) inside a FRESH family from English-Imperial\Generic Model.rft, Revit 2023+.
# Builds: category, parameters, reference planes, labeled + EQ dimensions, 15 locked extrusions,
# visibility wiring, Clearance subcategory, power connector, then an automatic flex test.
# One Dynamo run = one undo step in Revit (Ctrl+Z removes everything it built).
import clr, os
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Electrical import ElectricalSystemType
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
from System import Guid, Convert

doc = DocumentManager.Instance.CurrentDBDocument
app = DocumentManager.Instance.CurrentUIApplication.Application
log = []

# ---------------------------------------------------------------- recipe
IN_ = lambda v: v / 12.0  # inches -> feet

DEFAULTS = {"Rack Units": 42, "Frame Allowance": IN_(4), "Width": 2.0, "Depth": 3.5,
            "Post Size": IN_(2), "Manager Width": 0.5, "Front Clearance": 3.0, "Rear Clearance": 3.0}
FLEX = {"Rack Units": 45, "Frame Allowance": IN_(4), "Width": 2.5, "Depth": 4.0,
        "Post Size": IN_(4), "Manager Width": IN_(10), "Front Clearance": 3.5, "Rear Clearance": 2.5}

def height(v): return (v["Rack Units"] * 1.75) / 12.0 + v["Frame Allowance"]

# name, axis (x = constant X, y = constant Y, z = constant Z), position from values, Is Reference
PLANES = [
    ("Left",                "x", lambda v: -v["Width"] / 2, "Left"),
    ("Right",               "x", lambda v:  v["Width"] / 2, "Right"),
    ("Back",                "y", lambda v:  v["Depth"], "Back"),
    ("Front Clearance",     "y", lambda v: -v["Front Clearance"], "NotAReference"),
    ("Rear Clearance",      "y", lambda v:  v["Depth"] + v["Rear Clearance"], "NotAReference"),
    ("Left Post",           "x", lambda v: -v["Width"] / 2 + v["Post Size"], "NotAReference"),
    ("Right Post",          "x", lambda v:  v["Width"] / 2 - v["Post Size"], "NotAReference"),
    ("Front Post",          "y", lambda v:  v["Post Size"], "NotAReference"),
    ("Back Post",           "y", lambda v:  v["Depth"] - v["Post Size"], "NotAReference"),
    ("Mid Depth",           "y", lambda v:  v["Depth"] / 2, "NotAReference"),
    ("Upright Front",       "y", lambda v:  v["Depth"] / 2 - v["Post Size"] / 2, "NotAReference"),
    ("Upright Back",        "y", lambda v:  v["Depth"] / 2 + v["Post Size"] / 2, "NotAReference"),
    ("Left Manager Outer",  "x", lambda v: -v["Width"] / 2 - v["Manager Width"], "NotAReference"),
    ("Right Manager Outer", "x", lambda v:  v["Width"] / 2 + v["Manager Width"], "NotAReference"),
    ("Top",                 "z", height, "Top"),
]

# view, planes (in order), axis, line offset (ft), label, EQ
d = DEFAULTS
OX = d["Width"] / 2 + d["Manager Width"]
DIMS = [
    ("plan",  ["Left", "Center (Left/Right)", "Right"], "x", d["Depth"] + d["Rear Clearance"] + 0.5, None, True),
    ("plan",  ["Left", "Right"], "x", d["Depth"] + d["Rear Clearance"] + 1.0, "Width", False),
    ("plan",  ["Center (Front/Back)", "Back"], "y", -OX - 1.0, "Depth", False),
    ("plan",  ["Front Clearance", "Center (Front/Back)"], "y", -OX - 1.75, "Front Clearance", False),
    ("plan",  ["Back", "Rear Clearance"], "y", -OX - 1.75, "Rear Clearance", False),
    ("plan",  ["Left", "Left Post"], "x", -d["Front Clearance"] - 0.5, "Post Size", False),
    ("plan",  ["Right Post", "Right"], "x", -d["Front Clearance"] - 0.5, "Post Size", False),
    ("plan",  ["Center (Front/Back)", "Front Post"], "y", OX + 0.75, "Post Size", False),
    ("plan",  ["Back Post", "Back"], "y", OX + 0.75, "Post Size", False),
    ("plan",  ["Center (Front/Back)", "Mid Depth", "Back"], "y", OX + 1.5, None, True),
    ("plan",  ["Upright Front", "Mid Depth", "Upright Back"], "y", OX + 2.25, None, True),
    ("plan",  ["Upright Front", "Upright Back"], "y", OX + 3.0, "Post Size", False),
    ("plan",  ["Left Manager Outer", "Left"], "x", -d["Front Clearance"] - 1.0, "Manager Width", False),
    ("plan",  ["Right", "Right Manager Outer"], "x", -d["Front Clearance"] - 1.0, "Manager Width", False),
    ("front", ["Ref. Level", "Top"], "z", -OX - 1.0, "Height", False),
]

# name, left, right, front, back, extrusion-end parameter, visibility parameter, subcategory
BOXES = [
    ("Cabinet Body", "Left", "Right", "Front Post", "Back Post", "Height", "Is Cabinet", None),
    ("Front Door", "Left", "Right", "Center (Front/Back)", "Front Post", "Height", "Front Door Visible", None),
    ("Rear Door", "Left", "Right", "Back Post", "Back", "Height", "Rear Door Visible", None),
    ("Post FL", "Left", "Left Post", "Center (Front/Back)", "Front Post", "Height", "Is 4 Post", None),
    ("Post FR", "Right Post", "Right", "Center (Front/Back)", "Front Post", "Height", "Is 4 Post", None),
    ("Post BL", "Left", "Left Post", "Back Post", "Back", "Height", "Is 4 Post", None),
    ("Post BR", "Right Post", "Right", "Back Post", "Back", "Height", "Is 4 Post", None),
    ("Upright L", "Left", "Left Post", "Upright Front", "Upright Back", "Height", "Is 2 Post", None),
    ("Upright R", "Right Post", "Right", "Upright Front", "Upright Back", "Height", "Is 2 Post", None),
    ("Foot L", "Left", "Left Post", "Center (Front/Back)", "Back", "Post Size", "Is 2 Post", None),
    ("Foot R", "Right Post", "Right", "Center (Front/Back)", "Back", "Post Size", "Is 2 Post", None),
    ("Manager L", "Left Manager Outer", "Left", "Center (Front/Back)", "Back", "Height", "Left Manager", None),
    ("Manager R", "Right", "Right Manager Outer", "Center (Front/Back)", "Back", "Height", "Right Manager", None),
    ("Front Clearance Zone", "Left", "Right", "Front Clearance", "Center (Front/Back)", "Height", "Show Clearance", "Clearance"),
    ("Rear Clearance Zone", "Left", "Right", "Back", "Rear Clearance", "Height", "Show Clearance", "Clearance"),
]

# ---------------------------------------------------------------- parameters
def params_spec():
    inch = lambda v: UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Inches)
    volts = lambda v: UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Volts)
    va = lambda v: UnitUtils.ConvertToInternalUnits(v, UnitTypeId.VoltAmperes)
    G = "3f2b8c1e-5a47-4d6b-9e21-7c0a4b8d1e"
    shared = [
        ("Rack Units", SpecTypeId.Int.Integer, GroupTypeId.Geometry, G + "01", 42),
        ("Height", SpecTypeId.Length, GroupTypeId.Geometry, G + "02", None),
        ("Width", SpecTypeId.Length, GroupTypeId.Geometry, G + "03", inch(24)),
        ("Depth", SpecTypeId.Length, GroupTypeId.Geometry, G + "04", inch(42)),
        ("Manager Width", SpecTypeId.Length, GroupTypeId.Geometry, G + "05", inch(6)),
        ("Front Clearance", SpecTypeId.Length, GroupTypeId.Geometry, G + "06", inch(36)),
        ("Rear Clearance", SpecTypeId.Length, GroupTypeId.Geometry, G + "07", inch(36)),
        ("Voltage", SpecTypeId.ElectricalPotential, GroupTypeId.Electrical, G + "08", volts(120)),
        ("Number of Poles", SpecTypeId.Int.NumberOfPoles, GroupTypeId.Electrical, G + "11", 1),
        ("Apparent Load", SpecTypeId.ApparentPower, GroupTypeId.Electrical, G + "10", va(5000)),
    ]
    family = [
        ("Frame Allowance", SpecTypeId.Length, GroupTypeId.Geometry, inch(4)),
        ("Post Size", SpecTypeId.Length, GroupTypeId.Geometry, inch(2)),
        ("Is 2 Post", SpecTypeId.Boolean.YesNo, GroupTypeId.Constraints, 0),
        ("Is 4 Post", SpecTypeId.Boolean.YesNo, GroupTypeId.Constraints, 0),
        ("Is Cabinet", SpecTypeId.Boolean.YesNo, GroupTypeId.Constraints, 1),
        ("Front Door", SpecTypeId.Boolean.YesNo, GroupTypeId.Constraints, 1),
        ("Rear Door", SpecTypeId.Boolean.YesNo, GroupTypeId.Constraints, 1),
        ("Left Manager", SpecTypeId.Boolean.YesNo, GroupTypeId.Constraints, 0),
        ("Right Manager", SpecTypeId.Boolean.YesNo, GroupTypeId.Constraints, 0),
        ("Show Clearance", SpecTypeId.Boolean.YesNo, GroupTypeId.Visibility, 1),
        ("Front Door Visible", SpecTypeId.Boolean.YesNo, GroupTypeId.Visibility, None),
        ("Rear Door Visible", SpecTypeId.Boolean.YesNo, GroupTypeId.Visibility, None),
    ]
    formulas = [("Height", 'Rack Units * 1.75" + Frame Allowance'),
                ("Front Door Visible", "and(Is Cabinet, Front Door)"),
                ("Rear Door Visible", "and(Is Cabinet, Rear Door)")]
    return shared, family, formulas

def set_value(fm, p, v):
    if v is None: return
    if isinstance(v, int): fm.Set(p, int(v))
    else: fm.Set(p, float(v))

def build_parameters(fm):
    shared, family, formulas = params_spec()
    folder = os.path.dirname(doc.PathName) or r"C:\MDC\Masters"
    sp_path = os.path.join(folder, "MDC_SharedParameters.txt")
    if not os.path.exists(sp_path): open(sp_path, "w").close()
    original = app.SharedParametersFilename
    try:
        app.SharedParametersFilename = sp_path
        spfile = app.OpenSharedParameterFile()
        group = spfile.Groups.get_Item("MDC Rack") or spfile.Groups.Create("MDC Rack")
        for name, spec, grp, guid, val in shared:
            if fm.get_Parameter(name): continue
            ext = group.Definitions.get_Item(name)
            if ext is None:
                opts = ExternalDefinitionCreationOptions(name, spec)
                opts.GUID = Guid(guid)
                ext = group.Definitions.Create(opts)
            set_value(fm, fm.AddParameter(ext, grp, False), val)
    finally:
        app.SharedParametersFilename = original
    for name, spec, grp, val in family:
        if fm.get_Parameter(name): continue
        set_value(fm, fm.AddParameter(name, grp, spec, False), val)
    for name, f in formulas:
        fm.SetFormula(fm.get_Parameter(name), f)
    for bip, text in [(BuiltInParameter.ALL_MODEL_MANUFACTURER, "Midwest Design Creation"),
                      (BuiltInParameter.ALL_MODEL_URL, "https://midwestdesigncreation.com")]:
        p = fm.get_Parameter(bip)
        if p: fm.Set(p, text)
    log.append("Parameters and formulas ready")

# ---------------------------------------------------------------- helpers
def find_view(vtype, name):
    views = [v for v in FilteredElementCollector(doc).OfClass(View) if not v.IsTemplate and v.ViewType == vtype]
    for v in views:
        if v.Name == name: return v
    return views[0]

def planes_by_name():
    return dict((r.Name, r) for r in FilteredElementCollector(doc).OfClass(ReferencePlane))

def ref_type(name):
    return Convert.ToInt32(getattr(FamilyInstanceReferenceType, name))

def plane_pos(rp, axis):
    o = rp.GetPlane().Origin
    return o.X if axis == "x" else (o.Y if axis == "y" else o.Z)

def face(ext, normal):
    opt = Options(); opt.ComputeReferences = True
    for g in ext.get_Geometry(opt):
        if isinstance(g, Solid) and g.Faces.Size > 0:
            for f in g.Faces:
                if isinstance(f, PlanarFace) and f.FaceNormal.IsAlmostEqualTo(normal):
                    return f
    raise Exception("face not found")

# ---------------------------------------------------------------- build
if not doc.IsFamilyDocument:
    OUT = ["Open a fresh family from Generic Model.rft first."]
elif "Left Post" in planes_by_name():
    OUT = ["This family already has rack planes. Start from a fresh Generic Model family."]
else:
    TransactionManager.Instance.EnsureInTransaction(doc)
    try:
        fm = doc.FamilyManager
        doc.OwnerFamily.FamilyCategory = Category.GetCategory(doc, BuiltInCategory.OST_CommunicationDevices)
        if fm.CurrentType is None: fm.NewType("Default")
        build_parameters(fm)

        plan = find_view(ViewType.FloorPlan, "Ref. Level")
        front = find_view(ViewType.Elevation, "Front")
        level = FilteredElementCollector(doc).OfClass(Level).FirstElement()

        # Reference planes
        existing = planes_by_name()
        R = {"Center (Left/Right)": existing["Center (Left/Right)"], "Center (Front/Back)": existing["Center (Front/Back)"]}
        AX = {"Center (Left/Right)": "x", "Center (Front/Back)": "y", "Ref. Level": "z"}
        CO = {"Center (Left/Right)": 0.0, "Center (Front/Back)": 0.0, "Ref. Level": 0.0}
        big = 25.0
        for name, axis, fn, isref in PLANES:
            c = fn(DEFAULTS)
            if axis == "x":
                rp = doc.FamilyCreate.NewReferencePlane(XYZ(c, -big, 0), XYZ(c, big, 0), XYZ.BasisZ, plan)
            elif axis == "y":
                rp = doc.FamilyCreate.NewReferencePlane(XYZ(-big, c, 0), XYZ(big, c, 0), XYZ.BasisZ, plan)
            else:
                rp = doc.FamilyCreate.NewReferencePlane(XYZ(-big, 0, c), XYZ(big, 0, c), XYZ.BasisY, front)
            rp.Name = name
            try: rp.get_Parameter(BuiltInParameter.ELEM_REFERENCE_NAME).Set(ref_type(isref))
            except Exception as e: log.append("Note: Is Reference not set on " + name)
            R[name] = rp; AX[name] = axis; CO[name] = c
        log.append("Reference planes: %d" % len(PLANES))
        doc.Regenerate()

        def ref(n): return level.GetPlaneReference() if n == "Ref. Level" else R[n].GetReference()

        # Dimensions
        for vname, names, axis, off, label, eq in DIMS:
            ra = ReferenceArray()
            for n in names: ra.Append(ref(n))
            cs = [CO[n] for n in names]; lo, hi = min(cs), max(cs)
            if axis == "x": line = Line.CreateBound(XYZ(lo, off, 0), XYZ(hi, off, 0))
            elif axis == "y": line = Line.CreateBound(XYZ(off, lo, 0), XYZ(off, hi, 0))
            else: line = Line.CreateBound(XYZ(off, 0, lo), XYZ(off, 0, hi))
            try:
                dim = doc.FamilyCreate.NewDimension(plan if vname == "plan" else front, line, ra)
            except Exception as e:
                raise Exception("Dimension %s (%s): %s" % (" / ".join(names), vname, e))
            if eq: dim.AreSegmentsEqual = True
            if label: dim.FamilyLabel = fm.get_Parameter(label)
        log.append("Dimensions: %d (labeled and EQ)" % len(DIMS))

        # Clearance subcategory
        cat = doc.OwnerFamily.FamilyCategory
        sub = cat.SubCategories.get_Item("Clearance") if cat.SubCategories.Contains("Clearance") \
              else doc.Settings.Categories.NewSubcategory(cat, "Clearance")

        # Boxes
        sp = SketchPlane.Create(doc, level.Id)
        E = {}
        for name, l, r, f, b, topp, vis, subcat in BOXES:
            x0, x1, y0, y1 = CO[l], CO[r], CO[f], CO[b]
            pts = [XYZ(x0, y0, 0), XYZ(x1, y0, 0), XYZ(x1, y1, 0), XYZ(x0, y1, 0)]
            loop = CurveArray()
            for i in range(4): loop.Append(Line.CreateBound(pts[i], pts[(i + 1) % 4]))
            prof = CurveArrArray(); prof.Append(loop)
            topval = fm.CurrentType.AsDouble(fm.get_Parameter(topp))
            ext = doc.FamilyCreate.NewExtrusion(True, prof, sp, topval)
            doc.Regenerate()
            for plane, normal in [(l, XYZ(-1, 0, 0)), (r, XYZ(1, 0, 0)), (f, XYZ(0, -1, 0)), (b, XYZ(0, 1, 0))]:
                doc.FamilyCreate.NewAlignment(plan, ref(plane), face(ext, normal).Reference).IsLocked = True
            fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(BuiltInParameter.EXTRUSION_END_PARAM), fm.get_Parameter(topp))
            fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(BuiltInParameter.IS_VISIBLE_PARAM), fm.get_Parameter(vis))
            if subcat: ext.Subcategory = sub
            E[name] = (ext, l, r, f, b, topp)
        log.append("Extrusions: %d, all sides locked" % len(BOXES))

        # Power connector on top of the cabinet body
        try:
            doc.Regenerate()
            conn = ConnectorElement.CreateElectricalConnector(doc, ElectricalSystemType.PowerBalanced,
                                                              face(E["Cabinet Body"][0], XYZ.BasisZ).Reference)
            for bip, pname in [(BuiltInParameter.RBS_ELEC_VOLTAGE, "Voltage"),
                               (BuiltInParameter.RBS_ELEC_NUMBER_OF_POLES, "Number of Poles"),
                               (BuiltInParameter.RBS_ELEC_APPARENT_LOAD, "Apparent Load")]:
                fm.AssociateElementParameterToFamilyParameter(conn.get_Parameter(bip), fm.get_Parameter(pname))
            log.append("Power connector added and associated")
        except Exception as e:
            log.append("NOTE: connector not added automatically (" + str(e) + "); add it by hand")

        # Flex test (rolled back afterwards)
        st = SubTransaction(doc); st.Start()
        fails = []
        try:
            for k, v in FLEX.items(): set_value(fm, fm.get_Parameter(k), v)
            doc.Regenerate()
            exp = dict((n, fn(FLEX)) for n, a, fn, i in PLANES)
            exp.update({"Center (Left/Right)": 0.0, "Center (Front/Back)": 0.0})
            for n, a, fn, i in PLANES:
                if abs(plane_pos(R[n], a) - exp[n]) > 1e-4: fails.append("plane " + n)
            for name, (ext, l, r, f, b, topp) in E.items():
                bb = ext.get_BoundingBox(None)
                want = [exp[l], exp[r], exp[f], exp[b], fm.CurrentType.AsDouble(fm.get_Parameter(topp))]
                got = [bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y, bb.Max.Z]
                if any(abs(a - b2) > 1e-4 for a, b2 in zip(got, want)): fails.append("box " + name)
        finally:
            st.RollBack()
        log.append("FLEX TEST PASSED: all planes and boxes followed" if not fails
                   else "FLEX TEST FAILED: " + ", ".join(fails))
    except Exception as e:
        log.append("ERROR: " + str(e))
    TransactionManager.Instance.TransactionTaskDone()
    OUT = log
