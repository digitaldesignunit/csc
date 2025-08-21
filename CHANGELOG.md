# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0.5] - 2025-08-21

### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.5
- CSC Sheetscan Module: 0.0.1.11

### Added

#### CSC React Frontend

- Added responsive mobile navigation with burger menu
- Added mobile UserItem display in header
- Improved header design with better typography and spacing

### Changed

#### CSC React Frontend

- Redesigned header for better mobile and desktop experience
- Implemented collapsible mobile navigation menu
- Moved theme toggle to header for better accessibility
- Added smooth animations for mobile menu transitions
- Mobile menu automatically closes after navigation

## [0.2.0.4] - 2025-08-21

### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.4
- CSC Sheetscan Module: 0.0.1.11

### Fixed

#### CSC React Frontend

- Fixed sidebar menu hover behavior - buttons no longer stay "selected" after hovering
- Replaced Command components with proper navigation items for better UX
- Maintained card-like visual appearance while fixing persistent selection states

## [0.2.0.3] - 2025-08-21

### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.3
- CSC Sheetscan Module: 0.0.1.11

### Fixed

#### CSC React Frontend

- Fixed missing role field in user registration API - now automatically sets role to 'user' for new registrations
- Fixed Access card visibility on home page - now hidden when user is logged in

## [0.2.0.2] - 2025-08-20

### Versions

- CSC FastAPI Backend:  0.2.1.0
- CSC React Frontend:   0.2.0.2
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC React Frontend

- Changed routes to adapt to new preview image fetch method
- Ensure that prod builds locally without errors

## [0.2.0.2] - 2025-08-20

### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.1
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Add preview image route

## [0.2.0.1] - 2025-08-20

### Versions

- CSC FastAPI Backend:  0.2.1.0
- CSC React Frontend:   0.2.0.1
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC React Frontend

- Now builds in production mode

## [0.2.0.0] - 2025-08-19

### Versions

- CSC FastAPI Backend:  0.2.1.0
- CSC React Frontend:   0.2.0.0
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- First stable version with new and revamped backend

#### CSC React Frontend

- Completely revamped NextJS app using NextJS 15, builds in development mode
- Production build still failing

## [0.0.1.20] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.12
- CSC React Frontend:   0.1.4.18
- CSC Sheetscan Module: 0.0.1.11

### Added

#### CSC React Frontend

- Added BoundingBox display option

### Changed

#### CSC React Frontend

- Modified ComponentViewer interface to be an overlay on top of the 3d canvas

## [0.0.1.19] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.12
- CSC React Frontend:   0.1.4.17
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Modified componentcount route to work with a filter query (we will need this for correct pagination in frontend)

#### CSC React Frontend

- Reoriented all Rubble meshes according to PCA
- Recomputed primitive geometry with 300 faces
- Updated database, component geometry, component previews

## [0.0.1.18] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.10
- CSC React Frontend:   0.1.4.16
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Added material filter to components and shallowcomponents route

#### CSC React Frontend

- Added functionality to filter for materials and component types

## [0.0.1.17] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.9
- CSC React Frontend:   0.1.4.15
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Added routes to fetch detailed geometry, reduced mesh geometry, material and textures

#### CSC React Frontend

- Updated detailed and reduced geometry routing to fetch geometry using backend API

## [0.0.1.16] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.8
- CSC React Frontend:   0.1.4.14
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC React Frontend

- Fixed Tailwinds

## [0.0.1.15] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.8
- CSC React Frontend:   0.1.4.13
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC React Frontend

- Updated ComponentDetail display

## [0.0.1.14] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.8
- CSC React Frontend:   0.1.4.12
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Removed Materialthickness

#### CSC React Frontend

- Removed Materialthickness and adapted everything to use BBX extents

## [0.0.1.13] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.7
- CSC React Frontend:   0.1.4.11
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC React Frontend

- Updated ComponentViewer component to be able to display more detailed meshes on request

## [0.0.1.12] - 2024-12-14

### Versions

- CSC FastAPI Backend:  0.1.0.7
- CSC React Frontend:   0.1.4.10
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Modified component spec to enable SAS rubble imports

#### CSC React Frontend

- Modified Component Model and implementation to reflect changes in component spec

## [0.0.1.11] - 2024-10-23

### Versions

- CSC FastAPI Backend:  0.1.0.6
- CSC React Frontend:   0.1.4.9
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC React Frontend

- Added possibility to pre-set reference id in `frontend/components/ComponentLookup.tsx`
- Added possibility to pre-set reference id in `frontend/app/findcomponent/page.tsx`
- Added link to find component with pre-set reference id in `frontend/components/ComponentSheet.tsx`
- Added link to find component with pre-set reference id in `frontend/app/components/[component_id]/page.tsx`

## [0.0.1.10] - 2024-10-07

### Versions

- CSC FastAPI Backend:  0.1.0.6
- CSC React Frontend:   0.1.4.8
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Corrected docstring of single component fetch route

#### CSC React Frontend

- Added `components/[component_id]` API route to retrieve single component data
- Added working ComponentDetailPage (`frontend/app/components/[component_id]/page.tsx`)
- Modified `ComponentSheet` to link to component details page

## [0.0.1.9] - 2024-10-02

### Versions

- CSC FastAPI Backend:  0.1.0.5
- CSC React Frontend:   0.1.4.7
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC React Frontend

- Added proper imprint
- Fixed npm vulns

## [0.0.1.9] - 2024-06-21

### Versions

- CSC FastAPI Backend:  0.1.0.5
- CSC React Frontend:   0.1.4.6
- CSC Sheetscan Module: 0.0.1.11

### Changed

#### CSC FastAPI Backend

- Changed Component model to reflect current location as attribute

#### CSC React Frontend

- Extended DataTable for Components with location attribute

#### CSC Sheetscan Module

- Extended BaseModel & SheetModel with location

## [0.0.1.8] - 2024-06-12

### Versions

- CSC FastAPI Backend:  0.1.0.4
- CSC React Frontend:   0.1.4.5
- CSC Sheetscan Module: 0.0.1.10

### Changed

#### CSC React Frontend

- Extended DataTable for Components

## [0.0.1.7] - 2024-06-12

### Versions

- CSC FastAPI Backend:  0.1.0.4
- CSC React Frontend:   0.1.4.4
- CSC Sheetscan Module: 0.0.1.10

### Changed

#### CSC FastAPI Backend

- Fixed color definition in ComponentModel in `models.py`

#### CSC React Frontend

- Adapted table layout for component overview

## [0.0.1.6] - 2024-06-06

### Versions

- CSC FastAPI Backend:  0.1.0.3
- CSC React Frontend:   0.1.4.3
- CSC Sheetscan Module: 0.0.1.10

### Added

#### CSC FastAPI Backend

- Added preview generation routine

### Changed

#### CSC FastAPI Backend

- Moved database connection functions to `utility` module

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