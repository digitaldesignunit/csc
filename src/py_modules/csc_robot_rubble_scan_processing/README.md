# Robot Rubble Scan Processing

Processes aligned 3D scan meshes into a CSC identity plus version-0 snapshot,
then optionally uploads them to the catalog API.

The UUID folder name becomes the identity `_id`. Geometry stays in the
scan's marker-plane frame (no extra centering). PCA is computed on the
rubble mesh only and stored as `pca_frame`. Vertex colors are baked from
the OBJ diffuse texture (`map_Kd`, typically `mesh.jpg`).

## Setup

1. Install dependencies:
```bash
pip install numpy trimesh scipy pillow requests
```

2. Create credentials file:
```bash
cp csc_credentials.json.example csc_credentials.json
# Edit with your API credentials
```

```json
{
  "server": "https://api.2ndchances.build",
  "user": "your-username",
  "pwd": "your-password"
}
```

## Scan folder layout

```
<uuid>/
  metadata.json
  output/
    mesh.obj          # aligned mesh (Rhino Z-up): object, end_effector,
                      # marker_blue_*, marker_green_x
    mesh.jpg          # diffuse texture (vertex colors baked from this)
  transcode/          # written by process_robot_scan.py
    <uuid>.json       # CreateComponentRequest (POST /identities)
    ply_manifest.json
    meshes/<i>/detailed.ply
    meshes/<i>/reduced.ply
```

Legacy `output/aligned_mesh.obj` (Y-up) is still accepted and converted.

## Usage

### Programmatic Interface

```python
# Process only
from process_robot_scan import process_scan_by_path
success = process_scan_by_path('/path/to/uuid-folder')

# Upload only
from upload_robot_scan import load_credentials, upload_scan_by_path
credentials = load_credentials('csc_credentials.json')
success = upload_scan_by_path('/path/to/uuid-folder', credentials)

# Process and upload
from process_and_upload_scan import main
main('/path/to/uuid-folder')
```

### Command Line (Testing)

```bash
# Process
python process_robot_scan.py /path/to/uuid-folder

# Upload
python upload_robot_scan.py /path/to/uuid-folder [credentials_file]

# Process and upload
python process_and_upload_scan.py /path/to/uuid-folder [credentials_file]
```
