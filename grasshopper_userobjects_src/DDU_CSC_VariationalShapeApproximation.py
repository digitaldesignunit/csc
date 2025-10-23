# -*- coding: utf-8 -*-
#! python3
# venv: DDU_CSC
print('ENV OK!')
# r: charset_normalizer
# r: requests
# r: numpy
# r: scipy
# r: scikit-learn
# r: robust-laplacian
# r: potpourri3d

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import List, Tuple, Dict

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
from sklearn.cluster import KMeans

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'VariationalShapeApproximation'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'VSA'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '0 Development'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    """
    Implements the Variational Shape Approximation (VSA) algorithm to
    segment a mesh into planar regions. Returns colored visualization
    mesh, proxy planes, and error metrics.

    Variational Shape Approximation (VSA) implementation based on:
    Cohen-Steiner D, Alliez P, Desbrun M (2004) Variational shape
    approximation. ACM Trans Graph (TOG) 23(3):905-914
    """
)


class CSC_VariationalShapeApproximation(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251023
    """

    def __init__(self):
        super().__init__()
        # initialize props
        self.Component = ghenv.Component  # type: ignore[reportUnedfinedVariable] # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def extract_mesh_data(self, mesh: Rhino.Geometry.Mesh) -> Tuple[
            np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract vertices, faces, face centers, and face normals from mesh.
        Returns: (vertices, faces, face_centers, face_normals)
        """
        # Extract vertices
        vertices = np.array([[v.X, v.Y, v.Z] for v in mesh.Vertices])

        # Extract faces (convert quads to triangles)
        faces = []
        for face in mesh.Faces:
            if face.IsTriangle:
                faces.append([face.A, face.B, face.C])
            elif face.IsQuad:
                # Split quad into two triangles
                faces.append([face.A, face.B, face.C])
                faces.append([face.A, face.C, face.D])
        faces = np.array(faces)

        # Compute face centers
        face_centers = np.array([
            np.mean(vertices[face], axis=0) for face in faces
        ])

        # Compute face normals
        face_normals = []
        for face in faces:
            v0, v1, v2 = vertices[face]
            normal = np.cross(v1 - v0, v2 - v0)
            norm = np.linalg.norm(normal)
            if norm > 1e-10:
                normal = normal / norm
            else:
                normal = np.array([0.0, 0.0, 1.0])  # fallback
            face_normals.append(normal)
        face_normals = np.array(face_normals)

        return vertices, faces, face_centers, face_normals

    def compute_face_areas(self, vertices: np.ndarray,
                          faces: np.ndarray) -> np.ndarray:
        """Compute area of each face."""
        areas = []
        for face in faces:
            v0, v1, v2 = vertices[face]
            area = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0))
            areas.append(area)
        return np.array(areas)

    def fit_plane_to_region(self, vertices: np.ndarray,
                           faces: np.ndarray,
                           face_centers: np.ndarray,
                           face_areas: np.ndarray,
                           region_faces: List[int]) -> Tuple[
                               np.ndarray, np.ndarray]:
        """
        Fit a plane to a region using proper VSA L2,1 energy minimization.
        Minimizes sum of area-weighted squared distances from face centers to plane.
        Returns: (plane_center, plane_normal)
        """
        if not region_faces:
            return (np.array([0.0, 0.0, 0.0]),
                    np.array([0.0, 0.0, 1.0]))

        # Collect face centers and areas for this region
        region_face_centers = []
        areas = []
        total_area = 0.0
        
        for face_idx in region_faces:
            # Use pre-computed face center for efficiency
            face_center = face_centers[face_idx]
            region_face_centers.append(face_center)
            
            area = face_areas[face_idx]
            areas.append(area)
            total_area += area

        if len(region_face_centers) < 3 or total_area < 1e-10:
            return (np.array([0.0, 0.0, 0.0]),
                    np.array([0.0, 0.0, 1.0]))

        region_face_centers = np.array(region_face_centers)
        areas = np.array(areas)

        # Compute area-weighted centroid (this is the optimal plane center)
        weighted_centroid = np.sum(region_face_centers * areas.reshape(-1, 1), axis=0) / total_area

        # Fit plane normal using area-weighted PCA
        # Center face centers around weighted centroid
        centered_points = region_face_centers - weighted_centroid
        
        # Create area-weighted covariance matrix
        # Each point contributes proportionally to its area
        weighted_points = centered_points * np.sqrt(areas.reshape(-1, 1))
        
        if len(weighted_points) >= 3:
            # SVD to find principal components
            U, S, Vt = np.linalg.svd(weighted_points, full_matrices=False)
            # Normal is the direction with smallest variance (last column of V)
            normal = Vt[-1]
        else:
            normal = np.array([0.0, 0.0, 1.0])

        # Ensure unit-length normal for stable distance computations
        nrm = np.linalg.norm(normal)
        if nrm > 1e-12:
            normal = normal / nrm

        return weighted_centroid, normal

    def compute_approximation_error(self, vertices: np.ndarray,
                                   faces: np.ndarray,
                                   face_centers: np.ndarray,
                                   face_areas: np.ndarray,
                                   regions: List[List[int]],
                                   plane_centers: List[np.ndarray],
                                   plane_normals: List[np.ndarray],
                                   debug: bool = False) -> float:
        """
        Compute the VSA L2,1 approximation error.
        Error = sum of area-weighted squared distances from face centers to proxy planes.
        """
        total_error = 0.0
        total_area = 0.0
        max_distance = 0.0
        error_count = 0

        for region_idx, region_faces in enumerate(regions):
            if not region_faces:
                continue

            plane_center = plane_centers[region_idx]
            plane_normal = plane_normals[region_idx]
            region_error = 0.0
            region_area = 0.0

            for face_idx in region_faces:
                face_area = face_areas[face_idx]

                # Use pre-computed face center for efficiency
                face_center = face_centers[face_idx]
                
                # Compute squared distance from face center to proxy plane
                # Distance from point to plane: |dot(point - plane_center, plane_normal)|
                to_face = face_center - plane_center
                distance = abs(np.dot(to_face, plane_normal))
                squared_distance = distance * distance
                max_distance = max(max_distance, distance)
                
                # VSA L2,1 error: area-weighted squared distance
                error_contribution = squared_distance * face_area
                
                total_error += error_contribution
                total_area += face_area
                region_error += error_contribution
                region_area += face_area
                error_count += 1

            if debug and region_area > 0:
                avg_region_error = region_error / region_area
                self._addRemark(f"Region {region_idx}: {len(region_faces)} faces, "
                               f"avg error = {avg_region_error:.6f}")

        # Normalize by total area to get average error per unit area
        final_error = total_error / total_area if total_area > 0 else 0.0
        
        if debug:
            self._addRemark(f"VSA L2,1 error: {error_count} faces, "
                           f"max distance = {max_distance:.4f}, "
                           f"final error = {final_error:.6f}")

        return final_error

    def initialize_regions_random(self, num_faces: int, num_regions: int) -> np.ndarray:
        """Initialize regions randomly for more challenging starting point."""
        np.random.seed(42)  # For reproducible results
        labels = np.random.randint(0, num_regions, size=num_faces)
        return labels

    def initialize_regions_kmeans(self, face_centers: np.ndarray,
                                 face_normals: np.ndarray,
                                 num_regions: int) -> np.ndarray:
        """Initialize regions using K-means clustering."""
        # Combine position and normal information
        # Weight normals more heavily to create more challenging initial regions
        features = np.hstack([face_centers * 0.3, face_normals * 0.7])

        # Normalize features
        features = (features - np.mean(features, axis=0)) / (
            np.std(features, axis=0) + 1e-10)

        # K-means clustering
        kmeans = KMeans(n_clusters=num_regions, random_state=42, n_init=10)
        labels = kmeans.fit_predict(features)

        return labels

    def assign_faces_to_regions(self, vertices: np.ndarray,
                               faces: np.ndarray,
                               face_centers: np.ndarray,
                               face_normals: np.ndarray,
                               face_areas: np.ndarray,
                               plane_centers: List[np.ndarray],
                               plane_normals: List[np.ndarray]) -> List[
                                   List[int]]:
        """
        Assign each face to the region that minimizes VSA L2,1 error.
        Uses distance from face center to proxy plane.
        """
        num_faces = len(faces)
        num_regions = len(plane_centers)
        regions = [[] for _ in range(num_regions)]

        for face_idx in range(num_faces):
            # Use pre-computed face center for efficiency
            face_center = face_centers[face_idx]

            best_region = 0
            best_distance = float('inf')

            for region_idx in range(num_regions):
                plane_center = plane_centers[region_idx]
                plane_normal = plane_normals[region_idx]

                # VSA assignment: minimize distance from face center to proxy plane
                to_face = face_center - plane_center
                distance = abs(np.dot(to_face, plane_normal))

                if distance < best_distance:
                    best_distance = distance
                    best_region = region_idx

            regions[best_region].append(face_idx)

        return regions

    def vsa_iteration(self, vertices: np.ndarray, faces: np.ndarray,
                     face_centers: np.ndarray, face_normals: np.ndarray,
                     face_areas: np.ndarray, regions: List[List[int]]) -> Tuple[
                         List[List[int]], List[np.ndarray], List[np.ndarray]]:
        """
        Perform one VSA iteration: update proxies and reassign faces.
        """
        # Update proxies (fit planes to current regions using proper VSA method)
        plane_centers = []
        plane_normals = []

        for region_faces in regions:
            center, normal = self.fit_plane_to_region(vertices, faces, face_centers,
                                                     face_areas, region_faces)
            plane_centers.append(center)
            plane_normals.append(normal)

        # Reassign faces to regions using VSA distance-based assignment
        new_regions = self.assign_faces_to_regions(
            vertices, faces, face_centers, face_normals, face_areas,
            plane_centers, plane_normals
        )

        return new_regions, plane_centers, plane_normals

    def split_high_error_regions(self, vertices: np.ndarray, faces: np.ndarray,
                                face_centers: np.ndarray, face_normals: np.ndarray,
                                face_areas: np.ndarray, regions: List[List[int]],
                                plane_centers: List[np.ndarray],
                                plane_normals: List[np.ndarray],
                                threshold: float) -> Tuple[List[List[int]], bool]:
        """Split regions that have high approximation error."""
        new_regions = []
        split_occurred = False
        
        # Limit maximum number of regions to prevent explosion
        max_regions = min(50, len(faces) // 10)
        if len(regions) >= max_regions:
            return regions, False
        
        # Limit splits per iteration (conservative to avoid region explosion)
        splits_this_iteration = 0
        max_splits_per_iteration = 1
        # Require clear local improvement to justify a split
        min_split_improvement = 0.10  # 10% improvement on the region error
        
        for region_idx, region_faces in enumerate(regions):
            if len(region_faces) < 6:  # Don't split very small regions
                new_regions.append(region_faces)
                continue
                
            # Compute VSA L2,1 error for this region
            region_error = 0.0
            region_area = 0.0
            plane_center = plane_centers[region_idx]
            plane_normal = plane_normals[region_idx]
            
            for face_idx in region_faces:
                face_area = face_areas[face_idx]
                
                # Use pre-computed face center for efficiency
                face_center = face_centers[face_idx]
                
                # VSA L2,1 error: squared distance from face center to proxy plane
                to_face = face_center - plane_center
                distance = abs(np.dot(to_face, plane_normal))
                squared_distance = distance * distance
                
                region_error += squared_distance * face_area
                region_area += face_area
            
            avg_region_error = region_error / region_area if region_area > 0 else 0.0
            
            # Split if error is significantly above threshold AND region is large enough
            # AND we haven't split too many regions this iteration
            if (avg_region_error > threshold * 2.0 and len(region_faces) > 20 and 
                splits_this_iteration < max_splits_per_iteration):
                # Split into 2 sub-regions using K-means
                region_face_centers = []
                region_face_normals = []
                
                for face_idx in region_faces:
                    # Use pre-computed face center for efficiency
                    center = face_centers[face_idx]
                    region_face_centers.append(center)
                    
                    # Use pre-computed face normal for efficiency
                    normal = face_normals[face_idx]
                    region_face_normals.append(normal)
                
                if len(region_face_centers) >= 2:
                    region_face_centers = np.array(region_face_centers)
                    region_face_normals = np.array(region_face_normals)
                    
                    # K-means with 2 clusters
                    features = np.hstack([region_face_centers, region_face_normals])
                    features = (features - np.mean(features, axis=0)) / (np.std(features, axis=0) + 1e-10)
                    
                    kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
                    labels = kmeans.fit_predict(features)
                    
                    # Create sub-regions
                    sub_region_0 = []
                    sub_region_1 = []
                    
                    for i, face_idx in enumerate(region_faces):
                        if labels[i] == 0:
                            sub_region_0.append(face_idx)
                        else:
                            sub_region_1.append(face_idx)
                    
                    if len(sub_region_0) > 0 and len(sub_region_1) > 0:
                        # Evaluate if the split provides sufficient local error improvement
                        # Fit planes for each sub-region
                        c0, n0 = self.fit_plane_to_region(vertices, faces, face_centers, face_areas, sub_region_0)
                        c1, n1 = self.fit_plane_to_region(vertices, faces, face_centers, face_areas, sub_region_1)
                        # Compute sub-region errors (area-weighted average)
                        err0 = 0.0
                        area0 = 0.0
                        for fidx in sub_region_0:
                            a = face_areas[fidx]
                            p = face_centers[fidx]
                            d = abs(np.dot(p - c0, n0))
                            err0 += (d * d) * a
                            area0 += a
                        avg0 = (err0 / area0) if area0 > 0 else 0.0
                        err1 = 0.0
                        area1 = 0.0
                        for fidx in sub_region_1:
                            a = face_areas[fidx]
                            p = face_centers[fidx]
                            d = abs(np.dot(p - c1, n1))
                            err1 += (d * d) * a
                            area1 += a
                        avg1 = (err1 / area1) if area1 > 0 else 0.0
                        # New weighted average error for both sub-regions
                        new_avg_error = ((avg0 * area0) + (avg1 * area1)) / ((area0 + area1) if (area0 + area1) > 0 else 1.0)
                        # Require at least min_split_improvement relative improvement over original region error
                        if avg_region_error > 0 and (avg_region_error - new_avg_error) / avg_region_error >= min_split_improvement:
                            new_regions.append(sub_region_0)
                            new_regions.append(sub_region_1)
                            split_occurred = True
                            splits_this_iteration += 1
                            continue
            
            # No split, keep original region
            new_regions.append(region_faces)
        
        return new_regions, split_occurred

    def find_adjacent_regions(self, faces: np.ndarray, regions: List[List[int]]) -> Dict[int, set]:
        """Find which regions are adjacent (share edges)."""
        # Create face-to-region mapping
        face_to_region = {}
        for region_idx, region_faces in enumerate(regions):
            for face_idx in region_faces:
                face_to_region[face_idx] = region_idx
        
        # Build edge-to-faces mapping
        edge_to_faces = {}
        for face_idx, face in enumerate(faces):
            # Create edges (sorted vertex pairs)
            edges = [
                tuple(sorted([face[0], face[1]])),
                tuple(sorted([face[1], face[2]])),
                tuple(sorted([face[2], face[0]]))
            ]
            for edge in edges:
                if edge not in edge_to_faces:
                    edge_to_faces[edge] = []
                edge_to_faces[edge].append(face_idx)
        
        # Find adjacent regions
        adjacency = {i: set() for i in range(len(regions))}
        for edge, edge_faces in edge_to_faces.items():
            if len(edge_faces) == 2:  # Shared edge
                face1, face2 = edge_faces
                if face1 in face_to_region and face2 in face_to_region:
                    region1 = face_to_region[face1]
                    region2 = face_to_region[face2]
                    if region1 != region2:
                        adjacency[region1].add(region2)
                        adjacency[region2].add(region1)
        
        return adjacency

    def merge_regions_if_beneficial(self, vertices: np.ndarray, faces: np.ndarray,
                                   face_centers: np.ndarray, face_areas: np.ndarray, 
                                   regions: List[List[int]],
                                   plane_centers: List[np.ndarray],
                                   plane_normals: List[np.ndarray],
                                   threshold: float) -> Tuple[List[List[int]], bool]:
        """Merge adjacent regions if it doesn't exceed error threshold."""
        if len(regions) <= 2:  # Don't merge if we have very few regions
            return regions, False
            
        adjacency = self.find_adjacent_regions(faces, regions)
        merged_occurred = False
        
        # Try to merge each region with its neighbors
        region_merged = [False] * len(regions)
        new_regions = []
        
        for region_idx in range(len(regions)):
            if region_merged[region_idx]:
                continue
                
            current_region = regions[region_idx]
            best_merge_candidate = None
            best_merge_error = float('inf')
            
            # Check all adjacent regions
            for neighbor_idx in adjacency[region_idx]:
                if region_merged[neighbor_idx]:
                    continue
                    
                # Test merging these two regions
                merged_faces = current_region + regions[neighbor_idx]
                
                # Fit plane to merged region using proper VSA method
                merged_center, merged_normal = self.fit_plane_to_region(
                    vertices, faces, face_centers, face_areas, merged_faces)
                
                # Compute VSA L2,1 error for merged region
                merged_error = 0.0
                merged_area = 0.0
                
                for face_idx in merged_faces:
                    face_area = face_areas[face_idx]
                    
                    # Use pre-computed face center for efficiency
                    face_center = face_centers[face_idx]
                    
                    # VSA L2,1 error: squared distance from face center to proxy plane
                    to_face = face_center - merged_center
                    distance = abs(np.dot(to_face, merged_normal))
                    squared_distance = distance * distance
                    
                    merged_error += squared_distance * face_area
                    merged_area += face_area
                
                avg_merged_error = merged_error / merged_area if merged_area > 0 else 0.0
                
                # If merged error is acceptable, consider this merge
                if avg_merged_error <= threshold and avg_merged_error < best_merge_error:
                    best_merge_candidate = neighbor_idx
                    best_merge_error = avg_merged_error
            
            # Perform the best merge if found
            if best_merge_candidate is not None:
                merged_faces = current_region + regions[best_merge_candidate]
                new_regions.append(merged_faces)
                region_merged[region_idx] = True
                region_merged[best_merge_candidate] = True
                merged_occurred = True
                self._addRemark(f"Merged regions {region_idx} and {best_merge_candidate}, "
                               f"error = {best_merge_error:.4f}")
            else:
                # No beneficial merge found, keep original region
                new_regions.append(current_region)
                region_merged[region_idx] = True
        
        return new_regions, merged_occurred

    def perform_vsa(self, mesh: Rhino.Geometry.Mesh, mode: str, value: float,
                   max_iterations: int = 50) -> Tuple[
                       List[List[int]], List[np.ndarray], List[np.ndarray],
                       List[float], int]:
        """
        Perform Variational Shape Approximation.

        Args:
            mesh: Input Rhino mesh
            mode: 'faces' for fixed number of regions, 'threshold' for error
            value: Number of regions (faces mode) or error threshold (0-1)
            max_iterations: Maximum number of iterations

        Returns:
            (regions, plane_centers, plane_normals, error_history, iterations)
        """
        # Extract mesh data
        vertices, faces, face_centers, face_normals = self.extract_mesh_data(
            mesh)
        face_areas = self.compute_face_areas(vertices, faces)

        self._addRemark(f"Processing mesh with {len(vertices)} vertices "
                       f"and {len(faces)} faces")

        # Initialize regions
        if mode == 'faces':
            num_regions = max(1, int(value))
            self._addRemark(f"VSA mode: Fixed {num_regions} regions")
        else:  # threshold mode
            # Start with fewer regions for threshold mode
            num_regions = max(2, min(6, len(faces) // 100))
            self._addRemark(f"VSA mode: Threshold {value:.3f} "
                           f"(error metric), starting with {num_regions} regions")

        # ALWAYS use K-means initialization - it's good!
        initial_labels = self.initialize_regions_kmeans(face_centers,
                                                       face_normals,
                                                       num_regions)

        regions = [[] for _ in range(num_regions)]
        for face_idx, label in enumerate(initial_labels):
            regions[label].append(face_idx)

        # Remove empty regions
        regions = [region for region in regions if region]

        error_history = []

        # VSA iterations
        for iteration in range(max_iterations):
            # Perform one VSA iteration
            new_regions, plane_centers, plane_normals = self.vsa_iteration(
                vertices, faces, face_centers, face_normals, face_areas,
                regions
            )

            # Compute approximation error with debug info for first iteration
            debug_info = (iteration == 0)
            error = self.compute_approximation_error(
                vertices, faces, face_centers, face_areas, new_regions, plane_centers,
                plane_normals, debug=debug_info
            )
            error_history.append(error)

            self._addRemark(f"Iteration {iteration + 1}: {len(new_regions)} regions, "
                           f"Error = {error:.4f}")

            # For threshold mode, try both splitting and merging
            if mode == 'threshold':
                # First try merging regions that can be combined without exceeding threshold
                merged_regions, merge_occurred = self.merge_regions_if_beneficial(
                    vertices, faces, face_centers, face_areas, new_regions, plane_centers,
                    plane_normals, value
                )
                
                if merge_occurred:
                    self._addRemark(f"Merged regions: {len(new_regions)} -> {len(merged_regions)}")
                    new_regions = merged_regions
                    # Re-fit planes after merging
                    _, plane_centers, plane_normals = self.vsa_iteration(
                        vertices, faces, face_centers, face_normals, face_areas,
                        new_regions
                    )
                    # Recompute error
                    error = self.compute_approximation_error(
                        vertices, faces, face_centers, face_areas, new_regions, plane_centers,
                        plane_normals, debug=False
                    )
                
                # Then try splitting if error is still too high
                if error > value:
                    split_regions, split_occurred = self.split_high_error_regions(
                        vertices, faces, face_centers, face_normals, face_areas, new_regions, 
                        plane_centers, plane_normals, value
                    )
                    
                    if split_occurred:
                        self._addRemark(f"Split regions: {len(new_regions)} -> {len(split_regions)}")
                        new_regions = split_regions
                        # After any split, greedily merge as much as possible
                        while True:
                            merged_regions, merge_more = self.merge_regions_if_beneficial(
                                vertices, faces, face_centers, face_areas, new_regions, plane_centers,
                                plane_normals, value
                            )
                            if not merge_more:
                                break
                            self._addRemark(f"Post-split merging: {len(new_regions)} -> {len(merged_regions)}")
                            new_regions = merged_regions
                        # Re-fit planes after split/merge adjustments
                        _, plane_centers, plane_normals = self.vsa_iteration(
                            vertices, faces, face_centers, face_normals, face_areas,
                            new_regions
                        )
                        # Recompute error
                        error = self.compute_approximation_error(
                            vertices, faces, face_centers, face_areas, new_regions, plane_centers,
                            plane_normals, debug=False
                        )

            # Check convergence for threshold mode
            if mode == 'threshold' and error <= value:
                self._addRemark(f"Converged: Error {error:.4f} <= "
                               f"Threshold {value:.4f}")
                regions = new_regions
                break

            # Check convergence (regions didn't change much)
            # For fixed-regions mode, avoid early stopping and prefer running
            # to MaxIterations. Only apply this early-stop in threshold mode.
            if iteration > 0 and mode != 'faces':
                prev_error = (error_history[-2] if len(error_history) > 1
                             else float('inf'))
                # Use relative error change for better convergence detection
                relative_change = (abs(error - prev_error) / prev_error 
                                 if prev_error > 0 else 0.0)
                # Also require that assignment changes are sufficiently small
                # Compute fraction of faces that changed region
                total_faces = float(len(faces)) if len(faces) > 0 else 1.0
                changed = 0
                if len(regions) == len(new_regions):
                    # Build face->region maps
                    prev_map = {}
                    for r_idx, r_faces in enumerate(regions):
                        for f_idx in r_faces:
                            prev_map[f_idx] = r_idx
                    new_map = {}
                    for r_idx, r_faces in enumerate(new_regions):
                        for f_idx in r_faces:
                            new_map[f_idx] = r_idx
                    for f_idx in range(len(faces)):
                        if prev_map.get(f_idx) != new_map.get(f_idx):
                            changed += 1
                frac_changed = changed / total_faces

                if relative_change < 1e-4 and frac_changed < 0.005:  # 0.5% faces move
                    self._addRemark(
                        f"Converged: dE/E={relative_change:.6f}, moved={frac_changed*100:.3f}%")
                    regions = new_regions
                    break

            regions = new_regions

        return regions, plane_centers, plane_normals, error_history, iteration + 1


    def create_region_visualization(self, vertices: np.ndarray,
                                   faces: np.ndarray,
                                   regions: List[List[int]]) -> Tuple[
                                       Rhino.Geometry.Mesh,
                                       List[System.Drawing.Color]]:
        """
        Create colored mesh for region visualization.
        """
        colored_mesh = Rhino.Geometry.Mesh()

        # Add vertices
        for vertex in vertices:
            colored_mesh.Vertices.Add(float(vertex[0]), float(vertex[1]), float(vertex[2]))

        # Generate colors for regions
        colors = []
        np.random.seed(42)  # For consistent colors
        for i in range(len(regions)):
            r = int(np.random.randint(50, 255))
            g = int(np.random.randint(50, 255))
            b = int(np.random.randint(50, 255))
            colors.append(System.Drawing.Color.FromArgb(255, r, g, b))

        # Create face-to-region mapping
        face_to_region = {}
        for region_idx, region_faces in enumerate(regions):
            for face_idx in region_faces:
                face_to_region[face_idx] = region_idx

        # Add faces with colors
        for face_idx, face in enumerate(faces):
            if len(face) == 3:
                colored_mesh.Faces.AddFace(int(face[0]), int(face[1]), int(face[2]))

                # Set vertex colors based on region
                region_idx = face_to_region.get(face_idx, 0)
                color = colors[region_idx % len(colors)]

                for vertex_idx in face:
                    vertex_idx = int(vertex_idx)
                    while colored_mesh.VertexColors.Count <= vertex_idx:
                        colored_mesh.VertexColors.Add(
                            System.Drawing.Color.Gray)
                    colored_mesh.VertexColors[vertex_idx] = color

        colored_mesh.Normals.ComputeNormals()
        colored_mesh.Compact()

        return colored_mesh, colors

    def create_proxy_geometry(self, plane_centers: List[np.ndarray],
                             plane_normals: List[np.ndarray],
                             regions: List[List[int]], vertices: np.ndarray,
                             faces: np.ndarray) -> List[Rhino.Geometry.Plane]:
        """
        Create proxy planes for visualization.
        """
        proxy_planes = []

        for region_idx, (center, normal) in enumerate(zip(plane_centers,
                                                          plane_normals)):
            if not regions[region_idx]:
                continue

            # Create Rhino plane
            center_pt = Rhino.Geometry.Point3d(float(center[0]), float(center[1]), float(center[2]))
            normal_vec = Rhino.Geometry.Vector3d(float(normal[0]), float(normal[1]),
                                                float(normal[2]))

            # Find a reasonable size for the plane based on region extent
            region_vertices = []
            for face_idx in regions[region_idx]:
                face = faces[face_idx]
                for vertex_idx in face:
                    region_vertices.append(vertices[vertex_idx])

            plane = Rhino.Geometry.Plane(center_pt, normal_vec)
            proxy_planes.append(plane)

        return proxy_planes

    def RunScript(self,
            Mesh: Rhino.Geometry.Mesh,
            Mode: bool,
            Value: float,
            MaxIterations: int):
        """
        Run VSA algorithm.

        Inputs:
        - Mesh: Input mesh to approximate
        - Mode: True for fixed number of regions, False for threshold-based
        - Value: Number of regions (Mode=True) or error threshold (Mode=False)
        - MaxIterations: Maximum number of iterations
        """

        # Initialize param descriptions
        self.InputParams[0].Description = 'Input mesh to approximate using VSA'
        self.InputParams[1].Description = ('Mode: True for fixed number of '
                                          'regions, False for error threshold')
        self.InputParams[2].Description = ('Value: Number of regions '
                                          '(Mode=True) or L2,1 error threshold '
                                          '(Mode=False, try 0.001-0.01 for good results)')
        self.InputParams[3].Description = ('Maximum number of VSA iterations '
                                          '(default: 50)')

        # Initialize output param descriptions
        self.OutputParams[0].Description = ('Region visualization mesh with '
                                           'colored regions')
        self.OutputParams[1].Description = ('Proxy planes representing each '
                                           'region')
        self.OutputParams[2].Description = ('Error metrics: [final_error, '
                                           'initial_error, reduction_ratio]')
        self.OutputParams[3].Description = ('Statistics: [num_regions, '
                                           'iterations, convergence_info]')

        # Set up output variables
        RegionVisualization = None
        ProxyPlanes = []
        ErrorMetrics = []
        Statistics = []

        try:
            # Input validation
            if not Mesh or not Mesh.IsValid:
                self._addError('Please provide a valid mesh')
                self.Component.Message = 'Invalid mesh input'
                return (RegionVisualization, ProxyPlanes,
                       ErrorMetrics, Statistics)

            if Value is None or Value <= 0:
                self._addError('Value must be positive')
                self.Component.Message = 'Invalid value'
                return (RegionVisualization, ProxyPlanes,
                       ErrorMetrics, Statistics)

            if MaxIterations is None or MaxIterations <= 0:
                MaxIterations = 50

            # Determine mode
            mode_str = 'faces' if Mode else 'threshold'

            if mode_str == 'threshold' and Value < 0:
                self._addWarning('L2,1 error threshold should be positive. '
                                'Try values like 0.001-0.01 for good approximations.')

            self.Component.Message = f'Running VSA ({mode_str} mode)...'

            # Perform VSA
            (regions, plane_centers, plane_normals, error_history,
             iterations) = self.perform_vsa(
                Mesh, mode_str, Value, MaxIterations
            )

            if not regions:
                self._addError('VSA failed to create regions')
                self.Component.Message = 'VSA failed'
                return (RegionVisualization, ProxyPlanes,
                       ErrorMetrics, Statistics)

            # Extract mesh data for output creation
            vertices, faces, _, _ = self.extract_mesh_data(Mesh)

            # Create region visualization
            RegionVisualization, region_colors = (
                self.create_region_visualization(vertices, faces, regions)
            )

            # Create proxy planes
            ProxyPlanes = self.create_proxy_geometry(
                plane_centers, plane_normals, regions, vertices, faces
            )

            # Compute error metrics
            if error_history:
                final_error = error_history[-1]
                initial_error = (error_history[0] if len(error_history) > 1
                                else final_error)
                reduction_ratio = ((initial_error - final_error) /
                                  initial_error if initial_error > 0 else 0.0)
                ErrorMetrics = [final_error, initial_error, reduction_ratio]
            else:
                ErrorMetrics = [0.0, 0.0, 0.0]

            # Compute statistics
            num_regions = len(regions)
            convergence_info = (1.0 if iterations < MaxIterations else 0.0)
            Statistics = [num_regions, iterations, convergence_info]

            # Success message
            self.Component.Message = (f'VSA completed: {num_regions} regions, '
                                     f'{iterations} iterations')
            self._addRemark(f'VSA completed successfully with {num_regions} '
                           f'regions in {iterations} iterations')
            self._addRemark(f'Final error: {ErrorMetrics[0]:.6f}')

        except Exception as e:
            self._addError(f'VSA error: {str(e)}')
            self.Component.Message = f'Error: {str(e)}'

        return (RegionVisualization, ProxyPlanes, ErrorMetrics, Statistics)