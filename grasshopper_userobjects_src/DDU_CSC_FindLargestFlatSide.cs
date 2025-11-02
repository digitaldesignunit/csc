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
		Mesh InputMesh,
		double AngleTolerance,
		double DistanceTolerance,
		int FaceCountThreshold,
		int MaxSamples,
		ref object FlatPlane,
		ref object Points)
    {
        // GHENV COMPONENT SETTINGS
        this.Component.Name = "FindLargestFlatSide";
        this.Component.NickName = "FindLargestFlatSide";
        this.Component.Category = "DDU_CSC";
        this.Component.SubCategory = "7 Geometry Tools";
        this.Component.Description = (
            "Finds the largest flat side of a mesh using optimized algorithm. " +
            "Uses normal clustering and early termination heuristics for performance.");
        // Initialize input param descriptions
        this.Component.Params.Input[0].Description = (
            "Input Mesh for finding the largest flat side."
        );
        this.Component.Params.Input[1].Description = (
            "Angle tolerance for clustering normals."
        );
        this.Component.Params.Input[2].Description = (
            "Distance tolerance"
        );
        this.Component.Params.Input[3].Description = (
            "Face count threshold for large meshes. Meshes with face count " +
            "above this value will be processed by sampling a subset of vertices.\n" +
            "Defaults to 15.000"
        );
        this.Component.Params.Input[4].Description = (
            "Maximum points to sample for the fallback algorithm.\n" +
            "Defaults to 5.000"
        );

        // Initialize output param descriptions
        int opi = 0;
        if (this.Component.Params.Output[0].Name == "out")
            opi = 1;
        this.Component.Params.Input[0+opi].Description = (
            "Flattest Plane found. Normal always points AWAY from the Mesh."
        );
        this.Component.Params.Input[1+opi].Description = (
            "Final Points that were used to fit the flat plane."
        );

        // Validation
        if (InputMesh == null || !InputMesh.IsValid)
        {
            this.AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, 
                "Input Parameter Mesh failed to collect Data!");
            FlatPlane = new Grasshopper.DataTree<Plane>();
            Points = new Grasshopper.DataTree<Point3d>();
            return;
        }
        
        if (AngleTolerance <= 0)
            AngleTolerance = 3.0;
        
        if (DistanceTolerance <= 0)
            DistanceTolerance = 1.0;
        
        if (FaceCountThreshold <= 0)
            FaceCountThreshold = 10000;
        
        if (MaxSamples <= 0)
            MaxSamples = 5000;

        double angleTolRad = RhinoMath.ToRadians(AngleTolerance);
        
        // Ensure face and vertex normals are computed
        InputMesh.FaceNormals.ComputeFaceNormals();
        InputMesh.Normals.ComputeNormals();
        
        int faceCount = InputMesh.Faces.Count;
        var vertices = InputMesh.Vertices;
        var vertexNormals = InputMesh.Normals;
        var faceNormals = InputMesh.FaceNormals;
        
        // Precompute all face data
        var faceData = new List<FaceData>(faceCount);
        for (int i = 0; i < faceCount; i++)
        {
            var face = InputMesh.Faces[i];
            var p1 = vertices[face.A];
            var p2 = vertices[face.B];
            var p3 = vertices[face.C];
            
            var plane = new Plane(p1, p2, p3);
            var normal = faceNormals[i];
            
            faceData.Add(new FaceData
            {
                Index = i,
                Face = face,
                Plane = plane,
                Normal = normal,
                Vertices = face.IsQuad 
                    ? new[] { face.A, face.B, face.C, face.D }
                    : new[] { face.A, face.B, face.C }
            });
        }
        
        int maxPointsFound = 0;
        Plane bestPlane = Plane.WorldXY;
        HashSet<int> bestPointsIndices = new HashSet<int>();
        int vertexCount = vertices.Count;
        
        // DECISION: Use sampling directly for large meshes, clustering for smaller ones
        if (faceCount > FaceCountThreshold)
        {
            // Very large mesh: Use sampling approach directly
            int sampleSize = Math.Min(MaxSamples, faceCount);
            var sampledBest = FindBestFromSample(
                faceData,
                vertices,
                angleTolRad,
                DistanceTolerance,
                sampleSize);
            
            maxPointsFound = sampledBest.PointsCount;
            bestPointsIndices = sampledBest.Points;
            bestPlane = sampledBest.Plane;
        }
        else
        {
            // Small to medium mesh: Use clustering approach
            var normalClusters = ClusterFacesByNormal(faceData, angleTolRad);
            
            // Early termination threshold
            // If we find a cluster covering >80% of vertices, we can stop
            double earlyTermThreshold = 0.8 * vertexCount;
            
            // Process clusters instead of individual faces
            foreach (var cluster in normalClusters)
            {
                if (cluster.Count == 0) continue;
                
                // Use the first face in cluster as representative
                var baseFaceData = faceData[cluster[0]];
                var basePlane = baseFaceData.Plane;
                var baseNormal = baseFaceData.Normal;
                
                var currentPointsIndices = new HashSet<int>();
                
                // Check all faces in this cluster
                foreach (int faceIdx in cluster)
                {
                    var otherFaceData = faceData[faceIdx];
                    var otherNormal = otherFaceData.Normal;
                    
                    // Verify normal alignment (should be true for same cluster, but verify)
                    double angle = Vector3d.VectorAngle(baseNormal, otherNormal);
                    bool isParallel = (angle < angleTolRad) || 
                                     (angle > (Math.PI - angleTolRad));
                    
                    if (isParallel)
                    {
                        // Check distance for all vertices of this face
                        bool allInTolerance = true;
                        foreach (int vIdx in otherFaceData.Vertices)
                        {
                            double dist = basePlane.DistanceTo(vertices[vIdx]);
                            if (Math.Abs(dist) > DistanceTolerance)
                            {
                                allInTolerance = false;
                                break;
                            }
                        }
                        
                        if (allInTolerance)
                        {
                            foreach (int vIdx in otherFaceData.Vertices)
                                currentPointsIndices.Add(vIdx);
                        }
                    }
                }
                
                // Check if this cluster is better
                if (currentPointsIndices.Count > maxPointsFound)
                {
                    maxPointsFound = currentPointsIndices.Count;
                    bestPointsIndices = new HashSet<int>(currentPointsIndices);
                    bestPlane = basePlane;
                    
                    // Early termination check
                    if (maxPointsFound >= earlyTermThreshold)
                        break;
                }
            }
        }
        
        // Convert indices to points
        var finalPoints = new List<Point3d>();
        var finalNormals = new List<Vector3d>();
        foreach (int idx in bestPointsIndices)
        {
            finalPoints.Add(vertices[idx]);
            finalNormals.Add(vertexNormals[idx]);
        }
        
        // Fit plane to all found points for better accuracy
        if (finalPoints.Count > 2)
        {
            Plane fittedPlane;
            PlaneFitResult pfr = Plane.FitPlaneToPoints(finalPoints, out fittedPlane);
            if ((int) pfr >= 0)
            {
                bestPlane = fittedPlane;
                var ptX = finalPoints.Select(pt => pt.X);
                var ptY = finalPoints.Select(pt => pt.Y);
                var ptZ = finalPoints.Select(pt => pt.Z);
                Point3d ptCentroid = new Point3d(
                    ptX.Sum() / ptX.Count(),
                    ptY.Sum() / ptY.Count(),
                    ptZ.Sum() / ptZ.Count()
                );
                bestPlane.Origin = ptCentroid;
                var vX = finalNormals.Select(v => v.X);
                var vY = finalNormals.Select(v => v.Y);
                var vZ = finalNormals.Select(v => v.Z);
                Vector3d avgNormal = new Vector3d(
                    vX.Sum() / vX.Count(),
                    vY.Sum() / vY.Count(),
                    vZ.Sum() / vZ.Count()
                );
                avgNormal.Unitize();
                double dp = avgNormal * bestPlane.Normal;
                if (dp < 0)
                {
                    bestPlane.Flip();
                }
            }
        }
        
        FlatPlane = bestPlane;
        Points = finalPoints;
    }
    
    // Cluster faces by normal direction using spatial hashing
    private List<List<int>> ClusterFacesByNormal(List<FaceData> faceData, double angleTol)
    {
        // Use a dictionary to group faces by quantized normal direction
        // This creates buckets of similar normals
        var clusters = new Dictionary<string, List<int>>();
        
        foreach (var fd in faceData)
        {
            // Quantize normal to create hash key
            // Round to nearest 5 degrees to create buckets
            var normal = fd.Normal;
            int quantizedX = (int)(Math.Round(normal.X / angleTol) * angleTol * 1000);
            int quantizedY = (int)(Math.Round(normal.Y / angleTol) * angleTol * 1000);
            int quantizedZ = (int)(Math.Round(normal.Z / angleTol) * angleTol * 1000);
            
            // Also consider opposite direction (flip normal)
            string key1 = $"{quantizedX},{quantizedY},{quantizedZ}";
            string key2 = $"{-quantizedX},{-quantizedY},{-quantizedZ}";
            
            if (!clusters.ContainsKey(key1))
            {
                // Check if opposite key exists
                if (clusters.ContainsKey(key2))
                {
                    clusters[key2].Add(fd.Index);
                }
                else
                {
                    clusters[key1] = new List<int> { fd.Index };
                }
            }
            else
            {
                clusters[key1].Add(fd.Index);
            }
        }
        
        return clusters.Values.ToList();
    }
    
    // Sample-based search for very large meshes
    private (HashSet<int> Points, int PointsCount, Plane Plane) FindBestFromSample(
        List<FaceData> faceData,
        Rhino.Geometry.Collections.MeshVertexList vertices,
        double angleTol,
        double distTol,
        int sampleSize)
    {
        var random = new Random(42); // Fixed seed for reproducibility
        var sampled = faceData.OrderBy(x => random.Next()).Take(sampleSize).ToList();

        int maxPoints = 0;
        HashSet<int> bestPoints = new HashSet<int>();
        Plane bestPlane = Plane.WorldXY;

        foreach (var baseFace in sampled)
        {
            var currentPoints = new HashSet<int>();

            foreach (var otherFace in faceData)
            {
                double angle = Vector3d.VectorAngle(baseFace.Normal, otherFace.Normal);
                bool isParallel = (angle < angleTol) || (angle > (Math.PI - angleTol));

                if (isParallel)
                {
                    bool allInTol = true;
                    foreach (int vIdx in otherFace.Vertices)
                    {
                        Point3d vertex = vertices[vIdx];
                        double dist = Math.Abs(baseFace.Plane.DistanceTo(vertex));
                        if (dist > distTol)
                        {
                            allInTol = false;
                            break;
                        }
                    }

                    if (allInTol)
                    {
                        foreach (int vIdx in otherFace.Vertices)
                            currentPoints.Add(vIdx);
                    }
                }
            }

            if (currentPoints.Count > maxPoints)
            {
                maxPoints = currentPoints.Count;
                bestPoints = new HashSet<int>(currentPoints);
                bestPlane = baseFace.Plane;
            }
        }

        return (bestPoints, maxPoints, bestPlane);
    }
    
    private class FaceData
    {
        public int Index;
        public MeshFace Face;
        public Plane Plane;
        public Vector3d Normal;
        public int[] Vertices;
    }
}