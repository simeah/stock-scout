# StockScout

AI-powered stock news tracker for retail investors.

## Features
- Fetch 100+ articles per stock from Google News + SEC EDGAR
- Semantic deduplication with Claude
- LLM scoring by stock impact
- Email briefs with thesis hits
- History tracking to avoid duplicates
- Support for Claude, Gemini, and GPT-4 APIs

## Setup
1. Clone: `git clone https://github.com/YOUR_USERNAME/stock-scout.git`
2. Install: `pip install -r requirements.txt`
3. Configure: Copy `.env.example` to `.env` and add your API keys
4. Run: `streamlit run app.py`

## API Keys
- Google (Gemini): https://aistudio.google.com/app/apikey (FREE)
- Anthropic (Claude): https://console.anthropic.com/settings/keys
- OpenAI (GPT-4): https://platform.openai.com/api-keys

## Usage
1. Go to Setup page and create your portfolio
2. Go to Run Tracker and click "Run Pipeline"
3. Review results and send email

## License
MIT
EOF
