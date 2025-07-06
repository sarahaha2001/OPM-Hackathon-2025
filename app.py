from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, Response
import sqlite3, os, json
from datetime import datetime
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from PIL import Image, UnidentifiedImageError
import numpy as np, cv2
from werkzeug.exceptions import RequestEntityTooLarge
import folium
import requests
import tempfile
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
GEMINI_HEADERS = {
    "Content-Type": "application/json",
    "X-goog-api-key": GEMINI_API_KEY
}


app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure random key
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

DB_PATH = 'db/hsse.db'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load model and class definitions
model = YOLO("model/best.pt")
CLASS_NAMES = ['Hardhat','Mask','NO-Hardhat','NO-Mask','NO-Safety Vest',
               'Person','Safety Cone','Safety Vest','machinery','vehicle']
PPE = {"Hardhat","Mask","Safety Vest"}
VIOL = {"NO-Hardhat","NO-Mask","NO-Safety Vest"}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_processed_articles():
    """Load processed health & safety articles from JSON file"""
    try:
        # Look for the most recent processed articles file
        processed_files = [f for f in os.listdir('.') if f.startswith('processed_articles_') and f.endswith('.json')]
        if not processed_files:
            return []
        
        # Get the most recent file
        latest_file = max(processed_files, key=lambda x: os.path.getctime(x))
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        articles = data.get('articles', [])
        
        # Filter articles that have Gemini summaries and content
        processed_articles = []
        for article in articles:
            if article.get('gemini_summary') and article.get('content'):
                processed_articles.append(article)
                
        return processed_articles[:20]  # Limit to 20 most recent
        
    except Exception as e:
        print(f"Error loading processed articles: {str(e)}")
        return []

def calculate_news_metrics(articles):
    """Calculate metrics from processed articles"""
    metrics = {
        'total_articles': len(articles),
        'high_risk': 0,
        'medium_risk': 0,
        'low_risk': 0,
        'total_fines': 0,
        'construction_incidents': 0,
        'severity_distribution': {},
        'incident_types': {},
        'recent_companies': []
    }
    
    for article in articles:
        summary = article.get('gemini_summary', {})
        if not summary:
            continue
            
        # Count severity levels
        severity = summary.get('severity', 'Unknown')
        if severity in ['Critical', 'High']:
            metrics['high_risk'] += 1
        elif severity == 'Medium':
            metrics['medium_risk'] += 1
        elif severity == 'Low':
            metrics['low_risk'] += 1
            
        # Track severity distribution
        metrics['severity_distribution'][severity] = metrics['severity_distribution'].get(severity, 0) + 1
        
        # Track incident types
        incident_type = summary.get('type', 'Unknown')
        metrics['incident_types'][incident_type] = metrics['incident_types'].get(incident_type, 0) + 1
        
        # Count construction incidents
        industry = summary.get('industry', '')
        if 'construction' in industry.lower():
            metrics['construction_incidents'] += 1
            
        # Sum fines
        fine = summary.get('fine', '')
        if fine and fine != 'None' and '£' in str(fine):
            try:
                fine_amount = int(str(fine).replace('£', '').replace(',', ''))
                metrics['total_fines'] += fine_amount
            except:
                pass
                
        # Collect company names
        company = summary.get('company', '')
        if company and company != 'Unknown' and len(company) > 3:
            if company not in metrics['recent_companies']:
                metrics['recent_companies'].append(company)
                
    return metrics

def get_trend_data(articles):
    """Generate trend data for charts"""
    # Group articles by date for trend analysis
    daily_counts = {}
    severity_trends = {'Critical': [], 'High': [], 'Medium': [], 'Low': []}
    
    for article in articles:
        # Extract date from scraped_at or processed_at
        date_str = article.get('scraped_at', '') or article.get('processed_at', '')
        if date_str:
            try:
                date = datetime.fromisoformat(date_str.replace('Z', '')).strftime('%Y-%m-%d')
                daily_counts[date] = daily_counts.get(date, 0) + 1
                
                # Track severity by date
                summary = article.get('gemini_summary', {})
                severity = summary.get('severity')
                if severity in severity_trends:
                    severity_trends[severity].append({'date': date, 'count': 1})
            except:
                continue
                
    # Convert to chart-friendly format
    dates = sorted(daily_counts.keys())[-7:]  # Last 7 days
    trend_data = [{'date': date, 'incidents': daily_counts.get(date, 0)} for date in dates]
    
    return trend_data

def get_center(box):
    # Handle both formats: [x1,y1,x2,y2] and [x1,y1,x2,y2,conf,cls]
    if len(box) >= 4:
        x1,y1,x2,y2 = box[:4]  # Take only first 4 values
        return ((x1+x2)/2,(y1+y2)/2)
    else:
        raise ValueError(f"Box must have at least 4 coordinates, got {len(box)}")

def get_incidents_from_db():
    """Fetch incident data from the database"""
    try:
        conn = get_db_connection()
        # Fetch incidents with location data (latitude and longitude not null)
        incidents = conn.execute("""
            SELECT id, incident_type, description, latitude, longitude, created_at, company_name
            FROM reports 
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 100
        """).fetchall()
        conn.close()
        
        incidents_list = []
        for incident in incidents:
            incidents_list.append({
                'id': incident['id'],
                'type': incident['incident_type'] or 'Unknown',
                'description': incident['description'] or 'No description',
                'latitude': float(incident['latitude']),
                'longitude': float(incident['longitude']),
                'timestamp': incident['created_at'],
                'company': incident['company_name'] or 'Unknown Company'
            })
        
        return incidents_list
    except Exception as e:
        print(f"Error fetching incidents from database: {str(e)}")
        return []

def get_incident_color(incident_type):
    """Get marker color based on incident type"""
    color_map = {
        'Near Miss': 'orange',
        'Accident': 'red',
        'Environmental': 'green',
        'Safety Observation': 'blue',
        'Injury': 'darkred',
        'Property Damage': 'purple'
    }
    return color_map.get(incident_type, 'gray')

def generate_incident_map():
    """Generate Folium map with real incident data"""
    try:
        # Get incidents from database
        incidents = get_incidents_from_db()
        
        if not incidents:
            # Default center on Guyana if no incidents
            center_lat, center_lon = 5.5, -59.5
        else:
            # Calculate center based on incidents
            center_lat = sum(inc['latitude'] for inc in incidents) / len(incidents)
            center_lon = sum(inc['longitude'] for inc in incidents) / len(incidents)
        
        # Create map
        incident_map = folium.Map(
            location=[center_lat, center_lon], 
            zoom_start=7 if incidents else 6, 
            control_scale=True
        )

        # Base map layers
        folium.TileLayer(
            tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            attr='&copy; OpenStreetMap contributors',
            name='Default'
        ).add_to(incident_map)

        folium.TileLayer(
            tiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
            attr='&copy; CartoDB',
            name='Light Mode',
            control=True
        ).add_to(incident_map)

        folium.TileLayer(
            tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
            attr='&copy; CartoDB',
            name='Dark Mode',
            control=True
        ).add_to(incident_map)

        folium.TileLayer(
            tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            attr='Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap (CC-BY-SA)',
            name='Terrain'
        ).add_to(incident_map)

        # Add incident markers
        for incident in incidents:
            try:
                # Format timestamp
                try:
                    timestamp = datetime.fromisoformat(incident['timestamp'].replace('Z', '+00:00'))
                    formatted_time = timestamp.strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_time = incident['timestamp']
                
                # Create popup content
                popup_text = f"""
                <div style="min-width: 200px;">
                    <strong>{incident['type']}</strong><br>
                    <strong>Company:</strong> {incident['company']}<br>
                    <strong>Description:</strong> {incident['description']}<br>
                    <strong>Date:</strong> {formatted_time}<br>
                    <small>ID: #{incident['id']}</small>
                </div>
                """
                
                # Get marker color based on incident type
                marker_color = get_incident_color(incident['type'])
                
                folium.Marker(
                    location=[incident['latitude'], incident['longitude']],
                    popup=folium.Popup(popup_text, max_width=300),
                    tooltip=f"{incident['type']} - {incident['company']}",
                    icon=folium.Icon(color=marker_color, icon='info-sign')
                ).add_to(incident_map)
                
            except Exception as e:
                print(f"Error adding marker for incident {incident['id']}: {str(e)}")
                continue

        # Add layer control
        folium.LayerControl(collapsed=False).add_to(incident_map)
        
        # Generate HTML
        map_html = incident_map._repr_html_()
        return map_html
        
    except Exception as e:
        print(f"Error generating map: {str(e)}")
        # Return a basic map if there's an error
        basic_map = folium.Map(location=[5.5, -59.5], zoom_start=6)
        return basic_map._repr_html_()

def analyze_detections(results):
    try:
        if not results or len(results) == 0:
            return ["No detections found"]
        
        if not hasattr(results[0], 'boxes') or results[0].boxes is None:
            return ["No objects detected"]
        
        if results[0].boxes.data is None or len(results[0].boxes.data) == 0:
            return ["No objects detected"]
        
        persons, labels = [], []
        arr = results[0].boxes.data.cpu().numpy()
        
        for b in arr:
            if len(b) < 6:  # Ensure we have all required values
                continue
                
            x1,y1,x2,y2,conf,cls = b
            cls_idx = int(cls)
            
            if cls_idx >= len(CLASS_NAMES):  # Validate class index
                continue
                
            label = CLASS_NAMES[cls_idx]
            labels.append((label,[x1,y1,x2,y2]))
            
            if label=="Person":
                persons.append({"box":[x1,y1,x2,y2],"ppe":set(),"violations":set()})
        
        # If no persons detected, return empty analysis
        if not persons:
            return ["No persons detected in image"]
        
        # Associate PPE and violations with persons
        for label,box in labels:
            if label=="Person": 
                continue
                
            c = get_center(box)
            closest,dist = None,float("inf")
            
            for p in persons:
                try:
                    d = np.linalg.norm(np.array(c)-np.array(get_center(p["box"])))
                    if d<dist:
                        dist,closest = d,p
                except Exception as e:
                    print(f"Error calculating distance: {e}")
                    continue
            
            if closest and dist<200:
                if label in PPE: 
                    closest["ppe"].add(label)
                if label in VIOL: 
                    closest["violations"].add(label)
        
        # Generate results for each person
        results_list = []
        for p in persons:
            if p["violations"]:
                results_list.append(list(p["violations"]))
            else:
                results_list.append(["Fully Compliant ✅"])
        
        return results_list
        
    except Exception as e:
        print(f"Error in analyze_detections: {str(e)}")
        import traceback
        traceback.print_exc()
        return ["Analysis error occurred"]

def validate_form_data(form_data):
    """Validate required form fields"""
    required_fields = ['reporterType', 'incidentType', 'industry', 'companyName', 'description']
    errors = []
    
    for field in required_fields:
        if not form_data.get(field) or form_data.get(field).strip() == '':
            errors.append(f'{field.replace("_", " ").title()} is required')
    
    return errors

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify(error="File too large. Maximum size is 50MB."), 413

@app.errorhandler(413)
def handle_413_error(e):
    return jsonify(error="Request entity too large"), 413

@app.route('/', methods=['GET'])
def home():
    try:
        conn = get_db_connection()
        
        # Get database metrics data
        db_metrics = get_dashboard_metrics(conn)
        
        # Get regional breakdown
        regional_data = get_regional_breakdown(conn)
        
        # Get quick stats
        stats = get_quick_stats(conn)
        
        conn.close()
        
        # Load processed health & safety articles
        articles = load_processed_articles()
        news_metrics = calculate_news_metrics(articles)
        trend_data = get_trend_data(articles)
        
        # Combine database metrics with news metrics for enhanced dashboard
        enhanced_metrics = {
            **db_metrics,
            'news_total_fines': news_metrics['total_fines'],
            'news_high_risk': news_metrics['high_risk'],
            'news_construction': news_metrics['construction_incidents']
        }
        
        return render_template('index.html', 
                             metrics=enhanced_metrics, 
                             regional_data=regional_data, 
                             stats=stats,
                             articles=articles[:10],  # Top 10 for news section
                             news_metrics=news_metrics,
                             trend_data=trend_data)
    except Exception as e:
        print(f"Error loading dashboard: {str(e)}")
        # Return with default values if data loading fails
        return render_template('index.html', 
                             metrics={}, 
                             regional_data=[], 
                             stats={},
                             articles=[],
                             news_metrics={},
                             trend_data=[])

@app.route('/ai')
def ai_voice_ui():
    return render_template("ai.html")

@app.route('/ask', methods=['POST'])
def ask():
    user_input = request.json.get('message')

    # Build prompt from your system — you can customize this
    prompt = f"""You are an HSSE voice assistant. Answer based on internal company knowledge only.

Question: {user_input}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(GEMINI_URL, headers=GEMINI_HEADERS, json=payload)
        if response.status_code == 200:
            content = response.json().get("candidates", [{}])[0].get("content", {})
            parts = content.get("parts", [])
            text = parts[0].get("text", "I couldn't find an answer.") if parts else "Empty response."
            return jsonify({"response": text})
        else:
            return jsonify({"response": f"Error from Gemini: {response.status_code}"}), 500
    except Exception as e:
        return jsonify({"response": f"Internal error: {str(e)}"}), 500


@app.route('/api/news-data')
def api_news_data():
    """API endpoint to serve processed news data as JSON"""
    try:
        articles = load_processed_articles()
        news_metrics = calculate_news_metrics(articles)
        trend_data = get_trend_data(articles)
        
        return jsonify({
            'success': True,
            'articles': articles,
            'metrics': news_metrics,
            'trends': trend_data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/map')
def map_view():
    """Route to display the interactive incident map"""
    try:
        # Get incident count for display
        conn = get_db_connection()
        incident_count = conn.execute(
            "SELECT COUNT(*) as count FROM reports WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        ).fetchone()['count']
        conn.close()
        
        return render_template('map.html', incident_count=incident_count)
    except Exception as e:
        print(f"Error loading map page: {str(e)}")
        return render_template('map.html', incident_count=0)

@app.route('/map-data')
def map_data():
    """Route to serve the map HTML content"""
    try:
        map_html = generate_incident_map()
        return Response(map_html, mimetype='text/html')
    except Exception as e:
        print(f"Error generating map data: {str(e)}")
        return Response(f"<html><body><h3>Error loading map: {str(e)}</h3></body></html>", 
                       mimetype='text/html')

def get_dashboard_metrics(conn):
    """Get national HSSE metrics"""
    try:
        # Current month incidents
        current_incidents = conn.execute(
            "SELECT COUNT(*) as count FROM reports WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        ).fetchone()['count']
        
        # Previous month incidents for comparison
        prev_incidents = conn.execute(
            "SELECT COUNT(*) as count FROM reports WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', '-1 month')"
        ).fetchone()['count']
        
        # Calculate percentage change
        incidents_change = calculate_percentage_change(current_incidents, prev_incidents)
        
        # Get other metrics from metrics table
        metrics_row = conn.execute("SELECT * FROM dashboard_metrics ORDER BY id DESC LIMIT 1").fetchone()
        
        if metrics_row:
            return {
                'total_incidents': current_incidents,
                'incidents_change': incidents_change,
                'near_misses': metrics_row['near_misses'],
                'near_misses_change': metrics_row['near_misses_change'],
                'safety_observations': metrics_row['safety_observations'],
                'observations_change': metrics_row['observations_change'],
                'ltifr': metrics_row['ltifr'],
                'ltifr_change': metrics_row['ltifr_change']
            }
        else:
            return {
                'total_incidents': current_incidents,
                'incidents_change': incidents_change,
                'near_misses': 0,
                'near_misses_change': '+0%',
                'safety_observations': 0,
                'observations_change': '+0%',
                'ltifr': 0.0,
                'ltifr_change': '+0%'
            }
    except Exception as e:
        print(f"Error getting metrics: {str(e)}")
        return {}

def get_regional_breakdown(conn):
    """Get regional incident breakdown"""
    try:
        regions = conn.execute("""
            SELECT region_name, incident_count, color 
            FROM regional_data 
            ORDER BY incident_count DESC
        """).fetchall()
        
        return [{'name': r['region_name'], 'incidents': r['incident_count'], 'color': r['color']} 
                for r in regions]
    except Exception as e:
        print(f"Error getting regional data: {str(e)}")
        return []

def get_quick_stats(conn):
    """Get quick stats data"""
    try:
        stats_row = conn.execute("SELECT * FROM quick_stats ORDER BY id DESC LIMIT 1").fetchone()
        
        if stats_row:
            return {
                'active_sites': stats_row['active_sites'],
                'total_employees': stats_row['total_employees'],
                'safety_officers': stats_row['safety_officers'],
                'training_sessions': stats_row['training_sessions']
            }
        else:
            return {}
    except Exception as e:
        print(f"Error getting quick stats: {str(e)}")
        return {}

def calculate_percentage_change(current, previous):
    """Calculate percentage change between two values"""
    if previous == 0:
        return "+100%" if current > 0 else "0%"
    
    change = ((current - previous) / previous) * 100
    return f"{'+' if change >= 0 else ''}{change:.1f}%"

@app.route('/detect-json', methods=['POST'])
def detect_json():
    if request.method != 'POST':
        return jsonify(error="Method not allowed"), 405
    
    imgf = request.files.get('image')
    if not imgf:
        return jsonify(error="No image provided"), 400
    
    if imgf.filename == '':
        return jsonify(error="No image selected"), 400
    
    if not allowed_file(imgf.filename):
        return jsonify(error="Invalid file type. Only PNG, JPG, JPEG, GIF allowed"), 400
    
    fn = secure_filename(imgf.filename)
    if not fn:
        return jsonify(error="Invalid filename"), 400
    
    try:
        img = Image.open(imgf).convert('RGB')
    except UnidentifiedImageError:
        return jsonify(error="Unsupported image format"), 400
    except Exception as e:
        print(f"Error opening image: {str(e)}")
        return jsonify(error="Error processing image"), 400

    # Generate unique filename to avoid conflicts
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    jpg = f"temp_{timestamp}_{os.path.splitext(fn)[0]}.jpg"
    path = os.path.join(UPLOAD_FOLDER, jpg)
    
    try:
        img.save(path, format='JPEG')
        if cv2.imread(path) is None:
            print(f"OpenCV cannot read image: {path}")
            return jsonify(error="Cannot read saved image"), 400

        res = model.predict(source=path, save=False)
        vio = analyze_detections(res)
        
        print(f"Analysis successful for {path}: {vio}")
        
        # Clean up temporary file
        try:
            os.remove(path)
        except Exception as cleanup_error:
            print(f"Cleanup error: {cleanup_error}")
            pass  # Continue even if cleanup fails
            
        return jsonify(violations=vio)
    except Exception as e:
        print(f"Error in detect_json: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        
        # Clean up temporary file on error
        try:
            os.remove(path)
        except:
            pass
        return jsonify(error=f"Error analyzing image: {str(e)}"), 500

@app.route('/report', methods=['GET','POST'])
def report():
    if request.method == 'GET':
        return render_template('report.html')
    
    elif request.method == 'POST':
        try:
            # Validate form data
            form_errors = validate_form_data(request.form)
            if form_errors:
                flash('Please correct the following errors: ' + ', '.join(form_errors))
                return redirect(url_for('report'))
            
            conn = get_db_connection()
            rpt = request.form.get('reporterType')
            user_id = None
            
            # Handle reporter information - for named/thirdparty, this would be handled
            # by your backend systems (e.g., user authentication, session data, etc.)
            if rpt in ('named', 'thirdparty'):
                # In a real system, you would get user info from:
                # - Current logged-in user session
                # - User authentication system
                # - External user management system
                # For now, we'll create a placeholder entry
                cur = conn.execute(
                    'INSERT INTO users(full_name,organization,email,phone) VALUES(?,?,?,?)',
                    ('System Generated User', 'Auto-populated', 'system@example.com', '000-000-0000')
                )
                user_id = cur.lastrowid
                conn.commit()

            # Insert main report
            cur = conn.execute(
                '''INSERT INTO reports
                   (reporter_type,user_id,incident_type,industry,company_name,
                    description,location_text,latitude,longitude,accuracy)
                   VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (rpt, user_id,
                 request.form.get('incidentType', '').strip(),
                 request.form.get('industry', '').strip(),
                 request.form.get('companyName', '').strip(),
                 request.form.get('description', '').strip(),
                 request.form.get('location_text', ''),
                 request.form.get('latitude'),
                 request.form.get('longitude'),
                 request.form.get('accuracy'))
            )
            rpt_id = cur.lastrowid
            conn.commit()

            # Handle photo uploads and classification
            photos = request.files.getlist('photos')
            for photo in photos:
                if photo and photo.filename and allowed_file(photo.filename):
                    try:
                        # Validate file
                        photo.seek(0, 2)  # Seek to end
                        file_size = photo.tell()
                        photo.seek(0)  # Reset to beginning
                        
                        if file_size > 10 * 1024 * 1024:  # 10MB limit per photo
                            flash(f'Photo {photo.filename} is too large (max 10MB)')
                            continue
                        
                        # Generate secure filename
                        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
                        secure_name = secure_filename(photo.filename)
                        fname = f"photo_{rpt_id}_{timestamp}_{secure_name}"
                        ppath = os.path.join(UPLOAD_FOLDER, fname)
                        
                        # Save photo
                        photo.save(ppath)
                        
                        # Insert photo record
                        cur2 = conn.execute(
                            'INSERT INTO photos(report_id,file_path) VALUES(?,?)',
                            (rpt_id, ppath)
                        )
                        photo_id = cur2.lastrowid
                        
                        # Analyze photo
                        try:
                            res = model.predict(source=ppath, save=False)
                            vio = analyze_detections(res)
                            conn.execute(
                                'INSERT INTO photo_classifications(photo_id,results_json) VALUES(?,?)',
                                (photo_id, json.dumps(vio))
                            )
                        except Exception as e:
                            # Log error but continue - photo is saved even if analysis fails
                            print(f"Error analyzing photo {fname}: {str(e)}")
                            conn.execute(
                                'INSERT INTO photo_classifications(photo_id,results_json) VALUES(?,?)',
                                (photo_id, json.dumps(['Analysis failed']))
                            )
                    except Exception as e:
                        flash(f'Error processing photo {photo.filename}: {str(e)}')
                        continue

            conn.commit()
            conn.close()
            
            flash('Report submitted successfully!')
            return redirect(url_for('report'))
            
        except Exception as e:
            flash(f'Error submitting report: {str(e)}')
            return redirect(url_for('report'))
    
    else:
        return jsonify(error="Method not allowed"), 405

if __name__ == '__main__':
    app.run(debug=True)