using System;
using System.Linq;
using Autodesk.Revit.DB;

namespace MDC.Automation
{
    /// <summary>
    /// Phase 2: builds a fully parametric (flexing) box family.
    ///   Reference planes: Left, Right, Front, Back (plan) and Top (elevation)
    ///   Extrusion hosted on Ref. Level, each face aligned and locked to its plane
    ///   Labeled dimensions: Width (Left-Right), Depth (Front-Back), Height (Ref. Level-Top)
    ///   EQ dimensions keep the box centered on the family origin
    ///   Flex test: changes each parameter, verifies the geometry follows, then rolls back
    /// </summary>
    public static class BoxBuilder
    {
        private const double Tol = 1e-6;
        private const double DimOffset = 1.5; // feet from the box edge
        private const double EqOffset = 3.0;

        public static void Build(Document famDoc, BoxParams p)
        {
            double w = p.WidthFt, d = p.DepthFt, h = p.HeightFt;

            ViewPlan plan = FindView<ViewPlan>(famDoc, ViewType.FloorPlan, "Ref. Level");
            View front = FindView<View>(famDoc, ViewType.Elevation, "Front");
            Level refLevel = new FilteredElementCollector(famDoc).OfClass(typeof(Level)).Cast<Level>().FirstOrDefault()
                ?? throw new InvalidOperationException("No level found in the family template.");

            FamilyParameter pw, pd, ph;
            Extrusion box;

            using (var t = new Transaction(famDoc, "MDC Build Parametric Box"))
            {
                t.Start();
                SwallowWarnings(t);

                // 1. Type and parameters (must exist before dimensions are labeled)
                FamilyManager fm = famDoc.FamilyManager;
                if (fm.CurrentType == null) fm.NewType(p.TypeName);
                else fm.RenameCurrentType(p.TypeName);

                pw = GetOrAddLength(fm, "Width");
                pd = GetOrAddLength(fm, "Depth");
                ph = GetOrAddLength(fm, "Height");
                fm.Set(pw, w);
                fm.Set(pd, d);
                fm.Set(ph, h);
                SetText(fm, BuiltInParameter.ALL_MODEL_MANUFACTURER, "Midwest Design Creation");
                SetText(fm, BuiltInParameter.ALL_MODEL_URL, "https://midwestdesigncreation.com");
                Console.WriteLine("MDC: parameters ready");

                // 2. Reference planes
                double big = Math.Max(w, d) + 4.0;
                ReferencePlane left  = VerticalPlane(famDoc, plan, new XYZ(-w / 2, -big, 0), new XYZ(-w / 2, big, 0), "Left");
                ReferencePlane right = VerticalPlane(famDoc, plan, new XYZ( w / 2, -big, 0), new XYZ( w / 2, big, 0), "Right");
                ReferencePlane frnt  = VerticalPlane(famDoc, plan, new XYZ(-big, -d / 2, 0), new XYZ(big, -d / 2, 0), "Front");
                ReferencePlane back  = VerticalPlane(famDoc, plan, new XYZ(-big,  d / 2, 0), new XYZ(big,  d / 2, 0), "Back");

                ReferencePlane top = famDoc.FamilyCreate.NewReferencePlane(
                    new XYZ(-big, 0, h), new XYZ(big, 0, h), XYZ.BasisY, front);
                top.Name = "Top";
                Console.WriteLine("MDC: reference planes created");

                // 3. Extrusion hosted on the Ref. Level
                var loop = new CurveArray();
                XYZ a = new XYZ(-w / 2, -d / 2, 0), b = new XYZ(w / 2, -d / 2, 0),
                    c = new XYZ(w / 2, d / 2, 0),   e = new XYZ(-w / 2, d / 2, 0);
                loop.Append(Line.CreateBound(a, b));
                loop.Append(Line.CreateBound(b, c));
                loop.Append(Line.CreateBound(c, e));
                loop.Append(Line.CreateBound(e, a));
                var profile = new CurveArrArray();
                profile.Append(loop);

                SketchPlane sp = SketchPlane.Create(famDoc, refLevel.Id);
                box = famDoc.FamilyCreate.NewExtrusion(true, profile, sp, h);
                famDoc.Regenerate();
                Console.WriteLine("MDC: extrusion created");

                // 4. Lock each face to its reference plane
                Lock(famDoc, plan,  left,  FaceWithNormal(box, -XYZ.BasisX), "Left");
                Lock(famDoc, plan,  right, FaceWithNormal(box,  XYZ.BasisX), "Right");
                Lock(famDoc, plan,  frnt,  FaceWithNormal(box, -XYZ.BasisY), "Front");
                Lock(famDoc, plan,  back,  FaceWithNormal(box,  XYZ.BasisY), "Back");
                Lock(famDoc, front, top,   FaceWithNormal(box,  XYZ.BasisZ), "Top");
                Console.WriteLine("MDC: faces locked");

                // 5. Labeled dimensions
                Label(famDoc, plan, pw, Line.CreateBound(
                    new XYZ(-w / 2, -d / 2 - DimOffset, 0), new XYZ(w / 2, -d / 2 - DimOffset, 0)),
                    left.GetReference(), right.GetReference());

                Label(famDoc, plan, pd, Line.CreateBound(
                    new XYZ(w / 2 + DimOffset, -d / 2, 0), new XYZ(w / 2 + DimOffset, d / 2, 0)),
                    frnt.GetReference(), back.GetReference());

                Label(famDoc, front, ph, Line.CreateBound(
                    new XYZ(-w / 2 - DimOffset, 0, 0), new XYZ(-w / 2 - DimOffset, 0, h)),
                    refLevel.GetPlaneReference(), top.GetReference());
                Console.WriteLine("MDC: dimensions labeled");

                // 6. EQ dimensions to keep the box centered
                ReferencePlane centerLR = FindPlane(famDoc, "Center (Left/Right)");
                ReferencePlane centerFB = FindPlane(famDoc, "Center (Front/Back)");

                if (centerLR != null)
                    Equalize(famDoc, plan, Line.CreateBound(
                        new XYZ(-w / 2, -d / 2 - EqOffset, 0), new XYZ(w / 2, -d / 2 - EqOffset, 0)),
                        left.GetReference(), centerLR.GetReference(), right.GetReference());
                else Console.WriteLine("MDC: note, Center (Left/Right) plane not found, skipped EQ");

                if (centerFB != null)
                    Equalize(famDoc, plan, Line.CreateBound(
                        new XYZ(w / 2 + EqOffset, -d / 2, 0), new XYZ(w / 2 + EqOffset, d / 2, 0)),
                        frnt.GetReference(), centerFB.GetReference(), back.GetReference());
                else Console.WriteLine("MDC: note, Center (Front/Back) plane not found, skipped EQ");
                Console.WriteLine("MDC: EQ constraints added");

                t.Commit();
            }

            FlexTest(famDoc, box, pw, pd, ph, w, d, h);
        }

        // ---------- Flex test ----------

        private static void FlexTest(Document doc, Extrusion box,
            FamilyParameter pw, FamilyParameter pd, FamilyParameter ph, double w, double d, double h)
        {
            double tw = w + 1.0, td = d + 0.5, th = h + 0.75; // new test sizes in feet
            string result;

            using (var t = new Transaction(doc, "MDC Flex Test"))
            {
                t.Start();
                SwallowWarnings(t);
                FamilyManager fm = doc.FamilyManager;
                fm.Set(pw, tw);
                fm.Set(pd, td);
                fm.Set(ph, th);
                doc.Regenerate();

                BoundingBoxXYZ bb = box.get_BoundingBox(null);
                double gw = bb.Max.X - bb.Min.X, gd = bb.Max.Y - bb.Min.Y, gh = bb.Max.Z - bb.Min.Z;
                double cx = (bb.Max.X + bb.Min.X) / 2, cy = (bb.Max.Y + bb.Min.Y) / 2;

                bool ok = Near(gw, tw) && Near(gd, td) && Near(gh, th) && Near(cx, 0) && Near(cy, 0) && Near(bb.Min.Z, 0);
                result = $"expected {tw:0.###} x {td:0.###} x {th:0.###} ft, got {gw:0.###} x {gd:0.###} x {gh:0.###} ft, center ({cx:0.###}, {cy:0.###}), base {bb.Min.Z:0.###}";

                t.RollBack(); // always restore the customer's sizes

                if (!ok) throw new InvalidOperationException("MDC flex test FAILED: " + result);
            }
            Console.WriteLine("MDC: flex test passed, " + result);
        }

        private static bool Near(double a, double b) => Math.Abs(a - b) < 1e-4;

        // ---------- Helpers ----------

        private static T FindView<T>(Document doc, ViewType type, string name) where T : View
        {
            var views = new FilteredElementCollector(doc).OfClass(typeof(View)).Cast<View>()
                .Where(v => !v.IsTemplate && v.ViewType == type).OfType<T>().ToList();
            return views.FirstOrDefault(v => v.Name == name) ?? views.FirstOrDefault()
                ?? throw new InvalidOperationException($"No {type} view found in the family template.");
        }

        private static ReferencePlane FindPlane(Document doc, string name) =>
            new FilteredElementCollector(doc).OfClass(typeof(ReferencePlane)).Cast<ReferencePlane>()
                .FirstOrDefault(r => r.Name == name);

        private static ReferencePlane VerticalPlane(Document doc, View plan, XYZ start, XYZ end, string name)
        {
            ReferencePlane rp = doc.FamilyCreate.NewReferencePlane(start, end, XYZ.BasisZ, plan);
            rp.Name = name;
            return rp;
        }

        private static PlanarFace FaceWithNormal(Extrusion ext, XYZ normal)
        {
            var opt = new Options { ComputeReferences = true, IncludeNonVisibleObjects = true };
            foreach (GeometryObject obj in ext.get_Geometry(opt))
            {
                if (obj is Solid solid && solid.Faces.Size > 0)
                    foreach (Face f in solid.Faces)
                        if (f is PlanarFace pf && pf.FaceNormal.IsAlmostEqualTo(normal, Tol) && pf.Reference != null)
                            return pf;
            }
            throw new InvalidOperationException("Could not find extrusion face with normal " + normal);
        }

        private static void Lock(Document doc, View view, ReferencePlane plane, PlanarFace face, string label)
        {
            Dimension align = doc.FamilyCreate.NewAlignment(view, plane.GetReference(), face.Reference);
            align.IsLocked = true;
            Console.WriteLine($"MDC: locked {label} face");
        }

        private static void Label(Document doc, View view, FamilyParameter param, Line line, params Reference[] refs)
        {
            var ra = new ReferenceArray();
            foreach (Reference r in refs) ra.Append(r);
            Dimension dim = doc.FamilyCreate.NewDimension(view, line, ra);
            dim.FamilyLabel = param;
        }

        private static void Equalize(Document doc, View view, Line line, params Reference[] refs)
        {
            var ra = new ReferenceArray();
            foreach (Reference r in refs) ra.Append(r);
            Dimension dim = doc.FamilyCreate.NewDimension(view, line, ra);
            dim.AreSegmentsEqual = true;
        }

        private static FamilyParameter GetOrAddLength(FamilyManager fm, string name) =>
            fm.get_Parameter(name) ?? fm.AddParameter(name, GroupTypeId.Geometry, SpecTypeId.Length, false);

        private static void SetText(FamilyManager fm, BuiltInParameter bip, string value)
        {
            FamilyParameter fp = fm.get_Parameter(bip);
            if (fp != null && !fp.IsReadOnly) fm.Set(fp, value);
        }

        // Log and dismiss warnings so a headless run never stalls on them.
        private static void SwallowWarnings(Transaction t)
        {
            FailureHandlingOptions opts = t.GetFailureHandlingOptions();
            opts.SetFailuresPreprocessor(new WarningSwallower());
            t.SetFailureHandlingOptions(opts);
        }

        private class WarningSwallower : IFailuresPreprocessor
        {
            public FailureProcessingResult PreprocessFailures(FailuresAccessor accessor)
            {
                foreach (FailureMessageAccessor f in accessor.GetFailureMessages())
                {
                    if (f.GetSeverity() == FailureSeverity.Warning)
                    {
                        Console.WriteLine("MDC warning: " + f.GetDescriptionText());
                        accessor.DeleteWarning(f);
                    }
                }
                return FailureProcessingResult.Continue;
            }
        }
    }
}
