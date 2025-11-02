#region Usings
using System;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;

using Rhino;
using Rhino.Geometry;

using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Data;
using Grasshopper.Kernel.Types;
#endregion

public class Script_Instance : GH_ScriptInstance
{
    #region Notes
    /* 
      Members:
        RhinoDoc RhinoDocument
        GH_Document GrasshopperDocument
        IGH_Component Component
        int Iteration

      Methods (Virtual & overridable):
        Print(string text)
        Print(string format, params object[] args)
        Reflect(object obj)
        Reflect(object obj, string method_name)

        Author: Max Benjamin Eschenbach, Alessandro Garruto
        License: MIT License
        Version: 251102
    */
    #endregion

    private void RunScript(
		List<Polyline> Curves,
		int MaxIter,
		double Tolerance,
		int Starts,
		int Seed,
		ref object Quads,
		ref object Areas)
    {
        // Set component params
        this.Component.Name = "MaxInscribedQuad";
        this.Component.NickName = "MaxInscribedQuad";
        this.Component.Category = "DDU_CSC";
        this.Component.SubCategory = "7 Geometry Tools";
        this.Component.Description = (
            "Finds a maximum-area inscribed 4-point polygon (quadrilateral) inside each input closed polyline.\n" +
            "Method 0: pure Rhino (default)\n"
        );

        // Initialize input param descriptions
        if (this.Component.Params.Input.Count > 0)
            this.Component.Params.Input[0].Description = "Closed boundary polylines (PolylineCurve). Each is processed independently.";
        if (this.Component.Params.Input.Count > 2)
            this.Component.Params.Input[1].Description = "Maximum iterations for the optimizer.";
        if (this.Component.Params.Input.Count > 3)
            this.Component.Params.Input[2].Description = "Containment tolerance for inside checks (default 0.01).";
        if (this.Component.Params.Input.Count > 4)
            this.Component.Params.Input[3].Description = "Multi-start count; more starts improves quality (default 64).";
        if (this.Component.Params.Input.Count > 5)
            this.Component.Params.Input[4].Description = "Random seed for reproducibility (default 42).";

        // Initialize output param descriptions
        int i = 0;
        if (this.Component.Params.Output.Count > 0 && this.Component.Params.Output[0].Name == "out")
            i += 1;
        if (this.Component.Params.Output.Count > 0 + i)
            this.Component.Params.Output[0 + i].Description = "List of best inscribed quadrilaterals (Polyline).";
        if (this.Component.Params.Output.Count > 1 + i)
            this.Component.Params.Output[1 + i].Description = "Area of each quadrilateral.";

        // Process inputs
        if (Curves == null)
        {
            this.AddRuntimeMessage(
                GH_RuntimeMessageLevel.Warning,
                "Input Parameter Curves failed to collect Data!"
            );
            Quads = new Grasshopper.DataTree<System.Object>();
            Areas = new Grasshopper.DataTree<System.Object>();
            return;
        }
        if (MaxIter <= 0 | MaxIter == null)
            MaxIter = 150;
        if (Tolerance <= 0 | Tolerance == null)
            Tolerance = 0.01;
        if (Starts <= 0 | Starts == null)
            Starts = 64;
        if (Seed == 0 | Seed == null)
            Seed = 42;

        List<Polyline> quads = new List<Polyline>();
        List<double> areas = new List<double>();

        foreach (Polyline c in Curves)
        {
            PolylineCurve curve = c.ToPolylineCurve();
            if (curve == null || !curve.IsValid || !curve.IsClosed)
            {
                quads.Add(null);
                areas.Add(0.0);
                continue;
            }

            Polyline q;
            double a;
            BestQuad(curve, Tolerance, Starts, MaxIter, Seed, out q, out a);
            quads.Add(q);
            areas.Add(a);
        }

        Quads = quads;
        Areas = areas;
    }

    private static Plane FitPlaneForPolyline(PolylineCurve pl)
    {
        Plane plane;
        bool ok = pl.TryGetPlane(out plane);
        if (ok)
            return plane;

        Point3d[] pts = new Point3d[pl.PointCount];
        for (int i = 0; i < pl.PointCount; i++)
        {
            pts[i] = pl.Point(i);
        }
        PlaneFitResult pfr = Plane.FitPlaneToPoints(pts, out plane);
        bool ok2 = (int) pfr >= 0;
        return ok2 ? plane : Plane.WorldXY;
    }

    private static Point3d PointAtU(PolylineCurve plCurve, double u)
    {
        u = u % 1.0;
        double length = plCurve.GetLength();
        double s = u * length;
        double t;
        bool ok = plCurve.LengthParameter(s, out t);
        return ok ? plCurve.PointAt(t) : plCurve.PointAtStart;
    }

    private static double PolygonAreaXY(List<Point3d> pts)
    {
        double s = 0.0;
        int n = pts.Count;
        for (int i = 0; i < n; i++)
        {
            int j = (i + 1) % n;
            s += pts[i].X * pts[j].Y - pts[i].Y * pts[j].X;
        }
        return 0.5 * Math.Abs(s);
    }

    private static List<Point3d> SimpleQuad(List<Point3d> pts)
    {
        double cx = pts.Sum(p => p.X) / 4.0;
        double cy = pts.Sum(p => p.Y) / 4.0;
        List<Tuple<double, Point3d>> angPts = new List<Tuple<double, Point3d>>();
        foreach (Point3d p in pts)
        {
            double angle = Math.Atan2(p.Y - cy, p.X - cx);
            angPts.Add(Tuple.Create(angle, p));
        }
        angPts.Sort((a, b) => a.Item1.CompareTo(b.Item1));
        return angPts.Select(t => t.Item2).ToList();
    }

    private static bool SegmentInside(Curve curve, Plane plane, Point3d p, Point3d q, double Tolerance, int samples = 7)
    {
        for (int i = 0; i < samples; i++)
        {
            double a = (samples == 1) ? 0.0 : (double)i / (double)(samples - 1);
            Point3d m = new Point3d(
                p.X * (1 - a) + q.X * a,
                p.Y * (1 - a) + q.Y * a,
                p.Z * (1 - a) + q.Z * a
            );
            PointContainment rel = curve.Contains(m, plane, Tolerance);
            if (rel != PointContainment.Inside && rel != PointContainment.Coincident)
                return false;
        }
        return true;
    }

    private double QuadAreaIfValid(PolylineCurve curve, Plane plane, PolylineCurve pl, List<double> uvec, double Tolerance)
    {
        List<double> us = new List<double>(uvec.Select(u => u % 1.0));
        us.Sort();
        List<Point3d> pts = us.Select(u => PointAtU(pl, u)).ToList();
        List<Point3d> quad = SimpleQuad(pts);
        for (int i = 0; i < 4; i++)
        {
            int j = (i + 1) % 4;
            if (!SegmentInside(curve, plane, quad[i], quad[j], Tolerance))
                return 0.0;
        }
        return PolygonAreaXY(quad);
    }

    private Tuple<List<double>, double> ImproveUvec(PolylineCurve curve, Plane plane, PolylineCurve pl, List<double> uvec, double Tolerance, double delta, int iters = 1)
    {
        List<double> u = new List<double>(uvec);
        double best = QuadAreaIfValid(curve, plane, pl, u, Tolerance);
        for (int iter = 0; iter < iters; iter++)
        {
            for (int k = 0; k < 4; k++)
            {
                bool improved = true;
                while (improved)
                {
                    improved = false;
                    foreach (double step in new double[] { -delta, delta })
                    {
                        List<double> cand = new List<double>(u);
                        cand[k] = (cand[k] + step) % 1.0;
                        double a = QuadAreaIfValid(curve, plane, pl, cand, Tolerance);
                        if (a > best)
                        {
                            best = a;
                            u = cand;
                            improved = true;
                            break;
                        }
                    }
                }
            }
        }
        return Tuple.Create(u, best);
    }

    private void BestQuad(PolylineCurve curve, double tol, int Starts, int MaxIter, int Seed, out Polyline quad, out double area)
    {
        quad = null;
        area = 0.0;

        if (curve == null || !curve.IsValid || !curve.IsClosed)
            return;

        Plane plane = FitPlaneForPolyline(curve);
        PolylineCurve pl = curve;

        Random rng = new Random(Seed);
        double phi = (Math.Sqrt(5.0) - 1.0) * 0.5;
        List<List<double>> seeds = new List<List<double>>();

        double baseU = rng.NextDouble();
        for (int i = 0; i < Math.Max(1, Starts); i++)
        {
            double u1 = (baseU + i * phi) % 1.0;
            double u2 = (u1 + 0.25 + (0.03 * ((i * 3) % 5))) % 1.0;
            double u3 = (u1 + 0.50 + (0.07 * ((i * 5) % 7))) % 1.0;
            double u4 = (u1 + 0.75 + (0.11 * ((i * 7) % 11))) % 1.0;
            seeds.Add(new List<double> { u1, u2, u3, u4 });
        }

        double bestArea = 0.0;
        List<double> bestU = null;

        foreach (List<double> seedU in seeds)
        {
            double a0 = QuadAreaIfValid(curve, plane, pl, seedU, tol);
            if (a0 <= 0.0)
                continue;

            List<double> u = new List<double>(seedU);
            double a = a0;
            double delta = 0.08;
            int levels = Math.Max(1, Math.Min(6, MaxIter / 50));

            for (int lvl = 0; lvl < levels; lvl++)
            {
                var result = ImproveUvec(curve, plane, pl, u, tol, delta, iters: 1 + lvl);
                u = result.Item1;
                a = result.Item2;
                delta *= 0.35;
            }

            if (a > bestArea)
            {
                bestArea = a;
                bestU = u;
            }
        }

        if (bestU == null || bestArea <= 0.0)
            return;

        List<double> us = new List<double>(bestU.Select(ui => ui % 1.0));
        us.Sort();
        List<Point3d> pts = us.Select(u => PointAtU(pl, u)).ToList();
        List<Point3d> quadPts = SimpleQuad(pts);
        quadPts.Add(quadPts[0]);
        quad = new Polyline(quadPts);
        area = bestArea;
    }
}