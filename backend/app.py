import json
import boto3
import os
import uuid
from datetime import datetime

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
    student_email = body.get('email') # Coming from Cognito in Frontend
    
    
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
    """
    Finds all classes a specific student has attended.
    """
    student_email = event['queryStringParameters']['email']

    # Scan for records where SK matches the student email
    # (In a real production app, we would use a GSI, but Scan is fine here)
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
    
# --- ADD THIS TO THE BOTTOM OF app.py ---

def get_course_details(event, context):
    """
    Returns EVERYTHING for a specific course:
    1. Trend Data (Dates vs Count)
    2. Student Roster with Calculation (Present / Total Sessions)
    3. Detailed list of who attended which specific session.
    """
    target_class = event['queryStringParameters']['className']
    
    # 1. Scan everything (In production, use Query with GSI)
    response = table.scan()
    items = response.get('Items', [])

    # Containers
    sessions = []      # List of all session IDs for this class
    session_dates = {} # Map SessionID -> Date
    attendance = []    # List of all attendance records for this class
    
    # 2. Filter Raw Data
    for item in items:
        # Is it a Session Metadata record for THIS class?
        if item.get('SK') == 'METADATA' and item.get('ClassName') == target_class:
            sess_id = item['PK'].replace('SESSION#', '')
            date_str = item.get('CreatedAt', '').split('T')[0]
            sessions.append(sess_id)
            session_dates[sess_id] = date_str
            
        # Is it an Attendance record for THIS class?
        elif item.get('Type') == 'Attendance' and item.get('ClassName') == target_class:
            attendance.append(item)

    # 3. Calculate Trends (Graph Data)
    # Group attendance by SessionID
    daily_counts = {sess_id: 0 for sess_id in sessions}
    daily_rosters = {sess_id: [] for sess_id in sessions} # Who attended each day

    for record in attendance:
        sess_id = record['PK'].replace('SESSION#', '')
        email = record.get('Email', 'Unknown')
        
        if sess_id in daily_counts:
            daily_counts[sess_id] += 1
            daily_rosters[sess_id].append(email)

    # 4. Calculate Student Ratios
    # Total Sessions for this class
    total_sessions_count = len(sessions)
    student_stats = {} # Email -> Count

    for record in attendance:
        email = record.get('Email')
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

    # 5. Format Graph Data (Sorted by Date)
    # Sort sessions by date so the graph goes Left -> Right correctly
    sorted_sessions = sorted(sessions, key=lambda s: session_dates.get(s, ''))
    
    graph_labels = [session_dates[s] for s in sorted_sessions]
    graph_data = [daily_counts[s] for s in sorted_sessions]
    
    # Map Date -> List of Students (for the "Click on Day" feature)
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