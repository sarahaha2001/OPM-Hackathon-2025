import requests
from bs4 import BeautifulSoup
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
import json
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HealthSafetyScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def fetch_page(self, url, retries=3):
        """Fetch a single page with error handling and retries"""
        for attempt in range(retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1})")
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error fetching {url} (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
                    
    def extract_links_constructionnews(self, html, base_url):
        """Extract h2 a href links from Construction News"""
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Find all h2 elements with anchor tags
        h2_elements = soup.find_all('h2')
        for h2 in h2_elements:
            a_tag = h2.find('a', href=True)
            if a_tag:
                title = a_tag.get_text(strip=True)
                url = urljoin(base_url, a_tag['href'])
                
                # Skip non-article links
                if title and '/health-and-safety/' in url:
                    links.append({
                        'title': title,
                        'url': url,
                        'source': 'constructionnews',
                        'scraped_at': datetime.now().isoformat()
                    })
        
        return links
        
    def extract_links_bbc(self, html, base_url):
        """Extract BBC topic links with specific class structure"""
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Try multiple BBC selectors as their structure may vary
        selectors = [
            'div.liverpool-card div.anchor-inner-wrapper a',
            'div[data-testid="liverpool-card"] a',
            'article a',
            '.media__link'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for a_tag in elements:
                if a_tag.get('href'):
                    title = a_tag.get_text(strip=True)
                    url = urljoin(base_url, a_tag['href'])
                    
                    if title and url not in [link['url'] for link in links]:
                        links.append({
                            'title': title,
                            'url': url,
                            'source': 'bbc',
                            'scraped_at': datetime.now().isoformat()
                        })
        
        return links
        
    def extract_links_hse_network(self, html, base_url):
        """Extract article links from HSE Network"""
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Look for article elements and various link patterns
        selectors = [
            'article a[href]',
            '.post-title a[href]',
            'h2 a[href]',
            'h3 a[href]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for a_tag in elements:
                title = a_tag.get_text(strip=True)
                url = urljoin(base_url, a_tag['href'])
                
                # Filter out navigation and non-article links
                if (title and 
                    len(title) > 10 and  # Reasonable title length
                    url not in [link['url'] for link in links] and
                    'hse-network.com' in url):
                    
                    links.append({
                        'title': title,
                        'url': url,
                        'source': 'hse-network',
                        'scraped_at': datetime.now().isoformat()
                    })
        
        return links
        
    def extract_links_hse_press(self, html, base_url):
        """Extract h2 a href links from HSE Press"""
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        # Look for article titles and links
        selectors = [
            'h2 a[href]',
            '.entry-title a[href]',
            'article h2 a[href]',
            'h3 a[href]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for a_tag in elements:
                title = a_tag.get_text(strip=True)
                url = urljoin(base_url, a_tag['href'])
                
                if (title and 
                    url not in [link['url'] for link in links] and
                    'press.hse.gov.uk' in url):
                    
                    links.append({
                        'title': title,
                        'url': url,
                        'source': 'hse-press',
                        'scraped_at': datetime.now().isoformat()
                    })
        
        return links
        
    def fetch_article_content(self, url):
        """Fetch full article content with intelligent content extraction"""
        html = self.fetch_page(url)
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 
                           'noscript', 'iframe', '.advertisement', '.ads', 
                           '.social-share', '.navigation', '.sidebar']):
            element.decompose()
            
        # Try to find main content area with various selectors
        content_selectors = [
            'article .content',
            'article .post-content', 
            'article .entry-content',
            '.main-content article',
            '.content article',
            'article',
            '.post-content',
            '.entry-content',
            '#content',
            'main',
            '.main'
        ]
        
        content = None
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content and len(content.get_text(strip=True)) > 100:
                break
                
        if not content:
            # Fallback to body but try to exclude headers/footers
            content = soup.find('body')
            
        if content:
            # Clean up the content
            text = content.get_text(separator=' ', strip=True)
            # Remove excessive whitespace
            text = ' '.join(text.split())
            return text
        
        return None
        
    def scrape_site(self, site_config):
        """Scrape a single site with pagination support"""
        all_links = []
        
        logger.info(f"Scraping {site_config['name']}...")
        
        # Scrape main page
        html = self.fetch_page(site_config['url'])
        if html:
            links = site_config['extractor'](html, site_config['url'])
            all_links.extend(links)
            logger.info(f"Found {len(links)} links from {site_config['name']} main page")
            
            # Handle pagination if specified
            if 'pagination' in site_config:
                for page in site_config['pagination']:
                    if page == 1:  # Skip page 1 as we already scraped it
                        continue
                        
                    if 'hse-network' in site_config['url']:
                        paginated_url = f"{site_config['url']}page/{page}/"
                    elif 'press.hse.gov.uk' in site_config['url']:
                        paginated_url = f"{site_config['url']}page/{page}/"
                    else:
                        continue
                        
                    logger.info(f"Scraping page {page}: {paginated_url}")
                    html = self.fetch_page(paginated_url)
                    if html:
                        links = site_config['extractor'](html, paginated_url)
                        all_links.extend(links)
                        logger.info(f"Found {len(links)} links from page {page}")
                        
                    time.sleep(1)  # Be respectful to servers
                    
        return all_links
        
    def scrape_all_sites(self, fetch_content=True, max_articles_per_site=10):
        """Main scraping function for all sites"""
        sites = [
            {
                'url': 'https://www.constructionnews.co.uk/health-and-safety/',
                'extractor': self.extract_links_constructionnews,
                'name': 'Construction News'
            },
            {
                'url': 'https://www.bbc.com/news/topics/cpzy90q2y90t',
                'extractor': self.extract_links_bbc,
                'name': 'BBC Health & Safety'
            },
            {
                'url': 'https://www.hse-network.com/category/latest-health-and-safety-news/',
                'extractor': self.extract_links_hse_network,
                'name': 'HSE Network',
                'pagination': list(range(1, 6))  # Pages 1-5
            },
            {
                'url': 'https://press.hse.gov.uk/category/news/',
                'extractor': self.extract_links_hse_press,
                'name': 'HSE Press',
                'pagination': [1, 2]  # Pages 1-2
            }
        ]
        
        all_links = []
        articles_content = {}
        
        for site in sites:
            try:
                site_links = self.scrape_site(site)
                all_links.extend(site_links)
                
                # Fetch content for articles if requested
                if fetch_content:
                    # Limit articles per site to avoid overwhelming servers
                    limited_links = site_links[:max_articles_per_site]
                    
                    for i, link in enumerate(limited_links):
                        logger.info(f"Fetching content {i+1}/{len(limited_links)} from {site['name']}: {link['title'][:50]}...")
                        content = self.fetch_article_content(link['url'])
                        if content:
                            articles_content[link['url']] = content
                        time.sleep(2)  # Be respectful to servers
                        
                time.sleep(3)  # Pause between sites
                
            except Exception as e:
                logger.error(f"Error scraping {site['name']}: {e}")
                continue
                
        return all_links, articles_content
        
    def convert_to_xml(self, links, articles_content):
        """Convert scraped data to XML format suitable for Gemini processing"""
        root = ET.Element('health_safety_news')
        root.set('scraped_at', datetime.now().isoformat())
        root.set('total_articles', str(len(links)))
        
        for i, link in enumerate(links):
            article_elem = ET.SubElement(root, 'article')
            article_elem.set('id', str(i))
            
            title_elem = ET.SubElement(article_elem, 'title')
            title_elem.text = link['title']
            
            url_elem = ET.SubElement(article_elem, 'url')
            url_elem.text = link['url']
            
            source_elem = ET.SubElement(article_elem, 'source')
            source_elem.text = link['source']
            
            scraped_at_elem = ET.SubElement(article_elem, 'scraped_at')
            scraped_at_elem.text = link.get('scraped_at', '')
            
            if link['url'] in articles_content:
                content_elem = ET.SubElement(article_elem, 'content')
                content_elem.text = articles_content[link['url']]
                
        return ET.tostring(root, encoding='unicode')
        
    def save_data(self, links, articles_content, filename_base='health_safety_news'):
        """Save data in multiple formats"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save as XML for Gemini processing
        xml_output = self.convert_to_xml(links, articles_content)
        xml_filename = f'{filename_base}_{timestamp}.xml'
        with open(xml_filename, 'w', encoding='utf-8') as f:
            f.write(xml_output)
        logger.info(f"XML data saved to {xml_filename}")
        
        # Save as JSON for easier processing
        json_data = {
            'scraped_at': datetime.now().isoformat(),
            'total_links': len(links),
            'total_articles_with_content': len(articles_content),
            'links': links,
            'articles_content': articles_content
        }
        
        json_filename = f'{filename_base}_{timestamp}.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON data saved to {json_filename}")
        
        return xml_filename, json_filename

# Usage example and testing
if __name__ == "__main__":
    scraper = HealthSafetyScraper()
    
    # Test with limited articles first
    print("Starting health & safety news scraping...")
    print("This will take several minutes to complete respectfully...")
    
    try:
        # Get all links and fetch content for first 5 articles per site
        all_links, articles_content = scraper.scrape_all_sites(
            fetch_content=True, 
            max_articles_per_site=5
        )
        
        # Save the data
        xml_file, json_file = scraper.save_data(all_links, articles_content)
        
        # Print summary
        print(f"\n=== SCRAPING COMPLETE ===")
        print(f"Total links found: {len(all_links)}")
        print(f"Articles with content: {len(articles_content)}")
        print(f"XML file: {xml_file}")
        print(f"JSON file: {json_file}")
        
        # Show sample of what was found
        print(f"\nSample links by source:")
        sources = {}
        for link in all_links:
            source = link['source']
            if source not in sources:
                sources[source] = []
            sources[source].append(link['title'])
            
        for source, titles in sources.items():
            print(f"\n{source.upper()} ({len(titles)} articles):")
            for title in titles[:3]:  # Show first 3
                print(f"  - {title}")
            if len(titles) > 3:
                print(f"  ... and {len(titles) - 3} more")
                
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
    except Exception as e:
        print(f"Error during scraping: {e}")
        logger.exception("Scraping failed")