# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1.1] - 2024-05-23

### Versions

- CSC FastAPI Backend:  0.1.0.0
- CSC React Frontend:   0.1.4.0
- CSC Sheetscan Module: 0.0.1.10

### Fixed

#### CSC React Frontend

- Fixed Caching (hopefully)

### Added

- Initiated `CHANGELOG.md`

## [0.0.1.2] - 2024-05-24

### Versions

- CSC FastAPI Backend:  0.1.0.1
- CSC React Frontend:   0.1.4.1
- CSC Sheetscan Module: 0.0.1.10

### Fixed

#### CSC FastAPI Backend

- Updated `ComponentModel` in `models.py`
- Fixed response models in `routers.py`

#### CSC React Frontend

- Fixed timestamp printing in console

### Added

#### CSC React Frontend

- Added `timestamp_string` function to `lib/utils.ts`

## [0.0.1.3] - 2024-05-24

### Versions

- CSC FastAPI Backend:  0.1.0.1
- CSC React Frontend:   0.1.4.2
- CSC Sheetscan Module: 0.0.1.10

### Changed

#### CSC React Frontend

- Reformatted layout to incorporate Footer.
- Started reformatting of Component Overview DataTable

### Added

#### CSC React Frontend

- Added Credits Page `app/credits/page.tsx`
- Added Footer Component `components/Footer.tsx`
- Added Function `copyright_date` to `lib/utils.ts`

## [0.0.1.4] - 2024-06-04

### Versions

- CSC FastAPI Backend:  0.1.0.2
- CSC React Frontend:   0.1.4.2
- CSC Sheetscan Module: 0.0.1.10

### Added

#### CSC React Frontend

- Added lazy loading of components
- Added `fetch-components-shallow` route to API
- Added `fetch-component-geometry` route to API

#### CSC FastAPI Backend:

- Added API endpoints for retrieving component geometry and shallow components without geometry

### Changed

#### CSC React Frontend

- Components in the overview are now retrieved _shallow_, e.g. without geometry.
- Geometry is loaded on click during opening of the Component Detail Sheet.

## [0.0.1.5] - 2024-06-04

### Versions

- CSC FastAPI Backend:  0.1.0.2
- CSC React Frontend:   0.1.4.3
- CSC Sheetscan Module: 0.0.1.10

### Added

#### CSC React Frontend

- Add `ComponentViewerSkeleton.tsx` to display loading message during geometry load.

### Changed

#### CSC React Frontend

- Fix linting in all components.
- Change Sidebar width to `250px`