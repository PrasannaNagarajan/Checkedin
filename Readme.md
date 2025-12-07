CloudCheckIn: Serverless QR Attendance System

CloudCheckIn is a modern, cloud-native application designed to revolutionize university attendance tracking. Built on a fully serverless architecture in AWS, the system replaces paper sign-in sheets and roll calls with dynamic QR codes, real-time logging, and automated analytics.

❓ Problem & Solution
The Problem

Traditional attendance methods are inefficient:

Calling names wastes class time

Paper sheets are unreliable

Students can sign in for absent peers (“buddy punching”)

Professors lack real-time attendance insights

The Solution

CloudCheckIn delivers a seamless digital workflow:

Professors generate a unique QR code for each class session.

Students scan the QR code with their phones to instantly check in.

The System logs attendance in real time, sends notifications, and provides analytics.

🌟 Features & Perks
👨‍🏫 Professor Experience

Real-Time Dashboard to monitor attendance as students check in.

Course Management: Add, delete, and switch between multiple classes.

Analytics Graphing: Click any date to see student-level attendance for that session.

Automated Email Alerts via Amazon SNS when students check in.

Zero Maintenance thanks to fully serverless AWS infrastructure.

🧑‍🎓 Student Experience

Fast Check-In by scanning the projected QR code.

Instant Confirmation via a large green checkmark.

Personal Attendance History stored persistently.

Secure Authentication through University email enforcement using AWS Cognito.

⚙️ Critical Configuration (Before Deployment)

⚠️ IMPORTANT — You must configure your professor email in two places.

1. Frontend Config (frontend/logic.js)

Line 3 must contain your professor email:

const PROFESSOR_EMAIL = "your_email@pitt.edu";


This email determines who has Professor Dashboard access.

2. Backend Config (template.yaml)

Update the SNS subscription email endpoint:

MyEmailSubscription:
  Type: AWS::SNS::Subscription
  Properties:
    TopicArn: !Ref AttendanceNotificationTopic
    Protocol: email
    Endpoint: "your_email@pitt.edu"   # <--- UPDATE THIS


This email receives automatic attendance alerts.

🏗️ Architecture Diagram

CloudCheckIn uses a scalable, event-driven, serverless microservices architecture:

graph TD
    %% Users
    Professor[👤 Professor]
    Student[👤 Student]

    %% Frontend & Auth
    subgraph Frontend & Auth
        S3[🪣 Amazon S3\nStatic Web Hosting]
        Cognito[🔐 Amazon Cognito\nUser Pools & JWT]
    end

    %% API
    API[🚪 Amazon API Gateway\nREST API]

    %% Backend Microservices
    subgraph AWS Lambda
        Create[CreateSession]
        Mark[MarkAttendance]
        Analytics[GetCourseDetails]
        History[GetStudentHistory]
        Manage[ManageCourses]
    end

    %% Data/Events
    DDB[(🗄️ Amazon DynamoDB\nSingle-Table Design)]
    SNS[📢 Amazon SNS]
    Email[📧 Email Alert]

    %% Data Flow
    Professor & Student -->|HTTPS| S3
    Professor & Student -->|Auth| Cognito
    Cognito -->|JWT| Professor & Student

    Professor -->|Manage/Generate| API
    Student -->|Scan QR| API

    API --> Create & Mark & Analytics & History & Manage

    Create & Mark & Analytics & History & Manage -->|Read/Write| DDB

    Mark -->|Publish Event| SNS
    SNS -->|Send Email| Email

📝 AWS Service Justification
Compute: AWS Lambda

Chosen over EC2 because:

Attendance spikes briefly at class start

Lambda scales instantly with traffic

Zero idle cost

Database: Amazon DynamoDB

Chosen over RDS because:

Single-digit ms latency needed during check-in bursts

No joins required

Single-table design handles courses, sessions, and attendance efficiently

Authentication: AWS Cognito

Chosen over custom auth because:

Built-in user management, password handling, MFA

Secure JWT tokens for API authorization

Frontend Hosting: Amazon S3

Chosen over EC2/Nginx because:

Frontend is static HTML/JS

No servers, cheaper, and more durable

Notifications: Amazon SNS

Chosen over SMTP email because:

Decoupled event system

Easy to expand to SMS or additional subscribers

Orchestration: AWS SAM / CloudFormation

Chosen because:

Full Infrastructure-as-Code

Enables automated deployments via GitHub Actions

🚀 How to Use
👨‍🏫 Professor Workflow

Log In using the professor email configured in logic.js.

Add Course → saved instantly in DynamoDB.

Generate QR Code for today’s session.

Project QR Code to students.

Analyze Attendance Trends with interactive graphs.

Click a Data Point to see the full student roster for that date.

🧑‍🎓 Student Workflow

Scan QR Code using phone camera.

Log In (first-time users register automatically).

Receive Green Checkmark confirming successful check-in.

Visit My History to view all past attendance records.

🛠️ Deployment Guide
Method 1 — Automated Deployment (Recommended)

Uses GitHub Actions + AWS SAM to deploy automatically.

Push code to main.

GitHub Actions will:

Build backend

Deploy infrastructure using SAM

Sync frontend to S3

GitHub Secrets Required

AWS_ACCESS_KEY_ID

AWS_SECRET_ACCESS_KEY

These allow GitHub Actions to deploy your app to AWS.

📂 Repository Structure
cloudcheckin/
│
├── frontend/
│   ├── logic.js
│   ├── index.html
│   └── styles.css
│
├── backend/
│   ├── create_session.py
│   ├── mark_attendance.py
│   ├── get_course_details.py
│   ├── get_student_history.py
│   └── manage_courses.py
│
├── template.yaml
└── README.md