#!/usr/bin/env python3
"""
Painting Appraiser for ShopGoodwill.com

This script fetches paintings from shopgoodwill.com using their API, uses OpenAI's Responses API with web search to appraise them,
and outputs URLs of paintings.

Usage:
    export OPENAI_API_KEY="your-api-key-here"
    python appraise.py

Requirements:
    pip install requests beautifulsoup4 openai pillow python-dateutil pandas
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from openai import OpenAI

from pydantic import BaseModel


class PaintingInfo(BaseModel):
    """Information about a painting listing."""
    url: str
    title: str
    image_url: Optional[str] = None
    current_price: str = "Unknown"
    description: str = ""
    item_id: Optional[str] = None
    api_data: Optional[Dict] = None


class Appraisal(BaseModel):
    """Complete appraisal result for a painting."""
    estimated_value_min: float
    estimated_value_max: float
    estimated_value_best: float
    confidence_level: str
    reasoning: str
    risk_factors: str
    market_category: str
    web_search_summary: str
    recent_sales_data: str
    artist_market_status: str
    authentication_notes: str
    comparable_works: str
    artist: str
    description_summary: str
    medium: str
    dimensions: str
    painting_info: PaintingInfo


class AppraisalResponse(BaseModel):
    """Response format for AI-generated appraisal data from OpenAI API."""
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
    artist: str  # Artist name extracted from title, description, or signature analysis
    description_summary: str  # Brief summary of the artwork based on title and description
    medium: str  # Medium/materials used (oil on canvas, watercolor, acrylic, etc.)
    dimensions: str  # Size/dimensions of the artwork if available


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
        
    def get_paintings_list(self, page: int = 1) -> List[PaintingInfo]:
        """
        Get paintings listing using the API endpoint instead of web scraping.
        
        Args:
            page: Page number to fetch
            
        Returns:
            List of PaintingInfo objects with basic info
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
                    
                    painting_info = PaintingInfo(
                        url=url,
                        title=title,
                        current_price=current_price,
                        item_id=item_id,
                        api_data=item
                    )
                    paintings.append(painting_info)
                    
                except Exception as e:
                    print(f"Error processing item: {e}")
                    continue
            
            print(f"Found {len(paintings)} paintings on page {page}")
            return paintings
            
        except Exception as e:
            print(f"Error fetching paintings list from API: {e}")
            return []

    def get_painting_details(self, painting_url: str, item_id: str = None) -> Optional[PaintingInfo]:
        """
        Get detailed information about a specific painting using the API endpoint.
        
        Args:
            painting_url: URL to the painting's detail page
            item_id: Item ID (extracted from URL if not provided)
            
        Returns:
            PaintingInfo object with detailed painting info or None if failed
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
            
            return PaintingInfo(
                url=painting_url,
                title=title,
                image_url=image_url,
                current_price=current_price,
                description=description,
                item_id=item_id,
                api_data=data
            )
            
        except Exception as e:
            print(f"Error fetching painting details from API for item {item_id}: {e}")
            return None

    def appraise_painting(self, painting_info: PaintingInfo) -> Optional[Appraisal]:
        """
        Use OpenAI GPT-4o multimodal API to appraise a painting with enhanced research-style prompts that encourage thorough analysis.
        
        Args:
            painting_info: PaintingInfo object with painting information including image_url
            
        Returns:
            Appraisal object with appraisal results or None if failed
        """
        if not painting_info.image_url:
            print(f"No image URL for painting: {painting_info.title}")
            return None
        
        # Use the image URL directly since we now find proper JPEG images
        image_url = painting_info.image_url
        
        try:
            # Construct the prompt for appraisal with web search capabilities
            prompt = f"""
            You are an expert art appraiser with access to real-time market data through web search. Analyze this painting and provide a comprehensive market appraisal.

            Known Information:
            - Title: {painting_info.title}
            - Description: {painting_info.description[:1000]}...

            REQUIRED: Use web search to research the following before making your appraisal:
            
            1. Artist Market Research:
               - Search for the artist name if present in the title, description, or signature in the image, 
                 appending "auction sold" to find auction results
               - Look for biography, career highlights, and market recognition
               - Find recent sales data and price trends
            
            2. Comparable Works:
               - Search for similar paintings based on title and description, appending "auction sold" to find 
                 auction results
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

            After completing your web research, analyze the image and provide:
            1. Artistic quality and technique
            2. Historical significance or style period
            3. Condition (based on what you can see)
            4. Market demand and recent sales data
            5. Artist recognition and career status
            6. Authentication likelihood
            7. Artist name extracted from title, description, or visible signature
            8. Brief description summary of the artwork
            9. Medium/materials used (oil on canvas, watercolor, acrylic, etc.)
            10. Dimensions/size of the artwork if visible or mentioned

            Provide your response using the structured output format with comprehensive analysis including web research findings.
            """
            
            # Debug: Print the image URL being sent to OpenAI
            print(f"📝 TITLE: {painting_info.title}")
            print(f"🔗 LISTING URL: {painting_info.url}")
            print(f"💵 CURRENT PRICE: {painting_info.current_price}")
            print(f"🖼️ IMAGE URL: {image_url}")
            
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
                text_format=AppraisalResponse
            )
            
            # Extract structured data from Responses API using output_parsed
            appraisal_response = response.output_parsed
            
            # Create Appraisal object with the extracted data and painting info
            appraisal = Appraisal(
                estimated_value_min=appraisal_response.estimated_value_min,
                estimated_value_max=appraisal_response.estimated_value_max,
                estimated_value_best=appraisal_response.estimated_value_best,
                confidence_level=appraisal_response.confidence_level,
                reasoning=appraisal_response.reasoning,
                risk_factors=appraisal_response.risk_factors,
                market_category=appraisal_response.market_category,
                web_search_summary=appraisal_response.web_search_summary,
                recent_sales_data=appraisal_response.recent_sales_data,
                artist_market_status=appraisal_response.artist_market_status,
                authentication_notes=appraisal_response.authentication_notes,
                comparable_works=appraisal_response.comparable_works,
                artist=appraisal_response.artist,
                description_summary=appraisal_response.description_summary,
                medium=appraisal_response.medium,
                dimensions=appraisal_response.dimensions,
                painting_info=painting_info
            )
            
            return appraisal
                
        except Exception as e:
            print(f"Error appraising painting {painting_info.title}: {e}")
            return None

    def load_appraisals(self, appraisals_file: str = "appraisals.csv") -> Dict:
        """Load appraisal data from CSV file using pandas."""
        try:
            df = pd.read_csv(appraisals_file)
            appraisals = []
            processed_urls = set()
            
            for _, row in df.iterrows():
                # Create PaintingInfo object
                painting_info = PaintingInfo(
                    url=str(row['url']),
                    title=str(row['title']),
                    image_url=str(row['image_url']),
                    current_price=str(row['current_price']),
                    description=str(row['description'])
                )
                
                # Create Appraisal object
                appraisal = Appraisal(
                    estimated_value_min=float(row['estimated_value_min']),
                    estimated_value_max=float(row['estimated_value_max']),
                    estimated_value_best=float(row['estimated_value_best']),
                    confidence_level=str(row['confidence_level']),
                    reasoning=str(row['reasoning']),
                    risk_factors=str(row['risk_factors']),
                    market_category=str(row['market_category']),
                    web_search_summary=str(row['web_search_summary']),
                    recent_sales_data=str(row['recent_sales_data']),
                    artist_market_status=str(row['artist_market_status']),
                    authentication_notes=str(row['authentication_notes']),
                    comparable_works=str(row['comparable_works']),
                    artist=str(row.get('artist', '')),
                    description_summary=str(row.get('description_summary', '')),
                    medium=str(row.get('medium', '')),
                    dimensions=str(row.get('dimensions', '')),
                    painting_info=painting_info
                )
                appraisals.append(appraisal)
                processed_urls.add(str(row['url']))
            
            print(f"Loaded data: {len(appraisals)} appraisals found so far")
            return {"appraisals": appraisals, "processed_urls": processed_urls, "last_page": 0, "last_item": 0}
            
        except FileNotFoundError:
            return {"appraisals": [], "processed_urls": set(), "last_page": 0, "last_item": 0}
        except Exception as e:
            print(f"Error loading appraisal data: {e}")
            return {"appraisals": [], "processed_urls": set(), "last_page": 0, "last_item": 0}

    def save_appraisals(self, data: Dict, appraisals_file: str = "appraisals.csv"):
        """Save appraisal data to CSV file using pandas, sorted by descending appraisal value."""
        try:
            appraisals = data["appraisals"]
            
            # Flatten the Appraisal objects for pandas DataFrame
            rows = []
            for appraisal in appraisals:
                row = {
                    'estimated_value_best': appraisal.estimated_value_best,
                    'estimated_value_min': appraisal.estimated_value_min,
                    'estimated_value_max': appraisal.estimated_value_max,
                    'confidence_level': appraisal.confidence_level,
                    'market_category': appraisal.market_category,
                    'reasoning': appraisal.reasoning,
                    'risk_factors': appraisal.risk_factors,
                    'web_search_summary': appraisal.web_search_summary,
                    'recent_sales_data': appraisal.recent_sales_data,
                    'artist_market_status': appraisal.artist_market_status,
                    'authentication_notes': appraisal.authentication_notes,
                    'comparable_works': appraisal.comparable_works,
                    'artist': appraisal.artist,
                    'description_summary': appraisal.description_summary,
                    'medium': appraisal.medium,
                    'dimensions': appraisal.dimensions,
                    'title': appraisal.painting_info.title,
                    'current_price': appraisal.painting_info.current_price,
                    'url': appraisal.painting_info.url,
                    'image_url': appraisal.painting_info.image_url or '',
                    'description': appraisal.painting_info.description
                }
                rows.append(row)
            
            # Create DataFrame and sort by estimated_value_best descending
            df = pd.DataFrame(rows)
            if not df.empty:
                df = df.sort_values('estimated_value_best', ascending=False)
            
            # Define column order
            column_order = [
                'estimated_value_best', 'estimated_value_min', 'estimated_value_max',
                'confidence_level', 'market_category', 
                'title', 'artist', 'description_summary', 'medium', 'dimensions', 'current_price', 'url', 'image_url',
                'reasoning', 'risk_factors', 'web_search_summary', 'recent_sales_data',
                'artist_market_status', 'authentication_notes', 'comparable_works', 'description'
            ]
            
            # Reorder columns and save to CSV
            df = df[column_order]
            df.to_csv(appraisals_file, index=False, encoding='utf-8')
            
            print(f"Saved {len(df)} appraisals to {appraisals_file} (sorted by value)")
                    
        except Exception as e:
            print(f"Error saving appraisal data: {e}")

    def run_appraisal(self, max_pages: int = 1000, delay: float = 0.0, appraisals_file: str = "appraisals.csv") -> List[Appraisal]:
        """
        Run the full appraisal process on multiple pages of paintings with appraisal data saving.
        
        Args:
            max_pages: Maximum number of pages to process
            delay: Delay between API calls in seconds
            appraisals_file: File to save/load appraisal data
            
        Returns:
            List of Appraisal objects for all paintings sorted by value
        """
        # Load previous data
        data = self.load_appraisals(appraisals_file)
        appraisals_list = data["appraisals"]
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
                    if painting_basic.url in processed_urls:
                        continue
                    
                    print(f"\nProcessing painting {i+1}/{len(paintings)}: {painting_basic.title}")
                    
                    try:
                        # Note: API already filters for active auctions when active_auctions_only=True
                        # No need for additional client-side filtering since API does this efficiently
                        
                        # Get detailed painting information
                        painting_details = self.get_painting_details(painting_basic.url, painting_basic.item_id)
                        if not painting_details:
                            processed_urls.add(painting_basic.url)
                            continue
                        
                        # Appraise the painting
                        appraisal = self.appraise_painting(painting_details)
                        if not appraisal:
                            processed_urls.add(painting_basic.url)
                            continue
                        
                        best_estimate = appraisal.estimated_value_best
                        # Ensure best_estimate is a number
                        if isinstance(best_estimate, str):
                            try:
                                best_estimate = float(best_estimate.replace('$', '').replace(',', ''))
                            except:
                                best_estimate = 0
                        
                        # Add all appraisals to the list
                        appraisals_list.append(appraisal)
                        
                        # Print detailed appraisal findings to console
                        self.print_appraisal_findings(appraisal)
                        print("─" * 80)
                    
                        processed_urls.add(painting_basic.url)
                        
                        # Update data
                        data.update({
                            "appraisals": appraisals_list,
                            "processed_urls": processed_urls,
                            "last_page": page,
                            "last_item": i + 1
                        })
                        
                        # Save data every 5 items (sorted by value)
                        if (i + 1) % 5 == 0:
                            self.save_appraisals(data, appraisals_file)
                        
                        # Rate limiting
                        time.sleep(delay)
                        
                    except Exception as e:
                        print(f"Error processing painting {painting_basic.title}: {e}")
                        processed_urls.add(painting_basic.url)
                        # Save data after error
                        data.update({
                            "appraisals": appraisals_list,
                            "processed_urls": processed_urls,
                            "last_page": page,
                            "last_item": i + 1
                        })
                        self.save_appraisals(data, appraisals_file)
                        continue
                
                # Reset start_item for next page
                start_item = 0
                
                # Save data after each page
                data.update({
                    "appraisals": appraisals_list,
                    "processed_urls": processed_urls,
                    "last_page": page + 1,
                    "last_item": 0
                })
                self.save_appraisals(data, appraisals_file)
                
                # Brief pause between pages
                time.sleep(2)
        finally:
            # Final data save
            self.save_appraisals(data, appraisals_file)
        
        # Sort all appraisals by estimated value (highest first)
        appraisals_list.sort(key=lambda x: self._get_numeric_value(x.estimated_value_best), reverse=True)
        
        return appraisals_list
    
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



    def print_appraisal_findings(self, appraisal: Appraisal):
        """Print detailed appraisal findings for a single painting."""
        painting = appraisal.painting_info
        
        print(f"\n🎨 APPRAISAL FINDINGS:")
        print(f"{'='*60}")
        print(f"ARTIST: {appraisal.artist or 'Unknown'}")
        print(f"MEDIUM: {appraisal.medium or 'Unknown'}")
        print(f"DIMENSIONS: {appraisal.dimensions or 'Unknown'}")
        
        print(f"\n💰 VALUATION:")
        print(f"   Range: ${appraisal.estimated_value_min:,.2f} - ${appraisal.estimated_value_max:,.2f}")
        print(f"   Best Estimate: ${appraisal.estimated_value_best:,.2f}")
        print(f"   Confidence Level: {appraisal.confidence_level}")
        print(f"   Market Category: {appraisal.market_category}")
        
        print(f"\n🔍 ANALYSIS:")
        if appraisal.reasoning:
            print(f"   Reasoning: {appraisal.reasoning}")
        
        if appraisal.artist_market_status:
            print(f"   Artist Market Status: {appraisal.artist_market_status}")
        
        if appraisal.web_search_summary:
            print(f"   Web Research: {appraisal.web_search_summary}")
        
        if appraisal.recent_sales_data:
            print(f"   Recent Sales: {appraisal.recent_sales_data}")
        
        if appraisal.comparable_works:
            print(f"   Comparable Works: {appraisal.comparable_works}")
        
        if appraisal.authentication_notes:
            print(f"   Authentication: {appraisal.authentication_notes}")
        
        if appraisal.risk_factors:
            print(f"   Risk Factors: {appraisal.risk_factors}")

    def print_summary(self, results: List[Appraisal]):
        """Print a summary of all paintings sorted by estimated value."""
        if not results:
            print(f"\nNo paintings were appraised.")
            return
        
        print(f"\n{'='*60}")
        print(f"SUMMARY: Found {len(results)} paintings sorted by estimated value")
        print(f"{'='*60}")
        
        for i, appraisal in enumerate(results, 1):
            painting = appraisal.painting_info
            print(f"\n{i}. {painting.title}")
            print(f"   Artist: {appraisal.artist or 'Unknown'}")
            if appraisal.description_summary:
                print(f"   Description: {appraisal.description_summary[:150]}...")
            if appraisal.medium:
                print(f"   Medium: {appraisal.medium}")
            if appraisal.dimensions:
                print(f"   Dimensions: {appraisal.dimensions}")
            print(f"   Current Price: {painting.current_price}")
            print(f"   Estimated Value: ${appraisal.estimated_value_best:,.2f}")
            print(f"   Confidence: {appraisal.confidence_level}")
            print(f"   URL: {painting.url}")
            if appraisal.reasoning:
                print(f"   Reasoning: {appraisal.reasoning[:200]}...")
            if appraisal.web_search_summary:
                print(f"   Research: {appraisal.web_search_summary[:150]}...")
            if appraisal.authentication_notes:
                print(f"   Authentication: {appraisal.authentication_notes[:100]}...")


def main():
    parser = argparse.ArgumentParser(description='Appraise paintings from ShopGoodwill.com')
    parser.add_argument('--max-pages', type=int, default=1000,
                      help='Maximum number of pages to process (default: 1000)')
    parser.add_argument('--delay', type=float, default=0.0,
                      help='Delay between API calls in seconds (default: 1.0)')
    parser.add_argument('--appraisals-file', dest='appraisals_file', default='appraisals.csv',
                      help='Appraisals data file for storing results and progress (default: appraisals.csv)')
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
        results = appraiser.run_appraisal(args.max_pages, args.delay, args.appraisals_file)
        
        # Display results (they're already saved in the appraisals file)
        print(f"\nResults saved to {args.appraisals_file}")
        appraiser.print_summary(results)
        
        # Print just the URLs for easy copying (sorted by value)
        if results:
            print(f"\n{'='*60}")
            print("PAINTING URLS (SORTED BY VALUE - HIGHEST FIRST):")
            print(f"{'='*60}")
            for appraisal in results:
                best_estimate = appraiser._get_numeric_value(appraisal.estimated_value_best)
                print(f"${best_estimate:,.2f} - {appraisal.painting_info.url}")
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()