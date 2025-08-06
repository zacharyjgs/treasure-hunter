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


# OpenAI Model Pricing (2025 rates per 1M tokens)
# Note: Reasoning tokens are priced the same as output tokens
MODEL_PRICING = {
    "o4-mini": {"input": 1.10, "output": 4.40, "cached": 0.275},
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached": 0.075},
    "gpt-4.1": {"input": 2.00, "output": 8.00, "cached": 0.50},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60, "cached": 0.10},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40, "cached": 0.025},
    "nectarine-alpha-2025-07-25": {"input": 0.00, "output": 0.00, "cached": 0.00},
    "nectarine-alpha-new-minimal-effort-2025-07-25": {"input": 0.00, "output": 0.00, "cached": 0.00},
}


class PaintingInfo(BaseModel):
    """Information about a painting listing."""
    url: str
    title: str
    image_url: Optional[str] = None  # Primary image URL for backward compatibility
    image_urls: List[str] = []  # All available image URLs
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
    style: str
    time_period: str
    subject_matter: str
    condition: str
    quality: str
    signature_details: str
    back_markings: str
    frame_construction: str
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
    style: str  # Artistic style (e.g., Impressionist, Abstract, Realist, etc.)
    time_period: str  # Estimated time period or era when created
    subject_matter: str  # What the artwork depicts (landscape, portrait, still life, etc.)
    condition: str  # Overall condition assessment based on visible condition
    quality: str  # Overall artistic quality assessment (e.g., Excellent, Good, Average, Poor)
    signature_details: str  # Description of signature, monogram, or stamp found on artwork
    back_markings: str  # Auction house labels, gallery stickers, exhibition tags, or other back markings
    frame_construction: str  # Details about frame, stretcher bars, joints, and construction methods


class PaintingAppraiser:
    def __init__(self, openai_api_key: str, active_auctions_only: bool = True, max_images: Optional[int] = None, model: str = "o4-mini"):
        """
        Initialize the painting appraiser.
        
        Args:
            openai_api_key: OpenAI API key
            active_auctions_only: Only process paintings with active auctions
            max_images: Maximum number of images to send to AI per painting (None for no limit)
            model: OpenAI model to use for appraisal (default: o4-mini)
        """
        self.client = OpenAI(api_key=openai_api_key)
        self.active_auctions_only = active_auctions_only
        self.max_images = max_images
        self.model = model
        self.base_url = "https://shopgoodwill.com"
        
        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0
        self.total_reasoning_tokens = 0
        self.total_tokens = 0
        self.total_requests = 0

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
            
            # Get all image URLs from imageUrlString
            image_url = None
            image_urls = []
            image_url_string = data.get('imageUrlString', '')
            if image_url_string:
                # Split by semicolon to get all image paths
                image_paths = image_url_string.split(';')
                image_server = data.get('imageServer', 'https://shopgoodwillimages.azureedge.net/production/')
                
                for i, image_path in enumerate(image_paths):
                    if image_path.strip():
                        clean_path = image_path.replace('\\', '/').strip()
                        full_image_url = f"{image_server}{clean_path}"
                        
                        # Validate that this is a proper product image
                        if self._is_valid_product_image(full_image_url):
                            image_urls.append(full_image_url)
                            
                            # Set the first valid image as the primary image for backward compatibility
                            if image_url is None:
                                image_url = full_image_url
            
            return PaintingInfo(
                url=painting_url,
                title=title,
                image_url=image_url,
                image_urls=image_urls,
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
            painting_info: PaintingInfo object with painting information including image_urls
            
        Returns:
            Appraisal object with appraisal results or None if failed
        """
        # Use all available images, fallback to primary image if image_urls is empty
        available_images = painting_info.image_urls if painting_info.image_urls else ([painting_info.image_url] if painting_info.image_url else [])
        
        if not available_images:
            print(f"No image URLs for painting: {painting_info.title}")
            return None
        
        # Limit number of images if max_images is specified
        if self.max_images is not None and len(available_images) > self.max_images:
            available_images = available_images[:self.max_images]
            print(f"📋 Limiting to {self.max_images} images (out of {len(painting_info.image_urls)} available)")
        
        try:
            # Construct the prompt for appraisal with web search capabilities
            prompt = f"""
            You are an expert art appraiser with access to real-time market data through web search. Analyze this painting and provide a comprehensive market appraisal.

            NOTE: You will be provided with {len(available_images)} image(s) of this artwork. Please examine all images carefully as they may show different angles, details, signatures, or conditions that are important for your assessment.

            STEP 1 - BASIC IDENTIFICATION:
            Examine all provided images carefully and determine:
            1. Artist name - Look for signatures, monograms, or stamps in the image; also check if artist is mentioned in title/description
            2. Signature details - Describe any visible signatures, monograms, stamps, or artist marks found on the artwork
            3. Medium/materials used - Identify if it's oil on canvas, watercolor, acrylic, pastel, print, etc.
            4. Dimensions/size - Note the artwork size if visible or mentioned in the description
            5. Style and time period - Analyze the artistic style and estimate when it was created
            6. Subject matter - Describe what the artwork depicts
            7. Overall condition - Note any visible damage, wear, or restoration
            8. Frame construction - Examine and describe the frame, stretcher bars, joinery methods, and construction details as these can indicate the artwork's age and period value
            9. Back markings - Look for auction house labels, gallery stickers, exhibition tags, or other markings that indicate provenance
            10. Quality assessment - Evaluate the artistic quality (technique, composition, execution) as Excellent, Good, Average, or Poor

            STEP 2 - RESEARCH AND AUTHENTICATION:
            Use web search to research the following:
            
            1. Artist Market Research:
               - Search for the artist name (from Step 1) appending "auction sold" to find auction results
               - Look for biography, career highlights, and market recognition
               - Find recent sales data and price trends
            
            2. Comparable Works:
               - Search for similar paintings by this artist or similar style/medium
               - Look for works with similar subject matter, medium, and size
               - Find current market trends for this type of art
            
            3. Authentication Research:
               - Search for known works and signatures by this artist
               - Look for any authentication guides or red flags
               - Check museum collections or catalogs
               - Verify if the signature style matches known examples

            STEP 3 - FINAL ANALYSIS:
            Synthesize findings from Steps 1 and 2 for comprehensive valuation:

            1. ARTIST CATEGORIZATION & MARKET POSITIONING:
               - ESTABLISHED ARTIST: Has documented sales history, museum recognition, or auction records
               - UNKNOWN ARTIST: No market data, auction records, or recognition found - be extremely conservative (typically $10-$300 range)
               - For unknown artists: value based primarily on size, quality, and decorative appeal
               - Cross-reference technical quality with artist's known skill level and career status

            2. AUTHENTICATION & CONDITION IMPACT:
               - Verify signature style matches research findings; note any red flags
               - Assess condition impact on value and factor restoration costs
               - Examine frame construction, stretcher bars, and joinery methods as period indicators
               - Check for auction house labels, gallery tags, or exhibition markings that establish provenance
               - Consider attribution certainty (signed vs. attributed vs. uncertain)

            3. MARKET VALUATION WITH BIAS ADJUSTMENT:
               - Compare to recent auction sales and market comparables
               - IMPORTANT: Online sales platforms often show inflated "sold" prices due to selection bias, 
                 marketing tactics, and non-representative samples
               - Factor in current market trends for style/period/subject matter
               - Provide conservative estimates that account for quick sale scenarios

            4. RISK FACTORS & FINAL JUSTIFICATION:
               - Address attribution gaps, condition issues, and market volatility
               - Explain valuation rationale based on all research findings
               - Be especially conservative with unknown/unverified artists

            Complete ALL 3 STEPS and provide your response using the structured output format with comprehensive analysis including all web research findings.
            
            Known Information:
            - Title: {painting_info.title}
            - Description: {painting_info.description[:1000]}...
            """
            
            # Debug: Print the image URLs being sent to OpenAI
            print(f"📝 TITLE: {painting_info.title}")
            print(f"🔗 LISTING URL: {painting_info.url}")
            print(f"🏷️ CURRENT PRICE: {painting_info.current_price}")
            print(f"🖼️ IMAGES ({len(available_images)}): {available_images}")
            
            # Build content array with text prompt and all available images
            content = [{"type": "input_text", "text": prompt}]
            
            # Add all available images to the content
            for i, image_url in enumerate(available_images):
                content.append({
                    "type": "input_image", 
                    "image_url": image_url
                })
            
            # Use Responses API with web search and structured outputs
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": content
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
            
            # Extract cost information from response
            usage = response.usage if hasattr(response, 'usage') else None
            if usage:
                input_tokens = usage.input_tokens if hasattr(usage, 'input_tokens') else 0
                output_tokens = usage.output_tokens if hasattr(usage, 'output_tokens') else 0
                total_tokens = usage.total_tokens if hasattr(usage, 'total_tokens') else (input_tokens + output_tokens)
                
                # Extract cached tokens from input_tokens_details
                cached_tokens = 0
                if hasattr(usage, 'input_tokens_details') and usage.input_tokens_details:
                    cached_tokens = getattr(usage.input_tokens_details, 'cached_tokens', 0)
                fresh_input_tokens = input_tokens - cached_tokens
                
                # Extract reasoning tokens from output_tokens_details
                reasoning_tokens = 0
                if hasattr(usage, 'output_tokens_details') and usage.output_tokens_details:
                    reasoning_tokens = getattr(usage.output_tokens_details, 'reasoning_tokens', 0)
                
                # Update running totals
                self.total_input_tokens += input_tokens
                self.total_output_tokens += output_tokens
                self.total_cached_tokens += cached_tokens
                self.total_reasoning_tokens += reasoning_tokens
                self.total_tokens += total_tokens
                self.total_requests += 1
                
                # Calculate cost for this request using helper method
                cost_breakdown = self._calculate_cost(input_tokens, output_tokens, cached_tokens, reasoning_tokens, self.model)
            
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
                style=appraisal_response.style,
                time_period=appraisal_response.time_period,
                subject_matter=appraisal_response.subject_matter,
                condition=appraisal_response.condition,
                quality=appraisal_response.quality,
                signature_details=appraisal_response.signature_details,
                back_markings=appraisal_response.back_markings,
                frame_construction=appraisal_response.frame_construction,
                painting_info=painting_info
            )

            self.print_appraisal_findings(appraisal)
            
            # Display API usage information at the end
            if usage:
                # Display condensed cost and token info on single line
                if "error" not in cost_breakdown:
                    if reasoning_tokens > 0:
                        if cached_tokens > 0:
                            print(f"\n💰 API USAGE: ${cost_breakdown['total_cost']:.4f} | {fresh_input_tokens:,} fresh + {cached_tokens:,} cached + {output_tokens:,} output + {reasoning_tokens:,} reasoning = {total_tokens:,} tokens")
                        else:
                            print(f"\n💰 API USAGE: ${cost_breakdown['total_cost']:.4f} | {input_tokens:,} input + {output_tokens:,} output + {reasoning_tokens:,} reasoning = {total_tokens:,} tokens")
                    else:
                        if cached_tokens > 0:
                            print(f"\n💰 API USAGE: ${cost_breakdown['total_cost']:.4f} | {fresh_input_tokens:,} fresh + {cached_tokens:,} cached + {output_tokens:,} output = {total_tokens:,} tokens")
                        else:
                            print(f"\n💰 API USAGE: ${cost_breakdown['total_cost']:.4f} | {input_tokens:,} input + {output_tokens:,} output = {total_tokens:,} tokens")
                else:
                    print(f"\n💰 API USAGE: Cost calculation error | {total_tokens:,} tokens")
            else:
                print(f"\n💰 API USAGE: Usage data not available")
            
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
                # Parse image_urls from semicolon-separated string if available
                image_urls_str = str(row.get('image_urls', ''))
                image_urls = [url.strip() for url in image_urls_str.split(';') if url.strip()] if image_urls_str else []
                
                painting_info = PaintingInfo(
                    url=str(row['url']),
                    title=str(row['title']),
                    image_url=str(row['image_url']),
                    image_urls=image_urls,
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
                    style=str(row.get('style', '')),
                    time_period=str(row.get('time_period', '')),
                    subject_matter=str(row.get('subject_matter', '')),
                    condition=str(row.get('condition', '')),
                    quality=str(row.get('quality', '')),
                    signature_details=str(row.get('signature_details', '')),
                    back_markings=str(row.get('back_markings', '')),
                    frame_construction=str(row.get('frame_construction', '')),
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
                    'style': appraisal.style,
                    'time_period': appraisal.time_period,
                    'subject_matter': appraisal.subject_matter,
                    'condition': appraisal.condition,
                    'quality': appraisal.quality,
                    'signature_details': appraisal.signature_details,
                    'back_markings': appraisal.back_markings,
                    'frame_construction': appraisal.frame_construction,
                    'title': appraisal.painting_info.title,
                    'current_price': appraisal.painting_info.current_price,
                    'url': appraisal.painting_info.url,
                    'image_url': appraisal.painting_info.image_url or '',
                    'image_urls': ';'.join(appraisal.painting_info.image_urls) if appraisal.painting_info.image_urls else '',
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
                'title', 'artist', 'description_summary', 'medium', 'dimensions', 'style', 'time_period', 'subject_matter', 'condition', 'quality', 'signature_details', 'back_markings', 'frame_construction', 'current_price', 'url', 'image_url', 'image_urls',
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
                        print("─" * 80)
                        
                        best_estimate = appraisal.estimated_value_best
                        # Ensure best_estimate is a number
                        if isinstance(best_estimate, str):
                            try:
                                best_estimate = float(best_estimate.replace('$', '').replace(',', ''))
                            except:
                                best_estimate = 0
                        
                        # Add all appraisals to the list
                        appraisals_list.append(appraisal)                                    
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

    def print_appraisal_findings(self, appraisal: Appraisal):
        """Print detailed appraisal findings for a single painting."""
        painting = appraisal.painting_info
        
        print(f"\n🎨 APPRAISAL FINDINGS:")
        print(f"{'='*60}")
        print(f"ARTIST: {appraisal.artist or 'Unknown'}")
        print(f"MEDIUM: {appraisal.medium or 'Unknown'}")
        print(f"DIMENSIONS: {appraisal.dimensions or 'Unknown'}")
        print(f"STYLE: {appraisal.style or 'Unknown'}")
        print(f"TIME PERIOD: {appraisal.time_period or 'Unknown'}")
        print(f"SUBJECT MATTER: {appraisal.subject_matter or 'Unknown'}")
        print(f"CONDITION: {appraisal.condition or 'Unknown'}")
        print(f"QUALITY: {appraisal.quality or 'Unknown'}")
        print(f"SIGNATURE: {appraisal.signature_details or 'Not specified'}")
        print(f"BACK MARKINGS: {appraisal.back_markings or 'None noted'}")
        print(f"FRAME CONSTRUCTION: {appraisal.frame_construction or 'Not analyzed'}")
        
        print(f"\n💎 VALUATION:")
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
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int, cached_tokens: int, reasoning_tokens: int = 0, model: str = "o4-mini") -> dict:
        """
        Calculate cost breakdown for given token usage.
        
        Args:
            input_tokens: Total input tokens
            output_tokens: Total output tokens (includes reasoning tokens)
            cached_tokens: Cached input tokens
            reasoning_tokens: Reasoning tokens (for display only - already included in output_tokens)
            model: Model name for pricing lookup
            
        Returns:
            Dictionary with cost breakdown
        """
        if model not in MODEL_PRICING:
            return {"error": f"Unknown model: {model}"}
            
        pricing = MODEL_PRICING[model]
        fresh_input_tokens = input_tokens - cached_tokens
        
        fresh_input_cost = (fresh_input_tokens / 1_000_000) * pricing["input"]
        cached_input_cost = (cached_tokens / 1_000_000) * pricing["cached"]
        input_cost = fresh_input_cost + cached_input_cost
        output_cost = (output_tokens / 1_000_000) * pricing["output"]  # Already includes reasoning tokens
        total_cost = input_cost + output_cost
        
        return {
            "fresh_input_cost": fresh_input_cost,
            "cached_input_cost": cached_input_cost,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "reasoning_tokens": reasoning_tokens,  # For display purposes
            "total_cost": total_cost,
            "model": model
        }

    def print_cost_summary(self):
        """Print final cost summary for the session."""
        print(f"\n💰 FINAL COST SUMMARY:")
        print(f"{'='*50}")
        print(f"Total Requests: {self.total_requests}")
        print(f"Input Tokens: {self.total_input_tokens:,}")
        print(f"  └─ Cached: {self.total_cached_tokens:,}")
        print(f"  └─ Fresh: {self.total_input_tokens - self.total_cached_tokens:,}")
        print(f"Output Tokens: {self.total_output_tokens:,}")
        if self.total_reasoning_tokens > 0:
            print(f"Reasoning Tokens: {self.total_reasoning_tokens:,}")
        print(f"Total Tokens: {self.total_tokens:,}")
        
        if self.total_tokens > 0:
            # Calculate estimated costs using helper method
            cost_breakdown = self._calculate_cost(
                self.total_input_tokens, 
                self.total_output_tokens, 
                self.total_cached_tokens,
                self.total_reasoning_tokens,
                self.model
            )
            
            if "error" not in cost_breakdown:
                print(f"Estimated Input Cost: ${cost_breakdown['input_cost']:.4f}")
                if self.total_cached_tokens > 0:
                    print(f"  └─ Fresh input: ${cost_breakdown['fresh_input_cost']:.4f}")
                    print(f"  └─ Cached input: ${cost_breakdown['cached_input_cost']:.4f}")
                print(f"Estimated Output Cost: ${cost_breakdown['output_cost']:.4f}")
                if self.total_reasoning_tokens > 0:
                    print(f"  └─ Includes {self.total_reasoning_tokens:,} reasoning tokens")
                print(f"Estimated Total Cost: ${cost_breakdown['total_cost']:.4f}")
                print(f"Model: {cost_breakdown['model']}")

    def appraise_single_url(self, painting_url: str) -> List[Appraisal]:
        """
        Appraise a single painting from a specific URL without saving to file.
        
        Args:
            painting_url: URL to the painting's detail page
            
        Returns:
            List containing single Appraisal object or empty list if failed
        """
        # Get painting details from the URL
        painting_info = self.get_painting_details(painting_url)
        if not painting_info:
            return []
        
        # Appraise the painting
        appraisal = self.appraise_painting(painting_info)
        if not appraisal:
            return []
        
        return [appraisal]


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
    parser.add_argument('--url', type=str,
                      help='Appraise a specific painting URL instead of scanning all paintings')
    parser.add_argument('--max-images', type=int, default=None,
                      help='Maximum number of images to send to AI for each painting (default: no limit)')
    parser.add_argument('--model', type=str, default='o4-mini',
                      help='OpenAI model to use for appraisal (default: o4-mini)')
    
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
    max_images_msg = f"max {args.max_images} images per painting" if args.max_images else "all available images"
    if not args.url:
        print(f"Starting painting appraisal ({auction_filter_msg})")
        print(f"Processing up to {args.max_pages} pages")
        print(f"Using {max_images_msg}")
        print(f"Model: {args.model}")
    else:
        print(f"Single painting appraisal using {max_images_msg}")
        print(f"Model: {args.model}")
    
    # Initialize the appraiser
    appraiser = PaintingAppraiser(api_key, active_auctions_only, args.max_images, args.model)
    
    try:
        # Run appraisal (single URL or batch)
        if args.url:
            results = appraiser.appraise_single_url(args.url)
            print(f"\nSingle URL appraisal completed")
        else:
            results = appraiser.run_appraisal(args.max_pages, args.delay, args.appraisals_file)
            print(f"\nResults saved to {args.appraisals_file}")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        # Always show cost summary at the end
        appraiser.print_cost_summary()


if __name__ == "__main__":
    main()