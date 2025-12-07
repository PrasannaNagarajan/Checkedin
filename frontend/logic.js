// --- CONFIGURATION ---
// REPLACE THIS with your specific email to be the "Professor"
const PROFESSOR_EMAIL = "prn37@pitt.edu"; 

var poolData = { UserPoolId: config.userPoolId, ClientId: config.clientId };
var userPool = new AmazonCognitoIdentity.CognitoUserPool(poolData);
var currentUser = null;

// --- GLOBAL VARS FOR PROFESSOR DASHBOARD ---
let currentCourse = null;
let courseList = [];
let courseDataCache = null; 

// Check if there is a session ID in the URL (Student scanned QR)
const urlParams = new URLSearchParams(window.location.search);
const scannedSessionId = urlParams.get('session');

// --- INITIALIZATION ---
window.onload = function() {
    checkLoginStatus();
    if (scannedSessionId) {
        document.getElementById('auth-message').innerText = "Please log in to mark your attendance.";
    }
};

function checkLoginStatus() {
    var cognitoUser = userPool.getCurrentUser();
    if (cognitoUser != null) {
        cognitoUser.getSession(function(err, session) {
            if (session.isValid()) {
                currentUser = cognitoUser.getUsername();
                handleLoggedInUser(currentUser);
            }
        });
    }
}

function handleLoggedInUser(email) {
    document.getElementById('auth-section').classList.add('hidden');
    document.getElementById('logoutBtn').classList.remove('hidden');

    // ROUTING LOGIC
    if (scannedSessionId) {
        // SCENARIO A: Student scanned a QR code
        document.getElementById('student-view').classList.remove('hidden');
        performAutoAttendance(scannedSessionId, email);
        loadStudentHistory(email); // Load history for student
    } else if (email === PROFESSOR_EMAIL) {
        // SCENARIO B: The Professor Logged In
        document.getElementById('professor-view').classList.remove('hidden');
        initProfessorDashboard(); // <--- UPDATED: Load courses from DB
    } else {
        // SCENARIO C: Student logged in manually
        document.getElementById('student-view').classList.remove('hidden');
        document.getElementById('attendance-status').innerHTML = 
            "<h3>You are logged in.</h3><p>Please scan the class QR code to mark attendance.</p>";
        loadStudentHistory(email); // Load history for student
    }
}

// --- STUDENT FEATURES ---

async function performAutoAttendance(sessionId, email) {
    const statusDiv = document.getElementById('attendance-status');
    statusDiv.innerHTML = "⏳ Marking you present...";

    try {
        const response = await fetch(`${config.apiUrl}/mark-attendance`, {
            method: 'POST',
            body: JSON.stringify({ sessionId: sessionId, email: email })
        });
        const data = await response.json();
        
        statusDiv.innerHTML = `
            <h1 style="font-size: 50px;">✅</h1>
            <h3>You are present!</h3>
            <p>Session ID: ${sessionId}</p>
        `;
    } catch (e) {
        statusDiv.innerHTML = "❌ Error marking attendance. Please try again.";
    }
}

async function loadStudentHistory(email) {
    const list = document.getElementById('history-list');
    list.innerHTML = "<li>Loading...</li>";

    try {
        const response = await fetch(`${config.apiUrl}/student-history?email=${email}`);
        const data = await response.json();

        list.innerHTML = ""; // Clear list
        
        if (data.length === 0) {
            list.innerHTML = "<li>No attendance records found.</li>";
            return;
        }

        data.forEach(item => {
            const li = document.createElement("li");
            li.innerText = `${item.date}: ${item.class}`;
            list.appendChild(li);
        });
    } catch (e) {
        list.innerHTML = "<li style='color:red'>Failed to load history</li>";
    }
}

// --- NEW PROFESSOR DASHBOARD LOGIC (DB CONNECTED) ---

// 1. Initialize Dashboard & Load Courses
async function initProfessorDashboard() {
    try {
        const response = await fetch(`${config.apiUrl}/courses`);
        const data = await response.json();
        
        // Update global list with DB data
        courseList = data;
        renderSidebar();
    } catch (e) {
        console.error("Failed to load courses", e);
    }
}

// 2. Add New Course (To DB)
async function addNewCourse() {
    const name = document.getElementById('newCourseInput').value.trim();
    if(!name) return;

    // Save to DB
    await fetch(`${config.apiUrl}/courses`, {
        method: 'POST',
        body: JSON.stringify({ className: name })
    });

    // Add locally and refresh
    if (!courseList.includes(name)) {
        courseList.push(name);
        renderSidebar();
    }
    document.getElementById('newCourseInput').value = "";
}

// 3. Delete Course (From DB)
async function deleteCourse(event, className) {
    event.stopPropagation(); // Stop click from triggering course selection
    
    if(!confirm(`Are you sure you want to delete ${className}?`)) return;

    // Delete from DB
    await fetch(`${config.apiUrl}/courses`, {
        method: 'DELETE',
        body: JSON.stringify({ className: className })
    });

    // Remove locally
    courseList = courseList.filter(c => c !== className);
    
    // If we deleted the currently active course, reset the view
    if (currentCourse === className) {
        currentCourse = null;
        document.getElementById('course-actions').classList.add('hidden');
        document.getElementById('selected-course-title').innerText = "Select a Course";
    }

    renderSidebar();
}

// 4. Render Sidebar (With Delete Buttons)
function renderSidebar() {
    const container = document.getElementById('course-list');
    container.innerHTML = "";
    
    if (courseList.length === 0) {
        container.innerHTML = "<div style='padding:10px; color:#666; font-size:0.9em;'>No courses found.<br>Add one below!</div>";
        return;
    }

    courseList.forEach(course => {
        const div = document.createElement("div");
        div.className = `course-item ${currentCourse === course ? 'course-active' : ''}`;
        
        // Layout: Name on left, Delete 'X' on right
        div.style.display = "flex";
        div.style.justifyContent = "space-between";
        div.style.alignItems = "center";
        
        div.innerHTML = `
            <span>${course}</span>
            <span onclick="deleteCourse(event, '${course}')" 
                  style="color:red; font-weight:bold; padding:0 5px; cursor:pointer;"
                  title="Delete Class">
                  &times;
            </span>
        `;
        
        // Click handler for selecting the course (ignores clicks on the X)
        div.onclick = (e) => {
            if(e.target.innerText !== "×") loadCourseData(course);
        };
        
        container.appendChild(div);
    });
}

// 5. Load Data for Selected Course
async function loadCourseData(className) {
    currentCourse = className;
    renderSidebar(); // Update highlight
    
    document.getElementById('selected-course-title').innerText = className;
    document.getElementById('course-actions').classList.remove('hidden');
    document.getElementById('day-detail-box').classList.add('hidden');

    // Fetch Details from Backend
    const response = await fetch(`${config.apiUrl}/course-details?className=${className}`);
    const data = await response.json();
    courseDataCache = data; // Save for click interaction

    // Render Roster Table
    const tbody = document.getElementById('roster-body');
    tbody.innerHTML = "";
    data.roster.forEach(student => {
        const tr = document.createElement("tr");
        const color = student.ratio < 50 ? 'red' : 'black'; // Alert if attendance is low
        
        tr.innerHTML = `
            <td>${student.email}</td>
            <td>${student.attended}</td>
            <td>${student.total}</td>
            <td style="color:${color}; font-weight:bold;">${student.ratio}%</td>
        `;
        tbody.appendChild(tr);
    });

    // Render Chart
    renderChart(data.graphLabels, data.graphData);
}

// 6. Render Chart with Click Handler
function renderChart(labels, counts) {
    const ctx = document.getElementById('courseChart').getContext('2d');
    if (window.myChart) window.myChart.destroy();

    window.myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Students Present',
                data: counts,
                borderColor: '#007bff',
                backgroundColor: 'rgba(0, 123, 255, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            onClick: (e) => {
                const points = window.myChart.getElementsAtEventForMode(e, 'nearest', { intersect: true }, true);
                if (points.length) {
                    const index = points[0].index;
                    const dateClicked = labels[index];
                    showDayDetails(dateClicked);
                }
            }
        }
    });
}

function showDayDetails(date) {
    const students = courseDataCache.dailyDetails[date] || [];
    document.getElementById('day-detail-box').classList.remove('hidden');
    document.getElementById('detail-date').innerText = date;
    
    if (students.length === 0) {
        document.getElementById('detail-list').innerText = "No students recorded.";
    } else {
        document.getElementById('detail-list').innerText = students.join(", ");
    }
}

// 7. Generate QR (Popup Modal)
let activeSessionId = null;

async function openQrModal() {
    if(!currentCourse) return;
    
    // Only create a NEW session if we don't have one yet
    if (!activeSessionId) {
        const response = await fetch(`${config.apiUrl}/create-session`, {
            method: 'POST',
            body: JSON.stringify({ className: currentCourse })
        });
        const data = await response.json();
        activeSessionId = data.sessionId; // Save it!
    }
    
    // Use the saved ID
    const magicUrl = `${window.location.origin}${window.location.pathname}?session=${activeSessionId}`;
    
    document.getElementById('qr-modal').classList.remove('hidden');
    document.getElementById('qr-course-name').innerText = currentCourse;
    document.getElementById('qr-display-modal').innerHTML = "";
    new QRCode(document.getElementById("qr-display-modal"), magicUrl);
    
    // Only refresh data if it was a new session
    setTimeout(() => loadCourseData(currentCourse), 1000);
}

// --- AUTH FUNCTIONS (UNCHANGED) ---

function signUp() {
    // FIX: Force Lowercase and trim
    var email = document.getElementById('email').value.toLowerCase().trim();
    var password = document.getElementById('password').value;
    
    var attributeList = [new AmazonCognitoIdentity.CognitoUserAttribute({ Name: 'email', Value: email })];
    userPool.signUp(email, password, attributeList, null, function(err, result) {
        if (err) { alert(err.message || JSON.stringify(err)); return; }
        alert('Registered! Check your email for the code.');
        document.getElementById('confirm-box').classList.remove('hidden');
    });
}

function confirmUser() {
    // FIX: Force Lowercase and trim
    var email = document.getElementById('email').value.toLowerCase().trim();
    var code = document.getElementById('code').value.trim();
    
    var cognitoUser = new AmazonCognitoIdentity.CognitoUser({ Username: email, Pool: userPool });
    cognitoUser.confirmRegistration(code, true, function(err, result) {
        if (err) { alert(err); return; }
        alert('Confirmed! Please Sign In.');
    });
}

function signIn() {
    // FIX: Force Lowercase and trim
    var email = document.getElementById('email').value.toLowerCase().trim();
    var password = document.getElementById('password').value;
    
    var authDetails = new AmazonCognitoIdentity.AuthenticationDetails({ Username: email, Password: password });
    var cognitoUser = new AmazonCognitoIdentity.CognitoUser({ Username: email, Pool: userPool });

    cognitoUser.authenticateUser(authDetails, {
        onSuccess: function(result) {
            currentUser = email;
            handleLoggedInUser(email);
        },
        onFailure: function(err) { alert(err.message); }
    });
}

function signOut() {
    var cognitoUser = userPool.getCurrentUser();
    if (cognitoUser != null) cognitoUser.signOut();
    location.href = window.location.pathname; // Reload
}

// --- DRAGGABLE MODAL LOGIC ---

makeDraggable(document.getElementById("draggable-modal"));

function closeModal() {
    document.getElementById('qr-modal').classList.add('hidden');
    const modal = document.getElementById("draggable-modal");
    modal.style.top = "";
    modal.style.left = "";
}

function makeDraggable(elmnt) {
  var pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
  
  if (document.getElementById(elmnt.id + "header")) {
    document.getElementById(elmnt.id + "header").onmousedown = dragMouseDown;
  } else {
    elmnt.onmousedown = dragMouseDown;
  }

  function dragMouseDown(e) {
    e = e || window.event;
    e.preventDefault();
    pos3 = e.clientX;
    pos4 = e.clientY;
    document.onmouseup = closeDragElement;
    document.onmousemove = elementDrag;
  }

  function elementDrag(e) {
    e = e || window.event;
    e.preventDefault();
    pos1 = pos3 - e.clientX;
    pos2 = pos4 - e.clientY;
    pos3 = e.clientX;
    pos4 = e.clientY;
    elmnt.style.top = (elmnt.offsetTop - pos2) + "px";
    elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
  }

  function closeDragElement() {
    document.onmouseup = null;
    document.onmousemove = null;
  }
}