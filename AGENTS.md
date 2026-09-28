# AGENTS.md - AYON Ftrack Integration

This file contains context for AI agents working on this codebase.

## Project Overview

This is the AYON Ftrack integration addon. It provides:
- Publishing plugins for integrating AYON data into Ftrack
- Event handlers and actions for Ftrack
- Common utilities and constants

## Key Files

### Publishing Plugins

- `client/ayon_ftrack/plugins/publish/integrate_ftrack_instances.py`: Collects and prepares ftrack component data for integration. Handles review representations (video/image) and thumbnails.

- `client/ayon_ftrack/plugins/publish/integrate_ftrack_api.py`: Commits components to the ftrack server. Creates assets, asset versions, and components.

### Event Handlers

- `client/ayon_ftrack/event_handlers_user/action_download_reviews.py`: Action to download review media from ftrack.

## Review Component Identification

**Important**: Review components are identified by the `ayon_review_type` metadata field:
- `ayon_review_type: "video"` - Video review component (playable mp4)
- `ayon_review_type: "image"` - Image review component

**Legacy Support**: For backwards compatibility, the system also recognizes legacy component names:
- `ftrackreview-mp4` - Legacy video review component name
- `ftrackreview-image` - Legacy image review component name

The video review component now uses the **original filename** of the source file instead of the generic `ftrackreview-mp4` name.

## Recent Changes

### Video Review Component Naming (December 2024)

Changed the video review component naming from hardcoded `ftrackreview-mp4` to use the original filename of the file being converted.

**Files Modified:**
1. `integrate_ftrack_instances.py` - Uses original filename for video review component, adds `ayon_review_type` metadata
2. `integrate_ftrack_api.py` - Detects video reviews by metadata instead of hardcoded name
3. `action_download_reviews.py` - Finds reviews by metadata, with legacy name fallback

**Backwards Compatibility:**
- All files maintain support for legacy `ftrackreview-mp4` and `ftrackreview-image` component names
- Existing components with legacy names will continue to work

