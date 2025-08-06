#!/usr/bin/env python3
"""
Painting Appraiser for ShopGoodwill.com

This script fetches paintings from shopgoodwill.com using their API, uses OpenAI's Responses API with web search to appraise them,
and outputs URLs of paintings.

Usage:
    export OPENAI_API_KEY="your-api-key-here"
    python appraise.py

Requirements:
    pip install requests beautifulsoup4 openai pillow python-dateutil
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, quote

import openai
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

from pydantic import BaseModel


class ArtAppraisal(BaseModel):
    estimated_value_min: float  # Should be $10-$75 for unknown artists, $25-$200 for decorative unknown works
    estimated_value_max: float  # Should rarely exceed $300 for unknown artists unless exceptional quality
    estimated_value_best: float  # Conservative middle estimate
    confidence_level: str  # Should be "low" for unknown artists
    reasoning: str  # Must explain if artist is unknown and justify low valuation
    risk_factors: str  # Should mention lack of provenance/market data for unknown artists
    market_category: str  # Should be "Unknown Artist" or "Decorative Art" for unestablished artists
    web_search_summary: str  # Should explicitly state if no market data found
    recent_sales_data: str  # Should state "No sales data available" if none found
    artist_market_status: str  # Should clearly state "No established art market presence" if applicable
    authentication_notes: str  # Should mention lack of known works/signatures for unknown artists
    comparable_works: str  # Should reference general unknown artist market prices if no specifics found


class PaintingAppraiser:
    def __init__(self, openai_api_key: str, active_auctions_only: bool = True):
        """
        Initialize the painting appraiser.
        
        Args:
            openai_api_key: OpenAI API key
            active_auctions_only: Only process paintings with active auctions
        """
        self.client = OpenAI(api_key=openai_api_key)
        self.active_auctions_only = active_auctions_only
        self.base_url = "https://shopgoodwill.com"

    def _is_valid_product_image(self, image_url: str) -> bool:
        """
        Check if an image URL appears to be a valid product image, not a logo or icon.
        """
        if not image_url:
            return False
        
        # Convert to lowercase for case-insensitive matching
        url_lower = image_url.lower()
        
        # Exclude obvious non-product images
        exclude_patterns = [
            'logo', 'icon', 'banner', 'header', 'footer', 'nav', 'menu',
            'button', 'arrow', 'star', 'heart', 'cart', 'search',
            'facebook', 'twitter', 'instagram', 'social',
            'general/logo.svg', 'sprites', 'ui/'
        ]
        
        for pattern in exclude_patterns:
            if pattern in url_lower:
                return False
        
        # Must be a reasonable image format
        if not any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']):
            return False
        
        # Prefer images that look like they're product-specific
        good_patterns = [
            '/item/', 'product', 'listing', 'auction', '/items/'
        ]
        
        # ShopGoodwill specific patterns
        if 'shopgoodwillimages.azureedge.net' in url_lower and '/items/' in url_lower:
            return True
        
        # If it has good patterns, it's likely a product image
        for pattern in good_patterns:
            if pattern in url_lower:
                return True
        
        # If no specific good patterns but also no bad patterns, it might be okay
        # This is for cases where the image URL doesn't have clear indicators
        return True




        
    def get_paintings_list(self, page: int = 1) -> List[Dict]:
        """
        Get paintings listing using the API endpoint instead of web scraping.
        
        Args:
            page: Page number to fetch
            
        Returns:
            List of painting dictionaries with basic info
        """
        try:
            # Generate current date + 30 days for auction end date filter
            future_date = datetime.now() + timedelta(days=30)
            # Format as M/D/YYYY
            date_str = f"{future_date.month}/{future_date.day}/{future_date.year}"
            
            # API endpoint for search
            api_url = "https://buyerapi.shopgoodwill.com/api/Search/ItemListing"
            
            # Headers based on the curl example
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'no-cache',
                'content-type': 'application/json',
                'origin': 'https://shopgoodwill.com',
                'pragma': 'no-cache',
                'priority': 'u=1, i',
                'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
            }
            
            # API payload - modified from the curl example for paintings (category 71)
            payload = {
                "isSize": False,
                "isWeddingCatagory": "false",
                "isMultipleCategoryIds": False,
                "isFromHeaderMenuTab": False,
                "layout": "",
                "isFromHomePage": False,
                "searchText": "",
                "selectedGroup": "Keyword",
                "selectedCategoryIds": "71",  # Paintings category
                "selectedSellerIds": "",
                "lowPrice": "0",
                "highPrice": "999999",
                "searchBuyNowOnly": "",
                "searchPickupOnly": "false",
                "searchNoPickupOnly": "true",  # Exclude pickup only items
                "searchOneCentShippingOnly": "false",
                "searchDescriptions": "false",
                "searchClosedAuctions": "false" if self.active_auctions_only else "true",
                "closedAuctionEndingDate": date_str,
                "closedAuctionDaysBack": "7",
                "searchCanadaShipping": "false",
                "searchInternationalShippingOnly": "false",
                "sortColumn": "1",
                "page": str(page),
                "pageSize": "40",
                "sortDescending": "false",
                "savedSearchId": 0,
                "useBuyerPrefs": "true",
                "searchUSOnlyShipping": "false",
                "categoryLevelNo": "1",
                "partNumber": "",
                "catIds": "-1,15,71",
                "categoryId": "71",
                "categoryLevel": 2
            }
            
            print(f"Fetching page {page} from API...")
            print(f"Using auction end date filter: {date_str}")
            
            # Make the API request
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract items from the API response
            paintings = []
            items = data.get('searchResults', {}).get('items', [])
            
            for item in items:
                try:
                    item_id = str(item.get('itemId', ''))
                    title = item.get('title', f'Painting {item_id}')
                    
                    # Build URL from item ID
                    url = f"{self.base_url}/item/{item_id}"
                    
                    # Get current price
                    current_price = ""
                    if item.get('currentPrice'):
                        current_price = f"${item['currentPrice']:.2f}"
                    
                    paintings.append({
                        'item_id': item_id,
                        'url': url,
                        'title': title,
                        'current_price': current_price,
                        'api_data': item  # Store full API data for later use
                    })
                    
                except Exception as e:
                    print(f"Error processing item: {e}")
                    continue
            
            print(f"Found {len(paintings)} paintings on page {page}")
            return paintings
            
        except Exception as e:
            print(f"Error fetching paintings list from API: {e}")
            return []

    def is_auction_active(self, painting_url: str, api_data: Dict = None) -> bool:
        """
        Check if the auction for a painting is still active using API data.
        
        Args:
            painting_url: URL to the painting's detail page
            api_data: API data from search or item detail (optional)
            
        Returns:
            True if auction is active, False otherwise
        """
        try:
            # If we don't have API data, get it
            if not api_data:
                # Extract item ID from URL
                match = re.search(r'/item/(\d+)', painting_url)
                if not match:
                    print(f"Could not extract item ID from URL: {painting_url}")
                    return False
                item_id = match.group(1)
                
                # Get item details from API
                details = self.get_painting_details(painting_url, item_id)
                if not details or not details.get('api_data'):
                    print(f"Could not get API data for: {painting_url}")
                    return False
                api_data = details['api_data']
            
            # Check auction status from API data
            # First check the remainingTime field - most reliable indicator
            remaining_time = api_data.get('remainingTime', '').lower()
            if 'ended' in remaining_time or 'closed' in remaining_time or 'sold' in remaining_time:
                print(f"⏰ Auction ended (remainingTime: {remaining_time}) for: {painting_url}")
                return False
            
            # Check end date using correct field name
            end_date_str = api_data.get('endTime') or api_data.get('auctionEndTime') or api_data.get('endDate')
            if end_date_str:
                try:
                    # Parse the end date (format may vary)
                    from datetime import datetime
                    import dateutil.parser
                    end_date = dateutil.parser.parse(end_date_str)
                    now = datetime.now(end_date.tzinfo) if end_date.tzinfo else datetime.now()
                    
                    if end_date <= now:
                        print(f"⏰ Auction ended (past end date: {end_date_str}) for: {painting_url}")
                        return False
                except Exception as date_error:
                    print(f"⚠️ Could not parse end date '{end_date_str}': {date_error}")
            
            # Check for explicit status indicators
            auction_status = api_data.get('status', '').lower()
            item_status = api_data.get('itemStatus', '').lower()
            
            inactive_statuses = ['ended', 'closed', 'sold', 'completed', 'finished', 'inactive']
            for status in inactive_statuses:
                if status in auction_status or status in item_status:
                    print(f"⏰ Auction ended (status: {auction_status}/{item_status}) for: {painting_url}")
                    return False
            
            # Check for active status indicators in remainingTime
            # Look for time patterns like "20h 20m", "1d 5h", "30m", etc.
            if remaining_time and any(time_indicator in remaining_time for time_indicator in ['h ', 'm ', 'd ', 's ', 'day', 'hour', 'minute', 'second']):
                print(f"✅ Active auction found (remainingTime: {remaining_time}): {painting_url}")
                return True
            
            # Check for active status indicators
            active_statuses = ['active', 'open', 'bidding', 'live', 'ongoing']
            for status in active_statuses:
                if status in auction_status or status in item_status:
                    print(f"✅ Active auction found (status: {auction_status}/{item_status}): {painting_url}")
                    return True
            
            # Check if we can place bids (API might have this info)
            can_bid = api_data.get('canBid', api_data.get('biddingAllowed', True))
            if can_bid is False:
                print(f"⏰ Bidding not allowed for: {painting_url}")
                return False
            
            # If filtering for active auctions only and we can't determine status, be conservative
            if self.active_auctions_only:
                print(f"❓ Cannot determine auction status, assuming inactive (filtering active only): {painting_url}")
                return False
            else:
                print(f"✅ Cannot determine auction status, assuming active (not filtering): {painting_url}")
                return True
            
        except Exception as e:
            print(f"Error checking auction status for {painting_url}: {e}")
            return False

    def get_painting_details(self, painting_url: str, item_id: str = None) -> Optional[Dict]:
        """
        Get detailed information about a specific painting using the API endpoint.
        
        Args:
            painting_url: URL to the painting's detail page
            item_id: Item ID (extracted from URL if not provided)
            
        Returns:
            Dictionary with detailed painting info or None if failed
        """
        try:
            # Extract item ID from URL if not provided
            if not item_id:
                match = re.search(r'/item/(\d+)', painting_url)
                if not match:
                    print(f"Could not extract item ID from URL: {painting_url}")
                    return None
                item_id = match.group(1)
            
            print(f"Fetching details for item {item_id} from API...")
            
            # API endpoint for item details
            api_url = f"https://buyerapi.shopgoodwill.com/api/ItemDetail/GetItemDetailModelByItemId/{item_id}"
            
            # Headers based on the curl example
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'no-cache',
                'origin': 'https://shopgoodwill.com',
                'pragma': 'no-cache',
                'priority': 'u=1, i',
                'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
            }
            
            # Make the API request
            response = requests.get(api_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract information from API response (data is at root level, not nested)
            title = data.get('title', f'Painting {item_id}')
            description = data.get('description', '').strip()
            
            # Clean up HTML description
            if description:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(description, 'html.parser')
                description = soup.get_text(separator=' ').strip()
            
            # Get current price
            current_price = "Unknown"
            if data.get('currentPrice'):
                current_price = f"${data['currentPrice']:.2f}"
            
            # Get main image URL from imageUrlString
            image_url = None
            image_url_string = data.get('imageUrlString', '')
            if image_url_string:
                # Split by semicolon and take the first image
                image_paths = image_url_string.split(';')
                if image_paths and image_paths[0]:
                    image_path = image_paths[0].replace('\\', '/')
                    image_server = data.get('imageServer', 'https://shopgoodwillimages.azureedge.net/production/')
                    image_url = f"{image_server}{image_path}"
            
            # Extract artist, medium, dimensions from description
            artist = "Unknown Artist"
            medium = "Unknown Medium" 
            dimensions = ""
            
            # Try to parse structured description for artwork info
            if description:
                # Look for common patterns in the description
                import re
                
                # Extract Type of Art (medium)
                type_match = re.search(r'Type of Art:\s*(.+?)(?:\n|$)', description, re.IGNORECASE)
                if type_match:
                    medium = type_match.group(1).strip()
                
                # Extract Size
                size_match = re.search(r'Size \(in inches\):\s*(.+?)(?:\n|$)', description, re.IGNORECASE)
                if size_match:
                    dimensions = size_match.group(1).strip()
            
            # Also check description for artist/medium info if not found in metadata
            if artist == "Unknown Artist" and description:
                artist_match = re.search(r'artist[:\s]+([^\n.]+)', description, re.IGNORECASE)
                if artist_match:
                    artist = artist_match.group(1).strip()
            
            if medium == "Unknown Medium" and description:
                medium_match = re.search(r'media[:\s]+([^\n.]+)', description, re.IGNORECASE)
                if medium_match:
                    medium = medium_match.group(1).strip()
            
            return {
                'url': painting_url,
                'title': title,
                'image_url': image_url,
                'current_price': current_price,
                'artist': artist,
                'medium': medium,
                'dimensions': dimensions,
                'description': description,
                'api_data': data  # Store full API data for reference
            }
            
        except Exception as e:
            print(f"Error fetching painting details from API for item {item_id}: {e}")
            return None

    def appraise_painting(self, painting_info: Dict) -> Optional[Dict]:
        """
        Use OpenAI GPT-4o multimodal API to appraise a painting with enhanced research-style prompts that encourage thorough analysis.
        
        Args:
            painting_info: Dictionary with painting information including image_url
            
        Returns:
            Dictionary with appraisal results or None if failed
        """
        if not painting_info.get('image_url'):
            print(f"No image URL for painting: {painting_info.get('title', 'Unknown')}")
            return None
        
        # Use the image URL directly since we now find proper JPEG images
        image_url = painting_info['image_url']
        
        try:
            # Construct the prompt for appraisal with web search capabilities
            prompt = f"""
            You are an expert art appraiser with access to real-time market data through web search. Analyze this painting and provide a comprehensive market appraisal.

            Known Information:
            - Title: {painting_info.get('title', 'Unknown')}
            - Artist: {painting_info.get('artist', 'Unknown')}
            - Medium: {painting_info.get('medium', 'Unknown')}
            - Dimensions: {painting_info.get('dimensions', 'Unknown')}
            - Current asking price: {painting_info.get('current_price', 'Unknown')}
            - Description: {painting_info.get('description', '')[:500]}...

            REQUIRED: Use web search to research the following before making your appraisal:
            
            1. Artist Market Research:
               - Search for "{painting_info.get('artist', 'Unknown')} artist auction results 2023 2024"
               - Look for biography, career highlights, and market recognition
               - Find recent sales data and price trends
            
            2. Comparable Works:
               - Search for "similar paintings {painting_info.get('artist', 'Unknown')} sold auction"
               - Look for works with similar style, medium, and size
               - Find current market trends for this type of art
            
            3. Authentication Research:
               - Search for known works and signatures by this artist
               - Look for any authentication guides or red flags
               - Check museum collections or catalogs

            Guidelines on unknown artists:
            - If NO market data, auction records, or recognition is found for the artist, treat as UNKNOWN ARTIST
            - Unknown artists typically sell for less and value depends more on size, quality, and decorative appeal
            - Only established artists with documented sales history should be valued highly
            - Be extremely conservative with valuations for unverified or unknown artists
            
            EXAMPLE: If you find an artist named "John Smith" but your web search reveals no auction records, no art galleries representing them, no museum collections, and no recent sales data, then value the painting as if by an unknown artist ($25-$200 range), NOT as if by an established artist ($1000+ range).

            After completing your web research, analyze the image and provide:
            1. Artistic quality and technique
            2. Historical significance or style period  
            3. Condition (based on what you can see)
            4. Market demand and recent sales data
            5. Artist recognition and career status
            6. Authentication likelihood

            Provide your response using the structured output format with comprehensive analysis including web research findings.
            """
            
            # Debug: Print the image URL being sent to OpenAI
            print(f"🖼️  IMAGE URL: {image_url}")
            print(f"📝 TITLE: {painting_info.get('title', 'Unknown')}")
            print(f"🎨 ARTIST: {painting_info.get('artist', 'Unknown')}")
            print(f"🔗 LISTING URL: {painting_info.get('url', 'Unknown')}")
            print("─" * 80)
            
            # Use Responses API with web search and structured outputs
            response = self.client.responses.parse(
                model="gpt-4o-2024-08-06",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {
                                "type": "input_image", 
                                "image_url": image_url
                            }
                        ]
                    }
                ],
                tools=[
                    {
                        "type": "web_search"
                    }
                ],
                text_format=ArtAppraisal
            )
            
            # Extract structured data from Responses API using output_parsed
            appraisal_data = response.output_parsed
            
            # Convert Pydantic model to dict and add painting info
            appraisal_dict = appraisal_data.model_dump()
            appraisal_dict['painting_info'] = painting_info
            
            return appraisal_dict
                
        except Exception as e:
            print(f"Error appraising painting {painting_info.get('title', 'Unknown')}: {e}")
            return None

    def load_paintings(self, paintings_file: str = "appraisals.json") -> Dict:
        """Load paintings data from previous run if it exists."""
        try:
            with open(paintings_file, 'r') as f:
                data = json.load(f)
                print(f"Loaded data: {len(data.get('paintings', []))} paintings found so far")
                return data
        except FileNotFoundError:
            return {"paintings": [], "processed_urls": set(), "last_page": 0, "last_item": 0}
        except Exception as e:
            print(f"Error loading paintings data: {e}")
            return {"paintings": [], "processed_urls": set(), "last_page": 0, "last_item": 0}

    def save_paintings(self, data: Dict, paintings_file: str = "appraisals.json"):
        """Save paintings data to file."""
        try:
            # Convert set to list for JSON serialization
            data_copy = data.copy()
            data_copy["processed_urls"] = list(data_copy["processed_urls"])
            
            with open(paintings_file, 'w') as f:
                json.dump(data_copy, f, indent=2)
        except Exception as e:
            print(f"Error saving paintings data: {e}")

    def run_appraisal(self, max_pages: int = 5, delay: float = 1.0, paintings_file: str = "appraisals.json") -> List[Dict]:
        """
        Run the full appraisal process on multiple pages of paintings with data saving.
        
        Args:
            max_pages: Maximum number of pages to process
            delay: Delay between API calls in seconds
            paintings_file: File to save/load paintings data
            
        Returns:
            List of appraisals for all paintings sorted by value
        """
        # Load previous data
        data = self.load_paintings(paintings_file)
        paintings_list = data["paintings"]
        processed_urls = set(data["processed_urls"])
        start_page = max(1, data["last_page"])
        start_item = data["last_item"]
        
        try:
            for page in range(start_page, max_pages + 1):
                print(f"\n--- Processing page {page} ---")
                
                # Get list of paintings on this page
                paintings = self.get_paintings_list(page)
                
                if not paintings:
                    print(f"No paintings found on page {page}, stopping")
                    break
                
                # Start from the right item if resuming
                start_index = start_item if page == start_page else 0
                
                for i, painting_basic in enumerate(paintings[start_index:], start_index):
                    # Skip if already processed
                    if painting_basic['url'] in processed_urls:
                        continue
                    
                    print(f"\nProcessing painting {i+1}/{len(paintings)}: {painting_basic['title']}")
                    
                    try:
                        # Note: API already filters for active auctions when active_auctions_only=True
                        # No need for additional client-side filtering since API does this efficiently
                        
                        # Get detailed painting information
                        painting_details = self.get_painting_details(painting_basic['url'], painting_basic['item_id'])
                        if not painting_details:
                            processed_urls.add(painting_basic['url'])
                            continue
                        
                        # Appraise the painting
                        appraisal = self.appraise_painting(painting_details)
                        if not appraisal:
                            processed_urls.add(painting_basic['url'])
                            continue
                        
                        best_estimate = appraisal.get('estimated_value_best', 0)
                        # Ensure best_estimate is a number
                        if isinstance(best_estimate, str):
                            try:
                                best_estimate = float(best_estimate.replace('$', '').replace(',', ''))
                            except:
                                best_estimate = 0
                        
                        # Add all appraisals to the list
                        paintings_list.append(appraisal)
                        
                        # Print detailed appraisal findings to console
                        self.print_appraisal_findings(appraisal)
                        
                        print(f"📊 APPRAISED: ${best_estimate:,.2f} - {painting_details['title']}")
                        print(f"   URL: {painting_details['url']}")
                        print("─" * 80)
                    
                        processed_urls.add(painting_basic['url'])
                        
                        # Update data
                        data.update({
                            "paintings": paintings_list,
                            "processed_urls": processed_urls,
                            "last_page": page,
                            "last_item": i + 1
                        })
                        
                        # Save data every 5 items
                        if (i + 1) % 5 == 0:
                            self.save_paintings(data, paintings_file)
                        
                        # Rate limiting
                        time.sleep(delay)
                        
                    except Exception as e:
                        print(f"Error processing painting {painting_basic['title']}: {e}")
                        processed_urls.add(painting_basic['url'])
                        # Save data after error
                        data.update({
                            "paintings": paintings_list,
                            "processed_urls": processed_urls,
                            "last_page": page,
                            "last_item": i + 1
                        })
                        self.save_paintings(data, paintings_file)
                        continue
                
                # Reset start_item for next page
                start_item = 0
                
                # Save data after each page
                data.update({
                    "paintings": paintings_list,
                    "processed_urls": processed_urls,
                    "last_page": page + 1,
                    "last_item": 0
                })
                self.save_paintings(data, paintings_file)
                
                # Brief pause between pages
                time.sleep(2)
        finally:
            # Final data save
            self.save_paintings(data, paintings_file)
        
        # Sort all paintings by estimated value (highest first)
        paintings_list.sort(key=lambda x: self._get_numeric_value(x.get('estimated_value_best', 0)), reverse=True)
        
        return paintings_list
    
    def _get_numeric_value(self, value):
        """Convert a value to numeric for sorting."""
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value.replace('$', '').replace(',', ''))
            except:
                return 0
        return 0



    def print_appraisal_findings(self, appraisal: Dict):
        """Print detailed appraisal findings for a single painting."""
        painting = appraisal['painting_info']
        
        print(f"\n🎨 DETAILED APPRAISAL FINDINGS")
        print(f"{'='*60}")
        print(f"Title: {painting['title']}")
        print(f"Artist: {painting['artist']}")
        print(f"Medium: {painting['medium']}")
        print(f"Dimensions: {painting.get('dimensions', 'Unknown')}")
        print(f"Current Price: {painting['current_price']}")
        print(f"Listing URL: {painting['url']}")
        
        print(f"\n💰 VALUATION:")
        print(f"   Range: ${appraisal.get('estimated_value_min', 0):,.2f} - ${appraisal.get('estimated_value_max', 0):,.2f}")
        print(f"   Best Estimate: ${appraisal.get('estimated_value_best', 0):,.2f}")
        print(f"   Confidence Level: {appraisal.get('confidence_level', 'Unknown')}")
        print(f"   Market Category: {appraisal.get('market_category', 'Unknown')}")
        
        print(f"\n🔍 ANALYSIS:")
        if appraisal.get('reasoning'):
            print(f"   Reasoning: {appraisal['reasoning']}")
        
        if appraisal.get('artist_market_status'):
            print(f"   Artist Market Status: {appraisal['artist_market_status']}")
        
        if appraisal.get('web_search_summary'):
            print(f"   Web Research: {appraisal['web_search_summary']}")
        
        if appraisal.get('recent_sales_data'):
            print(f"   Recent Sales: {appraisal['recent_sales_data']}")
        
        if appraisal.get('comparable_works'):
            print(f"   Comparable Works: {appraisal['comparable_works']}")
        
        if appraisal.get('authentication_notes'):
            print(f"   Authentication: {appraisal['authentication_notes']}")
        
        if appraisal.get('risk_factors'):
            print(f"   Risk Factors: {appraisal['risk_factors']}")

    def print_summary(self, results: List[Dict]):
        """Print a summary of all paintings sorted by estimated value."""
        if not results:
            print(f"\nNo paintings were appraised.")
            return
        
        print(f"\n{'='*60}")
        print(f"SUMMARY: Found {len(results)} paintings sorted by estimated value")
        print(f"{'='*60}")
        
        for i, appraisal in enumerate(results, 1):
            painting = appraisal['painting_info']
            print(f"\n{i}. {painting['title']}")
            print(f"   Artist: {painting['artist']}")
            print(f"   Current Price: {painting['current_price']}")
            print(f"   Estimated Value: ${appraisal['estimated_value_best']:,.2f}")
            print(f"   Confidence: {appraisal['confidence_level']}")
            print(f"   URL: {painting['url']}")
            if appraisal.get('reasoning'):
                print(f"   Reasoning: {appraisal['reasoning'][:200]}...")
            if appraisal.get('research_summary'):
                print(f"   Research: {appraisal['research_summary'][:150]}...")
            if appraisal.get('authentication_notes'):
                print(f"   Authentication: {appraisal['authentication_notes'][:100]}...")


def main():
    parser = argparse.ArgumentParser(description='Appraise paintings from ShopGoodwill.com')
    parser.add_argument('--max-pages', type=int, default=1000,
                      help='Maximum number of pages to process (default: 1000)')
    parser.add_argument('--delay', type=float, default=1.0,
                      help='Delay between API calls in seconds (default: 1.0)')
    parser.add_argument('--paintings-file', default='appraisals.json',
                      help='Paintings data file for storing results and progress (default: appraisals.json)')
    parser.add_argument('--include-ended-auctions', dest='include_ended_auctions', action='store_true', default=False,
                      help='Include ended auctions as well')
    parser.add_argument('--no-include-ended-auctions', dest='include_ended_auctions', action='store_false',
                      help='Only process paintings with active auctions (default)')
    
    args = parser.parse_args()
    
    # Handle auction filtering logic
    active_auctions_only = not args.include_ended_auctions
    
    # Get API key from environment variable
    api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set!")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        print("Get your API key from: https://platform.openai.com/")
        sys.exit(1)
    
    auction_filter_msg = "active auctions only" if active_auctions_only else "all auctions (including ended)"
    print(f"Starting painting appraisal ({auction_filter_msg})")
    print(f"Processing up to {args.max_pages} pages")
    
    # Initialize the appraiser
    appraiser = PaintingAppraiser(api_key, active_auctions_only)
    
    try:
        # Run the appraisal
        results = appraiser.run_appraisal(args.max_pages, args.delay, args.paintings_file)
        
        # Display results (they're already saved in the paintings file)
        print(f"\nResults saved to {args.paintings_file}")
        appraiser.print_summary(results)
        
        # Print just the URLs for easy copying (sorted by value)
        if results:
            print(f"\n{'='*60}")
            print("PAINTING URLS (SORTED BY VALUE - HIGHEST FIRST):")
            print(f"{'='*60}")
            for appraisal in results:
                best_estimate = appraiser._get_numeric_value(appraisal.get('estimated_value_best', 0))
                print(f"${best_estimate:,.2f} - {appraisal['painting_info']['url']}")
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()