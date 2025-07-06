#!/usr/bin/env python3
"""
Updated test script for REST API version
Run this to test your setup with the new Gemini REST API processor
"""

import os
import sys
import json
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_dependencies():
    """Test if all required packages are installed"""
    required_packages = [
        'requests',
        'beautifulsoup4', 
        'flask'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            if package == 'beautifulsoup4':
                import bs4
            else:
                __import__(package)
            logger.info(f"✅ {package} - OK")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"❌ {package} - MISSING")
    
    if missing_packages:
        logger.error(f"Missing packages: {missing_packages}")
        logger.error("Install with: pip install " + " ".join(missing_packages))
        return False
    
    return True

def test_gemini_rest_api():
    """Test Gemini REST API connection"""
    try:
        # Import the NEW REST API processor
        from gemini_rest_processor import GeminiRestProcessor
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.error("❌ GEMINI_API_KEY environment variable not set")
            logger.error("Set it with: export GEMINI_API_KEY='your_key_here'")
            return False
        
        # Test with the REST API processor
        processor = GeminiRestProcessor(model="gemini-2.0-flash")
        
        # Test connection
        if processor.test_connection():
            logger.info("✅ Gemini REST API - OK")
            return True
        else:
            logger.error("❌ Gemini REST API - Connection failed")
            return False
            
    except ImportError:
        logger.error("❌ Could not import gemini_rest_processor.py")
        logger.error("Make sure the file exists in current directory")
        return False
    except Exception as e:
        logger.error(f"❌ Gemini REST API - Error: {e}")
        return False

def test_scraper():
    """Test web scraping functionality"""
    try:
        from scraper import HealthSafetyScraper
        
        scraper = HealthSafetyScraper()
        
        # Test HSE Press (most reliable)
        logger.info("Testing HSE Press scraping...")
        html = scraper.fetch_page('https://press.hse.gov.uk/category/news/')
        
        if html and len(html) > 1000:
            links = scraper.extract_links_hse_press(html, 'https://press.hse.gov.uk/category/news/')
            
            if len(links) > 0:
                logger.info(f"✅ Scraper - Found {len(links)} HSE Press links")
                return True, links[:3]
            else:
                logger.error("❌ Scraper - No links found")
                return False, []
        else:
            logger.error("❌ Scraper - Could not fetch page")
            return False, []
            
    except ImportError:
        logger.error("❌ Could not import scraper.py")
        logger.error("Make sure the file exists in current directory")
        return False, []
    except Exception as e:
        logger.error(f"❌ Scraper - Error: {e}")
        return False, []

def test_gemini_processing():
    """Test Gemini article processing with REST API"""
    try:
        from gemini_rest_processor import GeminiRestProcessor
        
        processor = GeminiRestProcessor(model="gemini-2.0-flash")
        
        # Test with sample article
        test_content = """
        A construction worker was seriously injured after falling from height at a building site in Manchester. 
        The 35-year-old worker was taken to hospital with multiple fractures. HSE is investigating the incident.
        The company failed to provide adequate safety equipment and training.
        """
        
        logger.info("Testing Gemini REST API article processing...")
        result = processor.summarize_article(
            title="Construction Worker Injured in Fall",
            content=test_content,
            url="https://example.com/test",
            source="test"
        )
        
        if result and len(result) > 50:
            logger.info("✅ Gemini REST Processing - OK")
            logger.info(f"Sample result: {result[:200]}...")
            
            # Try to parse as JSON
            try:
                json_result = json.loads(result)
                logger.info("✅ Response is valid JSON")
                logger.info(f"Incident type: {json_result.get('incident_type', 'N/A')}")
            except:
                logger.warning("⚠️ Response is not JSON, but processing works")
            
            return True, result
        else:
            logger.error("❌ Gemini REST Processing - No/limited response")
            return False, None
            
    except Exception as e:
        logger.error(f"❌ Gemini REST Processing - Error: {e}")
        return False, None

def test_flask_app():
    """Test Flask app functionality"""
    try:
        from app import app
        
        # Test app creation
        with app.test_client() as client:
            response = client.get('/')
            
            if response.status_code == 200:
                logger.info("✅ Flask App - Dashboard route OK")
                return True
            else:
                logger.error(f"❌ Flask App - Dashboard returned {response.status_code}")
                return False
                
    except ImportError:
        logger.error("❌ Could not import app.py")
        logger.error("Make sure the file exists in current directory")
        return False
    except Exception as e:
        logger.error(f"❌ Flask App - Error: {e}")
        return False

def run_end_to_end_test():
    """Run a complete end-to-end test with REST API"""
    logger.info("🧪 Running end-to-end test with REST API...")
    
    # Create test data
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
<health_safety_news scraped_at="2025-07-05T14:30:22" total_articles="2">
    <article id="0">
        <title>Test Construction Incident</title>
        <url>https://example.com/test1</url>
        <source>test</source>
        <scraped_at>2025-07-05T14:30:22</scraped_at>
        <content>A construction worker was injured at a site in London. The incident involved a fall from height. HSE is investigating.</content>
    </article>
    <article id="1">
        <title>Safety Fine Issued</title>
        <url>https://example.com/test2</url>
        <source>test</source>
        <scraped_at>2025-07-05T14:30:22</scraped_at>
        <content>A manufacturing company has been fined £50,000 for safety breaches after a worker was injured by machinery.</content>
    </article>
</health_safety_news>"""

    test_file = 'test_data_rest.xml'
    try:
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(sample_xml)
        logger.info(f"✅ Created test data file: {test_file}")
    except Exception as e:
        logger.error(f"❌ Error creating test data: {e}")
        return False

    try:
        from app import process_scraped_file
        
        # Process test data with REST API
        logger.info("Processing test data with Gemini REST API...")
        result_file = process_scraped_file(test_file, max_articles=2)
        
        if result_file and os.path.exists(result_file):
            logger.info(f"✅ End-to-end test - Generated: {result_file}")
            
            # Verify output
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if (data.get('processed_articles', 0) > 0 and 
                data.get('dashboard_summary') and
                len(data.get('articles', [])) > 0):
                
                logger.info("✅ End-to-end test - Output verified")
                return True
            else:
                logger.error("❌ End-to-end test - Invalid output format")
                return False
        else:
            logger.error("❌ End-to-end test - No output file generated")
            return False
            
    except Exception as e:
        logger.error(f"❌ End-to-end test - Error: {e}")
        return False
    finally:
        # Clean up test files
        for file in ['test_data_rest.xml'] + list(Path('.').glob('processed_articles_*.json')):
            try:
                os.remove(file)
                logger.info(f"🧹 Cleaned up: {file}")
            except:
                pass

def main():
    """Run all tests"""
    print("🔬 Health & Safety News Workflow - REST API Test Suite")
    print("=" * 60)
    
    all_tests_passed = True
    
    # Test 1: Dependencies
    print("\n1. Testing Dependencies...")
    if not test_dependencies():
        all_tests_passed = False
    
    # Test 2: Gemini REST API
    print("\n2. Testing Gemini REST API...")
    if not test_gemini_rest_api():
        all_tests_passed = False
        print("⚠️ Gemini tests will be skipped")
        gemini_available = False
    else:
        gemini_available = True
    
    # Test 3: Scraper
    print("\n3. Testing Web Scraper...")
    scraper_works, sample_links = test_scraper()
    if not scraper_works:
        all_tests_passed = False
    else:
        print("Sample links found:")
        for link in sample_links:
            print(f"  - {link['title']}")
    
    # Test 4: Gemini Processing (REST API)
    if gemini_available:
        print("\n4. Testing Gemini REST API Processing...")
        processing_works, sample_result = test_gemini_processing()
        if not processing_works:
            all_tests_passed = False
    
    # Test 5: Flask App
    print("\n5. Testing Flask App...")
    if not test_flask_app():
        all_tests_passed = False
    
    # Test 6: End-to-end (REST API)
    if gemini_available:
        print("\n6. Running End-to-End Test (REST API)...")
        if not run_end_to_end_test():
            all_tests_passed = False
    
    # Summary
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 ALL TESTS PASSED! Your REST API setup is ready.")
        print("\nNext steps:")
        print("1. Run: python scraper.py")
        print("2. Run: python app.py <generated_xml_file> 10")
        print("3. Run: python app.py")
        print("4. Open: http://localhost:5001")
        print("\n📡 Now using Gemini 2.0 Flash via direct REST API!")
    else:
        print("❌ SOME TESTS FAILED. Please fix the issues above.")
        
    return all_tests_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)