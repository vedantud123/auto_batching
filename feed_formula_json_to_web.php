<?php
date_default_timezone_set('Asia/Kolkata');
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Feed Formula Comparison</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    th, td { white-space: nowrap; } /* Sidebar */
    /* Sidebar */
    .sidebar {
      width: 180px;
      background-color: #2c3e50;
      color: #fff;
      display: flex;
      flex-direction: column;
      padding-top: 15px;
      position: fixed;
      left: 0; top: 0; bottom: 0;
      box-shadow: 2px 0 10px rgba(0,0,0,0.2);
    }
    .sidebar h2 {
      text-align: center;
      margin-bottom: 20px;
      font-size: 16px;
      color: #ecf0f1;
    }
    .sidebar a {
      padding: 8px 12px;
      text-decoration: none;
      color: #ecf0f1;
      font-size: 13px;
      transition: all 0.3s;
    }
    .sidebar a:hover {
      background-color: #34495e;
      padding-left: 20px;
    }

    /* Main Content */
    .main-content {
      margin-left: 180px; /* match sidebar width */
      flex: 1;
      padding: 40px;
      overflow-y: auto;
    }

    .main-content h2 {
      margin-bottom: 20px;
      color: #2c3e50;
      font-size: 28px;
    }.modal-close-btn {
      position: absolute;
      top: 10px;
      right: 10px;
      background-color: #e74c3c;
      color: white;
      border: none;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      font-size: 20px;
      font-weight: bold;
      cursor: pointer;
      box-shadow: 0 2px 6px rgba(0,0,0,0.2);
      transition: background-color 0.3s ease;
    }
    .modal-close-btn:hover {
      background-color: #c0392b;
    }

  </style>
</head>
<body class="bg-[#ADD8E6] text-gray-800 min-h-screen font-sans m-0">
<div class="flex h-screen">
     <div class="sidebar">
      <h2>Dashboard</h2>
      <a href="http://localhost:8080/php/index.php">🏠 Home</a>
      <a href="http://localhost:8080/php/shead_config.php">⚙️ Configuration</a>
      <a href="http://localhost:8080/php/feed_formula_json_to_web.php">📊 Feed Formula</a>
      <a href="http://localhost:8080/php/report.php">📊 Report</a>
      <a href="https://sunfra.com/">💬 Support</a>
    </div>


  <div class="main-content flex-1 p-6 overflow-auto">
    <div class="flex justify-between items-center mb-4">
      <div></div>
      <button onclick="handleUpdateClick()" class="bg-gradient-to-r from-green-400 to-green-600 hover:from-green-500 hover:to-green-700 text-white font-semibold px-5 py-2 rounded-xl shadow-md transition duration-300">
	🔄 Update
      </button>
    </div>

    <h1 class="text-4xl font-bold text-center mb-12 text-blue-700 drop-shadow">🐥 Feed Formula Overview</h1>

    <div id="feed-formula-table" class="mb-16"></div>
    <div id="feed-medicine-table"></div>

  <div id="updateModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 hidden">
    <div class="bg-[#ADD8E6] p-6 rounded-lg shadow-2xl max-w-4xl w-full h-[80vh] overflow-auto relative">

      <button type="button" id="addNewMaterialBtn" class="mb-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded">
	+ Add New Material
      </button>

      <div class="flex justify-between items-center mb-4 relative">
	<h2 class="text-2xl font-bold text-blue-700">🛠 Update Feed Data</h2>
	<button 
	  onclick="closeModal()" 
	  class="absolute top-0 right-0 transform translate-x-2 -translate-y-2 
		 bg-red-500 text-white hover:bg-red-600 rounded-full w-8 h-8 
		 flex items-center justify-center text-lg font-bold shadow-md transition">
	  &times;
	</button>
      </div>

      <form id="updateForm">
	<div id="modalContent" class="space-y-6"></div>
	<div class="mt-6 flex justify-end">
	  <button type="submit" class="bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded-lg font-semibold shadow-md">
	    💾 Save Changes
	  </button>
	</div>
      </form>
    </div>
  </div>

  <div id="newMaterialModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] hidden">
    <div class="bg-white p-6 rounded-lg shadow-2xl max-w-md w-full relative">
      <div class="flex justify-between items-center mb-4">
	<h3 class="text-xl font-semibold text-blue-700">Add New Material</h3>
	<button onclick="closeNewMaterialModal()" class="text-gray-500 hover:text-red-500 text-xl font-bold">&times;</button>
      </div>
      <form id="newMaterialForm">
	<div class="mb-4">
	  <label class="block font-medium text-gray-700 mb-1" for="newMaterialType">Type</label>
	  <select id="newMaterialType" name="type" required class="w-full px-3 py-2 border border-gray-400 rounded-md">
	    <option value="" disabled selected>Select Type</option>
	    <option value="Feed_Formula">Feed Formula</option>
	    <option value="Feed_Medicine">Feed Medicine</option>
	  </select>
	</div>
	<div class="mb-4">
	  <label class="block font-medium text-gray-700 mb-1" for="newMaterialName">Material Name</label>
	  <select id="newMaterialName" name="material" required class="w-full px-3 py-2 border border-gray-400 rounded-md">
		    <option value="" disabled selected>Select Material</option>
		  </select>
	</div>
	<div class="flex justify-end">
	  <button type="submit" class="bg-green-600 hover:bg-green-700 text-white px-5 py-2 rounded font-semibold">
	    Add Material
	  </button>
	</div>
      </form>
    </div>
  </div>
</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/js/all.min.js" defer></script>
<script>
const clientId = 1;
let originalData = [];
window.handleUpdateClick = async function() {
  try {
    const [data, weeks] = await Promise.all([fetchMainData()]);
    console.log("Fetched data:", data);
    console.log("Fetched weeks:", weeks);
    openModal(data, weeks);
  } catch (error) {
    console.error("Error fetching data or weeks:", error);
    alert("Failed to load data for editing.");
  }
};

async function fetchMainData() {
  const res = await fetch(`http://localhost:8080/php/feed_formula_json.php?client_id=1`);
  const json = await res.json();
  return json[clientId] || [];
}

function extractAllMaterials(data, type) {
  if (!Array.isArray(data)) {
    console.error("extractAllMaterials was called with data:", data);
    return [];
  }
  const materials = new Set();
  data.forEach(shead => {
    const sheadKey = Object.keys(shead)[0];
    const items = shead[sheadKey][type] || {};
    Object.keys(items).forEach(mat => materials.add(mat));
  });
  return Array.from(materials).sort();
}


function generateTable(data, type, title, containerId) {
  const materials = extractAllMaterials(data, type);
  const sheads = data.map(shead => Object.keys(shead)[0]);

  let table = `<h2 class="text-3xl font-semibold text-blue-600 mb-6">${title}</h2>`;
  table += `
    <div class="overflow-auto rounded-lg shadow-xl border border-gray-300 bg-white">
      <table class="min-w-full text-sm text-gray-700 table-fixed">
        <thead class="bg-blue-100 sticky top-0 z-10">
        <tr>
          <th class="p-3 text-left font-semibold border border-gray-300 bg-blue-100">Material</th>`;
  sheads.forEach(shead => {
    table += `<th class="p-3 text-center font-semibold border border-gray-300 bg-blue-100">${shead.replace('_', ' ').toUpperCase()}</th>`;
  });
  table += `</tr></thead><tbody>`;

  materials.forEach(material => {
    table += `<tr class="hover:bg-blue-50 transition-all">
      <td class="p-3 border border-gray-300 font-medium text-blue-800 bg-white">${material}</td>`;
    data.forEach(shead => {
      const sheadKey = Object.keys(shead)[0];
      const items = shead[sheadKey][type] || {};
      const value = items[material] ?? "-";
      table += `<td class="p-3 text-center border border-gray-300 bold bg-white">${value}</td>`;
    });
    table += `</tr>`;
  });

  table += `</tbody></table></div>`;
  document.getElementById(containerId).innerHTML = table;
}


async function renderTables() {
  const [data, weeks] = await Promise.all([
    fetchMainData(),
  ]);
  generateTable(data, "Feed_Formula", "Feed Formula", "feed-formula-table");
  generateTable(data, "Feed_Medicine", "Feed Medicine", "feed-medicine-table");
}

function openModal(data, weeks) {
  originalData = data;
  const container = document.getElementById("modalContent");
  container.innerHTML = "";

  const sheads = data.map(sheadObj => Object.keys(sheadObj)[0]);

  let feedFormulaMaterials = new Set();
  let feedMedicineMaterials = new Set();

  data.forEach(sheadObj => {
    const sheadKey = Object.keys(sheadObj)[0];
    const feedFormula = sheadObj[sheadKey]["Feed_Formula"] || {};
    const feedMedicine = sheadObj[sheadKey]["Feed_Medicine"] || {};

    Object.keys(feedFormula).forEach(m => feedFormulaMaterials.add(m));
    Object.keys(feedMedicine).forEach(m => feedMedicineMaterials.add(m));
  });

  feedFormulaMaterials = Array.from(feedFormulaMaterials).sort();
  feedMedicineMaterials = Array.from(feedMedicineMaterials).sort();

  function generateEditableTable(title, typeMaterials, type) {
    let tableHtml = `
  <h4 class="text-xl font-semibold text-blue-700 mb-3">${title}</h4>
  <div class="overflow-auto border border-gray-300 rounded bg-white shadow-md mb-8">
    <table class="min-w-full text-gray-800 text-sm table-fixed">
      <thead class="bg-blue-100 sticky top-0 z-10">
       <tr>
          <th class="border border-gray-300 p-2 text-left font-semibold">Material</th>`;

    sheads.forEach(shead => {
      tableHtml += `<th class="border border-gray-300 p-2 text-center font-semibold">${shead.toUpperCase()}</th>`;
    });

    tableHtml += `</tr></thead><tbody>`;

    typeMaterials.forEach(material => {
      tableHtml += `<tr class="hover:bg-blue-50 transition-all">
        <td class="border border-gray-300 p-2 font-medium">${material}</td>`;

      sheads.forEach(shead => {
        const currSheadData = data.find(d => Object.keys(d)[0] === shead);
        let val = "";
        if (currSheadData && currSheadData[shead][type]) {
          val = currSheadData[shead][type][material];
          if (val === undefined || val === null) val = "";
        }
        const inputId = `${shead}_${type}_${material}`.replace(/\s+/g, "_");
        tableHtml += `<td class="border border-gray-300 p-1 text-center">
          <input type="number" step="0.01" id="${inputId}" data-shead="${shead}" data-type="${type}" data-material="${material}" value="${val}" 
            class="w-full px-1 py-1 text-center border border-gray-300 rounded focus:outline-none focus:ring 
            ${type === 'Feed_Formula' ? 'focus:ring-blue-300' : 'focus:ring-purple-300'}" />
        </td>`;
      });

      tableHtml += `</tr>`;
    });

    tableHtml += `</tbody></table></div>`;

    return tableHtml;
  }

  container.innerHTML += generateEditableTable("Feed Formula", feedFormulaMaterials, "Feed_Formula");
  container.innerHTML += generateEditableTable("Feed Medicine", feedMedicineMaterials, "Feed_Medicine");
  document.getElementById("updateModal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("updateModal").classList.add("hidden");
}

function closeNewMaterialModal() {
  document.getElementById("newMaterialModal").classList.add("hidden");
  document.getElementById("newMaterialForm").reset();
}

document.getElementById("addNewMaterialBtn").addEventListener("click", async () => {
  await populateMaterialSelect();  
  document.getElementById("newMaterialModal").classList.remove("hidden");
});

document.getElementById("newMaterialForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const type = document.getElementById("newMaterialType").value;
  const material = document.getElementById("newMaterialName").value.trim();

  if (!type || !material) {
    alert("Please select type and enter material name.");
    return;
  }

  try {
    const apiMaterials = await fetchAvailableRawMaterials();

    const isInApi = apiMaterials.includes(material);
    if (!isInApi) {
      alert(`❌ "${material}" is not a valid material from raw materials list.`);
      return;
    }

    const currentData = originalData; // Already available globally
    const allCurrentMaterials = new Set();

    currentData.forEach(sheadObj => {
      const sheadKey = Object.keys(sheadObj)[0];
      const items = sheadObj[sheadKey][type] || {};
      Object.keys(items).forEach(mat => allCurrentMaterials.add(mat.trim()));
    });

    if (allCurrentMaterials.has(material)) {
      alert(`⚠️ "${material}" already exists in the current feed data.`);
      return;
    }

    const res = await fetch("http://localhost:8080/php/feed_formula_new_material.php", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, type, material }),
    });

    const result = await res.json();

    if (result.success || (result.message && result.message.toLowerCase().includes("success"))) {
      alert(result.message || "Material added successfully!");
      closeNewMaterialModal();

      const [data, weeks] = await Promise.all([fetchMainData()]);
      openModal(data, weeks);
    } else {
      alert(result.message || "Failed to add material.");
    }
  } catch (error) {
    alert("❌ Error adding material.");
    console.error(error);
  }
});

document.getElementById("updateForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const updated = originalData.map(sheadObj => {
    const sheadKey = Object.keys(sheadObj)[0];
    const original = sheadObj[sheadKey];
    const newFormula = {};
    const newMedicine = {};

    for (let mat in original["Feed_Formula"] || {}) {
      const inputId = `${sheadKey}_Feed_Formula_${mat}`.replace(/\s+/g, "_");
      const input = document.getElementById(inputId);
      if (input) {
        newFormula[mat] = parseFloat(input.value) || 0;
      }
    }

    for (let med in original["Feed_Medicine"] || {}) {
      const inputId = `${sheadKey}_Feed_Medicine_${med}`.replace(/\s+/g, "_");
      const input = document.getElementById(inputId);
      if (input) {
        newMedicine[med] = parseFloat(input.value) || 0;
      }
    }

    return {
      [sheadKey]: {
        "Feed_Formula": newFormula,
        "Feed_Medicine": newMedicine
      }
    };
  });

  try {
    const res = await fetch("http://localhost:8080/php/feed_formula_update.php", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, data: updated })
    });
    const result = await res.json();

    alert(result.message || "✅ Data updated successfully!");
    closeModal();
    renderTables();
  } catch (err) {
    alert("❌ Error saving data");
    console.error(err);
  }
});

async function fetchAvailableRawMaterials() {
  const res = await fetch(`http://localhost:8080/php/feed_raw_material_json.php?client_id=1`);
  const json = await res.json();
  const rawMaterials = json[clientId] || [];

  return rawMaterials
    .filter(item => item.type === "Feed_Medicine" || item.type === "Feed_Formula")
    .map(item => item.name.trim());
}

async function populateMaterialSelect() {
  const materials = await fetchAvailableRawMaterials();

  const select = document.getElementById("newMaterialName");
  if (!select) return;

  select.innerHTML = '<option value="" disabled selected>Select Material</option>'; 

  materials.forEach(mat => {
    const option = document.createElement("option");
    option.value = mat;
    option.textContent = mat;
    select.appendChild(option);
  });
}
fetchAvailableRawMaterials();
populateMaterialSelect();
renderTables();
</script>

</body>
</html>
