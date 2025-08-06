#!/usr/bin/env python3
"""
Painting Appraiser for ShopGoodwill.com

This script scrapes paintings from shopgoodwill.com, uses OpenAI's Responses API with web search to appraise them,
and outputs URLs of paintings estimated to be worth more than a given threshold.

Usage:
    export OPENAI_API_KEY="your-api-key-here"
    python appraise.py --threshold 500

Requirements:
    pip install requests beautifulsoup4 openai playwright
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import openai
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from playwright.sync_api import sync_playwright
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
    def __init__(self, openai_api_key: str, threshold: float = 500.0):
        """
        Initialize the painting appraiser.
        
        Args:
            openai_api_key: OpenAI API key
            threshold: Minimum estimated value threshold in USD
        """
        self.client = OpenAI(api_key=openai_api_key)
        self.threshold = threshold
        self.base_url = "https://shopgoodwill.com"
        self.playwright = None
        self.browser = None
        self.page = None

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



    def start_browser(self):
        """Start Playwright browser for scraping."""
        if self.playwright is None:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.page = self.browser.new_page()
            self.page.set_viewport_size({"width": 1920, "height": 1080})

    def stop_browser(self):
        """Stop Playwright browser and clean up resources."""
        if self.page:
            self.page.close()
            self.page = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        
    def get_paintings_list(self, page: int = 1) -> List[Dict]:
        """
        Scrape the paintings listing page to get basic info about all paintings using Playwright.
        
        Args:
            page: Page number to scrape
            
        Returns:
            List of painting dictionaries with basic info
        """
        if not self.page:
            self.start_browser()
        
        try:
            # Use the correct ShopGoodwill paintings URL with proper category filtering
            url = f"{self.base_url}/categories/listing?p={page}&st=&sg=Keyword&c=71&s=&lp=0&hp=999999&sbn=&spo=false&snpo=true&socs=false&sd=false&sca=false&caed=8%2F5%2F2025&cadb=7&scs=false&sis=false&col=1&ps=40&desc=false&ss=0&UseBuyerPrefs=true&sus=false&cln=1&catIds=-1,15,71&pn=&wc=false&mci=false&hmt=false&layout=grid&ihp="
            print(f"Navigating to: {url}")
            
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # Wait for dynamic content to load
            try:
                self.page.wait_for_selector('a[href*="/item/"]', timeout=10000)
            except:
                # If no items found, try alternative selectors
                try:
                    self.page.wait_for_selector('.item-title', timeout=5000)
                except:
                    print(f"No items found on page {page}")
                    return []
            
            paintings = []
            
            # Find all item links using different possible selectors
            selectors_to_try = [
                'a[href*="/item/"]',
                '.item-title a',
                '.product-title a',
                'a[href*="item"]'
            ]
            
            item_links = []
            for selector in selectors_to_try:
                links = self.page.query_selector_all(selector)
                if links:
                    item_links = links
                    print(f"Found {len(links)} links with selector: {selector}")
                    break
            
            if not item_links:
                print(f"No item links found on page {page}")
                return []
            
            seen_items = set()
            for link in item_links:
                try:
                    href = link.get_attribute('href')
                    if not href or href in seen_items:
                        continue
                    
                    # Ensure full URL
                    if href.startswith('/'):
                        href = self.base_url + href
                    
                    # Extract item ID
                    match = re.search(r'/item/(\d+)', href)
                    if not match:
                        continue
                    
                    item_id = match.group(1)
                    seen_items.add(href)
                    
                    # Get title
                    title = link.inner_text().strip() if link.inner_text() else f"Painting {item_id}"
                    
                    # Try to find price in the same container
                    price_text = ""
                    try:
                        # Look for price in parent container
                        parent = link.locator('xpath=..//..')
                        price_element = parent.locator('text=/\\$[\\d,]+\\.\\d{2}/').first
                        if price_element.is_visible():
                            price_text = price_element.inner_text().strip()
                    except:
                        pass
                    
                    paintings.append({
                        'item_id': item_id,
                        'url': href,
                        'title': title,
                        'current_price': price_text
                    })
                    
                except Exception as e:
                    print(f"Error processing link: {e}")
                    continue
            
            print(f"Found {len(paintings)} paintings on page {page}")
            return paintings
            
        except Exception as e:
            print(f"Error fetching paintings list: {e}")
            return []

    def get_painting_details(self, painting_url: str) -> Optional[Dict]:
        """
        Get detailed information about a specific painting using Playwright.
        
        Args:
            painting_url: URL to the painting's detail page
            
        Returns:
            Dictionary with detailed painting info or None if failed
        """
        if not self.page:
            self.start_browser()
            
        try:
            print(f"Fetching details from: {painting_url}")
            self.page.goto(painting_url, wait_until="domcontentloaded", timeout=15000)
            
            # Wait for page content to load - ShopGoodwill uses heavy JavaScript
            self.page.wait_for_timeout(5000)
            
            # Try to wait for actual content to appear (not just "Please wait!")
            try:
                self.page.wait_for_selector('h1', timeout=10000)
            except:
                print(f"Content may not have fully loaded for {painting_url}")
                # Continue anyway, but with a longer timeout
            
            # Extract title first (needed for image matching)
            title = "Unknown Title"
            try:
                title_element = self.page.query_selector('h1')
                if title_element:
                    title = title_element.inner_text().strip()
                else:
                    title = self.page.title()
            except:
                pass
            
            # Extract main image URL - ShopGoodwill hides the main product image
            image_url = None
            
            # Wait a bit more for images to load
            self.page.wait_for_timeout(3000)
            
            # First, look for the hidden product image (often has sr-only class)
            all_images = self.page.query_selector_all('img')
            print(f"Found {len(all_images)} images on the page")
            
            for img in all_images:
                src = img.get_attribute('src')
                alt = img.get_attribute('alt') or ''
                class_name = img.get_attribute('class') or ''
                
                if src and self._is_valid_product_image(src):
                    # Check if this looks like a product image
                    # ShopGoodwill product images often have the item title in alt text
                    title_words = title.lower().split()
                    alt_words = alt.lower().split()
                    
                    # If alt text has significant overlap with title, it's likely the product image
                    if len(title_words) > 3 and len(alt_words) > 3:
                        common_words = set(title_words) & set(alt_words)
                        if len(common_words) >= 3:  # At least 3 words in common
                            image_url = src if src.startswith('http') else self.base_url + src
                            break
                    
                    # Check for item-specific URL patterns
                    if '/Items/' in src and any(pattern in src.lower() for pattern in ['jpg', 'jpeg', 'png']):
                        image_url = src if src.startswith('http') else self.base_url + src
                        break
            
            # Fallback: try traditional selectors if nothing found
            if not image_url:
                image_selectors = [
                    'img[src*="production"][src*="Items"]',  # ShopGoodwill item path
                    'img[src*="/item/"]',  # Look for item-specific images
                    '.product-image img',
                    '.item-image img', 
                    'img[src*="images"]:not([src*="logo"]):not([src*="icon"])',  # Images but not logos/icons
                ]
                
                for selector in image_selectors:
                    try:
                        img_element = self.page.query_selector(selector)
                        if img_element:
                            src = img_element.get_attribute('src')
                            if src and self._is_valid_product_image(src):
                                image_url = src if src.startswith('http') else self.base_url + src
                                break
                    except:
                        continue
            
            # Extract current price - try multiple approaches
            current_price = "Unknown"
            price_selectors = [
                'text=/Current Price.*\\$[\\d,]+\\.\\d{2}/',
                'text=/\\$[\\d,]+\\.\\d{2}/',
                '.price',
                '.current-price'
            ]
            
            for selector in price_selectors:
                try:
                    price_element = self.page.query_selector(selector)
                    if price_element:
                        price_text = price_element.inner_text()
                        price_match = re.search(r'\\$[\\d,]+\\.\\d{2}', price_text)
                        if price_match:
                            current_price = price_match.group()
                            break
                except:
                    continue
            
            # Extract description
            description = ""
            desc_selectors = [
                'text=/Item Description/',
                '.description',
                '.item-description'
            ]
            
            for selector in desc_selectors:
                try:
                    desc_element = self.page.query_selector(selector)
                    if desc_element:
                        # Get the next element that contains the description
                        parent = desc_element.locator('xpath=..')
                        description = parent.inner_text().strip()
                        break
                except:
                    continue
            
            # Extract artist, medium, dimensions from page text
            page_text = self.page.inner_text('body')
            
            # Extract artist
            artist = "Unknown Artist"
            artist_match = re.search(r'Artist[:\\s]+([^\\n]+)', page_text, re.IGNORECASE)
            if artist_match:
                artist = artist_match.group(1).strip()
            
            # Extract medium
            medium = "Unknown Medium"
            medium_match = re.search(r'Media[:\\s]+([^\\n]+)', page_text, re.IGNORECASE)
            if medium_match:
                medium = medium_match.group(1).strip()
            
            # Extract dimensions
            dimensions = ""
            dim_match = re.search(r'Frame Size[^\\n]*[:\\s]+([^\\n]+)', page_text, re.IGNORECASE)
            if dim_match:
                dimensions = dim_match.group(1).strip()
            
            return {
                'url': painting_url,
                'title': title,
                'image_url': image_url,
                'current_price': current_price,
                'artist': artist,
                'medium': medium,
                'dimensions': dimensions,
                'description': description
            }
            
        except Exception as e:
            print(f"Error fetching painting details from {painting_url}: {e}")
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

            CRITICAL APPRAISAL GUIDELINES:
            - If NO market data, auction records, or recognition is found for the artist, treat as UNKNOWN ARTIST
            - Unknown artists typically sell for $25-$200 depending on size, quality, and decorative appeal
            - Only established artists with documented sales history should be valued above $500
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
            # Start browser for scraping
            self.start_browser()
            
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
                        # Get detailed painting information
                        painting_details = self.get_painting_details(painting_basic['url'])
                        if not painting_details:
                            processed_urls.add(painting_basic['url'])
                            continue
                        
                        # Appraise the painting
                        appraisal = self.appraise_painting(painting_details)
                        if not appraisal:
                            processed_urls.add(painting_basic['url'])
                            continue
                        
                        # Check if it meets our threshold
                        best_estimate = appraisal.get('estimated_value_best', 0)
                        # Ensure best_estimate is a number
                        if isinstance(best_estimate, str):
                            try:
                                best_estimate = float(best_estimate.replace('$', '').replace(',', ''))
                            except:
                                best_estimate = 0
                        
                        # Add all paintings regardless of threshold (we'll sort later)
                        paintings_list.append(appraisal)
                        print(f"📊 APPRAISED: ${best_estimate:,.2f} - {painting_details['title']}")
                        print(f"   URL: {painting_details['url']}")
                    
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
            # Always stop the browser when done
            self.stop_browser()
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
    parser.add_argument('--threshold', type=float, default=500.0,
                      help='Minimum estimated value threshold in USD (default: 500)')
    parser.add_argument('--max-pages', type=int, default=3,
                      help='Maximum number of pages to process (default: 3)')
    parser.add_argument('--delay', type=float, default=1.0,
                      help='Delay between API calls in seconds (default: 1.0)')
    parser.add_argument('--paintings-file', default='appraisals.json',
                      help='Paintings data file for storing results and progress (default: appraisals.json)')
    
    args = parser.parse_args()
    
    # Get API key from environment variable
    api_key = os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set!")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        print("Get your API key from: https://platform.openai.com/")
        sys.exit(1)
    
    print(f"Starting painting appraisal (all paintings will be sorted by value)")
    print(f"Processing up to {args.max_pages} pages")
    
    # Initialize the appraiser
    appraiser = PaintingAppraiser(api_key, args.threshold)
    
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