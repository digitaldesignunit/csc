#!/usr/bin/env python3
"""
MongoDB Color Field Format Migration Script

This script ensures the 'color' field is in the correct format for all components in the CSC database.
The color field should be a List[int] with exactly 3 integer values representing RGB (0-255).

The script:
1. Connects to MongoDB
2. Finds all components with color field in incorrect format
3. Converts them to proper [R, G, B] integer format
4. Updates the database
5. Provides a summary of the migration

Usage:
    python scripts/migrate_color_format.py

Requirements:
    - pymongo
    - MongoDB connection string in environment or config
"""

import os
import sys
import json
from typing import Any, List, Union
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('color_format_migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load MongoDB configuration from environment or config file"""
    # Try to load from environment variables first
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        return {'uri': mongo_uri}
    
    # Try to load from config file
    config_path = os.path.normpath(os.path.abspath(
        os.path.join('..', 'src', 'backend', 'config', 'dbconfig.json')
    ))
    print(f"Config path: {config_path}")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Construct MongoDB URI from config
                server = config.get('server')
                db = config.get('db')
                user = config.get('user')
                pwd = config.get('pwd')

                if user and pwd:
                    mongo_uri = (f"mongodb+srv://{user}:{pwd}@"
                                 f"{server}/{db}")

                return {'uri': mongo_uri}
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            return None
    
    return None


def convert_to_rgb_integers(value: Any) -> List[int]:
    """
    Convert various color formats to [R, G, B] integer list (0-255).
    
    Args:
        value: The color value to convert
        
    Returns:
        List[int]: RGB values as integers (0-255)
    """
    if value is None:
        # Default gray color
        return [110, 110, 110]
    
    if isinstance(value, list):
        if len(value) == 3:
            # Convert to integers and clamp to 0-255 range
            rgb = []
            for i, component in enumerate(value):
                if isinstance(component, (int, float)):
                    # Clamp to 0-255 range
                    clamped = max(0, min(255, int(component)))
                    rgb.append(clamped)
                else:
                    logger.warning(f"Invalid color component '{component}' at index {i}, using 110")
                    rgb.append(110)
            return rgb
        else:
            logger.warning(f"Color list has {len(value)} elements, expected 3. Using default gray.")
            return [110, 110, 110]
    
    if isinstance(value, str):
        # Try to parse string representations
        value_lower = value.lower().strip()
        
        # Handle common color names
        color_map = {
            'red': [255, 0, 0],
            'green': [0, 255, 0],
            'blue': [0, 0, 255],
            'white': [255, 255, 255],
            'black': [0, 0, 0],
            'gray': [128, 128, 128],
            'grey': [128, 128, 128],
            'yellow': [255, 255, 0],
            'cyan': [0, 255, 255],
            'magenta': [255, 0, 255],
            'orange': [255, 165, 0],
            'purple': [128, 0, 128],
            'brown': [165, 42, 42],
            'pink': [255, 192, 203],
            'lime': [0, 255, 0],
            'navy': [0, 0, 128],
            'teal': [0, 128, 128],
            'olive': [128, 128, 0],
            'maroon': [128, 0, 0],
            'silver': [192, 192, 192],
            'gold': [255, 215, 0]
        }
        
        if value_lower in color_map:
            return color_map[value_lower]
        
        # Try to parse hex colors (#RRGGBB or #RGB)
        if value.startswith('#'):
            hex_value = value[1:]
            if len(hex_value) == 6:
                try:
                    r = int(hex_value[0:2], 16)
                    g = int(hex_value[2:4], 16)
                    b = int(hex_value[4:6], 16)
                    return [r, g, b]
                except ValueError:
                    logger.warning(f"Invalid hex color '{value}', using default gray")
                    return [110, 110, 110]
            elif len(hex_value) == 3:
                try:
                    r = int(hex_value[0] * 2, 16)
                    g = int(hex_value[1] * 2, 16)
                    b = int(hex_value[2] * 2, 16)
                    return [r, g, b]
                except ValueError:
                    logger.warning(f"Invalid hex color '{value}', using default gray")
                    return [110, 110, 110]
        
        # Try to parse comma-separated values
        if ',' in value:
            try:
                parts = [x.strip() for x in value.split(',')]
                if len(parts) == 3:
                    rgb = []
                    for part in parts:
                        # Handle both integer and float values
                        if '.' in part:
                            rgb.append(max(0, min(255, int(float(part)))))
                        else:
                            rgb.append(max(0, min(255, int(part))))
                    return rgb
            except ValueError:
                logger.warning(f"Could not parse comma-separated color '{value}', using default gray")
                return [110, 110, 110]
        
        # Try to parse space-separated values
        try:
            parts = value.split()
            if len(parts) == 3:
                rgb = []
                for part in parts:
                    if '.' in part:
                        rgb.append(max(0, min(255, int(float(part)))))
                    else:
                        rgb.append(max(0, min(255, int(part))))
                return rgb
        except ValueError:
            pass
        
        logger.warning(f"Could not parse color string '{value}', using default gray")
        return [110, 110, 110]
    
    if isinstance(value, (int, float)):
        # Single numeric value - treat as grayscale
        gray_value = max(0, min(255, int(value)))
        return [gray_value, gray_value, gray_value]
    
    if isinstance(value, dict):
        # Try to extract RGB from dictionary
        if 'r' in value and 'g' in value and 'b' in value:
            try:
                r = max(0, min(255, int(value['r'])))
                g = max(0, min(255, int(value['g'])))
                b = max(0, min(255, int(value['b'])))
                return [r, g, b]
            except (ValueError, TypeError):
                logger.warning(f"Could not parse color dict '{value}', using default gray")
                return [110, 110, 110]
        elif 'red' in value and 'green' in value and 'blue' in value:
            try:
                r = max(0, min(255, int(value['red'])))
                g = max(0, min(255, int(value['green'])))
                b = max(0, min(255, int(value['blue'])))
                return [r, g, b]
            except (ValueError, TypeError):
                logger.warning(f"Could not parse color dict '{value}', using default gray")
                return [110, 110, 110]
        else:
            logger.warning(f"Color dict '{value}' missing RGB keys, using default gray")
            return [110, 110, 110]
    
    # For any other type, try to convert to string and parse
    try:
        str_value = str(value)
        logger.warning(f"Unknown color type '{type(value).__name__}' with value '{str_value}', using default gray")
        return [110, 110, 110]
    except Exception as e:
        logger.error(f"Error converting color value '{value}' to string: {e}")
        return [110, 110, 110]


def is_valid_color_format(value: Any) -> bool:
    """
    Check if a color value is already in the correct format.
    
    Args:
        value: The color value to check
        
    Returns:
        bool: True if the format is correct, False otherwise
    """
    if value is None:
        return True  # None is valid (optional field)
    
    if not isinstance(value, list):
        return False
    
    if len(value) != 3:
        return False
    
    for component in value:
        if not isinstance(component, int):
            return False
        if not (0 <= component <= 255):
            return False
    
    return True


def migrate_color_format():
    """Main migration function"""
    logger.info("Starting color field format migration...")
    
    # Load configuration
    config = load_config()
    if not config:
        logger.error("Failed to load MongoDB configuration")
        return False
    
    try:
        # Connect to MongoDB
        client = MongoClient(config['uri'])
        
        # Get database - try default first, then extract from URI
        db = client.get_default_database()
        if db is None:
            # Try to get database from URI
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        
        components_collection = db.components
        
        logger.info(f"Connected to database: {db.name}")
        logger.info(f"Collection: {components_collection.name}")
        
        # Find all components with color field
        has_color_query = {"color": {"$exists": True}}
        all_components_with_color = list(components_collection.find(has_color_query))
        
        logger.info(f"Found {len(all_components_with_color)} components with color field")
        
        # Filter components that need migration
        components_to_migrate = []
        for component in all_components_with_color:
            color_value = component.get('color')
            if not is_valid_color_format(color_value):
                components_to_migrate.append(component)
        
        logger.info(f"Found {len(components_to_migrate)} components with invalid color format")

        if not components_to_migrate:
            logger.info(
                "No components need migration. All components already have "
                "valid color field format."
            )
            return True

        # Process each component
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        conversion_stats = {}

        for component in components_to_migrate:
            try:
                component_id = component.get('_id')
                current_value = component.get('color')
                current_type = type(current_value).__name__
                
                # Convert to proper format
                rgb_value = convert_to_rgb_integers(current_value)
                
                # Track conversion statistics
                conversion_key = f"{current_type} -> [R, G, B]"
                conversion_stats[conversion_key] = conversion_stats.get(conversion_key, 0) + 1
                
                # Update the component
                result = components_collection.update_one(
                    {'_id': component_id},
                    {'$set': {'color': rgb_value}}
                )

                if result.modified_count > 0:
                    migrated_count += 1
                    logger.info(
                        f"Successfully migrated component {component_id}: "
                        f"'{current_value}' ({current_type}) -> {rgb_value} (List[int])"
                    )
                else:
                    logger.warning(
                        f"Component {component_id}: No changes made"
                    )
                    skipped_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing component "
                    f"{component.get('_id', 'unknown')}: {e}"
                )
                error_count += 1
        
        # Summary
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total components with color field: {len(all_components_with_color)}")
        logger.info(f"Components with invalid format: {len(components_to_migrate)}")
        logger.info(f"Successfully migrated: {migrated_count}")
        logger.info(f"Skipped: {skipped_count}")
        logger.info(f"Errors: {error_count}")
        logger.info("")
        logger.info("CONVERSION STATISTICS:")
        for conversion, count in conversion_stats.items():
            logger.info(f"  {conversion}: {count} components")
        logger.info("=" * 60)
        
        if error_count == 0:
            logger.info("Migration completed successfully!")
            return True
        else:
            logger.warning(f"Migration completed with {error_count} errors")
            return False
            
    except PyMongoError as e:
        logger.error(f"MongoDB error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()
            logger.info("MongoDB connection closed")


def verify_migration():
    """Verify that the migration was successful"""
    logger.info("Verifying migration...")
    
    config = load_config()
    if not config:
        logger.error("Failed to load MongoDB configuration for verification")
        return False
    
    try:
        client = MongoClient(config['uri'])
        
        # Get database - try default first, then extract from URI
        db = client.get_default_database()
        if db is None:
            db_name = config['uri'].split('/')[-1].split('?')[0]
            db = client[db_name]
        
        components_collection = db.components
        
        # Check for components with color field
        has_color_query = {"color": {"$exists": True}}
        has_color_count = components_collection.count_documents(has_color_query)
        
        # Check for components with valid color format
        valid_color_count = 0
        invalid_color_count = 0
        color_format_breakdown = {}
        
        for component in components_collection.find(has_color_query):
            color_value = component.get('color')
            if is_valid_color_format(color_value):
                valid_color_count += 1
            else:
                invalid_color_count += 1
                color_type = type(color_value).__name__
                color_format_breakdown[color_type] = color_format_breakdown.get(color_type, 0) + 1
        
        # Check for components with null color (valid)
        null_color_query = {"color": None}
        null_color_count = components_collection.count_documents(null_color_query)
        
        # Check for components with default gray color
        default_color_query = {"color": [110, 110, 110]}
        default_color_count = components_collection.count_documents(default_color_query)
        
        # Total components
        total_components = components_collection.count_documents({})
        
        logger.info("=" * 50)
        logger.info("VERIFICATION RESULTS")
        logger.info("=" * 50)
        logger.info(f"Total components: {total_components}")
        logger.info(f"Components with color field: {has_color_count}")
        logger.info(f"Components with valid color format: {valid_color_count}")
        logger.info(f"Components with invalid color format: {invalid_color_count}")
        logger.info(f"Components with null color: {null_color_count}")
        logger.info(f"Components with default gray color: {default_color_count}")
        logger.info("=" * 50)
        
        if invalid_color_count == 0:
            logger.info("✓ All components with color field have valid format")
        else:
            logger.warning(f"⚠ Found {invalid_color_count} components still with invalid color format:")
            for color_type, count in color_format_breakdown.items():
                logger.warning(f"  {color_type}: {count} components")
        
        if valid_color_count > 0:
            logger.info(f"✓ {valid_color_count} components now have valid color format")
        
        return invalid_color_count == 0
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    print("CSC Color Field Format Migration Script")
    print("=" * 45)
    
    # Run migration
    success = migrate_color_format()
    
    if success:
        print("\nMigration completed successfully!")
        
        # Ask user if they want to verify
        verify = input("\nWould you like to verify the migration? (y/n): ").lower().strip()
        if verify in ['y', 'yes']:
            verify_migration()
    else:
        print("\nMigration failed. Check the logs for details.")
        sys.exit(1)
