from flask import Flask, render_template, jsonify, request
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import logging
from pathlib import Path
import threading
import time

# Load .env file if it exists (Windows-friendly)
def load_env_file():
    env_file = Path('.env')
    if env_file.exists():
        print(f"📄 Loading .env file from {env_file.absolute()}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")  # Remove quotes
                    os.environ[key] = value
                    print(f"   ✅ Set {key} = {value[:10]}...")

# Load environment variables
load_env_file()

# Check API key immediately after loading
API_KEY = os.getenv('GEMINI_API_KEY')
if API_KEY:
    print(f"🔑 API Key loaded successfully (preview: {API_KEY[:10]}...)")
else:
    print("❌ WARNING: GEMINI_API_KEY not found in environment or .env file")
    print("💡 Create a .env file with: GEMINI_API_KEY=your_key_here")

# Import processors
from gemini_rest_processor import GeminiRestProcessor, DataProcessor
from scraper import HealthSafetyScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global status tracking
scraping_status = {
    'running': False,
    'progress': 0,
    'message': 'Ready to scrape',
    'last_run': None,
    'files_created': []
}

processing_status = {
    'running': False,
    'progress': 0,
    'message': 'Ready to process',
    'last_run': None,
    'files_created': []
}

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('automated_dashboard.html')

@app.route('/api/scrape', methods=['POST'])
def start_scraping():
    """Start automated scraping in background"""
    if scraping_status['running']:
        return jsonify({'error': 'Scraping already in progress'}), 400
    
    # Start scraping in background thread
    thread = threading.Thread(target=run_scraping_task)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Scraping started', 'status': 'running'})

@app.route('/api/process', methods=['POST'])
def start_processing():
    """Start automated processing in background"""
    if processing_status['running']:
        return jsonify({'error': 'Processing already in progress'}), 400
    
    max_articles = request.json.get('max_articles', 10) if request.json else 10
    
    # Start processing in background thread
    thread = threading.Thread(target=run_processing_task, args=(max_articles,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Processing started', 'status': 'running'})

@app.route('/api/scrape_and_process', methods=['POST'])
def scrape_and_process():
    """Run complete automated workflow"""
    if scraping_status['running'] or processing_status['running']:
        return jsonify({'error': 'Another task is already running'}), 400
    
    max_articles = request.json.get('max_articles', 10) if request.json else 10
    
    # Start complete workflow in background
    thread = threading.Thread(target=run_complete_workflow, args=(max_articles,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Complete workflow started', 'status': 'running'})

@app.route('/api/status')
def get_status():
    """Get current status of scraping and processing"""
    return jsonify({
        'scraping': scraping_status,
        'processing': processing_status
    })

@app.route('/api/latest_summary')
def get_latest_summary():
    """Get the latest processed summary for dashboard"""
    try:
        processed_files = list(Path('.').glob('processed_articles_*.json'))
        if not processed_files:
            return jsonify({'error': 'No processed data found. Run scrape & process first.'}), 404
            
        latest_file = max(processed_files, key=os.path.getctime)
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error retrieving summary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/articles')
def get_articles():
    """Get processed articles for display"""
    try:
        processed_files = list(Path('.').glob('processed_articles_*.json'))
        if not processed_files:
            return jsonify({'error': 'No processed data found. Run scrape & process first.'}), 404
            
        latest_file = max(processed_files, key=os.path.getctime)
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify({
            'articles': data.get('articles', []),
            'total': data.get('processed_articles', 0)
        })
        
    except Exception as e:
        logger.error(f"Error retrieving articles: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/env')
def debug_environment():
    """Debug endpoint to check environment variables"""
    api_key = os.getenv('GEMINI_API_KEY')
    return jsonify({
        'api_key_set': bool(api_key),
        'api_key_length': len(api_key) if api_key else 0,
        'api_key_preview': api_key[:10] + "..." if api_key and len(api_key) > 10 else None,
        'environment_vars': list(os.environ.keys())
    })

@app.route('/api/test_gemini')
def test_gemini_connection():
    """Test Gemini API connection"""
    try:
        # Use global API_KEY first
        api_key = API_KEY or os.getenv('GEMINI_API_KEY')
        if not api_key:
            return jsonify({
                'error': 'GEMINI_API_KEY not found', 
                'success': False,
                'env_file_exists': Path('.env').exists(),
                'help': 'Create .env file with GEMINI_API_KEY=your_key'
            }), 400
        
        # Test the connection
        processor = GeminiRestProcessor(api_key=api_key, model="gemini-2.0-flash")
        success = processor.test_connection()
        
        return jsonify({
            'success': success,
            'api_key_set': True,
            'message': 'Connection successful' if success else 'Connection failed'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/files')
def list_files():
    """List all generated files"""
    try:
        xml_files = list(Path('.').glob('health_safety_news_*.xml'))
        json_files = list(Path('.').glob('processed_articles_*.json'))
        
        files = []
        
        for file in xml_files:
            stat = file.stat()
            files.append({
                'name': file.name,
                'type': 'scraped_data',
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
            
        for file in json_files:
            stat = file.stat()
            files.append({
                'name': file.name,
                'type': 'processed_data',
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
        
        # Sort by creation time (newest first)
        files.sort(key=lambda x: x['created'], reverse=True)
        
        return jsonify({'files': files})
        
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return jsonify({'error': str(e)}), 500

# Background task functions
def run_scraping_task():
    """Background task to run scraping"""
    global scraping_status
    
    scraping_status['running'] = True
    scraping_status['progress'] = 0
    scraping_status['message'] = 'Initializing scraper...'
    
    try:
        scraper = HealthSafetyScraper()
        
        scraping_status['progress'] = 10
        scraping_status['message'] = 'Scraping Construction News...'
        
        # Get all links and content
        all_links, articles_content = scraper.scrape_all_sites(
            fetch_content=True, 
            max_articles_per_site=10
        )
        
        scraping_status['progress'] = 80
        scraping_status['message'] = 'Saving scraped data...'
        
        # Save the data
        xml_file, json_file = scraper.save_data(all_links, articles_content)
        
        scraping_status['progress'] = 100
        scraping_status['message'] = f'Scraping complete! Created {len(all_links)} links, {len(articles_content)} articles'
        scraping_status['last_run'] = datetime.now().isoformat()
        scraping_status['files_created'] = [xml_file, json_file]
        
        logger.info(f"Scraping completed: {xml_file}, {json_file}")
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        scraping_status['message'] = f'Scraping failed: {str(e)}'
        scraping_status['progress'] = 0
    finally:
        scraping_status['running'] = False

def run_processing_task(max_articles=10):
    """Background task to run Gemini processing"""
    global processing_status, API_KEY
    
    processing_status['running'] = True
    processing_status['progress'] = 0
    processing_status['message'] = 'Checking API key...'
    
    try:
        # Use the global API_KEY first, then try environment
        api_key = API_KEY or os.getenv('GEMINI_API_KEY')
        
        if not api_key:
            # Try loading .env again in this thread
            load_env_file()
            api_key = os.getenv('GEMINI_API_KEY')
        
        if not api_key:
            raise Exception("GEMINI_API_KEY not found. Please check your .env file or set environment variable.")
        
        processing_status['progress'] = 5
        processing_status['message'] = f'API key found ({len(api_key)} chars), finding scraped data...'
        
        # Find latest XML file
        xml_files = list(Path('.').glob('health_safety_news_*.xml'))
        if not xml_files:
            raise Exception("No scraped data found. Run scraping first.")
        
        latest_xml = max(xml_files, key=os.path.getctime)
        
        processing_status['progress'] = 10
        processing_status['message'] = f'Loading data from {latest_xml.name}...'
        
        # Load and process data - explicitly pass API key
        processor = DataProcessor(api_key=api_key, model="gemini-2.0-flash")
        articles = processor.load_scraped_data(latest_xml)
        
        processing_status['progress'] = 30
        processing_status['message'] = f'Processing {len(articles)} articles with Gemini...'
        
        processed_articles = processor.process_articles_with_gemini(articles, max_articles)
        
        processing_status['progress'] = 80
        processing_status['message'] = 'Generating dashboard summary...'
        
        dashboard_summary = processor.gemini.generate_dashboard_summary(processed_articles)
        
        processing_status['progress'] = 90
        processing_status['message'] = 'Saving processed data...'
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'processed_articles_{timestamp}.json'
        
        output_data = {
            'processed_at': datetime.now().isoformat(),
            'total_articles': len(articles),
            'processed_articles': len(processed_articles),
            'dashboard_summary': dashboard_summary,
            'articles': processed_articles
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        processing_status['progress'] = 100
        processing_status['message'] = f'Processing complete! Generated {output_file}'
        processing_status['last_run'] = datetime.now().isoformat()
        processing_status['files_created'] = [output_file]
        
        logger.info(f"Processing completed: {output_file}")
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        processing_status['message'] = f'Processing failed: {str(e)}'
        processing_status['progress'] = 0
    finally:
        processing_status['running'] = False

def run_complete_workflow(max_articles=10):
    """Run complete scraping + processing workflow"""
    logger.info("Starting complete automated workflow...")
    
    # Step 1: Scraping
    run_scraping_task()
    
    # Wait for scraping to complete
    while scraping_status['running']:
        time.sleep(1)
    
    # Check if scraping was successful
    if scraping_status['progress'] != 100:
        logger.error("Scraping failed, stopping workflow")
        return
    
    # Step 2: Processing
    time.sleep(2)  # Brief pause
    run_processing_task(max_articles)
    
    logger.info("Complete workflow finished")

# CLI function for standalone processing
def process_scraped_file(file_path, max_articles=10):
    """Standalone function to process scraped data (for manual workflow)"""
    try:
        processor = DataProcessor(model="gemini-2.0-flash")
        
        print(f"Loading data from {file_path}...")
        articles = processor.load_scraped_data(file_path)
        print(f"Loaded {len(articles)} articles")
        
        print(f"Processing up to {max_articles} articles with Gemini REST API...")
        processed_articles = processor.process_articles_with_gemini(articles, max_articles)
        print(f"Successfully processed {len(processed_articles)} articles")
        
        print("Generating dashboard summary...")
        dashboard_summary = processor.gemini.generate_dashboard_summary(processed_articles)
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'processed_articles_{timestamp}.json'
        
        output_data = {
            'processed_at': datetime.now().isoformat(),
            'total_articles': len(articles),
            'processed_articles': len(processed_articles),
            'dashboard_summary': dashboard_summary,
            'articles': processed_articles
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        print(f"Results saved to {output_file}")
        return output_file
        
    except Exception as e:
        print(f"Error processing file: {e}")
        return None

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # CLI mode (manual workflow)
        file_path = sys.argv[1]
        max_articles = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        
        print("=== Manual Workflow Mode ===")
        print(f"Processing: {file_path}")
        print(f"Max articles: {max_articles}")
        
        result = process_scraped_file(file_path, max_articles)
        if result:
            print(f"\n✅ Processing complete! Output: {result}")
        else:
            print("\n❌ Processing failed!")
    else:
        # Web mode (automated workflow)
        print("=== Automated Web App Mode ===")
        print("🚀 Starting automated health & safety dashboard...")
        print("📡 Using Gemini 2.0 Flash via REST API")
        print("🌐 Dashboard: http://localhost:5001")
        print("📝 Make sure GEMINI_API_KEY is set!")
        print()
        print("Features:")
        print("  • Click 'Scrape & Process' for complete automation")
        print("  • View real-time progress")
        print("  • See dashboard with AI insights")
        print()
        
        app.run(debug=True, host='0.0.0.0', port=5001)