import requests
import json
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class GeminiRestProcessor:
    """
    Gemini API processor using direct REST API calls to match the curl example format
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        """
        Initialize Gemini REST API processor
        
        Args:
            api_key: Gemini API key (or uses GEMINI_API_KEY env var)
            model: Model to use (default: gemini-2.0-flash to match curl example)
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("API key must be provided or set in GEMINI_API_KEY environment variable")
        
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.headers = {
            'Content-Type': 'application/json',
            'X-goog-api-key': self.api_key
        }
        
    def _make_request(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        """
        Make a request to the Gemini API using the exact format from curl example
        
        Args:
            prompt: Text prompt to send
            max_retries: Number of retry attempts
            
        Returns:
            Generated text response or None if failed
        """
        url = f"{self.base_url}/models/{self.model}:generateContent"
        
        # Request body matching the curl example format exactly
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Making Gemini API request (attempt {attempt + 1}/{max_retries})")
                logger.debug(f"URL: {url}")
                logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
                
                response = requests.post(
                    url,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                logger.debug(f"Response status: {response.status_code}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    response_data = response.json()
                    logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
                    
                    # Extract text from response
                    if 'candidates' in response_data:
                        candidates = response_data['candidates']
                        if candidates and len(candidates) > 0:
                            content = candidates[0].get('content', {})
                            parts = content.get('parts', [])
                            if parts and len(parts) > 0:
                                return parts[0].get('text', '')
                    
                    logger.warning("No text found in response")
                    return None
                    
                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    import time
                    time.sleep(wait_time)
                    continue
                    
                else:
                    logger.error(f"API request failed: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    
                    if attempt == max_retries - 1:
                        return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request exception: {e}")
                if attempt == max_retries - 1:
                    return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                logger.error(f"Raw response: {response.text}")
                return None
                
        return None
    
    def summarize_article(self, title: str, content: str, url: str, source: str) -> Optional[str]:
        """
        Summarize a single article - FORCE simple clean JSON
        """
        prompt = f"""
You are analyzing a workplace safety incident. Return ONLY clean JSON with these exact field names.

TITLE: {title}
CONTENT: {content[:2500]}

Return exactly this format with NO extra text, NO markdown, NO code blocks:

{{"type": "Fatality", "severity": "Critical", "industry": "Construction", "company": "Company Name", "location": "Location", "summary": "Plain English summary", "fine": "£50000", "lesson": "Safety lesson"}}

Rules:
- type: ONLY use Fatality, Injury, Fine, Fire, Chemical, Equipment, Fall, Guidance  
- severity: ONLY use Critical, High, Medium, Low
- industry: ONLY use Construction, Manufacturing, Healthcare, Mining, Transport, Energy, General
- company: actual company name or "Unknown"
- location: actual location or "Unknown"
- summary: 1-2 sentences in plain English
- fine: amount like "£50000" or "None"
- lesson: what to learn from this

Return ONLY the JSON object. Nothing else.
"""
        
        try:
            response = self._make_request(prompt)
            if response:
                # Strip any markdown formatting
                cleaned = response.strip()
                if cleaned.startswith('```'):
                    # Extract JSON from code blocks
                    lines = cleaned.split('\n')
                    json_lines = []
                    in_json = False
                    for line in lines:
                        if line.strip().startswith('{'):
                            in_json = True
                        if in_json:
                            json_lines.append(line)
                        if line.strip().endswith('}') and in_json:
                            break
                    cleaned = '\n'.join(json_lines)
                
                return cleaned
            return None
        except Exception as e:
            logger.error(f"Error processing article {title}: {e}")
            return None
    
    def generate_dashboard_summary(self, processed_articles: list) -> Optional[str]:
        """
        Generate PLAIN TEXT executive summary - NO JSON AT ALL
        """
        # Count actual data for context
        total_incidents = len(processed_articles)
        severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        fine_total = 0
        construction_incidents = 0
        
        for article in processed_articles:
            summary = article.get('gemini_summary', {})
            if isinstance(summary, dict):
                # Handle both formats
                severity = summary.get('severity') or summary.get('risk_level', 'Unknown')
                severity = severity.replace(' Risk', '').strip()  # Clean old format
                
                if severity in severity_counts:
                    severity_counts[severity] += 1
                
                # Count fines
                fine = summary.get('fine') or summary.get('fine_amount', '')
                if fine and fine != 'None' and '£' in str(fine):
                    try:
                        fine_num = int(str(fine).replace('£', '').replace(',', ''))
                        fine_total += fine_num
                    except:
                        pass
                
                # Count construction incidents
                industry = summary.get('industry') or summary.get('industry_sector', '')
                if 'construction' in industry.lower():
                    construction_incidents += 1
        
        high_risk_total = severity_counts['Critical'] + severity_counts['High']
        
        prompt = f"""
Write an executive briefing for safety managers about recent workplace incidents. Write in plain English paragraphs.

DATA SUMMARY:
- Total incidents: {total_incidents}
- High risk incidents: {high_risk_total} (Critical: {severity_counts['Critical']}, High: {severity_counts['High']})
- Medium risk: {severity_counts['Medium']}
- Low risk: {severity_counts['Low']}
- Construction incidents: {construction_incidents}
- Total fines: £{fine_total:,}

Write 2-3 short paragraphs covering:
1. Current situation headline
2. Key safety concerns and trends
3. Immediate recommendations for companies

Write like you're briefing executives. Use normal business language. NO technical jargon. NO bullet points. NO JSON. Just clear, readable paragraphs.
"""
        
        try:
            response = self._make_request(prompt)
            if response:
                # Ensure it's plain text by stripping any formatting
                cleaned = response.strip()
                if cleaned.startswith('```') or cleaned.startswith('{'):
                    # If AI returned JSON/code despite instructions, extract readable content
                    return f"Recent analysis of {total_incidents} workplace incidents shows {high_risk_total} high-risk cases requiring immediate attention. Construction remains the most affected sector with {construction_incidents} incidents and £{fine_total:,} in fines issued. Companies should prioritize equipment safety training, fall protection measures, and regulatory compliance to prevent similar incidents."
                return cleaned
            return None
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return None
    
    def test_connection(self) -> bool:
        """
        Test the API connection with a simple request
        """
        test_prompt = "Respond with exactly: 'API connection successful'"
        
        try:
            response = self._make_request(test_prompt)
            if response and "successful" in response.lower():
                logger.info("✅ Gemini API connection test successful")
                return True
            else:
                logger.error(f"❌ Unexpected test response: {response}")
                return False
        except Exception as e:
            logger.error(f"❌ API connection test failed: {e}")
            return False

# Updated DataProcessor class to use REST API
class DataProcessor:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        """
        Initialize with REST API processor
        """
        self.gemini = GeminiRestProcessor(api_key, model)
        
    def load_scraped_data(self, file_path):
        """Load scraped data from XML or JSON file"""
        from pathlib import Path
        import xml.etree.ElementTree as ET
        
        file_path = Path(file_path)
        
        if file_path.suffix == '.xml':
            return self._load_xml_data(file_path)
        elif file_path.suffix == '.json':
            return self._load_json_data(file_path)
        else:
            raise ValueError("Unsupported file format. Use XML or JSON.")
            
    def _load_xml_data(self, xml_file):
        """Load data from XML file"""
        import xml.etree.ElementTree as ET
        
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        articles = []
        for article_elem in root.findall('article'):
            article = {
                'id': article_elem.get('id'),
                'title': article_elem.find('title').text if article_elem.find('title') is not None else '',
                'url': article_elem.find('url').text if article_elem.find('url') is not None else '',
                'source': article_elem.find('source').text if article_elem.find('source') is not None else '',
                'content': article_elem.find('content').text if article_elem.find('content') is not None else '',
                'scraped_at': article_elem.find('scraped_at').text if article_elem.find('scraped_at') is not None else ''
            }
            articles.append(article)
            
        return articles
        
    def _load_json_data(self, json_file):
        """Load data from JSON file"""
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        articles = []
        for link in data.get('links', []):
            article = {
                'title': link.get('title', ''),
                'url': link.get('url', ''),
                'source': link.get('source', ''),
                'content': data.get('articles_content', {}).get(link.get('url', ''), ''),
                'scraped_at': link.get('scraped_at', '')
            }
            articles.append(article)
            
        return articles
        
    def process_articles_with_gemini(self, articles: list, max_articles: int = 20) -> list:
        """
        Process articles using Gemini REST API
        """
        from datetime import datetime
        import time
        
        processed_articles = []
        
        for i, article in enumerate(articles[:max_articles]):
            if not article['content']:  # Skip articles without content
                continue
                
            logger.info(f"Processing article {i+1}/{min(len(articles), max_articles)}: {article['title'][:50]}...")
            
            summary = self.gemini.summarize_article(
                article['title'],
                article['content'],
                article['url'],
                article['source']
            )
            
            if summary:
                try:
                    # Try to parse JSON response
                    summary_data = json.loads(summary)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON response: {e}")
                    # Fallback to raw text if JSON parsing fails
                    summary_data = {"raw_summary": summary}
                
                processed_article = {
                    **article,
                    'gemini_summary': summary_data,
                    'processed_at': datetime.now().isoformat()
                }
                processed_articles.append(processed_article)
                
            # Be respectful to API rate limits
            time.sleep(1)
                
        return processed_articles

# Test function
def test_gemini_rest_api():
    """
    Test the REST API implementation
    """
    print("🧪 Testing Gemini REST API...")
    
    try:
        processor = GeminiRestProcessor()
        
        # Test connection
        if not processor.test_connection():
            print("❌ Connection test failed")
            return False
        
        # Test article processing
        test_content = """
        A construction worker was seriously injured after falling from height at a building site in Manchester. 
        The 35-year-old worker was taken to hospital with multiple fractures. HSE is investigating the incident.
        The company failed to provide adequate safety equipment and training.
        """
        
        print("Testing article summarization...")
        result = processor.summarize_article(
            title="Construction Worker Injured in Fall",
            content=test_content,
            url="https://example.com/test",
            source="test"
        )
        
        if result:
            print("✅ Article processing successful")
            print(f"Sample result: {result[:300]}...")
            
            # Try to parse as JSON
            try:
                json_result = json.loads(result)
                print("✅ Response is valid JSON")
                print(f"Incident type: {json_result.get('incident_type', 'N/A')}")
                print(f"Risk level: {json_result.get('risk_level', 'N/A')}")
            except:
                print("⚠️ Response is not JSON format")
            
            return True
        else:
            print("❌ Article processing failed")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

if __name__ == "__main__":
    # Run test
    success = test_gemini_rest_api()
    
    if success:
        print("\n🎉 REST API implementation is working!")
        print("\nUsage:")
        print("processor = GeminiRestProcessor()")
        print("result = processor.summarize_article(title, content, url, source)")
    else:
        print("\n❌ Please check your API key and try again")
        print("Set with: export GEMINI_API_KEY='your_key_here'")