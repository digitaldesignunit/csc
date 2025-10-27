# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1.3] - 2025-10-09

### Versions

- CSC FastAPI Backend:  0.4.0.0
- CSC React Frontend:   0.4.0.0
- CSC Grasshopper Interface: 0.4.0.0

### Added

#### CSC React Frontend

- **BackgroundMesh**: Animated mesh on some pages as background.
- **Theme Toggle**: Switch between light, dark, and system.

### Changed

#### CSC React Frontend

- **Input Placeholders**: Improved registration form placeholders.

## [0.3.1.2] - 2025-10-07

### Versions

- CSC FastAPI Backend:  0.3.1.0
- CSC React Frontend:   0.3.1.1
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.1

### Added

#### CSC React Frontend

- **Cookie Notice**: Added a cookie notice banner that informs users about the use of technically necessary cookies only. Users can accept or dismiss the notice, and their choice is remembered in local storage.
- **Cookie Settings Page**: Introduced a "Cookie Settings" section in the settings page, allowing users to review cookie usage and re-display the cookie notice if desired.

### Changed

#### CSC React Frontend

- **Session Handling Update**: Improved session state management .


## [0.3.1.1] - 2025-09-11

### Versions

- CSC FastAPI Backend:  0.3.1.0
- CSC React Frontend:   0.3.1.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.1

### Added

#### CSC Grasshopper Interface
- **Binary Geometry Caching**: Implemented high-performance binary caching for geometry data using Rhino's JSON serialization
- **JSON Mesh Serialization**: Added support for serializing Rhino meshes to JSON with full user data preservation
- **Enhanced Error Handling**: Improved error handling for mesh reconstruction and geometry processing
- **Cache Validation**: Added comprehensive validation for cached geometry data before use

### Changed

#### CSC Grasshopper Interface
- **Cache Storage Format**: Migrated from OBJ text files to pickled JSON strings for maximum performance
- **Mesh Processing**: Optimized mesh duplication and transformation for cached geometry baking
- **Error Recovery**: Enhanced error recovery to continue processing when individual meshes fail
- **Debug Output**: Cleaned up excessive debug logging while preserving important status messages

### Fixed

#### CSC Grasshopper Interface
- **BakeComponents Error**: Fixed "does not exist in ObjectTable" error when baking cached geometry
- **Mesh Reconstruction**: Fixed issues with reconstructing meshes from JSON when some meshes fail
- **Cache Validation**: Fixed validation logic to properly handle empty or invalid cached data
- **Cross-Component Imports**: Removed circular import dependencies between Grasshopper components

### Technical Details

#### Binary Caching Implementation
- Uses `Rhino.Geometry.Mesh.ToJSON()` with `SerializationOptions` for full data preservation
- Stores pickled JSON strings instead of raw mesh objects for pickle compatibility
- Implements `Rhino.Geometry.Mesh.FromJSON()` for mesh reconstruction
- Maintains ETag compatibility with existing caching system

#### Performance Improvements
- Eliminated OBJ parsing overhead for cached geometry
- Reduced file I/O operations through binary storage
- Improved mesh processing with bulk operations
- Enhanced error handling prevents cascade failures

## [0.3.1.0] - 2025-09-09

### Versions

- CSC FastAPI Backend:  0.3.1.0
- CSC React Frontend:   0.3.1.0
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.0

### Added

#### CSC FastAPI Backend
- **Geometry ETag Support**: Added ETag generation and conditional request support for geometry endpoints
- **HTTP Caching Headers**: Added Cache-Control headers for improved geometry file caching
- **Conditional Requests**: Support for If-None-Match headers with 304 Not Modified responses
- **File-based ETags**: ETag generation based on file modification time and size for reliable cache validation

#### CSC React Frontend
- **Geometry ETag Caching**: Enhanced ComponentViewer with ETag-based conditional requests for geometry files
- **Smart Cache Validation**: Automatic cache validation using ETag headers to avoid unnecessary re-downloads
- **Improved Performance**: Reduced bandwidth usage and faster loading for cached geometry files

### Changed

#### CSC FastAPI Backend
- **Geometry Endpoints**: Enhanced `/components/{id}/geometry_detailed` and `/components/{id}/geometry_reduced` with ETag support
- **Backward Compatibility**: All changes are additive and maintain full backward compatibility with existing clients

#### CSC React Frontend
- **Component Validation UI**: Updated Validate button to only be active for unvalidated components
- **Enhanced User Feedback**: Dynamic button text and tooltips based on component validation status
- **Geometry Cache Structure**: Enhanced cache to store ETag metadata alongside geometry data

## [0.3.0.0] - 2025-09-05

### Versions

- CSC FastAPI Backend:  0.3.0.0 ✨
- CSC React Frontend:   0.3.0.0 ✨
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.2.0.0 ✨

### Added

#### CSC FastAPI Backend
- **Multi-Mesh Support**: Added `meshes` field to `ComponentGeometry` model for supporting multiple meshes per component
- **Marker Points Field**: Added `marker_points` field to `ComponentModel` for storing coordinate triplets
- **OBJ-Only Geometry**: Updated geometry endpoints to support OBJ files with embedded vertex colors only
- **Database Migration Scripts**: Created comprehensive migration scripts for multi-mesh and field format updates
- **Schema Validation**: Enhanced component validation with proper field type checking and format validation

#### CSC React Frontend
- **Multi-Mesh Visualization**: Complete support for displaying multiple meshes in ComponentViewer
- **Vertex Color Support**: Full support for `v X Y Z R G B` vertex colors in OBJ files with smart normalization
- **Mesh Visibility Controls**: Individual checkbox controls to show/hide specific meshes in primitive mode
- **Manual OBJ Parsing**: Custom OBJ parser for reliable vertex color extraction and face triangulation
- **Smart Color Normalization**: Automatic detection and conversion of 0-255 to 0-1 color ranges
- **Consistent Geometry Display**: Unified positioning and scaling across primitive, reduced, and detailed modes

#### CSC Grasshopper Interface
- **Multi-Mesh Input Support**: All components now accept `List[Rhino.Geometry.GeometryBase]` for single or multiple meshes
- **OBJ File Generation**: Enhanced OBJ export with proper object declarations (`o object_0`, `o object_1`, etc.)
- **Vertex Color Embedding**: Automatic embedding of vertex colors in OBJ files using `v X Y Z R G B` format
- **PCA Assembly Processing**: New method for computing PCA on entire multi-mesh assemblies with proper centering
- **Coordinate System Mapping**: Correct Rhino (X,Y,Z) to OBJ (X,Z,-Y) coordinate transformation
- **Multi-Mesh Baking**: Support for baking multiple meshes as grouped components with individual metadata
- **Enhanced SyncWithRhinoDoc**: Groups multiple meshes by component ID instead of treating as separate components

#### Database Migration Tools
- **Marker Points Migration**: `migrate_marker_points_and_multi_mesh.py` - Adds marker_points field and converts single-mesh to multi-mesh format
- **Fragment Boolean Migration**: `migrate_fragment_boolean.py` - Ensures fragment field is properly typed as boolean
- **Color Format Migration**: `migrate_color_format.py` - Converts color fields to proper `[R, G, B]` integer format
- **OBJ File Migration**: `convert_obj_files.py` - Processes existing OBJ files to remove MTL references and standardize format

### Changed

#### CSC FastAPI Backend
- **Geometry Endpoints**: Updated to serve OBJ files only, removed MTL and texture file support
- **API Validation**: Enhanced validation for multi-mesh components and proper field format checking
- **Deprecated Endpoints**: Material and texture serving endpoints now return 404 with informative messages
- **Component Model**: Added validation to ensure `mesh` and `meshes` fields are not both present

#### CSC React Frontend
- **ComponentViewer Architecture**: Complete rewrite for multi-mesh support with consistent rendering pipeline
- **Geometry Loading**: Replaced OBJLoader with custom parser for reliable vertex color handling
- **Material System**: Switched to `MeshBasicMaterial` for proper vertex color display without lighting requirements
- **Bounds Integration**: Fixed primitive geometry positioning to work correctly with `Bounds` component
- **Performance Optimization**: Improved geometry caching and memory management for large multi-mesh components

#### CSC Grasshopper Interface
- **CreateComponent**: Updated to handle both single and multiple mesh inputs with unified processing pipeline
- **FetchGeometry**: Enhanced to parse multi-object OBJ files and return lists of geometry objects
- **DisassembleComponent**: Added support for creating multiple `Rhino.Geometry.Mesh` objects from `meshes` field
- **BakeComponents**: Updated to bake multiple meshes with proper grouping and metadata
- **AddComponent**: Simplified to handle OBJ-only uploads with proper file validation
- **SyncWithRhinoDoc**: Refactored to group meshes by component ID for proper component management

### Technical Improvements

#### Multi-Mesh Architecture
- **Unified Data Model**: Consistent handling of single and multiple meshes across all components
- **Backward Compatibility**: Existing single-mesh components continue to work seamlessly
- **Forward Compatibility**: New multi-mesh format supports future enhancements
- **Data Integrity**: Comprehensive validation ensures proper component structure

#### Geometry Processing
- **Smart Scaling**: Consistent scaling and positioning across all geometry modes
- **Coordinate Systems**: Proper mapping between Rhino and OBJ coordinate systems
- **Face Triangulation**: Automatic conversion of quads and N-gons to triangles for rendering
- **Vertex Color Handling**: Robust parsing and normalization of vertex colors in various formats

#### Performance & Reliability
- **Memory Management**: Proper cleanup and caching of geometry objects
- **Error Handling**: Comprehensive error handling with informative user feedback
- **Type Safety**: Eliminated all TypeScript `any` types with proper interfaces
- **Code Quality**: Resolved all linting errors and improved maintainability

#### Migration & Deployment
- **Database Safety**: All migration scripts include comprehensive validation and rollback capabilities
- **File System Migration**: Automated conversion of existing OBJ files to new format
- **Schema Validation**: Post-migration verification ensures data integrity
- **Documentation**: Comprehensive documentation for all migration processes

### Breaking Changes

#### CSC FastAPI Backend
- **Material/Texture Endpoints**: `get_component_material_detailed`, `get_component_material_reduced`, and `get_component_texture` now return 404
- **Geometry Upload**: `add_reduced_geometry` and `add_detailed_geometry` now only accept OBJ files

#### CSC Grasshopper Interface
- **Input Parameters**: All geometry inputs now expect `List[Rhino.Geometry.GeometryBase]` instead of single objects
- **OBJ File Format**: Generated OBJ files now use object declarations and embedded vertex colors only

### Migration Notes

- **Database Migration**: Run `migrate_marker_points_and_multi_mesh.py` to update existing components
- **File System Migration**: Run `convert_obj_files.py` to update existing OBJ files
- **Frontend Update**: No manual migration required - automatically handles both old and new formats
- **Grasshopper Update**: Update all components to new versions for multi-mesh support

## [0.2.9.0] - 2025-09-04

### Versions

- CSC FastAPI Backend:  0.2.9.0 ✨
- CSC React Frontend:   0.2.4.0 ✨
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.2.0 ✨

### Added

#### CSC FastAPI Backend
- **ETag-based Caching System**: Implemented comprehensive caching solution with ETag support for conditional requests
- **Component Schema Caching**: Added schema endpoint with ETag support for offline component creation
- **Cache-Control Headers**: Added proper HTTP caching headers for better performance
- **ETag Generation Utilities**: Created utility functions for generating ETags from component data and timestamps

#### CSC Grasshopper Interface
- **Local Cache Management**: Implemented `_ComponentCache` class for local storage with thread safety and TTL support
- **Cache Integration**: All fetch components now use intelligent caching with ETag validation
- **Schema-driven Component Creation**: `CreateComponent` now uses cached/fetched schema instead of hardcoded data
- **Status Output**: Added detailed status messages via dedicated output parameter for better user feedback
- **Cache Control Parameters**: Added `DisableCache` and `ClearCache` inputs to SignIn component

### Changed

#### CSC FastAPI Backend
- **API Endpoints**: Enhanced `/components`, `/components/{id}`, and `/schema/component` with ETag support
- **Conditional Requests**: Implemented 304 Not Modified responses for unchanged resources
- **Component Model**: Added optional `etag` field to ComponentModel for cache validation
- **Backward Compatibility**: All changes are additive and maintain full backward compatibility

#### CSC Grasshopper Interface
- **Authentication Core**: Enhanced `_AuthCore` with `cached_get` method for intelligent caching
- **Component Data Creation**: Completely rewrote `build_component_data_from_schema` to use actual schema
- **Dynamic Schema Usage**: Components now build data structures dynamically from fetched schema
- **Improved Error Handling**: Enhanced validation and error messages throughout all components

### Technical Improvements
- **Hybrid ETag Generation**: Combines `lastmodified` timestamp with key component fields for robust cache validation
- **Cross-platform Caching**: Supports Windows (`%APPDATA%`) and macOS (`~/Library/Application Support`) cache locations
- **Single Components Cache + Metadata Cache**: Efficient storage strategy avoiding data duplication
- **Thread Safety**: Implemented proper locking mechanisms for concurrent cache access
- **Schema Validation**: Dynamic component data creation ensures strict adherence to data model
- **Performance Optimization**: Reduced bandwidth usage through intelligent caching and conditional requests

## [0.2.8.0] - 2025-09-03

### Versions

- CSC FastAPI Backend:  0.2.8.0 ✨
- CSC React Frontend:   0.2.3.0 ✨
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.1.0 ✨

### Added

#### CSC Grasshopper Interface
- **Enhanced Component Management**: Improved component creation and management workflows
- **Better Error Handling**: Enhanced error messages and user feedback across all components

### Changed

#### CSC FastAPI Backend
- **Version Bump**: Updated to version 0.2.8.0 for new release cycle
- **API Stability**: Maintained backward compatibility while preparing for future enhancements

#### CSC React Frontend
- **Version Bump**: Updated to version 0.2.3.0 for new release cycle
- **UI Improvements**: Enhanced user interface components and interactions

#### CSC Grasshopper Interface
- **Version Standardization**: All components now use consistent version numbering
- **Component Updates**: Refreshed component versions for better tracking and maintenance

### Technical Improvements
- **Version Management**: Improved version tracking across all project components
- **Release Coordination**: Better synchronization between backend, frontend, and Grasshopper interface
- **Documentation**: Updated changelog with comprehensive version information

## [0.2.5.0] - 2025-08-26

### Versions

- CSC FastAPI Backend:  0.2.5.0 ✨
- CSC React Frontend:   0.2.2.0 ✨
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.0.0

### Added

#### CSC React Frontend
- **Component Reservation System Integration**: Complete frontend integration for the component reservation system
- **User Dashboard**: New dashboard page accessible from user menu with quick stats and navigation
- **Reserved Components Page**: Dedicated page showing all components reserved by the logged-in user
- **Reservation Management**: Users can reserve and release components directly from component detail pages
- **Enhanced Component Overview**: Added "Reserved" column showing reservation status and username
- **Improved Navigation**: Added dashboard link to AppMenu with organized section headlines

#### User Experience Enhancements
- **Reservation Buttons**: "Reserve Component" and "Release Component" buttons on component detail cards
- **Username Display**: Shows human-readable usernames instead of UUIDs for reserved components
- **Smart UI States**: Dynamic button text and states based on reservation status
- **Quick Actions**: Release components directly from the reserved components overview table

#### Technical Improvements
- **Type Safety**: Eliminated all TypeScript `any` types with proper interfaces
- **React Hooks**: Fixed useEffect dependency warnings with useCallback
- **Code Quality**: Resolved all linting errors and improved code maintainability
- **Responsive Design**: Enhanced mobile and desktop layouts for reservation management

#### CSC FastAPI Backend
- **Component Reservation System**: New API routes for managing component reservations
- **Reserve Component Endpoint**: `POST /reserve/{component_id}` allows users to reserve components
- **List Reserved Components Endpoint**: `GET /reserve/{user_identifier}` lists all components reserved by a user
- **Release Component Endpoint**: `DELETE /reserve/{component_id}` allows users to release their reservations
- **User Identification Support**: Reservation endpoints accept both UUID and username for user identification
- **PCA Frame Property**: Added `pca_frame` property to component model for future PCA transformation support
- **Reserved Property**: Added `reserved` property to component model to track component reservations

#### Database Schema Updates
- **Component Model Enhancement**: Extended `ComponentModel` with `pca_frame` and `reserved` properties
- **Migration Script**: Created `migrate_add_pca_frame_and_reserved.py` to update existing components
- **Backward Compatibility**: All new properties are optional and don't affect existing functionality

### Changed

#### CSC React Frontend
- **Component Overview Table**: Added new "Reserved" column with reservation status and username information
- **User Menu**: Enhanced UserItem component with dashboard navigation link
- **AppMenu Organization**: Added section headlines ("Main" and "Other") for better navigation structure
- **Component Detail Cards**: Added reservation management buttons alongside existing "Find Component" button

#### CSC FastAPI Backend
- **Component Model**: Updated `ComponentModel` and `UpdateComponentModel` with new reservation fields
- **API Router**: Added new reservation router (`reserve.py`) to handle component reservation operations
- **Security**: Implemented proper authorization - users can only manage their own reservations unless admin
- **Data Enrichment**: Enhanced component endpoints to include `reserved_by_username` for better user experience

### Technical Improvements
- **Reservation Logic**: Robust reservation system with conflict detection and proper error handling
- **Database Operations**: Efficient MongoDB operations for reservation management
- **API Design**: RESTful API design following FastAPI best practices
- **Error Handling**: Comprehensive error responses with appropriate HTTP status codes
- **Security**: Role-based access control for reservation management
- **Frontend-Backend Integration**: Seamless integration between reservation API and frontend components

## [0.2.4.0] - 2025-08-25

### Versions

- CSC FastAPI Backend:  0.2.4.0 ✨
- CSC React Frontend:   0.2.1.0 ✨
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.0.0

### Added

#### CSC React Frontend
- **Dual Date Format Support**: Enhanced `formatTimestamp` function to handle both old and new date formats
- **Migration Compatibility**: Frontend now works seamlessly with both legacy `DDMMYY-HHMMSS` and new ISO `YYYY-MM-DDTHH:MM:SSZ` formats
- **Error Resilience**: Improved error handling prevents crashes from unknown date formats

#### Database Migration Tools
- **Bounding Box Format Migration**: Script to convert from `[[minX, minY, minZ], [maxX, maxY, maxZ]]` to `[X, Y, Z]` (maximum extents)
- **Date Format Migration**: Script to convert dates from `DDMMYY-HHMMSS` to proper ISO format
- **Comprehensive Migration**: Handles both bounding box and date format updates in a single operation

### Changed

#### CSC React Frontend
- **Date Display Consistency**: All timestamps now display in uniform `YYYY.MM.DD HH:MM:SS` format regardless of source format
- **Backward Compatibility**: Existing functionality preserved while adding support for new ISO date format
- **Enhanced User Experience**: Filter menu now collapsed by default for better space management
- **Improved Component Display**: Increased ID button width for better component ID visibility

#### Database Schema
- **Bounding Box Format**: Updated from coordinate pairs to maximum extents for better performance and clarity
- **Date Format Standardization**: All dates now stored in ISO 8601 format for better compatibility and sorting
- **Migration Safety**: Preserves original creation dates while updating modification timestamps

### Technical Improvements
- **Robust Date Parsing**: Intelligent format detection with graceful fallbacks
- **Migration Scripts**: Comprehensive database migration tools with verification capabilities
- **Frontend Resilience**: Enhanced error handling prevents application crashes from data format issues
- **Code Quality**: Improved defensive programming and error logging throughout the system

## [0.2.3.0] - 2025-08-25

### Versions

- CSC FastAPI Backend:  0.2.3.0 ✨
- CSC React Frontend:   0.2.0.9
- CSC Sheetscan Module: 0.0.1.11
- CSC Grasshopper Interface: 0.1.0.0

### Added

#### CSC FastAPI Backend
- **Enhanced Component Filtering**: Added comprehensive filtering capabilities to component API routes
- **Complexity Filtering**: New `complexity` parameter to filter components by complexity level (0-3)
- **Fragment Status Filtering**: New `fragment` parameter to filter components by fragment status
- **Bounding Box Dimension Filtering**: New range-based filters for component dimensions:
  - `bbx_min_x`, `bbx_min_y`, `bbx_min_z`: Minimum X, Y, Z values
  - `bbx_max_x`, `bbx_max_y`, `bbx_max_z`: Maximum X, Y, Z values
- **Improved API Documentation**: All query parameters now include descriptive documentation for better developer experience

### Changed

#### CSC FastAPI Backend
- **API Parameter Structure**: Updated all filter parameters to use FastAPI's `Query` with descriptive documentation
- **Consistent Filtering**: All three component routes (`/componentcount`, `/shallowcomponents`, `/components`) now support the same comprehensive filtering options
- **Enhanced OpenAPI Schema**: Better parameter documentation will improve the generated API documentation and Swagger UI
- **Backward Compatibility**: All existing functionality preserved - new filters are optional and don't affect current API usage

### Technical Improvements
- **MongoDB Query Optimization**: Efficient bounding box filtering using MongoDB's `$gte` and `$lte` operators
- **Parameter Validation**: Proper type hints and validation for all new filter parameters
- **Code Consistency**: Unified filtering logic across all component routes for maintainability
- **Professional API Standards**: Following FastAPI best practices for parameter documentation and validation

## [0.2.0.9] - 2025-08-22

### Versions

- CSC FastAPI Backend:  0.2.2.0
- CSC React Frontend:   0.2.0.9
- CSC Sheetscan Module: 0.0.1.11
- **CSC Grasshopper Interface: 0.1.0.0** ✨

### Added

#### CSC Grasshopper Interface (New Module)
- **Centralized Authentication System**: Implemented `AuthCore` class for JWT token management across all components
- **Sticky Storage Integration**: Components now share authentication state via Grasshopper's sticky storage
- **Comprehensive Error Handling**: Added runtime messages (Remark, Warning, Error) for better user feedback
- **Color Fallback System**: Enhanced mesh color handling with component color fallbacks and default gray
- **Parameter Documentation**: Added tooltips for all input/output parameters across all components
- **Consistent Coding Standards**: Unified import organization, pyright suppressions, and code structure

#### Updated Components
- **CSC_SignIn**: Complete authentication implementation with JWT token management
- **CSC_FetchAllComponents**: Updated to use centralized AuthCore pattern
- **CSC_FetchComponents**: Enhanced with AuthCore integration and improved error handling
- **CSC_DisassembleComponent**: Added descriptors output and comprehensive geometry processing
- **CSC_BakeComponents**: Enhanced with color fallbacks and improved user feedback

### Changed

#### CSC Grasshopper Interface
- **Authentication Flow**: Replaced scattered authentication logic with centralized AuthCore system
- **Component Architecture**: Standardized all components with consistent `__init__`, `_add*` methods, and error handling
- **Mesh Color Handling**: Implemented three-tier color fallback system (mesh colors → component color → default gray)
- **Output Format**: Descriptors now output as JSON strings for consistency with other components
- **Error Recovery**: All components now provide graceful error handling with clear user feedback
- **Code Quality**: Applied consistent pyright suppressions, import organization, and coding standards

#### Component-Specific Improvements
- **CSC_SignIn**: Added username tracking, refresh functionality, and comprehensive API error handling
- **CSC_FetchAllComponents**: Enhanced with proper authentication validation and runtime messaging
- **CSC_FetchComponents**: Improved individual component fetching with better error handling
- **CSC_DisassembleComponent**: Added descriptors output and enhanced geometry processing robustness
- **CSC_BakeComponents**: Improved baking process with better status tracking and error handling

### Technical Improvements
- **Memory Management**: Eliminated code duplication through centralized authentication
- **User Experience**: Consistent feedback across all components via multiple message channels
- **Robustness**: Enhanced error handling prevents crashes and provides clear user guidance
- **Maintainability**: Standardized code structure makes future updates easier and more consistent
- **Student Experience**: Professional-grade components with clear error messages and status updates

## [0.2.0.8] - 2025-08-21

### Added
- Enhanced authentication system with comprehensive error handling and user feedback
- Added Register button alongside Sign In button in UserItem component for non-authenticated users
- Added security notice on registration page warning users to use unique passwords
- Added cross-links between sign in and register pages for better user navigation

### Changed
- Improved sign in form error handling with specific error messages for different failure types
- Updated sign in and register pages to stick to top on mobile/narrow screens instead of centering
- Enhanced register page styling to match sign in page using consistent Card components
- Improved form validation with client-side checks and better error positioning

### Fixed
- Sign in form now properly displays error messages on authentication failures
- Register page layout now properly contains all elements within the form container
- Consistent styling between authentication pages for better user experience

## [0.2.0.7] - 2025-08-21

### Fixed
- Responsive layout issues when dynamically resizing window width
- Layout not properly adapting when switching between mobile and desktop viewports
- Sidebar visibility and positioning on resize events
- Component detail page responsive behavior when resizing from wide to narrow
- Fixed layout overflow issues caused by fixed minimum widths
- Component detail page width constraints - now properly adapts to viewport when resizing
- Fixed Card components expanding beyond container width on resize
- **Component detail page now properly constrains width to viewport (no more right-side overflow)**

### Changed
- Improved responsive behavior with proper resize event listeners
- Sidebar now dynamically shows/hides based on screen size
- Header and mobile menu properly adapt to viewport changes
- Layout structure changed from CSS Grid to Flexbox for better responsive behavior
- Added proper cleanup of resize event listeners
- Component detail page now uses flexible layout instead of fixed minimum widths
- Changed breakpoint from `md:` to `lg:` for better mobile experience
- Improved text sizing and button layout for different screen sizes
- Component detail page layout changed from CSS Grid to Flexbox for better width control
- Added explicit width constraints and overflow handling to Card components
- **Simplified component detail page width handling to match working overview page approach**
- **Enhanced ThemeToggle with hover effects - moon icon now uses accent color on hover**

### Added
- Dynamic screen size detection in Sidebar, Header, AppMenu, and ComponentDetailCard components
- Automatic mobile menu closing when resizing to desktop
- Proper z-index management for overlapping elements
- Responsive text sizing for ComponentViewer overlay UI
- Break-word handling for long component IDs
- Strict width constraints and overflow handling for component detail page

## [0.2.0.6] - 2025-08-21

### Changed
- Restructured frontend components folder organization:
  - `src/frontend/components/layout/` - Layout components (Header, Sidebar, Footer)
  - `src/frontend/components/auth/` - Authentication components (UserItem, SignInForm)
  - `src/frontend/components/components/` - Component-specific components
  - `src/frontend/components/common/` - Shared/common components (ThemeToggle, models)
- Updated all import statements to use correct absolute paths (`@/components/ui/...`)
- Fixed broken UI component imports after folder restructuring

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