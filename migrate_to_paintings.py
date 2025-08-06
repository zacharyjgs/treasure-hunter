#!/usr/bin/env python3

import json
import os

def migrate_progress_to_appraisals():
    """Migrate progress.json to the new appraisals.json format."""
    
    # Check if progress.json exists
    if not os.path.exists('progress.json'):
        print("No progress.json file found. Nothing to migrate.")
        return
    
    try:
        # Load the old progress.json
        with open('progress.json', 'r') as f:
            old_data = json.load(f)
        
        # Extract the data
        valuable_paintings = old_data.get('valuable_paintings', [])
        processed_urls = old_data.get('processed_urls', [])
        last_page = old_data.get('last_page', 0)
        last_item = old_data.get('last_item', 0)
        
        # Create new format
        new_data = {
            "paintings": valuable_paintings,  # All paintings are now in one list
            "processed_urls": processed_urls,
            "last_page": last_page,
            "last_item": last_item
        }
        
        # Save to appraisals.json
        with open('appraisals.json', 'w') as f:
            json.dump(new_data, f, indent=2)
        
        print(f"✅ Migration complete!")
        print(f"   - Migrated {len(valuable_paintings)} paintings from progress.json")
        print(f"   - Processed URLs: {len(processed_urls)}")
        print(f"   - Last page: {last_page}, Last item: {last_item}")
        print(f"   - New file: appraisals.json")
        
        # Optionally backup the old file
        os.rename('progress.json', 'progress.json.backup')
        print(f"   - Old file backed up as: progress.json.backup")
        
        # Also remove valuable_paintings.json if it exists
        if os.path.exists('valuable_paintings.json'):
            os.rename('valuable_paintings.json', 'valuable_paintings.json.backup')
            print(f"   - Old valuable_paintings.json backed up as: valuable_paintings.json.backup")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")

if __name__ == "__main__":
    migrate_progress_to_appraisals()