# Painting Appraiser for ShopGoodwill.com

A Python script that automatically appraises paintings from shopgoodwill.com using OpenAI's Responses API with web search capabilities and identifies potentially valuable pieces above a specified threshold.

## Quick Start

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Get OpenAI API key**: Visit [platform.openai.com](https://platform.openai.com/)
3. **Set environment variable**: `export OPENAI_API_KEY="your-key-here"`
4. **Run the appraiser**: `python appraise.py --threshold 500`

That's it! The script will find paintings estimated above $500 and output their URLs.

## Features

- **Automated Scraping**: Scrapes painting listings from ShopGoodwill.com
- **AI-Powered Appraisal**: Uses OpenAI's Responses API with built-in web search to research artists and market data
- **Real-Time Research**: Automatically searches for artist biographies, recent auction results, and market trends
- **Authentication Analysis**: Cross-references known works and signatures for authenticity assessment
- **Intelligent Filtering**: Only returns paintings estimated above your value threshold
- **Comprehensive Analysis**: Considers artistic quality, technique, condition, and market demand
- **Detailed Output**: Saves results with reasoning, confidence levels, research summaries, and authentication notes

## Installation

1. Clone or download this repository
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Setup

1. **Verify Dependencies**:
   Make sure you have Python 3.7+ installed.

2. **Get an OpenAI API Key**:
   - Visit [OpenAI's website](https://platform.openai.com/)
   - Create an account or sign in
   - Go to API Keys section and create a new API key
   - Keep this key secure and don't share it

3. **Set Environment Variable**:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

## Usage

### Basic Usage

```bash
python appraise.py --threshold 500
```

### Advanced Usage

```bash
python appraise.py \
  --threshold 1000 \
  --max-pages 5 \
  --delay 2.0 \
  --output my_valuable_paintings.json
```

### Command Line Arguments

- `--threshold`: Minimum estimated value in USD (default: 500)
- `--max-pages`: Maximum number of pages to process (default: 3)
- `--delay`: Delay between API calls in seconds (default: 1.0)
- `--output`: Output JSON filename (default: valuable_paintings.json)

## Example Output

The script will display progress as it runs:

```
Starting painting appraisal with threshold: $500.00
Processing up to 3 pages

--- Processing page 1 ---
Found 40 paintings on page 1

Processing painting 1/40: Women in a Gallery by Richard Frank James
✅ VALUABLE: $1,200.00 - Women in a Gallery by Richard Frank James (20th Cent.)-Oil on Canvas-Signed
   URL: https://shopgoodwill.com/item/237684201

Processing painting 2/40: Victorian Musician Family in Park
   Estimated value: $300.00 (below threshold)

...

===============================================================
SUMMARY: Found 3 paintings above $500.00
===============================================================

1. Women in a Gallery by Richard Frank James (20th Cent.)-Oil on Canvas-Signed
   Artist: Richard Frank James (20th Cent.)
   Current Price: $126.00
   Estimated Value: $1,200.00
   Confidence: medium
   URL: https://shopgoodwill.com/item/237684201
   Reasoning: This oil painting demonstrates solid academic technique with good composition...
   Research: Found recent auction results for Richard Frank James showing strong market demand...
   Authentication: Signature appears consistent with known examples from this period...

===============================================================
VALUABLE PAINTING URLS:
===============================================================
https://shopgoodwill.com/item/237684201
https://shopgoodwill.com/item/237684529
https://shopgoodwill.com/item/237465054
```

## Output Files

The script generates a JSON file (default: `valuable_paintings.json`) containing detailed appraisal information:

```json
[
  {
    "estimated_value_min": 800,
    "estimated_value_max": 1500,
    "estimated_value_best": 1200,
    "confidence_level": "medium",
    "reasoning": "This oil painting demonstrates solid academic technique...",
    "risk_factors": "Unknown provenance, condition shows some wear...",
    "market_category": "20th Century American",
    "research_summary": "Web search revealed recent auction sales of $800-1400 for similar works...",
    "authentication_notes": "Signature matches documented examples, painting style consistent with known works",
    "painting_info": {
      "url": "https://shopgoodwill.com/item/237684201",
      "title": "Women in a Gallery by Richard Frank James",
      "image_url": "https://shopgoodwill.com/images/...",
      "current_price": "$126.00",
      "artist": "Richard Frank James (20th Cent.)",
      "medium": "Oil on Canvas",
      "dimensions": "approx. 48\" L x 2.5\" W x 38.5\" H"
    }
  }
]
```

## How It Works

1. **Scraping**: The script visits ShopGoodwill.com's painting category and extracts links to individual paintings
2. **Detail Extraction**: For each painting, it visits the detail page to get high-resolution images and metadata
3. **AI Appraisal**: Sends the image and metadata to OpenAI's Responses API with web search enabled
4. **Real-Time Research**: The AI searches the web for artist information, recent sales, and authentication data
5. **Analysis**: Combines visual analysis with market research for comprehensive appraisal
6. **Filtering**: Only keeps paintings with estimated values above your threshold
7. **Output**: Saves detailed results with research summaries and displays a summary

## Important Notes

### Rate Limiting
- The script includes built-in delays to respect website and API limits
- Increase `--delay` if you encounter rate limiting issues
- OpenAI API calls cost money - each appraisal with GPT-4o + web search costs approximately $0.03-0.07

### Accuracy Disclaimer
- AI appraisals are estimates based on visual analysis combined with web research
- While the tool searches for market data and artist information, it cannot verify authenticity
- Actual values depend on many factors including provenance, condition, and market conditions
- Always consult professional appraisers for important decisions
- Use this tool as a screening mechanism, not as definitive valuation

### Legal Considerations
- Respect ShopGoodwill.com's terms of service
- Don't overload their servers with too many rapid requests
- This tool is for personal research purposes

## Troubleshooting

### Common Issues

1. **"OPENAI_API_KEY environment variable not set"**:
   - Make sure you've set the environment variable: `export OPENAI_API_KEY="your-key"`
   - Check the key is correct (should start with "sk-")

2. **"No paintings found"**:
   - Check your internet connection
   - The website structure may have changed
   - Try reducing the number of pages

3. **OpenAI API Errors**:
   - Verify your API key is correct
   - Check you have sufficient API credits
   - Increase the delay between requests

4. **Image Loading Errors**:
   - Some painting images may not load properly
   - The script will skip these and continue

### Getting Help

If you encounter issues:
1. Check that your OPENAI_API_KEY environment variable is set correctly
2. Check the error messages for specific details
3. Try running with fewer pages first (`--max-pages 1`)
4. Increase the delay between requests (`--delay 3.0`)

## Example Use Cases

- **Collectors**: Screen for undervalued pieces before bidding
- **Dealers**: Identify potential inventory opportunities
- **Researchers**: Analyze pricing trends in online art markets
- **Hobbyists**: Learn about art valuation and market dynamics

## Cost Estimation

- OpenAI API costs: ~$0.03-0.07 per painting analyzed (including web search)
- Processing 100 paintings: ~$3-7 in API costs
- Processing 1000 paintings: ~$30-70 in API costs
- Web search adds precision but increases cost - the enhanced accuracy is usually worth it

## Contributing

Feel free to submit improvements, bug fixes, or feature requests!

## License

This project is for educational and personal use. Please respect the terms of service of the websites and APIs used.