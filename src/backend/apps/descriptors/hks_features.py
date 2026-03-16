#!/usr/bin/env python3.9
"""
HKS (Heat Kernel Signature) with robust_laplacian for scale-invariant
shape descriptors.

Key idea:
  HKS(x, t) = sum_i exp(-lambda_i * t) * phi_i(x)^2

We compute eigenpairs of the generalized Laplacian:
  L phi_i = lambda_i M phi_i
where L is a cotangent-like Laplacian and M is a (diagonal) mass matrix.

Scale invariance strategy:
  1. Rescale eigenvalues by shape scale s^2 (total area/mass)
  2. Use time grid derived in scaled units
  3. L1-normalize per-vertex HKS across time
  4. L2-normalize the pooled descriptor vector

Mass-weighted pooling reduces sensitivity to non-uniform sampling density.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as sla
import robust_laplacian
import trimesh


# FUNCTION DEFINITIONS --------------------------------------------------------

def load_mesh_from_ply(
    filepath: str,
    clean_mesh: bool = False
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load a triangle mesh from a PLY file.

    Args:
        filepath: path to .ply file

    Returns:
        verts: (V, 3) float array of vertex positions
        faces: (F, 3) int array of triangle indices

    Raises:
        FileNotFoundError: if file doesn't exist
        ValueError: if file is not a valid triangle mesh
    """
    try:
        mesh = trimesh.load(filepath)
        if clean_mesh:
            # 3. Remove duplicate faces
            trimesh.repair.fix_inversion(mesh)
            # 5. Fix normals (if needed)
            trimesh.repair.fix_normals(mesh)
            # 6. Fill holes (optional - makes watertight)
            # trimesh.repair.fill_holes(mesh)
    except FileNotFoundError:
        raise FileNotFoundError(f'PLY file not found: {filepath}')
    except Exception as e:
        raise ValueError(f'Failed to load PLY file {filepath}: {e}')

    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(
            f'File {filepath} is not a triangle mesh. '
            f'Got type: {type(mesh)}'
        )

    verts = np.array(mesh.vertices, dtype=np.float64)
    faces = np.array(mesh.faces, dtype=np.int32)

    if len(verts) == 0:
        raise ValueError(f'Mesh has no vertices: {filepath}')
    if len(faces) == 0:
        raise ValueError(f'Mesh has no faces: {filepath}')

    return verts, faces


def build_laplacian_from_mesh(
    verts: np.ndarray,
    faces: np.ndarray,
    mollify_factor: float = 1e-5
) -> Tuple[sp.csr_matrix, sp.csr_matrix]:
    """
    Build Laplacian and mass matrix from a triangle mesh.

    Args:
        verts: (V, 3) float array of vertex positions
        faces: (F, 3) int array of triangle indices
        mollify_factor: regularization factor for numerical stability

    Returns:
        L: sparse (V, V) positive semidefinite Laplacian
        M: sparse (V, V) diagonal mass matrix (area weights)

    Raises:
        ValueError: if input shapes are invalid
    """
    if verts.ndim != 2 or verts.shape[1] != 3:
        raise ValueError(f'verts must be (V, 3), got {verts.shape}')
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError(f'faces must be (F, 3), got {faces.shape}')
    if len(verts) < 3:
        raise ValueError(
            f'mesh must have at least 3 vertices, got {len(verts)}'
        )
    if len(faces) < 1:
        raise ValueError(
            f'mesh must have at least 1 face, got {len(faces)}'
        )

    L, M = robust_laplacian.mesh_laplacian(
        verts, faces, mollify_factor=mollify_factor
    )
    return L, M


def build_laplacian_from_points(
    points: np.ndarray,
    mollify_factor: float = 1e-5,
    n_neighbors: int = 30
) -> Tuple[sp.csr_matrix, sp.csr_matrix]:
    """
    Build Laplacian and mass matrix from a point cloud.

    Args:
        points: (V, 3) float array of point positions
        mollify_factor: regularization factor for numerical stability
        n_neighbors: number of neighbors for local geometry estimation

    Returns:
        L: sparse (V, V) positive semidefinite Laplacian
        M: sparse (V, V) diagonal mass matrix

    Raises:
        ValueError: if input shapes are invalid
    """
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f'points must be (V, 3), got {points.shape}')
    if len(points) < n_neighbors:
        raise ValueError(
            f'point cloud must have at least {n_neighbors} points, '
            f'got {len(points)}'
        )

    L, M = robust_laplacian.point_cloud_laplacian(
        points, mollify_factor=mollify_factor, n_neighbors=n_neighbors
    )
    return L, M


def lap_eigendecomp(
    L: sp.csr_matrix,
    M: sp.csr_matrix,
    n_eigs: int = 128,
    sigma: float = 1e-8,
    tol: float = 0.0,
    max_disconnected: int = 10
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Solve L phi = lambda M phi for the smallest eigenpairs.

    Uses shift-invert mode near 0 to extract low-frequency modes.
    Automatically detects and skips near-zero eigenvalues from
    disconnected components.

    Args:
        L: sparse (V, V) Laplacian matrix
        M: sparse (V, V) mass matrix
        n_eigs: number of non-zero eigenvalues to compute
        sigma: shift-invert parameter for eigenvalue solver
        tol: convergence tolerance (0 = machine precision)
        max_disconnected: maximum number of near-zero eigenvalues to skip

    Returns:
        evals: (n_eigs,) positive eigenvalues, ascending order
        evecs: (V, n_eigs) M-orthonormal eigenvectors (columns)

    Raises:
        ValueError: if input matrices are incompatible or too small
        RuntimeError: if eigenvalue decomposition fails to converge
    """
    if L.shape[0] != L.shape[1]:
        raise ValueError(f'L must be square, got {L.shape}')
    if M.shape != L.shape:
        raise ValueError(
            f'M shape {M.shape} must match L shape {L.shape}'
        )
    if n_eigs >= L.shape[0] - 1:
        raise ValueError(
            f'n_eigs={n_eigs} must be < V-1={L.shape[0]-1}'
        )

    # Request extra eigenvalues to account for potential near-zero modes
    k = min(n_eigs + max_disconnected, L.shape[0] - 2)

    try:
        evals, evecs = sla.eigsh(L, k=k, M=M, sigma=sigma, tol=tol)
    except sla.ArpackNoConvergence as e:
        raise RuntimeError(f'Eigendecomposition failed to converge: {e}')

    # Skip near-zero eigenvalues (constant modes or disconnected parts)
    zero_threshold = 1e-8
    nonzero_mask = evals > zero_threshold
    n_zeros = (~nonzero_mask).sum()

    if n_zeros > max_disconnected:
        raise ValueError(
            f'Found {n_zeros} near-zero eigenvalues, expected at most '
            f'{max_disconnected}. Shape may be severely disconnected.'
        )

    evals_clean = evals[nonzero_mask]
    evecs_clean = evecs[:, nonzero_mask]

    # Return requested number of eigenvalues
    if len(evals_clean) < n_eigs:
        raise ValueError(
            f'Only {len(evals_clean)} non-zero eigenvalues available, '
            f'requested {n_eigs}. Try reducing n_eigs.'
        )

    # Check for negative eigenvalues (numerically shouldn't occur)
    if np.any(evals_clean[:n_eigs] < 0):
        n_negative = (evals_clean[:n_eigs] < 0).sum()
        raise ValueError(
            f'Found {n_negative} negative eigenvalues. '
            f'Laplacian may not be properly constructed.'
        )

    return evals_clean[:n_eigs], evecs_clean[:, :n_eigs]


def make_time_grid(
    evals: np.ndarray,
    M_diag: np.ndarray,
    n_times: int = 16,
    tmin_factor: float = 4.0,
    tmax_factor: float = 4.0
) -> np.ndarray:
    """
    Build a scale-invariant time grid from eigenvalues.

    Usage:
      - Reference-based: Compute once from a reference shape, reuse for
        all shapes in dataset (more consistent)
      - Per-shape: Compute fresh time grid for each shape (simpler,
        fully adaptive)

    Time bounds are chosen based on the resolved spectrum:
      t_min ~ tmin_factor / lambda_max
      t_max ~ tmax_factor / lambda_1

    Args:
        evals: (K,) eigenvalues
        M_diag: (V,) diagonal of mass matrix
        n_times: number of time samples
        tmin_factor: factor for minimum time (higher = shorter diffusion)
        tmax_factor: factor for maximum time (higher = longer diffusion)

    Returns:
        times: (n_times,) log-spaced time values

    Raises:
        ValueError: if inputs are invalid
    """
    if len(evals) == 0:
        raise ValueError('evals cannot be empty')
    if len(M_diag) == 0:
        raise ValueError('M_diag cannot be empty')
    if n_times < 1:
        raise ValueError(f'n_times must be >= 1, got {n_times}')

    # Scale eigenvalues by s^2 where s ~ sqrt(total area/mass)
    s2 = np.sum(M_diag)
    if s2 <= 0:
        raise ValueError(f'Total mass must be positive, got {s2}')

    lam_scaled = evals * s2

    lam1 = lam_scaled[0]
    lam_max = lam_scaled[-1]

    t_min = tmin_factor / max(lam_max, 1e-12)
    t_max = tmax_factor / max(lam1, 1e-12)

    if t_min >= t_max:
        raise ValueError(f't_min={t_min} must be < t_max={t_max}')

    times = np.logspace(np.log10(t_min), np.log10(t_max), n_times)
    return times


def hks_from_eigendecomp(
    evals: np.ndarray,
    evecs: np.ndarray,
    times: np.ndarray,
    M_diag: np.ndarray,
    epsilon: float = 1e-15
) -> np.ndarray:
    """
    Compute scale-invariant per-vertex HKS for the given time grid.

    Steps:
      1. Scale eigenvalues by s^2 (total area/mass)
      2. Compute HKS(x, t) = sum_i exp(-lambda_i t) * phi_i(x)^2
      3. L1-normalize each vertex's HKS across time

    The eigenvectors from eigsh are already M-orthonormal, so we use
    them directly.

    Args:
        evals: (K,) eigenvalues
        evecs: (V, K) M-orthonormal eigenvectors
        times: (T,) time samples
        M_diag: (V,) diagonal of mass matrix
        epsilon: small value to prevent division by zero

    Returns:
        H: (V, T) scale-invariant per-vertex HKS

    Raises:
        ValueError: if input shapes are incompatible
    """
    if evecs.shape[1] != len(evals):
        raise ValueError(
            f'evecs has {evecs.shape[1]} columns, '
            f'evals has {len(evals)} entries'
        )
    if evecs.shape[0] != len(M_diag):
        raise ValueError(
            f'evecs has {evecs.shape[0]} rows, '
            f'M_diag has {len(M_diag)} entries'
        )

    # Scale eigenvalues by s^2
    s2 = np.sum(M_diag)
    if s2 <= 0:
        raise ValueError(f'Total mass must be positive, got {s2}')

    lam_scaled = evals * s2

    # Compute HKS for each time
    phi2 = evecs ** 2

    # Clamp exponent argument to prevent underflow
    exp_arg = -np.outer(lam_scaled, times)
    # exp(-700) ~ 0, exp(700) ~ inf
    exp_arg = np.clip(exp_arg, -700, 700)
    exp_cache = np.exp(exp_arg)  # shape (K, T)

    H = phi2 @ exp_cache  # shape (V, T)

    # L1-normalize each vertex's HKS curve for scale invariance
    row_sums = H.sum(axis=1, keepdims=True)
    if np.any(row_sums <= epsilon):
        raise ValueError('Some vertices have zero or negative HKS sum')

    H = H / (row_sums + epsilon)

    return H


def pool_hks(
    H: np.ndarray,
    M_diag: np.ndarray,
    epsilon: float = 1e-15
) -> np.ndarray:
    """
    Pool per-vertex HKS to a fixed-length scale-invariant shape descriptor.

    Uses mass-weighted mean and variance, then L2-normalizes the result.

    Args:
        H: (V, T) per-vertex HKS
        M_diag: (V,) diagonal of mass matrix
        epsilon: small value to prevent division by zero

    Returns:
        descriptor: (2*T,) L2-normalized descriptor [mean, variance]

    Raises:
        ValueError: if input shapes are incompatible
    """
    if H.shape[0] != len(M_diag):
        raise ValueError(
            f'H has {H.shape[0]} rows, '
            f'M_diag has {len(M_diag)} entries'
        )

    # Normalize weights to sum to 1
    total_mass = np.sum(M_diag)
    if total_mass <= 0:
        raise ValueError(f'Total mass must be positive, got {total_mass}')

    weights = M_diag / (total_mass + epsilon)

    # Mass-weighted mean
    mu = (weights[:, None] * H).sum(axis=0)

    # Mass-weighted variance
    diff = H - mu[None, :]
    var = (weights[:, None] * diff * diff).sum(axis=0)

    # Concatenate mean and variance
    descriptor = np.concatenate([mu, var])

    # L2-normalize for comparable magnitudes across shapes
    norm = np.linalg.norm(descriptor)
    if norm <= epsilon:
        raise ValueError('Descriptor has zero or near-zero norm')

    descriptor = descriptor / (norm + epsilon)

    return descriptor


def visualize_descriptor_values(descriptors: np.ndarray, shape_indices=[0, 1]):
    """
    Plot descriptor values for specific shapes.

    Args:
        descriptors: (N, D) array where N is number of shapes,
        D is descriptor dimension (n_times * 2)
        shape_indices: which shapes to plot (list of integers)
    """
    import matplotlib.pyplot as plt

    # Validate inputs
    if descriptors.ndim == 1:
        # Single descriptor - reshape to (1, D)
        descriptors = descriptors.reshape(1, -1)
        print(f'Reshaped single descriptor to {descriptors.shape}')

    print(f'Descriptors shape: {descriptors.shape}')
    print(f'Shape indices: {shape_indices}')

    N, D = descriptors.shape

    # Validate indices
    for idx in shape_indices:
        if idx >= N:
            raise ValueError(f'Index {idx} out of range for {N} shapes')

    if D % 2 != 0:
        raise ValueError(
            f'Descriptor dimension {D} should be even (mean + variance)'
        )

    n_times = D // 2

    fig, axes = plt.subplots(
        len(shape_indices), 1, figsize=(12, 4*len(shape_indices))
    )
    if len(shape_indices) == 1:
        axes = [axes]

    for i, idx in enumerate(shape_indices):
        desc = descriptors[idx]
        mean_part = desc[:n_times]
        var_part = desc[n_times:]

        x = np.arange(n_times)
        axes[i].bar(x - 0.2, mean_part, width=0.4, label='Mean', alpha=0.7)
        axes[i].bar(x + 0.2, var_part, width=0.4, label='Variance', alpha=0.7)
        # write values to bars
        for j, val in enumerate(mean_part):
            axes[i].text(
                x[j] - 0.2,
                val,
                f'{val:.2f}',
                ha='center',
                va='bottom')
        for j, val in enumerate(var_part):
            axes[i].text(
                x[j] + 0.2,
                val,
                f'{val:.2f}',
                ha='center',
                va='bottom')
        axes[i].set_title(f'Shape {idx} HKS Descriptor')
        axes[i].set_xlabel('Time Index')
        axes[i].set_ylabel('Value (L2-normalized)')
        axes[i].legend()
        axes[i].grid(alpha=0.3)

    plt.tight_layout()
    plt.show()


def compute_pooled_hks_for_mesh(
    V: np.ndarray,
    F: np.ndarray,
    n_eigs: int = 64,
    n_times: int = 16
) -> np.ndarray:
    """
    Compute HKS for a mesh with the given number of eigenvalues and time steps.

    Args:
        V: (V, 3) float array of vertex positions
        F: (F, 3) int array of triangle indices
        n_eigs: number of eigenvalues to compute
        n_times: number of time steps

    Returns:
        pooled_H: (2*n_times,) float array of pooled HKS values
    """
    if V.ndim != 2 or V.shape[1] != 3:
        raise ValueError(f'V must be (V, 3), got {V.shape}')
    if F.ndim != 2 or F.shape[1] != 3:
        raise ValueError(f'F must be (F, 3), got {F.shape}')

    if len(V) < 3:
        raise ValueError(f'Mesh must have at least 3 vertices, got {len(V)}')
    if len(F) < 1:
        raise ValueError(f'Mesh must have at least 1 face, got {len(F)}')

    try:
        L, M = build_laplacian_from_mesh(V, F)
        evals, evecs = lap_eigendecomp(L, M, n_eigs=n_eigs)
        times = make_time_grid(evals, M_diag=M.diagonal(), n_times=n_times)
        H = hks_from_eigendecomp(evals, evecs, times, M_diag=M.diagonal())
        pooled_H = pool_hks(H, M_diag=M.diagonal())
        return pooled_H
    except Exception as e:
        print(f'Error: {e}')
        return None


def compute_simple_pooled_hks_for_mesh(
    V: np.ndarray,
    F: np.ndarray
) -> np.ndarray:
    """
    Compute simple HKS for a mesh with 64 eigenvalues and 16 time steps.

    Args:
        V: (V, 3) float array of vertex positions
        F: (F, 3) int array of triangle indices

    Returns:
        pooled_H: (2*16,) float array of pooled HKS values
    """
    return compute_pooled_hks_for_mesh(V, F, n_eigs=64, n_times=16)


def compute_simple_pooled_hks_for_trimesh(
    mesh: trimesh.Trimesh
) -> np.ndarray:
    """
    Compute simple HKS for a trimesh mesh with 64 eigenvalues and 16 time
    steps.
    """
    return compute_simple_pooled_hks_for_mesh(
        np.array(mesh.vertices),
        np.array(mesh.faces)
    )


def compute_simple_pooled_hks_on_convex_hull_trimesh(
    mesh: trimesh.Trimesh
) -> np.ndarray:
    """
    Compute simple HKS for a trimesh mesh on its convex hull with
    64 eigenvalues and 16 time steps.
    """
    cvh = mesh.convex_hull
    return compute_simple_pooled_hks_for_mesh(
        np.array(cvh.vertices),
        np.array(cvh.faces)
    )


def compute_moderate_pooled_hks_for_mesh(
    V: np.ndarray,
    F: np.ndarray
) -> np.ndarray:
    """
    Compute moderate HKS for a mesh with 64 eigenvalues and 32 time steps.

    Args:
        V: (V, 3) float array of vertex positions
        F: (F, 3) int array of triangle indices

    Returns:
        pooled_H: (2*32,) float array of pooled HKS values
    """
    return compute_pooled_hks_for_mesh(V, F, n_eigs=64, n_times=32)


def compute_moderate_pooled_hks_for_trimesh(
    mesh: trimesh.Trimesh
) -> np.ndarray:
    """
    Compute moderate HKS for a trimesh mesh with 64 eigenvalues and 32 time
    steps.
    """
    return compute_moderate_pooled_hks_for_mesh(
        np.array(mesh.vertices),
        np.array(mesh.faces)
    )


def compute_moderate_pooled_hks_for_convex_hull_trimesh(
    mesh: trimesh.Trimesh
) -> np.ndarray:
    """
    Compute moderate HKS for a trimesh mesh on its convex hull
    with 64 eigenvalues and 32 time steps.
    """
    cvh = mesh.convex_hull
    return compute_moderate_pooled_hks_for_mesh(
        np.array(cvh.vertices),
        np.array(cvh.faces)
    )


def compute_detailed_pooled_hks_for_mesh(
    V: np.ndarray,
    F: np.ndarray
) -> np.ndarray:
    """
    Compute detailed HKS for a mesh with 128 eigenvalues and 64 time steps.

    Args:
        V: (V, 3) float array of vertex positions
        F: (F, 3) int array of triangle indices

    Returns:
        pooled_H: (2*64,) float array of pooled HKS values
    """
    return compute_pooled_hks_for_mesh(V, F, n_eigs=128, n_times=64)


def compute_detailed_pooled_hks_for_trimesh(
    mesh: trimesh.Trimesh
) -> np.ndarray:
    """
    Compute detailed HKS for a trimesh mesh with 128 eigenvalues and 64 time
    steps.
    """
    return compute_detailed_pooled_hks_for_mesh(
        np.array(mesh.vertices),
        np.array(mesh.faces)
    )


def compute_detailed_pooled_hks_for_convex_hull_trimesh(
    mesh: trimesh.Trimesh
) -> np.ndarray:
    """
    Compute detailed HKS for a trimesh mesh on its convex hull
    with 128 eigenvalues and 64 time steps.
    """
    cvh = mesh.convex_hull
    return compute_detailed_pooled_hks_for_mesh(
        np.array(cvh.vertices),
        np.array(cvh.faces)
    )
