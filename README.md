# Treasure Hunter

A Python script that automatically appraises paintings from shopgoodwill.com using OpenAI's advanced reasoning models with web search capabilities and identifies potentially valuable pieces.

## Quick Start

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Get OpenAI API key**: Visit [platform.openai.com](https://platform.openai.com/)
3. **Set environment variable**: `export OPENAI_API_KEY="your-key-here"`
4. **Run the appraiser**: `python appraise.py --url "https://shopgoodwill.com/item/123456"`

That's it! The script will analyze the painting and provide a detailed appraisal.

## Features

- **Multi-Image Analysis**: Uses all available images from listings for comprehensive visual analysis
- **Advanced AI Models**: Supports OpenAI's latest reasoning models (o3, o4-mini, gpt-4.1, etc.)
- **Real-Time Research**: Automatically searches for artist biographies, recent auction results, and market trends
- **Comprehensive Analysis**: Examines style, condition, signature, frame construction, and back markings
- **Detailed Output**: Provides artist info, dimensions, medium, time period, subject matter, quality assessment
- **Cost Tracking**: Real-time API usage monitoring with detailed cost breakdown
- **Flexible Processing**: Single URL analysis or batch processing of multiple pages
- **CSV Export**: Saves results with full appraisal data for analysis

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

### Single Painting Analysis

```bash
# Analyze a specific painting
python appraise.py --url "https://shopgoodwill.com/item/237853018"

# Use a specific model
python appraise.py --url "https://shopgoodwill.com/item/237853018" --model gpt-4o

# Limit number of images
python appraise.py --url "https://shopgoodwill.com/item/237853018" --max-images 3
```

### Batch Processing

```bash
# Process multiple pages of paintings
python appraise.py --max-pages 5

# Include ended auctions
python appraise.py --max-pages 3 --include-ended-auctions

# Custom delay and file output
python appraise.py --max-pages 2 --delay 1.5 --appraisals-file my_appraisals.csv
```

### Command Line Arguments

- `--url`: Analyze a specific painting URL instead of batch processing
- `--model`: OpenAI model to use (default: o4-mini)
- `--max-images`: Maximum number of images to send to AI (default: all available)
- `--max-pages`: Maximum number of pages to process (default: 1000)
- `--delay`: Delay between API calls in seconds (default: 0.0)
- `--appraisals-file`: CSV file for storing results (default: appraisals.csv)
- `--include-ended-auctions`: Include ended auctions in batch processing
- `--no-include-ended-auctions`: Only process active auctions (default)

### Available Models

- `o4-mini` (default) - Latest reasoning model, great balance of cost and performance
- `o3` - Advanced reasoning for complex analysis
- `gpt-4o` - Multimodal capabilities
- `gpt-4o-mini` - Cost-effective option
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano` - Latest GPT models

## Example Output

### Single Painting Analysis

```
Single painting appraisal using all available images
Model: o4-mini

📝 TITLE: Beautiful Landscape Painting
🔗 LISTING URL: https://shopgoodwill.com/item/237853018
🏷️ CURRENT PRICE: $25.00
🖼️ IMAGES (3): [List of image URLs]

🎨 ARTIST: John Smith (b. 1940)
📏 DIMENSIONS: 16" x 20"
🖌️ MEDIUM: Oil on canvas
STYLE: Impressionist
TIME PERIOD: Late 20th century
SUBJECT MATTER: Landscape
CONDITION: Good with minor frame wear
QUALITY: Professional level
SIGNATURE: Signed lower right "J. Smith"
BACK MARKINGS: Gallery label from Smith Gallery, NYC
FRAME CONSTRUCTION: Traditional wood frame with canvas stretchers

💎 VALUATION:
   Range: $150.00 - $300.00
   Best Estimate: $225.00

💰 API USAGE: $0.0234 | 1,500 input + 800 output + 400 reasoning = 2,700 tokens
```

### Cost Summary

```
💰 FINAL COST SUMMARY:
==================================================
Total Requests: 3
Input Tokens: 4,500
  └─ Cached: 0
  └─ Fresh: 4,500
Output Tokens: 2,400
Reasoning Tokens: 1,200
Total Tokens: 8,100
Estimated Input Cost: $0.0495
Estimated Output Cost: $0.1056
  └─ Includes 1,200 reasoning tokens
Estimated Total Cost: $0.1551
Model: o4-mini
```

## Output Files

The script generates a CSV file containing detailed appraisal information with the following columns:

- Basic info: URL, title, current price, estimated values, confidence
- Artist details: Artist name, style, time period
- Physical details: Medium, dimensions, condition, quality
- Analysis: Subject matter, signature details, back markings, frame construction
- Research: Reasoning, risk factors, market category, web search summary
- Technical: All available image URLs, API data

## How It Works

1. **Image Extraction**: Scrapes all available images from the listing (not just the main image)
2. **Multi-Image Analysis**: Sends up to your specified limit of images to the AI for comprehensive analysis
3. **AI Appraisal**: Uses advanced reasoning models to analyze artistic quality, style, and market value
4. **Real-Time Research**: Built-in web search finds artist information, recent sales, and market data
5. **Comprehensive Output**: Provides detailed analysis including frame construction, signature details, and back markings
6. **Cost Tracking**: Monitors API usage with real-time cost calculation including reasoning tokens

## Important Notes

### Cost Management

- **Real-time tracking**: See costs for each request and session totals
- **Model selection**: Choose appropriate model for your budget (o4-mini is most cost-effective)
- **Image limits**: Use `--max-images` to control costs for listings with many images
- **Reasoning tokens**: Advanced models generate reasoning tokens (included in output token costs)

### Model Pricing (per 1M tokens)

| Model | Input | Output | Cached |
|-------|-------|---------|---------|
| o4-mini | $1.10 | $4.40 | $0.275 |
| gpt-4o | $2.50 | $10.00 | $1.25 |
| gpt-4o-mini | $0.15 | $0.60 | $0.075 |
| gpt-4.1 | $2.00 | $8.00 | $0.50 |

### Accuracy Disclaimer

- AI appraisals are estimates based on visual analysis combined with web research
- The tool provides comprehensive analysis but cannot verify authenticity
- Actual values depend on provenance, condition, and current market conditions
- Always consult professional appraisers for important decisions
- Use this tool as a sophisticated screening mechanism

### Enhanced Analysis Features

- **Frame Analysis**: Examines frame construction, stretcher bars, and joints for period indicators
- **Back Markings**: Looks for auction house labels, gallery stickers, and exhibition tags
- **Signature Study**: Detailed analysis of signatures, monograms, and artist stamps
- **Multi-Image Context**: Uses all available images for more accurate condition and authenticity assessment

## Troubleshooting

### Common Issues

1. **"OPENAI_API_KEY environment variable not set"**:
   - Set the environment variable: `export OPENAI_API_KEY="your-key"`
   - Verify the key format (should start with "sk-")

2. **High API costs**:
   - Use `--model gpt-4o-mini` for cheaper analysis
   - Limit images with `--max-images 2`
   - Monitor costs with built-in tracking

3. **Model errors**:
   - Verify your API key has access to the specified model
   - Try a different model if one is unavailable
   - Check OpenAI service status

## Example Use Cases

- **Art Collectors**: Comprehensive analysis before bidding with multiple image examination
- **Dealers**: Professional-level screening with detailed condition and authenticity notes
- **Researchers**: Market analysis with cost tracking for budget management
- **Appraisers**: AI-assisted evaluation with detailed technical analysis

## Recent Improvements

- **Multi-image analysis**: Now uses all available images instead of just the main image
- **Advanced models**: Support for latest OpenAI reasoning models (o3, o4-mini)
- **Cost tracking**: Real-time API usage and cost monitoring
- **Enhanced analysis**: Frame construction, back markings, and signature analysis
- **Better output**: Structured display with comprehensive details
- **Flexible processing**: Single URL or batch processing modes

## Contributing

Feel free to submit improvements, bug fixes, or feature requests! The codebase is actively maintained and enhanced.

## License

This project is for educational and personal use. Please respect the terms of service of the websites and APIs used.