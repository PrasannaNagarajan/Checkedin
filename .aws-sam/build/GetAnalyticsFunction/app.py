import json
import boto3
import os
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
table = dynamodb.Table(os.environ['TABLE_NAME'])
sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')

def create_session(event, context):
    """
    Professor calls this to create a class session.
    Returns a unique Session ID (which becomes the QR code data).
    """
    body = json.loads(event['body'])
    class_name = body.get('className')
    session_id = str(uuid.uuid4())[:8] # Short unique ID
    timestamp = datetime.utcnow().isoformat()

    # Store session in DynamoDB
    table.put_item(
        Item={
            'PK': f"SESSION#{session_id}",
            'SK': "METADATA",
            'ClassName': class_name,
            'CreatedAt': timestamp,
            'Type': 'Session'
        }
    )

    return {
        'statusCode': 200,
        'headers': { "Access-Control-Allow-Origin": "*" },
        'body': json.dumps({'sessionId': session_id, 'message': 'Session Created'})
    }

def mark_attendance(event, context):
    """
    Student scans QR code. This function runs.
    """
    body = json.loads(event['body'])
    session_id = body.get('sessionId')
    student_email = body.get('email').lower().strip() # Coming from Cognito in Frontend
    
    
    timestamp = datetime.utcnow().isoformat()
    
    session_meta = table.get_item(Key={'PK': f"SESSION#{session_id}", 'SK': 'METADATA'})
    class_name = session_meta.get('Item', {}).get('ClassName', 'Unknown Class')

    # 1. Save attendance record
    table.put_item(
        Item={
            'PK': f"SESSION#{session_id}",
            'SK': f"STUDENT#{student_email}",
            'Email': student_email,
            'Timestamp': timestamp,
            'ClassName': class_name,
            'Type': 'Attendance'
        }
    )

    # 2. Publish to SNS (Service 7 usage!)
    # In real life, you might check if they already scanned to avoid spam
    sns.publish(
        TopicArn=sns_topic_arn,
        Message=f"Student {student_email} checked into session {session_id}",
        Subject="New Attendance Record"
    )

    return {
        'statusCode': 200,
        'headers': { "Access-Control-Allow-Origin": "*" },
        'body': json.dumps({'message': 'Attendance Marked!'})
    }
    
def get_analytics(event, context):
    """
    Returns data for the Professor Dashboard.
    1. List of all sessions.
    2. Count of students per session (for the graph).
    """
    # SECURITY: In a real app, check the JWT token here. 
    # For this project, we will rely on the Frontend to hide this, 
    # but strictly speaking, you should check event['requestContext'] for the user's email.

    try:
        # Scan is okay for small class projects. In production, use Query with an Index.
        response = table.scan(
            FilterExpression=Attr('Type').eq('Attendance')
        )
        items = response.get('Items', [])

        # Process data for the Graph
        # We want to group by Session ID (or Date) and count students
        session_stats = {}
        
        for item in items:
            # We assume PK is "SESSION#<id>"
            sess_id = item['PK'].replace('SESSION#', '')
            if sess_id not in session_stats:
                session_stats[sess_id] = 0
            session_stats[sess_id] += 1

        # Format for Chart.js (Labels = Session IDs, Data = Counts)
        chart_data = {
            "labels": list(session_stats.keys()),
            "data": list(session_stats.values())
        }

        return {
            'statusCode': 200,
            'headers': { "Access-Control-Allow-Origin": "*" },
            'body': json.dumps(chart_data)
        }
    except Exception as e:
        return {'statusCode': 500, 'body': str(e)}
    
def get_student_history(event, context):
    try:
        # Get email safely
        params = event.get('queryStringParameters') or {}
        student_email = params.get('email', '').lower().strip()

        if not student_email:
            return {
                'statusCode': 400, 
                'headers': { "Access-Control-Allow-Origin": "*" }, 
                'body': 'Missing email'
            }

        # This was crashing because 'Attr' wasn't imported
        response = table.scan(
            FilterExpression=Attr('SK').eq(f"STUDENT#{student_email}")
        )
        
        history = []
        for item in response.get('Items', []):
            history.append({
                'class': item.get('ClassName', 'Unknown'),
                'date': item.get('Timestamp', '').split('T')[0]
            })

        return {
            'statusCode': 200,
            'headers': { "Access-Control-Allow-Origin": "*" },
            'body': json.dumps(history)
        }

    except Exception as e:
        print(f"ERROR: {str(e)}")
        # --- FIX 3: ADD HEADERS HERE SO YOU SEE THE REAL ERROR NEXT TIME ---
        return {
            'statusCode': 500, 
            'headers': { "Access-Control-Allow-Origin": "*" }, 
            'body': json.dumps({"error": str(e)})
        }
    
# --- ADD THIS TO THE BOTTOM OF app.py ---

def get_course_details(event, context):
    """
    Robust Analytics: Links Students to Classes via Session ID.
    Fixes issues where old data might be missing the 'ClassName' tag.
    """
    try:
        # Get target class (e.g., "CS1660")
        params = event.get('queryStringParameters') or {}
        target_class = params.get('className', '')
        
        # Scan everything
        response = table.scan()
        items = response.get('Items', [])

        # --- PASS 1: Find all Sessions that belong to this Class ---
        valid_sessions = set()       # Set of PKs (e.g. "SESSION#abc")
        session_dates = {}           # Map SessionID -> Date
        
        for item in items:
            if item.get('SK') == 'METADATA' and item.get('ClassName') == target_class:
                valid_sessions.add(item['PK'])
                
                # Format Date
                sess_id = item['PK'].replace('SESSION#', '')
                raw_date = item.get('CreatedAt', '')
                short_date = raw_date.split('T')[0] if 'T' in raw_date else raw_date
                session_dates[sess_id] = short_date

        # --- PASS 2: Find Students inside those Sessions ---
        attendance = []
        for item in items:
            # We check if the record's PK is in our valid_sessions list
            # This works even if the student record is missing 'ClassName'
            if item.get('Type') == 'Attendance' and item.get('PK') in valid_sessions:
                attendance.append(item)

        # --- PASS 3: Calculate Stats (Same as before) ---
        
        # Trends
        daily_counts = {sess_id: 0 for sess_id in session_dates.keys()}
        daily_rosters = {sess_id: [] for sess_id in session_dates.keys()}

        for record in attendance:
            sess_id = record['PK'].replace('SESSION#', '')
            email = record.get('Email', 'Unknown')
            
            if sess_id in daily_counts:
                daily_counts[sess_id] += 1
                daily_rosters[sess_id].append(email)

        # Ratios
        total_sessions_count = len(valid_sessions)
        student_stats = {} 

        for record in attendance:
            email = record.get('Email', '').lower().strip() # Normalize
            if email not in student_stats:
                student_stats[email] = 0
            student_stats[email] += 1
        
        # Format Roster List
        roster_data = []
        for email, count in student_stats.items():
            ratio = 0
            if total_sessions_count > 0:
                ratio = round((count / total_sessions_count) * 100, 1)
            
            roster_data.append({
                "email": email,
                "attended": count,
                "total": total_sessions_count,
                "ratio": ratio
            })

        # Format Graph Data (Sorted by Date)
        sorted_sessions = sorted(session_dates.keys(), key=lambda s: session_dates[s])
        
        graph_labels = [session_dates[s] for s in sorted_sessions]
        graph_data = [daily_counts[s] for s in sorted_sessions]
        
        detail_map = {}
        for s in sorted_sessions:
            date = session_dates[s]
            detail_map[date] = daily_rosters[s]

        return {
            'statusCode': 200,
            'headers': { "Access-Control-Allow-Origin": "*" },
            'body': json.dumps({
                "graphLabels": graph_labels,
                "graphData": graph_data,
                "roster": roster_data,
                "dailyDetails": detail_map
            })
        }

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {'statusCode': 500, 'headers': { "Access-Control-Allow-Origin": "*" }, 'body': str(e)}
    
def manage_courses(event, context):
    """
    Handles GET (List), POST (Add), DELETE (Remove) for Courses.
    PK: COURSE#<ClassName>
    SK: METADATA
    """
    method = event['httpMethod']
    
    try:
        # 1. GET: List all courses
        if method == 'GET':
            # Scan for all items that are Course Metadata
            # (In a real app, use a GSI, but Scan is fine here)
            response = table.scan(
                FilterExpression=Attr('PK').begins_with('COURSE#') & Attr('SK').eq('METADATA')
            )
            courses = [item['ClassName'] for item in response.get('Items', [])]
            return {
                'statusCode': 200,
                'headers': { "Access-Control-Allow-Origin": "*" },
                'body': json.dumps(courses)
            }

        # 2. POST: Add a new course
        elif method == 'POST':
            body = json.loads(event['body'])
            class_name = body.get('className')
            
            table.put_item(
                Item={
                    'PK': f"COURSE#{class_name}",
                    'SK': "METADATA",
                    'ClassName': class_name,
                    'Type': 'CourseMeta'
                }
            )
            return {
                'statusCode': 200,
                'headers': { "Access-Control-Allow-Origin": "*" },
                'body': json.dumps({'message': 'Course added'})
            }

        # 3. DELETE: Remove a course
        elif method == 'DELETE':
            body = json.loads(event['body'])
            class_name = body.get('className')
            
            table.delete_item(
                Key={
                    'PK': f"COURSE#{class_name}",
                    'SK': "METADATA"
                }
            )
            return {
                'statusCode': 200,
                'headers': { "Access-Control-Allow-Origin": "*" },
                'body': json.dumps({'message': 'Course deleted'})
            }

    except Exception as e:
        return {'statusCode': 500, 'body': str(e)}