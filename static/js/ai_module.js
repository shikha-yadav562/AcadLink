// ============================================================
// AcadLink AI Assignment Module — JS Interactions
// Author: Shikha Yadav
// ============================================================

// ------------------------------
// Populate assignment dropdown
// ------------------------------



function populateAssignmentSelect(assignments) {
  const select = document.getElementById("assignment_id");
  if (!select) return;
  select.innerHTML = `<option value="">-- Choose Assignment --</option>`;
  assignments.forEach((a) => {
    if (!a.my_submission_id) {
      const option = document.createElement("option");
      option.value = a.assignment_id;
      option.textContent = `${a.title} (${a.subject})`;
      select.appendChild(option);
    }
  });
}

// ------------------------------
// Refresh Student Submissions (table + dropdown)
// ------------------------------
async function refreshStudentSubmissions() {
  try {
    const res = await fetch("/api/student_submissions");
    const data = await res.json();

    const table = document.getElementById("submission_table");
    if (!table) return;

    let html = "";
    data.forEach((s) => {
      const score =
        s.ai_score !== null ? (s.ai_score * 100).toFixed(1) + "%" : "-";
      const statusColor =
        s.status === "verified"
          ? "text-green-600"
          : s.status === "rejected"
          ? "text-red-600"
          : "text-yellow-600";
      html += `
        <tr>
          <td class="px-6 py-4">${s.title}</td>
          <td class="px-6 py-4">${score}</td>
          <td class="px-6 py-4 ${statusColor}">${s.status || "-"}</td>
        </tr>`;
    });
    table.innerHTML = html;

    populateAssignmentSelect(data);
  } catch (err) {
    console.error("❌ Error loading student submissions:", err);
    showToast("Failed to load submissions.", "error");
  }
}

// ------------------------------
// Submit assignment (Student)
// ------------------------------
async function submitAssignment() {
  const assignmentSelect = document.getElementById("assignment_id");
  const fileInput = document.getElementById("file");
  const assignment_id = assignmentSelect?.value;
  const file = fileInput?.files[0];

  if (!assignment_id || !file) {
    showToast("Please select an assignment and upload a file.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("assignment_id", assignment_id);
  formData.append("file", file);

  try {
    const res = await fetch("/submit_assignment_ai", {
      method: "POST",
      body: formData,
    });

    console.log("Raw server response:", res.status);
    const data = await res.json();
    console.log("Parsed response:", data);

    if (data.success) {
      showToast("✅ Assignment submitted successfully!", "success");
      assignmentSelect.value = "";
      fileInput.value = "";
      refreshStudentSubmissions();
    } else {
      showToast(data.error || "Submission failed.", "error");
    }
  } catch (err) {
    console.error("Upload error:", err);
    showToast("Network or server error!", "error");
  }
}

// ------------------------------
// Toast Notification Utility
// ------------------------------
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className =
    "fixed bottom-5 right-5 z-50 px-4 py-2 rounded-lg shadow-lg text-white text-sm " +
    (type === "success"
      ? "bg-green-600"
      : type === "error"
      ? "bg-red-600"
      : "bg-indigo-600");

  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 500);
  }, 3000);
}

// ------------------------------
// AJAX Helper (Reusable)
// ------------------------------
async function postJSON(url, data) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return await res.json();
  } catch (err) {
    console.error("Error:", err);
    showToast("Network error!", "error");
  }
}

// ------------------------------
// Faculty Actions (Verify / Reject)
// ------------------------------
async function verifySubmission(subId) {
  const res = await fetch(`/verify_assignment/${subId}`, { method: "POST" });
  const data = await res.json();
  if (data.success) {
    showToast("✅ Assignment verified successfully!", "success");
    refreshFacultyTable();
  } else {
    showToast("Error verifying submission.", "error");
  }
}

async function rejectSubmission(subId) {
  const res = await fetch(`/reject_assignment/${subId}`, { method: "POST" });
  const data = await res.json();
  if (data.success) {
    showToast("❌ Submission rejected.", "error");
    refreshFacultyTable();
  } else {
    showToast("Error rejecting submission.", "error");
  }
}

// ------------------------------
// Faculty Table Refresh
// ------------------------------
async function refreshFacultyTable() {
  const table = document.querySelector("#faculty-submissions");
  if (!table) return;

  const res = await fetch("/api/faculty_submissions");
  const data = await res.json();

  let html = "";
  data.forEach((s) => {
    const score = s.ai_score ? (s.ai_score * 100).toFixed(1) + "%" : "-";
    html += `
      <tr>
        <td class="px-6 py-4">${s.roll_no}</td>
        <td class="px-6 py-4">${s.title}</td>
        <td class="px-6 py-4">${score}</td>
        <td class="px-6 py-4 ${s.status === "verified"
          ? "text-green-600"
          : s.status === "rejected"
          ? "text-red-600"
          : "text-yellow-600"}">${s.status}</td>
        <td class="px-6 py-4 flex space-x-2">
          <button onclick="verifySubmission(${s.id})" 
            class="bg-green-500 text-white px-3 py-1 rounded hover:bg-green-600">
            <i class="fas fa-check"></i>
          </button>
          <button onclick="rejectSubmission(${s.id})" 
            class="bg-red-500 text-white px-3 py-1 rounded hover:bg-red-600">
            <i class="fas fa-times"></i>
          </button>
        </td>
      </tr>`;
  });

  table.innerHTML = html;
}

// ------------------------------
// Auto Refresh (Student Page)
// ------------------------------
document.addEventListener("DOMContentLoaded", () => {
  // Only initialize if submission table exists
  if (document.getElementById("submission_table")) {
    refreshStudentSubmissions();
    setInterval(refreshStudentSubmissions, 10000);
  }

  // For faculty view
  if (document.getElementById("faculty-submissions")) {
    refreshFacultyTable();
    setInterval(refreshFacultyTable, 15000);
  }
});


// ------------------------------
// Real-Time Notifications (Student)
// ------------------------------
async function checkNotifications() {
  try {
    const res = await fetch("/api/student_notifications");
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) {
      data.forEach((n) => showToast(n.message, "info"));
    }
  } catch (err) {
    console.error("Notification check failed:", err);
  }
}

// 🔁 Automatically check every 15 seconds
setInterval(() => {
  // Only run for student page
  if (document.getElementById("submission_table")) {
    checkNotifications();
  }
}, 15000);